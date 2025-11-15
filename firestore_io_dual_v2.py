# --- firestore_io_dual_v2.py ---
from typing import Dict, Any, List
from google.oauth2 import service_account
from google.cloud import firestore

from config_dual import (
    PROJECT_ID,
    SERVICE_ACCOUNT_PATH,
    PERSONAS_ROOT,
    EXPERIMENT_ROOT,      # "experiments/ACEGPT_ACEGPT"
    LEGACY_DIETS_ROOT,    # "experiments/Experiment_ACEGPT"
)

__all__ = [
    "_client","list_persona_ids","read_persona","read_legacy_week46_diet",
    "read_updated_persona","read_diet","write_diet","write_logs","write_updated_persona"
]

def _client() -> firestore.Client:
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_PATH)
    return firestore.Client(project=PROJECT_ID, credentials=creds)

def _doc_to_dict(snap: firestore.DocumentSnapshot) -> Dict[str, Any]:
    return snap.to_dict() if snap and snap.exists else {}

def _path_ref(db: firestore.Client, path: str):
    parts = [p for p in path.split("/") if p]
    ref = db
    for i, p in enumerate(parts):
        if i % 2 == 0:
            ref = ref.collection(p)
        else:
            ref = ref.document(p)
    return ref

# -------- Personas --------
def list_persona_ids() -> List[str]:
    db = _client()
    return [d.id for d in db.collection(PERSONAS_ROOT).stream()]

def read_persona(pid: str) -> Dict[str, Any]:
    db = _client()
    snap = db.collection(PERSONAS_ROOT).document(pid).get()
    return _doc_to_dict(snap)

# -------- Legacy seed Week_2025_46 diet --------
def read_legacy_week46_diet(pid: str) -> Dict[str, Any]:
    db = _client()
    root = _path_ref(db, LEGACY_DIETS_ROOT)
    snap = (
        root.collection("users").document(pid)
            .collection("weeks").document("Week_2025_46")
            .collection("diet").document("plan")
            .get()
    )
    return _doc_to_dict(snap)

# -------- New experiment tree (ACEGPT_ACEGPT) --------
def read_updated_persona(pid: str, week_id: str) -> Dict[str, Any]:
    db = _client()
    root = _path_ref(db, EXPERIMENT_ROOT)
    snap = (
        root.collection("users").document(pid)
            .collection("weeks").document(week_id)
            .collection("updated_persona").document("plan")
            .get()
    )
    data = _doc_to_dict(snap)
    return data if data else read_persona(pid)

def read_diet(pid: str, week_id: str) -> Dict[str, Any]:
    db = _client()
    root = _path_ref(db, EXPERIMENT_ROOT)
    snap = (
        root.collection("users").document(pid)
            .collection("weeks").document(week_id)
            .collection("diet").document("plan")
            .get()
    )
    return _doc_to_dict(snap)

def write_diet(pid: str, week_id: str, payload: Dict[str, Any]) -> None:
    db = _client()
    root = _path_ref(db, EXPERIMENT_ROOT)
    (
        root.collection("users").document(pid)
            .collection("weeks").document(week_id)
            .collection("diet").document("plan")
            .set(payload)
    )

def write_logs(pid: str, week_id: str, payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise TypeError("write_logs expects a dict payload.")
    db = _client()
    root = _path_ref(db, EXPERIMENT_ROOT)
    (
        root.collection("users").document(pid)
            .collection("weeks").document(week_id)
            .collection("logs").document("plan")
            .set(payload)
    )

def write_updated_persona(pid: str, week_id: str, payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise TypeError("write_updated_persona expects a dict payload.")
    db = _client()
    root = _path_ref(db, EXPERIMENT_ROOT)
    (
        root.collection("users").document(pid)
            .collection("weeks").document(week_id)
            .collection("updated_persona").document("plan")
            .set(payload)
    )
