#!/bin/sh
# Called by the webtiles server with the player name before each game.
PLAYERNAME=$1
mkdir -p /data/rcs /data/rcs/running "/data/rcs/ttyrecs/$PLAYERNAME" /data/saves
if [ ! -f "/data/rcs/$PLAYERNAME.rc" ]; then
    cp /crawl/settings/ladder-init.txt "/data/rcs/$PLAYERNAME.rc"
fi
