# py "C:\Users\benja\OneDrive\deck_check\hi.py"

import requests
import time
from pathlib import Path

API_URL = "https://deckcheck.co/api/external/deck"
IDS_FILE = "precon_ids.txt"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})


def get_deck(deck_id):
    while True:
        response = session.get(
            API_URL,
            params={"deck_id": deck_id},
            timeout=30
        )

        if response.status_code == 429:
            print("Rate limited. Waiting 5 seconds...")
            time.sleep(5)
            continue

        response.raise_for_status()
        return response.json()


def get_commander(deck):
    commander = deck.get("mainCommander")

    if isinstance(commander, dict):
        return commander.get("name", "Unknown")

    if isinstance(commander, str):
        return commander

    return "Unknown"


def get_stat(deck, stat):
    crispi = deck.get("crispi") or {}
    return crispi.get(stat)


# ------------------------------------------------------------
# LOAD IDS
# ------------------------------------------------------------

if not Path(IDS_FILE).exists():
    print(f"ERROR: {IDS_FILE} not found.")
    exit()

ids = [
    line.strip()
    for line in Path(IDS_FILE).read_text(encoding="utf-8").splitlines()
    if line.strip()
]

print(f"Found {len(ids)} precon IDs.")
print()


# ------------------------------------------------------------
# DOWNLOAD DECK DATA
# ------------------------------------------------------------

results = []

for number, deck_id in enumerate(ids, 1):

    try:
        deck = get_deck(deck_id)

        crispi = deck.get("crispi") or {}

        result = {
            "name": deck.get("name", "Unknown"),
            "commander": get_commander(deck),
            "speed": crispi.get("speed"),
            "consistency": crispi.get("consistency"),
            "resilience": crispi.get("resilience"),
            "interaction": crispi.get("interaction"),
            "overall": crispi.get("overall"),
            "id": deck_id
        }

        results.append(result)

        print(
            f"[{number}/{len(ids)}] "
            f"{result['name']} "
        )

    except Exception as e:
        print(f"[{number}/{len(ids)}] {deck_id} — ERROR: {e}")

    time.sleep(0.2)


print()
print("Finished downloading deck data.")
print()


# ------------------------------------------------------------
# ASK WHAT TO SORT BY
# ------------------------------------------------------------

valid_stats = {
    "speed",
    "consistency",
    "resilience",
    "interaction",
    "overall"
}

while True:

    stat = input(
        "Sort by "
        "(speed / consistency / resilience / interaction / overall): "
    ).strip().lower()

    if stat in valid_stats:
        break

    print("Invalid option. Choose one of the five stats.")
    print()


# ------------------------------------------------------------
# SORT
# ------------------------------------------------------------

results.sort(
    key=lambda x: (
        x[stat] is not None,
        x[stat] if x[stat] is not None else -1
    ),
    reverse=True
)


# ------------------------------------------------------------
# DISPLAY
# ------------------------------------------------------------

print()
print("=" * 100)
print(f"PRECONS SORTED BY {stat.upper()} — HIGHEST TO LOWEST")
print("=" * 100)
print()

for rank, deck in enumerate(results, 1):

    value = deck[stat]

    if value is None:
        value_text = "N/A"
    else:
        value_text = f"{value:.2f}"

    print(
        f"{rank:3}. "
        f"{deck['name']:<45} "
        f"{stat.capitalize()}: {value_text}"
    )

    print(
        f"     Commander: {deck['commander']}"
    )

    print(
        f"Speed: {deck['speed']} | "
        f"Consistency: {deck['consistency']} | "
        f"Resilience: {deck['resilience']} | "
        f"Interaction: {deck['interaction']} | "
        f"Overall: {deck['overall']}"
    )

    print()