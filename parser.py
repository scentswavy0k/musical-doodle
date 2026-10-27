import requests
from bs4 import BeautifulSoup
import json
import csv
import re
import io
import os
from datetime import datetime

LITRES_URL = "https://www.litres.ru/book/edvard-monk/sneg-73795536/"
MYBOOK_URL = "https://mybook.ru/author/edvard-monk/sneg-46/"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

today = datetime.utcnow().strftime("%Y-%m-%d")


def to_num(val):
    if val is None:
        return ""
    return float(val) if "." in str(val) else int(val)


def fetch(url):
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r


# ============================================================
# LITRES
# ============================================================
litres_resp = fetch(LITRES_URL)
litres_soup = BeautifulSoup(litres_resp.content, "html.parser")
litres_text = litres_resp.text


def extract_value(key, text):
    m = re.search(rf'{key}[\\"\' ]*:[\\"\' ]*([\d.]+)', text)
    return m.group(1) if m else None


def extract_livelib_value(key, text):
    pattern = rf'livelib_ratings[\\"\' ]*:[\\"\' ]*\{{[^}}]*?{key}[\\"\' ]*:[\\"\' ]*([\d.]+)'
    m = re.search(pattern, text)
    return m.group(1) if m else None


rating_value = None
price_raw = None
for script in litres_soup.find_all("script", type="application/ld+json"):
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

reviews_count = to_num(extract_value("reviews_count", litres_text))
star_1 = to_num(extract_value("rated_1_count", litres_text))
star_2 = to_num(extract_value("rated_2_count", litres_text))
star_3 = to_num(extract_value("rated_3_count", litres_text))
star_4 = to_num(extract_value("rated_4_count", litres_text))
star_5 = to_num(extract_value("rated_5_count", litres_text))
rated_avg = to_num(extract_value("rated_avg", litres_text))
rated_total = to_num(extract_value("rated_total_count", litres_text))

livelib_avg = to_num(extract_value("livelib_rated_avg", litres_text))
livelib_total = to_num(extract_value("livelib_rated_count", litres_text))
livelib_1 = to_num(extract_livelib_value("rating_1_count", litres_text))
livelib_2 = to_num(extract_livelib_value("rating_2_count", litres_text))
livelib_3 = to_num(extract_livelib_value("rating_3_count", litres_text))
livelib_4 = to_num(extract_livelib_value("rating_4_count", litres_text))
livelib_5 = to_num(extract_livelib_value("rating_5_count", litres_text))


# ============================================================
# MYBOOK — три стратегии, как в вашем скрипте
# ============================================================
def mybook_from_json_ld(soup):
    """Стратегия 1: schema.org aggregateRating."""
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in (data if isinstance(data, list) else [data]):
            ar = obj.get("aggregateRating") if isinstance(obj, dict) else None
            if not ar:
                continue
            try:
                rating = float(ar["ratingValue"])
                count = int(ar.get("ratingCount") or ar.get("reviewCount"))
                return rating, count
            except (KeyError, TypeError, ValueError):
                continue
    return None, None


def mybook_from_text(soup):
    """Стратегия 2: '5 (2 оценки)' в видимом тексте."""
    text = soup.get_text(" ", strip=True)
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*\(\s*(\d+)\s*оценк", text)
    if m:
        return float(m.group(1).replace(",", ".")), int(m.group(2))
    m = re.search(r"(\d+)\s*оценк", text)
    count = int(m.group(1)) if m else None
    return None, count


def mybook_from_star(soup):
    """Стратегия 3: звезда 16×16 → ближайший <b> с числом."""
    star = soup.find("svg", attrs={"viewBox": "0 0 16 16"})
    if not star:
        return None
    b = star.find_next("b")
    if not b:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", b.get_text())
    return float(m.group().replace(",", ".")) if m else None


def get_mybook_rating():
    r = fetch(MYBOOK_URL)
    soup_mb = BeautifulSoup(r.text, "html.parser")
    rating, count = mybook_from_json_ld(soup_mb)
    if rating is None:
        rating, count2 = mybook_from_text(soup_mb)
        count = count or count2
    if rating is None:
        rating = mybook_from_star(soup_mb)
    return rating, count


# MyBook не должен ломать весь workflow — оборачиваем в try/except
try:
    mb_rating, mb_count = get_mybook_rating()
    print(f"MyBook: rating={mb_rating}, count={mb_count}")
except Exception as e:
    print(f"[WARN] MyBook parsing failed: {e}")
    mb_rating, mb_count = None, None


# ============================================================
# Запись в Gist-накопители
# ============================================================
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


GIST_TOKEN = os.environ.get("GIST_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "")

# litres.csv
header1 = ["datetime", "price", "review_count",
           "rated_total", "rating_value", "rated_avg",
           "1_star", "2_star", "3_star", "4_star", "5_star"]
row1 = [today, price, reviews_count,
        rated_total, rating_value if rating_value is not None else "", rated_avg,
        star_1, star_2, star_3, star_4, star_5]
append_or_replace("litres.csv", header1, row1, GIST_ID, "litres.csv", GIST_TOKEN)

# livelib.csv
header2 = ["datetime", "livelib_avg", "livelib_total",
           "1_star", "2_star", "3_star", "4_star", "5_star"]
row2 = [today, livelib_avg, livelib_total,
        livelib_1, livelib_2, livelib_3, livelib_4, livelib_5]
append_or_replace("livelib.csv", header2, row2, GIST_ID, "livelib.csv", GIST_TOKEN)

# mybook.csv
header3 = ["datetime", "rating_value", "rated_total"]
row3 = [today,
        mb_rating if mb_rating is not None else "",
        mb_count if mb_count is not None else ""]
append_or_replace("mybook.csv", header3, row3, GIST_ID, "mybook.csv", GIST_TOKEN)

print(f"litres.csv: {today}, price={price}, reviews={reviews_count}, "
      f"rated_total={rated_total}, rating={rating_value}, rated_avg={rated_avg}, "
      f"stars=({star_1},{star_2},{star_3},{star_4},{star_5})")
print(f"livelib.csv: {today}, avg={livelib_avg}, total={livelib_total}, "
      f"stars=({livelib_1},{livelib_2},{livelib_3},{livelib_4},{livelib_5})")
print(f"mybook.csv: {today}, rating={mb_rating}, count={mb_count}")
