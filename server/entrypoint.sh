#!/bin/sh
set -e
mkdir -p /data/rcs /data/saves /data/webserver
cd /crawl
exec python3 webserver/server.py "$@"
