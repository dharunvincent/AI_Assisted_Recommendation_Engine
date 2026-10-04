"""
data/download_movielens.py

Small helper script. Run this once to download the real MovieLens
"ml latest small" dataset from GroupLens, University of Minnesota, and
unpack it into data/ml-latest-small/

This is the only network call anywhere in this project. Everything else
after this script runs works fully offline, using the files it downloads.
"""

import os
import urllib.request
import zipfile

MOVIELENS_URL = "https://files.grouplens.org/datasets/movielens/ml-latest-small.zip"
DOWNLOAD_FOLDER = os.path.dirname(os.path.abspath(__file__))
ZIP_PATH = os.path.join(DOWNLOAD_FOLDER, "ml-latest-small.zip")


def download_movielens():
    if os.path.exists(os.path.join(DOWNLOAD_FOLDER, "ml-latest-small")):
        print("ml-latest-small folder already exists, skipping download.")
        return

    print("Downloading MovieLens ml-latest-small dataset ...")
    urllib.request.urlretrieve(MOVIELENS_URL, ZIP_PATH)
    print("Download complete. Unpacking ...")

    with zipfile.ZipFile(ZIP_PATH, "r") as zip_file:
        zip_file.extractall(DOWNLOAD_FOLDER)

    os.remove(ZIP_PATH)
    print("Done. You should now see data/ml-latest-small/movies.csv and ratings.csv")


if __name__ == "__main__":
    download_movielens()
