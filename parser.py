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

# --- 1. Агрегированные данные из JSON-LD (средний рейтинг и общее число) ---
rating_value = None
review_count = None

for script in soup.find_all("script", type="application/ld+json"):
    data = json.loads(script.string)
    if data.get("@type") in ["Book", "Product"]:
        aggregate_rating = data.get("aggregateRating", {})
        rating_value = aggregate_rating.get("ratingValue")
        review_count = aggregate_rating.get("reviewCount")
        if review_count:
            break

# --- 2. Детальная разбивка по звёздам из встроенного JSON ---
# Ищем объект вида: "rating":{"user_rating":null,"rated_1_count":0,...}
pattern = (
    r'"rating":\{"user_rating":(?:null|\d+),'
    r'"rated_1_count":(\d+),'
    r'"rated_2_count":(\d+),'
    r'"rated_3_count":(\d+),'
    r'"rated_4_count":(\d+),'
    r'"rated_5_count":(\d+),'
    r'"rated_avg":([\d.]+),'
    r'"rated_total_count":(\d+)\}'
)
match = re.search(pattern, response.text)

if match:
    star_1 = int(match.group(1))
    star_2 = int(match.group(2))
    star_3 = int(match.group(3))
    star_4 = int(match.group(4))
    star_5 = int(match.group(5))
    rated_avg = float(match.group(6))
    rated_total = int(match.group(7))
else:
    # Если разбивка не найдена (например, изменилась верстка) — пишем пустые значения
    star_1 = star_2 = star_3 = star_4 = star_5 = ""
    rated_avg = rated_total = ""

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
        rating_value, review_count,
        star_1, star_2, star_3, star_4, star_5,
        rated_avg, rated_total
    ])

print(f"Сохранено: avg={rating_value}, count={review_count}, "
      f"разбивка=({star_1},{star_2},{star_3},{star_4},{star_5}), "
      f"rated_avg={rated_avg}, total={rated_total}")
