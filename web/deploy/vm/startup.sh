#!/usr/bin/env bash
# VM startup script (metadata): Docker with the compose plugin, once; the containers restart on their own after a reboot.
set -e
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
mkdir -p /opt/arena
