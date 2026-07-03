#!/bin/bash
# elo-watchdog.sh
# Verifica se o nó Elo está vivo a cada 5 minutos

ELO_NAME="${ELO_NAME:-elo-node}"
ELO_PORT="${ELO_PORT:-7878}"
ELO_PEERS="${ELO_PEERS:-}"
ELO_DATA_DIR="${ELO_DATA_DIR:-$HOME/.elo}"
PID_FILE="$ELO_DATA_DIR/elo-node.pid"

mkdir -p "$ELO_DATA_DIR"

# Lock atômico pra evitar múltiplas instâncias
exec 200>"$ELO_DATA_DIR/elo-watchdog.lock"
flock -n 200 || { echo "ELO_WATCHDOG_LOCKED: another instance running"; exit 0; }

if [ -f "$PID_FILE" ]; then
    if ! kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "ELO_DEAD: PID $(cat $PID_FILE) — restarting"
        nohup python3 -m elo serve \
            --name "$ELO_NAME" \
            --port "$ELO_PORT" \
            --peers "$ELO_PEERS" \
            > "$ELO_DATA_DIR/elo-node.log" 2>&1 &
        echo $! > "$PID_FILE"
        echo "ELO_RESTARTED: PID $!"
    fi
else
    echo "ELO_NO_PID_FILE: starting fresh"
    nohup python3 -m elo serve \
        --name "$ELO_NAME" \
        --port "$ELO_PORT" \
        --peers "$ELO_PEERS" \
        > "$ELO_DATA_DIR/elo-node.log" 2>&1 &
    echo $! > "$PID_FILE"
    echo "ELO_STARTED: PID $!"
fi
