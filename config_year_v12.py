# config_year_v12.py
PROJECT_ID = "fitech-2nd-trail"
SERVICE_ACCOUNT_PATH = r"C:\Users\fakias0a\secrets\fitech-2nd-trail-e978c70041a0.json"

START_WEEK_ID = "Week_2025_46"
TOTAL_WEEKS = 54
INCLUDE_START_WEEK = False  # start the loop from 47 if 46 already exists

WORKOUT_MAP = {
    3: ["W33", "W29", "W21"],
    4: ["W25", "W21", "W25", "W21"],
    5: ["W03", "W07", "W11", "W15", "W21"],
}

RIYADH_TZ = "Asia/Riyadh"

# Claude (Anthropic)
ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
ANTHROPIC_URL   = "https://api.anthropic.com/v1/messages"
CLAUDE_TEMPERATURE = 0.6

# AceGPT (HF endpoint)
ACE_MAX_TOKENS = 650
ACE_TEMPERATURE = 0.6
