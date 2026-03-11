#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f logger.pid ]]; then
  echo "logger.pid not found" >&2
  exit 1
fi

pid="$(cat logger.pid)"
if ! kill -0 "$pid" 2>/dev/null; then
  echo "process $pid is not running" >&2
  exit 1
fi

kill -USR1 "$pid"
