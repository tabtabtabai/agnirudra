FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    openbox \
    ffmpeg \
    xdotool \
    scrot \
    git \
    curl \
    jq \
    wget \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install a real browser (the apt chromium-browser on 22.04 is a snap stub that doesn't work in Docker)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "amd64" ]; then \
        wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
        apt-get update && apt-get install -y /tmp/chrome.deb && \
        rm /tmp/chrome.deb && rm -rf /var/lib/apt/lists/*; \
    else \
        apt-get update && apt-get install -y --no-install-recommends chromium-browser && \
        rm -rf /var/lib/apt/lists/*; \
    fi

# Node.js 20 (for JS app support)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set python3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Browser wrapper with Docker-safe flags
# Browser wrapper: use whichever browser is installed
RUN CHROME=$(command -v google-chrome-stable || command -v chromium-browser || echo "echo 'No browser found' && exit 1") && \
    printf '#!/bin/bash\nexec %s --no-sandbox --disable-gpu --disable-dev-shm-usage "$@"\n' "$CHROME" \
    > /usr/local/bin/browser && chmod +x /usr/local/bin/browser

# Install agnirudra
WORKDIR /app
COPY pyproject.toml poetry.lock* README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --without dev

COPY docker/agni-vm/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
