#!/bin/sh
# Waits until the API and the dashboard answer, then prints where to open the app.
api="$1"
web="$2"
i=0
until curl -sf "$api/api/health" >/dev/null 2>&1 && curl -sf -o /dev/null "$web/"; do
  i=$((i + 1))
  if [ "$i" -gt 120 ]; then
    echo "Not ready after 120 s: check the api, worker and web logs above" >&2
    exit 1
  fi
  sleep 1
done
mode=$(curl -sf "$api/api/health" | sed -n 's/.*"mode":"\([a-z]*\)".*/\1/p')
echo "Ready: open $web (model mode: $mode)"
