#!/usr/bin/env python3
"""
Combines incidents.csv (UPD e-bike/e-scooter alert bulletins, from
scrape.py) with clery_incidents.csv (TAMU's Clery crime log -- broader:
regular bikes too, plus College Station PD as a second source, from
scrape_clery.py) into incidents_merged.csv, which zonejoin.py reads.

    python merge_incidents.py

Dedupes by case_no: the same UPD incident can legitimately show up in
both sources (once as its own alert bulletin, once as a line in the
general crime log), and double-counting it would inflate that zone's
grade unfairly. The Clery version wins on a collision -- it carries exact
Occurred Start/End timestamps straight from the source instead of ones
regex-parsed out of narrative prose.
"""

import csv
from pathlib import Path

HERE = Path(__file__).parent


def read_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    upd = read_csv(HERE / "incidents.csv")
    clery = read_csv(HERE / "clery_incidents.csv")

    fieldnames = []
    for r in upd + clery:
        for k in r:
            if k not in fieldnames:
                fieldnames.append(k)

    by_case = {r["case_no"]: r for r in upd if r.get("case_no")}
    overridden = sum(1 for r in clery if r.get("case_no") in by_case)
    for r in clery:
        if r.get("case_no"):
            by_case[r["case_no"]] = r  # clery wins on collision

    no_case = [r for r in upd + clery if not r.get("case_no")]
    merged = sorted(by_case.values(), key=lambda r: r.get("alert_date", "")) + no_case

    for r in merged:
        for k in fieldnames:
            r.setdefault(k, "")

    with open(HERE / "incidents_merged.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(merged)

    print(f"{len(upd)} UPD-alert + {len(clery)} Clery-log entries "
          f"-> {len(merged)} merged (incidents_merged.csv)")
    print(f"  {overridden} case(s) present in both sources -- Clery version kept")


if __name__ == "__main__":
    main()
