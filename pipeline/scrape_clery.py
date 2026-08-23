#!/usr/bin/env python3
"""
Scrapes TAMU UPD's Clery Act crime log -- all offense types, both UPD and
College Station PD as sources -- filtered down to bike/bicycle theft.

    python scrape_clery.py

Writes clery_incidents.csv, in the same column schema as incidents.csv so
merge_incidents.py can combine the two.

Why this exists alongside scrape.py: the UPD alert bulletins scrape.py
reads are electric bike/scooter theft only (NIBRS files those as motor
vehicle theft, hence the separate bulletin). Regular pedal-bike theft was
never captured anywhere -- this page has it, tagged plainly in the
"Nature" column, e.g. "Theft of Property $100<$750 (Bicycle)" with no
"Electric" in sight.

The one real constraint, baked into the source itself, not a bug here: the
public log is a rolling ~60-day window -- the page's own header literally
states the date range it covers (e.g. "6/21/2026 - 8/23/2026"), no
date-picker, no archive. That's the Clery Act's own public-log requirement
(60 days self-service, older needs a records request), not a scraping
limitation. A biweekly run stays comfortably inside that window and won't
miss anything going forward, but there's no way to backfill regular-bike
history from before this scraper's first run -- score.py's recency
weighting and shrinkage already account for thin/absent history
gracefully, so this is still worth having even without a backfill.
"""

import csv
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from scrape import norm, write_csv

HERE = Path(__file__).parent
URL = "https://clery.tamu.edu/CrimeLog/College_Station"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_WINDOW_HOURS = 7 * 24  # same precision filter as scrape.py, applied downstream at scoring time

BIKE_RE = re.compile(r"bicycle|bike", re.I)


def parse_dt(s):
    s = norm(s)
    for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def classify_vehicle(nature):
    """The Nature column says the item type outright ("(Bicycle)" vs
    "(Electric Bike)") -- no prose-guessing needed, unlike scrape.py's
    narrative pages."""
    return "ebike" if "electric" in nature.lower() else "bike"


def main():
    r = requests.get(URL, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    date_range_heading = soup.find(string=re.compile(r"Crime Log.*\d{1,2}/\d{1,2}/\d{4}"))
    if date_range_heading:
        print(f"  source page covers: {norm(date_range_heading)}")

    rows, seen = [], set()
    for container in soup.select(".crime-log-case-container"):
        case_table = container.select_one("table.crime-log-case")
        details_table = container.select_one("table.crime-log-details")
        if not case_table or not details_table:
            continue

        case_cells = [norm(td.get_text()) for td in case_table.select("tbody td")]
        if len(case_cells) < 2:
            continue
        case_no, case_source = case_cells[0], case_cells[1]

        for tr in details_table.select("tbody tr"):
            cells = [norm(td.get_text()) for td in tr.find_all("td")]
            if len(cells) < 7:
                continue
            nature, location, date_reported, occ_start, occ_end, dates_are, disposition = cells[:7]
            if not BIKE_RE.search(nature):
                continue

            dedupe_key = (case_no, nature, occ_start)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            seen_dt = parse_dt(occ_start)
            disc_dt = parse_dt(occ_end)
            window = within = ""
            if seen_dt and disc_dt:
                window = round((disc_dt - seen_dt).total_seconds() / 3600, 2)
                within = str(window <= MAX_WINDOW_HOURS)

            missing = not case_no or not location or window == ""
            rows.append({
                "case_no": case_no,
                "alert_key": f"clery-{case_no}",
                "alert_date": date_reported,
                "alert_url": URL,
                "source_format": "clery",
                "case_source": case_source,
                "vehicle_type": classify_vehicle(nature),
                "last_seen": seen_dt.isoformat() if seen_dt else "",
                "discovered_missing": disc_dt.isoformat() if disc_dt else "",
                "window_hours": window,
                "within_window": within,
                "location_raw": location,
                "zone_id": "",
                "needs_review": str(missing),
                "narrative_text": f"{nature} -- {disposition}",
            })

    write_csv(HERE / "clery_incidents.csv", rows)

    ebike_n = sum(1 for r in rows if r["vehicle_type"] == "ebike")
    upd_n = sum(1 for r in rows if r["case_source"] == "UPD")
    print(f"{len(rows)} bike-related entries -> clery_incidents.csv")
    print(f"  ebike: {ebike_n}   bike (non-electric): {len(rows) - ebike_n}")
    print(f"  UPD: {upd_n}   other agency: {len(rows) - upd_n}")


if __name__ == "__main__":
    main()
