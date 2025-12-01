# 文件名: sportsexperts_scraper.py

from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core_scraper import CoreScraper, requests
import time

class SportsExpertsScraper(CoreScraper):
    """
    Sports Experts 专属爬虫类，实现了会话管理和正确的JSON解析逻辑。
    """
    
    def _parse_html_products(self, html_text, base_url):
        soup = BeautifulSoup(html_text, 'lxml')
        products = []
        product_tiles = soup.select('div.product-tile[data-product-id]')
        for tile in product_tiles:
            try:
                product_id = tile.get('data-product-id')
                name_tag = tile.select_one('a[data-qa="search-product-title"]')
                price_tag = tile.select_one('span[data-qa="search-product-price"]')
                link_tag = tile.select_one('a.product-tile-media')
                image_tag = tile.select_one('img.img-fluid')
                if not (product_id and name_tag and price_tag and link_tag): continue
                name = name_tag.text.strip()
                price_str = price_tag.text.strip().replace('$', '').replace(',', '')
                price = float(price_str) if price_str else 0.0
                product_url = urljoin(base_url, link_tag.get('href'))
                image_url = image_tag.get('src') if image_tag else None
                href = link_tag.get('href', '')
                sku_id = href.split('/')[-1] if '/' in href else product_id
                products.append({
                    "sku_id": sku_id, "product_id": product_id, "name": name, "url": product_url, 
                    "image_url": image_url, "list_price": price, "sale_price": price, 
                    "discount_percentage": 0, "color": None, "size": None
                })
            except Exception as e: self.log(f"⚠️ 解析单个HTML商品时出错: {e}")
        return products

    def _parse_json_products(self, data, base_url):
        """
        专门用于解析后续页面的API JSON，移除了错误的去重逻辑。
        """
        search_results = data.get("ProductSearchResults", {})
        items = search_results.get("SearchResults", [])
        total_count = search_results.get("TotalCount", 0)
        products = []
        
        # --- 核心修正：不再按 ProductId 去重 ---
        for item in items:
            product_id = item.get("ProductId")
            pricing = item.get("Pricing", {})
            list_price = pricing.get("ListPrice")
            sale_price = pricing.get("Price") or list_price
            discount = round((1 - sale_price / list_price) * 100) if list_price and sale_price and list_price > sale_price else 0
            
            products.append({
                "sku_id": item.get("VariantId"), # 每个Variant都是唯一的
                "product_id": product_id,
                "name": item.get("DisplayName"),
                "url": urljoin(base_url, item.get("Url")),
                "image_url": item.get("ImageUrl"),
                "list_price": list_price,
                "sale_price": sale_price,
                "discount_percentage": discount,
                "color": None, "size": None
            })
        return products, total_count


    def fetch_data(self):
        """重写数据抓取方法，引入Session对象来自动管理Cookie。"""
        all_products = []
        
        session = requests.Session()
        session.headers.update(self.headers)
        
        try:
            main_page_url = self.cfg.get("main_page_url")
            if not main_page_url:
                self.log("❌ 配置文件中缺少 'main_page_url'。")
                return []
            self.log(f"📦 正在访问主页以获取Cookie...")
            response = session.get(main_page_url, impersonate=self.impersonate, timeout=30)
            response.raise_for_status()
            
            self.log(f"✅ 第 1 页HTML内容获取成功，开始解析...")
            page1_products = self._parse_html_products(response.text, self.base_url)
            all_products.extend(page1_products)
            self.log(f"✅ 第 1 页解析成功，找到 {len(page1_products)} 个商品。")
        except Exception as e:
            self.log(f"❌ 抓取第 1 页 (HTML) 失败: {e}")
        
        pagination = self.cfg.get("pagination", {})
        page_size = pagination.get("page_size", 24)
        max_pages = pagination.get("max_pages", 15)
        
        # 使用一个变量来存储从API获取的商品总数
        total_api_count = 0

        for page in range(2, max_pages + 1):
            self.log(f"📦 正在抓取第 {page}/{max_pages} 页 (通过API)...")
            payload = self.payload_template.copy()
            payload["Page"] = page
            payload["StartIndex"] = (page - 1) * page_size
            
            try:
                response = session.post(self.api_url, json=payload, impersonate=self.impersonate, timeout=20)
                response.raise_for_status()
                json_data = response.json()
                
                page_products, total_api_count = self._parse_json_products(json_data, self.base_url)
                
                if not page_products:
                    self.log("ℹ️ API返回内容为空，已抓取完所有后续页面，停止翻页。")
                    break
                all_products.extend(page_products)

                # 使用从API获取的总数来判断是否提前结束
                if total_api_count > 0 and len(all_products) >= total_api_count:
                    self.log(f"已抓取 {len(all_products)}/{total_api_count} 个商品，提前结束。")
                    break
                
                time.sleep(self.cfg.get("delay", 1))
            except Exception as e:
                self.log(f"❌ 抓取第 {page} 页 (API) 失败: {e}")
                break
        return all_products