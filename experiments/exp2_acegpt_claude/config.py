

import os
from typing import List

# ---------- Firestore ----------
PROJECT_ID = "fitech-2nd-trail"

# Use your given service account file (Windows path; raw string to avoid escapes)
SERVICE_ACCOUNT_FILE = r"C:\Users\fakias0a\secrets\fitech-2nd-trail-e978c70041a0.json"

# Collections / roots your scripts may reference
PERSONAS_COLLECTION = "personas"  # /personas/{persona_id}
EXPERIMENT_ROOT = "experiments/Experiment_ACEGPT"  # /experiments/Experiment_ACEGPT/...

# Timezone (used for week id, timestamps)
LOCAL_TZ_NAME = "Asia/Riyadh"

# ---------- Hugging Face vLLM Endpoint (OpenAI-compatible) ----------
ACEGPT_BASE_URL = "https://ydtqwx4q0fm1jeq0.us-east-1.aws.endpoints.huggingface.cloud"
ACEGPT_CHAT_URL = f"{ACEGPT_BASE_URL}/v1/chat/completions"
ACEGPT_COMPLETIONS_URL = f"{ACEGPT_BASE_URL}/v1/completions"

# Model deployed on the endpoint
ACEGPT_MODEL_NAME = "FreedomIntelligence/AceGPT-13B-chat"

# Auth: prefer HF_API_KEY; fall back to HF_API_TOKEN if that’s what you set
HF_API_KEY = os.getenv("HF_API_KEY") or os.getenv("HF_API_TOKEN") or ""

# ---------- Validation helper ----------
def _missing_fields() -> List[str]:
    missing: List[str] = []
    if not PROJECT_ID:
        missing.append("PROJECT_ID")
    if not SERVICE_ACCOUNT_FILE:
        missing.append("SERVICE_ACCOUNT_FILE (path not set)")
    else:
        try:
            import os as _os
            if not _os.path.exists(SERVICE_ACCOUNT_FILE):
                missing.append(f"SERVICE_ACCOUNT_FILE not found: {SERVICE_ACCOUNT_FILE}")
        except Exception:
            missing.append(f"SERVICE_ACCOUNT_FILE check failed: {SERVICE_ACCOUNT_FILE}")

    if not ACEGPT_CHAT_URL:
        missing.append("ACEGPT_CHAT_URL")
    if not ACEGPT_COMPLETIONS_URL:
        missing.append("ACEGPT_COMPLETIONS_URL")
    if not ACEGPT_MODEL_NAME:
        missing.append("ACEGPT_MODEL_NAME")
    if not HF_API_KEY:
        missing.append("HF_API_KEY (or HF_API_TOKEN) env var not set")
    return missing

def validate_config(raise_on_error: bool = True) -> bool:
    """
    Returns True if config looks usable; otherwise prints what’s missing.
    If raise_on_error=True, raises RuntimeError on missing items.
    """
    missing = _missing_fields()
    if missing:
        msg = "[config] Missing/invalid:\n  - " + "\n  - ".join(missing)
        if raise_on_error:
            raise RuntimeError(msg)
        else:
            print(msg)
            return False
    return True
