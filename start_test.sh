nohup ${CARGO_TARGET_DIR:-target}/release/td-sensor-logger --interval 10 --flush-count 100000 > logger.log 2>&1 &
echo $! > logger.pid
