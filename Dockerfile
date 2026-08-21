FROM node:22-bookworm-slim AS frontend-build

WORKDIR /workspace

RUN corepack enable

COPY package.json ./package.json
COPY frontend/package.json ./frontend/package.json
RUN pnpm config set dangerouslyAllowAllBuilds true \
    && pnpm --dir frontend install --no-frozen-lockfile

COPY public ./public
COPY frontend ./frontend
RUN pnpm --dir frontend build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WOTTYGIF_FFMPEG=ffmpeg \
    WOTTYGIF_FFPROBE=ffprobe

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg nginx \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /workspace/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /app/data/results

EXPOSE 8699

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8699/api/health', timeout=3)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
