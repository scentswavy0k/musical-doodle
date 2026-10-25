import requests
from bs4 import BeautifulSoup
import json
import csv
import re
from datetime import datetime

url = "https://www.litres.com/book/edvard-monk/sneg-73795536/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, "html.parser")
html_text = response.text

# --- 1. Агрегированные данные из JSON-LD (средний рейтинг и общее число) ---
rating_value = None
review_count = None

for script in soup.find_all("script", type="application/ld+json"):
    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        continue
    if data.get("@type") in ["Book", "Product"]:
        aggregate_rating = data.get("aggregateRating", {})
        rating_value = aggregate_rating.get("ratingValue")
        review_count = aggregate_rating.get("reviewCount")
        if review_count:
            break

# --- 2. Детальная разбивка по звёздам из встроенного JSON ---
# Ключи вида rated_N_count встречаются только в сериализованных данных Next.js,
# где кавычки экранированы как \" — поэтому допускаем любые комбинации
# кавычек, обратных слэшей и пробелов вокруг двоеточия.

def extract_value(key):
    """Находит значение по ключу, допуская экранированные/неэкранированные кавычки."""
    m = re.search(rf'{key}[\\"\' ]*:[\\"\' ]*([\d.]+)', html_text)
    return m.group(1) if m else None

def to_num(val):
    if val is None:
        return ""
    return float(val) if "." in val else int(val)

star_1 = to_num(extract_value("rated_1_count"))
star_2 = to_num(extract_value("rated_2_count"))
star_3 = to_num(extract_value("rated_3_count"))
star_4 = to_num(extract_value("rated_4_count"))
star_5 = to_num(extract_value("rated_5_count"))
rated_avg = to_num(extract_value("rated_avg"))
rated_total = to_num(extract_value("rated_total_count"))

# Диагностика: если разбивка не нашлась, покажем кусочек ответа вокруг ключа
if star_1 == "":
    idx = html_text.find("rated_1_count")
    if idx >= 0:
        print(f"[DEBUG] 'rated_1_count' найден на позиции {idx}, контекст: "
              f"{html_text[max(0, idx-40):idx+80]!r}")
    else:
        print("[DEBUG] 'rated_1_count' вообще не найден в ответе")

# --- 3. Запись в CSV ---
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

with open("data.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "datetime",
        "rating_value", "review_count",
        "1_star", "2_star", "3_star", "4_star", "5_star",
        "rated_avg", "rated_total"
    ])
    writer.writerow([
        now,
        rating_value if rating_value is not None else "",
        review_count if review_count is not None else "",
        star_1, star_2, star_3, star_4, star_5,
        rated_avg, rated_total
    ])

print(f"Сохранено: avg={rating_value}, count={review_count}, "
      f"stars=({star_1},{star_2},{star_3},{star_4},{star_5}), "
      f"rated_avg={rated_avg}, total={rated_total}")
