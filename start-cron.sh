#!/bin/sh
set -e

#1. 用envsubst替換模板中的 ${VAR}
envsubst < /etc/cron.d/app-cron.tmpl > /etc/cron.d/app-cron

#2. 修正權限並安裝到root的crontab
chmod 0644 /etc/cron.d/app-cron
crontab /etc/cron.d/app-cron

echo "[INFO] Installed crontab ==="
cat /etc/cron.d/app-cron
echo "============================"

#3. 前景模式下跑cron
exec cron -f