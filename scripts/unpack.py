#!/usr/bin/env python3
"""Unpack a release zip into ~/homelab-in-a-box (or custom path)."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Unpack Homelab-in-a-box zip on the server")
    parser.add_argument("zipfile", type=Path, help="Path to homelab-in-a-box.zip")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path.home() / "homelab-in-a-box",
        help="Target directory",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zipfile) as zf:
        zf.extractall(args.output)
    print(f"Extracted to {args.output}")
    print("Next: python3 scripts/setup-bootstrap.py")


if __name__ == "__main__":
    main()
