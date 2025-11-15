
from __future__ import annotations

import os
import re
import json
import time
import typing as T
import traceback
from datetime import datetime, timedelta

import requests
import pytz
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryError
from google.cloud import firestore

try:
    from anthropic import Anthropic
except Exception:  # pragma: no cover
    Anthropic = None  # type: ignore

# ---------------------------- CONFIG ---------------------------------
PROJECT_ID = os.getenv("GCP_PROJECT", "fitech-2nd-trail")
TZ = pytz.timezone("Asia/Riyadh")

START_WEEK = os.getenv("START_WEEK", "2025-W46")
N_WEEKS = int(os.getenv("N_WEEKS", "54"))

ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

WORKOUT_CHOICE: dict[int, list[str]] = {
    3: ["W33", "W29", "W21"],
    4: ["W25", "W21", "W25", "W21"],
    5: ["W03", "W07", "W11", "W15", "W21"],
}

SLEEP_BETWEEN_PERSONAS = float(os.getenv("SLEEP_BETWEEN_PERSONAS", "0.4"))
SLEEP_BETWEEN_WEEKS = float(os.getenv("SLEEP_BETWEEN_WEEKS", "1.0"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ---------------------------- UTILS ----------------------------------

def now_strings() -> tuple[str, str]:
    dt = datetime.now(TZ)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")


def iso_week_to_monday_date(iso_week: str) -> datetime:
    year_s, week_s = iso_week.split("-W")
    year, week = int(year_s), int(week_s)
    jan4 = datetime(year, 1, 4, tzinfo=TZ)
    week1_monday = jan4 - timedelta(days=(jan4.isoweekday() - 1))
    monday = week1_monday + timedelta(weeks=week - 1)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


def add_weeks(iso_week: str, n: int) -> str:
    monday = iso_week_to_monday_date(iso_week)
    monday2 = monday + timedelta(weeks=n)
    year, week, _ = monday2.isocalendar()
    return f"{year}-W{week:02d}"


def clean_value(v: T.Any) -> T.Any:
    try:
        if hasattr(v, "isoformat"):
            return str(v)
        if isinstance(v, (int, float, str, bool)) or v is None:
            return v
        if isinstance(v, (list, tuple)):
            return [clean_value(x) for x in v]
        if isinstance(v, dict):
            return {str(k): clean_value(val) for k, val in v.items()}
        return str(v)
    except Exception:
        return str(v)


def strip_nanoseconds(d: dict) -> dict:
    return {k: clean_value(v) for k, v in (d or {}).items()}


def clamp(x: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo

# ---------------------------- FIRESTORE I/O ---------------------------

def fs_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def read_doc(db: firestore.Client, path: str) -> dict:
    doc = db.document(path).get()
    return strip_nanoseconds(doc.to_dict() or {})


def write_doc(db: firestore.Client, path: str, data: dict) -> None:
    db.document(path).set(strip_nanoseconds(data), merge=True)


def exists(db: firestore.Client, path: str) -> bool:
    return db.document(path).get().exists


def list_persona_ids(db: firestore.Client) -> list[str]:
    ids = [doc.id for doc in db.collection("personas").stream()]
    ids.sort()
    return ids


def read_updated_persona(db: firestore.Client, user_id: str, week: str) -> dict:
    path = f"experiments/Experiment_OpenAI/users/{user_id}/weeks/{week}/updated_persona/plan"
    d = read_doc(db, path)
    if d:
        return d
    return read_doc(db, f"personas/{user_id}")


def read_diet(db: firestore.Client, user_id: str, week: str) -> dict:
    path = f"experiments/Experiment_OpenAI/users/{user_id}/weeks/{week}/diet/plan"
    return read_doc(db, path)


def pick_workouts(days_per_week: int) -> list[str]:
    return WORKOUT_CHOICE.get(int(days_per_week or 3), WORKOUT_CHOICE[3])


def read_workout_blurbs(db: firestore.Client, workout_ids: list[str]) -> dict[str, str]:
    out = {}
    for wid in workout_ids:
        d = read_doc(db, f"workouts/{wid}")
        out[wid] = d.get("summary") or d.get("title") or wid
    return out

# ---------------------------- OPENAI (DIET) --------------------------

class DietAPIError(Exception):
    pass


def try_parse_json(s: str) -> T.Any:
    s = (s or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(json)?", "", s).strip()
        s = re.sub(r"```$", "", s).strip()
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    return json.loads(s)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((requests.RequestException, DietAPIError)),
)
def openai_generate_diet(persona: dict, *, next_week: str, prev_diet: dict | None) -> dict:
    if not OPENAI_API_KEY:
        raise DietAPIError("OPENAI_API_KEY is not set")

    system = (
        "You are a licensed sports nutritionist. Design a ONE-DAY meal plan using mostly Saudi foods and realistic dishes. "
        "Respect allergies/barriers/budget/supplement preferences if present. Align with the user's primary goal. "
        "Ensure practical meals with kcal/macros per meal and totals. Output STRICT JSON ONLY."
    )

    fields = [
        "Age_band", "Sex", "BMI", "Weight_kg", "Muscle_mass_kg", "Fat_percent",
        "Days_per_week", "Current_fitness_level", "Primary_goal", "Sleep_hours",
        "Adherence_propensity", "Cooking_skill", "Budjet_SAR_per_day",
        "Allergies", "Supplements_preference", "Biggest_barrier", "Injury_history",
    ]
    P = {k: persona.get(k) for k in fields if k in persona}

    prev_summary = None
    if prev_diet:
        prev_summary = {
            "Total_kcal_target_kcal": prev_diet.get("Total_kcal_target_kcal"),
            "1st_meal": prev_diet.get("1st_meal"),
            "2nd_meal": prev_diet.get("2nd_meal"),
            "3rd_meal": prev_diet.get("3rd_meal"),
            "4th_meal": prev_diet.get("4th_meal"),
        }

    user_payload = {
        "task": "Generate one-day Saudi-style diet repeated for 7 days",
        "week_label": next_week,
        "persona": P,
        "previous_week_diet": prev_summary,
        "requirements": [
            "Use mostly Saudi foods and realistic dishes",
            "Respect allergies, barriers, budget, and supplements preference",
            "Target realistic daily calories given stats and goal",
            "Consider training days/intensity and sleep",
            "Ensure proper macro distribution",
            "Provide kcal/macros per meal and totals",
            "IMPORTANT: If previous_week_diet is given, DIVERSIFY meals and not repeat the same dishes",
        ],
        "output_schema": {
            "Date": "YYYY-MM-DD (string)",
            "Time": "HH:MM:SS (string)",
            "Note": "string",
            "Total_kcal_target_kcal": "number",
            "Total_carbs_g": "number",
            "Total_fat_g": "number",
            "Total_protein_g": "number",
            "Total_fiber_g": "number",
            "Total_sodium_mg": "number",
            "1st_meal": "string",
            "1st_meal_kcal_target_kcal": "number",
            "1st_meal_carbs_g": "number",
            "1st_meal_fat_g": "number",
            "1st_meal_protein_g": "number",
            "1st_meal_fiber_g": "number",
            "1st_meal_sodium_mg": "number",
            "2nd_meal": "string",
            "2nd_meal_kcal_target_kcal": "number",
            "2nd_meal_carbs_g": "number",
            "2nd_meal_fat_g": "number",
            "2nd_meal_protein_g": "number",
            "2nd_meal_fiber_g": "number",
            "2nd_meal_sodium_mg": "number",
            "3rd_meal": "string",
            "3rd_meal_kcal_target_kcal": "number",
            "3rd_meal_carbs_g": "number",
            "3rd_meal_fat_g": "number",
            "3rd_meal_protein_g": "number",
            "3rd_meal_fiber_g": "number",
            "3rd_meal_sodium_mg": "number",
            "4th_meal": "string",
            "4th_meal_kcal_target_kcal": "number",
            "4th_meal_carbs_g": "number",
            "4th_meal_fat_g": "number",
            "4th_meal_protein_g": "number",
            "4th_meal_fiber_g": "number",
            "4th_meal_sodium_mg": "number",
        },
        "json_instructions": "Return ONLY valid JSON. No Markdown, no code fences.",
    }

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.7,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }

    try:
        r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise DietAPIError(f"OpenAI request error: {e}")

    if r.status_code >= 300:
        snippet = r.text[:500]
        raise DietAPIError(f"OpenAI error {r.status_code}: {snippet}")

    data = r.json()
    try:
        text = data["choices"][0]["message"]["content"].strip()
    except Exception:
        raise DietAPIError(f"Malformed OpenAI response: {data}")

    diet = try_parse_json(text)
    if not isinstance(diet, dict):
        raise DietAPIError("Diet output was not a JSON object")

    if not diet.get("Date") or not diet.get("Time"):
        date_s, time_s = now_strings()
        diet.setdefault("Date", date_s)
        diet.setdefault("Time", time_s)

    return diet

# ---------------------------- ANTHROPIC (SIM) ------------------------

class ClaudeAPIError(Exception):
    pass


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(ClaudeAPIError),
)
def claude_simulate_week(persona: dict, diet: dict, workouts: dict[str, str]) -> dict:
    if not ANTHROPIC_API_KEY or Anthropic is None:
        raise ClaudeAPIError("Anthropic SDK not available or ANTHROPIC_API_KEY not set")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    system = (
        "You will act as the PERSONA described. You just completed 7 days following the diet plan and the assigned workouts. "
        "Report realistic outcomes for ONE WEEK. Keep changes modest and physiologically plausible. "
        "Return STRICT JSON only with the requested fields."
    )

    persona_in = {
        k: persona.get(k)
        for k in [
            "Adherence_propensity", "Age_band", "Sex", "BMI", "Biggest_barrier",
            "Current_fitness_level", "Days_per_week", "Weight_kg", "Muscle_mass_kg",
            "Fat_percent", "Injury_history", "Motivation_to_workout", "Sleep_hours",
            "Primary_goal", "Cooking_skill", "Budjet_SAR_per_day",
        ]
        if k in persona
    }

    diet_in = {
        k: diet.get(k)
        for k in [
            "Total_kcal_target_kcal", "Total_carbs_g", "Total_fat_g", "Total_protein_g",
            "Total_fiber_g", "Total_sodium_mg",
            "1st_meal", "1st_meal_kcal_target_kcal", "1st_meal_carbs_g", "1st_meal_fat_g", "1st_meal_protein_g", "1st_meal_fiber_g", "1st_meal_sodium_mg",
            "2nd_meal", "2nd_meal_kcal_target_kcal", "2nd_meal_carbs_g", "2nd_meal_fat_g", "2nd_meal_protein_g", "2nd_meal_fiber_g", "2nd_meal_sodium_mg",
            "3rd_meal", "3rd_meal_kcal_target_kcal", "3rd_meal_carbs_g", "3rd_meal_fat_g", "3rd_meal_protein_g", "3rd_meal_fiber_g", "3rd_meal_sodium_mg",
            "4th_meal", "4th_meal_kcal_target_kcal", "4th_meal_carbs_g", "4th_meal_fat_g", "4th_meal_protein_g", "4th_meal_fiber_g", "4th_meal_sodium_mg",
        ]
        if k in diet
    }

    user_prompt = {
        "persona": persona_in,
        "diet": diet_in,
        "workouts": workouts,
        "instructions": [
            "Assume you attempted to follow the plan proportional to your Adherence_propensity (0..1).",
            "Provide weekly averages; daily detail is not needed.",
            "Bound weekly body changes to plausible ranges: weight ±0.0..1.2 kg, muscle ±0.0..0.4 kg, fat_pct ±0.0..1.2% (direction depends on goal/adherence).",
            "Sleep_avg_hours should be close to persona Sleep_hours unless adherence/barriers impacted it.",
            "Return ONLY JSON fields listed below.",
        ],
        "output_schema": {
            "Date": "YYYY-MM-DD (string)",
            "Time": "HH:MM:SS (string)",
            "free_text_feedback": "string",
            "notes": "string",
            "daily_avg_kcal": "number",
            "Pre_weight_kg": "number",
            "Pre_muscle_kg": "number",
            "Pre_fat_pct": "number",
            "Post_weight_kg": "number",
            "Post_muscle_kg": "number",
            "Post_fat_pct": "number",
            "delta_weight_kg": "number",
            "delta_muscle_kg": "number",
            "delta_fat_pct": "number",
            "sleep_avg_hours": "number",
        },
        "json_instructions": "Return ONLY valid JSON. No Markdown, no code fences.",
    }

    try:
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1200,
            temperature=0.3,
            system=system,
            messages=[{"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)}],
        )
    except Exception as e:
        raise ClaudeAPIError(f"Anthropic request error: {e}")

    parts = getattr(msg, "content", [])
    text = ""
    if parts and hasattr(parts[0], "text"):
        text = parts[0].text
    elif isinstance(parts, list) and parts:
        m0 = parts[0]
        if isinstance(m0, dict) and "text" in m0:
            text = m0["text"]
    text = (text or "").strip()

    if not text:
        raise ClaudeAPIError("Empty response from Claude")

    data = try_parse_json(text)
    if not isinstance(data, dict):
        raise ClaudeAPIError("Claude output was not JSON object")

    # Stamp date/time if missing
    date_s, time_s = now_strings()
    data.setdefault("Date", date_s)
    data.setdefault("Time", time_s)

    # Pre/post clamps
    def _sg(d: dict, k: str, default: float) -> float:
        try:
            v = d.get(k, default)
            return float(v)
        except Exception:
            return float(default)

    pre_w = _sg(data, "Pre_weight_kg", persona.get("Weight_kg", 0.0))
    pre_m = _sg(data, "Pre_muscle_kg", persona.get("Muscle_mass_kg", 0.0))
    pre_f = _sg(data, "Pre_fat_pct", persona.get("Fat_percent", 0.0))

    post_w = _sg(data, "Post_weight_kg", pre_w)
    post_m = _sg(data, "Post_muscle_kg", pre_m)
    post_f = _sg(data, "Post_fat_pct", pre_f)

    data.setdefault("delta_weight_kg", round(post_w - pre_w, 3))
    data.setdefault("delta_muscle_kg", round(post_m - pre_m, 3))
    data.setdefault("delta_fat_pct", round(post_f - pre_f, 3))

    data["delta_weight_kg"] = clamp(data["delta_weight_kg"], -1.2, 1.2)
    data["delta_muscle_kg"] = clamp(data["delta_muscle_kg"], -0.4, 0.4)
    data["delta_fat_pct"] = clamp(data["delta_fat_pct"], -1.2, 1.2)

    data["Post_weight_kg"] = round(pre_w + data["delta_weight_kg"], 3)
    data["Post_muscle_kg"] = round(pre_m + data["delta_muscle_kg"], 3)
    data["Post_fat_pct"] = round(pre_f + data["delta_fat_pct"], 3)

    return data

# ---------------------------- PREFLIGHT ------------------------------

def preflight():
    print(f"[CONFIG] PROJECT_ID={PROJECT_ID} OPENAI_MODEL={OPENAI_MODEL} ANTHROPIC_MODEL={ANTHROPIC_MODEL}")
    # OpenAI ping
    try:
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": "You are terse."},
                {"role": "user", "content": "Reply with JSON {\"ok\":true}"},
            ],
            "temperature": 0,
        }
        r = requests.post(OPENAI_URL, headers=headers, json=payload, timeout=30)
        if r.status_code >= 300:
            raise RuntimeError(f"OpenAI ping failed {r.status_code}: {r.text[:200]}")
        _ = r.json()["choices"][0]["message"]["content"]
        print("[OK] OpenAI ping")
    except Exception as e:
        print("[FAIL] OpenAI ping:", e)
        raise

    # Anthropic ping
    try:
        if Anthropic is None:
            raise RuntimeError("anthropic SDK not installed")
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=16,
            temperature=0,
            system="You are terse.",
            messages=[{"role": "user", "content": "Return JSON {\"ok\":true}"}],
        )
        parts = getattr(msg, "content", [])
        txt = ""
        if parts and hasattr(parts[0], "text"):
            txt = parts[0].text
        elif isinstance(parts, list) and parts and isinstance(parts[0], dict):
            txt = parts[0].get("text", "")
        if not txt:
            raise RuntimeError("empty anthropic reply")
        print("[OK] Anthropic ping")
    except Exception as e:
        print("[FAIL] Anthropic ping:", e)
        raise

# ---------------------------- MAIN LOOP ------------------------------

def build_next_persona(prev_persona: dict, logs: dict) -> dict:
    base_fields = [
        "Age_band", "Sex", "BMI", "Days_per_week", "Current_fitness_level",
        "Primary_goal", "Adherence_propensity", "Cooking_skill", "Budjet_SAR_per_day",
    ]
    out = {k: prev_persona.get(k) for k in base_fields if k in prev_persona}

    def _sg(d: dict, k: str, default: float | None):
        try:
            v = d.get(k, default)
            return float(v) if v is not None else v
        except Exception:
            return default

    out["Weight_kg"] = _sg(logs, "Post_weight_kg", prev_persona.get("Weight_kg"))
    out["Muscle_mass_kg"] = _sg(logs, "Post_muscle_kg", prev_persona.get("Muscle_mass_kg"))
    out["Fat_percent"] = _sg(logs, "Post_fat_pct", prev_persona.get("Fat_percent"))
    out["Sleep_hours"] = _sg(logs, "sleep_avg_hours", prev_persona.get("Sleep_hours"))
    if "notes" in logs:
        out["notes"] = logs.get("notes")

    return strip_nanoseconds(out)


def main():
    print(f"[INFO] Start week: {START_WEEK}; generating {N_WEEKS} weeks for 24 users...")
    print("[INFO] Running preflight pings...")
    preflight()

    db = fs_client()
    persona_ids = list_persona_ids(db)
    if not persona_ids:
        print("[WARN] No personas found under /personas")
        return 0

    for i in range(1, N_WEEKS + 1):
        prev_week = add_weeks(START_WEEK, i - 1)
        next_week = add_weeks(START_WEEK, i)
        print(f"\n[WEEK] {prev_week} -> {next_week}")

        for pid in persona_ids:
            try:
                persona = read_updated_persona(db, pid, prev_week)
                if not persona:
                    print(f"[SKIP] {pid}: no persona state for {prev_week}")
                    continue

                diet_path = f"experiments/Experiment_OpenAI/users/{pid}/weeks/{next_week}/diet/plan"
                if not exists(db, diet_path):
                    prev_diet = read_diet(db, pid, prev_week)
                    diet = openai_generate_diet(persona, next_week=next_week, prev_diet=prev_diet)
                    write_doc(db, diet_path, diet)
                    print(f"[DIET] {pid} -> {diet_path}")
                else:
                    diet = read_diet(db, pid, next_week)
                    print(f"[DIET] {pid} exists -> reusing")

                dpw = int(float(persona.get("Days_per_week", 3))) if str(persona.get("Days_per_week", "")).strip() else 3
                wid_list = pick_workouts(dpw)
                workout_blurbs = read_workout_blurbs(db, wid_list)

                logs_path = f"experiments/Experiment_OpenAI/users/{pid}/weeks/{next_week}/logs/plan"
                if not exists(db, logs_path):
                    logs = claude_simulate_week(persona, diet, workout_blurbs)
                    write_doc(db, logs_path, logs)
                    print(f"[LOGS] {pid} -> {logs_path}")
                else:
                    logs = read_doc(db, logs_path)
                    print(f"[LOGS] {pid} exists -> reusing")

                up_path = f"experiments/Experiment_OpenAI/users/{pid}/weeks/{next_week}/updated_persona/plan"
                if not exists(db, up_path):
                    updated = build_next_persona(persona, logs)
                    write_doc(db, up_path, updated)
                    print(f"[UPDATE] {pid} -> {up_path}")
                else:
                    print(f"[UPDATE] {pid} exists -> skipping")

                time.sleep(SLEEP_BETWEEN_PERSONAS)

            except Exception as e:
                if isinstance(e, RetryError):
                    cause = e.last_attempt.exception()
                    print(f"[ERROR] {pid}: RetryError -> {type(cause).__name__}: {cause}")
                else:
                    print(f"[ERROR] {pid}: {type(e).__name__}: {e}")
                    tb = traceback.format_exc(limit=2)
                    print(tb)
                continue

        time.sleep(SLEEP_BETWEEN_WEEKS)

    print("\n[DONE] Yearly loop finished.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[INTERRUPTED]")
        raise
