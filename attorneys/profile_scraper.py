import requests
from bs4 import BeautifulSoup
import time
import pandas as pd
from tqdm import tqdm

def get_profile_details(profile_url):
    resp = requests.get(profile_url)
    soup = BeautifulSoup(resp.text, "html.parser")

    # firm name
    firm_tag = soup.select_one("div.firm-profile-section div.mb-4.h6")
    firm_name = firm_tag.get_text(strip=True) if firm_tag else None

    # external website
    site_tag = soup.select_one("a.ga-lawyer-link")
    site_link = site_tag["href"] if site_tag else None

    # practice area
    areas = [
        span.get_text(strip=True)
        for span in soup.select(
            "#awardedPracticeAreas .practice-area-badge"
        )
    ]

    # phone number
    phone_tag = soup.select_one("a.ga-lawyer-firm-phone")
    phone = phone_tag.get_text(strip=True) if phone_tag else None

    # address
    address_tag = soup.select_one("a.ga-lawyer-firm-directions")
    if address_tag:
        # replace <br> with comma and strip extra spaces
        address = " ".join(address_tag.stripped_strings)
    else:
        address = None

    profile = {
        "firm_name": firm_name,
        "site_link": site_link,
        "areas": areas,
        "phone": phone,
        "address": address
    }
    return profile

lawyer_df = pd.read_csv('lawyers_dedup.csv')
all_lawyers = lawyer_df.to_dict(orient="records")
# Update all_lawyers
for lawyer in tqdm(all_lawyers):
    profile = get_profile_details(lawyer["profile_url"])
    lawyer["firm_name"] = profile["firm_name"]
    lawyer["site_link"]   = profile["site_link"]
    lawyer["practice_area"] = ", ".join(profile["areas"])
    lawyer["phone"] = profile["phone"]
    lawyer["address"] = profile["address"]
    time.sleep(0.5)

lawyers_profile_df = pd.DataFrame(all_lawyers)
lawyers_profile_df.to_csv("lawyers_profile.csv")