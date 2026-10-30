#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Eval Worker — one-command installer
#
# Usage:
#   ./setup.sh                              # interactive
#   ./setup.sh --password=<UI_PASSWORD> \   # non-interactive
#              --name=gpu-01 \
#              --mode=real \                # real (default) | mock
#              --gpu-id=1 \                 # optional; auto-selected if omitted
#              --hf-token=<HF_TOKEN> \      # optional
#              --yes
#   ./setup.sh --reset                      # wipe everything + prompt again
#   ./setup.sh --status                     # show current status
#
# What it does:
#   1. Verifies docker + docker compose (+ nvidia if EVAL_MODE=real)
#   2. Prompts for anything not passed as a flag / already in .env
#   3. Writes .env, builds the image on this machine (Isaac Sim +
#      simulator from sim/ + worker; first build 30-60 min), starts it
#   4. Waits for /health and prints the UI address + password
#
# Idempotent: rerun any time (e.g. after `git pull`) — reuses .env and
# rebuilds only what changed. --reset starts over.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── colors (skip if not a tty) ───────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD=$'\e[1m'; DIM=$'\e[2m'; RED=$'\e[31m'; GRN=$'\e[32m'
  YLW=$'\e[33m'; BLU=$'\e[34m'; RST=$'\e[0m'
else
  BOLD=''; DIM=''; RED=''; GRN=''; YLW=''; BLU=''; RST=''
fi

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✓%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s⚠%s %s\n' "$YLW" "$RST" "$*"; }
die()  { printf '%s✗ %s%s\n' "$RED" "$*" "$RST" >&2; exit 1; }
hdr()  { printf '\n%s══ %s ══%s\n' "$BOLD" "$*" "$RST"; }

# ── args ─────────────────────────────────────────────────────────────
CLI_NAME=""; CLI_MODE=""; CLI_HF_TOKEN=""; CLI_PASSWORD=""
YES=0; RESET=0; STATUS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --name=*)        CLI_NAME="${arg#*=}" ;;
    --mode=*)        CLI_MODE="${arg#*=}" ;;
    --password=*)    CLI_PASSWORD="${arg#*=}" ;;
    --hf-token=*)    CLI_HF_TOKEN="${arg#*=}" ;;
    --gpu-id=*)      : ;;  # consumed later so `pick_next_gpu` can still auto-detect
    --yes|-y)        YES=1 ;;
    --reset)         RESET=1 ;;
    --status)        STATUS_ONLY=1 ;;
    --help|-h)       sed -n '2,25p' "$0"; exit 0 ;;
    *) die "Unknown flag: $arg (use --help)";;
  esac
done

# ── status-only path: dump state + exit ──────────────────────────────
if (( STATUS_ONLY )); then
  hdr "Eval Worker status"
  docker compose ps 2>/dev/null || die "docker compose not available"
  echo
  say "${DIM}Recent logs:${RST}"
  docker compose logs --tail=20 worker-agent 2>/dev/null || true
  echo
  local_port="$(grep -E '^WORKER_HOST_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8081)"
  say "${DIM}Local /health (port ${local_port:-8081}):${RST}"
  curl -sf "http://localhost:${local_port:-8081}/health" || warn "no /health response"
  exit 0
fi

# ── 1. prereqs ───────────────────────────────────────────────────────
hdr "Checking prerequisites"

command -v docker >/dev/null || die "docker not installed. Install Docker Engine 20.10+ from https://docs.docker.com/engine/install/"
DOCKER_VER="$(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',')"
ok "docker ${DOCKER_VER}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE_VER="$(docker compose version --short 2>/dev/null)"
  ok "docker compose ${COMPOSE_VER}"
else
  die "docker compose plugin missing. Install with your Docker distribution."
fi

command -v curl >/dev/null || die "curl not installed"
ok "curl"

# ── 2. reset if asked ────────────────────────────────────────────────
if (( RESET )); then
  hdr "Reset requested"
  warn "This stops the container and DELETES all tasks, settings, runs, zips and videos."
  if (( ! YES )); then
    read -r -p "Continue? [y/N] " ans
    [[ "${ans,,}" == y* ]] || die "aborted"
  fi
  docker compose down -v 2>/dev/null || true
  rm -f .env
  ok "reset done — will reconfigure from scratch"
fi

# ── 3. read existing .env, then prompt for anything still missing ────
hdr "Configuring worker"

# helper: read a var from .env if it exists
env_get() {
  [[ -f .env ]] || return 0
  grep -E "^${1}=" .env 2>/dev/null | tail -1 | cut -d= -f2- || true
}

WORKER_NAME="${CLI_NAME:-$(env_get WORKER_NAME)}"
MODE="${CLI_MODE:-$(env_get EVAL_MODE)}"
HF_TOKEN_VAL="${CLI_HF_TOKEN:-$(env_get HF_TOKEN)}"
ADMIN_PASSWORD="${CLI_PASSWORD:-$(env_get WORKER_ADMIN_PASSWORD)}"

prompt() {
  # prompt VAR "label" "default"
  local var="$1" label="$2" default="${3:-}" value
  if (( YES )); then
    value="$default"
  else
    if [[ -n "$default" ]]; then
      read -r -p "  ${label} [${default}]: " value
      value="${value:-$default}"
    else
      read -r -p "  ${label}: " value
    fi
  fi
  printf -v "$var" '%s' "$value"
}

# Worker name — hostname is a sane default
[[ -n "$WORKER_NAME" ]] || prompt WORKER_NAME "Worker name (shown in the UI)" "$(hostname -s 2>/dev/null || hostname || echo gpu-node)"

# UI login. Blank → random, printed at the end.
if [[ -z "$ADMIN_PASSWORD" ]]; then
  prompt ADMIN_PASSWORD "UI admin password (Enter = generate one)"
  [[ -n "$ADMIN_PASSWORD" ]] || ADMIN_PASSWORD="$(head -c 12 /dev/urandom | base64 | tr -d '/+=' | cut -c1-16)"
fi

# Mode — real unless asked for a GPU-less UI test.
[[ -n "$MODE" ]] || prompt MODE "Evaluation mode (real|mock)" "real"
case "$MODE" in
  mock|real) ;;
  *) die "EVAL_MODE must be 'mock' or 'real' (got '${MODE}')";;
esac

# HuggingFace token — optional. lerobot policies (multi_task_dit,
# smolvla, pi0, …) download weights from huggingface.co on first use.
# Without a token you're subject to the anonymous rate limit. Any token
# with `read` scope works. Skip with Enter.
if [[ -z "$HF_TOKEN_VAL" ]] && (( ! YES )); then
  say ""
  say "${DIM}Optional — HuggingFace token for lerobot weight downloads.${RST}"
  say "${DIM}Get one at https://huggingface.co/settings/tokens (read scope). Press Enter to skip.${RST}"
  prompt HF_TOKEN_VAL "HF_TOKEN (optional)"
fi

# ── GPU auto-selection ───────────────────────────────────────────────
# Every worker container claims exactly one GPU. When the operator spins
# up a SECOND worker on the same host we should hand it a different card
# automatically so they don't fight over GPU 0.
#
# Strategy:
#   1. If --gpu-id was passed OR .env already has a value, honor it.
#   2. Else list local GPUs via nvidia-smi.
#   3. Subtract the GPUs already claimed by other running worker
#      containers on this host (via `docker ps` + the container env).
#   4. Also subtract GPUs currently running non-worker processes with
#      > 100 MB VRAM (typical Isaac Sim / training runs) so we don't
#      collide with an existing job.
#   5. Pick the lowest-numbered survivor; error out if none.
#   6. In mock mode we skip everything above — no GPU needed.
GPU_ID="$(env_get GPU_ID)"
CLI_GPU_ID=""
for arg in "$@"; do case "$arg" in --gpu-id=*) CLI_GPU_ID="${arg#*=}" ;; esac; done
if [[ -n "$CLI_GPU_ID" ]]; then GPU_ID="$CLI_GPU_ID"; fi

pick_next_gpu() {
  # → prints the chosen id on stdout, empty if none available
  local all_gpus busy_gpus claimed_by_containers occupied candidate
  all_gpus="$(nvidia-smi --query-gpu=index --format=csv,noheader 2>/dev/null | tr -d ' ')"
  [[ -z "$all_gpus" ]] && { echo ""; return 0; }

  # GPUs with active compute contexts (any process, > 100 MB used mem).
  busy_gpus="$(nvidia-smi --query-compute-apps=gpu_uuid,used_memory --format=csv,noheader 2>/dev/null \
    | awk -F', ' 'int($2) > 100 {print $1}' \
    | while read -r uuid; do
        nvidia-smi --query-gpu=index,uuid --format=csv,noheader 2>/dev/null \
          | awk -F', ' -v u="$uuid" '$2 == u {print $1}'
      done)"

  # GPUs already reserved by other worker-agent containers on this host.
  claimed_by_containers="$(docker ps --format '{{.Names}}' 2>/dev/null \
    | while read -r name; do
        docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' "$name" 2>/dev/null \
          | grep -E '^GPU_ID=' | cut -d= -f2
      done | tr -d ' ')"

  occupied="$(printf '%s\n%s\n' "$busy_gpus" "$claimed_by_containers" | sort -u)"

  for candidate in $all_gpus; do
    if ! printf '%s\n' "$occupied" | grep -qx "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done
  echo ""
}

if [[ "$MODE" == "real" && -z "$GPU_ID" ]]; then
  auto_gpu="$(pick_next_gpu)"
  if [[ -n "$auto_gpu" ]]; then
    GPU_ID="$auto_gpu"
    ok "auto-selected GPU_ID=${GPU_ID} (next free card on this host)"
  else
    warn "no free GPU detected — falling back to GPU_ID=0"
    GPU_ID=0
  fi
elif [[ -z "$GPU_ID" ]]; then
  # mock mode → doesn't touch the GPU; a value is still written so the
  # container's rollout script has something to read.
  GPU_ID=0
fi

# In real mode, check for NVIDIA runtime
if [[ "$MODE" == "real" ]]; then
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    warn "nvidia-smi not found — real mode needs the NVIDIA driver on the host"
  else
    ok "nvidia-smi present"
  fi
  if ! docker info 2>/dev/null | grep -qi 'nvidia'; then
    die "Docker has no nvidia runtime — install nvidia-container-toolkit (or use --mode=mock for a GPU-less UI test)"
  else
    ok "nvidia runtime available to docker"
  fi
fi

# ── Host port auto-selection ─────────────────────────────────────────
# Every worker container needs its OWN host port for its UI — two
# workers on the same host can't both bind :8081.
#
# Preference order:
#   1. If .env already has WORKER_HOST_PORT, reuse (so re-runs are
#      idempotent and bookmarks / reverse-proxy config keep working).
#   2. Else walk from 8081 upward and pick the first port that is
#      neither bound on the host nor already declared in ANOTHER
#      worker-agent container's WORKER_HOST_PORT env.
port_in_use() {
  # returns 0 if $1 is bound on the host
  ss -Hltn "sport = :$1" 2>/dev/null | grep -q ":$1"
}
port_claimed_by_container() {
  # returns 0 if some running container was started with WORKER_HOST_PORT=$1
  docker ps --format '{{.Names}}' 2>/dev/null \
    | while read -r n; do
        docker inspect --format='{{range .Config.Env}}{{println .}}{{end}}' "$n" 2>/dev/null \
          | grep -E "^WORKER_HOST_PORT=$1$" && return 0
      done
  return 1
}
pick_free_port() {
  local p=8081
  while :; do
    if ! port_in_use "$p" && ! port_claimed_by_container "$p"; then
      echo "$p"; return 0
    fi
    p=$(( p + 1 ))
    (( p > 8181 )) && { echo ""; return 1; }
  done
}

HOST_PORT="$(env_get WORKER_HOST_PORT)"
if [[ -z "$HOST_PORT" ]]; then
  HOST_PORT="$(pick_free_port)"
  if [[ -n "$HOST_PORT" ]]; then
    ok "auto-selected WORKER_HOST_PORT=${HOST_PORT} (first free in 8081-8181)"
  else
    die "no free port found in 8081-8181 — free one up or pass WORKER_HOST_PORT in .env"
  fi
fi

# Derive a unique container name so two workers on the same host can
# coexist under docker compose.
CONTAINER_NAME="worker-agent-${HOST_PORT}"

# ── 4. write .env atomically ─────────────────────────────────────────
# Only rewrite when something changed, so a returning operator who's
# added custom fields (e.g. a proxy env var) doesn't lose them.
if [[ -f .env && \
      "$WORKER_NAME"    == "$(env_get WORKER_NAME)" && \
      "$MODE"           == "$(env_get EVAL_MODE)" && \
      "$HF_TOKEN_VAL"   == "$(env_get HF_TOKEN)" && \
      "$ADMIN_PASSWORD" == "$(env_get WORKER_ADMIN_PASSWORD)" && \
      "$GPU_ID"         == "$(env_get GPU_ID)" ]]; then
  hdr "Reusing existing .env"
  ok "all values unchanged — leaving .env as-is"
else
  hdr "Writing .env"
  TMP="$(mktemp .env.XXXXXX)"
  cat > "$TMP" <<EOF
# Generated by setup.sh on $(date -Iseconds)
WORKER_NAME=${WORKER_NAME}
WORKER_ADMIN_PASSWORD=${ADMIN_PASSWORD}

GPU_ID=${GPU_ID}
EVAL_MODE=${MODE}
WORKER_HOST_PORT=${HOST_PORT}
# Unique docker container name so multiple workers on one host don't collide.
WORKER_CONTAINER_NAME=${CONTAINER_NAME}
$( [[ "$MODE" == "mock" ]] && echo "COMPOSE_FILE=docker-compose.yml:docker-compose.mock.yml" )

WORKER_STORAGE_ROOT=/var/lib/worker-agent/storage
WORKER_STATE_DIR=/var/lib/worker-agent/state

# Optional HuggingFace token — lerobot policies download weights on
# first eval; a read-scope token avoids the anonymous rate limit.
HF_TOKEN=${HF_TOKEN_VAL}
EOF
  chmod 600 "$TMP"
  mv "$TMP" .env
  ok ".env written (host port ${HOST_PORT} → container 8080, container=${CONTAINER_NAME})"
fi

# ── 5. build + start ─────────────────────────────────────────────────
hdr "Building worker image"
# First real-mode build installs Isaac Sim + IsaacLab (~30 GB, 30-60 min);
# later builds reuse cached layers and only redo what changed.
docker compose build || die "worker image build failed"
hdr "Starting worker container"
docker compose up -d
echo

# ── 6. wait for local /health ────────────────────────────────────────
hdr "Waiting for local health"
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${HOST_PORT}/health" >/dev/null 2>&1; then
    ok "/health OK on http://localhost:${HOST_PORT}"
    break
  fi
  if (( i == 30 )); then
    warn "worker didn't respond on http://localhost:${HOST_PORT}/health after 60s"
    say "${DIM}logs:${RST}"
    docker compose logs --tail=40 worker-agent || true
    die "startup failed"
  fi
  sleep 2
done

# ── 7. wrap-up ───────────────────────────────────────────────────────
hdr "Done"
say "${GRN}Worker \"${WORKER_NAME}\" is up (${MODE} mode).${RST}"
say ""
say "Open the eval UI:  ${BOLD}http://$(hostname -I 2>/dev/null | awk '{print $1}'):${HOST_PORT}/${RST}"
say "Admin login:       ${BOLD}admin${RST} / ${BOLD}${ADMIN_PASSWORD}${RST}   (WORKER_ADMIN_PASSWORD in .env)"
say ""
say "Define tasks + eval settings there, then upload policy zips to evaluate."
say ""
say "Useful commands:"
say "  ${BLU}docker compose logs -f${RST}          tail live logs"
say "  ${BLU}docker compose ps${RST}               container status"
say "  ${BLU}git pull && ./setup.sh --yes${RST}    update to a new release"
say "  ${BLU}./setup.sh --status${RST}             one-shot health snapshot"
say "  ${BLU}./setup.sh --reset --yes${RST}        wipe everything + start over"
