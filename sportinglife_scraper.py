# 文件名: sportinglife_scraper.py

import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core_scraper import CoreScraper

class SportingLifeScraper(CoreScraper):
    """
    Sporting Life 专属爬虫类。
    它重写了 fetch_data 和 parse_data 方法，以适应HTML页面的抓取和解析。
    """
    def fetch_data(self):
        """重写数据抓取方法，以处理单个GET请求并返回HTML文本。"""
        self.log(f"📦 正在通过GET请求抓取页面: {self.api_url}")
        try:
            request_method = self.cfg.get("request_method", "GET")
            response = self._make_request(request_method, self.api_url)
            response.raise_for_status()
            return self.parse_data(response.text, self.base_url)
        except Exception as e:
            self.log(f"❌ 抓取页面失败: {e}")
            return []

    def parse_data(self, html_text, base_url):
        """
        重写数据解析方法，使用精准的CSS选择器和健壮的价格清理逻辑。
        """
        self.log("🤖 正在使用 BeautifulSoup 解析HTML内容...")
        try:
            soup = BeautifulSoup(html_text, 'lxml')
            products = []
            
            product_tiles = soup.select('div.product-tile')
            
            for tile in product_tiles:
                name_tag = tile.select_one('span.product-name')
                link_tag = tile.select_one('a.thumb-link')
                image_tag = tile.select_one('a.thumb-link img')
                item_id = tile.get('data-itemid')

                if not (name_tag and link_tag and item_id):
                    continue
                
                name = name_tag.text.strip()
                product_url = urljoin(base_url, link_tag.get('href'))
                image_url = image_tag.get('src') if image_tag else None

                # --- 开始：最终加强版的价格和折扣处理逻辑 ---
                list_price = 0.0
                sale_price = 0.0
                discount = 0

                try:
                    def clean_and_convert_price(price_tag):
                        """一个健壮的函数，用于清理和转换各种价格格式。"""
                        if not price_tag:
                            return 0.0
                        # '1 100,00 $' -> '1100.00' | '$1,100.00' -> '1100.00'
                        price_str = price_tag.text.strip()
                        cleaned_str = price_str.replace('$', '').replace(' ', '').replace(',', '.')
                        # 处理可能存在的多个小数点问题，只保留最后一个
                        if cleaned_str.count('.') > 1:
                           parts = cleaned_str.split('.')
                           cleaned_str = "".join(parts[:-1]) + "." + parts[-1]
                        return float(cleaned_str)

                    list_price_tag = tile.select_one('span.price-standard')
                    sale_price_tag = tile.select_one('span.price-sales')

                    sale_price = clean_and_convert_price(sale_price_tag)
                    
                    if list_price_tag:
                        list_price = clean_and_convert_price(list_price_tag)
                    else:
                        list_price = sale_price

                    if list_price > sale_price > 0:
                        discount = round((1 - sale_price / list_price) * 100)

                except (ValueError, AttributeError, TypeError) as e:
                    price_container = tile.select_one('div.product-price')
                    price_text = price_container.text.strip() if price_container else "N/A"
                    self.log(f"⚠️ 无法解析商品 '{name}' 的价格: '{price_text}'. 错误: {e}. 将价格记为0。")
                # --- 结束：最终加强版的价格和折扣处理逻辑 ---

                products.append({
                    "sku_id": item_id, "product_id": item_id.split('-')[0], "name": name,
                    "url": product_url, "image_url": image_url, "list_price": list_price,
                    "sale_price": sale_price, "discount_percentage": discount,
                    "color": None, "size": None
                })
            
            self.log(f"✅ 解析完成，共找到 {len(products)} 个商品。")
            return products
        except Exception as e:
            self.log(f"❌ 在SportingLifeScraper中解析HTML时发生严重错误: {e}")
            return []
