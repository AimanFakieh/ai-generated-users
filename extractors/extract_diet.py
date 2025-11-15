import os
import csv

import firebase_admin
from firebase_admin import credentials, firestore

# === CONFIGURATION ===

# Path to your service account JSON file
SERVICE_ACCOUNT_FILE = r"C:\Users\fakias0a\secrets\fitech-2nd-trail-e978c70041a0.json"

# Firestore project ID
PROJECT_ID = "fitech-2nd-trail"

# Output directory and CSV file path
OUTPUT_DIR = r"C:\Users\fakias0a\PycharmProjects\Resluts"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "diet_results.csv")

# All diet-related fields we want to extract from the 'plan' document
DIET_FIELDS = [
    "1st_meal",
    "1st_meal_carbs_g",
    "1st_meal_fat_g",
    "1st_meal_protein_g",
    "1st_meal_fiber_g",
    "1st_meal_sodium_mg",
    "1st_meal_kcal_target_kcal",
    "2nd_meal",
    "2nd_meal_carbs_g",
    "2nd_meal_fat_g",
    "2nd_meal_protein_g",
    "2nd_meal_fiber_g",
    "2nd_meal_sodium_mg",
    "2nd_meal_kcal_target_kcal",
    "3rd_meal",
    "3rd_meal_carbs_g",
    "3rd_meal_fat_g",
    "3rd_meal_protein_g",
    "3rd_meal_fiber_g",
    "3rd_meal_sodium_mg",
    "3rd_meal_kcal_target_kcal",
    "4th_meal",
    "4th_meal_carbs_g",
    "4th_meal_fat_g",
    "4th_meal_protein_g",
    "4th_meal_fiber_g",
    "4th_meal_sodium_mg",
    "4th_meal_kcal_target_kcal",
    "Total_kcal_target_kcal",
    "Total_carbs_g",
    "Total_fat_g",
    "Total_protein_g",
    "Total_fiber_g",
    "Total_sodium_mg",
    "Note",
]


def init_firestore():
    """
    Initialize Firestore using the Firebase Admin SDK and return a client.
    This will only initialize once even if called multiple times.
    """
    if not firebase_admin._apps:
        print("[INIT] Initializing Firebase app...")
        cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
        firebase_admin.initialize_app(cred, {"projectId": PROJECT_ID})
    else:
        print("[INIT] Firebase app already initialized.")

    return firestore.client()


def parse_user_and_week_from_path(path: str):
    """
    Given a Firestore document path like:
        experiments/Experiment_OpenAI/users/U01/weeks/Week1/diet/plan

    Extract:
        user_id  = U01
        week_num = Week1

    This function is robust as long as there is a 'users/{id}/weeks/{id}/diet/{doc}'
    pattern somewhere in the path.
    """
    segments = path.split("/")  # e.g. ['experiments', 'Experiment_OpenAI', 'users', 'U01', 'weeks', 'Week1', 'diet', 'plan']

    user_id = None
    week_number = None

    try:
        users_idx = segments.index("users")
        user_id = segments[users_idx + 1]
    except ValueError:
        # 'users' not found
        pass

    try:
        weeks_idx = segments.index("weeks")
        week_number = segments[weeks_idx + 1]
    except ValueError:
        # 'weeks' not found
        pass

    return user_id, week_number


def fetch_diet_data(db):
    """
    Search across ALL 'diet' subcollections in the whole Firestore project
    using collection_group('diet').

    For every document under a 'diet' collection:
      - Check if it has at least one of the DIET_FIELDS (so we know it's a diet plan).
      - Parse user_id and week_number from the path.
      - Collect all DIET_FIELDS into a row for the CSV.
    """
    rows = []

    print("[STEP] Listing top-level collections for info...")
    top_collections = [c.id for c in db.collections()]
    print(f"[INFO] Top-level collections: {top_collections}")

    print("\n[STEP] Searching across ALL 'diet' subcollections (collection_group('diet'))...")
    diet_query = db.collection_group("diet")

    # Stream all documents in any 'diet' collection
    docs = list(diet_query.stream())
    total_docs = len(docs)
    print(f"[INFO] Found {total_docs} document(s) inside collections named 'diet'.")

    if total_docs == 0:
        print("[WARN] There are no documents in any 'diet' collection. "
              "Either the data is stored elsewhere or the collection name is different.")
        return rows

    for idx, doc in enumerate(docs, start=1):
        path = doc.reference.path
        data = doc.to_dict() or {}

        # Show progress every few docs (and for the first few docs)
        if idx <= 10 or idx % 50 == 0 or idx == total_docs:
            print(f"\n[DOC {idx}/{total_docs}] Path: {path}")
            print(f"[DOC {idx}/{total_docs}] Fields: {list(data.keys())}")

        # Check if this doc has at least one of the DIET_FIELDS
        has_any_diet_field = any(
            (field in data and data[field] is not None) for field in DIET_FIELDS
        )
        if not has_any_diet_field:
            # Not a diet plan document we're interested in
            continue

        user_id, week_number = parse_user_and_week_from_path(path)

        if user_id is None or week_number is None:
            print(f"[WARN] Could not parse user/week from path (skipping): {path}")
            continue

        # Build a row with user_id, week_number, and all diet fields
        row = {
            "user_id": user_id,
            "week_number": week_number,
        }

        for field in DIET_FIELDS:
            row[field] = data.get(field)

        print(f"[OK]   Diet plan found for user={user_id}, week={week_number}")
        rows.append(row)

    # Sort by user_id first, then by week_number (as string)
    rows.sort(key=lambda r: (r["user_id"], str(r["week_number"])))

    print(f"\n[SUMMARY] Total diet plan rows: {len(rows)}")
    return rows


def write_csv(rows):
    """
    Write the collected rows into a CSV file with headers:
    'user id', 'Week number', and all DIET_FIELDS.
    """
    print(f"[STEP] Writing data to CSV at: {OUTPUT_CSV}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    fieldnames = ["user id", "Week number"] + DIET_FIELDS

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        total = len(rows)
        for idx, r in enumerate(rows, start=1):
            out_row = {
                "user id": r["user_id"],
                "Week number": r["week_number"],
            }
            # Add all diet fields, even if some are None
            for field in DIET_FIELDS:
                out_row[field] = r.get(field)

            writer.writerow(out_row)

            # Progress while writing
            if total > 0 and (idx % 10 == 0 or idx == total):
                print(f"[WRITE]   Wrote {idx}/{total} row(s)...")

    print("[DONE] CSV file creation completed.")


def main():
    print("=== Extract diet plan from Firestore to CSV (collection_group 'diet') ===")
    db = init_firestore()
    rows = fetch_diet_data(db)

    if not rows:
        print("\n[RESULT] No rows were found with diet fields.")
        print("         This might mean:")
        print("         - The field names differ slightly from DIET_FIELDS.")
        print("         - The docs with those fields are not under collections named 'diet'.")
        print("         - Or the data is stored in another place.")
    else:
        write_csv(rows)
        print(f"\n✅ Done. Wrote {len(rows)} row(s) to:")
        print(f"   {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
