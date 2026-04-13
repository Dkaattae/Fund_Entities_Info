import os
import gzip
import requests
from datetime import date, timedelta


BASE_URL = (
    "https://reports.adviserinfo.sec.gov/reports/CompilationReports/"
    "IA_FIRM_STATE_Feed_{mm}_{dd}_{yyyy}.xml.gz"
)
FILE_DIR = os.path.join(os.path.dirname(__file__), "state_adviser_files")


def build_url(dt: date) -> str:
    return BASE_URL.format(
        mm=f"{dt.month:02d}",
        dd=f"{dt.day:02d}",
        yyyy=dt.year,
    )


def download_file(dt: date, file_dir: str = FILE_DIR) -> str | None:
    """Download the IA_FIRM_STATE XML for the given date.

    Returns the path to the decompressed XML file, or None if unavailable.
    """
    os.makedirs(file_dir, exist_ok=True)

    xml_filename = f"IA_FIRM_STATE_{dt.strftime('%Y_%m_%d')}.xml"
    xml_path = os.path.join(file_dir, xml_filename)

    if os.path.exists(xml_path):
        print(f"Already downloaded: {xml_path}")
        return xml_path

    url = build_url(dt)
    print(f"Downloading {url} ...")
    resp = requests.get(url, timeout=120)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code} for {url}")
        return None

    xml_bytes = gzip.decompress(resp.content)
    with open(xml_path, "wb") as f:
        f.write(xml_bytes)

    print(f"Saved {xml_path} ({len(xml_bytes):,} bytes)")
    return xml_path


def find_latest_available(max_lookback: int = 10) -> date | None:
    """Probe recent dates to find the latest available feed."""
    today = date.today()
    for i in range(max_lookback):
        dt = today - timedelta(days=i)
        url = build_url(dt)
        resp = requests.head(url, timeout=30)
        if resp.status_code == 200:
            return dt
    return None


if __name__ == "__main__":
    dt = find_latest_available()
    if dt:
        print(f"Latest available: {dt}")
        download_file(dt)
    else:
        print("No recent feed found.")
