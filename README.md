# docker-vps-stack

Public template for a **Debian VPS** Docker homelab: **Cloudflare Tunnel** ingress (no open firewall ports), **Traefik**, **Portainer**, **Traefik Manager**, and optional **Authelia** (1FA).

**Two-phase setup** so a **headless** server gets remote HTTPS *before* auth is configured.

| Phase | Script | What runs | Remote URLs |
|-------|--------|-----------|-------------|
| **1** | `setup-bootstrap.py` | Tunnel + Traefik + Portainer + Traefik Manager | `https://port.yourdomain`, `https://traefik.yourdomain` — **no login** |
| **2** | `setup-authelia.py` | Postgres + Redis + Authelia + forward-auth | Same URLs, **username/password required** |

> **Security:** Phase 1 exposes Portainer and Traefik on the internet without Authelia. Complete Phase 2 immediately after you confirm the tunnel works.

---

## What gets committed vs generated

| In git (safe) | On your server only (never commit) |
|---------------|-------------------------------------|
| `compose*.yaml`, `templates/`, `scripts/` | `.env` — secrets and tunnel token |
| `.env.example` | `config.yaml` — your domain |
| | `/opt/appdata/docker-apps/**` — Traefik, Authelia, tunnel credentials |
| | `compose.auth-overrides.yaml` — generated in phase 2 |
| | `~/authelia-offline-backups/` — optional user DB backup |

Each user runs the setup scripts locally on their VPS; nothing sensitive is stored in this repo.

---

## Requirements

- Debian 11/12 VPS (root for bootstrap, then deploy user e.g. `joe`)
- Domain on **Cloudflare** (orange-cloud DNS)
- **Cloudflare Zero Trust** (free tier is fine)
- SSH access to the VPS

---

## Quick start

### 1. Clone (on the VPS)

```bash
sudo apt-get update && sudo apt-get install -y git
sudo bash -c 'curl -fsSL https://get.docker.com | sh'   # or use install-server.sh below
git clone https://github.com/YOUR_USER/docker-vps-stack.git /home/joe/docker-vps-stack
sudo chown -R joe:joe /home/joe/docker-vps-stack
```

Or use the install script (Docker + `cloudflared`):

```bash
git clone https://github.com/YOUR_USER/docker-vps-stack.git /home/joe/docker-vps-stack
cd /home/joe/docker-vps-stack
sudo bash scripts/install-server.sh
```

### 2. Phase 1 — Tunnel + Traefik + Portainer (headless)

Run as **joe**, not root:

```bash
cd /home/joe/docker-vps-stack
chmod +x scripts/compose.sh
python3 scripts/setup-bootstrap.py
./scripts/compose.sh up -d
```

#### Headless Cloudflare Tunnel (recommended)

On your **laptop** (browser):

1. [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels** → **Create a tunnel**
2. Name it (e.g. `vps-88pockets`) → choose **Docker** → copy the **connector token**
3. Under **Public Hostname**, add routes to `http://traefik:80`:

   | Public hostname | Service |
   |-----------------|---------|
   | `traefik.yourdomain.com` | `http://traefik:80` |
   | `port.yourdomain.com` | `http://traefik:80` |
   | `manager.yourdomain.com` | `http://traefik:80` |
   | `*.yourdomain.com` (optional) | `http://traefik:80` |

On the **VPS**, when `setup-bootstrap.py` asks for tunnel mode, choose **`token`** and paste the token.

Confirm in a browser:

- `https://port.yourdomain.com` → Portainer setup wizard  
- `https://traefik.yourdomain.com` → Traefik dashboard  
- `https://manager.yourdomain.com` → Traefik Manager setup wizard  

#### Alternative: `config` mode

If you can open a browser once for `cloudflared tunnel login` on the VPS (or copy `cert.pem` from another machine), choose **`config`** in the script; it creates the tunnel, DNS routes, and `config.yml` under `/opt/appdata/docker-apps/cloudflared/`.

### 3. Phase 2 — Authelia (1FA)

```bash
python3 scripts/setup-authelia.py
./scripts/compose.sh --profile auth up -d
```

- Prompts for **username** and **password**
- Offers to **backup** `users_database.yml` for offline storage (`scp` to your PC)
- Notifier: **filesystem** only (no SMTP)
- Adds `auth.yourdomain.com` and protects Portainer / Traefik / Manager

Test: open `https://port.yourdomain.com` → redirect to `https://auth.yourdomain.com` → sign in.

### 4. Optional apps

```bash
./scripts/compose.sh --profile rocketchat up -d
python3 scripts/add_stack.py   # list / register custom stacks
```

After Authelia, add Rocket.Chat to `compose.auth-overrides.yaml` (middleware line) or use Traefik Manager.

---

## Paths

| Path | Purpose |
|------|---------|
| `/home/joe/docker-vps-stack` | Compose project, `.env`, scripts |
| `/opt/appdata/docker-apps` | Traefik, Authelia, Portainer, tunnel config |

---

## Why two phases?

1. **Headless VPS** — you need working HTTP(S) through the tunnel before you can debug Authelia, Postgres, or labels.
2. **Portainer** gives you a UI to inspect containers if something fails in phase 2.
3. **Authelia** depends on Postgres, Redis, correct Traefik middleware, and DNS for `auth.` — easier when ingress already works.
4. **Public repo** — phase 1 only writes non-auth `.env` fields; phase 2 adds secrets to the same local `.env`.

---

## Compose profiles

| Profile | Services |
|---------|----------|
| `tunnel-token` | `cloudflared` (default, uses `CF_TUNNEL_TOKEN`) |
| `tunnel-config` | `cloudflared-config` (uses `config.yml` + credentials json) |
| `auth` | `postgres`, `redis`, `authelia` |
| `rocketchat` | MongoDB + Rocket.Chat |

`scripts/compose.sh` selects the tunnel profile from `CF_TUNNEL_MODE` and auto-includes `compose.auth-overrides.yaml` when present.

---

## Mail-in-a-Box

This stack does **not** publish host ports 80/443. MIAB can stay on the same machine if it keeps binding those ports itself and app hostnames use separate DNS names (e.g. `port.domain.com` vs `box.domain.com`).

---

## Immich + S3 (later)

Keep photo storage off the VPS disk — use **Cloudflare R2** or S3. See `stacks/immich.compose.yaml.example`.

---

## Troubleshooting

```bash
./scripts/compose.sh ps
./scripts/compose.sh logs cloudflared
./scripts/compose.sh logs traefik
./scripts/compose.sh --profile auth logs authelia
```

| Issue | Check |
|-------|--------|
| 502 / no route | Tunnel public hostname → `http://traefik:80` (not `https`, not `localhost`) |
| Tunnel not connecting | `CF_TUNNEL_TOKEN` in `.env`, `docker logs cloudflared` |
| Authelia loop | `auth.` hostname in tunnel + `access_control` bypass for auth subdomain |
| Phase 2 not protecting | `compose.auth-overrides.yaml` exists; re-run `./scripts/compose.sh --profile auth up -d` |

---

## License

MIT — see [LICENSE](LICENSE) if present; otherwise all files in this repo are provided as-is.

## References

- [Authelia (IBRACORP)](https://docs.ibracorp.io/docs/security/authelia)
- [Traefik Manager](https://github.com/chr0nzz/traefik-manager)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Rocket.Chat Docker](https://docs.rocket.chat/docs/deploy-with-docker-docker-compose)
