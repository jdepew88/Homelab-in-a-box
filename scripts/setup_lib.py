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

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = REPO_ROOT / "templates"


def prompt(text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    return value or default


def prompt_yes(text: str, default: str = "y") -> bool:
    return prompt(text, default).lower() in ("y", "yes", "1", "true")


def prompt_secret(text: str) -> str:
    while True:
        a = getpass.getpass(f"{text}: ")
        b = getpass.getpass("Confirm: ")
        if a == b and a:
            return a
        print("Mismatch or empty — try again.")


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
    return bool(re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+", d))


def require_not_root() -> None:
    if os.name == "posix" and os.geteuid() == 0:
        print(
            "Run as your deploy user (e.g. joe), not root:\n"
            "  sudo -u joe -H python3 scripts/setup-bootstrap.py",
            file=sys.stderr,
        )
        sys.exit(1)


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, text=True, check=check)


def cloudflared_bin() -> str:
    path = shutil.which("cloudflared")
    if not path:
        sys.exit("cloudflared not found. Run: sudo bash scripts/install-server.sh")
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
        sys.exit("Install argon2-cffi or ensure Docker is available for password hashing.")
    for line in result.stdout.splitlines():
        if line.startswith("$argon2"):
            return line.strip()
    sys.exit("Could not parse password hash from authelia output.")


def setup_cloudflare_tunnel_config_mode(
    *,
    domain: str,
    appdata_root: Path,
    tunnel_name: str,
    hostnames: list[str],
) -> str:
    cf_bin = cloudflared_bin()
    home_cf = Path.home() / ".cloudflared"
    home_cf.mkdir(parents=True, exist_ok=True)
    cert = home_cf / "cert.pem"
    if not cert.exists():
        print("\n--- Cloudflare login (browser) ---")
        print("Open the URL on any device with a browser (phone/laptop).")
        input("Press Enter to start login...")
        run([cf_bin, "tunnel", "login"])

    list_result = run([cf_bin, "tunnel", "list", "--output", "json"], check=False)
    tunnel_id = ""
    if list_result.returncode == 0 and list_result.stdout.strip():
        try:
            for t in json.loads(list_result.stdout):
                if t.get("name") == tunnel_name:
                    tunnel_id = t["id"]
                    print(f"  Reusing tunnel '{tunnel_name}' ({tunnel_id})")
                    break
        except json.JSONDecodeError:
            pass
    if not tunnel_id:
        run([cf_bin, "tunnel", "create", tunnel_name])
        list_result = run([cf_bin, "tunnel", "list", "--output", "json"])
        for t in json.loads(list_result.stdout):
            if t.get("name") == tunnel_name:
                tunnel_id = t["id"]
                break
    if not tunnel_id:
        sys.exit(f"Tunnel '{tunnel_name}' not found.")

    dest_dir = appdata_root / "cloudflared"
    dest_dir.mkdir(parents=True, exist_ok=True)
    src = home_cf / f"{tunnel_id}.json"
    if not src.exists():
        sys.exit(f"Missing {src}")
    dest = dest_dir / f"{tunnel_id}.json"
    shutil.copy2(src, dest)
    dest.chmod(0o600)

    render(
        TEMPLATES / "cloudflared" / "config.yml.template",
        dest_dir / "config.yml",
        {"__TUNNEL_ID__": tunnel_id, "__DOMAIN__": domain},
    )

    print("\n--- DNS routes ---")
    for host in hostnames:
        run([cf_bin, "tunnel", "route", "dns", tunnel_name, host], check=False)
    return tunnel_id


def backup_users_offline(users_path: Path, deploy_user: str) -> None:
    if not prompt_yes("Backup users_database.yml for offline storage?", "y"):
        return
    backup_dir = Path(prompt("Backup directory", str(Path.home() / "authelia-offline-backups")))
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
    print(f"  scp {deploy_user}@YOUR_VPS:{dest} .")
