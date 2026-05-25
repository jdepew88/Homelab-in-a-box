# Homelab-in-a-box

Debian VPS bootstrap for a self-hosted Docker control plane behind **Cloudflare Tunnel**.

**Repository:** https://github.com/jdepew88/Homelab-in-a-box  
**Default install path:** `~/homelab-in-a-box`

---

## What this is

Homelab-in-a-box installs and wires up a small stack on a fresh Debian server:

| Component | Role |
|-----------|------|
| **Cloudflare Tunnel** | Connects your VPS to Cloudflare without opening inbound firewall ports |
| **Traefik** | Reverse proxy — routes requests to containers by hostname |
| **Portainer** | Web UI to manage Docker |
| **Traefik Manager** | Web UI to edit Traefik routes and middleware |
| **Authelia** | Login gate (username/password) for protected UIs |
| **Optional profiles** | Extra apps in Compose, e.g. **Rocket.Chat** (`--profile rocketchat`) |

### Traffic path

```text
User browser
    → Cloudflare (DNS + edge)
    → Cloudflare Tunnel (cloudflared on the VPS)
    → Traefik
    → Docker services (Portainer, Traefik Manager, apps, …)
```

Each public hostname in Zero Trust must forward to **`http://traefik:80`**. Traefik then sends traffic to the correct container.

### Local-first / no phone-home

This project does **not**:

- Send your secrets to the repo owner or any third-party service operated by this project
- Use a central management server for your stack

Setup scripts write **only on your VPS**:

- `~/homelab-in-a-box/.env` — secrets and settings
- `~/homelab-in-a-box/config.yaml` — domain metadata (no secrets)
- `/opt/appdata/docker-apps/` — Traefik, Authelia, tunnel files, databases (paths are configurable in setup)

You clone the public repo; each machine gets its own generated config.

### Two-phase install

| Phase | Goal |
|-------|------|
| **1 — Bootstrap** | Tunnel + Traefik + Portainer + Traefik Manager reachable in the browser |
| **2 — Authelia** | Require login before using those UIs |

Phase 1 is intentionally open so you can confirm Cloudflare and Traefik work on a **headless** VPS before adding Postgres, Redis, and Authelia.

---

## Intended audience

You want a **quick VPS homelab control plane**: Docker, Cloudflare Tunnel, Traefik, and a simple login layer — without building the plumbing from scratch.

This guide assumes:

- A **fresh Debian** VM or VPS
- **SSH** access
- A **domain** on Cloudflare
- Comfort copying terminal commands and answering setup prompts

Examples use deploy user **`joe`** and path **`~/homelab-in-a-box`**. Change those if your user or home directory differs.

---

## What you need before starting

| Requirement | Notes |
|-------------|--------|
| Debian 11 or 12 | Clean VM or VPS |
| Deploy user with `sudo` | Not root for daily setup; e.g. `joe` |
| Git | Installed in quick start below |
| Domain on Cloudflare | DNS proxied (orange cloud) |
| Cloudflare Zero Trust | To create a tunnel (free tier works) |
| Tunnel connector token or `cloudflared` login | See [Cloudflare Tunnel](#cloudflare-tunnel-token-mode) |

Plan these **public hostnames** (replace `example.com` with your domain):

| Hostname | Typical use |
|----------|-------------|
| `auth.example.com` | Authelia login (add before or after phase 2) |
| `traefik.example.com` | Traefik dashboard |
| `port.example.com` | Portainer |
| `manager.example.com` | Traefik Manager |

Every hostname in the tunnel dashboard must use service URL **`http://traefik:80`**.

---

## Fresh VM quick start

### 1. Clone and install prerequisites

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/jdepew88/Homelab-in-a-box.git ~/homelab-in-a-box
cd ~/homelab-in-a-box
sudo bash scripts/install-server.sh
```

`install-server.sh` (run as root) installs Docker and `cloudflared`, creates `/opt/appdata/docker-apps`, and adds your deploy user to the `docker` group.

### 2. Refresh group membership

If Docker was newly installed, **log out and SSH back in** so `docker` works without `sudo`:

```bash
exit
# ssh back in as joe (or your deploy user)
groups
```

You should see `docker` in the list. If not, fix group membership before continuing.

### 3. Phase 1 — Bootstrap

Run as your **deploy user**, not root:

```bash
cd ~/homelab-in-a-box
python3 scripts/setup-bootstrap.py
chmod +x scripts/compose.sh
./scripts/compose.sh --profile tunnel-token up -d
```

**Bootstrap-only** (no Authelia, no Rocket.Chat, no `compose.yaml`):

```bash
cd /home/joe/homelab-in-a-box
docker compose -f compose.bootstrap.yaml up -d
```

With the Cloudflare tunnel token profile (when `CF_TUNNEL_TOKEN` is set in `.env`):

```bash
docker compose -f compose.bootstrap.yaml --profile tunnel-token up -d
```

Do **not** combine files like this — it loads `compose.bootstrap.yaml` twice (once via `compose.yaml` `include`, once via `-f`) and can cause duplicate merge errors:

```bash
docker compose -f compose.yaml -f compose.bootstrap.yaml up -d   # wrong
```

After phase 1, use `./scripts/compose.sh` (which uses `compose.yaml` only) for the full stack.

Check in a browser (no login yet):

- `https://port.<your-domain>`
- `https://traefik.<your-domain>`
- `https://manager.<your-domain>`

### 4. Phase 2 — Authelia

```bash
cd ~/homelab-in-a-box
python3 scripts/setup-authelia.py
./scripts/compose.sh --profile auth up -d
```

Sign in at `https://auth.<your-domain>`, then reopen Portainer or Traefik — you should be prompted for credentials.

The stack is **not complete** until phase 2 works.

---

## Traefik Manager password (bcrypt)

Traefik Manager stores its login password as a bcrypt hash in `manager.yml` under appdata (for example `/opt/appdata/docker-apps/traefik-manager/config/manager.yml`). Generate a new hash:

```bash
sudo apt update
sudo apt install -y python3-bcrypt
python3 scripts/newhash.py
```

Paste the printed hash into `manager.yml` (replacing the existing bcrypt password field). Bcrypt hashes usually start with `$2b$12$`.

---

## Verify bootstrap

After `docker compose -f compose.bootstrap.yaml up -d` (and tunnel profile if used):

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker inspect portainer --format '{{json .Config.Labels}}' | jq
curl -I -H "Host: port.jrtechconsult.com" http://127.0.0.1
curl -I -H "Host: manager.jrtechconsult.com" http://127.0.0.1
curl -I -H "Host: traefik.jrtechconsult.com" http://127.0.0.1
docker logs traefik --tail=100
docker logs traefik-manager --tail=100
```

Replace `jrtechconsult.com` and subdomains with your `DOMAIN` and `SUBDOMAIN_*` values from `.env`.

Validate Compose before starting:

```bash
docker compose -f compose.bootstrap.yaml config
```

---

## Traefik Manager `domains` in `manager.yml`

If Traefik Manager logs show:

```text
Domains: ['example.com']
```

edit `manager.yml` so it lists your real domain, for example:

```yaml
domains:
  - jrtechconsult.com
```

Docker Compose expands `${DOMAIN}` in **Compose labels and environment**, but **not** inside arbitrary mounted files such as `manager.yml` unless the application reads those variables itself. Set the domain explicitly in `manager.yml` after bootstrap or when you change `DOMAIN` in `.env`.

---

## Cloudflare Tunnel (token mode)

Recommended on a **headless** server: create the tunnel on a machine with a browser, paste the token on the VPS.

### In Cloudflare Zero Trust

1. Open https://one.dash.cloudflare.com/
2. **Networks** → **Tunnels** → **Create a tunnel**
3. Connector type: **Docker**
4. Copy the **connector token** (long string; treat as a secret)

### Public hostnames

Under the tunnel, add routes. **Service URL for every hostname:**

```text
http://traefik:80
```

| Public hostname | Service URL |
|-----------------|-------------|
| `auth.example.com` | `http://traefik:80` |
| `traefik.example.com` | `http://traefik:80` |
| `port.example.com` | `http://traefik:80` |
| `manager.example.com` | `http://traefik:80` |

Use your real domain and the subdomains you enter in `setup-bootstrap.py`. Wildcard `*.example.com` → `http://traefik:80` is optional.

### On the VPS

When `setup-bootstrap.py` asks for **tunnel mode**, type **`token`**, then paste the connector token. The script does **not** print the token again after you enter it.

Then:

```bash
docker compose -f compose.bootstrap.yaml --profile tunnel-token up -d
# or: ./scripts/compose.sh --profile tunnel-token up -d
docker logs cloudflared --tail=50
```

### Config mode (alternative)

Choose **`config`** only if you can complete `cloudflared tunnel login` (open the printed URL in a **browser** — never paste that URL into the shell as a command). The script can create a tunnel, write files under `/opt/appdata/docker-apps/cloudflared/`, and add DNS routes.

---

## Setup script prompts

### `scripts/setup-bootstrap.py`

| Prompt | Default / notes |
|--------|------------------|
| Compose directory | `/home/joe/homelab-in-a-box` — use `~/homelab-in-a-box` for user `joe` |
| Appdata root | `/opt/appdata/docker-apps` |
| Primary domain | e.g. `yourdomain.app` |
| Cloudflare email | Account email |
| Timezone | e.g. `America/New_York` |
| Traefik subdomain | `traefik` |
| Portainer subdomain | `port` |
| Traefik Manager subdomain | `manager` |
| Tunnel mode | **`token`** or **`config`** only |
| Tunnel name | Label in Cloudflare |
| CF tunnel token | Required in **token** mode |

If `.env` already exists, the script asks before overwriting bootstrap values.

### `scripts/setup-authelia.py`

| Prompt | Notes |
|--------|--------|
| Compose directory | Same as phase 1 |
| Authelia subdomain | `auth` |
| Username | Authelia login |
| Email | User record |
| Password | Stored as argon2 hash in `users_database.yml` |
| Backup users file? | Optional copy to e.g. `~/authelia-offline-backups/` |

Requires `.env` from phase 1.

---

## Files created on the VPS

### Project directory (`~/homelab-in-a-box`)

| File | Commit to git? | Contents |
|------|----------------|----------|
| `.env` | **Never** | Secrets, tunnel token, passwords |
| `config.yaml` | **Never** | Domain, Cloudflare email |
| `compose.auth-overrides.yaml` | **Never** | Authelia middleware labels (phase 2) |

### Appdata (default `/opt/appdata/docker-apps`)

| Path | Purpose |
|------|---------|
| `traefik/traefik.yml` | Traefik static config (from `templates/traefik/`) |
| `traefik/dynamic/config.yml` | Security middlewares ([install_traefik_compose](https://github.com/jdepew88/install_traefik_compose)) |
| `traefik/dynamic/authelia.yml` | Authelia forward-auth (phase 2) |
| `cloudflared/` | Tunnel config + credentials (config mode) |
| `authelia/` | Authelia config and `users_database.yml` |
| `postgres/` | Authelia database |
| `redis/` | Authelia sessions |
| `portainer/data/` | Portainer data |
| `traefik-manager/config/manager.yml` | Traefik Manager login + `domains` list (edit domain by hand) |
| `traefik-manager/` | Traefik Manager backups and state |

Safe to commit from the repo: `compose*.yaml`, `templates/`, `scripts/`, `.env.example`.

`.env` should include `COMPOSE_DIR`, `PRIMARY_DOMAIN`, and `DOMAIN` (setup writes all three). Older `.env` files with only `DOMAIN` still work — `regenerate-configs.py` fills `PRIMARY_DOMAIN` automatically.

---

## Traefik module (`traefik/`)

Vendored from [install_traefik_compose/traefik](https://github.com/jdepew88/install_traefik_compose/tree/main/traefik) (IBRACORP-style Docker Compose Traefik).

| Location | Use |
|----------|-----|
| `traefik/docker-compose.yml` | Optional **Traefik-only** stack (host ports 80/443 + ACME) |
| `traefik/traefik.yml`, `traefik/config.yml` | Reference for DNS/Let's Encrypt mode |
| `templates/traefik/` | What the main HIAB stack renders into appdata (tunnel → `:80`) |

The default homelab path uses **`./scripts/compose.sh`** at the repo root, not `traefik/docker-compose.yml`.

---

## Regenerating configs from an existing `.env`

Use this when templates or YAML on disk were fixed but your `.env` is already correct. This **does not** replace `.env`; it re-renders `traefik.yml`, `traefik/dynamic/config.yml`, and related appdata from `templates/` (including middlewares from `install_traefik_compose`).

```bash
cd ~/homelab-in-a-box
cp .env .env.bak.$(date +%Y%m%d-%H%M%S)
python3 scripts/regenerate-configs.py
./scripts/compose.sh down
./scripts/compose.sh up -d
docker ps
docker logs traefik --tail=100
docker logs cloudflared --tail=100
./scripts/compose.sh config | grep -i "Host"
```

You should see host rules such as `Host(\`port.yourdomain.app\`)` using `DOMAIN` / `PRIMARY_DOMAIN` and your `SUBDOMAIN_*` values from `.env`.

**Alternative:** re-run bootstrap and choose **regenerate** when prompted:

```bash
python3 scripts/setup-bootstrap.py
# Choose: regenerate
```

### Manual `.env` edit, then regenerate

```bash
cd ~/homelab-in-a-box
cp .env .env.bak.$(date +%Y%m%d-%H%M%S)
nano .env
python3 scripts/regenerate-configs.py
./scripts/compose.sh down
./scripts/compose.sh up -d
```

Required in `.env` for regeneration: `COMPOSE_DIR`, `APPDATA_ROOT`, `PRIMARY_DOMAIN` (or `DOMAIN`), `SUBDOMAIN_*`, `CF_TUNNEL_MODE`, `CF_TUNNEL_NAME`, and `CF_TUNNEL_TOKEN` when mode is `token`.

---

## Optional apps

**Rocket.Chat:**

```bash
cd ~/homelab-in-a-box
./scripts/compose.sh --profile rocketchat up -d
```

Add a tunnel hostname for your chat subdomain → `http://traefik:80`. Run phase 2 first so forward-auth applies.

**Custom stacks:**

```bash
python3 scripts/add_stack.py
```

---

## Compose profiles

| Profile | Services |
|---------|----------|
| `tunnel-token` | `cloudflared` using `CF_TUNNEL_TOKEN` |
| `tunnel-config` | `cloudflared` using local `config.yml` |
| `auth` | PostgreSQL, Redis, Authelia |
| `rocketchat` | MongoDB + Rocket.Chat |

`scripts/compose.sh` picks the tunnel profile from `CF_TUNNEL_MODE` in `.env` and merges `compose.auth-overrides.yaml` when present.

---

## Security

- **Secrets stay on your VPS** — `.env` and appdata are yours only
- **Do not commit** `.env`, `config.yaml`, or generated overrides
- **Do not share** tunnel tokens in chat, tickets, or screenshots
- **Phase 1** exposes Portainer and Traefik **without** Authelia until phase 2 finishes
- Complete **phase 2** before treating the deployment as done
- Back up `users_database.yml` offline when the Authelia script offers it

---

## Troubleshooting

### Docker: permission denied

```bash
groups   # need docker
```

Log out and SSH back in after `install-server.sh`.

### Invalid tunnel mode

Only **`token`** or **`config`** are valid. Re-run `setup-bootstrap.py` if you entered `2`, `yes`, or anything else. Or use `python3 scripts/regenerate-configs.py` if `.env` is already correct.

### Traefik folders or `traefik.yml` missing

Bootstrap and `regenerate-configs.py` create:

```text
/opt/appdata/docker-apps/traefik/
/opt/appdata/docker-apps/traefik/dynamic/
/opt/appdata/docker-apps/traefik/logs/
/opt/appdata/docker-apps/traefik/traefik.yml
```

If those are missing, run:

```bash
python3 scripts/regenerate-configs.py
```

### Bad YAML (one line with literal `\n`)

If a template was flattened into a single line, pull the latest repo and run `regenerate-configs.py`. Templates are read with a repair step that converts literal `\n` to real newlines when detected.

### Pasted a Cloudflare URL into the terminal

Login URLs are for a **browser tab**, not bash. Open the link on your laptop or phone. Prefer **token** mode on headless servers.

### Tunnel exists but sites do not load

```bash
cd ~/homelab-in-a-box
./scripts/compose.sh up -d
docker ps
```

All core containers should be `Up`. If `cloudflared` or `traefik` is missing, check logs below.

### Hostname does not load in the browser

In Zero Trust → tunnel → **Public Hostname**, confirm:

```text
http://traefik:80
```

Not `https://…`, not `localhost`, not a port on the host.

### Phase 2 does not ask for login

```bash
ls ~/homelab-in-a-box/compose.auth-overrides.yaml
./scripts/compose.sh --profile auth up -d
```

### Authelia redirect loop

Ensure `auth.<your-domain>` is in the tunnel and points to `http://traefik:80`.

### Logs

```bash
docker logs cloudflared --tail=100
docker logs traefik --tail=100
docker logs authelia --tail=100
```

Via compose:

```bash
cd ~/homelab-in-a-box
./scripts/compose.sh logs cloudflared
./scripts/compose.sh logs traefik
./scripts/compose.sh --profile auth logs authelia
```

### Config mode: `cloudflared tunnel list` fails

```bash
cloudflared tunnel login
```

Complete login in a browser, then re-run `python3 scripts/setup-bootstrap.py`. Or use **token** mode from the dashboard.

---

## License

MIT — see [LICENSE](LICENSE).

## References

- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [Authelia (IBRACORP)](https://docs.ibracorp.io/docs/security/authelia)
- [Traefik Manager](https://github.com/chr0nzz/traefik-manager)
- [Rocket.Chat — Docker Compose](https://docs.rocket.chat/docs/deploy-with-docker-docker-compose)
