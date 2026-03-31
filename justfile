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
