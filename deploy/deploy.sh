#!/usr/bin/env bash
# CampusEvent 一键部署脚本（Ubuntu 22.04 / Debian 12）
# 用法（在项目根目录执行）：sudo bash deploy/deploy.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${APP_USER:-$(id -un)}"
APP_PORT="${APP_PORT:-8000}"
ADMIN_CODE="${CAMPUS_ADMIN_CODE:-admin123}"

echo "[1/5] 检查系统依赖"
command -v python3 >/dev/null || { echo "缺少 python3"; exit 1; }
command -v nginx >/dev/null || { echo "请先安装 nginx：apt install -y nginx"; exit 1; }

echo "[2/5] 创建虚拟环境并安装依赖"
cd "$APP_DIR"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "[3/5] 初始化数据库（已有数据则跳过）"
if [ ! -f "$APP_DIR/instance/campus_event.db" ]; then
  python -m app.seed
else
  echo "  已存在数据库，跳过初始化（如需重置：python -m app.seed --reset）"
fi
mkdir -p "$APP_DIR/outbox" "$APP_DIR/logs"

echo "[4/5] 安装 systemd 服务"
sudo tee /etc/systemd/system/campus-event.service >/dev/null <<UNIT
[Unit]
Description=CampusEvent 校园活动报名与管理系统
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=CAMPUS_ADMIN_CODE=$ADMIN_CODE
ExecStart=$APP_DIR/.venv/bin/waitress-serve --listen=127.0.0.1:$APP_PORT --threads=8 run:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now campus-event

echo "[5/5] 配置 nginx 反向代理"
sudo tee /etc/nginx/sites-available/campus-event >/dev/null <<CONF
server {
    listen 80 default_server;
    server_name _;

    access_log /var/log/nginx/campus-event.access.log;
    error_log  /var/log/nginx/campus-event.error.log;

    location /static/ {
        alias $APP_DIR/app/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:$APP_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
CONF

sudo ln -sf /etc/nginx/sites-available/campus-event /etc/nginx/sites-enabled/campus-event
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

IP="$(hostname -I | awk '{print $1}')"
echo
echo "部署完成：http://$IP/"
echo "  管理员口令：$ADMIN_CODE（可用环境变量 CAMPUS_ADMIN_CODE 覆盖后重跑本脚本）"
echo "  服务状态：sudo systemctl status campus-event"
echo "  运行日志：sudo journalctl -u campus-event -f"
