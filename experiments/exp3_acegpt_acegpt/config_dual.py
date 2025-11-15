# --- Acegpt_Acegpt/config_dual.py ---

# Firestore
PROJECT_ID = "fitech-2nd-trail"
SERVICE_ACCOUNT_PATH = r"C:\Users\aiman\PycharmProjects\fitech-2nd-trail-service-account.json"

# Firestore paths
PERSONAS_ROOT     = "personas"
EXPERIMENT_ROOT   = "experiments/ACEGPT_ACEGPT"
LEGACY_DIETS_ROOT = "experiments/Experiment_ACEGPT"

# Time / Weeks
RIYADH_TZ = "Asia/Riyadh"
START_WEEK_ID = "Week_2025_46"
TOTAL_WEEKS = 54
INCLUDE_START_WEEK = True

# Map training days -> workout IDs to follow that week
WORKOUT_MAP = {
    3: ["W33", "W29", "W21"],
    4: ["W25", "W21", "W25", "W21"],
    5: ["W03", "W07", "W11", "W15", "W21"],
}

# AceGPT (HF Inference Endpoint via vLLM OpenAI-compatible routes)
ACEGPT_BASE_URL        = "https://ydtqwx4q0fm1jeq0.us-east-1.aws.endpoints.huggingface.cloud"
ACEGPT_COMPLETIONS_URL = ACEGPT_BASE_URL + "/v1/completions"
ACEGPT_CHAT_URL        = ACEGPT_BASE_URL + "/v1/chat/completions"

# Some modules expect these names — provide aliases
HF_COMPLETIONS_URL = ACEGPT_COMPLETIONS_URL
HF_CHAT_URL        = ACEGPT_CHAT_URL

# Model identifiers (used for logging/metadata by clients)
ACE_MODEL    = "FreedomIntelligence/AceGPT-13B-chat"
ACE_PROVIDER = "huggingface-vllm-openai"

# Build auth headers for HF endpoint
def hf_headers():
    import os
    key = os.environ.get("HF_API_KEY") or os.environ.get("HF_API_TOKEN")
    if not key:
        raise RuntimeError("Missing HF_API_KEY (or HF_API_TOKEN) in environment.")
    return {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
    }

# Sensible generation defaults
DEFAULT_MAX_TOKENS  = 512
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P       = 0.95
DEFAULT_STOP        = ["</s>"]

# ---- Aliases some modules import directly (avoid ImportError) ----
ACE_MAX_TOKENS  = DEFAULT_MAX_TOKENS
ACE_TEMPERATURE = DEFAULT_TEMPERATURE
ACE_TOP_P       = DEFAULT_TOP_P
ACE_STOP        = DEFAULT_STOP

# Optional networking/retry knobs (used by some clients)
ACE_TIMEOUT_S   = 60
ACE_MAX_RETRIES = 3

# If code refers to "agent 1/2" endpoints, keep them pointing to the same endpoint
ACEGPT_1_URL = ACEGPT_COMPLETIONS_URL
ACEGPT_2_URL = ACEGPT_COMPLETIONS_URL
