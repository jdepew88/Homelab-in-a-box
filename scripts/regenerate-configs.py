#!/usr/bin/env python3
"""
Regenerate Traefik/appdata config files from an existing .env (no prompts).

  cd ~/homelab-in-a-box
  cp .env .env.bak.$(date +%Y%m%d-%H%M%S)
  python3 scripts/regenerate-configs.py
  ./scripts/compose.sh down && ./scripts/compose.sh up -d
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from setup_lib import (  # noqa: E402
    REPO_ROOT as _ROOT,
    fail,
    load_env_file,
    normalize_env,
    regenerate_configs_from_env,
    require_not_root,
)


def main() -> None:
    require_not_root()
    compose_dir = _ROOT
    env_path = compose_dir / ".env"
    if not env_path.exists():
        fail(
            f"No .env at {env_path}\n"
            "Run: python3 scripts/setup-bootstrap.py"
        )

    env = normalize_env(load_env_file(env_path), compose_dir=compose_dir)
    print("=== Homelab-in-a-box — regenerate configs from .env ===")
    print("( .env is not modified )\n")

    try:
        written = regenerate_configs_from_env(env, compose_dir=compose_dir)
    except SystemExit:
        raise
    except Exception as exc:
        fail(str(exc))

    print(f"\nDone. {len(written)} file(s) written.")
    print("\nNext:")
    print(f"  cd {compose_dir}")
    print("  ./scripts/compose.sh down")
    print("  ./scripts/compose.sh up -d")
    print("  docker ps")
    print("  docker logs traefik --tail=100")
    print("  docker logs cloudflared --tail=100")
    print("  ./scripts/compose.sh config | grep -i Host")


if __name__ == "__main__":
    main()
