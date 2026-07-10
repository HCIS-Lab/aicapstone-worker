#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# AI Capstone Leaderboard — Worker Agent one-command installer
#
# Usage:
#   ./setup.sh                              # interactive
#   ./setup.sh --token=<JOIN_TOKEN> \       # non-interactive
#              --public-url=https://gpu-01.school.edu.tw \
#              --name=gpu-01 \
#              --mode=mock \
#              --yes
#   ./setup.sh --reset                      # wipe state + prompt again
#   ./setup.sh --status                     # show current status
#
# What it does:
#   1. Verifies docker + docker compose (+ nvidia if EVAL_MODE=real)
#   2. Prompts for anything not passed as a flag / already in .env
#   3. Writes .env, brings the container up
#   4. Waits for /health locally + confirms registration at central
#
# Idempotent: rerun any time — reuses existing .env if all values are
# present (unless --reset is passed).
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
DEFAULT_CENTRAL_URL="https://leaderboard.hcislab.tw"
CLI_TOKEN=""; CLI_PUBLIC_URL=""; CLI_NAME=""; CLI_MODE=""; CLI_CENTRAL=""
YES=0; RESET=0; STATUS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --token=*)       CLI_TOKEN="${arg#*=}" ;;
    --public-url=*)  CLI_PUBLIC_URL="${arg#*=}" ;;
    --name=*)        CLI_NAME="${arg#*=}" ;;
    --mode=*)        CLI_MODE="${arg#*=}" ;;
    --central=*)     CLI_CENTRAL="${arg#*=}" ;;
    --yes|-y)        YES=1 ;;
    --reset)         RESET=1 ;;
    --status)        STATUS_ONLY=1 ;;
    --help|-h)       sed -n '2,20p' "$0"; exit 0 ;;
    *) die "Unknown flag: $arg (use --help)";;
  esac
done

# ── status-only path: dump state + exit ──────────────────────────────
if (( STATUS_ONLY )); then
  hdr "Worker Agent status"
  docker compose ps 2>/dev/null || die "docker compose not available"
  echo
  say "${DIM}Recent logs:${RST}"
  docker compose logs --tail=20 worker-agent 2>/dev/null || true
  echo
  local_port="$(grep -E '^WORKER_HOST_PORT=' .env 2>/dev/null | cut -d= -f2 || echo 8081)"
  say "${DIM}Local /health:${RST}"
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
  warn "This will stop the container and wipe the cached machine JWT."
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

CENTRAL_URL="${CLI_CENTRAL:-$(env_get CENTRAL_API_URL)}"
JOIN_TOKEN="${CLI_TOKEN:-$(env_get WORKER_JOIN_TOKEN)}"
PUBLIC_URL="${CLI_PUBLIC_URL:-$(env_get WORKER_PUBLIC_URL)}"
WORKER_NAME="${CLI_NAME:-$(env_get WORKER_NAME)}"
MODE="${CLI_MODE:-$(env_get EVAL_MODE)}"

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

# Central URL — production default is fine for most schools
[[ -n "$CENTRAL_URL" ]] || prompt CENTRAL_URL "Central plane URL" "$DEFAULT_CENTRAL_URL"

# Worker name — hostname is a sane default
[[ -n "$WORKER_NAME" ]] || prompt WORKER_NAME "Worker name (shown in admin UI)" "$(hostname -s 2>/dev/null || hostname || echo gpu-node)"

# Join token — cannot default; require it
if [[ -z "$JOIN_TOKEN" ]]; then
  say ""
  say "${DIM}Get a join token from your SCHOOL_ADMIN's admin dashboard:${RST}"
  say "${DIM}  ${CENTRAL_URL}/admin/dashboard → Workers → “+ Issue Join Token”${RST}"
  say ""
  prompt JOIN_TOKEN "Join token"
  [[ -n "$JOIN_TOKEN" ]] || die "join token required"
fi

# Public URL — try to guess a sensible default
if [[ -z "$PUBLIC_URL" ]]; then
  guess="http://$(hostname -f 2>/dev/null || hostname || echo localhost):8081"
  say ""
  say "${DIM}Public URL this worker will be reachable at from a student's browser.${RST}"
  say "${DIM}Must include the port your reverse proxy / port-forward exposes.${RST}"
  prompt PUBLIC_URL "Worker public URL" "$guess"
fi

# Mode — default mock for safe smoke test
[[ -n "$MODE" ]] || prompt MODE "Evaluation mode (mock|real)" "mock"

case "$MODE" in
  mock|real) ;;
  *) die "EVAL_MODE must be 'mock' or 'real' (got '${MODE}')";;
esac

# In real mode, check for NVIDIA runtime
if [[ "$MODE" == "real" ]]; then
  if ! command -v nvidia-smi >/dev/null 2>&1; then
    warn "nvidia-smi not found — real mode needs the NVIDIA driver on the host"
  else
    ok "nvidia-smi present"
  fi
  if ! docker info 2>/dev/null | grep -qi 'nvidia'; then
    warn "Docker doesn't seem to know about the nvidia runtime — install nvidia-container-toolkit"
  else
    ok "nvidia runtime available to docker"
  fi
fi

# Host port. Central-plane dev boxes often already use 8080; default 8081.
HOST_PORT="$(env_get WORKER_HOST_PORT)"; HOST_PORT="${HOST_PORT:-8081}"

# ── 4. write .env atomically ─────────────────────────────────────────
# Only rewrite when we actually gathered new values from a prompt/flag,
# so a returning operator who's added custom fields (e.g. a proxy env
# var) doesn't silently lose them on `./setup.sh` re-runs.
existing_matches=0
if [[ -f .env && \
      "$CENTRAL_URL" == "$(env_get CENTRAL_API_URL)" && \
      "$JOIN_TOKEN"  == "$(env_get WORKER_JOIN_TOKEN)" && \
      "$PUBLIC_URL"  == "$(env_get WORKER_PUBLIC_URL)" && \
      "$WORKER_NAME" == "$(env_get WORKER_NAME)" && \
      "$MODE"        == "$(env_get EVAL_MODE)" ]]; then
  existing_matches=1
fi

if (( existing_matches )); then
  hdr "Reusing existing .env"
  ok "all values unchanged — leaving .env as-is"
else
  hdr "Writing .env"
  TMP="$(mktemp .env.XXXXXX)"
  cat > "$TMP" <<EOF
# Generated by setup.sh on $(date -Iseconds)
CENTRAL_API_URL=${CENTRAL_URL}
WORKER_JOIN_TOKEN=${JOIN_TOKEN}
WORKER_NAME=${WORKER_NAME}
WORKER_PUBLIC_URL=${PUBLIC_URL}

WORKER_STORAGE_ROOT=/var/lib/worker-agent/storage
WORKER_STATE_DIR=/var/lib/worker-agent/state

GPU_ID=0
EVAL_MODE=${MODE}
ISAAC_SIM_SCRIPT_PATH=/aicapstone/scripts/rollout.py

HEARTBEAT_INTERVAL_SEC=30
JOB_POLL_INTERVAL_SEC=10
REQUEST_TIMEOUT_SEC=30
WORKER_PORT=8080
WORKER_HOST_PORT=${HOST_PORT}

MAX_CONCURRENT_EVALS=1
ALLOWED_TASK_KEYS=cup_stacking,cutlery_arrangement,toy_block_collection
EOF
  chmod 600 "$TMP"
  mv "$TMP" .env
  ok ".env written (${HOST_PORT} → 8080)"
fi

# ── 5. build + start ─────────────────────────────────────────────────
hdr "Starting worker container"
docker compose up -d --build
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

# ── 7. confirm central sees us ───────────────────────────────────────
hdr "Waiting for central registration"
# We don't have a machine JWT locally so we can't ask central directly.
# Instead we wait for the agent's own logs to say `registered as worker <id>`,
# which is emitted after the /register or first heartbeat succeeds.
found=0
for i in $(seq 1 30); do
  if docker compose logs --tail=200 worker-agent 2>/dev/null | grep -qE 'registered as worker|heartbeat: ok'; then
    found=1
    break
  fi
  sleep 2
done

if (( found )); then
  worker_id="$(docker compose logs --tail=200 worker-agent 2>/dev/null \
    | grep -oE 'registered as worker [0-9]+' | tail -1 | awk '{print $NF}')"
  ok "central acknowledged registration${worker_id:+ (worker #${worker_id})}"
else
  warn "no 'registered'/'heartbeat: ok' line in logs yet — check with:"
  say "    docker compose logs -f worker-agent"
fi

# ── 8. wrap-up ───────────────────────────────────────────────────────
hdr "Done"
say "${GRN}Worker \"${WORKER_NAME}\" is up.${RST}"
say ""
say "Useful commands:"
say "  ${BLU}docker compose logs -f${RST}          tail live logs"
say "  ${BLU}docker compose ps${RST}               container status"
say "  ${BLU}docker compose restart${RST}          restart after a config change"
say "  ${BLU}./setup.sh --status${RST}             one-shot health snapshot"
say "  ${BLU}./setup.sh --reset --yes${RST}        wipe state + start over"
say ""
say "The SCHOOL_ADMIN dashboard on central should now show this worker as ${GRN}ONLINE${RST}."
