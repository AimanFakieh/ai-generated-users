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
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "logs_ACEgpt_ACEgpt_results.csv")


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
        experiments/Experiment_OpenAI/users/U01/weeks/Week1/logs/plan
    or:
        experiments/ACEGPT_ACEGPT/users/U01/weeks/Week1/logs/plan

    Extract:
        user_id  = U01
        week_num = Week1
    """
    segments = path.split("/")

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


def fetch_log_data(db):
    """
    Search across ALL 'logs' subcollections in the whole Firestore project
    using collection_group('logs').

    For every document under a 'logs' collection:
      - Restrict to docs whose path ends with 'logs/plan'.
      - Restrict to paths under either:
            /experiments/Experiment_OpenAI/...
        or  /experiments/ACEGPT_ACEGPT/...
      - Read the following fields (if present):
            Post_fat_pct
            Post_muscle_kg
            Post_weight_kg
            daily_avg_kcal
            sleep_avg_hours
            free_text_feedback
      - Parse user_id and week_number from the path.
      - Collect rows for the CSV.
    """
    rows = []

    print("[STEP] Listing top-level collections for info...")
    top_collections = [c.id for c in db.collections()]
    print(f"[INFO] Top-level collections: {top_collections}")

    print("\n[STEP] Searching across ALL 'logs' subcollections (collection_group('logs'))...")
    logs_query = db.collection_group("logs")

    docs = list(logs_query.stream())
    total_docs = len(docs)
    print(f"[INFO] Found {total_docs} document(s) inside collections named 'logs'.")

    if total_docs == 0:
        print("[WARN] There are no documents in any 'logs' collection.")
        return rows

    for idx, doc in enumerate(docs, start=1):
        path = doc.reference.path
        data = doc.to_dict() or {}

        # Show progress every few docs (and for the first few docs)
        if idx <= 10 or idx % 50 == 0 or idx == total_docs:
            print(f"\n[DOC {idx}/{total_docs}] Path: {path}")
            print(f"[DOC {idx}/{total_docs}] Fields: {list(data.keys())}")

        segments = path.split("/")
        # Only /.../logs/plan
        if not segments or segments[-1] != "plan":
            continue

        # Only from Experiment_OpenAI or ACEGPT_ACEGPT experiments
        if not (
            "experiments/Experiment_OpenAI" in path
            or "experiments/ACEGPT_ACEGPT" in path
        ):
            continue

        user_id, week_number = parse_user_and_week_from_path(path)

        if user_id is None or week_number is None:
            print(f"[WARN] Could not parse user/week from path (skipping): {path}")
            continue

        post_fat_pct       = data.get("Post_fat_pct")
        post_muscle_kg     = data.get("Post_muscle_kg")
        post_weight_kg     = data.get("Post_weight_kg")
        daily_avg_kcal     = data.get("daily_avg_kcal")
        sleep_avg_hours    = data.get("sleep_avg_hours")
        free_text_feedback = data.get("free_text_feedback")

        # Skip if all fields are missing
        if all(
            value is None
            for value in [
                post_fat_pct,
                post_muscle_kg,
                post_weight_kg,
                daily_avg_kcal,
                sleep_avg_hours,
                free_text_feedback,
            ]
        ):
            continue

        print(
            f"[OK]   user={user_id}, week={week_number} | "
            f"fat={post_fat_pct} | muscle={post_muscle_kg} | weight={post_weight_kg} | "
            f"kcal={daily_avg_kcal} | sleep={sleep_avg_hours} | "
            f"feedback_present={free_text_feedback is not None}"
        )

        rows.append(
            {
                "user_id": user_id,
                "week_number": week_number,
                "Post_fat_pct": post_fat_pct,
                "Post_muscle_kg": post_muscle_kg,
                "Post_weight_kg": post_weight_kg,
                "daily_avg_kcal": daily_avg_kcal,
                "sleep_avg_hours": sleep_avg_hours,
                "free_text_feedback": free_text_feedback,
                # Optional: which experiment this row came from
                "experiment": "Experiment_OpenAI"
                if "experiments/Experiment_OpenAI" in path
                else "ACEGPT_ACEGPT",
            }
        )

    # Sort by experiment, then user_id, then week_number
    rows.sort(key=lambda r: (r["experiment"], r["user_id"], str(r["week_number"])))

    print(f"\n[SUMMARY] Total rows with at least one target field: {len(rows)}")
    return rows


def write_csv(rows):
    """
    Write the collected rows into a CSV file with headers:
    'experiment', 'user id', 'Week number',
    'Post_fat_pct', 'Post_muscle_kg', 'Post_weight_kg',
    'daily_avg_kcal', 'sleep_avg_hours', 'free_text_feedback'
    """
    print(f"[STEP] Writing data to CSV at: {OUTPUT_CSV}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    fieldnames = [
        "experiment",
        "user id",
        "Week number",
        "Post_fat_pct",
        "Post_muscle_kg",
        "Post_weight_kg",
        "daily_avg_kcal",
        "sleep_avg_hours",
        "free_text_feedback",
    ]

    with open(OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        total = len(rows)
        for idx, r in enumerate(rows, start=1):
            writer.writerow(
                {
                    "experiment": r["experiment"],
                    "user id": r["user_id"],
                    "Week number": r["week_number"],
                    "Post_fat_pct": r["Post_fat_pct"],
                    "Post_muscle_kg": r["Post_muscle_kg"],
                    "Post_weight_kg": r["Post_weight_kg"],
                    "daily_avg_kcal": r["daily_avg_kcal"],
                    "sleep_avg_hours": r["sleep_avg_hours"],
                    "free_text_feedback": r["free_text_feedback"],
                }
            )
            if total > 0 and (idx % 10 == 0 or idx == total):
                print(f"[WRITE]   Wrote {idx}/{total} row(s)...")

    print("[DONE] CSV file creation completed.")


def main():
    print("=== Extract logs (multiple fields) from Experiment_OpenAI & ACEGPT_ACEGPT to CSV ===")
    db = init_firestore()
    rows = fetch_log_data(db)

    if not rows:
        print("\n[RESULT] No rows were found containing the target fields.")
        print("         Please check that the fields exist in:")
        print("         /experiments/Experiment_OpenAI/users/{user_id}/weeks/{week_number}/logs/plan")
        print("         /experiments/ACEGPT_ACEGPT/users/{user_id}/weeks/{week_number}/logs/plan")
    else:
        write_csv(rows)
        print(f"\n✅ Done. Wrote {len(rows)} row(s) to:")
        print(f"   {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
