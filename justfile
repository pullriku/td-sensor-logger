start:
    ./start.sh
stop:
    sudo ./stop.sh
flush:
    just stop && just start
