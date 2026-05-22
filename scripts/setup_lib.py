"""Shared helpers for setup-bootstrap.py and setup-authelia.py."""
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
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates"

DEFAULT_COMPOSE_HOME = "/home/joe/homelab-in-a-box"
DEFAULT_APPDATA_ROOT = "/opt/appdata/docker-apps"
DEFAULT_DOMAIN_EXAMPLE = "yourdomain.app"


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
    """Read a secret without printing it afterward."""
    value = prompt_secret(text)
    print("  (token saved — not shown again)")
    return value


def b64_secret(n: int = 32) -> str:
    return secrets.token_urlsafe(n)


def render(template_path: Path, dest: Path, mapping: dict[str, str]) -> None:
    text = template_path.read_text(encoding="utf-8")
    for key, val in mapping.items():
        text = text.replace(key, val)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    print(f"  wrote {dest}")


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
    if result.stdout and result.stdout.strip():
        print("--- stdout ---", file=sys.stderr)
        print(result.stdout.strip(), file=sys.stderr)
    if result.stderr and result.stderr.strip():
        print("--- stderr ---", file=sys.stderr)
        print(result.stderr.strip(), file=sys.stderr)


def fail(message: str, created: list[Path] | None = None) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    if created:
        print("\nFiles written before failure (safe to re-run setup or remove manually):", file=sys.stderr)
        for path in created:
            print(f"  - {path}", file=sys.stderr)
    print("\nFix the issue above, then re-run the same setup script.", file=sys.stderr)
    sys.exit(1)


def warn_existing_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    print(f"\nNote: {env_path} already exists.")
    if not prompt_yes("Update/overwrite bootstrap values in .env?", "n"):
        fail(
            f"Keeping existing {env_path}. "
            "Delete it or answer 'y' to overwrite if you intend a fresh bootstrap."
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


def parse_tunnel_list_json(result: subprocess.CompletedProcess[str]) -> list[dict]:
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        fail(
            "cloudflared tunnel list failed.\n"
            f"{err}\n"
            "Run: cloudflared tunnel login\n"
            "Then re-run: python3 scripts/setup-bootstrap.py"
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
        fail(f"Could not hash password via Docker.\n{err}\nInstall: pip3 install -r scripts/requirements.txt")
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
    render(
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
