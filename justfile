build:
    cargo build --release

start: build
    ./start.sh
stop:
    ./stop.sh
ps:
    pgrep -a td-sensor-logge
flush:
    ./flush.sh
plot:
    cd sensor-plotter && uv run python main.py && uv run fft_.py
plot-from from:
    cd sensor-plotter && uv run python main.py --from {{from}} && uv run python fft_.py --from {{from}}
plot-to to:
    cd sensor-plotter && uv run python main.py --to {{to}} && uv run python fft_.py --to {{to}}
plot-range from to:
    cd sensor-plotter && uv run python main.py --from {{from}} --to {{to}} && uv run python fft_.py --from {{from}} --to {{to}}
