# TAMU Bike Rack Safety

Shows TAMU College Station students which bike rack areas have reported
bike/scooter theft history, based on public UPD sources. Static site, no
backend. The data is regenerated on a schedule and committed as static JSON.

## How it works

1. **`pipeline/scrape.py`** : pulls TAMU UPD's Crime Alert index (a public
   JSON feed), fetches every bike/e-scooter theft alert page, and parses
   incidents (case number, dates, free-text location) into `incidents.csv`.
   Electric bikes/scooters only (NIBRS files those as motor vehicle theft,
   hence a dedicated bulletin).
2. **`pipeline/scrape_clery.py`** : pulls TAMU UPD's general Clery Act crime
   log (`clery.tamu.edu`), which additionally covers regular non-electric
   bike theft and reports filed with College Station PD, into
   `clery_incidents.csv`. That public log is a rolling ~60-day window (the
   Clery Act's own requirement, not a scraper limitation), good for ongoing
   coverage, but it can't backfill history from before this scraper's first
   run.
3. **`pipeline/merge_incidents.py`** : combines the two into
   `incidents_merged.csv`, deduping by case number (the same UPD incident
   can legitimately appear in both sources; the Clery version wins since it
   carries exact timestamps instead of ones parsed out of prose).
4. **`pipeline/zonejoin.py`** : matches each incident's location text to a
   campus "zone" (see below), preferring geocoding a real street address
   when the alert includes one, falling back to fuzzy name matching.
   Unmatched rows land in `needs_review.csv`.
5. **`pipeline/racks.py`** : pulls the public TAMU Transportation Services
   bike rack inventory (ArcGIS REST API) and assigns each rack to its
   nearest zone.
6. **`pipeline/score.py`** : grades each zone A+ through F. Incidents are
   weighted by recency (1-year half-life, so old reports fade), then each
   zone's rate is shrunk toward the campus-wide average via empirical-Bayes
   smoothing, weighted by how much rack capacity (evidence) that zone has,
   a zone with only a handful of racks doesn't get graded on its own thin
   history alone. Zones with zero reports of their own get an *estimated*
   grade instead, inverse-distance-weighted from nearby rated zones. Full
   rationale is in the docstring at the top of the file. Writes
   `site/data/zones.json` + `site/data/racks.geojson`.
7. **`site/`** : a static page. Gets the visitor's location client-side,
   finds the nearest zone by haversine distance against the ~90 zone
   centroids, and shows its grade plus an interactive map.

A GitHub Action (`.github/workflows/update.yml`) re-runs steps 1-6 on a
schedule and redeploys the site whenever the data changes.

## Zones

TAMU's bike rack GIS layers have no building/zone name field, so zones are
generated once by clustering rack points by proximity and reverse-geocoding
each cluster's centroid (`pipeline/gen_zones.py`) into `pipeline/zones.json`.
Labels are a starting point, not gospel, hand-edit `zones.json` for any
zone whose name is wrong or too generic, and grow each zone's `aliases`
list based on what `needs_review.csv` reveals over time. Re-run
`gen_zones.py` only if the physical rack layout changes significantly (it
will regenerate zone IDs, which breaks continuity with existing grades).

## Local development

```bash
cd pipeline
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python scrape.py manifest
./.venv/bin/python scrape.py fetch
./.venv/bin/python scrape.py parse
./.venv/bin/python scrape_clery.py
./.venv/bin/python merge_incidents.py
./.venv/bin/python zonejoin.py
./.venv/bin/python racks.py
./.venv/bin/python score.py

cd ../site
python3 -m http.server 8000
# open http://localhost:8000
```

## Honesty about the data

- Sample sizes per zone are small (dozens of incidents total across ~90
  zones). Grades are directional, not statistically rigorous.
- A grade of A+ with zero reports means **no theft has been reported
  there in the data collected**, not "verified safe." Under-reporting is
  real; lock your bike properly regardless of area grade.
- Regular pedal-bike theft is included via the Clery crime log, but that
  log is a rolling ~60-day window with no self-service archive, history
  from before `scrape_clery.py`'s first run isn't backfilled, so a zone's
  early grades may still be electric-bike-only even after this feature
  shipped.
