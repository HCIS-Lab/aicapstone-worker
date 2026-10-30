# Eval Worker

Self-contained Isaac Sim evaluation server for one GPU. A school installs
it on its own machine and runs everything from a web UI: define eval
tasks, set eval parameters, upload policy zips, follow runs live and
replay recorded videos. It does not connect to any central server, and
the simulator source is in this repository (`sim/`), so nothing else has
to be cloned.

---

## Contents

1. [Requirements](#1-requirements)
2. [Install](#2-install)
3. [Using the UI](#3-using-the-ui)
4. [Configuration](#4-configuration)
5. [Updating](#5-updating)
6. [Project structure](#6-project-structure)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Requirements

| Requirement | Notes |
|---|---|
| OS | Ubuntu 20.04 / 22.04 (tested); other Linux likely works |
| CPU / RAM | 4 core / 16 GB minimum |
| GPU | 1 per worker (RTX-class, ray tracing); not needed for `EVAL_MODE=mock` |
| NVIDIA driver | **570+** (image runs CUDA 12.8). Consumer GPUs (RTX 3090/4090/5090) have no forward-compat and fail with `CUDA error 804` on older drivers |
| Docker Engine | 20.10+ with the Compose v2 plugin (`docker compose version`) |
| `nvidia-container-toolkit` | For `EVAL_MODE=real` |
| Disk | ~60 GB: the image (~50 GB) plus the Omniverse cache, zips and videos |
| Network (build time) | Docker Hub, PyPI, pypi.nvidia.com, download.pytorch.org, GitHub (IsaacLab, leisaac) |
| Network (run time) | `huggingface.co` if a policy downloads base weights |

Check the GPU path before installing:

```bash
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.8.0-base-ubuntu22.04 nvidia-smi
```

---

## 2. Install

```bash
git clone https://github.com/HCIS-Lab/aicapstone-worker.git
cd aicapstone-worker
./setup.sh
```

`setup.sh` asks for a worker name and a UI password (Enter generates
one), picks a free GPU and a free port (8081–8181), writes `.env`, builds
the image **on this machine** and starts it. The first build installs
Isaac Sim + IsaacLab and takes 30–60 min; later builds reuse the cache.

Non-interactive:

```bash
./setup.sh --password='choose-one' --name=gpu-01 --yes
```

When it finishes it prints:

```
Open the eval UI:  http://<host-ip>:8081/
Admin password:    ...
```

**More GPUs on one host:** one clone per GPU (`git clone … worker-gpu1`,
`cd worker-gpu1 && ./setup.sh`); each picks its own GPU, port and
container name.

**Try the UI without a GPU:** `./setup.sh --mode=mock` — same UI, runs
return synthetic scores.

---

## 3. Using the UI

| Tab | What you can do |
|---|---|
| **Runs** | Upload a policy zip, pick the task, optionally override episodes / episode length for this run. Watch the queue, live progress and log; cancel, re-run, delete; replay the recorded video |
| **Tasks** | Built-in tasks are pre-loaded: `cup_stacking`, `cutlery_arrangement`, `toy_blocks_collection`. Add your own by pasting or uploading an eval config `.py`, or by entering any registered gym id. Each task can set its own episodes and episode length |
| **Settings** | Episodes per eval, episode length, total timeout (0 = none), device, action-horizon override, video recording on/off |

Precedence for a run: **run override > task override > Settings**.

**Policy zip:** a LeRobot checkpoint — `config.json`, `model.safetensors`
and the usual `train_config.json` / `policy_preprocessor.json` /
`policy_postprocessor.json`, at the top level or inside one folder
(e.g. `pretrained_model/`). The policy type is read from `config.json`.

**Eval config `.py`:** anything `rollout.py --task=<file.py>` accepts — a
module that registers an IsaacLab task. Start from the built-in tasks in
`sim/packages/simulator/src/simulator/tasks/` (e.g. copy
`cup_stacking/cup_stacking_env_cfg.py`, change the scene, randomisation
or success condition, and register it under a new gym id).

Runs execute one at a time on this worker's GPU, in upload order.

**Security:** the UI is protected only by the admin password over plain
HTTP. Keep the port on the campus network, or put an HTTPS reverse proxy
in front of it.

---

## 4. Configuration

`setup.sh` writes `.env`; full reference in [`.env.example`](./.env.example).

| Var | Default | Notes |
|---|---|---|
| `WORKER_NAME` | hostname | Shown in the UI header |
| `WORKER_ADMIN_PASSWORD` | *(generated)* | UI login. If empty the worker generates one and logs it on start |
| `GPU_ID` | auto-picked | Host GPU index this worker uses |
| `EVAL_MODE` | `real` | `real` \| `mock` |
| `WORKER_HOST_PORT` | auto-picked | Host port of the UI, first free in `8081..8181` |
| `WORKER_CONTAINER_NAME` | `worker-agent-<port>` | Unique per worker on a host |
| `HF_TOKEN` | *(empty)* | Optional HuggingFace read token for policy weight downloads |

Eval parameters (episodes, episode length, timeout, device, video) are
**not** environment variables — they are edited in the UI's Settings tab
and take effect for the next run.

After editing `.env`: `docker compose up -d`.

---

## 5. Updating

```bash
git pull
./setup.sh --yes
```

This rebuilds only what changed (worker code: seconds; `sim/` changes:
from the simulator install on). Tasks, settings, run history, zips and
videos are kept in docker volumes and survive the update.

| Volume | Contents | If deleted |
|---|---|---|
| `worker_state` | `local.db` (tasks, settings, runs), generated password | Custom tasks, settings and history are gone |
| `worker_storage` | Policy zips, logs, videos (`runs/sid=<id>/`) | Re-run and replay no longer possible |
| `worker_ov_cache` | Omniverse asset cache | Next eval re-downloads assets (slow) |

`docker compose down -v` and `./setup.sh --reset` delete all three.

---

## 6. Project structure

```
├── setup.sh               ← installer / status / reset
├── docker-compose.yml     ← service + volumes (real mode)
├── docker-compose.mock.yml← GPU-less override
├── Dockerfile.real        ← Isaac Sim + IsaacLab + sim/ + worker
├── Dockerfile             ← mock-mode image
├── .env.example
├── main.py                ← entry point: HTTP server + run queue thread
├── server.py              ← FastAPI app (/health + UI router)
├── local_ui.py            ← UI page + JSON API + login
├── local_store.py         ← tasks / settings / runs (SQLite)
├── local_runner.py        ← run queue → rollout
├── rollout.py             ← runs sim/scripts/rollout.py, parses the score
├── storage.py             ← on-disk layout
├── config.py              ← env vars
├── frontend/              ← web UI: Vue 3 + Vite + Tailwind, same design as the
│                            leaderboard; built inside the image (no Node on the host)
├── ov-cache.tgz           ← pre-warmed Omniverse cache baked into the image
└── sim/                   ← simulator source
    ├── packages/simulator/    ← tasks, scenes, assets (pip-installed in the image)
    └── scripts/
        ├── rollout.py         ← Isaac Sim evaluation loop
        └── policy_sidecar.py  ← lerobot ≥0.5 policies (Python 3.12 venv)
```

### Changing the UI

```bash
cd frontend
npm ci
VITE_WORKER_URL=http://localhost:8081 npm run dev   # hot reload, API proxied to a running worker
```

Open `http://localhost:5173/`. `./setup.sh --yes` rebuilds the image with
the change (the `ui` stage in the Dockerfiles runs `npm run build`).

IsaacLab is fetched during the build from `github.com/isaac-sim/IsaacLab`
at a pinned commit (`ISAACLAB_COMMIT` in `Dockerfile.real`).

### HTTP endpoints

| Method | Path | Auth |
|---|---|---|
| GET | `/`, `/runs/{id}`, `/tasks`, … | UI (SPA, any non-API path) |
| GET | `/health` | none |
| POST | `/api/login`, `/api/logout` | password → HttpOnly session cookie |
| GET/PUT | `/api/settings`, GET `/api/settings/defaults` | session |
| GET / PUT / DELETE | `/api/tasks`, `/api/tasks/{name}` | session |
| GET / POST | `/api/runs` (POST = multipart upload), GET `/api/runs/{id}` | session |
| GET | `/api/runs/{id}/log`, `/api/runs/{id}/video` | session |
| POST | `/api/runs/{id}/rerun`, `/api/runs/{id}/cancel` | session |
| DELETE | `/api/runs/{id}` | session |

---

## 7. Troubleshooting

First stop: `docker compose logs -f`, then the run's log in the UI.

| Symptom | Likely cause | Fix |
|---|---|---|
| Forgot the UI password | — | `grep WORKER_ADMIN_PASSWORD .env`, or if empty `docker compose logs worker-agent \| grep password` |
| `Docker has no nvidia runtime` in setup | `nvidia-container-toolkit` missing | Install it, `sudo systemctl restart docker` |
| `CUDA error 804 forward compatibility…` | Host driver too old | Install driver 570+, reboot |
| Run fails `could not detect policy_type` | `config.json` has no `type` / `policy_type` | Fix the checkpoint |
| Run fails `nonce framing missing` | Isaac Sim crashed (bad checkpoint, OOM, bad task config) | Read the run log tail in the UI |
| Run fails `eval timed out` | Total timeout in Settings too low for episodes × length | Raise it, or set 0 |
| Custom task fails `does not register a task` / import error | Eval config `.py` problem | Compare with a built-in task in `sim/packages/simulator/src/simulator/tasks/` |
| First eval hangs on asset download | Empty Omniverse cache, slow network | Wait; later runs use the cache |
| Upload fails `zip is missing [...]` | Zip lacks `config.json` / `model.safetensors` | Re-export the checkpoint |
