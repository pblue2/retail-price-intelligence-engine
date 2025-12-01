# 文件名: print_db.py (高级版 + Oberson 支持)

import sqlite3
import os
import sys

# --- 配置 ---
# 定义所有可查询的数据库信息（新增 oberson）
DATABASES = {
    "sportinglife": {
        "path": "/mnt/scraper/data/sportinglife.db",
        "table": "sportinglife_products",
        "name": "Sporting Life"
    },
    "sportsexperts": {
        "path": "/mnt/scraper/data/sportsexperts.db",
        "table": "sportsexperts_products",
        "name": "Sports Experts"
    },
    "momosports": {
        "path": "/mnt/scraper/data/momosports.db",
        "table": "momosports_products",
        "name": "Momo Sports"
    },
    "oberson": {  # 新增站点
        "path": "/mnt/scraper/data/oberson.db",
        "table": "oberson_products",
        "name": "Oberson"
    }
}

def print_product_data(db_path, table_name, site_name, discount_threshold=0):
    """
    连接到指定的SQLite数据库，查询并打印符合折扣条件的商品信息。
    """
    if not os.path.exists(db_path):
        print(f"\n错误：在路径 '{db_path}' 找不到 '{site_name}' 的数据库文件。")
        print("请确认对应的爬虫是否已成功运行过。")
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = f"SELECT name, list_price, sale_price, url FROM {table_name} ORDER BY (1.0 - CAST(sale_price AS REAL) / CAST(list_price AS REAL)) DESC;"
        
        print(f"\n==================== 正在从 {site_name} 的数据库中读取数据 ====================\n")
        
        cursor.execute(query)
        rows = cursor.fetchall()

        if not rows:
            print("数据库为空。请先运行一次对应的爬虫。")
            return

        # --- 核心修改：在Python中过滤数据 ---
        filtered_products = []
        for row in rows:
            name, list_price, sale_price, url = row
            # 确保价格是数字且原价不为0，以避免计算错误
            if isinstance(list_price, (int, float)) and isinstance(sale_price, (int, float)) and list_price > 0:
                discount = round((1 - sale_price / list_price) * 100)
                if discount >= discount_threshold:
                    filtered_products.append({
                        "name": name,
                        "list_price": list_price,
                        "sale_price": sale_price,
                        "discount": discount,
                        "url": url
                    })
        
        if not filtered_products:
            print(f"没有找到折扣率 >= {discount_threshold}% 的商品。")
            return
        
        print(f"共找到 {len(filtered_products)} 条折扣率 >= {discount_threshold}% 的商品 (按折扣率从高到低排序):\n")

        for i, prod in enumerate(filtered_products):
            print(f"--- 商品 #{i + 1} ---")
            print(f"商品名: {prod['name']}")
            print(f"原  价: ${prod['list_price']:.2f}")
            print(f"现  价: ${prod['sale_price']:.2f}  ({prod['discount']}% OFF)")
            print(f"链  接: {prod['url']}")
            print("-" * 30)

    except sqlite3.OperationalError as e:
        print(f"数据库查询错误: {e}")
        print(f"请确认表名 '{table_name}' 是否正确。")
    except Exception as e:
        print(f"发生未知错误: {e}")
    finally:
        if conn:
            conn.close()

def print_usage():
    """打印脚本的使用方法。"""
    print("\n错误：参数不正确。")
    print("用法 1: python print_db.py [网站简称]")
    print("用法 2: python print_db.py [网站简称] -d <折扣率>")
    print("用法 3: python print_db.py -a")
    print("用法 4: python print_db.py -a -d <折扣率>")
    print("\n参数说明:")
    print("  [网站简称]   要查询的特定网站。")
    print("  -a, --all    查询所有已配置的网站。")
    print("  -d, --discount 只显示折扣率大于或等于指定值的商品 (例如: -d 30)。")
    print("\n可用的网站简称:")
    for key in DATABASES:
        print(f"  - {key}")

if __name__ == "__main__":
    args = sys.argv[1:]
    
    if not args:
        print_usage()
        sys.exit(1)

    show_all = "-a" in args or "--all" in args
    discount_threshold = 0
    site_key = None

    # 解析参数
    try:
        if "-d" in args:
            idx = args.index("-d")
            discount_threshold = int(args[idx + 1])
        elif "--discount" in args:
            idx = args.index("--discount")
            discount_threshold = int(args[idx + 1])
    except (IndexError, ValueError):
        print("\n错误：-d 或 --discount 参数后必须跟一个数字。")
        print_usage()
        sys.exit(1)

    # 确定要查询的网站
    if not show_all:
        # 找到不是-d或其值的第一个参数作为网站简称
        temp_args = list(args)
        if "-d" in temp_args:
            idx = temp_args.index("-d")
            del temp_args[idx:idx+2]
        if "--discount" in temp_args:
            idx = temp_args.index("--discount")
            del temp_args[idx:idx+2]
        
        if len(temp_args) == 1:
            site_key = temp_args[0].lower()
        else:
            print_usage()
            sys.exit(1)

    # --- 执行查询 ---
    if show_all:
        for key in DATABASES:
            config = DATABASES[key]
            print_product_data(config["path"], config["table"], config["name"], discount_threshold)
    elif site_key:
        if site_key not in DATABASES:
            print(f"\n错误：无效的网站简称 '{site_key}'。")
            print_usage()
            sys.exit(1)
        config = DATABASES[site_key]
        print_product_data(config["path"], config["table"], config["name"], discount_threshold)
    else:
        print_usage()
        sys.exit(1)