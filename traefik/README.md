# Traefik (from install_traefik_compose)

Files in this folder come from [install_traefik_compose/traefik](https://github.com/jdepew88/install_traefik_compose/tree/main/traefik) — a Docker Compose Traefik setup following the [IBRACORP Traefik guide](https://docs.ibracorp.io/traefik/master/docker-compose).

## How Homelab-in-a-box uses them

| Path | Role in HIAB |
|------|----------------|
| `../templates/traefik/traefik.yml.template` | Active static config for the main stack (Cloudflare Tunnel, `:80` only) |
| `../templates/traefik/dynamic/config.yml.template` | Security middlewares + optional file-based routes (rendered to appdata) |
| `../compose.bootstrap.yaml` | Traefik service in the full homelab stack |
| `docker-compose.yml` here | **Optional** Traefik-only stack (reference / standalone install) |
| `traefik.yml`, `config.yml` here | **Reference** configs for DNS + Let's Encrypt (ACME) mode |

The main HIAB path does **not** publish host ports `80`/`443` on Traefik; ingress is **Cloudflare Tunnel** → `http://traefik:80`.

Use this folder when you want the original IBRACORP-style Traefik install (host ports + Cloudflare DNS ACME) on its own, or to compare with the HIAB templates.

## Standalone Traefik-only install

```bash
cd ~/homelab-in-a-box/traefik
cp .env.example .env
# Edit .env: DOMAIN_NAME, EMAIL, TRAEFIK_CF_DNS_API_TOKEN
docker network create proxy 2>/dev/null || true
docker compose up -d
```

This is separate from `./scripts/compose.sh` at the repo root.

## Regenerate HIAB Traefik files from `.env`

From the repo root:

```bash
python3 scripts/regenerate-configs.py
```

That writes `/opt/appdata/docker-apps/traefik/traefik.yml` and `dynamic/config.yml` from `templates/`, not from this folder directly.
