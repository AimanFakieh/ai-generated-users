# firestore_io_year_v11.py
from typing import Dict, List, Optional
from google.cloud import firestore
from google.oauth2 import service_account
from config_year_v11 import PROJECT_ID, SERVICE_ACCOUNT_PATH

def get_db() -> firestore.Client:
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH)
    return firestore.Client(project=PROJECT_ID, credentials=creds)

def list_persona_ids(db) -> List[str]:
    docs = db.collection("personas").stream()
    return sorted([d.id for d in docs])

def read_persona_base(db, pid: str) -> Dict:
    snap = db.collection("personas").document(pid).get()
    d = snap.to_dict() or {}
    d["ID"] = pid
    return d

def read_updated_persona(db, pid: str, week_id: str) -> Optional[Dict]:
    ref = (db.collection("experiments").document("Experiment_ACEGPT")
           .collection("users").document(pid)
           .collection("weeks").document(week_id)
           .collection("updated_persona").document("plan"))
    s = ref.get()
    return s.to_dict() if s.exists else None

def read_diet(db, pid: str, week_id: str) -> Optional[Dict]:
    ref = (db.collection("experiments").document("Experiment_ACEGPT")
           .collection("users").document(pid)
           .collection("weeks").document(week_id)
           .collection("diet").document("plan"))
    s = ref.get()
    return s.to_dict() if s.exists else None

def write_diet(db, pid: str, week_id: str, diet: Dict):
    (db.collection("experiments").document("Experiment_ACEGPT")
       .collection("users").document(pid)
       .collection("weeks").document(week_id)
       .collection("diet").document("plan")).set(diet)

def write_logs(db, experiment: str, pid: str, week_id: str, data: Dict):
    (db.collection("experiments").document(experiment)
       .collection("users").document(pid)
       .collection("weeks").document(week_id)
       .collection("logs").document("plan")).set(data)

def write_updated_persona(db, experiment: str, pid: str, week_id: str, data: Dict):
    (db.collection("experiments").document(experiment)
       .collection("users").document(pid)
       .collection("weeks").document(week_id)
       .collection("updated_persona").document("plan")).set(data)

def read_workout(db, wid: str) -> Optional[Dict]:
    s = db.collection("workouts").document(wid).get()
    return s.to_dict() if s.exists else None
