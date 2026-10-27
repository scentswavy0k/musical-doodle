import requests
from bs4 import BeautifulSoup
import json
import csv
import re
import io
import os
from datetime import datetime

url = "https://www.litres.ru/book/73795536/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, "html.parser")
html_text = response.text
today = datetime.utcnow().strftime("%Y-%m-%d")


def to_num(val):
    if val is None:
        return ""
    return float(val) if "." in str(val) else int(val)


def extract_value(key):
    m = re.search(rf'{key}[\\"\' ]*:[\\"\' ]*([\d.]+)', html_text)
    return m.group(1) if m else None


def extract_livelib_value(key):
    pattern = rf'livelib_ratings[\\"\' ]*:[\\"\' ]*\{{[^}}]*?{key}[\\"\' ]*:[\\"\' ]*([\d.]+)'
    m = re.search(pattern, html_text)
    return m.group(1) if m else None


# ---------- 1. JSON-LD: рейтинг и цена ----------
rating_value = None
price_raw = None

for script in soup.find_all("script", type="application/ld+json"):
    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        continue
    if data.get("@type") == "Book":
        rating_value = data.get("aggregateRating", {}).get("ratingValue")
        offers = data.get("offers", {})
        if isinstance(offers, list) and offers:
            offers = offers[0]
        if isinstance(offers, dict):
            price_raw = offers.get("price")
        break

price = to_num(str(price_raw)) if price_raw is not None else ""

# ---------- 2. Детальные данные из встроенного JSON ----------
reviews_count = to_num(extract_value("reviews_count"))
star_1        = to_num(extract_value("rated_1_count"))
star_2        = to_num(extract_value("rated_2_count"))
star_3        = to_num(extract_value("rated_3_count"))
star_4        = to_num(extract_value("rated_4_count"))
star_5        = to_num(extract_value("rated_5_count"))
rated_avg     = to_num(extract_value("rated_avg"))
rated_total   = to_num(extract_value("rated_total_count"))

livelib_avg   = to_num(extract_value("livelib_rated_avg"))
livelib_total = to_num(extract_value("livelib_rated_count"))
livelib_1     = to_num(extract_livelib_value("rating_1_count"))
livelib_2     = to_num(extract_livelib_value("rating_2_count"))
livelib_3     = to_num(extract_livelib_value("rating_3_count"))
livelib_4     = to_num(extract_livelib_value("rating_4_count"))
livelib_5     = to_num(extract_livelib_value("rating_5_count"))


# ---------- 3. Чтение Gist + накопление ----------
def fetch_gist_file(gist_id, filename, token):
    api_url = f"https://api.github.com/gists/{gist_id}"
    r = requests.get(api_url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })
    if r.status_code != 200:
        print(f"[WARN] Не удалось прочитать Gist ({r.status_code}): {r.text[:200]}")
        return ""
    files = r.json().get("files", {})
    return files.get(filename, {}).get("content", "") or ""


def append_or_replace(local_path, header, new_row, gist_id, filename, token):
    existing = fetch_gist_file(gist_id, filename, token) if token and gist_id else ""

    if existing.strip():
        rows = list(csv.reader(io.StringIO(existing)))
        if not rows or rows[0] != header:
            print(f"[INFO] Схема в {filename} не совпадает — файл перезаписан.")
            rows = [header]
    else:
        rows = [header]

    if len(rows) > 1 and rows[-1][0] == new_row[0]:
        rows[-1] = new_row
        print(f"{local_path}: заменена строка за {new_row[0]}")
    else:
        rows.append(new_row)
        print(f"{local_path}: добавлена строка за {new_row[0]} (всего: {len(rows)-1})")

    with open(local_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


# ---------- 4. Запись ----------
GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")

header1 = ["datetime", "price", "review_count",
           "rated_total", "rating_value", "rated_avg",
           "1_star", "2_star", "3_star", "4_star", "5_star"]
row1 = [today, price, reviews_count,
        rated_total, rating_value if rating_value is not None else "", rated_avg,
        star_1, star_2, star_3, star_4, star_5]
append_or_replace("litres.csv", header1, row1, GIST_ID, "litres.csv", GIST_TOKEN)

header2 = ["datetime", "livelib_avg", "livelib_total",
           "1_star", "2_star", "3_star", "4_star", "5_star"]
row2 = [today, livelib_avg, livelib_total,
        livelib_1, livelib_2, livelib_3, livelib_4, livelib_5]
append_or_replace("livelib.csv", header2, row2, GIST_ID, "livelib.csv", GIST_TOKEN)

print(f"litres.csv: {today}, price={price}, reviews={reviews_count}, "
      f"rated_total={rated_total}, rating={rating_value}, rated_avg={rated_avg}, "
      f"stars=({star_1},{star_2},{star_3},{star_4},{star_5})")
print(f"livelib.csv: {today}, avg={livelib_avg}, total={livelib_total}, "
      f"stars=({livelib_1},{livelib_2},{livelib_3},{livelib_4},{livelib_5})")
