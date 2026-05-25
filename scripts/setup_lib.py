"""Shared helpers for Homelab-in-a-box setup scripts."""
from __future__ import annotations

import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates"

DEFAULT_COMPOSE_HOME = "/home/joe/homelab-in-a-box"
DEFAULT_APPDATA_ROOT = "/opt/appdata/docker-apps"
DEFAULT_DOMAIN_EXAMPLE = "yourdomain.app"

SECRET_ENV_KEYS = frozenset(
    {
        "CF_TUNNEL_TOKEN",
        "CF_DNS_API_TOKEN",
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "AUTHELIA_JWT_SECRET",
        "AUTHELIA_SESSION_SECRET",
        "AUTHELIA_STORAGE_ENCRYPTION_KEY",
        "AUTHELIA_DB_PASSWORD",
        "ROCKETCHAT_MONGO_PASSWORD",
    }
)

REGENERATE_REQUIRED_KEYS = (
    "COMPOSE_DIR",
    "APPDATA_ROOT",
    "PRIMARY_DOMAIN",
    "SUBDOMAIN_TRAEFIK",
    "SUBDOMAIN_PORTAINER",
    "SUBDOMAIN_MANAGER",
    "SUBDOMAIN_AUTH",
    "CF_TUNNEL_MODE",
    "CF_TUNNEL_NAME",
)

AUTHELIA_REGENERATE_KEYS = (
    "AUTHELIA_JWT_SECRET",
    "AUTHELIA_SESSION_SECRET",
    "AUTHELIA_STORAGE_ENCRYPTION_KEY",
    "REDIS_PASSWORD",
    "POSTGRES_PASSWORD",
)


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


def prompt_required(
    text: str,
    default: str = "",
    *,
    validator: Callable[[str], bool] | None = None,
    error_hint: str = "",
) -> str:
    while True:
        value = prompt(text, default) if default else input(f"{text}: ").strip()
        if not value:
            print("This field cannot be blank.")
            continue
        if validator and not validator(value):
            if error_hint:
                print(error_hint)
            continue
        return value


def prompt_choice(text: str, choices: tuple[str, ...], default: str) -> str:
    if default not in choices:
        raise ValueError(f"default {default!r} not in choices")
    options = ", ".join(choices)
    while True:
        raw = input(f"{text} ({options}) [{default}]: ").strip().lower()
        if not raw:
            raw = default
        if raw in choices:
            return raw
        print(f"Invalid choice '{raw}'. Enter exactly one of: {options}")


def prompt_yes(text: str, default: str = "y") -> bool:
    default = default.lower()
    while True:
        raw = prompt(text, default).lower()
        if raw in ("y", "yes", "1", "true"):
            return True
        if raw in ("n", "no", "0", "false"):
            return False
        print("Enter y or n.")


def prompt_secret(text: str) -> str:
    while True:
        a = getpass.getpass(f"{text}: ")
        b = getpass.getpass("Confirm: ")
        if a == b and a:
            return a
        print("Mismatch or empty — try again.")


def prompt_secret_quiet(text: str) -> str:
    value = prompt_secret(text)
    print("  (token saved — not shown again)")
    return value


def b64_secret(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def mask_secret(value: str, visible: int = 4) -> str:
    if not value:
        return "(empty)"
    if len(value) <= visible:
        return "****"
    return value[:visible] + "…" + ("*" * 8)


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        fail(f"Missing {path}")
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env


load_env = load_env_file


def normalize_env(env: dict[str, str], *, compose_dir: Path | None = None) -> dict[str, str]:
    """Accept legacy DOMAIN / missing COMPOSE_DIR keys."""
    out = dict(env)
    if not out.get("PRIMARY_DOMAIN") and out.get("DOMAIN"):
        out["PRIMARY_DOMAIN"] = out["DOMAIN"]
    if not out.get("DOMAIN") and out.get("PRIMARY_DOMAIN"):
        out["DOMAIN"] = out["PRIMARY_DOMAIN"]
    if not out.get("COMPOSE_DIR"):
        out["COMPOSE_DIR"] = str(compose_dir or REPO_ROOT)
    if not out.get("SUBDOMAIN_AUTH"):
        out["SUBDOMAIN_AUTH"] = "auth"
    return out


def validate_required_env(env: dict[str, str], keys: Iterable[str]) -> list[str]:
    missing = [k for k in keys if not env.get(k, "").strip()]
    return missing


def validate_regenerate_env(env: dict[str, str]) -> None:
    missing = validate_required_env(env, REGENERATE_REQUIRED_KEYS)
    if missing:
        fail(
            "Missing required .env values:\n  "
            + "\n  ".join(missing)
            + "\n\nEdit .env or run setup-bootstrap.py for a full interactive setup."
        )
    mode = env["CF_TUNNEL_MODE"].strip().lower()
    if mode not in ("token", "config"):
        fail("CF_TUNNEL_MODE must be 'token' or 'config'.")
    if mode == "token" and not env.get("CF_TUNNEL_TOKEN", "").strip():
        fail("CF_TUNNEL_MODE=token requires CF_TUNNEL_TOKEN in .env.")
    if not valid_domain(env["PRIMARY_DOMAIN"].lower()):
        fail(f"PRIMARY_DOMAIN is not a valid domain: {env['PRIMARY_DOMAIN']!r}")


def write_env_file(path: Path, values: dict[str, str], *, preserve_secrets_from: dict[str, str] | None = None) -> None:
    """Write .env; optionally keep existing secret values when new value is empty."""
    merged = dict(values)
    if preserve_secrets_from:
        for key in SECRET_ENV_KEYS:
            if not merged.get(key, "").strip() and preserve_secrets_from.get(key, "").strip():
                merged[key] = preserve_secrets_from[key]
    lines = [f"{k}={v}" for k, v in merged.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def render_template(template_path: Path, dest: Path, mapping: dict[str, str]) -> Path:
    text = fix_flattened_literal_newlines(template_path.read_text(encoding="utf-8"))
    for key, val in mapping.items():
        text = text.replace(key, val)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return dest


render = render_template


def fix_flattened_literal_newlines(text: str) -> str:
    """Repair YAML accidentally stored as one line with literal \\n sequences."""
    if "\\n" in text and text.count("\n") <= 3:
        return text.replace("\\n", "\n")
    return text


def build_template_mapping(env: dict[str, str]) -> dict[str, str]:
    domain = env.get("PRIMARY_DOMAIN") or env.get("DOMAIN", "")
    return {
        "__DOMAIN__": domain,
        "__CF_EMAIL__": env.get("CF_EMAIL", ""),
        "__SUBDOMAIN_AUTH__": env.get("SUBDOMAIN_AUTH", "auth"),
        "__SUBDOMAIN_TRAEFIK__": env.get("SUBDOMAIN_TRAEFIK", "traefik"),
        "__SUBDOMAIN_PORTAINER__": env.get("SUBDOMAIN_PORTAINER", "port"),
        "__SUBDOMAIN_MANAGER__": env.get("SUBDOMAIN_MANAGER", "manager"),
        "__SUBDOMAIN_ROCKETCHAT__": env.get("SUBDOMAIN_ROCKETCHAT", "sub"),
        "__AUTHELIA_JWT_SECRET__": env.get("AUTHELIA_JWT_SECRET", ""),
        "__AUTHELIA_SESSION_SECRET__": env.get("AUTHELIA_SESSION_SECRET", ""),
        "__AUTHELIA_STORAGE_ENCRYPTION_KEY__": env.get("AUTHELIA_STORAGE_ENCRYPTION_KEY", ""),
        "__REDIS_PASSWORD__": env.get("REDIS_PASSWORD", ""),
        "__AUTHELIA_DB_PASSWORD__": env.get("AUTHELIA_DB_PASSWORD", env.get("POSTGRES_PASSWORD", "")),
        "__ADMIN_USERNAME__": env.get("AUTHELIA_USERNAME", "admin"),
        "__ADMIN_PASSWORD_HASH__": env.get("AUTHELIA_PASSWORD_HASH", ""),
        "__ADMIN_EMAIL__": env.get("AUTHELIA_EMAIL", f"admin@{domain}"),
        "__TUNNEL_ID__": env.get("CF_TUNNEL_ID", ""),
        "__HOST_IP__": env.get("HOST_IP", "127.0.0.1"),
        "__DOMAIN_NAME__": domain,
        "__EMAIL__": env.get("CF_EMAIL", ""),
    }


def ensure_directories(appdata_root: Path) -> list[Path]:
    paths = [
        appdata_root / "traefik" / "dynamic",
        appdata_root / "traefik" / "logs",
        appdata_root / "cloudflared",
        appdata_root / "portainer" / "data",
        appdata_root / "traefik-manager" / "config",
        appdata_root / "traefik-manager" / "backups",
        appdata_root / "authelia",
        appdata_root / "postgres" / "init",
        appdata_root / "postgres" / "data",
        appdata_root / "redis" / "data",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
    log_file = appdata_root / "traefik" / "logs" / "access.log"
    log_file.touch(exist_ok=True)
    (appdata_root / "authelia" / "notification.txt").touch(exist_ok=True)
    return paths


def authelia_env_ready(env: dict[str, str]) -> bool:
    return all(env.get(k, "").strip() for k in AUTHELIA_REGENERATE_KEYS)


def regenerate_configs_from_env(
    env: dict[str, str],
    *,
    compose_dir: Path,
    quiet: bool = False,
) -> list[Path]:
    """Re-render appdata (and optional Authelia) from .env. Does not modify .env."""
    env = normalize_env(env, compose_dir=compose_dir)
    validate_regenerate_env(env)

    appdata_root = Path(env["APPDATA_ROOT"])
    mapping = build_template_mapping(env)
    written: list[Path] = []

    def _write(template_rel: str, dest: Path) -> None:
        src = TEMPLATES / template_rel
        if not src.exists():
            fail(f"Missing template: {src}")
        render_template(src, dest, mapping)
        written.append(dest)
        if not quiet:
            print(f"  wrote {dest}")

    ensure_directories(appdata_root)
    if not quiet:
        print(f"\nUsing .env from {compose_dir / '.env'}")
        print(f"Appdata root: {appdata_root}\n")

    _write("traefik/traefik.yml.template", appdata_root / "traefik" / "traefik.yml")
    try:
        (appdata_root / "traefik" / "traefik.yml").chmod(0o644)
    except OSError:
        pass

    _write(
        "traefik/dynamic/config.yml.template",
        appdata_root / "traefik" / "dynamic" / "config.yml",
    )

    config_dest = compose_dir / "config.yaml"
    if (TEMPLATES / "config.yaml.template").exists():
        config_text = fix_flattened_literal_newlines(
            (TEMPLATES / "config.yaml.template").read_text(encoding="utf-8")
        )
        config_text = (
            config_text.replace("__DOMAIN__", mapping["__DOMAIN__"])
            .replace("__CF_EMAIL__", mapping["__CF_EMAIL__"])
            .replace("/home/joe/homelab-in-a-box", str(compose_dir))
            .replace("/opt/appdata/docker-apps", str(appdata_root))
            .replace("America/New_York", env.get("TZ", "America/New_York"))
        )
        config_dest.write_text(config_text, encoding="utf-8")
        written.append(config_dest)
        if not quiet:
            print(f"  wrote {config_dest}")

    if authelia_env_ready(env):
        if not quiet:
            print("\nAuthelia secrets found — regenerating Authelia configs.")
        _write("authelia/configuration.yml.template", appdata_root / "authelia" / "configuration.yml")
        _write("traefik/dynamic/authelia.yml.template", appdata_root / "traefik" / "dynamic" / "authelia.yml")
        if env.get("AUTHELIA_DB_PASSWORD", "").strip() or env.get("POSTGRES_PASSWORD", "").strip():
            _write(
                "postgres/init-authelia.sql.template",
                appdata_root / "postgres" / "init" / "01-authelia.sql",
            )
        overrides = compose_dir / "compose.auth-overrides.yaml"
        if (TEMPLATES / "compose.auth-overrides.yaml.template").exists():
            _write("compose.auth-overrides.yaml.template", overrides)
    else:
        if not quiet:
            print("Authelia env values not found; skipping Authelia config regeneration.")

    if env.get("CF_TUNNEL_MODE") == "config" and env.get("CF_TUNNEL_ID", "").strip():
        cf_cfg = appdata_root / "cloudflared" / "config.yml"
        if (TEMPLATES / "cloudflared" / "config.yml.template").exists():
            _write("cloudflared/config.yml.template", cf_cfg)

    return written


def print_env_summary(env: dict[str, str]) -> None:
    print("\nCurrent .env (secrets masked):")
    for key in sorted(env.keys()):
        val = env[key]
        if key in SECRET_ENV_KEYS:
            val = mask_secret(val)
        print(f"  {key}={val}")


def valid_domain(d: str) -> bool:
    return bool(
        re.fullmatch(
            r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+",
            d.lower(),
        )
    )


def valid_email(e: str) -> bool:
    return "@" in e and "." in e.split("@")[-1]


def valid_subdomain(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", s.lower()))


def require_not_root() -> None:
    if os.name == "posix" and os.geteuid() == 0:
        fail(
            "Run as your deploy user (e.g. joe), not root:\n"
            "  sudo -u joe -H python3 scripts/setup-bootstrap.py"
        )


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(f"  $ {' '.join(cmd)}")
    if capture:
        result = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if check and result.returncode != 0:
            _print_capture_failure(cmd, result)
            raise subprocess.CalledProcessError(result.returncode, cmd)
        return result
    return subprocess.run(cmd, text=True, check=check)


def _print_capture_failure(cmd: list[str], result: subprocess.CompletedProcess[str]) -> None:
    print(f"\nCommand failed (exit {result.returncode}): {' '.join(cmd)}", file=sys.stderr)
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    if stdout.strip():
        print("--- stdout ---", file=sys.stderr)
        print(stdout.strip(), file=sys.stderr)
    if stderr.strip():
        print("--- stderr ---", file=sys.stderr)
        print(stderr.strip(), file=sys.stderr)


def fail(message: str, created: list[Path] | None = None) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    if created:
        print("\nFiles written before failure (safe to re-run or remove):", file=sys.stderr)
        for path in created:
            print(f"  - {path}", file=sys.stderr)
    print("\nFix the issue above, then re-run.", file=sys.stderr)
    sys.exit(1)


def handle_existing_env(env_path: Path) -> str:
    """Return 'regenerate', 'interactive', or 'quit'."""
    print(f"\nExisting .env found: {env_path}")
    print_env_summary(normalize_env(load_env_file(env_path), compose_dir=env_path.parent))
    print("\nOptions:")
    print("  regenerate — re-render config files from .env (does not change secrets)")
    print("  interactive — full setup prompts (can overwrite .env)")
    print("  quit        — exit without changes")
    return prompt_choice("Choose action", ("regenerate", "interactive", "quit"), "regenerate")


def parse_tunnel_list_json(result: subprocess.CompletedProcess[str]) -> list[dict]:
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        fail(
            "cloudflared tunnel list failed.\n"
            f"{err}\n"
            "Run: cloudflared tunnel login\n"
            "Then re-run setup-bootstrap.py"
        )
    stdout = (result.stdout or "").strip()
    if not stdout:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        fail(
            f"cloudflared tunnel list returned invalid JSON: {exc}\n"
            f"Output was: {stdout[:400]}"
        )
    if not isinstance(data, list):
        fail("cloudflared tunnel list returned unexpected data (expected a JSON array).")
    return data


def find_tunnel_id(tunnels: list[dict], tunnel_name: str) -> str:
    for entry in tunnels:
        if entry.get("name") == tunnel_name:
            tid = entry.get("id")
            if tid:
                return str(tid)
    return ""


def cloudflared_bin() -> str:
    path = shutil.which("cloudflared")
    if not path:
        fail("cloudflared not found. Run: sudo bash scripts/install-server.sh")
    return path


def hash_password_argon2(password: str) -> str:
    try:
        from argon2 import PasswordHasher

        ph = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
        )
        return ph.hash(password)
    except ImportError:
        pass

    print("argon2-cffi not installed; using Docker to hash password...")
    cmd = [
        "docker",
        "run",
        "--rm",
        "authelia/authelia:latest",
        "authelia",
        "crypto",
        "hash",
        "generate",
        "argon2",
        "--password",
        password,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        fail(
            f"Could not hash password via Docker.\n{err}\n"
            "Install: pip install -r requirements.txt (or run scripts/install-server.sh)"
        )
    for line in (result.stdout or "").splitlines():
        if line.startswith("$argon2"):
            return line.strip()
    fail("Could not parse argon2 hash from authelia output.")


def setup_cloudflare_tunnel_config_mode(
    *,
    domain: str,
    appdata_root: Path,
    tunnel_name: str,
    hostnames: list[str],
    created: list[Path],
) -> str:
    cf_bin = cloudflared_bin()
    home_cf = Path.home() / ".cloudflared"
    home_cf.mkdir(parents=True, exist_ok=True)
    cert = home_cf / "cert.pem"
    if not cert.exists():
        print("\n--- Cloudflare login (browser) ---")
        print("Open the URL on any device with a browser (phone/laptop).")
        print("Do not paste the login URL into bash — open it in a browser only.")
        input("Press Enter to start login...")
        try:
            run([cf_bin, "tunnel", "login"])
        except subprocess.CalledProcessError:
            fail(
                "cloudflared tunnel login failed.\n"
                "Complete login in a browser, then re-run setup-bootstrap.py",
                created,
            )
        if not cert.exists():
            fail(
                f"Login finished but {cert} is missing.\n"
                "Re-run: cloudflared tunnel login",
                created,
            )

    list_result = run(
        [cf_bin, "tunnel", "list", "--output", "json"],
        check=False,
        capture=True,
    )
    tunnels = parse_tunnel_list_json(list_result)
    tunnel_id = find_tunnel_id(tunnels, tunnel_name)

    if tunnel_id:
        print(f"  Reusing existing tunnel '{tunnel_name}' ({tunnel_id})")
    else:
        print(f"\n--- Creating tunnel '{tunnel_name}' ---")
        try:
            run([cf_bin, "tunnel", "create", tunnel_name])
        except subprocess.CalledProcessError:
            fail(
                f"Could not create tunnel '{tunnel_name}'.\n"
                "Check Cloudflare permissions and try again.",
                created,
            )
        list_result = run(
            [cf_bin, "tunnel", "list", "--output", "json"],
            capture=True,
        )
        tunnels = parse_tunnel_list_json(list_result)
        tunnel_id = find_tunnel_id(tunnels, tunnel_name)
        if not tunnel_id:
            names = [t.get("name") for t in tunnels if t.get("name")]
            fail(
                f"Tunnel '{tunnel_name}' was not found after create.\n"
                f"Tunnels visible to cloudflared: {names or '(none)'}\n"
                "Try: cloudflared tunnel list",
                created,
            )

    dest_dir = appdata_root / "cloudflared"
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = home_cf / f"{tunnel_id}.json"
    if not src.exists():
        fail(
            f"Missing credentials file: {src}\n"
            "Re-run cloudflared tunnel login and tunnel create.",
            created,
        )
    dest = dest_dir / f"{tunnel_id}.json"
    shutil.copy2(src, dest)
    dest.chmod(0o600)
    created.append(dest)

    config_dest = dest_dir / "config.yml"
    render_template(
        TEMPLATES / "cloudflared" / "config.yml.template",
        config_dest,
        {"__TUNNEL_ID__": tunnel_id, "__DOMAIN__": domain},
    )
    created.append(config_dest)

    print("\n--- DNS routes ---")
    for host in hostnames:
        run([cf_bin, "tunnel", "route", "dns", tunnel_name, host], check=False)

    return tunnel_id


def backup_users_offline(users_path: Path, deploy_user: str) -> None:
    if not prompt_yes("Backup users_database.yml for offline storage?", "y"):
        return
    backup_dir = Path(
        prompt_required("Backup directory", str(Path.home() / "authelia-offline-backups"))
    )
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = backup_dir / f"users_database_{deploy_user}_{stamp}.yml"
    shutil.copy2(users_path, dest)
    dest.chmod(0o600)
    try:
        backup_dir.chmod(0o700)
    except OSError:
        pass
    print(f"\n  Backup: {dest}")
    print(f"  From your PC: scp {deploy_user}@YOUR_VPS:{dest} .")
