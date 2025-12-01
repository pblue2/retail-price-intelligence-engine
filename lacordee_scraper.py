# 文件名: lacordee_scraper.py
from playwright.sync_api import sync_playwright
import re
import time
import hashlib
from urllib.parse import urljoin
from core_scraper import CoreScraper

class LaCordeeScraper(CoreScraper):
    def __init__(self, config_path):
        super().__init__(config_path)
        self.search_url = self.cfg.get("search_url", "https://www.lacordee.com/en/search.html?query=Arcteryx")
        self.max_pages = self.cfg.get("max_pages", 5)
        self.delay = self.cfg.get("delay", 2)

    def fetch_data(self):
        products = []
        seen_variants = set()
        
        # --- 配置 ---
        max_retries = 3
        BASE_DOMAIN = "https://www.lacordee.com"

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            )
            page = context.new_page()

            for page_num in range(1, self.max_pages + 1):
                url = f"{self.search_url}&page={page_num}"
                self.log(f"正在抓取第 {page_num} 页: {url}")

                # --- 重试循环 ---
                for attempt in range(1, max_retries + 1):
                    try:
                        # 使用 domcontentloaded 加快失败判定（不等广告脚本）
                        page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        time.sleep(3)

                        try:
                            # 等待商品容器出现
                            page.wait_for_selector('article.item-root-Fmc', timeout=20000)
                        except:
                            if attempt < max_retries:
                                raise Exception("未找到商品元素 (加载超时)")
                            else:
                                self.log(f"第 {page_num} 页多次重试后仍未发现商品，跳过。")
                                break 

                        # 滚动加载图片
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(2)
                        page.evaluate("window.scrollTo(0, 0)")

                        items = page.query_selector_all('article.item-root-Fmc')
                        self.log(f"第 {page_num} 页找到 {len(items)} 个商品")

                        if not items:
                            break

                        # --- 解析逻辑 ---
                        for item in items:
                            try:
                                # 1. 提取 URL 和 名称
                                link_elem = item.query_selector('a.item-name-YL8')
                                href = link_elem.get_attribute('href') if link_elem else ""
                                name_elem = item.query_selector('h3')
                                raw_name = name_elem.inner_text().strip() if name_elem else "Unknown"

                                # URL 清洗（仅用于存储链接，不再用于生成ID）
                                if href:
                                    full_url = urljoin(BASE_DOMAIN, href)
                                    product_url = full_url.split('?')[0].lower().rstrip('/')
                                else:
                                    product_url = ""

                                # 2. 提取价格
                                sale_elem = item.query_selector('span.price-specialPrice-6Lo')
                                orig_elem = item.query_selector('span.price-normalPrice-zvG')
                                sale_text = sale_elem.inner_text().strip() if sale_elem else None
                                orig_text = orig_elem.inner_text().strip() if orig_elem else None

                                def parse_price(text):
                                    if not text: return 0.0
                                    return float(re.sub(r'[^\d.]', '', text))

                                sale_price_val = parse_price(sale_text)
                                orig_price_val = parse_price(orig_text)

                                if sale_price_val > 0:
                                    sale_price = sale_price_val
                                    list_price = orig_price_val if orig_price_val > 0 else sale_price_val
                                else:
                                    sale_price = orig_price_val
                                    list_price = orig_price_val

                                discount = 0
                                if list_price > 0 and list_price > sale_price:
                                    discount = round((list_price - sale_price) / list_price * 100)

                                # 3. 提取颜色
                                color_elem = item.query_selector('dd')
                                raw_color = color_elem.inner_text().strip() if color_elem else "Unknown"
                                if raw_color == "Unknown":
                                    swatch_elem = item.query_selector('button.swatch-button-cZb[title]')
                                    raw_color = swatch_elem.get_attribute('title') if swatch_elem else "Unknown"

                                # --- 4. 【核心】语义 ID 生成策略 ---
                                # 清洗名字和颜色
                                clean_name = raw_name.lower().strip()
                                clean_color = raw_color.lower().replace('/', '-').replace(' ', '').strip()

                                if clean_color == "unknown":
                                    # 只有颜色未知时，才退回到使用 URL 哈希兜底
                                    if product_url:
                                        base_key = product_url
                                    else:
                                        base_key = clean_name # 极少情况
                                    
                                    base_sku = hashlib.md5(base_key.encode('utf-8')).hexdigest()[:10]
                                    unique_sku_id = f"{base_sku}-unk"
                                else:
                                    # 黄金标准：ID 由 "名字+颜色" 决定，彻底无视 URL 变化
                                    composite_key = f"{clean_name}|{clean_color}"
                                    unique_sku_id = hashlib.md5(composite_key.encode('utf-8')).hexdigest()[:12]
                                    
                                    # base_sku 用于聚合（同名商品），使用名字哈希
                                    base_sku = hashlib.md5(clean_name.encode('utf-8')).hexdigest()[:10]

                                # 5. 去重
                                if unique_sku_id in seen_variants:
                                    continue
                                seen_variants.add(unique_sku_id)

                                full_name = f"{raw_name} - {raw_color}".strip(" -") if raw_color != "Unknown" else raw_name
                                
                                # 6. 图片提取
                                # 优先找 lazy load 图片类，找不到则找任意 img
                                img_elem = item.query_selector('img[class*="item-imageLoaded"]') or item.query_selector('img')
                                image_url = ""
                                if img_elem:
                                    raw_src = img_elem.get_attribute('src') or img_elem.get_attribute('data-src')
                                    if raw_src:
                                        # 智能拼接相对路径
                                        image_url = urljoin(BASE_DOMAIN, raw_src.split('?')[0])

                                products.append({
                                    "sku_id": unique_sku_id,
                                    "product_id": base_sku,
                                    "name": full_name,
                                    "url": product_url,
                                    "image_url": image_url,
                                    "list_price": list_price,
                                    "sale_price": sale_price,
                                    "discount_percentage": discount,
                                    "color": raw_color,
                                    "size": None,
                                    "source": "lacordee"
                                })

                            except Exception as e:
                                continue

                        time.sleep(time.time() % 2 + 1)
                        break # 成功，跳出重试循环

                    except Exception as e:
                        self.log(f"⚠️ 第 {page_num} 页 (第 {attempt} 次尝试) 失败: {e}")
                        if attempt < max_retries:
                            time.sleep(5)
                        else:
                            self.log(f"❌ 第 {page_num} 页已达到最大重试次数，跳过。")

            browser.close()

        self.log(f"抓取完成，共入库 {len(products)} 条商品")
        return products
