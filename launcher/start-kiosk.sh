#!/bin/bash

set -e

export DISPLAY=:0

xset s off
xset -dpms
xset s noblank

unclutter -idle 0.1 -root &

openbox-session &

sleep 2

# Launch the Stay Compass PWA.
# This will eventually be replaced by the Stay Compass Device Service.

exec chromium \
  --kiosk \
  --app=https://stayinniagara.com/compass/ \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000