import requests
from bs4 import BeautifulSoup
import csv
import json
from datetime import datetime
import os
import re

# ایجاد پوشه‌های لازم
os.makedirs('data2', exist_ok=True)

url = 'https://etkala.ir/search/category/5'

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'fa-IR,fa;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    response = requests.get(url, headers=headers, timeout=30)
    
    if response.status_code == 200:
        print("✅ دریافت صفحه با موفقیت انجام شد!")
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # ==========================================
        # روش 1: استخراج از دیتای JSON داخل صفحه (دقیق‌ترین روش)
        # ==========================================
        products_from_json = []
        
        # پیدا کردن تگ script که حاوی دیتای محصولات است
        script_tags = soup.find_all('script', type='application/json')
        
        for script in script_tags:
            try:
                import json as json_lib
                data = json_lib.loads(script.string)
                
                # بررسی وجود داده محصولات در ساختار JSON
                if 'props' in data and 'pageProps' in data['props']:
                    page_props = data['props']['pageProps']
                    
                    # استخراج محصولات از بخش homeProducts
                    if 'homeProducts' in page_props:
                        for section in page_props['homeProducts']:
                            if 'products' in section:
                                for product in section['products']:
                                    # استخراج اطلاعات محصول
                                    product_data = {
                                        'id': product.get('id', ''),
                                        'title': product.get('title', ''),
                                        'main_price': product.get('mainPrice', 0),
                                        'off_price': product.get('offPrice', 0),
                                        'off_percent': product.get('offPrecent', 0),
                                        'inventory': product.get('inventory', 0),
                                        'store': product.get('storeTitle', ''),
                                        'is_exist': product.get('isExist', False),
                                        'extracted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        'source': 'JSON'
                                    }
                                    
                                    # استخراج تصویر
                                    if 'picture' in product and product['picture']:
                                        product_data['image'] = product['picture'].get('thumbPath', '')
                                        product_data['image_alt'] = product['picture'].get('altName', '')
                                    
                                    products_from_json.append(product_data)
            except:
                continue
        
        # ==========================================
        # روش 2: استخراج از HTML (روش پشتیبان)
        # ==========================================
        products_from_html = []
        
        # پیدا کردن تمام کارت‌های محصول
        product_cards = soup.find_all('article', class_=re.compile(r'MuiCard-root'))
        
        print(f"🔍 تعداد کارت‌های محصول پیدا شده: {len(product_cards)}")
        
        for card in product_cards:
            try:
                # استخراج عنوان محصول
                title_element = card.find('h3', class_=re.compile(r'css-1dd3l3w'))
                if not title_element:
                    # جستجوی جایگزین
                    title_element = card.find('h3', class_=re.compile(r'MuiTypography-gutterBottom'))
                
                title = title_element.text.strip() if title_element else "بدون عنوان"
                
                # استخراج قیمت
                price_element = card.find('p', class_=re.compile(r'css-rfdkzn'))
                price_text = price_element.text.strip() if price_element else ""
                
                # استخراج قیمت اصلی (خط خورده)
                old_price_element = card.find('p', class_=re.compile(r'css-fmw6e5'))
                old_price_text = old_price_element.text.strip() if old_price_element else ""
                
                # استخراج درصد تخفیف
                discount_element = card.find('p', class_=re.compile(r'css-rfdkzn'))
                # اگر المنت تخفیف وجود داشته باشد، معمولاً در یک div با کلاس css-1juktww است
                discount_div = card.find('div', class_=re.compile(r'css-1juktww'))
                if discount_div:
                    discount_text = discount_div.text.strip() if discount_div else ""
                else:
                    discount_text = ""
                
                # استخراج لینک محصول
                link_element = card.find('a', class_='card-link')
                product_url = link_element.get('href', '') if link_element else ""
                
                # استخراج تصویر
                img_element = card.find('img', class_='cardImg')
                img_url = img_element.get('src', '') if img_element else ""
                img_alt = img_element.get('alt', '') if img_element else ""
                
                # پردازش قیمت‌ها (تبدیل به عدد)
                def clean_price(text):
                    if not text:
                        return 0
                    # حذف کاما و تبدیل به عدد
                    cleaned = re.sub(r'[^\d]', '', text)
                    return int(cleaned) if cleaned else 0
                
                product_info = {
                    'id': '',
                    'title': title,
                    'main_price': clean_price(old_price_text) if old_price_text else 0,
                    'off_price': clean_price(price_text) if price_text else 0,
                    'off_percent': clean_price(re.search(r'\d+', discount_text).group()) if discount_text and re.search(r'\d+', discount_text) else 0,
                    'inventory': 0,
                    'store': 'انبار مرکزی اتکالا',
                    'is_exist': True,
                    'product_url': product_url,
                    'image_url': img_url,
                    'extracted_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'HTML'
                }
                
                products_from_html.append(product_info)
            except Exception as e:
                print(f"⚠️ خطا در استخراج یک محصول: {e}")
                continue
        
        # ==========================================
        # ترکیب داده‌ها (اولویت با JSON)
        # ==========================================
        final_products = products_from_json if products_from_json else products_from_html
        
        if final_products:
            # حذف محصولات تکراری بر اساس عنوان
            seen_titles = set()
            unique_products = []
            for product in final_products:
                if product['title'] not in seen_titles:
                    seen_titles.add(product['title'])
                    unique_products.append(product)
            
            # ذخیره در CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_file = f'data2/data_prodouct_{timestamp}.csv'
            
            with open(csv_file, 'w', newline='', encoding='utf-8-sig') as f:
                fieldnames = ['id', 'title', 'main_price', 'off_price', 'off_percent', 
                            'inventory', 'store', 'is_exist', 'extracted_at', 'source']
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(unique_products)
            
            # ذخیره در JSON با اطلاعات کامل‌تر
            json_file = f'data2/data_product_{timestamp}.json'
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'extracted_at': datetime.now().isoformat(),
                    'total_products': len(unique_products),
                    'source': 'JSON' if products_from_json else 'HTML',
                    'products': unique_products
                }, f, ensure_ascii=False, indent=2)
            
            print(f"\n✅ {len(unique_products)} محصول استخراج و ذخیره شد:")
            print(f"   📁 CSV: {csv_file}")
            print(f"   📁 JSON: {json_file}")
            
            # نمایش نمونه محصولات
            print("\n📋 نمونه محصولات استخراج شده:")
            for i, product in enumerate(unique_products[:10], 1):
                print(f"   {i}. {product['title']}")
                print(f"      قیمت: {product.get('off_price', 0):,} ریال")
                if product.get('off_percent', 0) > 0:
                    print(f"      تخفیف: {product['off_percent']}%")
                print()
        else:
            print("⚠️ هیچ محصولی یافت نشد.")
            print("💡 نکات:")
            print("   - محتوای صفحه ممکن است با جاوااسکریپت بارگذاری شده باشد")
            print("   - برای این صفحات بهتر است از Selenium یا Playwright استفاده کنید")
            
    else:
        print(f"❌ خطا در دریافت صفحه. کد وضعیت: {response.status_code}")

except requests.exceptions.Timeout:
    print("❌ زمان درخواست به پایان رسید. اینترنت خود را بررسی کنید.")
except requests.exceptions.ConnectionError:
    print("❌ خطا در اتصال به سرور.")
except Exception as e:
    print(f"❌ خطای غیرمنتظره: {e}")









    