from google.cloud import firestore
from google.oauth2 import service_account
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import json
from pathlib import Path

from config import PROJECT_ID, SERVICE_ACCOUNT_FILE, validate_config
from acegpt_client import call_acegpt, build_firestore_payload

def get_riyadh_tz():
    try:
        return ZoneInfo("Asia/Riyadh")
    except (ZoneInfoNotFoundError, Exception):
        return timezone(timedelta(hours=3))

def get_week_id() -> str:
    tz = get_riyadh_tz()
    today = datetime.now(tz).date()
    iso_year, iso_week, _ = today.isocalendar()
    return f"Week_{iso_year}_{iso_week:02d}"

def init_firestore():
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE)
    return firestore.Client(project=PROJECT_ID, credentials=credentials)

def fetch_personas(db):
    return list(db.collection("personas").stream())  # materialize to allow counting

def save_diet_plan(db, persona_id: str, week_id: str, payload: dict):
    doc_ref = (
        db.collection("experiments").document("Experiment_ACEGPT")
        .collection("users").document(persona_id)
        .collection("weeks").document(week_id)
        .collection("diet").document("plan")
    )
    doc_ref.set(payload)
    print(f"[OK] Saved diet plan for {persona_id} @ {week_id}")

def write_report(report: dict):
    out = Path(__file__).resolve().parent / "last_run_report.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[INFO] Run report written to {out}")

def main():
    try:
        validate_config()
    except Exception as e:
        print(f"[FATAL] Config error: {e}")
        return

    db = init_firestore()
    week_id = get_week_id()
    print(f"[INFO] Using week: {week_id}")

    persona_docs = fetch_personas(db)
    fetched_ids = [d.id for d in persona_docs]
    print(f"[INFO] Personas fetched: {len(fetched_ids)} -> {fetched_ids}")

    success_ids, failed = [], []

    for persona_doc in persona_docs:
        persona_id = persona_doc.id
        pdata = persona_doc.to_dict() or {}
        print(f"\n[INFO] Processing persona: {persona_id}")

        try:
            ace = call_acegpt(persona_id, pdata)
            if not ace:
                failed.append({"id": persona_id, "reason": "acegpt_none"})
                print(f"[WARN] Skipping {persona_id} due to ACEGPT error/output issues.")
                continue

            payload = build_firestore_payload(ace)
            save_diet_plan(db, persona_id, week_id, payload)
            success_ids.append(persona_id)

        except Exception as e:
            failed.append({"id": persona_id, "reason": str(e)})
            print(f"[ERROR] {persona_id}: Exception: {e}")

    report = {
        "week_id": week_id,
        "total_personas": len(fetched_ids),
        "success_count": len(success_ids),
        "failed_count": len(failed),
        "success_ids": success_ids,
        "failed": failed,
        "fetched_ids": fetched_ids,
        "timestamp": datetime.now(get_riyadh_tz()).isoformat(timespec="seconds"),
    }
    write_report(report)

    print(f"\n[SUMMARY] Personas processed: {len(fetched_ids)}, success: {len(success_ids)}, failed: {len(failed)}")

if __name__ == "__main__":
    main()
