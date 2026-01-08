import pandas as pd
df = pd.read_excel(r"D:\work\生产运行支持系统(输电).xlsx", engine='openpyxl')

print(df.columns.tolist())
