# syntax=docker/dockerfile:1

FROM python:3.12-slim-bookworm

# 构建参数：国内网络可通过 --build-arg PIP_INDEX_URL=... 使用镜像源
ARG APP_UID=10001
ARG APP_GID=10001
ARG PIP_INDEX_URL=""
ARG PIP_TRUSTED_HOST=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/app \
    HOST=0.0.0.0 \
    PORT=8080 \
    DATA_DIR=/data \
    MOCK_MODE=0

# ffmpeg: 音频拼接/转码；gosu: 入口脚本降权；ca-certificates: 出站 HTTPS
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg gosu ca-certificates \
 && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid "${APP_GID}" app \
 && useradd --uid "${APP_UID}" --gid app --create-home --shell /usr/sbin/nologin app \
 && install -d -o app -g app /data

WORKDIR /app

COPY requirements.txt ./
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        PIP_INDEX_URL="$PIP_INDEX_URL" PIP_TRUSTED_HOST="$PIP_TRUSTED_HOST" \
            pip install -r requirements.txt; \
    else \
        pip install -r requirements.txt; \
    fi

COPY --chown=app:app . .
RUN chmod +x /app/docker-entrypoint.sh

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import http.client, os, sys; c = http.client.HTTPConnection('127.0.0.1', int(os.environ.get('PORT', '8080')), timeout=3); c.request('GET', '/api/health'); sys.exit(0 if c.getresponse().status == 200 else 1)"

EXPOSE 8080

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# 必须单 worker：任务注册表与每书锁都在进程内，多 worker 会导致状态错乱
CMD ["python", "server.py"]