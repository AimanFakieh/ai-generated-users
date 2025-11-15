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
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "diet_ACEgpt_ACEgpt_results.csv")


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
        experiments/ACEGPT_ACEGPT/users/U01/weeks/Week1/diet/plan

    Extract:
        user_id  = U01
        week_num = Week1
    """
    segments = path.split("/")  # e.g. ['experiments', 'ACEGPT_ACEGPT', 'users', 'U01', 'weeks', 'Week1', 'diet', 'plan']

    user_id = None
    week_number = None

    try:
        users_idx = segments.index("users")
        user_id = segments[users_idx + 1]
    except ValueError:
        pass

    try:
        weeks_idx = segments.index("weeks")
        week_number = segments[weeks_idx + 1]
    except ValueError:
        pass

    return user_id, week_number


def fetch_diet_data(db):
    """
    Search across ALL 'diet' subcollections in the whole Firestore project
    using collection_group('diet').

    For every document under a 'diet' collection:
      - Restrict to docs whose path ends with 'diet/plan'.
      - Restrict to paths under:
            /experiments/ACEGPT_ACEGPT/...
      - Read the diet fields and collect rows for CSV.
    """
    rows = []

    print("[STEP] Listing top-level collections for info...")
    top_collections = [c.id for c in db.collections()]
    print(f"[INFO] Top-level collections: {top_collections}")

    print("\n[STEP] Searching across ALL 'diet' subcollections (collection_group('diet'))...")
    diet_query = db.collection_group("diet")

    docs = list(diet_query.stream())
    total_docs = len(docs)
    print(f"[INFO] Found {total_docs} document(s) inside collections named 'diet'.")

    if total_docs == 0:
        print("[WARN] There are no documents in any 'diet' collection.")
        return rows

    for idx, doc in enumerate(docs, start=1):
        path = doc.reference.path
        data = doc.to_dict() or {}

        # Show progress for some docs
        if idx <= 10 or idx % 50 == 0 or idx == total_docs:
            print(f"\n[DOC {idx}/{total_docs}] Path: {path}")
            print(f"[DOC {idx}/{total_docs}] Fields: {list(data.keys())}")

        segments = path.split("/")

        # Only /.../diet/plan
        if not segments or segments[-1] != "plan":
            continue

        # Only from ACEGPT_ACEGPT experiment
        if "experiments/ACEGPT_ACEGPT" not in path:
            continue

        user_id, week_number = parse_user_and_week_from_path(path)

        if user_id is None or week_number is None:
            print(f"[WARN] Could not parse user/week from path (skipping): {path}")
            continue

        first_meal             = data.get("1st_meal")
        second_meal            = data.get("2nd_meal")
        third_meal             = data.get("3rd_meal")
        fourth_meal            = data.get("4th_meal")
        carbs_g                = data.get("Carbs_g")
        fat_g                  = data.get("Fat_g")
        protein_g              = data.get("Protein_g")
        total_sodium_mg        = data.get("Total_sodium_mg")
        total_kcal_target_kcal = data.get("Total_kcal_target_kcal")
        note                   = data.get("Note")
        raw_text               = data.get("raw_text")

        # Skip if everything is None
        if all(
            value is None
            for value in [
                first_meal,
                second_meal,
                third_meal,
                fourth_meal,
                carbs_g,
                fat_g,
                protein_g,
                total_sodium_mg,
                total_kcal_target_kcal,
                note,
                raw_text,
            ]
        ):
            continue

        print(
            f"[OK]   user={user_id}, week={week_number} | "
            f"1st_meal_present={first_meal is not None} | 2nd_meal_present={second_meal is not None} | "
            f"3rd_meal_present={third_meal is not None} | 4th_meal_present={fourth_meal is not None} | "
            f"Carbs_g={carbs_g} | Fat_g={fat_g} | Protein_g={protein_g} | "
            f"Total_kcal_target_kcal={total_kcal_target_kcal}"
        )

        rows.append(
            {
                "user_id": user_id,
                "week_number": week_number,
                "1st_meal": first_meal,
                "2nd_meal": second_meal,
                "3rd_meal": third_meal,
                "4th_meal": fourth_meal,
                "Carbs_g": carbs_g,
                "Fat_g": fat_g,
                "Protein_g": protein_g,
                "Total_sodium_mg": total_sodium_mg,
                "Total_kcal_target_kcal": total_kcal_target_kcal,
                "Note": note,
                "raw_text": raw_text,
            }
        )

    # Sort rows by user and week
    rows.sort(key=lambda r: (r["user_id"], str(r["week_number"])))

    print(f"\n[SUMMARY] Total rows with diet data: {len(rows)}")
    return rows


def write_csv(rows):
    """
    Write the collected rows into a CSV file with headers:
    'user id', 'Week number',
    '1st_meal', '2nd_meal', '3rd_meal', '4th_meal',
    'Carbs_g', 'Fat_g', 'Protein_g',
    'Total_sodium_mg', 'Total_kcal_target_kcal',
    'Note', 'raw_text'
    """
    print(f"[STEP] Writing data to CSV at: {OUTPUT_CSV}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    fieldnames = [
        "user id",
        "Week number",
        "1st_meal",
        "2nd_meal",
        "3rd_meal",
        "4th_meal",
        "Carbs_g",
        "Fat_g",
        "Protein_g",
        "Total_sodium_mg",
        "Total_kcal_target_kcal",
        "Note",
        "raw_text",
    ]

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        total = len(rows)
        for idx, r in enumerate(rows, start=1):
            writer.writerow(
                {
                    "user id": r["user_id"],
                    "Week number": r["week_number"],
                    "1st_meal": r["1st_meal"],
                    "2nd_meal": r["2nd_meal"],
                    "3rd_meal": r["3rd_meal"],
                    "4th_meal": r["4th_meal"],
                    "Carbs_g": r["Carbs_g"],
                    "Fat_g": r["Fat_g"],
                    "Protein_g": r["Protein_g"],
                    "Total_sodium_mg": r["Total_sodium_mg"],
                    "Total_kcal_target_kcal": r["Total_kcal_target_kcal"],
                    "Note": r["Note"],
                    "raw_text": r["raw_text"],
                }
            )
            if total > 0 and (idx % 10 == 0 or idx == total):
                print(f"[WRITE]   Wrote {idx}/{total} row(s)...")

    print("[DONE] CSV file creation completed.")


def main():
    print("=== Extract diet (ACEGPT_ACEGPT) data from Firestore to CSV ===")
    db = init_firestore()
    rows = fetch_diet_data(db)

    if not rows:
        print("\n[RESULT] No rows were found containing the target diet fields.")
        print("         Check that the fields exist in:")
        print("         /experiments/ACEGPT_ACEGPT/users/{user_id}/weeks/{week_number}/diet/plan")
    else:
        write_csv(rows)
        print(f"\n✅ Done. Wrote {len(rows)} row(s) to:")
        print(f"   {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
