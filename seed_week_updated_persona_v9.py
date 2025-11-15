# seed_week_updated_persona_v9.py
from typing import Dict
from config_seed_v9 import WEEK_ID_SEED, WORKOUT_MAP
from firestore_io_seed_v9 import (
    get_db, list_persona_ids, read_persona, read_diet_for_week,
    read_workout, write_logs, write_updated_persona
)
from claude_client_seed_v9 import simulate_week_with_claude

def choose_workouts(days_per_week: int):
    return WORKOUT_MAP.get(int(days_per_week), WORKOUT_MAP[3])

def build_updated_persona(persona: Dict, logs: Dict) -> Dict:
    return {
        "Age_band": persona.get("Age_band"),
        "Sex": persona.get("Sex"),
        "BMI": persona.get("BMI"),
        "Days_per_week": persona.get("Days_per_week"),
        "Current_fitness_level": persona.get("Current_fitness_level"),
        "Primary_goal": persona.get("Primary_goal"),
        "Adherence_propensity": persona.get("Adherence_propensity"),
        "Cooking_skill": persona.get("Cooking_skill"),
        "Budjet_SAR_per_day": persona.get("Budjet_SAR_per_day"),
        "Weight_kg": logs.get("Post_weight_kg"),
        "Muscle_mass_kg": logs.get("Post_muscle_kg"),
        "Fat_percent": logs.get("Post_fat_pct"),
        "Sleep_hours": logs.get("sleep_avg_hours"),
        "notes": logs.get("notes"),
    }

def main():
    db = get_db()
    pids = list_persona_ids(db)
    print(f"[INFO] Personas found: {len(pids)} -> {pids}")

    # cache workouts
    all_wids = {w for arr in WORKOUT_MAP.values() for w in arr}
    workouts_map = {wid: (read_workout(db, wid) or {}) for wid in all_wids}

    for pid in pids:
        persona = read_persona(db, pid) or {}
        if not persona:
            print(f"[WARN] {pid}: missing persona; skipping")
            continue

        diet = read_diet_for_week(db, pid, WEEK_ID_SEED)
        if not diet:
            print(f"[WARN] {pid}: missing diet @ {WEEK_ID_SEED}; skipping")
            continue

        days = int(persona.get("Days_per_week", 3) or 3)
        wids = choose_workouts(days)

        logs = simulate_week_with_claude(persona, diet, workouts_map, wids, WEEK_ID_SEED)

        write_logs(db, "Experiment_ACEGPT", pid, WEEK_ID_SEED, logs)
        print(f"[OK] logs saved for {pid} @ {WEEK_ID_SEED}")

        up = build_updated_persona(persona, logs)
        write_updated_persona(db, "Experiment_ACEGPT", pid, WEEK_ID_SEED, up)
        write_updated_persona(db, "Experiment_OpenAI", pid, WEEK_ID_SEED, up)
        print(f"[OK] updated_persona saved for {pid} @ {WEEK_ID_SEED}")

if __name__ == "__main__":
    main()
