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

now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

def to_num(val):
    if val is None:
        return ""
    return float(val) if "." in val else int(val)

# ---------- 1. Основной рейтинг Литрес ----------
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

def extract_value(key):
    """Значение по ключу с допуском экранированных кавычек (\"key\":...)."""
    m = re.search(rf'{key}[\\"\' ]*:[\\"\' ]*([\d.]+)', html_text)
    return m.group(1) if m else None

star_1 = to_num(extract_value("rated_1_count"))
star_2 = to_num(extract_value("rated_2_count"))
star_3 = to_num(extract_value("rated_3_count"))
star_4 = to_num(extract_value("rated_4_count"))
star_5 = to_num(extract_value("rated_5_count"))
rated_avg = to_num(extract_value("rated_avg"))
rated_total = to_num(extract_value("rated_total_count"))

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

print(f"data.csv: avg={rating_value}, count={review_count}, "
      f"stars=({star_1},{star_2},{star_3},{star_4},{star_5}), "
      f"rated_avg={rated_avg}, total={rated_total}")

# ---------- 2. Рейтинг LiveLib ----------
def extract_livelib_value(key):
    """
    Ищет значение по ключу ТОЛЬКО внутри блока livelib_ratings:{...}.
    Это защищает от путаницы с rated_N_count основного рейтинга.
    """
    pattern = rf'livelib_ratings[\\"\' ]*:[\\"\' ]*\{{[^}}]*?{key}[\\"\' ]*:[\\"\' ]*([\d.]+)'
    m = re.search(pattern, html_text)
    return m.group(1) if m else None

# Эти два ключа уникальны, но для единообразия используем тот же стиль
livelib_avg = to_num(extract_value("livelib_rated_avg"))
livelib_total = to_num(extract_value("livelib_rated_count"))

livelib_1 = to_num(extract_livelib_value("rating_1_count"))
livelib_2 = to_num(extract_livelib_value("rating_2_count"))
livelib_3 = to_num(extract_livelib_value("rating_3_count"))
livelib_4 = to_num(extract_livelib_value("rating_4_count"))
livelib_5 = to_num(extract_livelib_value("rating_5_count"))

# Диагностика
if livelib_total == "":
    idx = html_text.find("livelib_rated_count")
    if idx >= 0:
        print(f"[DEBUG] livelib_rated_count найден на позиции {idx}: "
              f"{html_text[max(0, idx-40):idx+120]!r}")
    else:
        print("[DEBUG] livelib_rated_count не найден в ответе")

with open("data2.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "datetime",
        "livelib_avg", "livelib_total",
        "1_star", "2_star", "3_star", "4_star", "5_star"
    ])
    writer.writerow([
        now,
        livelib_avg, livelib_total,
        livelib_1, livelib_2, livelib_3, livelib_4, livelib_5
    ])

print(f"data2.csv (LiveLib): avg={livelib_avg}, total={livelib_total}, "
      f"stars=({livelib_1},{livelib_2},{livelib_3},{livelib_4},{livelib_5})")
