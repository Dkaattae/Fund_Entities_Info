import requests
from bs4 import BeautifulSoup
import time
import pandas as pd

BASE = "https://www.bestlawyers.com"
START_URL = f"{BASE}/united-states/private-funds-hedge-funds-law"

def scrape_page(url):
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("a.ga-lawyer-card-click")
    results = []

    for a in cards:
        href = a["href"]
        lawyer_url = BASE + href

        # parse id info
        onclick = a.get("onclick","")
        lawyer_id = onclick.split("lawyerId':")[1].split("}")[0].split(")")[0]
        firm_id  = onclick.split("firmId':")[1].split("}")[0].split(")")[0]

        name = a["aria-label"].replace("’s Lawyer Profile","").strip()

        results.append({
            "name": name,
            "lawyer_id": lawyer_id,
            "firm_id": firm_id,
            "profile_url": lawyer_url
        })
    return results

# scrape all pages
all_lawyers = []
page = 1
while True:
    print("Scraping page", page)
    url = f"{START_URL}?page={page}"
    lawyers = scrape_page(url)

    if not lawyers:
        break  # no more
    all_lawyers.extend(lawyers)
    page += 1
    if page > 30:
        break
    time.sleep(1)

print("Total lawyers:", len(all_lawyers))
lawyer_df = pd.DataFrame(all_lawyers)
lawyer_df.to_csv('LawyerList.csv')