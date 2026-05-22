#!/usr/bin/env python3
"""
Phase 1 — Homelab-in-a-box: Cloudflare Tunnel + Traefik + Portainer + Traefik Manager.

  sudo -u joe -H python3 scripts/setup-bootstrap.py
  ./scripts/compose.sh up -d
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates"
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from setup_lib import (  # noqa: E402
    DEFAULT_APPDATA_ROOT,
    DEFAULT_COMPOSE_HOME,
    DEFAULT_DOMAIN_EXAMPLE,
    fail,
    prompt_choice,
    prompt_required,
    prompt_secret_quiet,
    render,
    require_not_root,
    setup_cloudflare_tunnel_config_mode,
    valid_domain,
    valid_email,
    valid_subdomain,
    warn_existing_env,
)


def main() -> None:
    require_not_root()
    created: list[Path] = []

    print("=== Homelab-in-a-box — Phase 1: Bootstrap ===\n")
    print("Tunnel + Traefik + Portainer (Authelia comes in phase 2).")
    print("Services are reachable without login until you run setup-authelia.py.\n")

    try:
        compose_home = Path(
            prompt_required("Compose directory", DEFAULT_COMPOSE_HOME, validator=lambda p: bool(p))
        )
        appdata_root = Path(
            prompt_required("Appdata root", DEFAULT_APPDATA_ROOT, validator=lambda p: bool(p))
        )
        domain = prompt_required(
            "Primary domain",
            DEFAULT_DOMAIN_EXAMPLE,
            validator=valid_domain,
            error_hint=f"Use a real hostname like {DEFAULT_DOMAIN_EXAMPLE} (lowercase, no https://).",
        ).lower()
        cf_email = prompt_required(
            "Cloudflare account email",
            validator=valid_email,
            error_hint="Enter the email on your Cloudflare account.",
        )
        tz = prompt_required("Timezone", "America/New_York")
        sub_traefik = prompt_required(
            "Traefik dashboard subdomain",
            "traefik",
            validator=valid_subdomain,
            error_hint="Use a single DNS label (letters, numbers, hyphens).",
        ).lower()
        sub_portainer = prompt_required(
            "Portainer subdomain",
            "port",
            validator=valid_subdomain,
            error_hint="Use a single DNS label (letters, numbers, hyphens).",
        ).lower()
        sub_manager = prompt_required(
            "Traefik Manager subdomain",
            "manager",
            validator=valid_subdomain,
            error_hint="Use a single DNS label (letters, numbers, hyphens).",
        ).lower()

        print("\n--- Cloudflare Tunnel ---")
        print("token — paste connector token from Zero Trust (best for headless VPS)")
        print("config — cloudflared login on this server + auto DNS (needs browser once)\n")
        mode = prompt_choice("Tunnel mode", ("token", "config"), "token")

        env_path = compose_home / ".env"
        warn_existing_env(env_path)

        cf_tunnel_token = ""
        tunnel_id = ""
        tunnel_name = prompt_required(
            "Tunnel name (label)",
            f"homelab-{domain.replace('.', '-')}",
            validator=lambda s: bool(s.strip()),
        )

        if mode == "token":
            print("\nOn your laptop: Zero Trust → Networks → Tunnels → Create tunnel → Docker")
            print("Add Public Hostnames → http://traefik:80 for:")
            print(f"  {sub_traefik}.{domain}")
            print(f"  {sub_portainer}.{domain}")
            print(f"  {sub_manager}.{domain}")
            print(f"  (optional) *.{domain}\n")
            cf_tunnel_token = prompt_secret_quiet("Paste CF_TUNNEL_TOKEN")
            if not cf_tunnel_token.strip():
                fail("Token mode requires a non-empty CF_TUNNEL_TOKEN.", created)
        else:
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
                created=created,
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
        traefik_yml = appdata_root / "traefik" / "traefik.yml"
        render(TEMPLATES / "traefik" / "traefik.yml.template", traefik_yml, mapping)
        created.append(traefik_yml)

        (appdata_root / "traefik" / "dynamic").mkdir(parents=True, exist_ok=True)
        (appdata_root / "traefik" / "logs").mkdir(parents=True, exist_ok=True)
        log_file = appdata_root / "traefik" / "logs" / "access.log"
        log_file.touch(exist_ok=True)
        (appdata_root / "traefik-manager" / "config").mkdir(parents=True, exist_ok=True)
        (appdata_root / "traefik-manager" / "backups").mkdir(parents=True, exist_ok=True)
        (appdata_root / "portainer" / "data").mkdir(parents=True, exist_ok=True)
        (appdata_root / "cloudflared").mkdir(parents=True, exist_ok=True)

        config_dest = compose_home / "config.yaml"
        config_text = (TEMPLATES / "config.yaml.template").read_text(encoding="utf-8")
        config_text = (
            config_text.replace("__DOMAIN__", domain)
            .replace("__CF_EMAIL__", cf_email)
            .replace("/home/joe/homelab-in-a-box", str(compose_home))
            .replace("/opt/appdata/docker-apps", str(appdata_root))
            .replace("America/New_York", tz)
            .replace("portainer: port", f"portainer: {sub_portainer}")
            .replace("traefik: traefik", f"traefik: {sub_traefik}")
            .replace("manager: manager", f"manager: {sub_manager}")
        )
        compose_home.mkdir(parents=True, exist_ok=True)
        config_dest.write_text(config_text, encoding="utf-8")
        created.append(config_dest)

        env_lines = [
            "COMPOSE_PROJECT_NAME=homelab-in-a-box",
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
            "POSTGRES_PASSWORD=",
            "REDIS_PASSWORD=",
            "AUTHELIA_JWT_SECRET=",
            "AUTHELIA_SESSION_SECRET=",
            "AUTHELIA_STORAGE_ENCRYPTION_KEY=",
        ]
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        try:
            env_path.chmod(0o600)
        except OSError:
            pass
        created.append(env_path)

    except KeyboardInterrupt:
        fail("Setup cancelled.", created)
    except subprocess.CalledProcessError:
        fail("A system command failed. See output above.", created)

    print(f"\n  wrote {env_path}")
    print("\n=== Phase 1 complete ===")
    print(f"  cd {compose_home}")
    print("  ./scripts/compose.sh up -d")
    print("\nVerify in a browser (no login yet):")
    print(f"  https://{sub_portainer}.{domain}")
    print(f"  https://{sub_traefik}.{domain}")
    print("\n=== Next (phase 2) ===")
    print("  python3 scripts/setup-authelia.py")
    print("  ./scripts/compose.sh --profile auth up -d")


if __name__ == "__main__":
    main()
