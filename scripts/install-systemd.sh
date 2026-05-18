#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-${USER}}"
PORT="9090"
HELPER_BIN="/usr/local/bin/singbox-manager-helper"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: scripts/install-systemd.sh [options]

Options:
  --dry-run             Print rendered systemd/sudoers files without installing.
  --user USER           System user that runs the web app. Default: current user.
  --port PORT           Local bind port for uvicorn. Default: 9090.
  --helper-bin PATH     Helper install path. Default: /usr/local/bin/singbox-manager-helper.
  -h, --help            Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --user)
      RUN_USER="${2:?--user requires a value}"
      shift 2
      ;;
    --port)
      PORT="${2:?--port requires a value}"
      shift 2
      ;;
    --helper-bin)
      HELPER_BIN="${2:?--helper-bin requires a value}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$ROOT_DIR"

render_template() {
  local template="$1"
  local safe_user safe_root safe_port safe_helper
  safe_user="$(printf '%s' "$RUN_USER" | sed 's/[&]/\\&/g')"
  safe_root="$(printf '%s' "$ROOT_DIR" | sed 's/[&]/\\&/g')"
  safe_port="$(printf '%s' "$PORT" | sed 's/[&]/\\&/g')"
  safe_helper="$(printf '%s' "$HELPER_BIN" | sed 's/[&]/\\&/g')"
  sed \
    -e "s#__SBM_USER__#${safe_user}#g" \
    -e "s#__SBM_PROJECT_DIR__#${safe_root}#g" \
    -e "s#__SBM_PORT__#${safe_port}#g" \
    -e "s#__SBM_HELPER_BIN__#${safe_helper}#g" \
    "$template"
}

if [[ "$DRY_RUN" == "1" ]]; then
  echo "# Rendered /etc/systemd/system/singbox-manager.service"
  render_template singbox-manager.service
  echo
  echo "# Rendered /etc/sudoers.d/singbox-manager"
  render_template sudoers.d/singbox-manager
  exit 0
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env from .env.example. Review it before using the panel."
else
  chmod 600 .env
fi

make install

service_tmp="$(mktemp)"
sudoers_tmp="$(mktemp)"
trap 'rm -f "$service_tmp" "$sudoers_tmp"' EXIT

render_template singbox-manager.service > "$service_tmp"
render_template sudoers.d/singbox-manager > "$sudoers_tmp"

sudo install -o root -g root -m 755 \
  scripts/singbox-manager-helper \
  "$HELPER_BIN"

sudo install -o root -g root -m 440 \
  "$sudoers_tmp" \
  /etc/sudoers.d/singbox-manager

sudo visudo -c

sudo mkdir -p /etc/sing-box/backups
sudo chown root:root /etc/sing-box /etc/sing-box/backups

sudo install -o root -g root -m 644 \
  "$service_tmp" \
  /etc/systemd/system/singbox-manager.service

sudo systemctl daemon-reload
sudo systemctl enable --now singbox-manager.service
sudo systemctl status singbox-manager.service --no-pager
