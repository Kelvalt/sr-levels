import csv, os

# Pine Seeds requires this exact format:
# time, open, high, low, close, volume (OHLCV)
# For S/R levels we'll use a custom format they support

DATA_PATH = os.path.expanduser("~/sr-levels/data")

def check_csvs():
    for f in os.listdir(DATA_PATH):
        if f.endswith(".csv"):
            print(f"\n{f}:")
            with open(os.path.join(DATA_PATH, f)) as file:
                for line in file:
                    print(line.strip())

check_csvs()
