import re
import time
from datetime import datetime
from pathlib import Path

import requests

API_URL = "https://deckcheck.co/api/external/deck"
IDS_FILE = "precon_ids.txt"
RESULTS_DIR = Path("results")

# Stay comfortably under the documented 10 req/s unauthenticated rate limit.
REQUEST_DELAY_SECONDS = 0.11

# The 12 DTI benchmark codes and what DeckCheck currently calls each one.
BENCHMARK_CATEGORY = {
    "R1": "Mana Velocity", "R2": "Card Flow",
    "A1": "Selection & Redundancy", "A2": "Assembly Velocity",
    "P1": "Critical Onset", "P2": "Win Compactness", "P3": "Exposure",
    "I1": "Reactive Disruption", "I2": "Proactive Denial",
    "S1": "Plan Shielding", "S2": "Engine Recovery", "S3": "Independence",
}

# The 5 top-level letter groups each benchmark code rolls up into.
GROUP_CODES = {
    "R": ["R1", "R2"],
    "A": ["A1", "A2"],
    "P": ["P1", "P2", "P3"],
    "I": ["I1", "I2"],
    "S": ["S1", "S2", "S3"],
}
GROUP_LABEL = {
    "R": "Resources",
    "A": "Access",
    "P": "Pressure",
    "I": "Interaction",
    "S": "Resilience",
}

# Letter grade -> numeric, for sorting purposes.
GRADE_VALUE = {"S": 5, "A": 4, "B": 3, "C": 2, "F": 1}

# Matches things like "<strong>Speed: 7.5/10</strong>" or
# "<strong>Velocity: 8/10</strong>" anywhere in fullAnalysis, whatever the
# category is actually called on the new site.
PROSE_RATING_RE = re.compile(
    r"<strong>\s*([A-Za-z][A-Za-z /]*?)\s*:\s*([\d.]+)\s*/\s*10\s*</strong>"
)

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})


def get_deck(deck_id):
    while True:
        response = session.get(API_URL, params={"deck_id": deck_id}, timeout=30)

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
    return "N/A"


def extract_prose_ratings(deck):
    """Pull every 'Category: X/10' rating out of fullAnalysis, whatever the
    category is named (Speed, Velocity, Suppression, etc.)."""
    analysis = deck.get("fullAnalysis") or ""
    ratings = {}
    for label, value in PROSE_RATING_RE.findall(analysis):
        label = label.strip()
        try:
            ratings[label] = float(value)
        except ValueError:
            pass
    return ratings


def extract_benchmark_grades(deck):
    """Return {code: letter} and {code: numeric} for the 12 DTI benchmarks."""
    dti = deck.get("dti") or {}
    benchmarks = dti.get("benchmarks") or {}
    numeric = {
        code: GRADE_VALUE.get(letter)
        for code, letter in benchmarks.items()
    }
    return benchmarks, numeric


# ------------------------------------------------------------
# LOAD IDS
# ------------------------------------------------------------

if not Path(IDS_FILE).exists():
    print(f"ERROR: {IDS_FILE} not found.")
    raise SystemExit

ids = [
    line.strip()
    for line in Path(IDS_FILE).read_text(encoding="utf-8").splitlines()
    if line.strip()
]

print(f"Found {len(ids)} deck IDs.")
print()


# ------------------------------------------------------------
# DOWNLOAD DECK DATA
# ------------------------------------------------------------

results = []
all_prose_categories = set()

for number, deck_id in enumerate(ids, 1):
    try:
        deck = get_deck(deck_id)

        dti = deck.get("dti") or {}
        letter_grades, numeric_grades = extract_benchmark_grades(deck)
        prose_ratings = extract_prose_ratings(deck)
        all_prose_categories.update(prose_ratings.keys())

        result = {
            "name": deck.get("name", "Unknown"),
            "commander": get_commander(deck),
            "format": deck.get("formatLabel", "Unknown"),
            "threat_index": dti.get("score"),
            "bracket": deck.get("bracket"),
            "letter_grades": letter_grades,   # e.g. {"R1": "S", ...}
            "numeric_grades": numeric_grades, # e.g. {"R1": 5, ...}
            "prose_ratings": prose_ratings,   # e.g. {"Speed": 7.5, ...}
            "id": deck_id,
        }

        results.append(result)
        print(f"[{number}/{len(ids)}] {result['name']}")

    except Exception as e:
        print(f"[{number}/{len(ids)}] {deck_id} — ERROR: {e}")

    time.sleep(REQUEST_DELAY_SECONDS)

print()
print("Finished downloading deck data.")
print()


# ------------------------------------------------------------
# BUILD LIST OF SORTABLE FIELDS
# ------------------------------------------------------------

# 1) Threat Index (overall power score)
# 2) Grouped letter categories (R, A, P, I, S) — sum of that group's codes
# 3) Individual benchmark codes (R1, R2, A1, A2, P1, P2, P3, I1, I2, S1, S2, S3)
# 4) Any prose category name actually found in the analyses (Speed, Velocity,
#    Suppression, Consistency, whatever the site currently calls them)

sortable_fields = (
    ["threat_index"]
    + sorted(GROUP_CODES.keys())
    + sorted(BENCHMARK_CATEGORY.keys())
    + sorted(all_prose_categories)
)


def print_menu():
    print("Available things to sort by:")
    print("  - threat_index   (overall DeckCheck Threat Index, 0-96)")
    print()
    print("  Grouped categories (sum of their sub-benchmarks):")
    for group, codes in GROUP_CODES.items():
        code_list = "+".join(codes)
        print(f"  - {group:<14} ({GROUP_LABEL[group]} total = {code_list})")
    print()
    print("  Individual benchmarks:")
    for code in sorted(BENCHMARK_CATEGORY.keys()):
        print(f"  - {code:<14} ({BENCHMARK_CATEGORY[code]}, graded F-S)")
    if all_prose_categories:
        print()
        print("  From written analysis (out of /10):")
        for cat in sorted(all_prose_categories):
            print(f"  - {cat}")
    print()
    print("  Type 'quit' to exit.")
    print()


def get_sort_value(deck, field):
    if field == "threat_index":
        return deck["threat_index"]
    if field in GROUP_CODES:
        values = [deck["numeric_grades"].get(code) for code in GROUP_CODES[field]]
        available = [v for v in values if v is not None]
        return sum(available) if available else None
    if field in BENCHMARK_CATEGORY:
        return deck["numeric_grades"].get(field)
    return deck["prose_ratings"].get(field)


def save_results_to_file(field, sorted_results):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_field = re.sub(r"[^A-Za-z0-9]+", "_", field).strip("_")
    filepath = RESULTS_DIR / f"results_{timestamp}_{safe_field}.txt"

    lines = []
    lines.append(f"Sorted by: {field}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 100)
    lines.append(f"DECKS SORTED BY {field.upper()} — HIGHEST TO LOWEST")
    lines.append("=" * 100)
    lines.append("")

    for rank, deck in enumerate(sorted_results, 1):
        value = get_sort_value(deck, field)
        value_text = (
            "N/A" if value is None
            else f"{value:.2f}" if isinstance(value, float)
            else str(value)
        )

        lines.append(f"{rank:3}. {deck['name']:<45} {field}: {value_text}")
        lines.append(f"     Commander: {deck['commander']}  |  Format: {deck['format']}")
        lines.append(f"     Threat Index: {deck['threat_index']} | Bracket: {deck['bracket']}")
        if deck["prose_ratings"]:
            prose_str = " | ".join(f"{k}: {v}" for k, v in deck["prose_ratings"].items())
            lines.append(f"     Analysis ratings -> {prose_str}")
        if deck["letter_grades"]:
            grades_str = " ".join(f"{k}:{v}" for k, v in sorted(deck["letter_grades"].items()))
            lines.append(f"     Benchmarks -> {grades_str}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


# ------------------------------------------------------------
# MAIN LOOP: sort, display, save, then back to the menu
# ------------------------------------------------------------

while True:
    print_menu()
    field = input("Sort by: ").strip()

    if field.lower() in ("quit", "exit", "q"):
        print("Goodbye!")
        break

    # allow case-insensitive match against prose category names / codes
    if field not in sortable_fields:
        match = next((f for f in sortable_fields if f.lower() == field.lower()), None)
        if match:
            field = match

    if field not in sortable_fields:
        print("Invalid option. Pick one of the fields listed above.")
        print()
        continue

    # Sort (None values always sink to the bottom)
    results.sort(
        key=lambda d: (
            get_sort_value(d, field) is not None,
            get_sort_value(d, field) if get_sort_value(d, field) is not None else -1,
        ),
        reverse=True,
    )

    print()
    print("=" * 100)
    print(f"DECKS SORTED BY {field.upper()} — HIGHEST TO LOWEST")
    print("=" * 100)
    print()

    for rank, deck in enumerate(results, 1):
        value = get_sort_value(deck, field)
        value_text = (
            "N/A" if value is None
            else f"{value:.2f}" if isinstance(value, float)
            else str(value)
        )

        print(f"{rank:3}. {deck['name']:<45} {field}: {value_text}")
        print(f"     Commander: {deck['commander']}  |  Format: {deck['format']}")
        print(f"     Threat Index: {deck['threat_index']} | Bracket: {deck['bracket']}")
        if deck["prose_ratings"]:
            prose_str = " | ".join(f"{k}: {v}" for k, v in deck["prose_ratings"].items())
            print(f"     Analysis ratings -> {prose_str}")
        if deck["letter_grades"]:
            grades_str = " ".join(f"{k}:{v}" for k, v in sorted(deck["letter_grades"].items()))
            print(f"     Benchmarks -> {grades_str}")
        print()

    saved_path = save_results_to_file(field, results)
    print(f"Saved results to: {saved_path.resolve()}")
    print()