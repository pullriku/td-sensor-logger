#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$script_dir/../.." && pwd)"

export PATH="$HOME/.cargo/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

: "${MODEL_NAME:=tdsn7200}"
: "${INTERVAL:=60}"
: "${FLUSH_COUNT:=10000}"
: "${BINARY:=$repo_dir/target/release/td-sensor-logger}"

if [[ ! -x "$BINARY" ]]; then
  echo "td-sensor-logger binary not found or not executable: $BINARY" >&2
  echo "run: cargo build --release" >&2
  exit 1
fi

cd "$repo_dir"
exec "$BINARY" "$MODEL_NAME" --interval "$INTERVAL" --flush-count "$FLUSH_COUNT"
