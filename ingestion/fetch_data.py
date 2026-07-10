"""
Re-download the DLD transactions snapshot from its Kaggle mirror. No Kaggle
account/API key needed -- this dataset's download endpoint is public.

Run this before filter_transactions.py to refresh data/raw/Transactions.csv
with whatever the mirror has most recently published.
"""

import os
import urllib.request
import zipfile
import io

DATASET_REF = "waelr1985/dubai-real-estate-transaction"
DOWNLOAD_URL = f"https://www.kaggle.com/api/v1/datasets/download/{DATASET_REF}"

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "..", "data", "raw")


def main():
    os.makedirs(RAW_DIR, exist_ok=True)
    print(f"Downloading {DOWNLOAD_URL} ...")
    with urllib.request.urlopen(DOWNLOAD_URL) as resp:
        data = resp.read()
    print(f"Downloaded {len(data):,} bytes, extracting...")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(RAW_DIR)
    print(f"Extracted into {RAW_DIR}")


if __name__ == "__main__":
    main()
