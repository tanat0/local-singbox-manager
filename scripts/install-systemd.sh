#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env from .env.example. Review it before using the panel."
else
  chmod 600 .env
fi

make install

sudo install -o root -g root -m 755 \
  scripts/singbox-manager-helper \
  /usr/local/bin/singbox-manager-helper

sudo install -o root -g root -m 440 \
  sudoers.d/singbox-manager \
  /etc/sudoers.d/singbox-manager

sudo visudo -c

sudo mkdir -p /etc/sing-box/backups
sudo chown root:root /etc/sing-box /etc/sing-box/backups

sudo install -o root -g root -m 644 \
  singbox-manager.service \
  /etc/systemd/system/singbox-manager.service

sudo systemctl daemon-reload
sudo systemctl enable --now singbox-manager.service
sudo systemctl status singbox-manager.service --no-pager
