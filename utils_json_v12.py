# utils_json_v12.py
import json, hashlib, random, math
from typing import Dict, Any, List, Optional

SAUDI_MEAL_NAMES = [
    "Masoub (banana+dates+milk)",
    "Chicken Kabsa (lean rice)",
    "Jareesh with laban",
    "Ful medames + tamees",
    "Balila cup (chickpeas)",
    "Grilled Hammour + rice + salad",
    "Labneh + cucumbers + olives + bread",
    "Tuna salad + lemon + olive oil",
    "Margoog (light) + salad",
    "Thareed (lean beef + veg)",
    "Harees (light) + salad",
    "Egg shakshouka + bread",
    "Date + laban snack",
]

def _f(v, default=0.0) -> float:
    try:
        if v is None: return float(default)
        if isinstance(v, str) and v.strip()=="":
            return float(default)
        return float(v)
    except Exception:
        return float(default)

def extract_first_json(text: str) -> Dict[str, Any]:
    if not text: raise ValueError("Empty response")
    if "```" in text:
        parts = text.split("```")
        candidates = [c for c in parts if "{" in c and "}" in c]
        if candidates:
            s = candidates[0]
            s2 = s[s.find("{"):s.rfind("}")+1]
            return json.loads(s2)
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1 or e <= s: raise ValueError("No JSON object found")
    return json.loads(text[s:e+1])

def _ensure_meal_label(val, idx):
    if isinstance(val, str) and val.strip():
        return val.strip()
    return SAUDI_MEAL_NAMES[idx % len(SAUDI_MEAL_NAMES)]

def _pull_nested_meal_num(obj: Dict[str, Any], key: str, fallback=0.0):
    if key in obj: return _f(obj.get(key), fallback)
    prefix = key.split("_")[0]  # '1st' or '2nd'...
    nested = obj.get(f"{prefix}_meal")
    if isinstance(nested, dict) and key in nested:
        return _f(nested.get(key), fallback)
    return float(fallback)

def ensure_diet_shape(obj: Dict[str, Any]) -> Dict[str, Any]:
    totals = ["Total_kcal_target_kcal","Total_carbs_g","Total_fat_g",
              "Total_protein_g","Total_fiber_g","Total_sodium_mg"]
    meals  = ["1st","2nd","3rd","4th"]
    mkeys  = ["kcal_target_kcal","carbs_g","fat_g","protein_g","fiber_g","sodium_mg"]

    for k in totals:
        obj[k] = _f(obj.get(k, 0.0), 0.0)

    for i, m in enumerate(meals):
        name_key = f"{m}_meal"
        obj[name_key] = _ensure_meal_label(obj.get(name_key), i)
        for mk in mkeys:
            full = f"{m}_meal_{mk}"
            obj[full] = _pull_nested_meal_num(obj, full, 0.0)

    # if totals missing, recompute from meals
    def _sum(mm): return float(sum(obj[f"{m}_meal_{mm}"] for m in meals))
    if obj["Total_kcal_target_kcal"]==0.0:
        obj["Total_kcal_target_kcal"] = _sum("kcal_target_kcal")
    if obj["Total_carbs_g"]==0.0:
        obj["Total_carbs_g"] = _sum("carbs_g")
    if obj["Total_fat_g"]==0.0:
        obj["Total_fat_g"] = _sum("fat_g")
    if obj["Total_protein_g"]==0.0:
        obj["Total_protein_g"] = _sum("protein_g")
    if obj["Total_fiber_g"]==0.0:
        obj["Total_fiber_g"] = _sum("fiber_g")
    if obj["Total_sodium_mg"]==0.0:
        obj["Total_sodium_mg"] = _sum("sodium_mg")

    if not obj.get("Note"):
        obj["Note"] = "Saudi-inspired plan. Adjust portions if training load changes."

    return obj

def _sha_seed(s: str) -> int:
    return int(hashlib.sha256(s.encode("utf-8")).hexdigest()[:12], 16)

def _dirichlet4(rnd: random.Random) -> List[float]:
    xs = [rnd.random() + 0.3 for _ in range(4)]
    s  = sum(xs)
    return [x/s for x in xs]

def _split(total: float, rnd: random.Random) -> List[float]:
    if total <= 0: return [0.0,0.0,0.0,0.0]
    w = _dirichlet4(rnd)
    return [round(total*wi, 1) for wi in w]

def _all_meals_identical(obj: Dict[str, Any], tol=1e-6) -> bool:
    meals = ["1st","2nd","3rd","4th"]
    keys  = ["kcal_target_kcal","carbs_g","fat_g","protein_g","fiber_g","sodium_mg"]
    first = {k: obj[f"1st_meal_{k}"] for k in keys}
    for m in meals[1:]:
        for k in keys:
            if abs(_f(obj[f"{m}_meal_{k}"]) - _f(first[k])) > tol:
                return False
    # also check identical meal names
    n0 = str(obj.get("1st_meal",""))
    if any(str(obj.get(f"{m}_meal","")) != n0 for m in meals[1:]):
        return False
    return True

def _similar_overview(a: Dict[str, Any], b: Optional[Dict[str, Any]], tol=1e-6) -> bool:
    if not b: return False
    # same meal names OR nearly equal totals implies similar overview
    same_names = all(str(a.get(f"{m}_meal","")) == str(b.get(f"{m}_meal","")) for m in ["1st","2nd","3rd","4th"])
    close_totals = all(abs(_f(a.get(k,0)) - _f(b.get(k,0))) <= tol for k in [
        "Total_kcal_target_kcal","Total_carbs_g","Total_fat_g","Total_protein_g","Total_fiber_g","Total_sodium_mg"
    ])
    return same_names or close_totals

def _goal_kcal(w_kg: float, goal: str) -> float:
    base = 28.0*w_kg
    if "fat" in goal: base -= 250
    if "muscle" in goal: base += 150
    return max(1600.0, min(3600.0, base))

def _jitter(value: float, pct: float, rnd: random.Random) -> float:
    lo = 1.0 - pct
    hi = 1.0 + pct
    return round(value * rnd.uniform(lo, hi), 1)

def _re_totals_with_jitter(obj: Dict[str, Any], persona: Dict[str, Any], rnd: random.Random):
    # Base on goal & weight; add small jitter to guarantee week/persona variety
    w = _f(persona.get("Weight_kg"), 75.0)
    goal = (persona.get("Primary_goal") or "").lower()
    kcal = _goal_kcal(w, goal)
    kcal = _jitter(kcal, 0.06, rnd)  # ±6% per persona-week

    # macro ratios varied by goal + jitter
    if "muscle" in goal:
        p = _jitter(min(max(1.9*w, 110), 190), 0.06, rnd)
        f = _jitter(kcal*0.27/9.0, 0.08, rnd)
    elif "fat" in goal:
        p = _jitter(min(max(1.8*w, 100), 180), 0.06, rnd)
        f = _jitter(kcal*0.30/9.0, 0.08, rnd)
    else:
        p = _jitter(min(max(1.7*w, 95), 175), 0.06, rnd)
        f = _jitter(kcal*0.28/9.0, 0.08, rnd)
    c = max(90.0, (kcal - (p*4 + f*9)) / 4.0)

    # fiber target & sodium target with persona-week jitter
    fiber   = round(rnd.uniform(24, 36), 1)
    sodium  = round(max(1500.0, min(3200.0, 2000.0 + (w-70.0)*8.0 + rnd.uniform(-350, 350))), 0)

    obj["Total_kcal_target_kcal"] = round(kcal, 1)
    obj["Total_carbs_g"]          = round(c, 1)
    obj["Total_fat_g"]            = round(f, 1)
    obj["Total_protein_g"]        = round(p, 1)
    obj["Total_fiber_g"]          = float(fiber)
    obj["Total_sodium_mg"]        = float(sodium)

def make_diet_fingerprint(obj: Dict[str, Any]) -> str:
    # A short signature to detect duplicates within the same week run
    key = (
        f"{obj.get('1st_meal','')}|{obj.get('2nd_meal','')}|"
        f"{obj.get('3rd_meal','')}|{obj.get('4th_meal','')}|"
        f"{round(_f(obj.get('Total_kcal_target_kcal')), -1)}|"
        f"{round(_f(obj.get('Total_sodium_mg')), -1)}"
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def diversify_meals(
    obj: Dict[str, Any],
    pid: str,
    week_id: str,
    persona: Dict[str, Any],
    last_week_obj: Optional[Dict[str, Any]],
    nonce: int = 0,
) -> Dict[str, Any]:
    """
    Force variety per persona/week.
    - Always apply persona-week seeded jitter to totals (so Total_sodium_mg not identical).
    - Re-split macros & sodium across meals.
    - Rotate meal names.
    - If still too similar to last week, push another rotation.
    """
    seed = _sha_seed(f"{pid}|{week_id}|diet|{nonce}")
    rnd  = random.Random(seed)

    # 1) Replace totals with goal/weight-informed values + jitter (guarantee cross-person/week differences)
    _re_totals_with_jitter(obj, persona, rnd)

    # 2) Assign meal names (rotating window)
    offset = rnd.randrange(0, len(SAUDI_MEAL_NAMES) - 4)
    chosen = [SAUDI_MEAL_NAMES[offset + i] for i in range(4)]
    for idx, tag in enumerate(["1st","2nd","3rd","4th"]):
        obj[f"{tag}_meal"] = chosen[idx]

    # 3) Re-split totals across meals with Dirichlet weights
    splits = {
        "kcal_target_kcal": _split(obj["Total_kcal_target_kcal"], rnd),
        "carbs_g":          _split(obj["Total_carbs_g"], rnd),
        "fat_g":            _split(obj["Total_fat_g"], rnd),
        "protein_g":        _split(obj["Total_protein_g"], rnd),
        "fiber_g":          _split(obj["Total_fiber_g"], rnd),
        "sodium_mg":        _split(obj["Total_sodium_mg"], rnd),
    }
    for i, tag in enumerate(["1st","2nd","3rd","4th"]):
        obj[f"{tag}_meal_kcal_target_kcal"] = splits["kcal_target_kcal"][i]
        obj[f"{tag}_meal_carbs_g"]          = splits["carbs_g"][i]
        obj[f"{tag}_meal_fat_g"]            = splits["fat_g"][i]
        obj[f"{tag}_meal_protein_g"]        = splits["protein_g"][i]
        obj[f"{tag}_meal_fiber_g"]          = splits["fiber_g"][i]
        obj[f"{tag}_meal_sodium_mg"]        = splits["sodium_mg"][i]

    # 4) If Ace output had identical meals or is too similar to last week, apply an extra rotation
    if _all_meals_identical(obj) or _similar_overview(obj, last_week_obj):
        return diversify_meals(obj, pid, week_id, persona, last_week_obj, nonce=nonce+1)

    return obj
