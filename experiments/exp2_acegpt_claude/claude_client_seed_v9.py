# claude_client_seed_v9.py
import os, json, math, random, hashlib, datetime, requests
from zoneinfo import ZoneInfo
from typing import Dict, List, Tuple

from config_seed_v9 import (
    ANTHROPIC_MODEL, ANTHROPIC_URL, CLAUDE_TEMPERATURE, RIYADH_TZ
)

# ------------- Time helpers -------------
def now_riyadh() -> Tuple[str, str]:
    t = datetime.datetime.now(ZoneInfo(RIYADH_TZ))
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S")

def clamp(v, lo, hi): return max(lo, min(hi, v))

# ------------- Claude helpers -------------
def call_claude(messages: List[Dict], max_tokens: int = 800) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": CLAUDE_TEMPERATURE,
    }
    r = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Claude status {r.status_code}: {r.text}")
    data = r.json()
    text_out = ""
    for b in data.get("content", []):
        if b.get("type") == "text":
            text_out += b.get("text", "")
    return text_out.strip()

def extract_first_json_block(text: str) -> Dict:
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise ValueError("No JSON object found in Claude output.")
    return json.loads(text[s:e+1])

# ------------- Prompt builder -------------
def workouts_payload(workout_ids: List[str], workouts_map: Dict[str, Dict]) -> List[Dict]:
    out = []
    for wid in workout_ids:
        wdoc = workouts_map.get(wid) or {}
        out.append({"workout_id": wid,
                    "title": wdoc.get("title", ""),
                    "exercises": wdoc.get("exercises", [])})
    return out

def prompt_for_claude(persona: Dict, diet: Dict, workouts: List[Dict], week_id: str) -> str:
    return f"""
You are simulating ONE persona for ONE week: {persona.get('ID','unknown')} ({week_id}).
Use the fields exactly as given. Then output exactly ONE JSON object (no prose).

Persona:
Adherence_propensity={persona.get('Adherence_propensity')}
Age_band={persona.get('Age_band')}
Sex={persona.get('Sex')}
BMI={persona.get('BMI')}
Biggest_barrier={persona.get('Biggest_barrier')}
Current_fitness_level={persona.get('Current_fitness_level')}
Days_per_week={persona.get('Days_per_week')}
Weight_kg={persona.get('Weight_kg')}
Muscle_mass_kg={persona.get('Muscle_mass_kg')}
Fat_percent={persona.get('Fat_percent')}
Injury_history={persona.get('Injury_history')}
Motivation_to_workout={persona.get('Motivation_to_workout')}
Sleep_hours={persona.get('Sleep_hours')}
Primary_goal={persona.get('Primary_goal')}

Diet (repeated daily x7):
Totals: kcal={diet.get('Total_kcal_target_kcal')}, C={diet.get('Total_carbs_g')}g, F={diet.get('Total_fat_g')}g, P={diet.get('Total_protein_g')}g, Fiber={diet.get('Total_fiber_g')}g, Na={diet.get('Total_sodium_mg')}mg
M1: {diet.get('1st_meal')} / kcal={diet.get('1st_meal_kcal_target_kcal')} C={diet.get('1st_meal_carbs_g')} F={diet.get('1st_meal_fat_g')} P={diet.get('1st_meal_protein_g')} Fiber={diet.get('1st_meal_fiber_g')} Na={diet.get('1st_meal_sodium_mg')}
M2: {diet.get('2nd_meal')} / kcal={diet.get('2nd_meal_kcal_target_kcal')} C={diet.get('2nd_meal_carbs_g')} F={diet.get('2nd_meal_fat_g')} P={diet.get('2nd_meal_protein_g')} Fiber={diet.get('2nd_meal_fiber_g')} Na={diet.get('2nd_meal_sodium_mg')}
M3: {diet.get('3rd_meal')} / kcal={diet.get('3rd_meal_kcal_target_kcal')} C={diet.get('3rd_meal_carbs_g')} F={diet.get('3rd_meal_fat_g')} P={diet.get('3rd_meal_protein_g')} Fiber={diet.get('3rd_meal_fiber_g')} Na={diet.get('3rd_meal_sodium_mg')}
M4: {diet.get('4th_meal')} / kcal={diet.get('4th_meal_kcal_target_kcal')} C={diet.get('4th_meal_carbs_g')} F={diet.get('4th_meal_fat_g')} P={diet.get('4th_meal_protein_g')} Fiber={diet.get('4th_meal_fiber_g')} Na={diet.get('4th_meal_sodium_mg')}

Workouts this week:
{json.dumps(workouts, ensure_ascii=False)}

REQUIRED OUTPUT: exactly one JSON object with keys:
Date, Time, free_text_feedback, notes, daily_avg_kcal,
Pre_weight_kg, Pre_muscle_kg, Pre_fat_pct,
Post_weight_kg, Post_muscle_kg, Post_fat_pct,
delta_weight_kg, delta_muscle_kg, delta_fat_pct, sleep_avg_hours

Make free_text_feedback & notes **persona-specific**: reference barrier, sleep, goal, and at least one workout or meal detail.
All numeric fields must be numbers (not strings). Date=YYYY-MM-DD (Asia/Riyadh), Time=HH:MM:SS.
No extra text outside the JSON.
"""

# ------------- Persona-aware fallback -------------
def _seed_from_pid(pid: str) -> int:
    h = hashlib.sha256((pid or "anon").encode("utf-8")).hexdigest()[:8]
    return int(h, 16)

def _choose(lst): return random.choice(lst) if lst else ""

def _mk_feedback(pid: str, persona: Dict, daily_kcal: float, days_per_week: int, workouts_ids: List[str], sleep_avg: float):
    # seeded randomness
    random.seed(_seed_from_pid(pid))

    goal = (persona.get("Primary_goal") or "").lower()
    barrier = (persona.get("Biggest_barrier") or "").lower()
    adher = float(persona.get("Adherence_propensity", 0.65) or 0.65)
    fitness = (persona.get("Current_fitness_level") or "").lower()

    tones = ["steady", "focused", "up-and-down", "disciplined", "cautious", "optimistic"]
    felt = ["energy", "recovery", "digestion", "motivation", "sleep", "joint comfort"]
    changes = ["noticeable", "subtle", "gradual", "promising", "uneven"]
    tone = _choose(tones); feel = _choose(felt); change = _choose(changes)

    adher_str = "very consistent" if adher >= 0.8 else "mostly consistent" if adher >= 0.6 else "on/off"
    goal_phrase = {
        "muscle": "push progressive overload and protein timing",
        "fat": "maintain a modest deficit and prioritize steps",
        "recomp": "balance protein and volume while keeping steps high",
    }
    gkey = "muscle" if "muscle" in goal else "fat" if "fat" in goal else "recomp"
    barrier_hint = ""
    if "time" in barrier: barrier_hint = "Short sessions and supersets helped the schedule."
    elif "motivation" in barrier: barrier_hint = "Music + a simple checklist boosted adherence."
    elif "sleep" in barrier: barrier_hint = "Earlier wind-down improved sleep quality."
    elif "injur" in barrier: barrier_hint = "Kept sets submaximal and respected joint feedback."
    else: barrier_hint = "Stuck to basics and removed small frictions."

    wk_str = ", ".join(workouts_ids[:3]) if workouts_ids else "N/A"
    lines = [
        f"This week felt {tone}. With {adher_str} adherence (~{daily_kcal:.0f} kcal/day), I completed {days_per_week} sessions (e.g., {wk_str}).",
        f"{barrier_hint} I noticed {change} changes in {feel}. Given my goal, I tried to {goal_phrase[gkey]}.",
        f"Average sleep was ~{sleep_avg:.1f} h; training quality tracked well with meal timing and hydration."
    ]
    return " ".join(lines)

def _mk_notes(pid: str, persona: Dict, sleep_avg: float, days_per_week: int, kcal: float):
    random.seed(_seed_from_pid(pid) + 13)

    budget = (persona.get("Budjet_SAR_per_day") or "").lower()
    cook = (persona.get("Cooking_skill") or "").lower()
    sex = (persona.get("Sex") or "")
    goal = (persona.get("Primary_goal") or "").lower()

    # tiny nudges for next week
    if "muscle" in goal:
        n1 = "Add a 20–30 g protein snack post-workout and a slow-digesting protein near bedtime."
    elif "fat" in goal:
        n1 = "Trim ~100–150 kcal from late snacks and keep daily steps >8–10k."
    else:
        n1 = "Hold calories steady and emphasize high-quality reps on compounds."

    n2 = "Insert a 10–15 min mobility block on rest days to keep joints happy."
    n3 = "Aim for a consistent lights-out routine to push sleep toward 7–8 h."
    if sleep_avg >= 7.5: n3 = "Maintain a consistent sleep window to preserve 7–8 h nights."

    if "low" in budget:
        n4 = "Batch-cook simple Saudi staples (rice, lentils, eggs) to stay on budget."
    elif "high" in budget:
        n4 = "Consider leaner cuts and more fresh produce to refine micronutrients."
    else:
        n4 = "Keep meals simple; adjust seasoning and veggies for variety."

    if "beginner" in cook:
        n5 = "Keep recipes under 5 steps; reuse the same spice mix to reduce friction."
    else:
        n5 = "Experiment with one new high-protein Saudi dish mid-week for variety."

    endings = [
        "Track water intake more tightly.",
        "Do a quick 5-min walk after larger meals.",
        "Warm up shoulders and hips before heavy sets.",
        "Prep tomorrow’s breakfast the night before.",
    ]
    n6 = _choose(endings)

    return " ".join([n1, n2, n3, n4, n5, n6])

def fallback_simulation(pid: str, persona: Dict, diet: Dict, workout_ids: List[str]) -> Dict:
    date_str, time_str = now_riyadh()
    adher = float(persona.get("Adherence_propensity", 0.65) or 0.65)
    pre_w = float(persona.get("Weight_kg", 75.0) or 75.0)
    pre_m = float(persona.get("Muscle_mass_kg", 30.0) or 30.0)
    pre_f = float(persona.get("Fat_percent", 25.0) or 25.0)
    goal = (persona.get("Primary_goal") or "").lower()
    days = int(persona.get("Days_per_week", 3) or 3)

    kcal = float(diet.get("Total_kcal_target_kcal", 2000.0) or 2000.0)
    daily_kcal = kcal * (0.82 + 0.38 * adher)
    daily_kcal = float(f"{daily_kcal:.1f}")

    if "fat" in goal:
        dW = -0.35 * adher; dM = +0.03 * adher
    elif "muscle" in goal:
        dW = +0.20 * adher; dM = +0.10 * adher
    else:
        dW = (-0.05 + 0.10*(adher-0.5)); dM = +0.05 * adher

    post_w = pre_w + dW
    post_m = pre_m + dM

    fat_kg = pre_w * (pre_f/100.0)
    fat_kg += 0.75 * dW if dW < 0 else 0.30 * dW
    post_f_pct = clamp((fat_kg / max(post_w, 0.1)) * 100.0, 5.0, 60.0)
    delta_f = post_f_pct - pre_f

    base_sleep = float(persona.get("Sleep_hours", 7.0) or 7.0)
    sleep_avg = base_sleep + (0.2 * (adher - 0.5))
    sleep_avg = float(f"{sleep_avg:.2f}")

    free_text = _mk_feedback(pid, persona, daily_kcal, days, workout_ids, sleep_avg)
    notes = _mk_notes(pid, persona, sleep_avg, days, kcal)

    return {
        "Date": date_str,
        "Time": time_str,
        "free_text_feedback": free_text,
        "notes": notes,
        "daily_avg_kcal": daily_kcal,
        "Pre_weight_kg": float(f"{pre_w:.2f}"),
        "Pre_muscle_kg": float(f"{pre_m:.2f}"),
        "Pre_fat_pct": float(f"{pre_f:.2f}"),
        "Post_weight_kg": float(f"{post_w:.2f}"),
        "Post_muscle_kg": float(f"{post_m:.2f}"),
        "Post_fat_pct": float(f"{post_f_pct:.2f}"),
        "delta_weight_kg": float(f"{dW:.2f}"),
        "delta_muscle_kg": float(f"{dM:.2f}"),
        "delta_fat_pct": float(f"{delta_f:.2f}"),
        "sleep_avg_hours": sleep_avg,
    }

def simulate_week_with_claude(persona: Dict, diet: Dict, workouts_map: Dict[str, Dict], workout_ids: List[str], week_id: str) -> Dict:
    wkts = workouts_payload(workout_ids, workouts_map)

    # Try Claude first (more diversity); if it fails, fallback is persona-aware
    try:
        text = call_claude(
            messages=[{"role": "user", "content": prompt_for_claude(persona, diet, wkts, week_id)}],
            max_tokens=700
        )
        data = extract_first_json_block(text)
        # Minimal validation
        required = [
            "Date","Time","free_text_feedback","notes","daily_avg_kcal",
            "Pre_weight_kg","Pre_muscle_kg","Pre_fat_pct",
            "Post_weight_kg","Post_muscle_kg","Post_fat_pct",
            "delta_weight_kg","delta_muscle_kg","delta_fat_pct","sleep_avg_hours"
        ]
        for k in required:
            if k not in data:
                raise ValueError(f"Claude JSON missing key: {k}")
        # Ensure numeric
        for k in ["daily_avg_kcal","Pre_weight_kg","Pre_muscle_kg","Pre_fat_pct","Post_weight_kg","Post_muscle_kg","Post_fat_pct","delta_weight_kg","delta_muscle_kg","delta_fat_pct","sleep_avg_hours"]:
            data[k] = float(data[k])
        return data
    except Exception:
        pid = str(persona.get("ID") or persona.get("id") or "unknown")
        return fallback_simulation(pid, persona, diet, workout_ids)
