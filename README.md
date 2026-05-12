# Sing-Box Manager

Local web UI for managing [sing-box](https://sing-box.sagernet.org/) on Manjaro/Arch Linux.

- Paste a proxy URL → generates, validates, and deploys a sing-box config
- Dashboard with service status, external IP check, and recent logs
- Config backups and one-click restore
- Binds to **127.0.0.1:9090 only**

Supported protocols: `vless://` (Reality / TLS), `hysteria2://`, `hy2://`

---

## Prerequisites

- sing-box 1.13+ installed at `/usr/bin/sing-box`
- sing-box running as `sing-box.service` (systemd)
- Python 3.11+

---

## Install

### 1. Clone / enter project directory

```bash
cd ~/Documents/projects/own/local-singbox-manager
```

### 2. Create virtualenv and install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Install the privileged helper

The helper is the only binary that runs as root. It validates all inputs and
only performs the three whitelisted operations: deploy config, manage service.

```bash
sudo cp scripts/singbox-manager-helper /usr/local/bin/singbox-manager-helper
sudo chmod 755 /usr/local/bin/singbox-manager-helper
sudo chown root:root /usr/local/bin/singbox-manager-helper
```

### 4. Configure sudoers

```bash
sudo cp sudoers.d/singbox-manager /etc/sudoers.d/singbox-manager
sudo chmod 440 /etc/sudoers.d/singbox-manager
sudo visudo -c   # must print "parsed OK"
```

The rule allows only `nikita` to call the helper without a password. Edit the
file if your username differs.

### 5. Run (development)

```bash
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 9090 --reload
```

Open http://127.0.0.1:9090

---

## Run as a systemd service

```bash
# Adjust WorkingDirectory and ExecStart paths in the unit file if needed
sudo cp singbox-manager.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now singbox-manager.service
sudo systemctl status singbox-manager.service
```

---

## Adding your first node

1. Open http://127.0.0.1:9090/nodes
2. Paste a proxy URL in the text box, e.g.:

```
vless://12345678-uuid@78.40.108.81:8443?security=reality&sni=www.bing.com&pbk=PUBLIC_KEY&sid=SHORT_ID&fp=chrome&type=tcp#mynode
```

3. Click **Add / Update Node**
4. Click **Activate** next to the new node
5. The app will: validate → backup current config → deploy → restart sing-box
6. Dashboard shows the new external IP if the VPN is working

---

## How it works

```
Browser → FastAPI (127.0.0.1:9090)
              │
              ├─ parse URL (vless/hy2)
              ├─ generate config JSON (from BASE_CONFIG + active outbound)
              ├─ /usr/bin/sing-box check -c /tmp/...   (no root needed)
              │
              └─ sudo /usr/local/bin/singbox-manager-helper deploy /tmp/...
                       │
                       ├─ validate JSON
                       ├─ backup /etc/sing-box/config.json → /etc/sing-box/backups/
                       ├─ copy new config
                       └─ systemctl restart sing-box.service
```

---

## Running tests

```bash
source .venv/bin/activate
pytest -v
```

Tests cover URL parsing (vless, hysteria2) and config generation. They do not
require sing-box or root access.

---

## Project structure

```
app/
  main.py              — FastAPI routes
  db.py                — SQLite / SQLAlchemy setup
  models.py            — Node model
  parsers/
    vless.py           — VLESS Reality/TLS URL parser
    hysteria2.py       — Hysteria2/hy2 URL parser
  singbox/
    generator.py       — generates /etc/sing-box/config.json from active node
    validator.py       — runs `sing-box check`
    deployer.py        — calls helper to deploy + backup
    service.py         — calls helper for systemctl, reads journalctl
  templates/           — Jinja2 HTML (dashboard, nodes, logs, backups)
  static/style.css     — dark theme CSS

scripts/
  singbox-manager-helper   — privileged helper (install to /usr/local/bin/)

sudoers.d/singbox-manager  — sudoers rule (install to /etc/sudoers.d/)
singbox-manager.service    — systemd unit for the web app
```

---

## Troubleshooting

**"Helper not found at /usr/local/bin/singbox-manager-helper"**
Run install step 3 above.

**"sudo: no password supplied" or password prompt**
Check that `/etc/sudoers.d/singbox-manager` is installed with mode 440 and
`visudo -c` reports OK.

**Config validation fails with TUN errors**
`sing-box check` may warn about TUN interface not existing — this is expected
during validation and does not affect deployment.

**External IP shows real IP instead of VPN IP**
sing-box service is not running or TUN is not capturing traffic. Check
`systemctl status sing-box.service` and the Logs page.

**Port 9090 already in use**
Change `--port` in the systemd unit or pass `PORT=xxxx` env var.
