build:
    cargo build --release

start: build
    mkdir -p ~/.config/systemd/user
    ln -sf {{justfile_directory()}}/systemd/user/td-sensor-logger.service ~/.config/systemd/user/td-sensor-logger.service
    test -f {{justfile_directory()}}/systemd/user/td-sensor-logger.env || cp {{justfile_directory()}}/systemd/user/td-sensor-logger.env.example {{justfile_directory()}}/systemd/user/td-sensor-logger.env
    systemctl --user daemon-reload
    systemctl --user enable --now td-sensor-logger.service

stop:
    systemctl --user stop td-sensor-logger.service

flush:
    systemctl --user reload td-sensor-logger.service

status:
    systemctl --user status td-sensor-logger.service

logs:
    journalctl --user -u td-sensor-logger.service -f

plot:
    cd sensor-plotter && uv run python main.py && uv run fft_.py
plot-from from:
    cd sensor-plotter && uv run python main.py --from {{from}} && uv run python fft_.py --from {{from}}
plot-to to:
    cd sensor-plotter && uv run python main.py --to {{to}} && uv run python fft_.py --to {{to}}
plot-range from to:
    cd sensor-plotter && uv run python main.py --from {{from}} --to {{to}} && uv run python fft_.py --from {{from}} --to {{to}}
