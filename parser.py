import requests
from bs4 import BeautifulSoup
import json
import csv
from datetime import datetime

url = "https://www.litres.com/book/edvard-monk/sneg-73795536/"

# Добавляем User-Agent, чтобы сайт не считал нас ботом
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, "html.parser")

rating_count = None
rating_value = None

# Находим все блоки JSON-LD
for script in soup.find_all("script", type="application/ld+json"):
    data = json.loads(script.string)
    # Проверяем, что это нужный нам тип (Book или Product)
    if data.get("@type") in ["Book", "Product"]:
        aggregate_rating = data.get("aggregateRating", {})
        rating_count = aggregate_rating.get("reviewCount")
        rating_value = aggregate_rating.get("ratingValue")
        if rating_count:
            break

# Формируем строку CSV
now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

with open("data.csv", "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["datetime", "rating_value", "review_count"])
    if rating_count:
        writer.writerow([now, rating_value, rating_count])
    else:
        writer.writerow([now, "", ""])
        print("Не удалось найти количество оценок.")

print(f"Данные сохранены в data.csv: {now}, рейтинг={rating_value}, оценок={rating_count}")
