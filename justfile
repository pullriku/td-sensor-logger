start:
    ./start.sh
stop:
    ./stop.sh
ps:
    pgrep -a td-sensor-logge
flush:
    ./flush.sh
plot:
    cd sensor-plotter && uv run python main.py
