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

# Browser wrapper (nohup + redirect so subprocess.run doesn't block)
RUN printf '#!/bin/bash\nnohup firefox-esr --no-remote "$@" >/dev/null 2>&1 &\ndisown\nsleep 1\necho "Browser launched"\n' \
    > /usr/local/bin/browser && chmod +x /usr/local/bin/browser

# Suppress Firefox first-run dialogs and password manager
RUN mkdir -p /root/.mozilla/firefox && \
    printf '[General]\nStartWithLastProfile=1\n' > /root/.mozilla/firefox/profiles.ini && \
    PROFILE_DIR=/root/.mozilla/firefox/default && mkdir -p "$PROFILE_DIR" && \
    printf 'user_pref("browser.startup.homepage_override.mstone", "ignore");\n\
user_pref("browser.shell.checkDefaultBrowser", false);\n\
user_pref("signon.rememberSignons", false);\n\
user_pref("signon.autofillForms", false);\n\
user_pref("signon.management.page.breach-alerts.enabled", false);\n\
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);\n\
user_pref("datareporting.policy.dataSubmissionEnabled", false);\n\
user_pref("browser.aboutConfig.showWarning", false);\n\
user_pref("browser.newtabpage.enabled", false);\n\
user_pref("browser.startup.homepage", "about:blank");\n\
user_pref("security.sandbox.warn_unprivileged_namespaces", false);\n\
user_pref("browser.aboutwelcome.enabled", false);\n\
user_pref("browser.messaging-system.whatsNewPanel.enabled", false);\n' \
    > "$PROFILE_DIR/user.js" && \
    printf '\n[Profile0]\nName=default\nIsRelative=1\nPath=default\nDefault=1\n' \
    >> /root/.mozilla/firefox/profiles.ini

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
