# oberson_scraper.py
import json
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from core_scraper import CoreScraper
from playwright.sync_api import sync_playwright

def extract_json_from_html_attribute(raw):
    if not raw:
        return None
    s = raw.replace('&quot;', '"')
    s = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s)
    match = re.search(r'\{.*\}', s, re.DOTALL)
    return match.group(0) if match else None

def safe_parse_data_product(raw):
    json_str = extract_json_from_html_attribute(raw)
    if not json_str:
        return None
    try:
        data = json.loads(json_str)
        variants_str = data.get('variants', '')
        if isinstance(variants_str, str) and variants_str.strip().startswith('['):
            data['variants'] = json.loads(variants_str.strip())
        else:
            data['variants'] = []
        return data
    except:
        return None

class ObersonScraper(CoreScraper):
    def fetch_data(self):
        all_products = []
        pages = self.cfg.get('pages_to_scrape', [1, 2])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=self.headers.get("User-Agent", "")
            )
            page = context.new_page()

            for page_num in pages:
                url = f"{self.cfg['main_page_url']}?page={page_num}"
                self.log(f"Parsing page {page_num}: {url}")

                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_selector('div.boost-sd__product-item', timeout=30000)

                    soup = BeautifulSoup(page.content(), 'lxml')
                    items = soup.select('div.boost-sd__product-item')
                    self.log(f"Page {page_num}: {len(items)} Arc'teryx products")

                    for item in items:
                        data = safe_parse_data_product(item.get('data-product', ''))
                        if not data:
                            continue

                        tags = [str(t).lower() for t in data.get('tags', [])]
                        if 'arc' not in ' '.join(tags):
                            continue

                        title_tag = item.select_one('.boost-sd__product-title')
                        name = title_tag.get_text(strip=True) if title_tag else "Unknown"

                        handle = data.get('handle', '')
                        product_url = urljoin(self.base_url, f"/en/products/{handle}")
                        product_id = str(data.get('id', ''))

                        list_price = float(data.get('compareAtPriceMin') or data.get('priceMin', 0))
                        sale_price = float(data.get('priceMin', 0))
                        discount = round((1 - sale_price / list_price) * 100) if list_price > sale_price else 0

                        image_url = data.get('images', [{}])[0].get('src', '')
                        if image_url and image_url.startswith('//'):
                            image_url = 'https:' + image_url

                        for v in data.get('variants', []):
                            title = v.get('title', '')
                            parts = [p.strip() for p in title.split('/') if p.strip()]
                            color = parts[0] if len(parts) > 0 else None
                            size = parts[1] if len(parts) > 1 else None

                            all_products.append({
                                "sku_id": str(v.get('id', '')),
                                "product_id": product_id,
                                "name": f"{name} - {title}",
                                "url": product_url,
                                "image_url": image_url,
                                "list_price": list_price,
                                "sale_price": sale_price,
                                "discount_percentage": discount,
                                "color": color,
                                "size": size
                            })

                except Exception as e:
                    self.log(f"Page {page_num} error: {e}")

            browser.close()

        self.log(f"Total fetched: {len(all_products)} Arc'teryx products")
        return all_products