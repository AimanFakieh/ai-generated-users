

from __future__ import annotations

import os
import sys
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

import pytz
from dateutil import tz  # (kept in case you want later use)
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from google.cloud import firestore
from openai import OpenAI

# ----------------------------
# Configuration
# ----------------------------

# Correct Firestore project ID
PROJECT_ID = "fitech-2nd-trail"

# Default OpenAI model (you can override with env var MODEL)
# Choose a model that supports response_format={"type": "json_object"}.
DEFAULT_MODEL = os.getenv("MODEL", "gpt-4.1-mini")

# Local timezone for week/date/time
TIMEZONE = pytz.timezone("Asia/Riyadh")

# Map persona_id -> user_id if different; by default we use persona_id as user_id
USER_ID_MAP: Dict[str, str] = {
    # "P01": "user_001",
}

# To test only some personas, set e.g. {"P01", "P02"}; keep None to run all
ALLOWLIST: Optional[set[str]] = None

# Init OpenAI client (uses OPENAI_API_KEY from env)
client = OpenAI()


# ----------------------------
# Helper functions
# ----------------------------

def _iso_week_riyadh(now: Optional[datetime] = None) -> str:
    """Return ISO year-week string using Asia/Riyadh local date, e.g., '2025-W46'."""
    local_now = (now or datetime.utcnow()).astimezone(TIMEZONE)
    iso_year, iso_week, _ = local_now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _today_local_strings() -> tuple[str, str]:
    """Return (date_str, time_str) in Asia/Riyadh, e.g., ('2025-11-10','10:12:00')."""
    local_now = datetime.utcnow().astimezone(TIMEZONE)
    return local_now.strftime("%Y-%m-%d"), local_now.strftime("%H:%M:%S")


def _extract_persona_fields(doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """Pull the requested persona fields, handling spelling variants safely."""

    def get(*keys):
        for k in keys:
            if k in doc_data and doc_data[k] is not None:
                return doc_data[k]
        return None

    return {
        "Age_band": get("Age_band"),
        "Sex": get("Sex"),
        "BMI": get("BMI"),
        "Weight_kg": get("Weight_kg"),
        "Muscle_mass_kg": get("Muscle_mass_kg"),
        "Fat_percent": get("Fat_percent"),
        "Days_per_week": get("Days_per_week"),
        "Current_fitness_level": get("Current_fitness_level"),
        "Primary_goal": get("Primary_goal"),
        "Sleep_hours": get("Sleep_hours"),
        "Adherence_propensity": get("Adherence_propensity"),
        "Cooking_skill": get("Cooking_skill"),
        # typo-safe for budget
        "Budjet_SAR_per_day": get("Budjet_SAR_per_day", "Budget_SAR_per_day", "Daily_budget_SAR"),
        # optional extras if present
        "Allergies": get("Allergies", "allergies"),
        "Barriers": get("Barriers", "Diet_barriers"),
        "Supplements": get("Supplements", "Supps"),
    }


def _build_system_prompt() -> str:
    """Base system prompt for the nutritionist behavior."""
    return (
        "You are a licensed nutritionist specializing in Saudi cuisine and sports nutrition. "
        "You design sustainable, realistic one-day diet plans (repeatable for a full week) using mostly Saudi foods. "
        "You must consider: age, sex, BMI, weight, body fat, muscle mass, primary goal, training frequency and intensity, "
        "sleep duration, adherence level, cooking skill, daily budget, allergies, barriers, and supplement preferences. "
        "You MUST return exactly the JSON structure requested—no markdown, no explanations outside JSON."
    )


def _build_user_prompt(persona_id: str, p: Dict[str, Any]) -> str:
    """User prompt containing persona data + instructions."""
    lines = [
        f"Persona ID: {persona_id}",
        "Design ONE DAY diet plan with 4 meals:",
        " - 1st_meal = breakfast",
        " - 2nd_meal = snack",
        " - 3rd_meal = lunch",
        " - 4th_meal = dinner",
        "This single day will be repeated for a full week.",
        "",
        "Requirements:",
        "- Use mostly Saudi / Arabian-context foods and dishes (tamees, ful, shakshouka, kabsa, jareesh, harees, dates, laban, labneh, khubz, etc.).",
        "- Keep it realistic and practical for the persona's budget and cooking_skill.",
        "- Adjust calories and macros to fit the persona's Primary_goal and training days.",
        "- Respect allergies / barriers / restrictions if provided.",
        "- For EACH meal, include approximate kcal, carbs_g, fat_g, protein_g, fiber_g, sodium_mg.",
        "- At the end, totals for kcal, carbs, fat, protein, fiber, sodium must be consistent with meal sums.",
        "",
        "Persona data JSON:",
        json.dumps(p, ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)


# ----------------------------
# OpenAI + retry
# ----------------------------

class OpenAITransientError(Exception):
    """Marker for retry-able OpenAI issues."""
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1.5, min=2, max=20),
    retry=retry_if_exception_type((OpenAITransientError,))
)
def generate_plan_for_persona(persona_id: str, persona_fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call OpenAI (chat.completions) to generate a structured one-day Saudi-style diet plan.

    We enforce JSON output with specific keys using response_format={"type": "json_object"}.
    """
    date_str, time_str = _today_local_strings()

    required_fields = [
        "Date", "Time", "Note",
        "Total_kcal_target_kcal", "Total_carbs_g", "Total_fat_g",
        "Total_protein_g", "Total_fiber_g", "Total_sodium_mg",
        "1st_meal", "1st_meal_kcal_target_kcal", "1st_meal_carbs_g",
        "1st_meal_fat_g", "1st_meal_protein_g", "1st_meal_fiber_g", "1st_meal_sodium_mg",
        "2nd_meal", "2nd_meal_kcal_target_kcal", "2nd_meal_carbs_g",
        "2nd_meal_fat_g", "2nd_meal_protein_g", "2nd_meal_fiber_g", "2nd_meal_sodium_mg",
        "3rd_meal", "3rd_meal_kcal_target_kcal", "3rd_meal_carbs_g",
        "3rd_meal_fat_g", "3rd_meal_protein_g", "3rd_meal_fiber_g", "3rd_meal_sodium_mg",
        "4th_meal", "4th_meal_kcal_target_kcal", "4th_meal_carbs_g",
        "4th_meal_fat_g", "4th_meal_protein_g", "4th_meal_fiber_g", "4th_meal_sodium_mg",
    ]

    fields_description = (
        "Return a SINGLE JSON object with EXACTLY these keys:\n"
        + ", ".join(f'"{k}"' for k in required_fields)
        + ". "
        "Each macro field must be numeric. "
        "Each meal field ('1st_meal'..'4th_meal') must be a descriptive string: Saudi-style dish name(s), "
        "portions in grams/cups, and short preparation notes. "
        "Do not add any extra keys. Do not wrap the JSON in markdown."
    )

    system_prompt = (
        _build_system_prompt()
        + f" Current local date/time (Asia/Riyadh): {date_str} {time_str}. "
        + fields_description
    )

    user_prompt = _build_user_prompt(persona_id, persona_fields)

    try:
        resp = client.chat.completions.create(
            model=DEFAULT_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except Exception as e:
        # Allow retry on transient errors (rate limits, timeouts, etc.)
        raise OpenAITransientError(str(e)) from e

    # Parse JSON from response
    try:
        content = resp.choices[0].message.content
        data = json.loads(content)
    except Exception as ex:
        raise RuntimeError(
            f"Model did not return valid JSON for {persona_id}: {ex} | raw={getattr(resp.choices[0].message, 'content', '')!r}"
        )

    # Ensure Date/Time
    data["Date"] = data.get("Date") or date_str
    data["Time"] = data.get("Time") or time_str

    # Validate required keys
    missing = [k for k in required_fields if k not in data]
    if missing:
        raise RuntimeError(f"Missing expected keys in model output for {persona_id}: {missing}")

    return data


# ----------------------------
# Firestore I/O
# ----------------------------

def get_db() -> firestore.Client:
    """Initialize Firestore client for PROJECT_ID."""
    return firestore.Client(project=PROJECT_ID)


def read_all_personas(db: firestore.Client) -> List[tuple[str, Dict[str, Any]]]:
    """Read all persona docs from /personas."""
    docs = db.collection("personas").stream()
    results: List[tuple[str, Dict[str, Any]]] = []
    for d in docs:
        pid = d.id
        if ALLOWLIST and pid not in ALLOWLIST:
            continue
        results.append((pid, d.to_dict() or {}))
    return results


def write_diet_plan(
    db: firestore.Client,
    user_id: str,
    week_number: str,
    payload: Dict[str, Any],
) -> None:
    """
    Write the generated diet plan to:
    /experiments/Experiment_OpenAI/users/{user_id}/weeks/{week_number}/diet/plan
    """
    (
        db.collection("experiments")
        .document("Experiment_OpenAI")
        .collection("users")
        .document(user_id)
        .collection("weeks")
        .document(week_number)
        .collection("diet")
        .document("plan")
        .set(payload, merge=True)
    )


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("[ERROR] OPENAI_API_KEY not set in environment.")
        return 2

    # Init Firestore
    try:
        db = get_db()
    except Exception as e:
        print("[ERROR] Could not init Firestore client. Check GOOGLE_APPLICATION_CREDENTIALS and IAM permissions.")
        print(str(e))
        return 3

    personas = read_all_personas(db)
    if not personas:
        print("[WARN] No personas found at /personas.")
        return 0

    week_number = _iso_week_riyadh()
    print(f"[INFO] Target week: {week_number}")

    processed = 0
    for persona_id, raw in personas:
        user_id = USER_ID_MAP.get(persona_id, persona_id)
        fields = _extract_persona_fields(raw)

        critical = ["Age_band", "Sex", "BMI", "Weight_kg", "Primary_goal"]
        missing = [k for k in critical if not fields.get(k)]
        if missing:
            print(f"[WARN] {persona_id}: Missing critical fields {missing}. Proceeding with available data.")

        try:
            diet = generate_plan_for_persona(persona_id, fields)
            write_diet_plan(db, user_id, week_number, diet)
            print(f"[OK] {persona_id} -> users/{user_id}/weeks/{week_number}/diet/plan")
            processed += 1
        except Exception as e:
            print(f"[ERROR] {persona_id}: {e}")

    print(f"[DONE] Processed {processed} persona(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
