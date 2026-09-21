"""
بارگذاری فایل‌های JSON اتکالا در MariaDB
"""

import json
from pathlib import Path
from datetime import datetime

import pymysql
from pymysql.cursors import DictCursor


# ═══════════════════════════════════════════════
# تنظیمات — بدون واسطه
# ═══════════════════════════════════════════════
HOST = "localhost"
USER = "root"
PASSWORD = "************"
DATABASE = "test_nova_DB"

DATASETS_DIR = Path("etkala_datasets")


# ═══════════════════════════════════════════════
# اتصال
# ═══════════════════════════════════════════════
def connect():
    print(f"🔌 اتصال: {USER}@{HOST}/{DATABASE}")
    return pymysql.connect(
        host=HOST,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
        charset="utf8mb4",
        cursorclass=DictCursor,
    )


# ═══════════════════════════════════════════════
# ساخت جداول
# ═══════════════════════════════════════════════
def create_tables(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_persian_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                category_id INT NOT NULL,
                url TEXT,
                store VARCHAR(255),
                is_exist TINYINT(1) DEFAULT 1,
                source VARCHAR(100),
                created_at DATETIME,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
                INDEX idx_products_category (category_id),
                INDEX idx_products_title (title(191))
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_persian_ci
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                main_price BIGINT,
                off_price BIGINT,
                off_percent TINYINT,
                extracted_at DATETIME,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
                INDEX idx_prices_product (product_id),
                INDEX idx_prices_extracted (extracted_at),
                INDEX idx_prices_off (off_percent)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_persian_ci
        """)

    conn.commit()
    print("✅ جداول ساخته/بررسی شدند.")


# ═══════════════════════════════════════════════
# دسته‌بندی
# ═══════════════════════════════════════════════
def get_or_create_category(conn, name):
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM categories WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("INSERT INTO categories (name) VALUES (%s)", (name,))
        conn.commit()
        return cur.lastrowid


# ═══════════════════════════════════════════════
# تاریخ
# ═══════════════════════════════════════════════
def to_mysql_datetime(s):
    if not s:
        return None
    try:
        dt = datetime.strptime(str(s), "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ═══════════════════════════════════════════════
# درج محصول + قیمت
# ═══════════════════════════════════════════════
def insert_product(conn, prod, category_id):
    pid = prod["id"]
    title = prod["title"] or ""
    url = prod.get("url") or ""
    store = prod.get("store") or ""
    is_exist = 1 if prod.get("is_exist") else 0
    source = prod.get("source") or "etkala.ir"
    created_at = to_mysql_datetime(prod.get("extracted_at"))

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO products
              (id, title, category_id, url, store, is_exist, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              title = VALUES(title),
              category_id = VALUES(category_id),
              url = VALUES(url),
              store = VALUES(store),
              is_exist = VALUES(is_exist),
              source = VALUES(source)
        """, (pid, title, category_id, url, store, is_exist, source, created_at))

        cur.execute("""
            INSERT INTO prices
              (product_id, main_price, off_price, off_percent, extracted_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            pid,
            prod.get("main_price"),
            prod.get("off_price"),
            prod.get("off_percent"),
            created_at,
        ))

    conn.commit()


# ═══════════════════════════════════════════════
# پردازش فایل JSON
# ═══════════════════════════════════════════════
def process_json_file(conn, json_path):
    print(f"\n📂 پردازش: {json_path.name}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    category_name = data.get("category_name") or json_path.stem
    products = data.get("products", [])

    if not products:
        print("  ⚠️ فایل خالیه.")
        return 0

    category_id = get_or_create_category(conn, category_name)
    print(f"  دسته: {category_name} (id={category_id})")

    count = 0
    errors = 0
    for prod in products:
        try:
            insert_product(conn, prod, category_id)
            count += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  ❌ خطا در محصول {prod.get('id')}: {e}")

    print(f"  ✓ {count} محصول درج/آپدیت شد. (خطا: {errors})")
    return count


# ═══════════════════════════════════════════════
# اجرا
# ═══════════════════════════════════════════════
def main():
    print(f"📁 پوشه دیتاست: {DATASETS_DIR.resolve()}")

    if not DATASETS_DIR.exists():
        print(f"❌ پوشه پیدا نشد: {DATASETS_DIR.resolve()}")
        return

    json_files = sorted(DATASETS_DIR.glob("*.json"))
    json_files = [f for f in json_files if not f.name.startswith("_")]

    if not json_files:
        print(f"⚠️ هیچ فایل JSON توی {DATASETS_DIR.resolve()} پیدا نشد.")
        print("   محتویات پوشه:")
        for f in DATASETS_DIR.iterdir():
            print(f"     - {f.name}")
        return

    print(f"🔍 {len(json_files)} فایل JSON پیدا شد:")
    for f in json_files:
        print(f"   • {f.name}")

    conn = connect()
    try:
        create_tables(conn)

        total = 0
        for jf in json_files:
            total += process_json_file(conn, jf)

        print(f"\n{'='*60}")
        print(f"🎯 مجموع: {total} محصول پردازش شد.")

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM categories")
            n_cat = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM products")
            n_prod = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM prices")
            n_price = cur.fetchone()["n"]

        print(f"\n📊 آمار دیتابیس {DATABASE}:")
        print(f"   • دسته‌بندی‌ها: {n_cat}")
        print(f"   • محصولات:    {n_prod}")
        print(f"   • قیمت‌ها:     {n_price}")

    finally:
        conn.close()



if __name__ == "__main__":
    main()