# 文件名: run_scraper.py

import sys
import json
from core_scraper import CoreScraper
from sportinglife_scraper import SportingLifeScraper 
from sportsexperts_scraper import SportsExpertsScraper 
from momosports_scraper import MomoSportsScraper
from oberson_scraper import ObersonScraper # <--- 导入新的 Oberson 爬虫
from lacordee_scraper import LaCordeeScraper

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python run_scraper.py <配置文件的路径>")
        sys.exit(1)

    config_file_path = sys.argv[1]
    
    with open(config_file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    site_name = config.get("site_name")

    if site_name == "Sporting Life":
        print(f"识别到 {site_name} 配置，使用专属的 SportingLifeScraper。")
        scraper = SportingLifeScraper(config_path=config_file_path)
    elif site_name == "Sports Experts":
        print(f"识别到 {site_name} 配置，使用专属的 SportsExpertsScraper。")
        scraper = SportsExpertsScraper(config_path=config_file_path)
    elif site_name == "Momo Sports":
        print(f"识别到 {site_name} 配置，使用专属的 MomoSportsScraper。")
        scraper = MomoSportsScraper(config_path=config_file_path)
    elif site_name == "Oberson": # <--- 为 Oberson 添加新的逻辑分支
        print(f"识别到 {site_name} 配置，使用专属的 ObersonScraper。")
        scraper = ObersonScraper(config_path=config_file_path)
    elif site_name == "LaCordee":
        print(f"识别到 {site_name} 配置，使用 LaCordeeScraper")
        scraper = LaCordeeScraper(config_path=config_file_path)
    else:
        print(f"识别到 {site_name} 配置，使用通用的 CoreScraper。")
        scraper = CoreScraper(config_path=config_file_path)
    
    scraper.run()
