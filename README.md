# Physical AI Leaderboard — Worker Agent

Federated GPU worker for the **Physical AI Leaderboard**. Runs on a
partner school's GPU host, pulls student submissions from the central
plane over long-poll, executes the Isaac Sim rollout locally, and
reports results back. Student zip bytes never traverse the central
plane — data locality is enforced by design.

Central URL defaults to **`https://hcislab.ddns.net/`** throughout this
document; override with `CENTRAL_API_URL` in `.env` if your deployment
lives elsewhere.

---

## Table of contents

1. [Overview](#1-overview)
2. [System Requirements](#2-system-requirements)
3. [Prerequisites](#3-prerequisites)
4. [Installation](#4-installation)
5. [Configuration](#5-configuration)
6. [Startup](#6-startup)
7. [Usage](#7-usage)
8. [Project Structure](#8-project-structure)
9. [Troubleshooting](#9-troubleshooting)
10. [FAQ](#10-faq)

---

## 1. Overview

The worker agent is a small FastAPI service + a background loop:

- **Register + heartbeat** to central with a one-shot join token
- **Long-poll** central for QUEUED submissions in the school's queue
- **Receive uploads** from student browsers directly (presigned URL flow)
- **Run rollouts** — Isaac Sim in `real` mode, synthetic in `mock` mode
- **Report results** back to central; central aggregates the leaderboard

Assignment is **pull-only**. Central never opens a connection to your
worker. Every online worker for your school hits
`POST /api/workers/next-job`; whichever asks first while free gets the
oldest QUEUED submission. No dispatcher, cron, or coordinator is needed
on the school side.

```
學生瀏覽器 ─► central: POST /api/submissions (取得 presigned URL)
        │
        ▼ 用中央發的 URL
你們的 worker: POST /upload/{token}  ← 學生 zip 直接進來，不經過中央
        │
        ▼
中央: notify submission ready
        │
        ▼ (worker long-poll)
你們的 worker: POST /api/workers/next-job → 拿到工作 → Isaac Sim → 回報結果
        │
        ▼
中央更新 leaderboard，顯示於各學校 Observability
```

Central never sees the student's zip bytes. Privacy + bandwidth are
handled locally by each participating school.

---

## 2. System Requirements

| Requirement | Notes |
|---|---|
| OS | Ubuntu 20.04 / 22.04 (tested); other Linux likely works |
| CPU / RAM | 4 core / 8 GB minimum |
| GPU | 1 per worker; not needed for `EVAL_MODE=mock` |
| NVIDIA driver | **570+** for `real` mode. The prebuilt image runs CUDA 12.8; driver 550 only ships up to CUDA 12.4. Consumer GPUs (RTX 3090/4090/5090) have **no forward-compat** and will hard-fail with `CUDA error 804` if the driver is older. |
| Docker Engine | 20.10+ |
| Docker Compose plugin | v2 (`docker compose version` works) |
| `nvidia-container-toolkit` | Only for `EVAL_MODE=real` |
| Free host port | One per worker; `setup.sh` picks from `8081..8181` |
| Disk | ≥30 GB per worker. Isaac Sim's Omniverse asset cache (`/root/.cache/ov`) grows to 10–20 GB, plus student zips + recordings |
| Public URL | Students' browsers must reach `{WORKER_PUBLIC_URL}/upload/{token}` — usually a reverse proxy in front of the worker's host port |

**Omniverse asset cache**: the container mounts a docker volume
`worker_ov_cache` at `/root/.cache/ov`. First `real` boot downloads
multi-GB USD assets from S3 (can take 30+ min on slow networks). The
cache persists across restarts. Only `docker compose down -v` wipes
it — **don't do that casually**.

---

## 3. Prerequisites

Before you start, make sure you have:

1. **A `SCHOOL_ADMIN` account on central.** If you don't have one,
   email `hcislab03@gmail.com` with:
   - Your school name (Chinese + English)
   - Contact person + email
   - Rough count of student groups you plan to enroll
2. **Docker + Docker Compose plugin** installed on the GPU host.
   Verify with `docker version` and `docker compose version`.
3. **For `real` mode: NVIDIA driver 570+** and `nvidia-container-toolkit`.
   Verify with:
   ```bash
   nvidia-smi   # driver version at the top
   docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
   ```
4. **A reachable public URL** for the worker (e.g.
   `https://gpu-01.your-school.edu.tw`). Typically achieved with an
   HTTPS reverse proxy (nginx / Caddy) forwarding to the worker's host
   port. Direct-exposing the host port without TLS is possible but
   discouraged.

`./setup.sh` re-runs these checks at the top and prints exactly what's
missing.

---

## 4. Installation

Two supported paths for getting this code onto the GPU host.

### Option A — clone the standalone worker repo (recommended)

Central maintainers publish this directory as its own repo at
`https://github.com/HCIS-Lab/aicapstone-worker.git`. Schools only see
the worker code, never the central plane.

```bash
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu0
cd worker-gpu0
./setup.sh
```

### Option B — sparse-checkout of the central repo

If a second repo isn't wanted:

```bash
git clone --filter=blob:none --sparse https://github.com/HCIS-Lab/aicapstone-leaderboard.git
cd aicapstone-leaderboard
git sparse-checkout set worker_agent
cd worker_agent
./setup.sh
```

Downside: `git ls-tree` still reveals the full central file list.
Prefer A.

### Option C — tarball release (offline installs)

For schools behind firewalls that can't reach GitHub:

```bash
# on the central side, release maintainer runs:
tar czf aicapstone-worker-$(date +%Y%m%d).tgz -C worker_agent \
  --exclude='__pycache__' --exclude='.env' --exclude='.env.*' .

# school operator receives the tarball:
mkdir aicapstone-worker && tar xzf aicapstone-worker-*.tgz -C aicapstone-worker
cd aicapstone-worker
./setup.sh
```

### For central maintainers: publishing the subtree

```bash
# from the central repo root
git subtree split --prefix=worker_agent -b _worker-split
git push -f git@github.com:HCIS-Lab/aicapstone-worker.git _worker-split:main
git branch -D _worker-split
```

Or use the `publish-worker` Makefile target if the repo defines one.

---

## 5. Configuration

`setup.sh` writes `.env` for you. Full reference in
[`.env.example`](./.env.example); the important knobs:

| Var | Default | Notes |
|---|---|---|
| `CENTRAL_API_URL` | `https://hcislab.ddns.net` | Central FastAPI base URL |
| `WORKER_JOIN_TOKEN` | *(required first boot)* | One-shot from central; after registration the machine JWT is cached and this can be removed |
| `WORKER_NAME` | `$(hostname)` | Shown in admin **Workers** tab |
| `WORKER_PUBLIC_URL` | *(no default)* | External URL for `/upload` — must be reachable from student browsers |
| `WORKER_HOST_PORT` | auto-picked | First free port in `8081..8181` |
| `EVAL_MODE` | `real` | `mock` \| `real` |
| `ISAAC_SIM_SCRIPT_PATH` | `/aicapstone/scripts/rollout.py` | `real` mode only |
| `WORKER_STORAGE_ROOT` | `/var/lib/worker-agent/storage` | Docker volume `worker_storage` |
| `WORKER_STATE_DIR` | `/var/lib/worker-agent/state` | Docker volume `worker_state` |
| `HEARTBEAT_INTERVAL_SEC` | `30` | Central marks stale after 60s |
| `JOB_POLL_INTERVAL_SEC` | `10` | Idle backoff |
| `MAX_CONCURRENT_EVALS` | `1` | Serial rollouts |
| `ALLOWED_TASK_KEYS` | *(empty = all)* | Restrict this worker to specific tasks |
| `HF_TOKEN` | *(empty)* | Optional. HuggingFace read-scope token — removes the anonymous rate limit that lerobot policy weights hit on first eval. Get one at `https://huggingface.co/settings/tokens`. |

**To change any setting after install**: edit `.env`, then
`docker compose restart`. Never edit files inside the running
container — they're lost on restart.

---

## 6. Startup

### Step 1 — Get a join token from central

1. Log into `https://hcislab.ddns.net/admin/dashboard` as your school's
   `SCHOOL_ADMIN`.
2. Go to the **Workers** tab (only visible to `SCHOOL_ADMIN` /
   `SUPERUSER`; if you don't see it, contact HCIS-Lab).
3. Click **+ Issue Join Token** and fill:

   | Field | Recommended |
   |---|---|
   | TTL (minutes) | `30` — enough to finish `setup.sh` |
   | Max uses | 1 per GPU on this host |
   | Note | Free-text, appears in audit log |

4. **The token is shown once.** Copy it immediately.

One token can be redeemed `max_uses` times. Use one `max_uses=3` token
for a three-GPU host, not three separate tokens.

### Step 2 — Run `setup.sh`

Interactive (recommended first time):

```bash
./setup.sh
```

It asks for four things (press Enter to accept each default):

| Prompt | Default |
|---|---|
| Central plane URL | `https://hcislab.ddns.net` |
| Worker name | `$(hostname)` — e.g. `nthu-gpu0` |
| Join token | *(paste from Step 1)* |
| Worker public URL | *(no default)* |
| Eval mode | `mock` for first boot; switch to `real` once verified |
| HuggingFace token | Optional; skip if you don't have one yet |

Fully non-interactive form:

```bash
./setup.sh --yes \
  --central=https://hcislab.ddns.net \
  --token=<JOIN_TOKEN> \
  --public-url=https://gpu-01.your-school.edu.tw \
  --name=gpu-01 \
  --mode=mock
```

What `setup.sh` does end-to-end:

1. Verifies docker + docker compose + (for `real`) `nvidia-container-toolkit`
2. Auto-picks a free GPU (scanning `nvidia-smi` and other worker containers)
3. Auto-picks a free host port in `8081..8181`
4. Names the container `worker-agent-<port>` so a second run on the same
   host won't collide
5. Writes `.env`, `docker compose up -d`
6. Waits for local `/health` on the picked port
7. Tails the log until it sees `registered as worker <id>`

Confirm success in central's **Observability** tab — the worker should
appear as **ONLINE** within 30 seconds.

### Step 3 — Multiple workers on the same host

Any number of workers on one machine, each with its own GPU, port,
container, and `.env`:

```bash
# First GPU
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu0
cd worker-gpu0 && ./setup.sh          # picks GPU 0, port 8081
cd ..

# Second GPU — same host, same join token, separate clone
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu1
cd worker-gpu1 && ./setup.sh          # picks GPU 1, port 8082
```

Both workers register under the same join token (as long as its
`max_uses` isn't exhausted) and appear as separate rows in central's
**Observability** tab. Each clone owns its own `worker_state` /
`worker_storage` / `worker_ov_cache` volumes — deleting one clone
doesn't touch the other.

### Step 4 — Switch from `mock` to `real`

```bash
sed -i 's/^EVAL_MODE=.*/EVAL_MODE=real/' .env
docker compose up -d --force-recreate
```

Confirm the driver is new enough (`nvidia-smi` should print
`Driver Version: 570.xxx.xx` or newer). If not, see
[Troubleshooting §9 → `CUDA error 804`](#9-troubleshooting).

---

## 7. Usage

Everything below runs from inside the worker clone directory.

### Day-2 operations

```bash
./setup.sh --status           # docker ps + last 20 log lines + /health probe
docker compose logs -f        # live tail
docker compose restart        # apply a .env change
docker compose down           # stop container (volumes kept)
docker compose down -v        # stop AND delete storage / state / OV cache
./setup.sh --reset --yes      # = down -v + re-register from a new token
```

### Watching a school's queue from central

Log into `SCHOOL_ADMIN` → **Observability** tab. You see only your own
school's data (SUPERUSER sees cross-school).

- **Workers card** — status, GPU id, heartbeat latency, current job
- **Queued** — student submissions not yet picked up
- **Running now** — in-flight rollouts + which worker owns each
- **Recent outcomes (24h)** — success/failure list. Failures carry a
  color-coded **who-to-contact** badge (`STUDENT` / `SCHOOL_OPS` /
  `CENTRAL_OPS`) so you can tell at a glance whether the fix is on
  your side, the student's, or ours.

### Removing a worker

- **Temporary**: `docker compose down` — keeps volumes, comes back on `up -d`.
- **Permanent**: from central's **Workers** tab, mark the worker
  **REVOKED**. Its next heartbeat will 401 and the agent exits. Then
  `docker compose down -v` on the host to reclaim disk. To re-add
  later, issue a fresh join token and run `./setup.sh --reset --yes`.

---

## 8. Project Structure

### Source layout

```
worker_agent/
├── README.md              ← you are here
├── .env.example           ← configuration reference
├── setup.sh               ← one-command installer / status / reset
├── docker-compose.yml     ← service + volume declarations
├── Dockerfile             ← mock-mode image
├── Dockerfile.real        ← real-mode image (Isaac Sim + IsaacLab baked in)
├── requirements.txt
├── main.py                ← agent entrypoint (heartbeat + poll loop)
├── server.py              ← FastAPI service exposing /health /upload /video
├── config.py              ← env-var parsing + validation
├── central_client.py      ← typed HTTP client for CENTRAL_API_URL
└── rollout.py             ← eval driver (mock + real Popen streaming)
```

### On-disk layout (inside the container)

```
/var/lib/worker-agent/
├── storage/                       # WORKER_STORAGE_ROOT
│   ├── submissions/
│   │   └── sid=<id>/
│   │       ├── pretrained_model.zip
│   │       ├── extracted/          (rmtree'd after rollout)
│   │       └── eval_video.mp4
│   └── tokens/
│       └── <token_hash>.json
└── state/                          # WORKER_STATE_DIR
    ├── machine_jwt                 # cached long-lived JWT
    └── worker_id                   # our numeric worker id
```

### Docker volumes

| Volume | Contents | Impact if cleared |
|---|---|---|
| `worker_storage` | Student zips, staged workdirs, recordings | In-progress evals lose their files; reported scores unaffected |
| `worker_state` | machine JWT + worker id | Must re-register with a fresh join token |
| `worker_ov_cache` | Isaac Sim S3 asset cache | First `real` eval afterwards re-downloads (long) |

### Endpoints

**Agent → Central** (called on `${CENTRAL_API_URL}`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/workers/register` | One-shot with `join_token` |
| POST | `/api/workers/heartbeat` | Every 30s |
| POST | `/api/workers/next-job` | Long-poll for work |
| POST | `/api/workers/submissions/{sid}/result` | Terminal report |
| POST | `/api/submissions/{sid}/upload-complete` | After receiving a student zip |

**Student / admin → Agent** (via `${WORKER_PUBLIC_URL}`):

| Method | Path | Auth |
|---|---|---|
| GET | `/health` | none |
| POST | `/upload/{token}` | Presigned token in URL |
| GET | `/download/{token}` | Presigned token in URL |
| GET | `/video/{token}` | Presigned token in URL |

All tokens are issued by central; the agent never mints its own.

### Auth flow

```
┌──────────────┐    join_token   ┌─────────┐
│ Agent        │────────────────▶│ Central │
│ (WORKER_     │                 │         │
│  JOIN_TOKEN) │◀────────────────│         │  machine_jwt (30d TTL)
└──────┬───────┘                 └─────────┘
       │
       │ machine_jwt cached in WORKER_STATE_DIR
       │
       │ heartbeat, next-job, result  (every request Bearer-authed)
       ▼
```

- Join token is one-shot per redemption and expires after its TTL.
- Machine JWT auto-rotates at heartbeat when within 3 days of expiry.
- Admin can **revoke** a worker; next heartbeat 401s and the agent
  exits. Recovery = new join token + `./setup.sh --reset`.

---

## 9. Troubleshooting

First stop for any weirdness: `docker compose logs -f`.
Second stop: central's **Observability** tab — the failure row's
who-to-contact badge tells you whether it's yours, the student's, or
HCIS-Lab's problem before you read the stack trace.

| Symptom | Likely cause | Fix |
|---|---|---|
| `join token expired` (410) | Past TTL | Issue a new one |
| `join token already exhausted` (409) | Redeem count used up | Issue a new one, or raise `max_uses` next time |
| `unknown or invalid join token` (401) | Typo or revoked | Copy again / issue new |
| Registered but stays `OFFLINE` in central | Heartbeat can't reach central | Check `CENTRAL_API_URL` from the host + network egress |
| Student upload times out | `WORKER_PUBLIC_URL` unreachable from student's network | `curl -I ${WORKER_PUBLIC_URL}/health` from a student's device to confirm |
| Isaac Sim won't start in `real` mode | Missing `nvidia-container-toolkit` | Install it + `sudo systemctl restart docker` |
| `CUDA error 804 forward compatibility was attempted on non supported HW` <br> `Skipping NVIDIA GPU due to CUDA being in bad state` | Host NVIDIA driver too old (usually 550.x). Prebuilt image needs CUDA 12.8 runtime → driver **570+**. Consumer GPUs (RTX 3090/4090/5090) have no forward-compat. | `sudo apt install -y nvidia-driver-570 && sudo reboot`, then confirm `nvidia-smi` shows `Driver Version: 570.xxx.xx` |
| `WORKER_JOIN_TOKEN not set` on boot | Cached JWT missing/corrupt AND no fresh token in `.env` | Issue a new token, put in `.env`, `docker compose restart` |
| Two workers collide on port | `.env` manually edited to a used port | Let `setup.sh` auto-pick, or `./setup.sh --reset` |
| Rollout fails with `nonce framing missing` | Bad checkpoint (mis-matched shapes, corrupt safetensors) | This is a `STUDENT` error — the student should re-verify their model loads with `torch.load` before uploading |
| First `real` eval hangs at "downloading OV assets" | `worker_ov_cache` volume is empty and S3 is slow | Wait (can be 30+ min the first time), or pre-warm the cache from a tarball if you have one |

---

## 10. FAQ

**Q. Do I need to run a backend / database / dispatcher on the school side?**
No. The worker is fully self-contained. It pulls work from central and
reports results — nothing else. Central owns the DB and the queue.

**Q. Can central push a job to us?**
No, by design. Central never opens a connection to your worker. All
work moves via worker-initiated long-poll. This means you don't have
to open inbound ports for central — only for student browser uploads.

**Q. Does the student's zip ever pass through central?**
No. Central issues a presigned URL of the form
`{WORKER_PUBLIC_URL}/upload/{token}` and the browser POSTs the zip
directly to your worker. Central is notified when the upload
completes, but the bytes stay in your school's network.

**Q. What happens if my worker crashes mid-rollout?**
Central sees the heartbeat stop, marks the submission FAILED after a
grace period, and the student can re-submit. There is no automatic
retry on the same worker — if you want that, restart the worker and
use the **Re-run** button in the Submissions tab (only works while the
zip is still on disk, i.e. before central runs its cleanup pass).

**Q. Can I run mock and real workers side-by-side?**
Yes. Different `.env` files → different `EVAL_MODE`. Mock is useful
during setup to prove the network path works before spending time on
Isaac Sim.

**Q. My school has a firewall that blocks outbound HTTPS to arbitrary
hosts. Will it work?**
Only `${CENTRAL_API_URL}` (the central plane) and `huggingface.co`
(policy weights, if the student's policy needs them) must be reachable
from the host. Everything else — Isaac Sim assets, container images —
is baked into the image or already cached.

**Q. What about updates to the Isaac Sim script / task USDs?**
HCIS-Lab republishes the prebuilt image. On your side:
`docker compose pull && docker compose up -d`. No re-registration
needed — the machine JWT survives image swaps.

**Q. How do I retire a worker permanently?**
From central's **Workers** tab, mark it **REVOKED**. Its next
heartbeat 401s and the agent exits. Then on the host,
`docker compose down -v` to reclaim disk.

**Q. Where do I ask for help?**
`hcislab03@gmail.com`, or open an issue against
`HCIS-Lab/aicapstone-worker`. Include:
- `docker compose logs --tail=200 worker-agent-<port>`
- The submission id (visible in central) that's failing
- Your school code
