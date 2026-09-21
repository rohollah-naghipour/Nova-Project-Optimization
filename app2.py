
import pymysql
import pandas as pd
from ortools.linear_solver import pywraplp


def get_connection():
    return pymysql.connect(
        host="localhost",
        port=3306,
        user="root",              
        password="10022001",              
        database="test_nova_DB",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def load_data_from_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    p.id            AS product_id,
                    p.title         AS title,
                    p.category_id   AS category_id,
                    c.name          AS category_name,
                    pr.main_price   AS main_price,
                    pr.off_price    AS off_price
                FROM products p
                JOIN categories c ON c.id = p.category_id
                JOIN prices pr    ON pr.product_id = p.id
                WHERE p.is_exist = 1
                  AND pr.main_price IS NOT NULL
                  AND pr.main_price > 0
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("جدول خالی برگشت. اتصال یا کوئری را بررسی کن.")

    # قیمت نهایی: اگر تخفیف داشت off_price وگرنه main_price
    df["main_price"] = pd.to_numeric(df["main_price"], errors="coerce")
    df["off_price"] = pd.to_numeric(df["off_price"], errors="coerce")
    df["final_price"] = df["off_price"].fillna(df["main_price"])

    df = df.dropna(subset=["final_price"])
    df = df[df["final_price"] > 0]
    df = df.drop_duplicates(subset=["product_id"]).reset_index(drop=True)
    return df


# =====================================================
# ۲) مدل بهینه‌سازی با OR-Tools
# =====================================================
def optimize_basket(
    df,
    budget,
    min_items=5,
    min_per_category=1,
    max_per_category=None,
    prefer_cheap=True,
    time_limit=60,
):
    """
    پارامترها:
    ----------
    df                 : دیتافریم محصولات
    budget             : بودجه (تومان)
    min_items          : حداقل تعداد محصول در سبد
    min_per_category   : حداقل تعداد از هر دسته (برای تنوع)
    max_per_category   : dict {category_id: max} سقف هر دسته
    prefer_cheap       : ترجیح محصولات ارزان‌تر برای جا دادن تعداد بیشتر
    """

    products = df["product_id"].tolist()
    categories = df["category_id"].unique().tolist()
    cat_of = dict(zip(df["product_id"], df["category_id"]))
    price = dict(zip(df["product_id"], df["final_price"]))
    title = dict(zip(df["product_id"], df["title"]))
    cat_name = dict(zip(df["category_id"], df["category_name"]))

    products_in_cat = {
        c: [p for p in products if cat_of[p] == c] for c in categories
    }

    # ---- ساخت solver با SCIP (رایگان و بدون محدودیت) ----
    solver = pywraplp.Solver.CreateSolver("SCIP")
    if not solver:
        raise RuntimeError("SCIP solver در دسترس نیست.")

    solver.SetTimeLimit(time_limit * 1000)  # میلی‌ثانیه

    # ---- متغیر تصمیم: x[i] باینری ----
    x = {p: solver.BoolVar(f"x_{p}") for p in products}

    # ---- قید بودجه ----
    solver.Add(
        solver.Sum(price[p] * x[p] for p in products) <= budget
    )

    # ---- حداقل تعداد کل ----
    solver.Add(solver.Sum(x[p] for p in products) >= min_items)

    # ---- کف هر دسته (اجبار حضور برای تنوع) ----
    if min_per_category:
        for c in categories:
            if products_in_cat[c]:
                solver.Add(
                    solver.Sum(x[p] for p in products_in_cat[c]) >= min_per_category
                )

    # ---- سقف هر دسته ----
    if max_per_category:
        for c, cap in max_per_category.items():
            if c in categories and products_in_cat[c]:
                solver.Add(
                    solver.Sum(x[p] for p in products_in_cat[c]) <= cap
                )

    # =====================================================
    # تابع هدف: تنوع + ترجیح ارزان‌ترها
    # =====================================================
    # برای تنوع: به هر دسته یک پاداش تشویقی می‌دیم که با تعداد اعضاش رشد کنه
    # این کار خطی می‌مونه و محدودیت لایسنس هم نداره
    objective_terms = []

    # ۱) پاداش برای هر محصول انتخاب‌شده (ترجیح ارزان‌ترها → وزن بیشتر)
    max_p = float(max(price.values()))
    for p in products:
        if prefer_cheap:
            weight = (max_p - price[p]) / max_p + 0.01
        else:
            weight = 1.0
        objective_terms.append(weight * x[p])

    # ۲) پاداش اضافی برای تنوع: هر محصول از یک دسته، بونوس کوچیک
    for c in categories:
        for p in products_in_cat[c]:
            objective_terms.append(0.001 * x[p])

    solver.Maximize(solver.Sum(objective_terms))

    # ---- حل ----
    print("\n⏳ در حال حل مدل...")
    status = solver.Solve()

    # =====================================================
    # استخراج جواب
    # =====================================================
    if status in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        selected = [p for p in products if x[p].solution_value() > 0.5]
        result = df[df["product_id"].isin(selected)].copy()
        result = result.sort_values(["category_name", "final_price"])

        total_cost = int(result["final_price"].sum())
        n_selected = len(result)
        n_cats = result["category_id"].nunique()

        status_txt = "بهینه" if status == pywraplp.Solver.OPTIMAL else "قابل قبول (سقف زمان)"

        print("\n" + "=" * 65)
        print(f"وضعیت حل        : {status_txt}")
        print(f"بودجه           : {budget:,} تومان")
        print(f"هزینه سبد       : {total_cost:,} تومان")
        print(f"باقیمانده       : {budget - total_cost:,} تومان")
        print(f"تعداد محصولات   : {n_selected}")
        print(f"دسته‌های پوشش‌داده: {n_cats} از {len(categories)}")
        print("=" * 65)

        dist = (
            result.groupby("category_name")
            .agg(تعداد=("product_id", "count"),
                 هزینه=("final_price", "sum"))
            .sort_values("تعداد", ascending=False)
        )
        print("\nتوزیع دسته‌ها:")
        print(dist.to_string())

        print("\nمحصولات انتخابی:")
        for _, row in result.iterrows():
            print(
                f"  [{str(row['category_name'])[:18]:<18}] "
                f"{str(row['title'])[:55]:<55} "
                f"{int(row['final_price']):>10,} تومان"
            )

        return result
    else:
        print("❌ جوابی یافت نشد. کد وضعیت:", status)
        print("   احتمالاً بودجه خیلی کم است یا قیدها ناسازگارند.")
        return None


# =====================================================
# ۳) اجرا
# =====================================================
def parse_budget(text):
    """ورودی بودجه رو با کاما یا فاصله هم قبول می‌کنه."""
    text = text.replace(",", "").replace("،", "").replace(" ", "").strip()
    return int(text)


if __name__ == "__main__":
    df = load_data_from_db()

    print("=" * 65)
    print("🛒 بهینه‌ساز سبد خرید متنوع")
    print("=" * 65)
    print(f"تعداد محصولات : {len(df):,}")
    print(f"تعداد دسته‌ها  : {df['category_id'].nunique()}")
    print(f"محدوده قیمت   : {df['final_price'].min():,.0f} تا "
          f"{df['final_price'].max():,.0f} تومان")
    print("=" * 65)

    # ---- گرفتن بودجه از ورودی ----
    while True:
        try:
            raw = input("\n💰 بودجه را به تومان وارد کنید (0 = خروج): ")
            budget = parse_budget(raw)
            if budget <= 0:
                print("خداحافظ!")
                break

            # تنظیم کف و سقف هر دسته بر اساس بودجه
            cats = df["category_id"].unique().tolist()

            # حداقل ۱ قلم از هر دسته (برای تنوع)
            min_per_cat = 1

            # حداکثر: متناسب با بودجه، اجازه‌ی چند قلم از هر دسته
            # (مثلاً ۱۰ قلم سقف، ولی نه بیشتر از کل بودجه تقسیم بر ارزان‌ترین)
            max_per_cat = {c: 8 for c in cats}

            basket = optimize_basket(
                df,
                budget=budget,
                min_items=5,
                min_per_category=min_per_cat,
                max_per_category=max_per_cat,
                prefer_cheap=True,
                time_limit=60,
            )

            # ---- ذخیره خروجی ----
            if basket is not None:
                out_file = f"basket_{budget}.csv"
                basket[["product_id", "title", "category_name", "final_price"]] \
                    .to_csv(out_file, index=False, encoding="utf-8-sig")
                print(f"\n✅ نتیجه در فایل «{out_file}» ذخیره شد.")

        except ValueError:
            print("⚠️ عدد معتبر وارد کن (مثلاً 2000000 یا 2,000,000).")
        except KeyboardInterrupt:
            print("\nخداحافظ!")
            break