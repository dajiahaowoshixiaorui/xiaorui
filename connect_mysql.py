import os
import sys
from mysql.connector import connect, Error


def load_env_file(path=".env"):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def main():
    load_env_file()
    host = os.environ.get("MYSQL_HOST", "localhost")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "123456")
    database = os.environ.get("MYSQL_DATABASE", "school")

    missing = []
    for k, v in [("MYSQL_HOST", host), ("MYSQL_USER", user), ("MYSQL_PASSWORD", password)]:
        if not v:
            missing.append(k)
    if missing:
        print("缺少环境变量: " + ", ".join(missing))
        print("请在 .env 或系统环境中设置所需变量")
        sys.exit(2)

    try:
        conn = connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connection_timeout=5,
        )
        ver = conn.get_server_info()
        print("连接成功")
        print("服务器版本: " + str(ver))
        cur = conn.cursor()
        cur.execute("SELECT VERSION()")
        row = cur.fetchone()
        if row:
            print("SELECT VERSION(): " + str(row[0]))
        cur.close()
        conn.close()
        sys.exit(0)
    except Error as e:
        print("连接失败: " + str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
