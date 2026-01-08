import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
import traceback

try:
    # 1. 读取 Excel
    excel_path = r"D:\work\生产运行支持系统(输电).xlsx"
    df = pd.read_excel(excel_path)

    print("✅ Excel 读取成功")
    print(df.head())
    print("📊 Excel 行数:", len(df))

    if df.empty:
        raise ValueError("Excel 文件为空，没有可导入的数据")

    # 2. 连接 MySQL
    # engine = create_engine(
    #     "mysql+pymysql://root:password@localhost:3306/school?charset=utf8mb4"
    # )
    engine = create_engine(
        "mysql+pymysql://root:123456@localhost:3306/school?charset=utf8mb4"
    )

    # 3. 写入 MySQL
    df.to_sql(
        name="students",
        con=engine,
        if_exists="append",
        index=False,
        method="multi"  # 批量插入，性能更好
    )

    print(f"🎉 成功写入 MySQL：{len(df)} 条数据")

except FileNotFoundError:
    print("❌ Excel 文件未找到，请检查路径是否正确")

except ValueError as e:
    print(f"❌ 数据校验失败：{e}")

except SQLAlchemyError as e:
    print("❌ 数据库写入失败")
    print("错误信息：", str(e))

except Exception as e:
    print("❌ 未知错误")
    print("错误信息：", str(e))
    print(traceback.format_exc())
