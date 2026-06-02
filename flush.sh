#!/usr/bin/env bash
set -euo pipefail

systemctl --user reload td-sensor-logger.service
