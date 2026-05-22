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
    handle_existing_env,
    load_env_file,
    normalize_env,
    prompt_choice,
    prompt_required,
    prompt_secret_quiet,
    regenerate_configs_from_env,
    render_template,
    require_not_root,
    setup_cloudflare_tunnel_config_mode,
    valid_domain,
    valid_email,
    valid_subdomain,
    write_env_file,
)


def _interactive_bootstrap(compose_home: Path, existing: dict[str, str] | None) -> None:
    created: list[Path] = []
    old = existing or {}

    try:
        appdata_root = Path(
            prompt_required(
                "Appdata root",
                old.get("APPDATA_ROOT") or DEFAULT_APPDATA_ROOT,
            )
        )
        domain = prompt_required(
            "Primary domain",
            old.get("PRIMARY_DOMAIN") or old.get("DOMAIN") or DEFAULT_DOMAIN_EXAMPLE,
            validator=valid_domain,
            error_hint=f"Use a real hostname like {DEFAULT_DOMAIN_EXAMPLE} (lowercase, no https://).",
        ).lower()
        cf_email = prompt_required(
            "Cloudflare account email",
            old.get("CF_EMAIL", ""),
            validator=valid_email,
            error_hint="Enter the email on your Cloudflare account.",
        )
        tz = prompt_required("Timezone", old.get("TZ", "America/New_York"))
        sub_traefik = prompt_required(
            "Traefik dashboard subdomain",
            old.get("SUBDOMAIN_TRAEFIK", "traefik"),
            validator=valid_subdomain,
        ).lower()
        sub_portainer = prompt_required(
            "Portainer subdomain",
            old.get("SUBDOMAIN_PORTAINER", "port"),
            validator=valid_subdomain,
        ).lower()
        sub_manager = prompt_required(
            "Traefik Manager subdomain",
            old.get("SUBDOMAIN_MANAGER", "manager"),
            validator=valid_subdomain,
        ).lower()

        print("\n--- Cloudflare Tunnel ---")
        print("token — paste connector token from Zero Trust (best for headless VPS)")
        print("config — cloudflared login on this server + auto DNS (needs browser once)\n")
        mode = prompt_choice("Tunnel mode", ("token", "config"), old.get("CF_TUNNEL_MODE", "token"))

        cf_tunnel_token = old.get("CF_TUNNEL_TOKEN", "") if mode == "token" else ""
        tunnel_id = old.get("CF_TUNNEL_ID", "")
        tunnel_name = prompt_required(
            "Tunnel name (label)",
            old.get("CF_TUNNEL_NAME") or f"homelab-{domain.replace('.', '-')}",
        )

        if mode == "token":
            print("\nOn your laptop: Zero Trust → Networks → Tunnels → Create tunnel → Docker")
            print("Add Public Hostnames → http://traefik:80 for:")
            print(f"  {sub_traefik}.{domain}")
            print(f"  {sub_portainer}.{domain}")
            print(f"  {sub_manager}.{domain}")
            print(f"  (optional) *.{domain}\n")
            if cf_tunnel_token:
                reuse = prompt_choice(
                    "Reuse existing CF_TUNNEL_TOKEN from .env?",
                    ("yes", "no"),
                    "yes",
                )
                if reuse == "no":
                    cf_tunnel_token = prompt_secret_quiet("Paste CF_TUNNEL_TOKEN")
            else:
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

        env_values = {
            "COMPOSE_PROJECT_NAME": "homelab-in-a-box",
            "COMPOSE_DIR": str(compose_home),
            "TZ": tz,
            "DOMAIN": domain,
            "PRIMARY_DOMAIN": domain,
            "CF_EMAIL": cf_email,
            "CF_TUNNEL_MODE": mode,
            "CF_TUNNEL_TOKEN": cf_tunnel_token,
            "CF_TUNNEL_NAME": tunnel_name,
            "CF_TUNNEL_ID": tunnel_id,
            "CF_DNS_API_TOKEN": old.get("CF_DNS_API_TOKEN", ""),
            "APPDATA_ROOT": str(appdata_root),
            "SUBDOMAIN_TRAEFIK": sub_traefik,
            "SUBDOMAIN_PORTAINER": sub_portainer,
            "SUBDOMAIN_MANAGER": sub_manager,
            "SUBDOMAIN_AUTH": old.get("SUBDOMAIN_AUTH", "auth"),
            "TM_COOKIE_SECURE": old.get("TM_COOKIE_SECURE", "true"),
            "POSTGRES_PASSWORD": old.get("POSTGRES_PASSWORD", ""),
            "REDIS_PASSWORD": old.get("REDIS_PASSWORD", ""),
            "AUTHELIA_JWT_SECRET": old.get("AUTHELIA_JWT_SECRET", ""),
            "AUTHELIA_SESSION_SECRET": old.get("AUTHELIA_SESSION_SECRET", ""),
            "AUTHELIA_STORAGE_ENCRYPTION_KEY": old.get("AUTHELIA_STORAGE_ENCRYPTION_KEY", ""),
            "AUTHELIA_DB_PASSWORD": old.get("AUTHELIA_DB_PASSWORD", ""),
            "SUBDOMAIN_ROCKETCHAT": old.get("SUBDOMAIN_ROCKETCHAT", "sub"),
            "ROCKETCHAT_ROOT_URL": old.get("ROCKETCHAT_ROOT_URL", f"https://sub.{domain}"),
            "ROCKETCHAT_IMAGE": old.get(
                "ROCKETCHAT_IMAGE",
                "registry.rocket.chat/rocketchat/rocket.chat:7.4.0",
            ),
            "ROCKETCHAT_MONGO_PASSWORD": old.get("ROCKETCHAT_MONGO_PASSWORD", ""),
        }

        env_path = compose_home / ".env"
        write_env_file(env_path, env_values, preserve_secrets_from=old)
        created.append(env_path)

        env = normalize_env(env_values, compose_dir=compose_home)
        regenerate_configs_from_env(env, compose_dir=compose_home)

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

    except KeyboardInterrupt:
        fail("Setup cancelled.", created)
    except subprocess.CalledProcessError:
        fail("A system command failed. See output above.", created)


def main() -> None:
    require_not_root()

    print("=== Homelab-in-a-box — Phase 1: Bootstrap ===\n")
    print("Tunnel + Traefik + Portainer (Authelia comes in phase 2).")
    print("Services are reachable without login until you run setup-authelia.py.\n")

    compose_home = Path(
        prompt_required("Compose directory", DEFAULT_COMPOSE_HOME, validator=lambda p: bool(p))
    )
    env_path = compose_home / ".env"

    if env_path.exists():
        action = handle_existing_env(env_path)
        if action == "quit":
            print("Exiting without changes.")
            return
        if action == "regenerate":
            env = normalize_env(load_env_file(env_path), compose_dir=compose_home)
            regenerate_configs_from_env(env, compose_dir=compose_home)
            print("\n=== Configs regenerated ( .env unchanged ) ===")
            print(f"  cd {compose_home}")
            print("  ./scripts/compose.sh down")
            print("  ./scripts/compose.sh up -d")
            return
        _interactive_bootstrap(compose_home, load_env_file(env_path))
        return

    _interactive_bootstrap(compose_home, None)


if __name__ == "__main__":
    main()
