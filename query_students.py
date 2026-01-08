import os
import sys
import json
import re
from typing import List, Dict
from mysql.connector import connect, Error

ALLOWED_FIELDS = {
    "student_id",   # 主键
    "name",         #必填字段
    "gender",       #必填字段
    "age",          #选填字段
    "class_id",
    "enroll_date",
    "系统名称",
    "功能模块",
    "图片",
    "字段分组",
    "字段名",
    "对接厂商",
    "数据中心",
}


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


def chatglm_generate_sql(prompt: str) -> str:
    api_key = os.environ.get("ZHIPUAI_API_KEY") or os.environ.get("CHATGLM_API_KEY")
    if not api_key:
        raise RuntimeError("缺少ChatGLM API密钥: ZHIPUAI_API_KEY 或 CHATGLM_API_KEY")
    model = os.environ.get("CHATGLM_MODEL", "glm-4")
    try:
        from zhipuai import ZhipuAI
    except Exception as e:
        raise RuntimeError("缺少zhipuai依赖") from e
    client = ZhipuAI(api_key=api_key)
    system_prompt = (
        "你是一个数据库助理,只返回针对MySQL students表的SELECT语句。"
        "只使用以下字段:student_id, name, gender, age, class_id, enroll_date, 系统名称, 功能模块, 图片, 字段分组, 字段名, 对接厂商, 数据中心。"
        "字段名保持原样，中文字段名需用反引号。如：`系统名称`。不要返回除SQL之外的任何文字。"
        "表名必须是students。不得使用*。只输出一行SQL。"
    )
    schema_hint = (
        "+-------------+-----------------+------+-----+---------+----------------+\n"
        "| Field       | Type            | Null | Key | Default | Extra          |\n"
        "+-------------+-----------------+------+-----+---------+----------------+\n"
        "| student_id  | int             | NO   | PRI | NULL    | auto_increment |\n"
        "| name        | varchar(50)     | NO   |     | NULL    |                |\n"
        "| gender      | enum('男','女') | NO   |     | NULL    |                |\n"
        "| age         | int             | YES  |     | NULL    |                |\n"
        "| class_id    | int             | YES  |     | NULL    |                |\n"
        "| enroll_date | date            | YES  |     | NULL    |                |\n"
        "| 系统名称    | varchar(255)    | YES  |     | NULL    |                |\n"
        "| 功能模块    | varchar(255)    | YES  |     | NULL    |                |\n"
        "| 图片        | varchar(255)    | YES  |     | NULL    |                |\n"
        "| 字段分组    | varchar(255)    | YES  |     | NULL    |                |\n"
        "| 字段名      | varchar(255)    | YES  |     | NULL    |                |\n"
        "| 对接厂商    | varchar(255)    | YES  |     | NULL    |                |\n"
        "| 数据中心    | varchar(255)    | YES  |     | NULL    |                |\n"
        "+-------------+-----------------+------+-----+---------+----------------+"
    )
    examples = [
        {"role": "user", "content": "查询所有女生的姓名和年龄"},
        {"role": "assistant", "content": "SELECT `name`, `age` FROM students WHERE `gender`='女';"},
        {"role": "user", "content": "显示班级ID为3的学生信息"},
        {"role": "assistant", "content": "SELECT `student_id`, `name`, `gender`, `age`, `class_id`, `enroll_date` FROM students WHERE `class_id`=3;"},
        {"role": "user", "content": "获取系统名称为‘教育系统’的学生姓名和入学日期"},
        {"role": "assistant", "content": "SELECT `name`, `enroll_date` FROM students WHERE `系统名称`='教育系统';"},
    ]
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": schema_hint},
        *examples,
        {"role": "user", "content": prompt},
    ]
    resp = client.chat.completions.create(model=model, messages=messages)
    text = ""
    try:
        text = resp.choices[0].message.content
    except Exception:
        text = json.dumps(resp, ensure_ascii=False)
    sql = text.strip()
    if sql.startswith("```"):
        sql = re.sub(r"^```[a-zA-Z]*\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
    sql = sql.strip()
    parts = sql.split("\n")
    if parts:
        if parts[0].lower().startswith("select"):
            sql = parts[0].strip()
        else:
            for p in parts:
                if p.strip().lower().startswith("select"):
                    sql = p.strip()
                    break
    sql = normalize_sql(sql)
    return sql


def normalize_sql(sql: str) -> str:
    fields_cn = ["系统名称", "功能模块", "图片", "字段分组", "字段名", "对接厂商", "数据中心"]
    for f in fields_cn:
        sql = re.sub(rf"(?<!`)({re.escape(f)})(?!`)", r"`\1`", sql)
    sql = re.sub(r"\s+;", ";", sql).strip()
    return sql


def ensure_sql_valid(sql: str) -> None:
    s = sql.strip().lower()
    if not s.startswith("select"):
        raise ValueError("仅允许SELECT语句")
    banned = ["insert", "update", "delete", "drop", "alter", "truncate"]
    for b in banned:
        if re.search(r"\b" + re.escape(b) + r"\b", s):
            raise ValueError("仅允许SELECT语句")
    if re.search(r"\bselect\s*\*", s):
        raise ValueError("不允许*")
    if " from " not in s:
        raise ValueError("SQL缺少FROM")
    if not re.search(r"\bfrom\s+`?students`?\b", s, flags=re.IGNORECASE):
        raise ValueError("必须查询students表")
    bt = re.findall(r"`([^`]+)`", sql)
    for name in bt:
        if name.lower() == "students":
            continue
        if name not in ALLOWED_FIELDS:
            raise ValueError("存在未允许的字段: " + name)
    tokens = re.findall(r"\b[a-zA-Z_][\w]*\b", sql)
    for t in tokens:
        if t.lower() in {"select", "from", "where", "and", "or", "in", "like", "between", "as", "order", "by", "asc", "desc", "limit", "group", "having", "not"}:
            continue
        if t.lower() in {"students"}:
            continue
        if t in ALLOWED_FIELDS:
            continue
        if re.match(r"^\d+$", t):
            continue
        raise ValueError("存在未允许的标识符: " + t)


def execute_sql(sql: str) -> List[Dict]:
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
        raise RuntimeError("缺少环境变量: " + ", ".join(missing))
    conn = connect(host=host, port=port, user=user, password=password, database=database, connection_timeout=5)
    cur = conn.cursor(dictionary=True)
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def run_query(nl_query: str) -> Dict:
    load_env_file()
    sql = chatglm_generate_sql(nl_query)
    ensure_sql_valid(sql)
    rows = execute_sql(sql)
    return {"sql": sql, "rows": rows}


def main():
    if len(sys.argv) < 2:
        print("请输入查询文本")
        sys.exit(2)
    nl_query = sys.argv[1]
    try:
        result = run_query(nl_query)
        print(result["sql"])
        print(json.dumps(result["rows"], ensure_ascii=False, default=str))
        sys.exit(0)
    except ValueError:
        print("-- 无法生成 SQL")
        sys.exit(1)
    except Exception as e:
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
