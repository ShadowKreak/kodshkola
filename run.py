"""Запуск приложения: python run.py  →  http://127.0.0.1:5000"""
import os

from edu import create_app

app = create_app()

if __name__ == "__main__":
    print("\n  KodShkola запущена: http://127.0.0.1:5000")
    print("  Код приглашения для регистрации администратора:", app.config["ADMIN_INVITE_CODE"], "\n")
    app.run(host=os.environ.get("EDU_HOST", "127.0.0.1"), port=int(os.environ.get("EDU_PORT", "5000")),
            debug=os.environ.get("EDU_DEBUG") == "1")
