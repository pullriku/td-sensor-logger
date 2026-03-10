nohup ${CARGO_TARGET_DIR:-target}/release/td-sensor-logger > logger.log 2>&1 &
echo $! > logger.pid
