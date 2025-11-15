# firestore_io_seed_v9.py
from google.cloud import firestore
from google.oauth2 import service_account
from typing import Dict, List, Optional

from config_seed_v9 import PROJECT_ID, SERVICE_ACCOUNT_PATH

def get_db() -> firestore.Client:
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH)
    return firestore.Client(project=PROJECT_ID, credentials=creds)

def list_persona_ids(db) -> List[str]:
    docs = db.collection("personas").stream()
    return sorted([d.id for d in docs])

def read_persona(db, pid: str) -> Dict:
    snap = db.collection("personas").document(pid).get()
    return snap.to_dict() or {}

def read_diet_for_week(db, user_id: str, week_id: str) -> Optional[Dict]:
    doc_ref = (db.collection("experiments")
                 .document("Experiment_ACEGPT")
                 .collection("users").document(user_id)
                 .collection("weeks").document(week_id)
                 .collection("diet").document("plan"))
    snap = doc_ref.get()
    return snap.to_dict() if snap.exists else None

def read_workout(db, wid: str) -> Optional[Dict]:
    snap = db.collection("workouts").document(wid).get()
    return snap.to_dict() if snap.exists else None

def write_logs(db, experiment: str, user_id: str, week_id: str, data: Dict) -> None:
    (db.collection("experiments").document(experiment)
       .collection("users").document(user_id)
       .collection("weeks").document(week_id)
       .collection("logs").document("plan")).set(data)

def write_updated_persona(db, experiment: str, user_id: str, week_id: str, data: Dict) -> None:
    (db.collection("experiments").document(experiment)
       .collection("users").document(user_id)
       .collection("weeks").document(week_id)
       .collection("updated_persona").document("plan")).set(data)
