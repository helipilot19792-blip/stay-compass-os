#!/bin/bash

set -e

export DISPLAY=:0

xset s off
xset -dpms
xset s noblank

unclutter -idle 0.1 -root &

openbox-session &

sleep 2

exec python3 /opt/stay-compass/device/stay-compass-device.py