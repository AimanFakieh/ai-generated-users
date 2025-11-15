# acegpt_client_v12.py
import os, json, time, requests
from typing import Dict, Any, Optional
from config_year_v12 import ACE_MAX_TOKENS, ACE_TEMPERATURE
from utils_json_v12 import extract_first_json, ensure_diet_shape, diversify_meals

def _short_line(p: Dict[str, Any]) -> str:
    return (
        f"Age={p.get('Age_band')} Sex={p.get('Sex')} BMI={p.get('BMI')} "
        f"Days={p.get('Days_per_week')} Level={p.get('Current_fitness_level')} Goal={p.get('Primary_goal')} "
        f"Adherence={p.get('Adherence_propensity')} Cooking={p.get('Cooking_skill')} Budget={p.get('Budjet_SAR_per_day')} "
        f"W={p.get('Weight_kg')}kg M={p.get('Muscle_mass_kg')}kg F%={p.get('Fat_percent')} Sleep={p.get('Sleep_hours')}h"
    )

def _schema(variation: str) -> str:
    return (
        "Return ONE JSON with keys only: "
        "Note, Total_kcal_target_kcal, Total_carbs_g, Total_fat_g, Total_protein_g, Total_fiber_g, Total_sodium_mg, "
        "1st_meal, 1st_meal_kcal_target_kcal, 1st_meal_carbs_g, 1st_meal_fat_g, 1st_meal_protein_g, 1st_meal_fiber_g, 1st_meal_sodium_mg, "
        "2nd_meal, 2nd_meal_kcal_target_kcal, 2nd_meal_carbs_g, 2nd_meal_fat_g, 2nd_meal_protein_g, 2nd_meal_fiber_g, 2nd_meal_sodium_mg, "
        "3rd_meal, 3rd_meal_kcal_target_kcal, 3rd_meal_carbs_g, 3rd_meal_fat_g, 3rd_meal_protein_g, 3rd_meal_fiber_g, 3rd_meal_sodium_mg, "
        "4th_meal, 4th_meal_kcal_target_kcal, 4th_meal_carbs_g, 4th_meal_fat_g, 4th_meal_protein_g, 4th_meal_fiber_g, 4th_meal_sodium_mg. "
        "All numbers must be numeric. Distribute macros/sodium across meals (avoid identical values). "
        "Use Saudi dishes; vary across personas/weeks. "
        f"VARIATION_TAG={variation}. No prose outside JSON."
    )

def _build_prompt(persona: Dict[str, Any], pid: str, week_id: str) -> str:
    return (
        "Design a ONE-DAY Saudi-style plan (repeat x7). Respect budget/cooking/goal/sleep/training. "
        "Be realistic; include per-meal macros and sodium. "
        f"Persona: {_short_line(persona)}\n" + _schema(f"{pid}|{week_id}")
    )

def _call_chat(prompt: str) -> str:
    url = os.getenv("ACEGPT_CHAT_URL", "")
    key = os.getenv("HF_API_KEY", "")
    if not url or not key:
        raise RuntimeError("ACEGPT_CHAT_URL or HF_API_KEY not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": "FreedomIntelligence/AceGPT-13B-chat",
        "temperature": ACE_TEMPERATURE,
        "max_tokens": ACE_MAX_TOKENS,
        "messages": [
            {"role": "system", "content": "You are a precise nutrition assistant. Output JSON only."},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    r = requests.post(url, headers=headers, json=body, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"AceGPT chat status {r.status_code}: {r.text}")
    return r.json()["choices"][0]["message"]["content"]

def _call_text(prompt: str) -> str:
    url = os.getenv("ACEGPT_URL", "")
    key = os.getenv("HF_API_KEY", "")
    if not url or not key:
        raise RuntimeError("ACEGPT_URL or HF_API_KEY not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"inputs": prompt + "\n\nJSON:", "parameters": {"max_new_tokens": ACE_MAX_TOKENS, "temperature": ACE_TEMPERATURE, "return_full_text": False}}
    r = requests.post(url, headers=headers, json=body, timeout=90)
    if r.status_code != 200:
        raise RuntimeError(f"AceGPT status {r.status_code}: {r.text}")
    data = r.json()
    if isinstance(data, list) and data and "generated_text" in data[0]:
        return data[0]["generated_text"]
    if isinstance(data, dict) and "choices" in data:
        ch = data["choices"][0]
        return ch.get("text") or ch.get("message", {}).get("content", "")
    return json.dumps(data)

def _fallback(persona: Dict[str, Any]) -> Dict[str, Any]:
    # Minimal fallback; totals diversified later
    return {
        "Note": "Fallback plan.",
        "Total_kcal_target_kcal": 0.0, "Total_carbs_g": 0.0, "Total_fat_g": 0.0, "Total_protein_g": 0.0,
        "Total_fiber_g": 0.0, "Total_sodium_mg": 0.0,
        "1st_meal":"", "2nd_meal":"", "3rd_meal":"", "4th_meal":"",
        "1st_meal_kcal_target_kcal":0.0,"1st_meal_carbs_g":0.0,"1st_meal_fat_g":0.0,"1st_meal_protein_g":0.0,"1st_meal_fiber_g":0.0,"1st_meal_sodium_mg":0.0,
        "2nd_meal_kcal_target_kcal":0.0,"2nd_meal_carbs_g":0.0,"2nd_meal_fat_g":0.0,"2nd_meal_protein_g":0.0,"2nd_meal_fiber_g":0.0,"2nd_meal_sodium_mg":0.0,
        "3rd_meal_kcal_target_kcal":0.0,"3rd_meal_carbs_g":0.0,"3rd_meal_fat_g":0.0,"3rd_meal_protein_g":0.0,"3rd_meal_fiber_g":0.0,"3rd_meal_sodium_mg":0.0,
        "4th_meal_kcal_target_kcal":0.0,"4th_meal_carbs_g":0.0,"4th_meal_fat_g":0.0,"4th_meal_protein_g":0.0,"4th_meal_fiber_g":0.0,"4th_meal_sodium_mg":0.0,
    }

def get_diet_from_ace(
    persona: Dict[str, Any], pid: str, week_id: str, last_week_diet: Optional[Dict[str, Any]], diversify_nonce: int = 0
) -> Dict[str, Any]:
    prompt = _build_prompt(persona, pid, week_id)
    text = ""
    for attempt in range(2):
        try:
            if os.getenv("ACEGPT_CHAT_URL"):
                text = _call_chat(prompt)
            else:
                text = _call_text(prompt)
            if not text: raise RuntimeError("AceGPT returned empty content")
            raw = extract_first_json(text)
            diet = ensure_diet_shape(raw)
            return diversify_meals(diet, pid, week_id, persona, last_week_diet, nonce=diversify_nonce)
        except Exception:
            time.sleep(1 + attempt)
    # fallback + diversify
    diet = ensure_diet_shape(_fallback(persona))
    return diversify_meals(diet, pid, week_id, persona, last_week_diet, nonce=diversify_nonce)
