# Worker Agent

Distributed GPU worker for the AI Capstone Leaderboard federated
architecture (Phase 3+4). Runs on a partner school's GPU host and
communicates with the central control plane over HTTP.

## Responsibilities

- **Register + heartbeat** to central with a one-shot join token
- **Long-poll** central for QUEUED submissions in the school's queue
- **Receive uploads** from student browsers directly (presigned URL flow)
- **Run rollouts** (Isaac Sim, or mock mode for smoke testing)
- **Report results** back to central; central aggregates the leaderboard

The central platform never sees the student's zip bytes when this agent
is deployed — data locality is enforced by design.

> **中文版學校端啟動流程 (SCHOOL_ADMIN 主要看這份)** → [STARTUP.md](./STARTUP.md)

## Quick start (one command)

Prereqs on the GPU host: Docker Engine 20.10+, docker compose plugin, curl.
For `EVAL_MODE=real`: NVIDIA driver + `nvidia-container-toolkit`.

```bash
git clone https://github.com/HCIS-Lab/aicapstone-worker.git
cd aicapstone-worker
./setup.sh                # interactive — asks for join token + public URL
```

Or fully non-interactive:

```bash
./setup.sh \
  --central=https://leaderboard.hcislab.tw \
  --token=<JOIN_TOKEN_FROM_CENTRAL> \
  --public-url=https://gpu-01.your-school.edu.tw \
  --name=gpu-01 \
  --mode=mock \
  --yes
```

What `setup.sh` does:
1. verifies docker + docker compose + (optionally) nvidia runtime
2. prompts for anything not passed as a flag (or reuses `.env` on re-run)
3. writes `.env`, builds the image, `docker compose up -d`
4. waits for local `/health`
5. tails the agent log until it sees `registered as worker <id>`

Verify manually anytime with:

```bash
./setup.sh --status               # ps + last 20 log lines + /health probe
docker compose logs -f            # live tail
```

Reset (wipe cached machine JWT + reconfigure):

```bash
./setup.sh --reset
```

## Multiple workers on the same host

You can run any number of workers on one machine — each gets its own
GPU, host port, and container name. The central plane doesn't need to
know how you split them; workers pull work themselves.

**How the assignment actually works (no per-school dispatcher needed):**

1. Students submit at central → central persists the row with
   `status=QUEUED` and tags it with the student's `school_id`.
2. Every online worker for that school long-polls
   `POST /api/workers/next-job`. Whichever worker asks first while free
   gets the oldest QUEUED submission — pure pull architecture, no push
   from central and no coordinator inside the school.
3. Central issues a presigned URL to the student's browser of the form
   `{WORKER_PUBLIC_URL}/upload/{token}` so the zip goes **directly** to
   the worker that will run it — the bytes never traverse central.

The one thing you must give each worker is its **own reachable URL**.
Two workers can't share a port, so `setup.sh` will:

- **Auto-pick a free host port** in `8081..8181`
- **Adjust `WORKER_PUBLIC_URL`** if the guess was `:8081` but a later port was picked
- **Name each container** `worker-agent-<port>` so a second `docker compose up`
  on the same host doesn't error with "name is already in use"

Practical layout for a two-GPU host:

```bash
# First worker
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu0
cd worker-gpu0 && ./setup.sh          # picks GPU 0, port 8081
cd ..

# Second worker (separate clone → separate .env / state volume)
git clone https://github.com/HCIS-Lab/aicapstone-worker.git worker-gpu1
cd worker-gpu1 && ./setup.sh          # picks GPU 1, port 8082
```

Both workers register under the same `SCHOOL_ADMIN` join token and show
up as separate rows in the **Observability** tab.

### Getting a join token

Central issues one from the SCHOOL_ADMIN dashboard:

> `/admin/dashboard` → `Workers` tab → **`+ Issue Join Token`**

The token is one-shot and expires in 15 min. Central swaps it for a
long-lived machine JWT during registration; the JWT lives under
`WORKER_STATE_DIR` (docker volume `worker_state`) and survives restarts.

## Real GPU mode (Isaac Sim)

Set `EVAL_MODE=real` in `.env`, then:

1. **Bind-mount the simulator + task configs** into the container.
   Uncomment the volumes in `docker-compose.yml`:
   ```yaml
   volumes:
     - ../aicapstone:/aicapstone:ro
     - ../private_tasks:/private_tasks:ro
   ```

2. **Enable the NVIDIA runtime**:
   ```yaml
   runtime: nvidia
   environment:
     NVIDIA_VISIBLE_DEVICES: ${GPU_ID:-all}
     NVIDIA_DRIVER_CAPABILITIES: graphics,display,utility,compute
   ```

3. **Rebuild with GPU driver deps** (add to the Dockerfile as needed).

4. **Storage volume** must be big enough for expected submissions
   (~2–5 GB each, kept until admin cleans up).

## File layout on disk

```
/var/lib/worker-agent/
├── storage/                 # WORKER_STORAGE_ROOT
│   ├── submissions/
│   │   └── sid=<id>/
│   │       ├── pretrained_model.zip
│   │       ├── extracted/       (rmtree'd after rollout)
│   │       └── eval_video.mp4
│   └── tokens/
│       └── <token_hash>.json
└── state/                   # WORKER_STATE_DIR
    ├── machine_jwt          # cached long-lived JWT
    └── worker_id            # our numeric worker id
```

## Auth flow

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

- Join token is **one-shot** and expires in 15 min (default).
- Machine JWT rotates automatically at heartbeat when it's within 3 days of
  expiry.
- Admin can **revoke** a worker from the UI → next heartbeat 401s → agent
  re-registers (needs a fresh join token if `WORKER_JOIN_TOKEN` is still
  set, otherwise exits and requires operator action).

## Endpoints (central-facing)

The agent calls these on `${CENTRAL_API_URL}`:

| Method | Path                                    | Notes                        |
|--------|-----------------------------------------|------------------------------|
| POST   | `/api/workers/register`                 | one-shot with join_token     |
| POST   | `/api/workers/heartbeat`                | every 30s                    |
| POST   | `/api/workers/next-job`                 | poll for work                |
| POST   | `/api/workers/submissions/{sid}/result` | terminal report              |
| POST   | `/api/submissions/{sid}/upload-complete`| after receiving student zip  |

## Endpoints (student/admin-facing)

Students' browsers + central `<a href>` links hit these directly:

| Method | Path                    | Auth                     |
|--------|-------------------------|--------------------------|
| GET    | `/health`               | none                     |
| POST   | `/upload/{token}`       | presigned token in URL   |
| GET    | `/download/{token}`     | presigned token in URL   |
| GET    | `/video/{token}`        | presigned token in URL   |

`{token}` values come from central; see the central-side flow in
[`../backend/app/routers/submissions.py`](../backend/app/routers/submissions.py)
`init_submission` and `issue_download_url`.

## Configuration reference

See `.env.example` for the full list. The important ones:

| Var                       | Default                              | Notes |
|---------------------------|--------------------------------------|-------|
| `CENTRAL_API_URL`         | `http://localhost:8001`              | Central FastAPI base URL |
| `WORKER_JOIN_TOKEN`       | (required first boot)                | One-shot from central |
| `WORKER_NAME`             | `$(hostname)`                        | Shown in admin UI |
| `WORKER_PUBLIC_URL`       | `http://$(hostname):8080`            | External URL for `/upload` |
| `EVAL_MODE`               | `mock`                               | `mock` \| `real` |
| `ISAAC_SIM_SCRIPT_PATH`   | `/aicapstone/scripts/rollout.py`     | Real mode only |
| `WORKER_STORAGE_ROOT`     | `/var/lib/worker-agent/storage`      | Persist across container recreation |
| `WORKER_STATE_DIR`        | `/var/lib/worker-agent/state`        | Ditto |
| `HEARTBEAT_INTERVAL_SEC`  | `30`                                 | Central marks stale > 60s |
| `JOB_POLL_INTERVAL_SEC`   | `10`                                 | Backoff when idle |
| `MAX_CONCURRENT_EVALS`    | `1`                                  | Currently the agent runs serially |
| `ALLOWED_TASK_KEYS`       | (empty = all)                        | Restrict to specific tasks |

## Troubleshooting

- **`WORKER_JOIN_TOKEN not set` on boot**
  Cached `machine_jwt` is missing/corrupt AND no fresh join token was
  provided. Issue a new token from central, put it in `.env`, restart.

- **Health probe 200 but worker stays OFFLINE in central**
  Heartbeat is failing silently — check `docker compose logs worker-agent`
  for a network error to `CENTRAL_API_URL`, or a 401 saying the JWT was
  revoked.

- **Student upload times out**
  `WORKER_PUBLIC_URL` isn't reachable from the student's network.
  Check the school firewall + DNS. Central issues the URL at init time;
  the browser needs to reach that host directly.

- **`policy_id mismatch` complained about at central**
  The zip doesn't contain the 5 canonical training files — reject it at
  the source (fix the student's tooling) rather than patching the
  agent.

## Development

```bash
pip install -r requirements.txt
export CENTRAL_API_URL=http://localhost:8001
export WORKER_JOIN_TOKEN=<paste>
export WORKER_STORAGE_ROOT=./_dev_storage
export WORKER_STATE_DIR=./_dev_state
python -m worker_agent.main
```
