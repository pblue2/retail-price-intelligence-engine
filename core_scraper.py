# 文件名: core_scraper.py

import os
import json
import sqlite3
import time
from datetime import datetime
from urllib.parse import urljoin

# 尝试导入 curl_cffi，如果失败则回退到 requests
try:
    from curl_cffi import requests
    CURL_CFFI_AVAILABLE = True
    print("成功加载 curl_cffi 库，将用于网络请求。")
except ImportError:
    import requests
    CURL_CFFI_AVAILABLE = False
    print("未找到 curl_cffi 库，将使用 requests 库。")


class CoreScraper:
    def __init__(self, config_path):
        """通过指定的配置文件初始化爬虫。"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.cfg = json.load(f)

        # --- 核心配置 ---
        self.site_name = self.cfg["site_name"]
        self.db_path = self.cfg.get("db_path")
        self.log_path = self.cfg.get("log_path")
        self.base_url = self.cfg.get("base_url", "")
        self.table_name = self.cfg.get("table_name", f"{self.site_name.lower().replace(' ', '_')}_products")
        self.impersonate = self.cfg.get("impersonate") if CURL_CFFI_AVAILABLE else None

        # --- 通知配置 ---
        self.bark_urls = self.cfg["bark_urls"]
        self.icon_url = self.cfg["icon_url"]
        self.discount_threshold = self.cfg.get("discount_threshold", 0)

        # --- 请求配置 ---
        self.api_url = self.cfg.get("api_url")
        self.headers = self.cfg.get("headers", {})
        self.cookies = self.cfg.get("cookies", {})
        self.payload_template = self.cfg.get("payload_template", {})

        self.conn = None
        self._setup_logging()
        self.init_db()
        self.migrate_database()  # 兼容旧数据库

    def _setup_logging(self):
        """配置日志，将信息同时输出到控制台和文件。"""
        log_dir = os.path.dirname(self.log_path)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        self.log_file = open(self.log_path, 'a', encoding='utf-8')
        print(f"日志将记录在: {self.log_path}")

    def log(self, message):
        """记录一条日志信息。"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self.log_file.write(log_entry + '\n')
        self.log_file.flush()

    # ---------- 1. 数据库管理 ----------
    def connect_db(self):
        """建立并返回数据库连接。"""
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """初始化数据库，并确保商品表存在（包含 miss_count）。"""
        conn = self.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {self.table_name} (
            sku_id TEXT PRIMARY KEY, 
            product_id TEXT NOT NULL, 
            name TEXT, 
            url TEXT, 
            image_url TEXT,
            list_price REAL, 
            sale_price REAL, 
            discount_percentage REAL, 
            color TEXT, 
            size TEXT,
            is_active INTEGER DEFAULT 1, 
            last_seen TEXT,
            miss_count INTEGER DEFAULT 0
        )
        """)
        conn.commit()
        conn.close()
        self.log(f"数据库 '{self.db_path}' 及表 '{self.table_name}' 初始化完成（含 miss_count）。")

    def migrate_database(self):
        """为旧数据库添加 miss_count 字段（仅执行一次）"""
        conn = self.connect_db()
        cursor = conn.cursor()
        try:
            cursor.execute(f"ALTER TABLE {self.table_name} ADD COLUMN miss_count INTEGER DEFAULT 0")
            conn.commit()
            self.log("数据库迁移完成：已添加 miss_count 字段")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                pass  # 字段已存在
            else:
                self.log(f"数据库迁移警告: {e}")
        conn.close()

    # ---------- 2. HTTP 请求 ----------
    def _make_request(self, method, url, **kwargs):
        """发起HTTP请求，如果配置了伪装浏览器，则自动使用 curl_cffi。"""
        kwargs['headers'] = {**self.headers, **kwargs.get('headers', {})}
        kwargs['cookies'] = {**self.cookies, **kwargs.get('cookies', {})}
        kwargs.setdefault('timeout', 20)

        if self.impersonate:
            return requests.request(method, url, impersonate=self.impersonate, **kwargs)
        else:
            return requests.request(method, url, **kwargs)

    # ---------- 3. 数据抓取 ----------
    def fetch_data(self):
        """主数据抓取方法。"""
        all_products = []
        max_pages = self.cfg.get("pagination", {}).get("max_pages", 1)
        for page in range(1, max_pages + 1):
            self.log(f"正在抓取第 {page}/{max_pages} 页...")
            payload = self.payload_template.copy()
            if "variables" in payload:
                payload["variables"]["page"] = page
            try:
                response = self._make_request("POST", self.api_url, json=payload)
                response.raise_for_status()
                page_products = self.parse_data(response.json(), self.base_url)
                if not page_products:
                    self.log("当前页未发现商品，停止翻页。")
                    break
                all_products.extend(page_products)
                time.sleep(self.cfg.get("delay", 1))
            except Exception as e:
                self.log(f"抓取第 {page} 页失败: {e}")
                break
        return all_products

    # ---------- 4. 数据解析 ----------
    def parse_data(self, data, base_url):
        """解析原始JSON数据，并根据配置附加URL后缀。"""
        try:
            items = data.get("data", {}).get("categoryPageData", {}).get("products", [])
            products = []
            for item in items:
                pdp_url = item.get("pdpUrl", "")
                full_url = urljoin(base_url, pdp_url) if base_url and pdp_url else pdp_url
                if self.cfg.get("url_suffix"):
                    full_url += self.cfg.get("url_suffix")
                
                def clean_price(price_val):
                    if isinstance(price_val, list) and price_val: price_val = price_val[0]
                    try: return float(str(price_val).replace('$', '').replace('CA', '').strip())
                    except (ValueError, TypeError): return 0.0

                list_price = clean_price(item.get("listPrice"))
                sale_price = clean_price(item.get("productSalePrice") or item.get("salePrice"))
                discount = round((1 - sale_price / list_price) * 100) if list_price and sale_price and list_price > sale_price else 0

                products.append({
                    "sku_id": item.get("productId"), 
                    "product_id": item.get("productId"), 
                    "name": item.get("displayName"), 
                    "url": full_url,
                    "image_url": item.get("swatches", [{}])[0].get("primaryImage"), 
                    "list_price": list_price, 
                    "sale_price": sale_price if sale_price else list_price,  # 默认使用 list_price
                    "discount_percentage": discount, 
                    "color": None, 
                    "size": None
                })
            return products
        except Exception as e:
            self.log(f"解析数据出错: {e}")
            return []

    # ---------- 5. 通知逻辑 ----------
    def send_bark_notification(self, title, body, url, image_url):
        """通过 Bark 发送通知。"""
        self.log(f"    -> 准备发送通知: {title}")
        for bark_url in self.bark_urls:
            try:
                payload = {
                    "title": title, 
                    "body": body, 
                    "icon": self.icon_url, 
                    "url": url or "", 
                    "image": image_url or "", 
                    "group": self.site_name
                }
                self._make_request("POST", bark_url, json=payload, timeout=10)
            except Exception as e:
                self.log(f"    -> Bark 推送失败: {e}")

    def check_and_notify(self, products):
        """将抓取到的商品与数据库记录比较，并发送通知（含 miss_count 补货逻辑）。"""
        conn = self.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT sku_id, sale_price, is_active, miss_count 
            FROM {self.table_name}
        """)
        old_products = {
            row['sku_id']: {
                'sale_price': row['sale_price'], 
                'is_active': row['is_active'],
                'miss_count': row['miss_count']
            } 
            for row in cursor.fetchall()
        }
        conn.close()
        
        self.log(f"正在将 {len(products)} 个抓取商品与 {len(old_products)} 条数据库记录进行比较...")
        
        stats = {"new": 0, "drop": 0, "restock": 0, "high_discount": 0}

        for p in products:
            sku_id, name, sale_price = p["sku_id"], p["name"], p["sale_price"]
            old_p = old_products.get(sku_id)
            
            # 确保 sale_price 不是 None
            if sale_price is None:
                sale_price = p.get("list_price", 0.0)

            # 1. 新品
            if not old_p:
                self.send_bark_notification(
                    f"【{self.site_name}】新品上架", 
                    f"{name}\n价格: ${sale_price}", 
                    p["url"], 
                    p["image_url"]
                )
                stats["new"] += 1

            # 2. 降价
            elif old_p and old_p['sale_price'] is not None and sale_price < old_p['sale_price']:
                self.send_bark_notification(
                    f"【{self.site_name}】商品降价", 
                    f"{name}\n现价 ${sale_price} (原价 ${old_p['sale_price']})", 
                    p["url"], 
                    p["image_url"]
                )
                stats["drop"] += 1

            # 3. 重新上架（仅 miss_count >= 3 才通知，避免频繁）
            elif old_p and not old_p['is_active'] and old_p['miss_count'] >= 3:
                self.send_bark_notification(
                    f"【{self.site_name}】重新上架", 
                    f"{name}\n价格: ${sale_price}", 
                    p["url"], 
                    p["image_url"]
                )
                stats["restock"] += 1

            # 4. 超高折扣（仅对新品或降价商品发）
            discount = p.get("discount_percentage", 0)
            if discount > self.discount_threshold:
                if not old_p or (old_p['sale_price'] is not None and sale_price < old_p.get('sale_price', float('inf'))):
                    self.send_bark_notification(
                        f"【{self.site_name}】超高折扣!", 
                        f"{discount}% OFF - {name}\n价格: ${sale_price}", 
                        p["url"], 
                        p["image_url"]
                    )
                    stats["high_discount"] += 1

        self.log(f"通知统计 → 新品: {stats['new']} | 降价: {stats['drop']} | 补货: {stats['restock']} | 高折扣: {stats['high_discount']}")

    # ---------- 6. 数据库更新 ----------
    def update_database(self, products):
        """保存商品数据，更新 miss_count，并标记长期未出现商品。"""
        conn = self.connect_db()
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 所有活跃商品 miss_count +1
        cursor.execute(f"UPDATE {self.table_name} SET miss_count = miss_count + 1 WHERE is_active = 1")
        
        # 2. 更新本次抓取的商品（miss_count = 0, is_active = 1）
        update_data = []
        for p in products:
            # 确保 sale_price 有默认值
            if p["sale_price"] is None:
                p["sale_price"] = p.get("list_price", 0.0)
            update_data.append((
                p["sku_id"], p["product_id"], p["name"], p["url"], p["image_url"], 
                p["list_price"], p["sale_price"], p["discount_percentage"], 
                p["color"], p["size"], 1, now, 0  # is_active=1, miss_count=0
            ))
        
        if update_data:
            cursor.executemany(f"""
                INSERT INTO {self.table_name} 
                (sku_id, product_id, name, url, image_url, list_price, sale_price, 
                 discount_percentage, color, size, is_active, last_seen, miss_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sku_id) DO UPDATE SET
                    name=excluded.name, url=excluded.url, image_url=excluded.image_url, 
                    list_price=excluded.list_price, sale_price=excluded.sale_price,
                    discount_percentage=excluded.discount_percentage, color=excluded.color, 
                    size=excluded.size, is_active=excluded.is_active, 
                    last_seen=excluded.last_seen, miss_count=excluded.miss_count
            """, update_data)
        
        # 3. miss_count >= 80 → is_active = 0
        inactive_count = cursor.execute(
            f"UPDATE {self.table_name} SET is_active = 0 WHERE miss_count >= 80 AND is_active = 1"
        ).rowcount
        if inactive_count > 0:
            self.log(f"标记 {inactive_count} 个长期未出现商品为不活跃（miss_count >= 80）")

        conn.commit()
        conn.close()
        self.log(f"数据库已更新。本次活跃商品: {len(products)} 个")

    # ---------- 7. 主执行逻辑 ----------
    def run(self):
        """爬虫的主运行循环，包含首次运行静默处理。"""
        self.log(f"\n{'='*20} 开始为 {self.site_name} 执行抓取任务 {'='*20}")
        
        # 检查数据库是否已初始化
        conn = self.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT 1 FROM {self.table_name} LIMIT 1")
        is_database_populated = cursor.fetchone() is not None
        conn.close()
        
        products = self.fetch_data()
        
        if not products:
            self.log("未抓取到任何商品，任务结束。")
            self.log_file.close()
            return

        if not is_database_populated:
            self.log("检测到首次运行或数据库为空 → 本次仅初始化数据，不发送通知。")
        else:
            self.log("非首次运行 → 开始检查更新并发送通知...")
            self.check_and_notify(products)

        self.update_database(products)

        # 最终统计
        conn = self.connect_db()
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
        total = cursor.fetchone()[0]
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE is_active = 1")
        active = cursor.fetchone()[0]
        cursor.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE miss_count >= 80")
        long_inactive = cursor.fetchone()[0]
        conn.close()

        self.log(f"{self.site_name} 任务成功结束！")
        self.log(f"   总SKU: {total} | 活跃: {active} | 长期未出现: {long_inactive}")
        self.log(f"   本次抓取: {len(products)} 个商品")
        self.log_file.close()