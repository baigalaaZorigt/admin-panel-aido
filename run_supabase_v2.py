"""supabase_v2.sql-ийг .env-ийн SUPABASE_DB_URL руу нэг transaction-ээр ажиллуулна.

⚠️ Хуучин бүх хүснэгтийг өгөгдөлтэй нь устгаад шинээр үүсгэнэ.
Ажиллуулах: .venv/bin/python run_supabase_v2.py
"""
import os
from urllib.parse import unquote, urlparse

import psycopg
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = ["users", "bookings", "tours", "staff", "content_drafts", "knowledge_base",
          "chat_messages", "handoffs", "fb_page_stats", "fb_post_stats"]

env = dotenv_values(os.path.join(HERE, ".env"))
db_url = (env.get("SUPABASE_DB_URL") or "").strip()
admin_password = (env.get("ADMIN_PASSWORD") or "").strip()
if not db_url or not admin_password:
    raise SystemExit(".env-д SUPABASE_DB_URL болон ADMIN_PASSWORD хоёулаа байх ёстой.")

sql = open(os.path.join(HERE, "supabase_v2.sql"), encoding="utf-8").read()
# Нууц үгийг файлд бичихгүй, зөвхөн ажиллуулах үед орлуулна
sql = sql.replace("'ЭНД_ТҮР_НУУЦ_ҮГ'", "'" + admin_password.replace("'", "''") + "'")

if input("Бүх хүснэгт устаж шинээр үүснэ. Үргэлжлүүлэх үү? (тийм/үгүй): ").strip().lower() != "тийм":
    raise SystemExit("Цуцаллаа. Юу ч өөрчлөгдсөнгүй.")

# Нууц үгэнд @ г.м. тэмдэгт байж болох тул хаягийг хэсэг болгон задалж дамжуулна
url = urlparse(db_url)
conn_args = {"host": url.hostname, "port": url.port or 5432, "user": unquote(url.username or ""),
             "password": unquote(url.password or ""), "dbname": url.path.lstrip("/") or "postgres",
             "connect_timeout": 15}

try:
    with psycopg.connect(**conn_args) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("notify pgrst, 'reload schema'")  # REST API шинэ хүснэгтүүдийг танина
        conn.commit()
        print("АМЖИЛТТАЙ ✓  Хүснэгт бүрийн мөрийн тоо:")
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(f"select count(*) from public.{table}")
                print(f"  {table:15} {cur.fetchone()[0]}")
except psycopg.Error as exc:
    # Нэг transaction учраас алдаа гарвал сан огт өөрчлөгдөхгүй
    print("АЛДАА (сан өөрчлөгдөөгүй):", str(exc).replace(conn_args["password"], "***")[:400])
