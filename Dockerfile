FROM node:22-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements.txt
RUN python3 -m venv /opt/venv \
    && pip install --upgrade pip \
    && pip install -r backend/requirements.txt

COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci

COPY backend backend
COPY frontend frontend
COPY scripts scripts

RUN cd frontend && npm run build \
    && npm prune --omit=dev \
    && chmod +x /app/scripts/render-start.sh

# The app runs as the unprivileged `node` user (uid 1000, built into the node base
# image), but the container starts as root: Render mounts the /var/data disk
# root-owned, so render-start.sh chowns it at boot and then drops to `node` via
# setpriv before launching any app process. The chowns below cover paths baked
# into the image: /var/data for local runs without a mount, /app/backend (SQLite +
# default .cache when env vars are absent), /app/frontend/.next (Next.js runtime
# cache). Both ports are >1024, so the app processes never need root.
RUN mkdir -p /var/data \
    && chown node:node /var/data /app/backend \
    && chown -R node:node /app/frontend/.next

ENV NODE_ENV=production

EXPOSE 10000

CMD ["/app/scripts/render-start.sh"]
