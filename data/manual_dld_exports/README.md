# Manual DLD exports

Drop point for CSV exports pulled directly from DLD's own portal (the
authoritative source — fresher than the Kaggle mirror `ingestion/` normally
uses, since that mirror only updates whenever its uploader feels like it).

CSVs dropped here are gitignored (raw data, not code) — only this README is
tracked.

## How to get a file

1. Go to https://dubailand.gov.ae/en/open-data/real-estate-data/
2. Select the **Transactions** category
3. Set the date range to start the day after the graph's current
   `date_range_end` (check `data/processed/manifest.json` or ask AqarIQ's
   dashboard for the latest `DatasetVersion`) through today — this keeps the
   export small and avoids re-processing data we already have
4. Leave area/property-type filters blank (get everything in that range)
5. Complete the CAPTCHA, click **Download as CSV**
6. Save the file into this folder
7. Tell Claude the file is here — it'll inspect the format and ingest it

There's no way to automate steps 1–6 (CAPTCHA-gated by design) — this is a
~5-minute manual task, ideally repeated monthly to keep the graph current.
