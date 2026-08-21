#!/bin/sh
set -eu

uvicorn app.main:app --host 127.0.0.1 --port 8698 &
backend_pid=$!
nginx_pid=

cleanup() {
    [ -z "$nginx_pid" ] || kill "$nginx_pid" 2>/dev/null || true
    [ -z "$backend_pid" ] || kill "$backend_pid" 2>/dev/null || true
    [ -z "$nginx_pid" ] || wait "$nginx_pid" 2>/dev/null || true
    [ -z "$backend_pid" ] || wait "$backend_pid" 2>/dev/null || true
}

trap cleanup INT TERM EXIT

nginx -g 'daemon off;' &
nginx_pid=$!

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
    sleep 1
done

if ! kill -0 "$backend_pid" 2>/dev/null; then
    wait "$backend_pid"
else
    wait "$nginx_pid"
fi
