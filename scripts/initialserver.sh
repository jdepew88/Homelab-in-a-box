#!/usr/bin/env bash
# Initial server bootstrap (same as install-server.sh):
#   sudo bash scripts/initialserver.sh
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install-server.sh" "$@"
