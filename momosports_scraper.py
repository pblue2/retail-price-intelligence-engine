# 文件名: momosports_scraper.py

import json
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core_scraper import CoreScraper, requests
import time
import re

class MomoSportsScraper(CoreScraper):
    """
    Momo Sports 专属爬虫，实现了先抓HTML首页，再抓API后续页的混合逻辑。
    """

    def _get_total_count(self, soup):
        """从HTML或HTML片段中提取商品总数。"""
        try:
            toolbar_amount = soup.select_one("p.toolbar-amount")
            if toolbar_amount:
                # 正则表达式匹配 "of 157" 这样的模式
                match = re.search(r'of\s+(\d+)', toolbar_amount.text)
                if match:
                    return int(match.group(1))
        except Exception:
            return 0
        return 0

    def fetch_data(self):
        """实现两步走策略：先抓HTML，再抓API。"""
        all_products = []
        pagination = self.cfg.get("pagination", {})
        page_size = pagination.get("page_size", 36)
        
        session = requests.Session()
        session.headers.update(self.headers)
        
        # --- 第1步: 抓取并解析第一页 (HTML) ---
        try:
            main_page_url = f"{self.api_url}?product_list_limit={page_size}"
            self.log(f"📦 正在抓取第 1 页 (通过解析HTML)...")
            response = session.get(main_page_url, impersonate=self.impersonate, timeout=30)
            response.raise_for_status()
            
            # Session会自动保存Cookie，同时我们直接解析这个页面的HTML
            page1_products = self.parse_data(response.text, self.base_url)
            all_products.extend(page1_products)
            self.log(f"✅ 第 1 页解析成功，找到 {len(page1_products)} 个商品。")
            
            # 从第一页获取商品总数，以决定总共需要翻多少页
            soup = BeautifulSoup(response.text, 'lxml')
            total_count = self._get_total_count(soup)
            if total_count > 0:
                total_pages = (total_count + page_size - 1) // page_size
                self.log(f"ℹ️ 商品总数: {total_count}，共计 {total_pages} 页。")
            else:
                total_pages = pagination.get("max_pages", 10)
                self.log(f"⚠️ 未能获取商品总数，将按最大页数 {total_pages} 抓取。")

        except Exception as e:
            self.log(f"❌ 抓取第 1 页 (HTML) 失败: {e}")
            return [] # 如果第一页都失败了，就没必要继续了

        # --- 第2步: 循环抓取后续页 (API) ---
        for page in range(2, total_pages + 1):
            self.log(f"📦 正在抓取第 {page}/{total_pages} 页 (通过API)...")
            params = {
                'p': page,
                'product_list_limit': page_size,
                'shopbyAjax': 1
            }
            try:
                response = session.get(self.api_url, params=params, impersonate=self.impersonate, timeout=20)
                response.raise_for_status()
                json_data = response.json()
                html_content = json_data.get('categoryProducts')

                if not html_content:
                    self.log("ℹ️ API未返回商品HTML内容，停止翻页。")
                    break

                page_products = self.parse_data(html_content, self.base_url)
                if not page_products: break
                
                all_products.extend(page_products)
                time.sleep(self.cfg.get("delay", 1))
            except Exception as e:
                self.log(f"❌ 抓取第 {page} 页 (API) 失败: {e}")
                break
        return all_products

    def parse_data(self, html_text, base_url):
        """解析HTML片段，此方法被两步策略共用。"""
        self.log("🤖 正在使用 BeautifulSoup 解析HTML内容...")
        try:
            soup = BeautifulSoup(html_text, 'lxml')
            products = []
            product_items = soup.select('li.product-item')
            for item in product_items:
                try:
                    name_tag = item.select_one('a.product-item-link')
                    link_tag = item.select_one('a.product-item-photo')
                    image_tag = item.select_one('img.product-image-photo')
                    sku_id_raw = item.get('id', '')
                    final_price_tag = item.select_one('.price-final_price .price')
                    old_price_tag = item.select_one('.old-price .price')

                    if not (name_tag and link_tag and sku_id_raw and final_price_tag): continue
                    
                    name = name_tag.text.strip()
                    product_url = link_tag.get('href')
                    image_url = image_tag.get('src') if image_tag else None
                    sku_id = sku_id_raw.replace('product-sku-', '')
                    sale_price = float(re.sub(r'[^\d.]', '', final_price_tag.text))
                    list_price = float(re.sub(r'[^\d.]', '', old_price_tag.text)) if old_price_tag else sale_price
                    discount = round((1 - sale_price / list_price) * 100) if list_price > sale_price else 0

                    products.append({
                        "sku_id": sku_id, "product_id": sku_id, "name": name, "url": product_url, 
                        "image_url": image_url, "list_price": list_price, "sale_price": sale_price, 
                        "discount_percentage": discount, "color": None, "size": None
                    })
                except Exception as e:
                    self.log(f"⚠️ 解析单个商品时出错: {e}")
            self.log(f"✅ 解析完成，找到 {len(products)} 个商品。")
            return products
        except Exception as e:
            self.log(f"❌ 在MomoSportsScraper中解析HTML时发生严重错误: {e}")
            return []