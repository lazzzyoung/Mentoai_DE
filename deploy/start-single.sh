#!/bin/sh
caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
CADDY_PID=$!
/usr/bin/mentoai serve --host 127.0.0.1 --port 8000 &
APP_PID=$!
trap 'kill -TERM $CADDY_PID $APP_PID 2>/dev/null' INT TERM
wait
