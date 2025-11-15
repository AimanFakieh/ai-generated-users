# claude_client_v12.py
import os, json, hashlib, random, datetime, requests
from typing import Dict, List, Tuple
from zoneinfo import ZoneInfo
from config_year_v12 import ANTHROPIC_MODEL, ANTHROPIC_URL, CLAUDE_TEMPERATURE, RIYADH_TZ

def _seed(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:12], 16)

def now_riyadh() -> Tuple[str, str]:
    t = datetime.datetime.now(ZoneInfo(RIYADH_TZ))
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S")

def call_claude(messages: List[Dict], max_tokens: int = 800) -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key: raise RuntimeError("ANTHROPIC_API_KEY is not set")
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    payload = {"model": ANTHROPIC_MODEL, "max_tokens": max_tokens, "messages": messages, "temperature": CLAUDE_TEMPERATURE}
    r = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Claude status {r.status_code}: {r.text}")
    data = r.json()
    out = ""
    for b in data.get("content", []):
        if b.get("type") == "text": out += b.get("text","")
    return out.strip()

def _rng(pid: str, week_id: str, salt: int = 0) -> random.Random:
    return random.Random(_seed(f"{pid}|{week_id}|logs|{salt}"))

def _pick(rng: random.Random, arr): return arr[rng.randrange(0, len(arr))]

def _mk_feedback(pid: str, week_id: str, persona: Dict, diet: Dict, workouts_ids: List[str], salt: int = 0) -> str:
    rng = _rng(pid, week_id, salt)
    goal = (persona.get("Primary_goal") or "").lower()
    barrier = (persona.get("Biggest_barrier") or "").lower()
    budget = (persona.get("Budjet_SAR_per_day") or "").lower()
    cook = (persona.get("Cooking_skill") or "").lower()
    m1 = str(diet.get("1st_meal","")); m2 = str(diet.get("2nd_meal",""))
    wid = workouts_ids[rng.randrange(0, len(workouts_ids))] if workouts_ids else "W21"
    tones = ["steady","focused","up-and-down","disciplined","optimistic","energized","measured","resilient"]
    feel  = ["energy","recovery","digestion","sleep","appetite","joint comfort","pump","motivation"]
    change= ["noticeable","gradual","clear","promising","mixed","strong"]
    tone  = _pick(rng, tones); f=_pick(rng, feel); ch=_pick(rng, change)
    adher = float(persona.get("Adherence_propensity", 0.65) or 0.65)
    adher_txt = "very consistent" if adher>=0.8 else "mostly consistent" if adher>=0.6 else "on/off"
    barrier_hint = {
        "time":"Short supersets and grouped movements saved time.",
        "motivation":"Small checklists + music helped motivation spikes.",
        "sleep":"Earlier wind-down boosted sleep quality.",
        "injur":"Controlled tempo and warm-ups kept joints safe.",
    }.get(next((k for k in barrier.split() if k in ["time","motivation","sleep","injur"]), "x"), "Removing frictions improved follow-through.")
    goal_hint = {"muscle":"prioritized progressive overload + protein timing",
                 "fat":"kept a mild deficit + high steps",
                 "recomp":"balanced volume and daily activity"}
    gk = "muscle" if "muscle" in goal else "fat" if "fat" in goal else "recomp"
    return (
        f"Felt {tone} this week. With {adher_txt} adherence, I completed sessions incl. {wid}. "
        f"Meals like '{m1}' and '{m2}' sat well; {barrier_hint} I saw {ch} changes in {f}. "
        f"For my goal, I {goal_hint[gk]}. Budget={budget or 'medium'}, cooking={cook or 'intermediate'}."
    )

def _mk_notes(pid: str, week_id: str, persona: Dict, diet: Dict, salt: int = 0) -> str:
    rng = _rng(pid, week_id, salt)
    sleep = float(persona.get("Sleep_hours", 7.0) or 7.0)
    kcal  = float(diet.get("Total_kcal_target_kcal", 2000.0) or 2000.0)
    knobs = [
        "front-load protein earlier",
        "lighten late snacks",
        "add 10–15 min mobility",
        "track water more tightly",
        "5-min post-meal walks",
        "prep breakfast the night before",
        "warm shoulders/hips before heavy sets",
        "swap one rice meal for jareesh mid-week",
        "season with za’atar to vary flavor",
    ]
    tweak = _pick(rng, knobs)
    return f"Next week: keep ~{kcal:.0f} kcal/day, {tweak}, and aim for consistent {sleep:.1f} h sleep."

def simulate_week_with_claude_fallback(persona: Dict, diet: Dict, workouts_ids: List[str], pid: str, week_id: str, salt: int = 0) -> Dict:
    rng = _rng(pid, week_id, salt)
    date_str, time_str = now_riyadh()
    pre_w = float(persona.get("Weight_kg", 75.0) or 75.0)
    pre_m = float(persona.get("Muscle_mass_kg", 30.0) or 30.0)
    pre_f = float(persona.get("Fat_percent", 25.0) or 25.0)
    adher = float(persona.get("Adherence_propensity", 0.65) or 0.65)
    days  = int(persona.get("Days_per_week", 3) or 3)
    kcal  = float(diet.get("Total_kcal_target_kcal", 2000.0) or 2000.0)
    daily = round(kcal * (0.82 + 0.38*adher) + rng.uniform(-60,60), 1)

    goal = (persona.get("Primary_goal") or "").lower()
    if "fat" in goal:
        dW = -0.35*adher + rng.uniform(-0.08, 0.02)
        dM = +0.03*adher + rng.uniform(-0.02, 0.05)
    elif "muscle" in goal:
        dW = +0.20*adher + rng.uniform(-0.05, 0.12)
        dM = +0.10*adher + rng.uniform( 0.00, 0.10)
    else:
        dW = (-0.05 + 0.10*(adher-0.5)) + rng.uniform(-0.06,0.06)
        dM = +0.05*adher + rng.uniform(-0.02,0.06)

    post_w = pre_w + dW
    post_m = pre_m + dM
    fat_kg = pre_w * (pre_f/100.0)
    fat_kg += (0.75*dW if dW<0 else 0.30*dW)
    post_f = max(5.0, min((fat_kg/max(post_w,0.1))*100.0, 60.0))
    sleep  = round(float(persona.get("Sleep_hours",7.0) or 7.0) + (0.2*(adher-0.5)) + rng.uniform(-0.25,0.25), 2)

    feedback = _mk_feedback(pid, week_id, persona, diet, workouts_ids, salt)
    notes    = _mk_notes(pid, week_id, persona, diet, salt)

    return {
        "Date": date_str, "Time": time_str,
        "free_text_feedback": feedback,
        "notes": notes,
        "daily_avg_kcal": daily,
        "Pre_weight_kg": round(pre_w,2), "Pre_muscle_kg": round(pre_m,2), "Pre_fat_pct": round(pre_f,2),
        "Post_weight_kg": round(post_w,2), "Post_muscle_kg": round(post_m,2), "Post_fat_pct": round(post_f,2),
        "delta_weight_kg": round(dW,2), "delta_muscle_kg": round(dM,2), "delta_fat_pct": round(post_f-pre_f,2),
        "sleep_avg_hours": sleep,
    }

def simulate_week_with_claude(persona: Dict, diet: Dict, workouts_map: Dict[str, Dict], workouts_ids: List[str], pid: str, week_id: str, nonce: int = 0) -> Dict:
    # Try API once; if generic or error, use seeded fallback (nonce ensures new variant if we need another attempt)
    try:
        wkts = [{"workout_id": wid, "title": (workouts_map.get(wid) or {}).get("title",""), "exercises": (workouts_map.get(wid) or {}).get("exercises", [])} for wid in workouts_ids]
        prompt = f"""
Simulate one persona for ONE week. DIVERSITY_TAG={pid}|{week_id}|{nonce}
Output exactly ONE JSON (no prose) with keys:
Date, Time, free_text_feedback, notes, daily_avg_kcal,
Pre_weight_kg, Pre_muscle_kg, Pre_fat_pct,
Post_weight_kg, Post_muscle_kg, Post_fat_pct,
delta_weight_kg, delta_muscle_kg, delta_fat_pct, sleep_avg_hours.

Persona: {json.dumps(persona, ensure_ascii=False)}
Diet: {json.dumps(diet, ensure_ascii=False)}
Workouts: {json.dumps(wkts, ensure_ascii=False)}

Make free_text_feedback and notes specific to this persona & this week:
- reference at least ONE meal by name,
- reference ONE workout id,
- mention barrier or sleep or budget,
- keep a different tone per DIVERSITY_TAG.
"""
        text = call_claude([{"role":"user","content":prompt}], max_tokens=700)
        s,e = text.find("{"), text.rfind("}")
        data = json.loads(text[s:e+1])
        # quick sanity & numeric coerce
        need = ["Date","Time","free_text_feedback","notes","daily_avg_kcal",
                "Pre_weight_kg","Pre_muscle_kg","Pre_fat_pct",
                "Post_weight_kg","Post_muscle_kg","Post_fat_pct",
                "delta_weight_kg","delta_muscle_kg","delta_fat_pct","sleep_avg_hours"]
        for k in need:
            if k not in data: raise ValueError("missing key "+k)
        for k in ["daily_avg_kcal","Pre_weight_kg","Pre_muscle_kg","Pre_fat_pct",
                  "Post_weight_kg","Post_muscle_kg","Post_fat_pct",
                  "delta_weight_kg","delta_muscle_kg","delta_fat_pct","sleep_avg_hours"]:
            data[k] = float(data[k])
        return data
    except Exception:
        return simulate_week_with_claude_fallback(persona, diet, workouts_ids, pid, week_id, salt=nonce)
