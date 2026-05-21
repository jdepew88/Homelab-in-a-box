#!/usr/bin/env python3
"""
Phase 2 — Authelia (1FA) + lock down Traefik, Portainer, Traefik Manager.

Requires Phase 1 (.env from setup-bootstrap.py) and stack already reachable via tunnel.

  python3 scripts/setup-authelia.py
  ./scripts/compose.sh --profile auth up -d
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from setup_lib import (
    TEMPLATES,
    backup_users_offline,
    b64_secret,
    hash_password_argon2,
    prompt,
    prompt_secret,
    prompt_yes,
    render,
    require_not_root,
)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


def main() -> None:
    require_not_root()

    compose_home = Path(
        prompt("Compose directory", "/home/joe/docker-vps-stack")
    )
    env_path = compose_home / ".env"
    if not env_path.exists():
        sys.exit(f"Missing {env_path} — run setup-bootstrap.py first.")

    env = load_env(env_path)
    domain = env.get("DOMAIN") or prompt("Primary domain")
    appdata_root = Path(env.get("APPDATA_ROOT", "/opt/appdata/docker-apps"))
    sub_auth = env.get("SUBDOMAIN_AUTH", "auth")

    print("\n=== Phase 2: Authelia (1FA) ===\n")

    authelia_user = prompt("Authelia username")
    if not re.fullmatch(r"[a-zA-Z0-9._-]+", authelia_user):
        sys.exit("Invalid username.")
    authelia_email = prompt("Email", f"{authelia_user}@{domain}")
    authelia_password = prompt_secret("Authelia password")

    jwt_secret = b64_secret(48)
    session_secret = b64_secret(48)
    storage_key = b64_secret(32)
    postgres_password = b64_secret(32)
    redis_password = b64_secret(32)
    authelia_db_password = b64_secret(32)
    password_hash = hash_password_argon2(authelia_password)

    mapping = {
        "__DOMAIN__": domain,
        "__CF_EMAIL__": env.get("CF_EMAIL", ""),
        "__SUBDOMAIN_AUTH__": sub_auth,
        "__SUBDOMAIN_PORTAINER__": env.get("SUBDOMAIN_PORTAINER", "port"),
        "__SUBDOMAIN_TRAEFIK__": env.get("SUBDOMAIN_TRAEFIK", "traefik"),
        "__SUBDOMAIN_MANAGER__": env.get("SUBDOMAIN_MANAGER", "manager"),
        "__SUBDOMAIN_ROCKETCHAT__": env.get("SUBDOMAIN_ROCKETCHAT", "sub"),
        "__AUTHELIA_JWT_SECRET__": jwt_secret,
        "__AUTHELIA_SESSION_SECRET__": session_secret,
        "__AUTHELIA_STORAGE_ENCRYPTION_KEY__": storage_key,
        "__REDIS_PASSWORD__": redis_password,
        "__AUTHELIA_DB_PASSWORD__": authelia_db_password,
        "__ADMIN_USERNAME__": authelia_user,
        "__ADMIN_PASSWORD_HASH__": password_hash,
        "__ADMIN_EMAIL__": authelia_email,
    }

    print("\nWriting Authelia + Traefik middleware...")
    render(
        TEMPLATES / "authelia" / "configuration.yml.template",
        appdata_root / "authelia" / "configuration.yml",
        mapping,
    )
    users_path = appdata_root / "authelia" / "users_database.yml"
    render(
        TEMPLATES / "authelia" / "users_database.yml.template",
        users_path,
        mapping,
    )
    render(
        TEMPLATES / "postgres" / "init-authelia.sql.template",
        appdata_root / "postgres" / "init" / "01-authelia.sql",
        mapping,
    )
    render(
        TEMPLATES / "traefik" / "dynamic" / "authelia.yml.template",
        appdata_root / "traefik" / "dynamic" / "authelia.yml",
        mapping,
    )
    render(
        TEMPLATES / "compose.auth-overrides.yaml.template",
        compose_home / "compose.auth-overrides.yaml",
        mapping,
    )

    (appdata_root / "authelia").mkdir(parents=True, exist_ok=True)
    (appdata_root / "authelia" / "notification.txt").touch(exist_ok=True)
    (appdata_root / "postgres" / "data").mkdir(parents=True, exist_ok=True)
    (appdata_root / "postgres" / "init").mkdir(parents=True, exist_ok=True)
    (appdata_root / "redis" / "data").mkdir(parents=True, exist_ok=True)

    deploy_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "joe"
    backup_users_offline(users_path, deploy_user)

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updates = {
        "POSTGRES_PASSWORD": postgres_password,
        "REDIS_PASSWORD": redis_password,
        "AUTHELIA_JWT_SECRET": jwt_secret,
        "AUTHELIA_SESSION_SECRET": session_secret,
        "AUTHELIA_STORAGE_ENCRYPTION_KEY": storage_key,
        "SUBDOMAIN_AUTH": sub_auth,
    }
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key, _, _ = line.partition("=")
            key = key.strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    print(f"\n  updated {env_path}")
    print(f"  wrote {compose_home / 'compose.auth-overrides.yaml'}")
    print("\n=== Phase 2 complete ===")
    print(f"  cd {compose_home}")
    print("  ./scripts/compose.sh --profile auth up -d")
    print(f"\nLogin at https://{sub_auth}.{domain}")
    print(f"Then use https://{env.get('SUBDOMAIN_PORTAINER', 'port')}.{domain} (protected)")


if __name__ == "__main__":
    main()
