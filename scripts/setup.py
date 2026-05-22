#!/usr/bin/env python3
"""Deprecated — use setup-bootstrap.py then setup-authelia.py."""
import sys

print(
    "Homelab-in-a-box uses two setup scripts:\n"
    "  1. python3 scripts/setup-bootstrap.py\n"
    "  2. python3 scripts/setup-authelia.py\n",
    file=sys.stderr,
)
sys.exit(1)
