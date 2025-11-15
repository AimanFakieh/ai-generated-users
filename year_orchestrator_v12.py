# year_orchestrator_v12.py
import datetime
from typing import Dict, Set
from config_year_v12 import START_WEEK_ID, TOTAL_WEEKS, INCLUDE_START_WEEK, WORKOUT_MAP
from firestore_io_year_v11 import (
    get_db, list_persona_ids, read_persona_base, read_updated_persona,
    read_diet, write_diet, write_logs, write_updated_persona, read_workout
)
from acegpt_client_v12 import get_diet_from_ace
from claude_client_v12 import simulate_week_with_claude
from utils_json_v12 import make_diet_fingerprint

def _week_to_monday(week_id: str) -> datetime.date:
    _, yyyy, ww = week_id.split("_")
    return datetime.date.fromisocalendar(int(yyyy), int(ww), 1)

def _week_from_date(d: datetime.date) -> str:
    iso = d.isocalendar()
    return f"Week_{iso.year}_{iso.week:02d}"

def week_sequence(start_week_id: str, n: int, include_start: bool) -> list[str]:
    start_date = _week_to_monday(start_week_id)
    weeks = []
    idx0 = 0 if include_start else 1
    for i in range(idx0, idx0 + n):
        monday = start_date + datetime.timedelta(days=7*i)
        weeks.append(_week_from_date(monday))
    return weeks

def _choose_workouts(days_per_week: int):
    return WORKOUT_MAP.get(int(days_per_week), WORKOUT_MAP[3])

def build_updated_persona(prev: Dict, logs: Dict) -> Dict:
    return {
        "Age_band": prev.get("Age_band"),
        "Sex": prev.get("Sex"),
        "BMI": prev.get("BMI"),
        "Days_per_week": prev.get("Days_per_week"),
        "Current_fitness_level": prev.get("Current_fitness_level"),
        "Primary_goal": prev.get("Primary_goal"),
        "Adherence_propensity": prev.get("Adherence_propensity"),
        "Cooking_skill": prev.get("Cooking_skill"),
        "Budjet_SAR_per_day": prev.get("Budjet_SAR_per_day"),
        "Weight_kg": logs.get("Post_weight_kg"),
        "Muscle_mass_kg": logs.get("Post_muscle_kg"),
        "Fat_percent": logs.get("Post_fat_pct"),
        "Sleep_hours": logs.get("sleep_avg_hours"),
        # copy week-specific notes (already persona+week unique)
        "notes": logs.get("notes"),
    }

def main():
    db   = get_db()
    pids = list_persona_ids(db)
    print(f"[INFO] Personas: {pids}")

    # load workouts
    all_wids = {wid for arr in WORKOUT_MAP.values() for wid in arr}
    workouts_map = {wid: (read_workout(db, wid) or {}) for wid in all_wids}

    weeks = week_sequence(START_WEEK_ID, TOTAL_WEEKS, INCLUDE_START_WEEK)

    for w in weeks:
        print(f"\n================= {w} =================")
        idx  = weeks.index(w)
        prev = START_WEEK_ID if idx == 0 else weeks[idx-1]

        # per-week de-dup guards (avoid same diet across different personas in this week)
        used_diet_fps: Set[str] = set()
        used_text_fps: Set[str] = set()

        for pid in pids:
            print(f"[INFO] Week {w} -> {pid}")

            # persona source for this week (carry over from prev week if exists)
            persona_src = read_updated_persona(db, pid, prev) or read_persona_base(db, pid)
            persona_src["ID"] = pid

            # last week diet (for similarity check)
            last_diet = read_diet(db, pid, prev)

            # --- 1) Diet with forced diversification & cross-person uniqueness in SAME week ---
            attempt = 0
            while True:
                diet = get_diet_from_ace(persona_src, pid, w, last_week_diet=last_diet, diversify_nonce=attempt)
                fp   = make_diet_fingerprint(diet)
                if fp not in used_diet_fps:
                    used_diet_fps.add(fp)
                    break
                attempt += 1
                if attempt > 3:
                    # accept and move on (already varied by nonce)
                    break
            write_diet(db, pid, w, diet)
            print(f"[OK] diet saved @ {w} for {pid}")

            # --- 2) Workouts for the week ---
            days = int(persona_src.get("Days_per_week", 3) or 3)
            wids = _choose_workouts(days)

            # --- 3) Logs with uniqueness guard (notes + free_text_feedback) ---
            attempt = 0
            while True:
                logs = simulate_week_with_claude(persona_src, diet, workouts_map, wids, pid, w, nonce=attempt)
                # create a small fingerprint of texts to avoid identical outputs across personas within the same week
                text_sig = hashlib.sha1(
                    (logs.get("free_text_feedback","") + "|" + logs.get("notes","")).encode("utf-8")
                ).hexdigest()[:16]
                if text_sig not in used_text_fps:
                    used_text_fps.add(text_sig)
                    break
                attempt += 1
                if attempt > 3:
                    break
            write_logs(db, "Experiment_ACEGPT", pid, w, logs)
            print(f"[OK] logs saved @ {w} for {pid}")

            # --- 4) Updated persona into both experiments (notes already persona+week unique) ---
            up = build_updated_persona(persona_src, logs)
            write_updated_persona(db, "Experiment_ACEGPT", pid, w, up)
            write_updated_persona(db, "Experiment_OpenAI", pid, w, up)
            print(f"[OK] updated_persona saved @ {w} for {pid}")

if __name__ == "__main__":
    import hashlib
    main()
