#!/usr/bin/env python3
"""
Register an optional compose stack from stacks/.

  python3 scripts/add_stack.py                    # list stacks
  python3 scripts/add_stack.py rocketchat       # enable built-in profile hint
  python3 scripts/add_stack.py stacks/myapp.compose.yaml
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
STACKS_SRC = REPO_ROOT / "stacks"
STACKS_DIR = REPO_ROOT / "compose.stacks"
ENABLED_FILE = REPO_ROOT / "compose.stacks.enabled"


def list_stacks() -> list[Path]:
    return sorted(STACKS_SRC.glob("*.compose.yaml")) + sorted(
        STACKS_SRC.glob("*.compose.yaml.example")
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Available stack templates in stacks/:\n")
        for p in list_stacks():
            print(f"  - {p.name}")
        print("\nBuilt-in profiles (edit compose.*.yaml):")
        print("  rocketchat  →  docker compose --profile rocketchat up -d")
        print("  immich      →  see stacks/immich.compose.yaml.example")
        print("\nTo add a custom stack:")
        print("  1. Copy stacks/example-app.compose.yaml → compose.stacks/myapp.compose.yaml")
        print("  2. Replace __DOMAIN__ placeholders")
        print("  3. Run:")
        print("     docker compose -f compose.yaml -f compose.stacks/myapp.compose.yaml up -d")
        if ENABLED_FILE.exists():
            print("\nPreviously enabled:", ENABLED_FILE.read_text())
        return

    arg = sys.argv[1]
    if arg == "rocketchat":
        print("Rocket.Chat is already in compose.rocketchat.yaml.")
        print("Start with:")
        print("  docker compose --profile rocketchat up -d")
        return

    src = Path(arg)
    if not src.is_absolute():
        src = REPO_ROOT / arg
    if not src.exists():
        candidate = STACKS_SRC / arg
        if candidate.exists():
            src = candidate
        else:
            sys.exit(f"Stack file not found: {arg}")

    STACKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = STACKS_DIR / src.name.replace(".example", "")
    shutil.copy2(src, dest)

    lines = []
    if ENABLED_FILE.exists():
        lines = [ln.strip() for ln in ENABLED_FILE.read_text().splitlines() if ln.strip()]
    rel = f"compose.stacks/{dest.name}"
    if rel not in lines:
        lines.append(rel)
    ENABLED_FILE.write_text("\n".join(lines) + "\n")

    compose_cmd = "docker compose -f compose.yaml " + " ".join(
        f"-f {line}" for line in lines
    )
    print(f"Copied to {dest}")
    print(f"Recorded in {ENABLED_FILE}")
    print("\nDeploy with:")
    print(f"  {compose_cmd} up -d")


if __name__ == "__main__":
    main()
