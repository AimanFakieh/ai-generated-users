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
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "updated_persona_ACEgpt_Claude_results.csv")


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
        experiments/Experiment_ACEGPT/users/U01/weeks/Week1/updated_persona/plan

    Extract:
        user_id  = U01
        week_num = Week1
    """
    segments = path.split("/")  # e.g. [..., 'users', 'U01', 'weeks', 'Week1', 'updated_persona', 'plan']

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


def fetch_updated_persona_data(db):
    """
    Search across ALL 'updated_persona' subcollections in the whole Firestore project
    using collection_group('updated_persona').

    For every document under an 'updated_persona' collection:
      - Restrict to docs whose path ends with 'updated_persona/plan'.
      - Restrict to paths under:
            /experiments/Experiment_ACEGPT/...
      - Read persona fields and collect rows for CSV.
    """
    rows = []

    print("[STEP] Listing top-level collections for info...")
    top_collections = [c.id for c in db.collections()]
    print(f"[INFO] Top-level collections: {top_collections}")

    print("\n[STEP] Searching across ALL 'updated_persona' subcollections (collection_group('updated_persona'))...")
    persona_query = db.collection_group("updated_persona")

    docs = list(persona_query.stream())
    total_docs = len(docs)
    print(f"[INFO] Found {total_docs} document(s) inside collections named 'updated_persona'.")

    if total_docs == 0:
        print("[WARN] There are no documents in any 'updated_persona' collection.")
        return rows

    for idx, doc in enumerate(docs, start=1):
        path = doc.reference.path
        data = doc.to_dict() or {}

        # Show progress for some docs
        if idx <= 10 or idx % 50 == 0 or idx == total_docs:
            print(f"\n[DOC {idx}/{total_docs}] Path: {path}")
            print(f"[DOC {idx}/{total_docs}] Fields: {list(data.keys())}")

        segments = path.split("/")

        # Only /.../updated_persona/plan
        if not segments or segments[-1] != "plan":
            continue

        # Only from Experiment_ACEGPT experiment
        if "experiments/Experiment_ACEGPT" not in path:
            continue

        user_id, week_number = parse_user_and_week_from_path(path)

        if user_id is None or week_number is None:
            print(f"[WARN] Could not parse user/week from path (skipping): {path}")
            continue

        adherence_propensity   = data.get("Adherence_propensity")
        age_band               = data.get("Age_band")
        bmi                    = data.get("BMI")
        budjet_sar_per_day     = data.get("Budjet_SAR_per_day")
        cooking_skill          = data.get("Cooking_skill")
        current_fitness_level  = data.get("Current_fitness_level")
        days_per_week          = data.get("Days_per_week")
        primary_goal           = data.get("Primary_goal")
        sex                    = data.get("Sex")
        sleep_hours            = data.get("Sleep_hours")

        # Skip if everything is None
        if all(
            value is None
            for value in [
                adherence_propensity,
                age_band,
                bmi,
                budjet_sar_per_day,
                cooking_skill,
                current_fitness_level,
                days_per_week,
                primary_goal,
                sex,
                sleep_hours,
            ]
        ):
            continue

        print(
            f"[OK]   user={user_id}, week={week_number} | "
            f"Adherence={adherence_propensity} | Age_band={age_band} | BMI={bmi} | "
            f"Budget={budjet_sar_per_day} | Cooking={cooking_skill} | Fitness={current_fitness_level} | "
            f"Days_per_week={days_per_week} | Goal={primary_goal} | Sex={sex} | Sleep_hours={sleep_hours}"
        )

        rows.append(
            {
                "user_id": user_id,
                "week_number": week_number,
                "Adherence_propensity": adherence_propensity,
                "Age_band": age_band,
                "BMI": bmi,
                "Budjet_SAR_per_day": budjet_sar_per_day,
                "Cooking_skill": cooking_skill,
                "Current_fitness_level": current_fitness_level,
                "Days_per_week": days_per_week,
                "Primary_goal": primary_goal,
                "Sex": sex,
                "Sleep_hours": sleep_hours,
            }
        )

    # Sort rows by user and week
    rows.sort(key=lambda r: (r["user_id"], str(r["week_number"])))

    print(f"\n[SUMMARY] Total rows with updated persona data: {len(rows)}")
    return rows


def write_csv(rows):
    """
    Write the collected rows into a CSV file with headers:
    'user id', 'Week number',
    'Adherence_propensity', 'Age_band', 'BMI', 'Budjet_SAR_per_day',
    'Cooking_skill', 'Current_fitness_level', 'Days_per_week',
    'Primary_goal', 'Sex', 'Sleep_hours'
    """
    print(f"[STEP] Writing data to CSV at: {OUTPUT_CSV}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    fieldnames = [
        "user id",
        "Week number",
        "Adherence_propensity",
        "Age_band",
        "BMI",
        "Budjet_SAR_per_day",
        "Cooking_skill",
        "Current_fitness_level",
        "Days_per_week",
        "Primary_goal",
        "Sex",
        "Sleep_hours",
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
                    "Adherence_propensity": r["Adherence_propensity"],
                    "Age_band": r["Age_band"],
                    "BMI": r["BMI"],
                    "Budjet_SAR_per_day": r["Budjet_SAR_per_day"],
                    "Cooking_skill": r["Cooking_skill"],
                    "Current_fitness_level": r["Current_fitness_level"],
                    "Days_per_week": r["Days_per_week"],
                    "Primary_goal": r["Primary_goal"],
                    "Sex": r["Sex"],
                    "Sleep_hours": r["Sleep_hours"],
                }
            )
            if total > 0 and (idx % 10 == 0 or idx == total):
                print(f"[WRITE]   Wrote {idx}/{total} row(s)...")

    print("[DONE] CSV file creation completed.")


def main():
    print("=== Extract updated_persona (Experiment_ACEGPT) data from Firestore to CSV ===")
    db = init_firestore()
    rows = fetch_updated_persona_data(db)

    if not rows:
        print("\n[RESULT] No rows were found containing the target updated_persona fields.")
        print("         Check that the fields exist in:")
        print("         /experiments/Experiment_ACEGPT/users/{user_id}/weeks/{week_number}/updated_persona/plan")
    else:
        write_csv(rows)
        print(f"\n✅ Done. Wrote {len(rows)} row(s) to:")
        print(f"   {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
