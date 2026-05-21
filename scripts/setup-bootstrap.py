#!/usr/bin/env python3
"""
Phase 1 — Cloudflare Tunnel + Traefik + Portainer (+ Traefik Manager).

Designed for headless Debian VPS: get remote HTTPS first, add Authelia later.

Recommended (headless): create tunnel in Cloudflare Zero Trust on your laptop,
copy the connector token, paste when prompted. Configure hostnames in the dashboard.

  sudo -u joe -H python3 scripts/setup-bootstrap.py
  ./scripts/compose.sh up -d
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Shared helpers from repo (inline to keep single-file bootstrap portable)
REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from setup_lib import (  # noqa: E402
    prompt,
    render,
    require_not_root,
    setup_cloudflare_tunnel_config_mode,
    valid_domain,
)


def main() -> None:
    require_not_root()

    print("=== Phase 1: Bootstrap (Tunnel + Traefik + Portainer) ===\n")
    print("Authelia is NOT installed yet — services are reachable without login.")
    print("Run setup-authelia.py as soon as you can reach Portainer.\n")

    compose_home = Path(prompt("Compose directory", "/home/joe/docker-vps-stack"))
    appdata_root = Path(prompt("Appdata root", "/opt/appdata/docker-apps"))
    domain = prompt("Primary domain", "88pockets.app").lower()
    if not valid_domain(domain):
        sys.exit(f"Invalid domain: {domain}")

    cf_email = prompt("Cloudflare account email", "")
    if not cf_email or "@" not in cf_email:
        sys.exit("Cloudflare email is required.")

    tz = prompt("Timezone", "America/New_York")
    sub_traefik = prompt("Traefik dashboard subdomain", "traefik")
    sub_portainer = prompt("Portainer subdomain", "port")
    sub_manager = prompt("Traefik Manager subdomain", "manager")

    print("\n--- Cloudflare Tunnel (headless-friendly) ---")
    print("1) token  — create tunnel in Zero Trust on your PC, paste connector token (best for headless)")
    print("2) config — run cloudflared login on this server (needs browser once), auto config + DNS\n")
    mode = prompt("Tunnel mode", "token").lower()
    if mode not in ("token", "config"):
        sys.exit("Tunnel mode must be 'token' or 'config'")

    cf_tunnel_token = ""
    tunnel_id = ""
    tunnel_name = ""

    if mode == "token":
        print("\nOn your laptop: Zero Trust → Networks → Tunnels → Create tunnel → Docker")
        print("Copy the token, then add Public Hostnames (before or after compose up):")
        print(f"  {sub_traefik}.{domain}   → http://traefik:80")
        print(f"  {sub_portainer}.{domain} → http://traefik:80")
        print(f"  {sub_manager}.{domain}   → http://traefik:80")
        print(f"  (optional) *.{domain}    → http://traefik:80\n")
        cf_tunnel_token = prompt("Paste CF_TUNNEL_TOKEN")
        if not cf_tunnel_token.strip():
            sys.exit("Tunnel token is required for token mode.")
        tunnel_name = prompt("Tunnel name (label only)", f"vps-{domain.replace('.', '-')}")
    else:
        tunnel_name = prompt("New tunnel name", f"vps-{domain.replace('.', '-')}")
        hostnames = [
            f"{sub_traefik}.{domain}",
            f"{sub_portainer}.{domain}",
            f"{sub_manager}.{domain}",
            domain,
        ]
        tunnel_id = setup_cloudflare_tunnel_config_mode(
            domain=domain,
            appdata_root=appdata_root,
            tunnel_name=tunnel_name,
            hostnames=hostnames,
        )

    mapping = {
        "__DOMAIN__": domain,
        "__CF_EMAIL__": cf_email,
        "__SUBDOMAIN_AUTH__": "auth",
        "__SUBDOMAIN_TRAEFIK__": sub_traefik,
        "__SUBDOMAIN_PORTAINER__": sub_portainer,
        "__SUBDOMAIN_MANAGER__": sub_manager,
    }

    print("\nWriting Traefik config...")
    render(
        TEMPLATES / "traefik" / "traefik.yml.template",
        appdata_root / "traefik" / "traefik.yml",
        mapping,
    )
    (appdata_root / "traefik" / "dynamic").mkdir(parents=True, exist_ok=True)
    # No authelia.yml yet — phase 2

    (appdata_root / "traefik" / "logs").mkdir(parents=True, exist_ok=True)
    (appdata_root / "traefik" / "logs" / "access.log").touch(exist_ok=True)
    (appdata_root / "traefik-manager" / "config").mkdir(parents=True, exist_ok=True)
    (appdata_root / "traefik-manager" / "backups").mkdir(parents=True, exist_ok=True)
    (appdata_root / "portainer" / "data").mkdir(parents=True, exist_ok=True)
    (appdata_root / "cloudflared").mkdir(parents=True, exist_ok=True)

    config_text = (TEMPLATES / "config.yaml.template").read_text(encoding="utf-8")
    config_text = (
        config_text.replace("__DOMAIN__", domain)
        .replace("__CF_EMAIL__", cf_email)
        .replace("/home/joe/docker-vps-stack", str(compose_home))
        .replace("/opt/appdata/docker-apps", str(appdata_root))
        .replace("America/New_York", tz)
        .replace("auth: auth", "auth: auth")
        .replace("portainer: portainer", f"portainer: {sub_portainer}")
        .replace("traefik: traefik", f"traefik: {sub_traefik}")
        .replace("manager: manager", f"manager: {sub_manager}")
    )
    compose_home.mkdir(parents=True, exist_ok=True)
    (compose_home / "config.yaml").write_text(config_text, encoding="utf-8")

    env_lines = [
        "COMPOSE_PROJECT_NAME=vps-stack",
        f"TZ={tz}",
        f"DOMAIN={domain}",
        f"CF_EMAIL={cf_email}",
        f"CF_TUNNEL_MODE={mode}",
        f"CF_TUNNEL_TOKEN={cf_tunnel_token}",
        f"CF_TUNNEL_NAME={tunnel_name}",
        f"CF_TUNNEL_ID={tunnel_id}",
        "CF_DNS_API_TOKEN=",
        f"APPDATA_ROOT={appdata_root}",
        f"SUBDOMAIN_TRAEFIK={sub_traefik}",
        f"SUBDOMAIN_PORTAINER={sub_portainer}",
        f"SUBDOMAIN_MANAGER={sub_manager}",
        "SUBDOMAIN_AUTH=auth",
        "TM_COOKIE_SECURE=true",
        "# Phase 2 fills POSTGRES_PASSWORD, REDIS_PASSWORD, Authelia secrets via setup-authelia.py",
        "POSTGRES_PASSWORD=",
        "REDIS_PASSWORD=",
        "AUTHELIA_JWT_SECRET=",
        "AUTHELIA_SESSION_SECRET=",
        "AUTHELIA_STORAGE_ENCRYPTION_KEY=",
    ]
    env_path = compose_home / ".env"
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    try:
        env_path.chmod(0o600)
    except OSError:
        pass

    print(f"\n  wrote {env_path}")
    print(f"  wrote {compose_home / 'config.yaml'}")
    print("\n=== Phase 1 complete ===")
    print(f"  cd {compose_home}")
    print("  ./scripts/compose.sh up -d")
    print(f"\nThen open (no login yet):")
    print(f"  https://{sub_portainer}.{domain}")
    print(f"  https://{sub_traefik}.{domain}")
    print("\n=== Next: lock down with Authelia ===")
    print("  python3 scripts/setup-authelia.py")
    print("  ./scripts/compose.sh --profile auth up -d")


if __name__ == "__main__":
    main()
