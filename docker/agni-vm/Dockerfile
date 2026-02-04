FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:1

# System dependencies + PPAs (deadsnakes for python3.11, mozillateam for firefox-esr)
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    ca-certificates \
    gnupg \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && add-apt-repository -y ppa:mozillateam/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
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
    firefox-esr \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 (for JS app support)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set python3.11 as default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Browser wrapper
RUN printf '#!/bin/bash\nexec firefox-esr --no-remote "$@"\n' \
    > /usr/local/bin/browser && chmod +x /usr/local/bin/browser

# Install Python dependencies (cached unless pyproject.toml/poetry.lock change)
WORKDIR /app
COPY pyproject.toml poetry.lock* README.md ./
RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --without dev --no-root

# Copy source and install the project package (fast, deps already cached)
COPY src/ ./src/
RUN poetry install --no-interaction --without dev

COPY docker/agni-vm/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
