# CampusEvent 云服务器部署说明

## 0. 前置条件

| 项 | 要求 |
| --- | --- |
| 服务器 | 1 核 1G 以上，Ubuntu 22.04 / Debian 12（CentOS 亦可，需改包管理器） |
| 网络 | 有公网 IP；安全组/防火墙放行 **80**（如需 https 再放行 443） |
| 软件 | python3、python3-venv、nginx、git |

## 1. 一键部署

```bash
sudo apt update && sudo apt install -y python3-venv nginx git
git clone <仓库地址> /opt/campus-event
cd /opt/campus-event
sudo bash deploy/deploy.sh
```

脚本做的事：
1. 建 `.venv` 并安装 `requirements.txt`；
2. 首次运行用 `python -m app.seed` 初始化 SQLite；
3. 写入并启动 `campus-event.service`（waitress，监听 `127.0.0.1:8000`）；
4. 写入 nginx 反代配置（`/static/` 直出静态文件），reload。

访问：`http://<公网IP>/`

## 2. 手工部署（逐步可控，便于答辩说明）

```bash
cd /opt/campus-event
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m app.seed                # 初始化演示数据
waitress-serve --listen=127.0.0.1:8000 --threads=8 run:app &   # 前台/后台均可
```

nginx 配置见 `deploy/nginx.conf` 模板；systemd 单元见 `deploy/campus-event.service`。

## 3. 环境变量

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `CAMPUS_ADMIN_CODE` | 管理员演示口令 | `admin123` |
| `CAMPUS_SECRET_KEY` | Flask session 密钥（生产务必改） | 内置演示值 |
| `CAMPUS_DB` | SQLite 文件路径 | `instance/campus_event.db` |
| `CAMPUS_OUTBOX` | 邮件渠道落盘目录 | `outbox` |

> 生产环境请通过 systemd 的 `Environment=` 或 `EnvironmentFile=` 注入，**不要**提交到仓库。

## 4. 运维

```bash
sudo systemctl status campus-event
sudo journalctl -u campus-event -f
sudo systemctl restart campus-event

# 备份数据库（SQLite 单文件）
cp /opt/campus-event/instance/campus_event.db ~/backup-$(date +%F).db

# 重置演示数据
cd /opt/campus-event && . .venv/bin/activate && python -m app.seed --reset
```

## 5. 验收自检清单

```bash
curl -I http://127.0.0.1:8000/            # 200
curl -s  http://<公网IP>/ | head -20       # 页面标题包含 CampusEvent
ls /opt/campus-event/outbox/*.eml          # 报名后应出现邮件文件
```
