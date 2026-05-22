# Homelab-in-a-box

Public template for a **Debian VPS** Docker homelab: **Cloudflare Tunnel**, **Traefik**, **Portainer**, **Traefik Manager**, and **Authelia** (1FA).

**Two-phase setup** so a **headless** server gets remote HTTPS through Cloudflare *before* authentication is configured.

| Phase | Script | What runs | Remote URLs |
|-------|--------|-----------|-------------|
| **1** | `scripts/setup-bootstrap.py` | Tunnel + Traefik + Portainer + Traefik Manager | `https://port.yourdomain.app` — **no login** |
| **2** | `scripts/setup-authelia.py` | Postgres + Redis + Authelia | Same URLs — **username/password** |

> **Security:** Phase 1 exposes Portainer and Traefik without Authelia. Run phase 2 as soon as the tunnel works.

Repository: [github.com/jdepew88/Homelab-in-a-box](https://github.com/jdepew88/Homelab-in-a-box)

---

## What gets committed vs generated

| In git (safe) | On your server only (never commit) |
|---------------|-------------------------------------|
| `compose*.yaml`, `templates/`, `scripts/` | `.env` — secrets and tunnel token |
| `.env.example` | `config.yaml` — your domain |
| | `/opt/appdata/docker-apps/**` — runtime config and data |
| | `compose.auth-overrides.yaml` — generated in phase 2 |

---

## Requirements

- Debian 11/12 VPS
- Domain on **Cloudflare** (proxied DNS)
- **Cloudflare Zero Trust** (free tier works)
- SSH access
- Deploy user with `sudo` (examples use `joe`)

---

## Setup (fresh Debian VM)

### 1. Install prerequisites (as root)

```bash
git clone https://github.com/jdepew88/Homelab-in-a-box.git ~/homelab-in-a-box
cd ~/homelab-in-a-box
sudo bash scripts/install-server.sh
```

If Docker was just installed, **log out and SSH back in** so the `docker` group applies:

```bash
exit
# ssh back in
groups    # should list docker
```

### 2. Phase 1 — bootstrap (as deploy user, not root)

```bash
cd ~/homelab-in-a-box
chmod +x scripts/compose.sh
python3 scripts/setup-bootstrap.py
./scripts/compose.sh up -d
```

**Headless tunnel (recommended):** On your laptop, [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks** → **Tunnels** → **Create tunnel** → **Docker** → copy the connector token. On the VPS, choose tunnel mode **`token`** and paste the token (it is not shown again).

Add **Public Hostnames** in the tunnel (service URL must be):

```text
http://traefik:80
```

| Hostname example | Points to |
|------------------|-----------|
| `traefik.yourdomain.app` | `http://traefik:80` |
| `port.yourdomain.app` | `http://traefik:80` |
| `manager.yourdomain.app` | `http://traefik:80` |
| `*.yourdomain.app` (optional) | `http://traefik:80` |

Verify: `https://port.yourdomain.app` opens Portainer.

### 3. Phase 2 — Authelia

```bash
python3 scripts/setup-authelia.py
./scripts/compose.sh --profile auth up -d
```

Add tunnel hostname `auth.yourdomain.app` → `http://traefik:80` if you used explicit hostnames instead of a wildcard.

---

## Paths

| Path | Purpose |
|------|---------|
| `~/homelab-in-a-box` | Compose project, `.env`, scripts (default; configurable in setup) |
| `/opt/appdata/docker-apps` | Persistent app data (default; configurable) |

---

## Why two phases?

1. **Headless VPS** — confirm Cloudflare → Traefik → Portainer before adding Postgres, Redis, and Authelia.
2. **Portainer** — web UI to inspect containers if phase 2 fails.
3. **Public repo** — secrets stay in each user’s local `.env` only.

---

## Compose profiles

| Profile | Services |
|---------|----------|
| `tunnel-token` | `cloudflared` using `CF_TUNNEL_TOKEN` |
| `tunnel-config` | `cloudflared-config` using `config.yml` + credentials |
| `auth` | `postgres`, `redis`, `authelia` |
| `rocketchat` | MongoDB + Rocket.Chat |

`scripts/compose.sh` reads `CF_TUNNEL_MODE` and includes `compose.auth-overrides.yaml` when present.

---

## Optional apps

```bash
./scripts/compose.sh --profile rocketchat up -d
python3 scripts/add_stack.py
```

---

## Troubleshooting

| Problem | What to do |
|---------|------------|
| Pasted Cloudflare login URL into bash | Do **not** run the URL as a command. Open it in a browser only, or use **token** mode instead. |
| Invalid tunnel mode (`2`, `yes`, etc.) | Re-run `setup-bootstrap.py` and enter exactly `token` or `config`. |
| `cloudflared tunnel list` empty / errors | Run `cloudflared tunnel login`, then re-run bootstrap; or use **token** mode from the dashboard. |
| `permission denied` on `docker` | Log out and SSH back in after `install-server.sh`, or run `groups` and confirm `docker`. |
| 502 / blank page | Tunnel hostname must target **`http://traefik:80`** (not `https`, not `localhost`). |
| Tunnel not connecting | Check `CF_TUNNEL_TOKEN` in `.env` and `docker logs cloudflared`. |
| Phase 2 not protecting apps | Ensure `compose.auth-overrides.yaml` exists; run `./scripts/compose.sh --profile auth up -d`. |
| Authelia redirect loop | Add `auth.yourdomain.app` → `http://traefik:80` in the tunnel. |

```bash
./scripts/compose.sh ps
./scripts/compose.sh logs cloudflared
./scripts/compose.sh logs traefik
./scripts/compose.sh --profile auth logs authelia
```

---

## Immich + object storage (later)

Use **Cloudflare R2** or S3 for photo storage instead of VPS disk. See `stacks/immich.compose.yaml.example`.

---

## License

MIT — see [LICENSE](LICENSE).

## References

- [Authelia (IBRACORP)](https://docs.ibracorp.io/docs/security/authelia)
- [Traefik Manager](https://github.com/chr0nzz/traefik-manager)
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
