# --- acegpt_client_dual_v2.py ---
from __future__ import annotations
import os, json, hashlib, random, math
from typing import Dict, Any
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from config_dual import (
    HF_COMPLETIONS_URL, HF_CHAT_URL,
    ACE_MODEL, ACE_PROVIDER,
    ACE_MAX_TOKENS, ACE_TEMPERATURE, ACE_TOP_P,
    DEFAULT_STOP, hf_headers
)

# ---------- helpers ----------
def _variety_key(pid: str, week_id: str) -> str:
    base = f"{pid}:{week_id}:v3"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def _rng_from_key(key: str) -> random.Random:
    return random.Random(int(key[:16], 16))

def _pick(rng: random.Random, choices):
    return choices[rng.randrange(len(choices))]

def _jitter(rng: random.Random, value: float, pct: float = 0.1, min_val: float | None = None) -> float:
    """±pct jitter"""
    v = value * (1.0 + rng.uniform(-pct, pct))
    if min_val is not None:
        v = max(min_val, v)
    return v

# ---------- diverse fallback plan ----------
def _fallback_saudi_plan(pid: str, week_id: str) -> Dict[str, Any]:
    """
    Returns a *different* Saudi-style plan per (pid, week) with varied meals/macros/sodium.
    """
    key = _variety_key(pid, week_id)
    rng = _rng_from_key(key)

    # 4 rotating breakfast/sahoor ideas
    breakfasts = [
        "Balila (chickpeas) with cumin + lemon; laban; 1 date",
        "Ful medames with olive oil + tomato; whole-wheat tamees",
        "Oats cooked in milk; chopped dates + walnuts; cinnamon",
        "Saudi shakshuka (eggs with peppers/tomato); small saj bread"
    ]

    lunches = [
        "Kabsa (chicken) with basmati rice; mixed salad; lemon dressing",
        "Mandi (lamb) small portion; grilled zucchini; yoghurt",
        "Sayadiyah (spiced fish + rice); tahini salad",
        "Chicken jareesh (cracked wheat stew); cucumber mint salad"
    ]

    dinners = [
        "Grilled chicken tawook; fattoush salad; small pita",
        "Shrimp with sazbiya spices; brown rice; arugula salad",
        "Beef kofta (baked); tabbouleh; tahini drizzle",
        "Grilled hammour; roasted sweet potato; steamed broccoli"
    ]

    snacks = [
        "Arabic coffee + 3 dates",
        "Low-fat laban + almonds (handful)",
        "Labneh with cucumber + mint; rye crackers",
        "Banana + peanut butter (1 tbsp)"
    ]

    b = _pick(rng, breakfasts)
    l = _pick(rng, lunches)
    d = _pick(rng, dinners)
    s = _pick(rng, snacks)

    # Macro target varies by theme
    themes = [
        ("lean_gain",   2400, 0.28, 0.47, 0.25),
        ("fat_loss",    1900, 0.32, 0.43, 0.25),
        ("recomp",      2150, 0.30, 0.45, 0.25),
        ("endurance",   2300, 0.22, 0.56, 0.22),
        ("high_protein",2200, 0.35, 0.40, 0.25),
    ]
    theme, base_kcal, p, c, f = _pick(rng, themes)

    kcal = int(round(_jitter(rng, base_kcal, 0.12), 0))
    prot_g = int(round((kcal * p) / 4.0))
    carb_g = int(round((kcal * c) / 4.0))
    fat_g  = int(round((kcal * f) / 9.0))

    # Sodium varies per seed and week (broader range, but reasonable)
    sodium = int(round(_jitter(rng, 1850 + rng.randint(-250, 250), 0.15, 900), 0))

    return {
        "1st_meal": f"Breakfast: {b}",
        "2nd_meal": f"Lunch: {l}",
        "3rd_meal": f"Snack: {s}",
        "4th_meal": f"Dinner: {d}",
        "Total_kcal_target_kcal": kcal,
        "Protein_g": prot_g,
        "Carbs_g": carb_g,
        "Fat_g": fat_g,
        "Total_sodium_mg": sodium,
        "variety_theme": theme,
        "model": ACE_MODEL,
        "provider": ACE_PROVIDER,
        "source": "fallback-varied-v3"
    }

# ---------- retrying HTTP completions ----------
class AceHTTPError(RuntimeError):
    pass

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=6))
def _complete(prompt: str, *, temperature: float | None = None, max_tokens: int | None = None) -> str:
    body = {
        "model": ACE_MODEL,
        "prompt": prompt,
        "temperature": temperature if temperature is not None else ACE_TEMPERATURE,
        "top_p": ACE_TOP_P,
        "max_tokens": max_tokens if max_tokens is not None else ACE_MAX_TOKENS,
        "stop": DEFAULT_STOP,
    }
    r = requests.post(HF_COMPLETIONS_URL, headers=hf_headers(), json=body, timeout=120)
    if r.status_code >= 500:
        # transient -> let tenacity retry
        raise AceHTTPError(f"AceGPT status {r.status_code}: {r.text}")
    if r.status_code != 200:
        # fail fast
        raise RuntimeError(f"AceGPT status {r.status_code}: {r.text}")
    data = r.json()
    txt = data.get("choices", [{}])[0].get("text", "").strip()
    return txt or ""

# ---------- public API ----------
def get_diet_from_ace(prompt: str, *, pid: str, week_id: str, retries: int = 2) -> Dict[str, Any]:
    """
    Try the endpoint; if it fails or returns unusable text, return a diverse fallback
    keyed by (pid, week_id) so results always differ across personas & weeks.
    """
    try:
        out = _complete(prompt, temperature=ACE_TEMPERATURE, max_tokens=ACE_MAX_TOKENS)
        # Try a very light parser: we only care about presence of key fields. If not found, fallback.
        lower = out.lower()
        looks_ok = any(k in lower for k in ["breakfast", "meal 1", "lunch", "dinner"])
        if not looks_ok:
            return _fallback_saudi_plan(pid, week_id)

        # Heuristic extraction; still inject diversity into sodium/macros if missing
        key = _variety_key(pid, week_id)
        rng = _rng_from_key(key)

        def _extract_line(prefixes):
            for line in out.splitlines():
                l = line.strip()
                for p in prefixes:
                    if l.lower().startswith(p):
                        return l
            return None

        m1 = _extract_line(["breakfast", "meal 1"])
        m2 = _extract_line(["lunch", "meal 2"])
        m3 = _extract_line(["snack", "meal 3"])
        m4 = _extract_line(["dinner", "meal 4"])

        kcal = None
        for line in out.splitlines():
            if "kcal" in line.lower() or "calorie" in line.lower():
                # crude grab of first number
                import re
                m = re.search(r"(\d{3,4})", line)
                if m: kcal = int(m.group(1)); break

        # If anything is missing, borrow from varied fallback to ensure completeness & diversity
        fallback = _fallback_saudi_plan(pid, week_id)
        diet = {
            "1st_meal": m1 or fallback["1st_meal"],
            "2nd_meal": m2 or fallback["2nd_meal"],
            "3rd_meal": m3 or fallback["3rd_meal"],
            "4th_meal": m4 or fallback["4th_meal"],
            "Total_kcal_target_kcal": kcal or fallback["Total_kcal_target_kcal"],
            "Protein_g": fallback["Protein_g"],
            "Carbs_g": fallback["Carbs_g"],
            "Fat_g": fallback["Fat_g"],
            "Total_sodium_mg": fallback["Total_sodium_mg"],
            "variety_theme": fallback["variety_theme"],
            "model": ACE_MODEL,
            "provider": ACE_PROVIDER,
            "source": "hf+fallback-mixed-v3" if not (m1 and m2 and m3 and m4 and kcal) else "hf-structured-v3",
            "raw_text": out[:4000],
        }
        return diet
    except Exception:
        # On any failure -> diverse fallback
        return _fallback_saudi_plan(pid, week_id)

def generate_feedback(persona: Dict[str, Any], diet: Dict[str, Any], workouts, seed_key: str) -> Dict[str, str]:
    """
    Produce distinct free_text_feedback + notes per (persona, week) with persona-aware content.
    """
    rng = _rng_from_key(hashlib.sha256(seed_key.encode()).hexdigest())

    goal = str(persona.get("Primary_goal", "recomp")).lower()
    days = str(persona.get("Days_per_week", 4))
    budget = str(persona.get("Budjet_SAR_per_day", "Medium"))
    level = str(persona.get("Current_fitness_level", "Beginner"))
    sleep = str(persona.get("Sleep_hours", 7))
    theme = diet.get("variety_theme", "recomp")

    angles = [
        "hydration timing (esp. around training)",
        "fiber distribution across the day",
        "protein spread to hit leucine threshold",
        "carb timing before/after harder sessions",
        "sodium & bloat control with spices/herbs",
        "sleep routine and late-meal cut-off",
        "simple meal-prep to support adherence",
        "restaurant swaps for social meals",
    ]
    tone = _pick(rng, [
        "Keep it steady and practical.",
        "Nice momentum—stay consistent.",
        "Good base—tighten timing this week.",
        "Progressing—focus on recovery quality.",
        "Solid week—dial in hydration and steps.",
        "You’re building rhythm—keep meals simple.",
    ])

    focus1 = _pick(rng, angles)
    focus2 = _pick(rng, [a for a in angles if a != focus1])

    ft = (
        f"{tone} Goal looks like **{goal}** with {days} sessions/week at {level} level. "
        f"This week’s theme leans **{theme}** within a **{budget}** budget. "
        f"Prioritize {focus1}; also watch {focus2}. "
        f"Sleep target ≈ {sleep}h—protect it with a consistent last-meal cut-off."
    )

    sodium = diet.get("Total_sodium_mg")
    kcal   = diet.get("Total_kcal_target_kcal")
    wkids  = ", ".join(workouts) if workouts else "W-general"

    notes = (
        f"kcal≈{kcal}; sodium≈{sodium} mg; workouts={wkids}. "
        f"Track water intake; 1 glass with each meal. "
        f"Add 1–2k steps on rest days. "
        f"Swap starchy side at dinner 2x this week if morning weight spikes."
    )

    return {"free_text_feedback": ft, "notes": notes}
