# Base: official Python 3.12 slim (Debian Bookworm)
FROM python:3.12-slim-bookworm

# System packages needed by PlatformIO + esptool + serial
# libusb-1.0-0 is used by esptool / serial tooling.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    unzip \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    usbutils \
    libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install PlatformIO Core
RUN pip install --no-cache-dir platformio

# Pre-warm the esp32dev_wireless toolchain so the first build is faster.
# This runs inside the container at image-build time; the .pio volume mount in
# devcontainer.json caches the result across rebuilds.
COPY platformio.ini /tmp/pio-prefetch/platformio.ini
COPY sdkconfig.defaults /tmp/pio-prefetch/sdkconfig.defaults
RUN cd /tmp/pio-prefetch && \
    mkdir -p src && \
    printf '#include <Arduino.h>\nvoid setup(){}\nvoid loop(){}\n' > src/main.cpp && \
    pio pkg install -e esp32dev_wireless || true && \
    rm -rf /tmp/pio-prefetch

WORKDIR /workspace
