"""
اسکرپینگ اتکالا - یک دسته با همه صفحات
استفاده:
    python3 etkala_scraper.py <URL_دسته> "<نام_دسته>"

مثال:
    python3 etkala_scraper.py "https://etkala.ir/search/category/14" "لبنیات"
"""

import sys
import re
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup


# ═══════════════════════════════════════════════
# تنظیمات
# ═══════════════════════════════════════════════
BASE_URL = "https://etkala.ir"
OUTPUT_DIR = Path("etkala_datasets")
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_PAGES = 50              # حداکثر تعداد صفحه برای هر دسته
PAGE_LOAD_DELAY = 5         # صبر بعد از باز کردن هر صفحه
SCROLL_PAUSE = 2            # صبر بعد از هر اسکرول
PAGE_DELAY = 2              # فاصله بین صفحات


# ═══════════════════════════════════════════════
# ساخت درایور
# ═══════════════════════════════════════════════
def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=fa-IR")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


# ═══════════════════════════════════════════════
# ابزار
# ═══════════════════════════════════════════════
def to_en_digits(s):
    if not s:
        return s
    return str(s).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬،", "0123456789,,"))


def parse_price(s):
    s = to_en_digits(str(s))
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s else None


def add_page_to_url(url, page_num):
    """اضافه کردن پارامتر page به URL با حفظ بقیه پارامترها."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs["page"] = [str(page_num)]
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def parse_raw_text(raw):
    raw = raw.strip()
    raw = re.sub(r"\s+", " ", raw)

    m_off = re.match(r"^(\d{1,2})\s+", raw)
    off_percent = int(m_off.group(1)) if m_off else None
    rest = raw[m_off.end():] if m_off else raw

    price_matches = list(re.finditer(r"([\d۰-۹][\d۰-۹,٬،]{3,})", rest))

    if len(price_matches) >= 2:
        main_price_str = price_matches[-1].group(1)
        off_price_str = price_matches[-2].group(1)
        title = rest[:price_matches[-2].start()].strip()
    elif len(price_matches) == 1:
        main_price_str = price_matches[0].group(1)
        off_price_str = None
        title = rest[:price_matches[0].start()].strip()
    else:
        main_price_str = None
        off_price_str = None
        title = rest

    title = re.sub(r"تومان[ء\s]*", "", title).strip()
    title = re.sub(r"\s+", " ", title).strip()

    main_price = parse_price(main_price_str)
    off_price = parse_price(off_price_str)

    if main_price and off_price and off_price > main_price:
        main_price, off_price = off_price, main_price

    if off_percent is None and main_price and off_price and main_price > 0:
        off_percent = round((main_price - off_price) / main_price * 100)

    return {
        "title": title or None,
        "main_price": main_price,
        "off_price": off_price,
        "off_percent": off_percent,
    }


# ═══════════════════════════════════════════════
# استخراج محصولات از HTML
# ═══════════════════════════════════════════════
def extract_from_html(html, category_name, extracted_at):
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select("a[href*='/products/']")

    page_products = {}
    for a in links:
        href = a.get("href", "")
        m = re.search(r"/products/(\d+)", href)
        if not m:
            continue
        pid = m.group(1)
        if pid in page_products:
            continue

        raw_text = a.get_text(" ", strip=True)
        parsed = parse_raw_text(raw_text)

        if not parsed["title"] or not parsed["main_price"]:
            continue

        page_products[pid] = {
            "id": int(pid),
            "title": parsed["title"],
            "main_price": parsed["main_price"],
            "off_price": parsed["off_price"],
            "off_percent": parsed["off_percent"],
            "inventory": None,
            "store": "انبار مرکزی اتکالا",
            "category_name": category_name,
            "is_exist": True,
            "extracted_at": extracted_at,
            "source": "etkala.ir",
            "url": f"{BASE_URL}{href}" if href.startswith("/") else href,
        }

    return page_products


# ═══════════════════════════════════════════════
# اسکرپ همه صفحات یک دسته
# ═══════════════════════════════════════════════
def scrape_all_pages(driver, base_url, category_name):
    extracted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    all_products = {}     # {id: product}  ← برای حذف تکراری‌ها

    for page_num in range(1, MAX_PAGES + 1):
        page_url = add_page_to_url(base_url, page_num)
        print(f"\n📄 صفحه {page_num}: {page_url}")

        try:
            driver.get(page_url)
            time.sleep(PAGE_LOAD_DELAY)

            # اسکرول تا انتهای صفحه (برای لود lazy-load ها)
            last_h = driver.execute_script("return document.body.scrollHeight")
            for _ in range(10):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_PAUSE)
                new_h = driver.execute_script("return document.body.scrollHeight")
                if new_h == last_h:
                    break
                last_h = new_h

            html = driver.page_source
            page_products = extract_from_html(html, category_name, extracted_at)

            # تعداد محصول جدید
            new_count = 0
            for pid, prod in page_products.items():
                if pid not in all_products:
                    all_products[pid] = prod
                    new_count += 1

            print(f"  → {len(page_products)} محصول در صفحه، {new_count} محصول جدید")
            print(f"  → مجموع تا اینجا: {len(all_products)}")

            # اگه این صفحه هیچ محصول جدیدی نداشت → یعنی به آخر رسیدیم
            if new_count == 0:
                print("  ✓ صفحه جدید محصولی نداشت — توقف.")
                break

            time.sleep(PAGE_DELAY)

        except Exception as e:
            print(f"  ❌ خطا در صفحه {page_num}: {e}")
            break

    return list(all_products.values())


# ═══════════════════════════════════════════════
# ذخیره JSON
# ═══════════════════════════════════════════════
def save_json(products, category_name):
    safe_name = re.sub(r"[^\w\-]", "_", category_name)
    filename = OUTPUT_DIR / f"{safe_name}.json"

    data = {
        "category_name": category_name,
        "extracted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "etkala.ir",
        "total_products": len(products),
        "products": products,
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n💾 {len(products)} محصول ذخیره شد → {filename}")
    return filename


# ═══════════════════════════════════════════════
# اجرا
# ═══════════════════════════════════════════════
def main():
    if len(sys.argv) < 3:
        print("استفاده:")
        print('  python3 etkala_scraper.py "<URL دسته>" "<نام دسته>"')
        print()
        print("مثال:")
        print('  python3 etkala_scraper.py "https://etkala.ir/search/category/14" "لبنیات"')
        sys.exit(1)

    base_url = sys.argv[1].strip()
    category_name = sys.argv[2].strip()

    print(f"\n{'='*60}")
    print(f"📦 دسته: {category_name}")
    print(f"🔗 مسیر پایه: {base_url}")
    print(f"{'='*60}")

    driver = make_driver()
    try:
        products = scrape_all_pages(driver, base_url, category_name)

        if not products:
            print("⚠️ هیچ محصولی استخراج نشد.")
            return

        save_json(products, category_name)

        print("\n📋 نمونه ۵ محصول اول:")
        for p in products[:5]:
            print(f"  • [{p['id']}] {p['title']}")
            print(f"      قیمت: {p['main_price']:,}  |  تخفیف: {p['off_price']}  |  {p['off_percent']}%")

    except Exception as e:
        print(f"❌ خطا: {e}")
        traceback.print_exc()
    finally:
        driver.quit()


if __name__ == "__main__":
    main()