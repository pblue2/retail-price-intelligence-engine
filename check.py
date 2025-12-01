# 文件名: print_db.py

import sqlite3
import os

# --- 配置 ---
# 数据库文件的路径
DB_PATH = "/mnt/scraper/data/sportinglife.db"
# 您在配置文件中定义的表名
TABLE_NAME = "sportinglife_products"

def print_product_data():
    """
    连接到SQLite数据库，查询商品信息并打印到控制台。
    """
    # 检查数据库文件是否存在
    if not os.path.exists(DB_PATH):
        print(f"错误：找不到数据库文件，请确认路径是否正确: {DB_PATH}")
        return

    conn = None  # 初始化连接变量
    try:
        # 连接到数据库
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # SQL查询语句，选择我们需要的列，并按商品名称排序
        query = f"SELECT name, list_price, sale_price, url FROM {TABLE_NAME} ORDER BY name;"
        
        print(f"--- 正在从数据库 '{DB_PATH}' 的 '{TABLE_NAME}' 表中读取数据 ---\n")
        
        cursor.execute(query)
        rows = cursor.fetchall()

        # 检查是否查询到了数据
        if not rows:
            print("数据库中没有找到任何商品。请先运行一次爬虫。")
            return

        # 遍历所有查询结果并打印
        for i, row in enumerate(rows):
            name, list_price, sale_price, url = row
            
            print(f"--- 商品 #{i + 1} ---")
            print(f"商品名: {name}")
            print(f"原  价: ${list_price:.2f}") # 格式化为两位小数的货币
            
            # 如果原价和现价不同，就显示折扣信息
            if list_price > sale_price:
                discount = round((1 - sale_price / list_price) * 100)
                print(f"现  价: ${sale_price:.2f} ({discount}% OFF)")
            else:
                 print(f"现  价: ${sale_price:.2f}")

            print(f"链  接: {url}")
            print("-" * 20) # 分隔符

    except sqlite3.Error as e:
        print(f"数据库查询时发生错误: {e}")
    finally:
        # 无论成功与否，最后都要确保关闭数据库连接
        if conn:
            conn.close()
            # print("\n--- 数据库连接已关闭 ---")

if __name__ == "__main__":
    print_product_data()
