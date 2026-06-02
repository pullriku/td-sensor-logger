#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$HOME/.config/systemd/user"
ln -sf "$repo_dir/systemd/user/td-sensor-logger.service" "$HOME/.config/systemd/user/td-sensor-logger.service"

if [[ ! -f "$repo_dir/systemd/user/td-sensor-logger.env" ]]; then
  cp "$repo_dir/systemd/user/td-sensor-logger.env.example" "$repo_dir/systemd/user/td-sensor-logger.env"
fi

systemctl --user daemon-reload
systemctl --user enable --now td-sensor-logger.service
