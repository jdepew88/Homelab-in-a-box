#!/usr/bin/env python3
"""Deprecated — use setup-bootstrap.py then setup-authelia.py."""
import sys

print(
    "This script was split into two phases:\n"
    "  1. python3 scripts/setup-bootstrap.py   # Tunnel + Traefik + Portainer\n"
    "  2. python3 scripts/setup-authelia.py    # Authelia 1FA\n",
    file=sys.stderr,
)
sys.exit(1)
