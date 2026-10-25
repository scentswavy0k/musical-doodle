import requests
from bs4 import BeautifulSoup
import json
import csv
import re
import io
import os
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


def extract_value(key):
    """Значение по ключу с допуском экранированных кавычек (\"key\":...)."""
    m = re.search(rf'{key}[\\"\' ]*:[\\"\' ]*([\d.]+)', html_text)
    return m.group(1) if m else None


def extract_livelib_value(key):
    """Значение по ключу только внутри блока livelib_ratings:{...}."""
    pattern = rf'livelib_ratings[\\"\' ]*:[\\"\' ]*\{{[^}}]*?{key}[\\"\' ]*:[\\"\' ]*([\d.]+)'
    m = re.search(pattern, html_text)
    return m.group(1) if m else None


# ---------- Парсинг ----------
rating_value = None
for script in soup.find_all("script", type="application/ld+json"):
    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, TypeError):
        continue
    if data.get("@type") in ["Book", "Product"]:
        rating_value = data.get("aggregateRating", {}).get("ratingValue")
        if rating_value:
            break

reviews_count = to_num(extract_value("reviews_count"))  # отзывы (16)
star_1 = to_num(extract_value("rated_1_count"))
star_2 = to_num(extract_value("rated_2_count"))
star_3 = to_num(extract_value("rated_3_count"))
star_4 = to_num(extract_value("rated_4_count"))
star_5 = to_num(extract_value("rated_5_count"))
rated_avg = to_num(extract_value("rated_avg"))
rated_total = to_num(extract_value("rated_total_count"))

livelib_avg = to_num(extract_value("livelib_rated_avg"))
livelib_total = to_num(extract_value("livelib_rated_count"))
livelib_1 = to_num(extract_livelib_value("rating_1_count"))
livelib_2 = to_num(extract_livelib_value("rating_2_count"))
livelib_3 = to_num(extract_livelib_value("rating_3_count"))
livelib_4 = to_num(extract_livelib_value("rating_4_count"))
livelib_5 = to_num(extract_livelib_value("rating_5_count"))


# ---------- Чтение Gist + накопление ----------
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


def append_to_csv(local_path, header, new_row, gist_id, filename, token):
    existing = fetch_gist_file(gist_id, filename, token) if token and gist_id else ""

    if existing.strip():
        rows = list(csv.reader(io.StringIO(existing)))
        if not rows or rows[0] != header:
            print(f"[INFO] Схема в {filename} не совпадает — файл перезаписан.")
            rows = [header]
    else:
        rows = [header]

    rows.append(new_row)

    with open(local_path, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    print(f"{local_path}: {len(rows) - 1} строк(и), добавлена строка {new_row[0]}")


# ---------- Запись ----------
GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")

header1 = ["datetime", "rating_value", "review_count",
           "1_star", "2_star", "3_star", "4_star", "5_star",
           "rated_avg", "rated_total"]
row1 = [now, rating_value or "", reviews_count,
        star_1, star_2, star_3, star_4, star_5, rated_avg, rated_total]
append_to_csv("data.csv", header1, row1, GIST_ID, "data.csv", GIST_TOKEN)

header2 = ["datetime", "livelib_avg", "livelib_total",
           "1_star", "2_star", "3_star", "4_star", "5_star"]
row2 = [now, livelib_avg, livelib_total,
        livelib_1, livelib_2, livelib_3, livelib_4, livelib_5]
append_to_csv("data2.csv", header2, row2, GIST_ID, "data2.csv", GIST_TOKEN)

print(f"data.csv: rating={rating_value}, reviews={reviews_count}, "
      f"stars=({star_1},{star_2},{star_3},{star_4},{star_5}), "
      f"rated_avg={rated_avg}, rated_total={rated_total}")
print(f"data2.csv (LiveLib): avg={livelib_avg}, total={livelib_total}, "
      f"stars=({livelib_1},{livelib_2},{livelib_3},{livelib_4},{livelib_5})")
