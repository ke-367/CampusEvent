"""开发/演示入口：python run.py  （生产部署见 deploy/README）"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
