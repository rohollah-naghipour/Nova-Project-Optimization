import pandas as pd
import pulp as pl
import re
from datetime import datetime

# ============================================
# 1. بارگذاری و پردازش داده
# ============================================

CATEGORY_RULES = {
    'پودر ژله': ['پودرژله', 'پودر ژله', 'پودرکرم'],
    'روغن': ['روغن'],
    'کره بادام زمینی': ['کره بادام', 'بادام زمینی'],
    'تن ماهی': ['تن ماهی'],
    'چای': ['چای'],
    'سس': ['سس', 'کچاپ'],
    'کنسرو': ['کنسرو'],
    'نمک': ['نمک'],
    'شکلات': ['شکلات'],
    'نوشیدنی': ['دوغ', 'بستنی'],
    'پنیر': ['پنیر'],
    'سوسیس و کالباس': ['سوسیس', 'همبرگر', 'ژامبون'],
    'میگو': ['میگو'],
    'مرغ': ['مرغ'],
    'برنج': ['برنج'],
    'شکر': ['شکر'],
    'دستمال و کیسه': ['دستمال', 'کیسه فریزر'],
    'نوار بهداشتی': ['نواربهداشتی', 'نوار بهداشتی'],
    'محصولات آرایشی': ['کرم', 'ژل', 'دئودورانت', 'استیک'],
    'مواد شوینده': ['مایع ظرفشویی', 'پودر لباسشویی', 'مایع لباسشویی'],
    'اسنک': ['چیپس', 'کرانچی', 'پاپ کرن', 'کراکر', 'اسنک'],
    'ادویه': ['فلفل'],
    'رب': ['رب'],
    'سویا': ['سویا']
}

def load_and_categorize(file_path):
    df = pd.read_csv(file_path)
    df['off_price'] = df['off_price'].astype(float)
    
    def extract_quantity(title):
        patterns = [
            r'(\d+(?:\.\d+)?)\s*(گرم|کیلو|کیلوگرم|عددی|برگ|میل|سی سی|لیتر|ک)',
            r'(\d+(?:\.\d+)?)\s*گرمی',
            r'(\d+(?:\.\d+)?)\s*عددی'
        ]
        for pattern in patterns:
            match = re.search(pattern, title)
            if match:
                value = float(match.group(1))
                unit = match.group(2) if len(match.groups()) > 1 else 'گرم'
                if unit in ['کیلو', 'کیلوگرم']:
                    return value * 1000
                elif unit in ['لیتر', 'ک']:
                    return value * 1000
                else:
                    return value
        return None
    
    df['quantity'] = df['title'].apply(extract_quantity)
    df = df[df['quantity'].notna()].copy()
    
    def assign_category(title):
        for cat, keywords in CATEGORY_RULES.items():
            for keyword in keywords:
                if keyword in title:
                    return cat
        return 'سایر'
    
    df['category'] = df['title'].apply(assign_category)
    return df

# ============================================
# 2. دریافت ورودی از کاربر
# ============================================

def get_user_input(categories):
    print("\n" + "="*60)
    print("🛒 سیستم بهینه‌سازی خرید - اتکالا")
    print("="*60)
    
    while True:
        try:
            budget_input = input("\n💰 لطفاً بودجهٔ خود را به تومان وارد کنید (مثال: 50000000): ")
            budget = float(budget_input.replace(',', '').strip())
            if budget <= 0:
                print("❌ بودجه باید بزرگتر از صفر باشد!")
                continue
            break
        except ValueError:
            print("❌ لطفاً یک عدد معتبر وارد کنید!")
    
    print("\n📋 حالا نیازمندی‌های خود را وارد کنید.")
    print("(برای هر دسته، حداقل مقداری که نیاز دارید را وارد کنید)")
    print("✏️ اگر نیازی ندارید، عدد 0 را وارد کنید")
    print("-"*50)
    
    required = {}
    for cat in categories:
        while True:
            try:
                qty_input = input(f"  {cat}: ")
                qty = float(qty_input.replace(',', '').strip())
                if qty < 0:
                    print("❌ مقدار نمی‌تواند منفی باشد!")
                    continue
                if qty > 0:
                    required[cat] = qty
                break
            except ValueError:
                print("❌ لطفاً یک عدد معتبر وارد کنید!")
    
    return budget, required

# ============================================
# 3. تابع بهینه‌سازی با خروجی انگلیسی
# ============================================

def optimize_shopping_budget(df, budget, required_categories, output_file='shopping_list.txt'):
    prob = pl.LpProblem("Budget_Grocery", pl.LpMaximize)
    
    buy_vars = {}
    all_products = []
    
    for idx, row in df.iterrows():
        var_name = f"{row['category']}_{row['id']}"
        max_qty = min(row['inventory'], 20) if row['inventory'] > 0 else 20
        buy_vars[var_name] = pl.LpVariable(var_name, lowBound=0, upBound=max_qty, cat='Integer')
        all_products.append((var_name, row))
        prob += buy_vars[var_name] * row['quantity']
    
    prob += pl.lpSum([buy_vars[var_name] * row['off_price'] 
                      for var_name, row in all_products]) <= budget
    
    for category, min_qty in required_categories.items():
        cat_products = [(var_name, row) for var_name, row in all_products 
                       if row['category'] == category]
        if cat_products:
            prob += pl.lpSum([buy_vars[var_name] * row['quantity'] 
                             for var_name, row in cat_products]) >= min_qty
        else:
            print(f"⚠️ دسته '{category}' در دیتا موجود نیست")
    
    prob.solve(pl.PULP_CBC_CMD(msg=False))
    
    result = {
        'status': pl.LpStatus[prob.status],
        'total_cost': 0,
        'total_quantity': 0,
        'items': []
    }
    
    if prob.status == 1:
        for var_name, row in all_products:
            var = buy_vars[var_name]
            qty = int(var.varValue) if var.varValue > 0 else 0
            if qty > 0:
                cost = qty * row['off_price']
                total_qty = qty * row['quantity']
                
                result['items'].append({
                    'title': row['title'],
                    'category': row['category'],
                    'quantity': qty,
                    'unit_qty': row['quantity'],
                    'unit_price': row['off_price'],
                    'total_cost': cost,
                    'total_qty': total_qty,
                    'inventory': row['inventory']
                })
                result['total_cost'] += cost
                result['total_quantity'] += total_qty
    
    # ============================================
    # ذخیره در فایل با فرمت انگلیسی
    # ============================================
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("🛒 OPTIMIZED SHOPPING LIST - Etkala\n")
        f.write(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*80 + "\n\n")
        
        f.write(f"💰 Budget: {budget:,.0f} Toman\n")
        f.write(f"📊 Status: {result['status']}\n")
        
        if result['status'] == 'Optimal':
            f.write(f"✅ Total Cost: {result['total_cost']:,.0f} Toman\n")
            f.write(f"📦 Total Quantity (Weight/Count): {result['total_quantity']:,.0f}\n")
            f.write(f"💡 Remaining Balance: {budget - result['total_cost']:,.0f} Toman\n\n")
            
            f.write("-"*80 + "\n")
            f.write("📋 Shopping Items by Category:\n")
            f.write("-"*80 + "\n\n")
            
            items_by_cat = {}
            for item in result['items']:
                cat = item['category']
                if cat not in items_by_cat:
                    items_by_cat[cat] = []
                items_by_cat[cat].append(item)
            
            # ترجمه دسته‌بندی‌ها به انگلیسی
            category_translation = {
                'پودر ژله': 'Jelly Powder',
                'روغن': 'Oil',
                'کره بادام زمینی': 'Peanut Butter',
                'تن ماهی': 'Tuna',
                'چای': 'Tea',
                'سس': 'Sauce',
                'کنسرو': 'Canned Food',
                'نمک': 'Salt',
                'شکلات': 'Chocolate',
                'نوشیدنی': 'Beverages',
                'پنیر': 'Cheese',
                'سوسیس و کالباس': 'Sausage & Ham',
                'میگو': 'Shrimp',
                'مرغ': 'Chicken',
                'برنج': 'Rice',
                'شکر': 'Sugar',
                'دستمال و کیسه': 'Tissue & Bags',
                'نوار بهداشتی': 'Sanitary Pads',
                'محصولات آرایشی': 'Cosmetics',
                'مواد شوینده': 'Detergents',
                'اسنک': 'Snacks',
                'ادویه': 'Spices',
                'رب': 'Tomato Paste',
                'سویا': 'Soy Protein',
                'سایر': 'Other'
            }
            
            for category, items in sorted(items_by_cat.items()):
                cat_en = category_translation.get(category, category)
                f.write(f"\n🔹 {cat_en} ({category})\n")
                f.write("─"*50 + "\n")
                for item in items:
                    f.write(f"  • {item['title']}\n")
                    f.write(f"    Quantity: {item['quantity']} pack(s)\n")
                    f.write(f"    Unit Weight/Count: {item['unit_qty']} units\n")
                    f.write(f"    Unit Price: {item['unit_price']:,.0f} Toman\n")
                    f.write(f"    Total Price: {item['total_cost']:,.0f} Toman\n")
                    f.write(f"    Inventory: {item['inventory']} units\n\n")
            
            f.write("-"*80 + "\n")
            f.write(f"📊 Total Items: {len(result['items'])} products\n")
            f.write(f"💰 Final Cost: {result['total_cost']:,.0f} Toman\n")
            f.write(f"📦 Total Weight/Count: {result['total_quantity']:,.0f} units\n")
        else:
            f.write("❌ Problem is infeasible!\n")
            f.write("Suggestion: Increase your budget or reduce requirements.\n")
        
        f.write("\n" + "="*80 + "\n")
        f.write("✨ Optimized using PuLP library (Linear Programming).\n")
        f.write(f"🔗 Source: Etkala - {datetime.now().strftime('%Y-%m-%d')}\n")
    
    return result

# ============================================
# 4. اجرا
# ============================================

if __name__ == "__main__":
    df = load_and_categorize('etkala_products_20260816_112618.csv')
    print(f"✅ {len(df)} محصول بارگذاری و دسته‌بندی شد.")
    
    categories = sorted(df['category'].unique())
    print("\n📋 دسته‌های موجود برای خرید:")
    for cat in categories:
        print(f"  • {cat}")
    
    BUDGET, required = get_user_input(categories)
    
    if not required:
        print("\n⚠️ هیچ نیازمندی وارد نشد! لطفاً حداقل یک دسته را مشخص کنید.")
    else:
        print(f"\n💰 شروع بهینه‌سازی با بودجهٔ {BUDGET:,.0f} تومان...")
        print("📋 نیازمندی‌های شما:")
        for cat, qty in required.items():
            print(f"  • {cat}: {qty:,.0f} واحد")
        
        result = optimize_shopping_budget(df, BUDGET, required, 'shopping_list_optimized.txt')
        
        print(f"\n✅ بهینه‌سازی کامل شد!")
        print(f"📄 خروجی در فایل 'shopping_list_optimized.txt' ذخیره شد.")
        
        if result['status'] == 'Optimal':
            print(f"\n📊 خلاصه:")
            print(f"  • هزینهٔ کل: {result['total_cost']:,.0f} تومان")
            print(f"  • تعداد اقلام: {len(result['items'])}")
            print(f"  • مبلغ باقی‌مانده: {BUDGET - result['total_cost']:,.0f} تومان")
        else:
            print("\n❌ مسئله قابل حل نیست! بودجه را افزایش دهید.")