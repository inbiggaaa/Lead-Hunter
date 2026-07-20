# Digests pin the exact upstream image content (Phase 5 supply-chain).
# Refresh via: docker pull <image> && docker inspect --format='{{index .RepoDigests 0}}' <image>
FROM python@sha256:db3ff2e1800a8581e2c48a27c3995339d47bdf046da21c7627accd3d51053a93

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /home/app app \
    && mkdir -p /app/sessions \
    && chown -R app:app /app

# Locked runtime dependencies (refresh: ./scripts/refresh_requirements_lock.sh)
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock \
    && chown -R app:app /usr/local/lib/python3.11/site-packages /usr/local/bin

# App code
COPY --chown=app:app . .

USER app

# Each service overrides CMD
CMD ["python", "-m", "app.main"]
