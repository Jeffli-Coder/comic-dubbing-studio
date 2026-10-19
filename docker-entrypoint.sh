#!/bin/sh
# 容器入口：以 root 启动时修正数据卷属主，再降权到 app 运行。
set -eu

DATA_DIR="${DATA_DIR:-/data}"
export DATA_DIR

if [ "$(id -u)" = "0" ]; then
    install -d -o app -g app "$DATA_DIR"

    # Linux bind mount 通常是 root 属主；named volume 会继承镜像里的 app:app。
    # 只有属主不对时才递归 chown，避免每次启动都扫描大目录。
    if [ "$(stat -c %u "$DATA_DIR" 2>/dev/null || echo 0)" != "$(id -u app)" ]; then
        chown -R app:app "$DATA_DIR" 2>/dev/null || true
    fi

    exec gosu app "$@"
fi

# 以任意非 root UID 运行（Kubernetes/OpenShift）时假定 /data 已可写
exec "$@"