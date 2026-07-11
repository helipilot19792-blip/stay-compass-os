#!/bin/bash
set -e

echo "Installing required packages..."

sudo apt update

sudo apt install -y \
    git \
    curl \
    wget \
    chromium \
    network-manager \
    openssh-server \
    fbi \
    xserver-xorg \
    xinit \
    openbox \
    unclutter \
    xdotool

echo "Package installation complete."
