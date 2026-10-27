import requests
from bs4 import BeautifulSoup
import json
import csv
import re
import io
import os
import time
from datetime import datetime

LITRES_URL = "https://www.litres.ru/book/edvard-monk/sneg-73795536/"
MYBOOK_URL = "https://mybook.ru/author/edvard-monk/sneg-46/"
BOOKMIX_URL = "https://bookmix.ru/book.phtml?id=4524133"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

today = datetime.utcnow().strftime("%Y-%m-%d")


def to_num(val):
    """Приводит строку/число к int или float; запятую трактует как точку."""
    if val is None:
        return ""
    s = str(val).replace(",", ".").strip()
    if not s:
        return ""
    try:
        return float(s) if "." in s else int(s)
    except ValueError:
        return ""


def fetch(url, timeout=15):
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r


# ============================================================
# LITRES + LIVELIB
# ============================================================
def extract_value(key, text, nested=False):
    prefix = r'livelib_ratings[\\"\' ]*:[\\"\' ]*\{{[^}}]*?' if nested else ''
    m = re.search(rf'{prefix}{key}[\\"\' ]*:[\\"\' ]*([\d.]+)', text)
    return m.group(1) if m else None


def get_litres_data():
    """Парсит страницу Литрес. Возвращает dict с данными + статусами."""
    keys = [
        "price", "review_count", "rated_total", "rating_value", "rated_avg",
        "star_1", "star_2", "star_3", "star_4", "star_5",
        "livelib_avg", "livelib_total",
        "livelib_1", "livelib_2", "livelib_3", "livelib_4", "livelib_5",
    ]
    result = {k: "" for k in keys}
    result["litres_status"] = "REQUEST_ERROR"
    result["livelib_status"] = "REQUEST_ERROR"

    try:
        r = fetch(LITRES_URL)
    except requests.RequestException as e:
        print(f"[WARN] Litres request failed: {e}")
        return result

    soup = BeautifulSoup(r.content, "html.parser")
    text = r.text

    # JSON-LD: rating + price
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

    result["rating_value"] = rating_value if rating_value is not None else ""
    result["price"] = to_num(str(price_raw)) if price_raw is not None else ""
    result["review_count"] = to_num(extract_value("reviews_count", text))
    result["star_1"] = to_num(extract_value("rated_1_count", text))
    result["star_2"] = to_num(extract_value("rated_2_count", text))
    result["star_3"] = to_num(extract_value("rated_3_count", text))
    result["star_4"] = to_num(extract_value("rated_4_count", text))
    result["star_5"] = to_num(extract_value("rated_5_count", text))
    result["rated_avg"] = to_num(extract_value("rated_avg", text))
    result["rated_total"] = to_num(extract_value("rated_total_count", text))

    result["livelib_avg"] = to_num(extract_value("livelib_rated_avg", text))
    result["livelib_total"] = to_num(extract_value("livelib_rated_count", text))
    result["livelib_1"] = to_num(extract_value("rating_1_count", text, nested=True))
    result["livelib_2"] = to_num(extract_value("rating_2_count", text, nested=True))
    result["livelib_3"] = to_num(extract_value("rating_3_count", text, nested=True))
    result["livelib_4"] = to_num(extract_value("rating_4_count", text, nested=True))
    result["livelib_5"] = to_num(extract_value("rating_5_count", text, nested=True))

    result["litres_status"] = "OK" if result["rating_value"] != "" else "PARSE_ERROR"
    result["livelib_status"] = "OK" if result["livelib_avg"] != "" else "PARSE_ERROR"

    return result


lit = get_litres_data()
print(f"Litres: status={lit['litres_status']}")
print(f"LiveLib: status={lit['livelib_status']}")


# ============================================================
# MYBOOK
# ============================================================
MYBOOK_RATING_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*\(\s*(\d+)\s*оценк")


def get_mybook_rating():
    """Возвращает (rating, count, status). При сбое — (0, 0, <причина>)."""
    try:
        r = fetch(MYBOOK_URL)
    except requests.RequestException as e:
        print(f"[WARN] MyBook request failed: {e}")
        return 0, 0, "REQUEST_ERROR"

    text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
    m = MYBOOK_RATING_RE.search(text)
    if not m:
        return 0, 0, "PARSE_ERROR"

    return float(m.group(1).replace(",", ".")), int(m.group(2)), "OK"


mb_rating, mb_count, mb_status = get_mybook_rating()
print(f"MyBook: rating={mb_rating}, count={mb_count}, status={mb_status}")

# ============================================================
# BOOKMIX
# ============================================================
BOOKMIX_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


def bookmix_fetch(url, timeout=20, retries=3, delay=1.0):
    last_err = None
    with requests.Session() as session:
        for attempt in range(1, retries + 1):
            try:
                r = session.get(url, headers=BOOKMIX_HEADERS, timeout=timeout)
                if r.status_code == 200:
                    if not r.encoding:
                        r.encoding = "utf-8"
                    return r.text
                last_err = RuntimeError(f"HTTP {r.status_code} для {url}")
            except requests.RequestException as exc:
                last_err = exc
            time.sleep(delay * attempt)
    raise last_err


def bookmix_num(s):
    """'4.6' -> 4.6; '5.0' -> 5 (int); '0' -> 0; '4,25' -> 4.25."""
    value = float(s.replace(",", "."))
    return int(value) if value.is_integer() else value


def bookmix_parse_rating(soup):
    """
    Рейтинг = «Общая оценка».

    Сначала пробуем текст «Общая оценка (X.X)» — он однозначен.
    Запасной путь — класс starN: N кодирует «целая часть + один знак
    после запятой» (star46 → 4.6, star50 → 5, star05 → 0.5, star0 → 0).
    """
    el = soup.find("div", id=re.compile(r"^ratingunit_long_static\d+$"))
    if not el:
        return None

    # 1) Текст «Общая оценка (X.X)»
    box = el.find_parent("div", class_="book-rating") or el.parent
    if box:
        for h6 in box.find_all("h6"):
            text = h6.get_text(" ", strip=True)
            if "Общая оценка" not in text:
                continue
            span = h6.find("span")
            candidate = span.get_text() if span else text
            m = re.search(r"\d+(?:[.,]\d+)?", candidate)
            if m:
                return bookmix_num(m.group())

    # 2) Запасной путь: класс starN
    for cls in el.get("class", []):
        m = re.fullmatch(r"star(\d+)", cls)
        if not m:
            continue
        digits = m.group(1)
        n = int(digits)
        if len(digits) == 1:          # star0 → 0, star5 → 5
            return n
        return bookmix_num(str(n / 10.0))   # star46 → 4.6, star05 → 0.5
    return None


def bookmix_count_by_onclick(soup, func_name):
    a = soup.find("a", onclick=re.compile(rf"\b{func_name}\b"))
    if a is None:
        return None
    m = re.search(r"\d+", a.get_text() or "")
    return int(m.group()) if m else None


def bookmix_count_from_link_text(a):
    if a is None:
        return None
    m = re.search(r"\((\d+)\)", a.get_text() or "")
    return int(m.group(1)) if m else None


def bookmix_parse_avg(raw):
    """'пока нет' / пусто -> 0; '4.25' -> 4.25; '5' -> 5; '4,5' -> 4.5."""
    if raw is None:
        return 0
    raw = raw.strip()
    if not raw or not re.search(r"\d", raw):
        return 0
    try:
        return bookmix_num(raw)
    except ValueError:
        return 0


def bookmix_parse_section_avg(soup, header_prefix):
    h2 = soup.find("h2", string=re.compile(rf"^{header_prefix}"))
    if not h2:
        return 0
    box = h2.find_next("div", class_="average-grade")
    if not box:
        return 0
    count_el = box.select_one(".count")
    return bookmix_parse_avg(count_el.get_text() if count_el else None)


def bookmix_parse_counters(soup):
    return {
        "reviews": bookmix_count_from_link_text(soup.find("a", id="allreviewslink")),
        "discussions": bookmix_count_from_link_text(
            soup.find("a", href=re.compile(r"^/discussion\.phtml"))
        ),
        "read": bookmix_count_by_onclick(soup, "getwhoreadbybook"),
        "want_to_read": bookmix_count_by_onclick(soup, "getwhowanttoreadbybook"),
    }


def get_bookmix_stats():
    try:
        html = bookmix_fetch(BOOKMIX_URL)
    except Exception as e:
        print(f"[WARN] BookMix request failed: {e}")
        return {
            "reviews": None, "reviews_avg": None,
            "discussions": None, "discussions_avg": None,
            "rating": None, "overall_rating": None,
            "read": None, "want_to_read": None,
            "status": "REQUEST_ERROR",
        }

    soup_bm = BeautifulSoup(html, "html.parser")
    rating = bookmix_parse_rating(soup_bm)

    return {
        **bookmix_parse_counters(soup_bm),
        "reviews_avg": bookmix_parse_section_avg(soup_bm, "Рецензии на книгу"),
        "discussions_avg": bookmix_parse_section_avg(soup_bm, "Отзывы на книгу"),
        "rating": rating,
        "overall_rating": rating,
        "status": "OK" if rating is not None else "PARSE_ERROR",
    }


bm = get_bookmix_stats()
print(f"BookMix: status={bm['status']}, rating={bm['rating']}")

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

REPORTS = [
    (
        "litres.csv",
        ["datetime", "price", "review_count", "rated_total",
         "rating_value", "rated_avg",
         "1_star", "2_star", "3_star", "4_star", "5_star", "status"],
        [today, lit["price"], lit["review_count"], lit["rated_total"],
         lit["rating_value"], lit["rated_avg"],
         lit["star_1"], lit["star_2"], lit["star_3"], lit["star_4"], lit["star_5"],
         lit["litres_status"]],
    ),
    (
        "livelib.csv",
        ["datetime", "livelib_avg", "livelib_total",
         "1_star", "2_star", "3_star", "4_star", "5_star", "status"],
        [today, lit["livelib_avg"], lit["livelib_total"],
         lit["livelib_1"], lit["livelib_2"], lit["livelib_3"],
         lit["livelib_4"], lit["livelib_5"], lit["livelib_status"]],
    ),
    (
        "mybook.csv",
        ["datetime", "rating_value", "rated_total", "status"],
        [today, mb_rating, mb_count, mb_status],
    ),
    (
        "bookmix.csv",
        ["datetime", "reviews", "reviews_avg", "discussions", "discussions_avg",
         "rating", "overall_rating", "read", "want_to_read", "status"],
        [today, bm["reviews"], bm["reviews_avg"],
         bm["discussions"], bm["discussions_avg"],
         bm["rating"], bm["overall_rating"],
         bm["read"], bm["want_to_read"], bm["status"]],
    ),
]

for filename, header, row in REPORTS:
    append_or_replace(filename, header, row, GIST_ID, filename, GIST_TOKEN)
