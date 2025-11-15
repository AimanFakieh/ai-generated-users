
from __future__ import annotations

import os
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytz
from google.cloud import firestore
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

# ------------------------------- Config ------------------------------------ #
PROJECT_ID = "fitech-2nd-trail"
TARGET_WEEK = "2025-W46"  # first week we already generated diets for
TZ = pytz.timezone("Asia/Riyadh")

# Prefer a stable alias; you can override via ANTHROPIC_MODEL env var if needed
DEFAULT_CLAUDE_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

# Workout menus by days per week
WORKOUT_CHOICE = {
    3: ["W33", "W29", "W21"],
    4: ["W25", "W21", "W25", "W21"],
    5: ["W03", "W07", "W11", "W15", "W21"],
}

# ----------------------------- Data classes -------------------------------- #
@dataclass
class Persona:
    pid: str
    Age_band: Optional[str] = None
    Sex: Optional[str] = None
    BMI: Optional[float] = None
    Days_per_week: Optional[int] = None
    Current_fitness_level: Optional[str] = None
    Primary_goal: Optional[str] = None
    Adherence_propensity: Optional[float] = None
    Cooking_skill: Optional[str] = None
    Budjet_SAR_per_day: Optional[float] = None
    Weight_kg: Optional[float] = None
    Muscle_mass_kg: Optional[float] = None
    Fat_percent: Optional[float] = None
    Sleep_hours: Optional[float] = None


@dataclass
class DietPlan:
    Total_kcal_target_kcal: Optional[float] = None
    Total_carbs_g: Optional[float] = None
    Total_fat_g: Optional[float] = None
    Total_protein_g: Optional[float] = None
    Total_fiber_g: Optional[float] = None
    Total_sodium_mg: Optional[float] = None
    meal1: Dict[str, Any] = None
    meal2: Dict[str, Any] = None
    meal3: Dict[str, Any] = None
    meal4: Dict[str, Any] = None


# ------------------------------ Utilities ---------------------------------- #
def now_strings() -> Tuple[str, str]:
    now = datetime.now(TZ)
    return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")


def coerce_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, str):
            xs = x.strip().replace(",", "")
            # remove trailing units
            xs = re.sub(r"[^0-9.\-]+$", "", xs)
            return float(xs)
        return float(x)
    except Exception:
        return None


def get_first(d: Dict[str, Any], *keys: str, default: Any = None):
    for k in keys:
        if k in d and d[k] is not None:
            v = d[k]
            # Convert Firestore Timestamp-like objects to str
            if hasattr(v, "isoformat") and not isinstance(v, (str, int, float)):
                try:
                    return v.isoformat()
                except Exception:
                    return str(v)
            return v
    return default


def deep_snip(obj: Any, max_len: int = 2000) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def json_from_text(text: str) -> Dict[str, Any]:
    """Extract the first JSON object found in text. Handles ```json fences."""
    if not text:
        return {}
    # Strip code fences
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.I)
    if fence:
        block = fence.group(1)
        try:
            return json.loads(block)
        except Exception:
            pass
    # Fallback: find first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start : end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass
    # Last resort
    try:
        return json.loads(text)
    except Exception:
        return {}


# --------------------------- Firestore access ------------------------------ #
def fs_client() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID)


def load_personas(db: firestore.Client) -> List[Persona]:
    personas: List[Persona] = []
    for doc in db.collection("personas").stream():
        data = doc.to_dict() or {}
        pid = doc.id
        p = Persona(
            pid=pid,
            Age_band=get_first(data, "Age_band"),
            Sex=get_first(data, "Sex"),
            BMI=coerce_float(get_first(data, "BMI")),
            Days_per_week=int(coerce_float(get_first(data, "Days_per_week")) or 0) or None,
            Current_fitness_level=get_first(data, "Current_fitness_level"),
            Primary_goal=get_first(data, "Primary_goal"),
            Adherence_propensity=coerce_float(
                get_first(data, "Adherence_propensity", "Adherence propensity")
            ),
            Cooking_skill=get_first(data, "Cooking_skill"),
            Budjet_SAR_per_day=coerce_float(
                get_first(data, "Budjet_SAR_per_day", "Budget_SAR_per_day", "Budget_per_day_SAR")
            ),
            Weight_kg=coerce_float(get_first(data, "Weight_kg")),
            Muscle_mass_kg=coerce_float(get_first(data, "Muscle_mass_kg")),
            Fat_percent=coerce_float(get_first(data, "Fat_percent")),
            Sleep_hours=coerce_float(get_first(data, "Sleep_hours")),
        )
        personas.append(p)
    return personas


def read_diet_plan(db: firestore.Client, pid: str, week: str) -> Optional[DietPlan]:
    ref = (
        db.collection("experiments")
        .document("Experiment_OpenAI")
        .collection("users")
        .document(pid)
        .collection("weeks")
        .document(week)
        .collection("diet")
        .document("plan")
    )
    snap = ref.get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}

    def meal(prefix: str) -> Dict[str, Any]:
        return {
            "name": get_first(d, prefix),
            "kcal": coerce_float(
                get_first(d, f"{prefix}_kcal_target_kcal", f"{prefix}_kcal_target_kca")
            ),
            "carbs_g": coerce_float(get_first(d, f"{prefix}_carbs_g")),
            "fat_g": coerce_float(get_first(d, f"{prefix}_fat_g")),
            "protein_g": coerce_float(get_first(d, f"{prefix}_protein_g")),
            "fiber_g": coerce_float(get_first(d, f"{prefix}_fiber_g")),
            "sodium_mg": coerce_float(get_first(d, f"{prefix}_sodium_mg")),
        }

    return DietPlan(
        Total_kcal_target_kcal=coerce_float(get_first(d, "Total_kcal_target_kcal")),
        Total_carbs_g=coerce_float(get_first(d, "Total_carbs_g")),
        Total_fat_g=coerce_float(get_first(d, "Total_fat_g")),
        Total_protein_g=coerce_float(get_first(d, "Total_protein_g")),
        Total_fiber_g=coerce_float(get_first(d, "Total_fiber_g")),
        Total_sodium_mg=coerce_float(get_first(d, "Total_sodium_mg")),
        meal1=meal("1st_meal"),
        meal2=meal("2nd_meal"),
        meal3=meal("3rd_meal"),
        meal4=meal("4th_meal"),
    )


def read_workouts(db: firestore.Client, ids: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for wid in ids:
        snap = db.collection("workouts").document(wid).get()
        if not snap.exists:
            out.append({"id": wid, "title": wid, "exercises": []})
            continue
        w = snap.to_dict() or {}
        out.append(
            {
                "id": wid,
                "title": get_first(w, "title", "name", default=wid),
                "exercises": get_first(w, "exercises", "items", default=[]),
                "meta": {k: v for k, v in w.items() if k not in {"title", "name", "exercises", "items"}},
            }
        )
    return out


# ------------------------------ Anthropic ---------------------------------- #

def build_system_prompt() -> str:
    return (
        "You are Claude Sonnet acting as a *real person* who followed a one-week diet and workout plan. "
        "Simulate faithfully and return only JSON according to the requested schema. "
        "Use realistic weekly changes (typical weight change ±0.6 kg; muscle change up to ±0.25 kg; fat% change ±1.0). "
        "Base adherence and sleep on the persona's Adherence_propensity and Sleep_hours."
    )


def build_user_prompt(p: Persona, d: DietPlan, workouts: List[Dict[str, Any]]) -> str:
    persona_block = {
        "Age_band": p.Age_band,
        "Sex": p.Sex,
        "BMI": p.BMI,
        "Days_per_week": p.Days_per_week,
        "Current_fitness_level": p.Current_fitness_level,
        "Primary_goal": p.Primary_goal,
        "Adherence_propensity": p.Adherence_propensity,
        "Cooking_skill": p.Cooking_skill,
        "Budjet_SAR_per_day": p.Budjet_SAR_per_day,
        "Weight_kg": p.Weight_kg,
        "Muscle_mass_kg": p.Muscle_mass_kg,
        "Fat_percent": p.Fat_percent,
        "Sleep_hours": p.Sleep_hours,
    }

    diet_block = {
        "Total_kcal_target_kcal": d.Total_kcal_target_kcal,
        "Total_carbs_g": d.Total_carbs_g,
        "Total_fat_g": d.Total_fat_g,
        "Total_protein_g": d.Total_protein_g,
        "Total_fiber_g": d.Total_fiber_g,
        "Total_sodium_mg": d.Total_sodium_mg,
        "1st_meal": d.meal1,
        "2nd_meal": d.meal2,
        "3rd_meal": d.meal3,
        "4th_meal": d.meal4,
    }

    user_instructions = (
        f"Persona (from /personas/{p.pid}) and Diet (from Week {TARGET_WEEK}) below.\n"
        "You followed the diet (repeat the one-day plan 7x) and the workouts for the week.\n"
        "Return ONLY a JSON object matching this exact schema keys: \n"
        "{\n"
        "  \"Date\": \"YYYY-MM-DD\",\n"
        "  \"Time\": \"HH:MM:SS\",\n"
        "  \"free_text_feedback\": \"...\",\n"
        "  \"notes\": \"...\",\n"
        "  \"daily_avg_kcal\": number,\n"
        "  \"Pre_weight_kg\": number,\n"
        "  \"Pre_muscle_kg\": number,\n"
        "  \"Pre_fat_pct\": number,\n"
        "  \"Post_weight_kg\": number,\n"
        "  \"Post_muscle_kg\": number,\n"
        "  \"Post_fat_pct\": number,\n"
        "  \"delta_weight_kg\": number,\n"
        "  \"delta_muscle_kg\": number,\n"
        "  \"delta_fat_pct\": number,\n"
        "  \"sleep_avg_hours\": number\n"
        "}\n"
        "Rules: numeric fields must be numbers (not strings). Keep changes small and plausible for one week."
    )

    workouts_brief = [
        {
            "id": w.get("id"),
            "title": w.get("title"),
            "exercises_count": len(w.get("exercises") or []),
        }
        for w in workouts
    ]

    payload = {
        "persona": persona_block,
        "diet": diet_block,
        "workouts_this_week": workouts_brief,
        "week": TARGET_WEEK,
        "instructions": user_instructions,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
def call_claude(client: Anthropic, model: str, system_prompt: str, user_payload: str) -> Dict[str, Any]:
    msg = client.messages.create(
        model=model,
        system=system_prompt,
        max_tokens=1200,
        temperature=0.6,
        messages=[{"role": "user", "content": user_payload}],
    )
    # Concatenate all text parts
    text_parts = []
    for part in msg.content:
        if getattr(part, "type", None) == "text":
            text_parts.append(part.text)
        elif isinstance(part, dict) and part.get("type") == "text":
            text_parts.append(part.get("text", ""))
    text = "\n".join([t for t in text_parts if t])
    data = json_from_text(text)
    if not data:
        raise RuntimeError("Claude returned no parseable JSON")
    return data


def clamp_and_fill(p: Persona, data: Dict[str, Any]) -> Dict[str, Any]:
    # Provide defaults from persona if pre values are missing; then clamp weekly changes
    pre_w = coerce_float(data.get("Pre_weight_kg")) or (p.Weight_kg or 0.0)
    pre_m = coerce_float(data.get("Pre_muscle_kg")) or (p.Muscle_mass_kg or 0.0)
    pre_f = coerce_float(data.get("Pre_fat_pct")) or (p.Fat_percent or 0.0)

    post_w = coerce_float(data.get("Post_weight_kg"))
    post_m = coerce_float(data.get("Post_muscle_kg"))
    post_f = coerce_float(data.get("Post_fat_pct"))

    # Reasonable ranges for one week
    def clamp(x: Optional[float], lo: float, hi: float, fallback: float) -> float:
        if x is None or math.isnan(x) or math.isinf(x):
            return fallback
        return max(lo, min(hi, x))

    # If Post is missing, infer tiny change based on adherence
    adh = p.Adherence_propensity or 0.6
    delta_w = coerce_float(data.get("delta_weight_kg"))
    delta_m = coerce_float(data.get("delta_muscle_kg"))
    delta_f = coerce_float(data.get("delta_fat_pct"))

    if post_w is None:
        # ±0.6 kg scaled by adherence away from maintenance
        guess_w = pre_w + (adh - 0.5) * 1.0  # ~[-0.5,+0.5]
        post_w = clamp(guess_w, pre_w - 0.8, pre_w + 0.8, pre_w)
    if post_m is None:
        guess_m = pre_m + max(0.0, adh - 0.4) * 0.2  # up to +0.12kg
        post_m = clamp(guess_m, pre_m - 0.15, pre_m + 0.25, pre_m)
    if post_f is None:
        guess_f = pre_f + (0.45 - adh) * 0.8  # small shift
        post_f = clamp(guess_f, max(0.0, pre_f - 1.2), pre_f + 1.2, pre_f)

    # Fill deltas if missing
    if delta_w is None:
        delta_w = post_w - pre_w
    if delta_m is None:
        delta_m = post_m - pre_m
    if delta_f is None:
        delta_f = post_f - pre_f

    # Sleep default
    sleep_avg = coerce_float(data.get("sleep_avg_hours")) or (p.Sleep_hours or 7.0)

    # Daily kcal default
    daily_kcal = coerce_float(data.get("daily_avg_kcal"))
    if daily_kcal is None:
        daily_kcal = 0.0  # we won't block; diet target was in the plan

    # Date/time
    date_str = data.get("Date") or now_strings()[0]
    time_str = data.get("Time") or now_strings()[1]

    clean = {
        "Date": date_str,
        "Time": time_str,
        "free_text_feedback": str(data.get("free_text_feedback", ""))[:4000],
        "notes": str(data.get("notes", ""))[:2000],
        "daily_avg_kcal": round(float(daily_kcal), 2) if isinstance(daily_kcal, (int, float)) else 0.0,
        "Pre_weight_kg": round(float(pre_w), 2) if pre_w else 0.0,
        "Pre_muscle_kg": round(float(pre_m), 2) if pre_m else 0.0,
        "Pre_fat_pct": round(float(pre_f), 2) if pre_f else 0.0,
        "Post_weight_kg": round(float(post_w), 2),
        "Post_muscle_kg": round(float(post_m), 2),
        "Post_fat_pct": round(float(post_f), 2),
        "delta_weight_kg": round(float(delta_w), 2),
        "delta_muscle_kg": round(float(delta_m), 2),
        "delta_fat_pct": round(float(delta_f), 2),
        "sleep_avg_hours": round(float(sleep_avg), 2),
    }
    return clean


# ------------------------------- Main flow --------------------------------- #

def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[FATAL] ANTHROPIC_API_KEY is not set.")
        return 2

    db = fs_client()
    client = Anthropic(api_key=api_key)

    personas = load_personas(db)
    if not personas:
        print("[WARN] No personas found under /personas")
        return 0

    system_prompt = build_system_prompt()
    processed = 0

    for p in personas:
        try:
            diet = read_diet_plan(db, p.pid, TARGET_WEEK)
            if not diet:
                print(f"[SKIP] {p.pid}: No diet plan found for week {TARGET_WEEK}")
                continue

            days = p.Days_per_week or 3
            workout_ids = WORKOUT_CHOICE.get(days, WORKOUT_CHOICE[3])
            workouts = read_workouts(db, workout_ids)

            user_payload = build_user_prompt(p, diet, workouts)

            # First try the configured/default model; if that fails due to Not Found, try the alias.
            model_to_use = DEFAULT_CLAUDE_MODEL
            try:
                raw = call_claude(client, model_to_use, system_prompt, user_payload)
            except Exception as e:
                # If model name specific fails, fallback to the alias (same as default) and then to a known older alias
                if model_to_use != "claude-sonnet-4-5":
                    try:
                        raw = call_claude(client, "claude-sonnet-4-5", system_prompt, user_payload)
                    except Exception:
                        raise
                else:
                    raise

            clean = clamp_and_fill(p, raw)

            # Write LOGS
            logs_ref = (
                db.collection("experiments")
                .document("Experiment_OpenAI")
                .collection("users")
                .document(p.pid)
                .collection("weeks")
                .document(TARGET_WEEK)
                .collection("logs")
                .document("plan")
            )
            logs_ref.set(clean)

            # Write UPDATED PERSONA
            updated = {
                "Age_band": p.Age_band,
                "Sex": p.Sex,
                "BMI": p.BMI,
                "Days_per_week": p.Days_per_week,
                "Current_fitness_level": p.Current_fitness_level,
                "Primary_goal": p.Primary_goal,
                "Adherence_propensity": p.Adherence_propensity,
                "Cooking_skill": p.Cooking_skill,
                "Budjet_SAR_per_day": p.Budjet_SAR_per_day,
                "Weight_kg": clean["Post_weight_kg"],
                "Muscle_mass_kg": clean["Post_muscle_kg"],
                "Fat_percent": clean["Post_fat_pct"],
                "Sleep_hours": clean["sleep_avg_hours"],
                "notes": clean.get("notes", ""),
            }

            upd_ref = (
                db.collection("experiments")
                .document("Experiment_OpenAI")
                .collection("users")
                .document(p.pid)
                .collection("weeks")
                .document(TARGET_WEEK)
                .collection("updated_persona")
                .document("plan")
            )
            upd_ref.set(updated)

            print(f"[OK] {p.pid} -> logs & updated_persona saved for {TARGET_WEEK}")
            processed += 1

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[ERROR] {p.pid}: {e}")
            continue

    print(f"[DONE] Processed {processed} persona(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
