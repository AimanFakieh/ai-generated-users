# --- Acegpt_Acegpt/utils_sim_dual.py ---
from __future__ import annotations
import math, hashlib, random
from typing import Dict, Any, Tuple
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None  # Py<=3.8 fallback not needed for your env

# Helpers
def _seed_from(pid: str, week_id: str) -> int:
    h = hashlib.sha256(f"{pid}::{week_id}".encode("utf-8")).hexdigest()
    # take 12 hex chars -> int
    return int(h[:12], 16)

def _to_float(x, default=0.0) -> float:
    try:
        if x is None: return float(default)
        if isinstance(x, (int, float)): return float(x)
        return float(str(x).strip())
    except Exception:
        return float(default)

def _riyadh_now() -> Tuple[str, str]:
    tz = ZoneInfo("Asia/Riyadh") if ZoneInfo else timezone.utc
    now = datetime.now(tz)
    return (now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S"))

def _adherence_factor(adherence: str) -> float:
    if not adherence:
        return 0.9
    a = str(adherence).lower()
    if "high" in a:      return 1.02
    if "med" in a or "mod" in a: return 0.95
    if "low" in a:       return 0.85
    # numeric like "0.7"?
    try:
        v = float(a)
        return max(0.75, min(1.05, v))
    except Exception:
        return 0.9

def _goal_deltas(goal: str) -> Tuple[Tuple[float,float], Tuple[float,float], Tuple[float,float]]:
    """
    Returns ranges for (delta_weight_kg, delta_muscle_kg, delta_fat_pct) for ONE week.
    """
    g = (goal or "").lower()
    if "fat" in g or "cut" in g or "loss" in g:
        return ((-1.0, -0.2),   (0.00, 0.20), (-1.0, -0.2))
    if "muscle" in g or "gain" in g or "bulk" in g:
        return ((-0.1, 0.6),    (0.10, 0.45), (-0.3, 0.1))
    if "recomp" in g or "re-com" in g:
        return ((-0.4, 0.3),    (0.05, 0.25), (-0.6, 0.0))
    # maintenance / general health
    return ((-0.2, 0.2), (0.00, 0.15), (-0.2, 0.2))

def _days_bonus(days_per_week: int) -> float:
    if days_per_week >= 5: return 1.10
    if days_per_week == 4: return 1.05
    if days_per_week == 3: return 1.00
    return 0.95

def _sleep_bonus(hours: float) -> float:
    if hours >= 8:   return 1.06
    if hours >= 7:   return 1.03
    if hours >= 6:   return 1.00
    return 0.94

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _rounded(x: float, nd=2) -> float:
    return float(f"{x:.{nd}f}")

def _make_feedback(pid: str, week_id: str, persona: Dict[str, Any], diet: Dict[str, Any], sim_text: str, notes_hint: str) -> Tuple[str, str]:
    # Build distinct feedback strings by mixing templates and persona fields.
    rnd = random.Random(_seed_from(pid, week_id) + 101)
    goal = str(persona.get("Primary_goal", "general fitness"))
    barrier = str(persona.get("Biggest_barrier", "time management"))
    days = persona.get("Days_per_week", 3)
    sex  = str(persona.get("Sex", "M"))
    kcal = _to_float(diet.get("Total_kcal_target_kcal"), 2000.0)

    styles = [
        "This week felt {tone}. I kept most meals on plan and energy was {energy}.",
        "Overall, adherence was {tone}. Training volume matched {days}/wk schedule.",
        "Diet quality was {tone}; meals aligned with target ~{kcal:.0f} kcal/day."
    ]
    tones = ["solid", "mostly good", "up-and-down", "challenging but improving"]
    energies = ["steady", "high on training days", "a bit flat", "better after day 3"]

    body = " ".join([
        rnd.choice(styles).format(tone=rnd.choice(tones), energy=rnd.choice(energies), days=days, kcal=kcal)
        for _ in range(2)
    ])
    # inject some of sim_text to keep “Ace voice” but limit size
    sim_snip = (sim_text or "").strip().replace("\n", " ")
    sim_snip = sim_snip[:220]
    free_text = f"{body} Key barrier was {barrier}. Goal focus: {goal}. {(' Reflection: ' + sim_snip) if sim_snip else ''}".strip()

    notes_templates = [
        "Next week: bump protein at dinner by ~10–15 g and keep sodium moderate; add a short walk after iftar/maghrib.",
        "Try swapping one carb source to whole-grain khubz or bulgur; maintain hydration earlier in the day.",
        "Keep NEAT up (8–10k steps). On heavy days, include laban or low-fat milk to support recovery.",
        "Reduce late caffeine; target lights-out earlier to protect sleep quality."
    ]
    notes = notes_hint or rnd.choice(notes_templates)
    return free_text, notes

def build_week1_payloads(
    pid: str,
    week_id: str,
    persona: Dict[str, Any],
    diet: Dict[str, Any],
    sim_text: str
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns (logs_payload, updated_persona_payload) as dicts.
    """
    rnd = random.Random(_seed_from(pid, week_id))

    # Date/Time
    date_str, time_str = _riyadh_now()

    # Persona metrics (pre)
    pre_w   = _to_float(persona.get("Weight_kg"), 70.0)
    pre_mus = _to_float(persona.get("Muscle_mass_kg"), max(0.35*pre_w, 22.0))
    pre_fat = _to_float(persona.get("Fat_percent"), 20.0)
    days    = int(_to_float(persona.get("Days_per_week"), 3))
    sleep_h = _to_float(persona.get("Sleep_hours"), 7.0)
    adher   = str(persona.get("Adherence_propensity", "Moderate"))

    # Diet target
    kcal_target = _to_float(diet.get("Total_kcal_target_kcal"), 2000.0)

    # Build multipliers
    mult = _adherence_factor(adher) * _days_bonus(days) * _sleep_bonus(sleep_h)
    # small random noise
    mult *= rnd.uniform(0.97, 1.03)
    daily_avg_kcal = _rounded(_clamp(kcal_target * mult, 1200.0, 4500.0), 1)

    # Goal-based expected changes
    goal = str(persona.get("Primary_goal", "maintenance"))
    (dw_lo, dw_hi), (dm_lo, dm_hi), (df_lo, df_hi) = _goal_deltas(goal)

    # tighten ranges with adherence/sleep
    tighten = (mult - 0.95)  # around 0 ≈ average plan match
    dw = rnd.uniform(dw_lo, dw_hi) * (1.0 + 0.6*tighten)
    dm = rnd.uniform(dm_lo, dm_hi) * (1.0 + 0.8*tighten)
    df = rnd.uniform(df_lo, df_hi) * (1.0 + 0.7*tighten)

    # ensure plausible coupling: muscle up rarely with big negative kcal unless recomposition
    if daily_avg_kcal < kcal_target * 0.9 and "gain" in goal.lower():
        dm *= 0.6

    post_w   = _rounded(_clamp(pre_w + dw, 30.0, 250.0), 2)
    post_mus = _rounded(_clamp(pre_mus + dm, 8.0, 120.0), 2)
    post_fat = _rounded(_clamp(pre_fat + df, 3.0, 65.0), 2)

    delta_w   = _rounded(post_w - pre_w, 2)
    delta_mus = _rounded(post_mus - pre_mus, 2)
    delta_fat = _rounded(post_fat - pre_fat, 2)

    # Texts
    free_text, notes = _make_feedback(pid, week_id, persona, diet, sim_text, notes_hint="")

    logs = {
        "Date": date_str,
        "Time": time_str,
        "free_text_feedback": free_text,
        "notes": notes,
        "daily_avg_kcal": daily_avg_kcal,
        "Pre_weight_kg": _rounded(pre_w, 2),
        "Pre_muscle_kg": _rounded(pre_mus, 2),
        "Pre_fat_pct": _rounded(pre_fat, 2),
        "Post_weight_kg": post_w,
        "Post_muscle_kg": post_mus,
        "Post_fat_pct": post_fat,
        "delta_weight_kg": delta_w,
        "delta_muscle_kg": delta_mus,
        "delta_fat_pct": delta_fat,
        "sleep_avg_hours": _rounded(_clamp(sleep_h + rnd.uniform(-0.3, 0.4), 4.0, 10.0), 2),
    }

    updated = {
        # copy-through fields
        "Age_band": persona.get("Age_band"),
        "Sex": persona.get("Sex"),
        "BMI": persona.get("BMI"),
        "Days_per_week": days,
        "Current_fitness_level": persona.get("Current_fitness_level"),
        "Primary_goal": persona.get("Primary_goal"),
        "Adherence_propensity": persona.get("Adherence_propensity"),
        "Cooking_skill": persona.get("Cooking_skill"),
        "Budjet_SAR_per_day": persona.get("Budjet_SAR_per_day"),
        # new metrics from logs
        "Weight_kg": post_w,
        "Muscle_mass_kg": post_mus,
        "Fat_percent": post_fat,
        "Sleep_hours": logs["sleep_avg_hours"],
        "notes": notes,
    }
    return logs, updated
