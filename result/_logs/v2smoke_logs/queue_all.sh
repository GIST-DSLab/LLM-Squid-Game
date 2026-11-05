#!/bin/zsh
cd "$(dirname "$0")/../.."
./outputs/_v2smoke_logs/queue.sh main
./outputs/_v2smoke_logs/queue.sh mate
echo "=== $(date '+%H:%M:%S') ALL DONE"
