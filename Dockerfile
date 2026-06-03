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

ENV NODE_ENV=production

EXPOSE 10000

CMD ["/app/scripts/render-start.sh"]
