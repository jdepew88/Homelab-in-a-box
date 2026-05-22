#!/usr/bin/env python3
"""
Phase 2 — Homelab-in-a-box: Authelia (1FA) + lock down apps.

  python3 scripts/setup-authelia.py
  ./scripts/compose.sh --profile auth up -d
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from setup_lib import (  # noqa: E402
    DEFAULT_COMPOSE_HOME,
    DEFAULT_APPDATA_ROOT,
    TEMPLATES,
    backup_users_offline,
    b64_secret,
    fail,
    hash_password_argon2,
    load_env,
    prompt_required,
    prompt_secret,
    render,
    require_not_root,
    valid_domain,
    valid_email,
    valid_subdomain,
)


def main() -> None:
    require_not_root()
    created: list[Path] = []

    print("=== Homelab-in-a-box — Phase 2: Authelia (1FA) ===\n")

    try:
        compose_home = Path(
            prompt_required("Compose directory", DEFAULT_COMPOSE_HOME)
        )
        env_path = compose_home / ".env"
        if not env_path.exists():
            fail(
                f"Missing {env_path}\n"
                "Run phase 1 first: python3 scripts/setup-bootstrap.py"
            )

        env = load_env(env_path)
        domain = env.get("DOMAIN") or ""
        if not domain or not valid_domain(domain):
            domain = prompt_required(
                "Primary domain",
                validator=valid_domain,
                error_hint="Enter the same domain you used in phase 1.",
            ).lower()
        appdata_root = Path(env.get("APPDATA_ROOT") or DEFAULT_APPDATA_ROOT)
        sub_auth = prompt_required(
            "Authelia subdomain",
            env.get("SUBDOMAIN_AUTH", "auth"),
            validator=valid_subdomain,
        ).lower()

        authelia_user = prompt_required("Authelia username")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", authelia_user):
            fail("Username may only contain letters, numbers, dot, underscore, hyphen.")
        authelia_email = prompt_required(
            "Authelia email",
            f"{authelia_user}@{domain}",
            validator=valid_email,
        )
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
        for template, dest in [
            ("authelia/configuration.yml.template", appdata_root / "authelia" / "configuration.yml"),
            ("authelia/users_database.yml.template", appdata_root / "authelia" / "users_database.yml"),
            ("postgres/init-authelia.sql.template", appdata_root / "postgres" / "init" / "01-authelia.sql"),
            ("traefik/dynamic/authelia.yml.template", appdata_root / "traefik" / "dynamic" / "authelia.yml"),
            (
                "compose.auth-overrides.yaml.template",
                compose_home / "compose.auth-overrides.yaml",
            ),
        ]:
            p = Path(dest)
            render(TEMPLATES / template, p, mapping)
            created.append(p)

        users_path = appdata_root / "authelia" / "users_database.yml"
        (appdata_root / "authelia").mkdir(parents=True, exist_ok=True)
        (appdata_root / "authelia" / "notification.txt").touch(exist_ok=True)
        (appdata_root / "postgres" / "data").mkdir(parents=True, exist_ok=True)
        (appdata_root / "postgres" / "init").mkdir(parents=True, exist_ok=True)
        (appdata_root / "redis" / "data").mkdir(parents=True, exist_ok=True)

        deploy_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "joe"
        backup_users_offline(users_path, deploy_user)

        updates = {
            "POSTGRES_PASSWORD": postgres_password,
            "REDIS_PASSWORD": redis_password,
            "AUTHELIA_JWT_SECRET": jwt_secret,
            "AUTHELIA_SESSION_SECRET": session_secret,
            "AUTHELIA_STORAGE_ENCRYPTION_KEY": storage_key,
            "SUBDOMAIN_AUTH": sub_auth,
        }
        lines = env_path.read_text(encoding="utf-8").splitlines()
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
        created.append(env_path)

    except KeyboardInterrupt:
        fail("Setup cancelled.", created)

    print(f"\n  updated {env_path}")
    print("\n=== Phase 2 complete ===")
    print(f"  cd {compose_home}")
    print("  ./scripts/compose.sh --profile auth up -d")
    print(f"\n  https://{sub_auth}.{domain}  (sign in)")
    print(f"  https://{env.get('SUBDOMAIN_PORTAINER', 'port')}.{domain}  (protected)")


if __name__ == "__main__":
    main()
