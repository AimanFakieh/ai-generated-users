# --- year_orchestrator_dual_v2.py ---
from typing import List, Tuple
import hashlib
from config_dual import START_WEEK_ID, TOTAL_WEEKS, INCLUDE_START_WEEK, WORKOUT_MAP
from firestore_io_dual_v2 import (
    list_persona_ids, read_updated_persona, read_diet,
    write_diet, write_logs, write_updated_persona, read_persona
)
from acegpt_client_dual_v2 import get_diet_from_ace, generate_feedback
from utils_time_dual import week_id_sequence, stamp_riyadh

def _diversity_tag(pid: str, week_id: str) -> str:
    """
    Deterministic tag used to push variety in HF prompt.
    """
    h = hashlib.sha256(f"{pid}:{week_id}:prompt-v3".encode()).hexdigest()
    motifs = [
        "spice-forward & herb-based",
        "lower-sodium & citrus-forward",
        "high-protein dairy-forward",
        "seafood-forward with brown rice",
        "date-inclusive pre-workout carb",
        "legume-forward fiber emphasis",
        "grill & roast (no frying)",
        "yoghurt/salad sides most meals",
    ]
    i = int(h[:8], 16) % len(motifs)
    return motifs[i]

def workouts_for(days_per_week) -> List[str]:
    try:
        d = int(days_per_week)
    except Exception:
        d = 4
    return WORKOUT_MAP.get(d, WORKOUT_MAP[4])

def build_diet_prompt(updated_persona: dict, week_id: str, pid: str) -> str:
    tag = _diversity_tag(pid, week_id)
    return (
        "You are a nutritionist. Design ONE-DAY Saudi-style diet the persona can repeat for the week. "
        "Vary choices week-to-week and across different people. "
        "Be practical, respect budget/preferences/goals, and include a 'Total kcal' line and macro lines.\n"
        f"[VARIETY_TAG]={tag}\n"
        f"[WEEK]={week_id}\n[PERSONA]={updated_persona}"
    )

def simulate_progress(updated_persona: dict, diet: dict, week_id: str, workouts: List[str]) -> Tuple[dict, dict]:
    pid = (updated_persona.get("ID") or updated_persona.get("id") or "PXX")

    # Numeric baselines with safe casting
    def _as_float(x, default=0.0):
        try:
            return float(str(x).replace(",", "").strip())
        except Exception:
            return default

    pre_w = _as_float(updated_persona.get("Weight_kg", 75), 75.0)
    pre_m = _as_float(updated_persona.get("Muscle_mass_kg", 35), 35.0)
    pre_f = _as_float(updated_persona.get("Fat_percent", 22), 22.0)

    goal      = str(updated_persona.get("Primary_goal", "recomp")).lower()
    adherence = str(updated_persona.get("Adherence_propensity", "medium")).lower()
    sleep_h   = _as_float(updated_persona.get("Sleep_hours", 7), 7.0)

    adj = -0.4 if "fat" in goal else (0.35 if "muscle" in goal else -0.05)
    adh_factor   = 0.7 if "low" in adherence else (1.1 if "high" in adherence else 1.0)
    sleep_factor = 0.9 if sleep_h < 6 else (1.05 if sleep_h >= 8 else 1.0)

    import random
    seed_key = f"{pid}-{week_id}"
    rnd = random.Random(seed_key)

    dw = round(adj * adh_factor * sleep_factor * (0.6 + 0.8 * rnd.random()), 2)
    dm = round((0.15 if "muscle" in goal else -0.05) * adh_factor * sleep_factor * (0.6 + 0.8 * rnd.random()), 2)
    df = round((-0.4 if "fat" in goal else (-0.1 if "recomp" in goal else 0.0)) * adh_factor * sleep_factor * (0.6 + 0.8 * rnd.random()), 2)

    post_w = round(pre_w + dw, 2)
    post_m = max(0.0, round(pre_m + dm, 2))
    post_f = max(3.0, round(pre_f + df, 2))

    date_str, time_str = stamp_riyadh()
    daily_avg_kcal = diet.get("Total_kcal_target_kcal") or 2200

    fb = generate_feedback(updated_persona, diet, workouts, seed_key)
    logs = {
        "Date": date_str, "Time": time_str,
        "free_text_feedback": fb["free_text_feedback"],
        "notes": fb["notes"],
        "daily_avg_kcal": daily_avg_kcal,
        "Pre_weight_kg": pre_w, "Pre_muscle_kg": pre_m, "Pre_fat_pct": pre_f,
        "Post_weight_kg": post_w, "Post_muscle_kg": post_m, "Post_fat_pct": post_f,
        "delta_weight_kg": round(post_w - pre_w, 2),
        "delta_muscle_kg": round(post_m - pre_m, 2),
        "delta_fat_pct": round(post_f - pre_f, 2),
        "sleep_avg_hours": sleep_h,
    }

    updated = {
        "Age_band": updated_persona.get("Age_band"),
        "Sex": updated_persona.get("Sex"),
        "BMI": updated_persona.get("BMI"),
        "Days_per_week": updated_persona.get("Days_per_week"),
        "Current_fitness_level": updated_persona.get("Current_fitness_level"),
        "Primary_goal": updated_persona.get("Primary_goal"),
        "Adherence_propensity": updated_persona.get("Adherence_propensity"),
        "Cooking_skill": updated_persona.get("Cooking_skill"),
        "Budjet_SAR_per_day": updated_persona.get("Budjet_SAR_per_day"),
        "Weight_kg": post_w,
        "Muscle_mass_kg": post_m,
        "Fat_percent": post_f,
        "Sleep_hours": sleep_h,
        "notes": fb["notes"],
    }
    return logs, updated

def write_diet_with_meta(pid: str, week_id: str, diet: dict):
    date_str, time_str = stamp_riyadh()
    payload = {"Date": date_str, "Time": time_str, "Note": "Nutritionist comments embedded in raw text."}
    payload.update(diet)
    write_diet(pid, week_id, payload)

def run_full_year():
    personas = list_persona_ids()
    print("[INFO] Personas:", personas)

    weeks = week_id_sequence(START_WEEK_ID, TOTAL_WEEKS, INCLUDE_START_WEEK)
    for week_id in weeks:
        print(f"\n================= {week_id} =================")
        for pid in personas:
            updated_persona = read_updated_persona(pid, week_id) or read_persona(pid)

            wlist = workouts_for(updated_persona.get("Days_per_week"))
            prompt = build_diet_prompt(updated_persona, week_id, pid)

            diet = get_diet_from_ace(prompt, pid=pid, week_id=week_id, retries=2)
            write_diet_with_meta(pid, week_id, diet)

            logs, upd = simulate_progress(updated_persona, diet, week_id, wlist)
            write_logs(pid, week_id, logs)
            write_updated_persona(pid, week_id, upd)

            print(f"[OK] Week {week_id} :: {pid} -> diet/logs/updated_persona saved")

if __name__ == "__main__":
    run_full_year()
