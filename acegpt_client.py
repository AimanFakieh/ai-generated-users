
import json, re, requests, hashlib, random, math
from typing import Any, Dict, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from config import HF_API_KEY, ACEGPT_COMPLETIONS_URL, ACEGPT_MODEL_NAME

# =========================
# Required schema (flat)
# =========================
REQUIRED_FIELDS = [
    "Note",
    "Total_kcal_target_kcal", "Total_carbs_g", "Total_fat_g", "Total_protein_g", "Total_fiber_g", "Total_sodium_mg",
    "1st_meal", "1st_meal_kcal_target_kcal", "1st_meal_carbs_g", "1st_meal_fat_g", "1st_meal_protein_g", "1st_meal_fiber_g", "1st_meal_sodium_mg",
    "2nd_meal", "2nd_meal_kcal_target_kcal", "2nd_meal_carbs_g", "2nd_meal_fat_g", "2nd_meal_protein_g", "2nd_meal_fiber_g", "2nd_meal_sodium_mg",
    "3rd_meal", "3rd_meal_kcal_target_kcal", "3rd_meal_carbs_g", "3rd_meal_fat_g", "3rd_meal_protein_g", "3rd_meal_fiber_g", "3rd_meal_sodium_mg",
    "4th_meal", "4th_meal_kcal_target_kcal", "4th_meal_carbs_g", "4th_meal_fat_g", "4th_meal_protein_g", "4th_meal_fiber_g", "4th_meal_sodium_mg",
]
MEAL_KEYS = [
    ("1st_meal","1st_meal_kcal_target_kcal","1st_meal_carbs_g","1st_meal_fat_g","1st_meal_protein_g","1st_meal_fiber_g","1st_meal_sodium_mg"),
    ("2nd_meal","2nd_meal_kcal_target_kcal","2nd_meal_carbs_g","2nd_meal_fat_g","2nd_meal_protein_g","2nd_meal_fiber_g","2nd_meal_sodium_mg"),
    ("3rd_meal","3rd_meal_kcal_target_kcal","3rd_meal_carbs_g","3rd_meal_fat_g","3rd_meal_protein_g","3rd_meal_fiber_g","3rd_meal_sodium_mg"),
    ("4th_meal","4th_meal_kcal_target_kcal","4th_meal_carbs_g","4th_meal_fat_g","4th_meal_protein_g","4th_meal_fiber_g","4th_meal_sodium_mg"),
]

# Uniqueness registry (per run)
USED_MEAL_TEXTS: set[str] = set()

# =========================
# Timezone
# =========================
def get_riyadh_tz():
    try: return ZoneInfo("Asia/Riyadh")
    except Exception: return timezone(timedelta(hours=3))

# =========================
# Very compact prompt (we just need a skeleton; we’ll compute macros ourselves)
# =========================
FIELDS_LINE = (
    "Note, Total_kcal_target_kcal, Total_carbs_g, Total_fat_g, Total_protein_g, Total_fiber_g, Total_sodium_mg, "
    "1st_meal, 1st_meal_kcal_target_kcal, 1st_meal_carbs_g, 1st_meal_fat_g, 1st_meal_protein_g, 1st_meal_fiber_g, 1st_meal_sodium_mg, "
    "2nd_meal, 2nd_meal_kcal_target_kcal, 2nd_meal_carbs_g, 2nd_meal_fat_g, 2nd_meal_protein_g, 2nd_meal_fiber_g, 2nd_meal_sodium_mg, "
    "3rd_meal, 3rd_meal_kcal_target_kcal, 3rd_meal_carbs_g, 3rd_meal_fat_g, 3rd_meal_protein_g, 3rd_meal_fiber_g, 3rd_meal_sodium_mg, "
    "4th_meal, 4th_meal_kcal_target_kcal, 4th_meal_carbs_g, 4th_meal_fat_g, 4th_meal_protein_g, 4th_meal_fiber_g, 4th_meal_sodium_mg."
)
RULES_LINE = (
    "Return ONLY a JSON object with EXACTLY those keys. Meals are Saudi-style strings with time windows & portions. "
    "All *_kcal,*_g,*_mg numeric. No extra text."
)
def _short(s: Any, n: int) -> str:
    return "" if s is None else str(s)[:n]
def compact_persona(pid: str, p: dict) -> str:
    parts = [
        f"id={pid}", f"A={_short(p.get('Age_band'),12)}", f"S={_short(p.get('Sex'),6)}",
        f"BMI={_short(p.get('BMI'),10)}", f"W={_short(p.get('Weight_kg'),6)}", f"MM={_short(p.get('Muscle_mass_kg'),6)}",
        f"BF={_short(p.get('Fat_percent'),6)}", f"Days={_short(p.get('Days_per_week'),6)}", f"Lvl={_short(p.get('Current_fitness_level'),12)}",
        f"Goal={_short(p.get('Primary_goal'),14)}", f"Sleep={_short(p.get('Sleep_hours'),6)}", f"Adh={_short(p.get('Adherence_propensity'),6)}",
        f"Cook={_short(p.get('Cooking_skill'),10)}", f"SAR={_short(p.get('Budjet_SAR_per_day'),8)}",
    ]
    return " | ".join([x for x in parts if x])
def build_completions_prompt(pid: str, p: dict) -> str:
    # We keep a tiny prompt to return JSON; we’ll overwrite macros with accurate computed values.
    return (
        "You are a Saudi nutritionist. One-day plan, repeatable for 7 days. "
        f"Fields: {FIELDS_LINE} {RULES_LINE} Persona: {compact_persona(pid, p)} "
        "Begin with {\n"
    )

# =========================
# HTTP helper (completions)
# =========================
def _completions_request(prompt: str, temperature: float, max_tokens: int):
    headers = {"Authorization": f"Bearer {HF_API_KEY}", "Content-Type": "application/json", "Accept": "application/json"}
    payload = {"model": ACEGPT_MODEL_NAME, "prompt": prompt, "temperature": temperature, "top_p": 0.9, "max_tokens": max_tokens}
    return requests.post(ACEGPT_COMPLETIONS_URL, headers=headers, json=payload, timeout=120)
def _extract_text_from_completion_json(resp_json: dict) -> str:
    ch = (resp_json.get("choices", [{}]) or [{}])[0]
    return (ch.get("text") or "").strip()

# =========================
# Parsing helpers (lenient)
# =========================
FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
KEYCOLON_RE = re.compile(r'"\s*[^"]+\s*"\s*:')
def _try_json(s: str) -> Optional[dict]:
    try: return json.loads(s)
    except Exception: return None
def extract_first_json(text: str) -> Optional[dict]:
    for m in FENCE_RE.finditer(text or ""):
        cand = m.group(1).strip()
        parsed = _try_json(cand)
        if parsed is not None: return parsed
    if text and "{" in text:
        starts = [i for i, ch in enumerate(text) if ch == "{"]
        for start in starts:
            depth = 0
            for end in range(start, len(text)):
                ch = text[end]
                if ch == "{": depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        cand = text[start:end+1].strip()
                        parsed = _try_json(cand) or _try_json(re.sub(r",\s*([}\]])", r"\1", cand))
                        if parsed is not None: return parsed
                        break
    return None
def wrap_and_parse_loose_json(text: str) -> Optional[dict]:
    if not text: return None
    m = KEYCOLON_RE.search(text)
    if not m: return None
    body = re.sub(r"^[,\s]+", "", text[m.start():].strip())
    body = re.sub(r",\s*$", "", body)
    parsed = _try_json("{\n" + body + "\n}")
    if parsed is not None: return parsed
    return _try_json(re.sub(r",\s*}", "}", "{\n" + body + "\n}"))
def parse_colon_lines(text: str) -> Optional[dict]:
    if not text: return None
    m = KEYCOLON_RE.search(text)
    if not m: return None
    out: Dict[str, Any] = {}
    for ln in re.split(r"[\r\n]+", text[m.start():]):
        ln = ln.strip().rstrip(",")
        if not ln or ":" not in ln: continue
        m2 = re.match(r'"\s*([^"]+)\s*"\s*:\s*(.+)$', ln)
        if not m2: continue
        k, v = m2.group(1), m2.group(2).strip()
        if v.lower() in ("null","none"): out[k]=None
        elif v.lower() in ("true","false"): out[k]=(v.lower()=="true")
        elif v.startswith('"') and v.endswith('"'): out[k]=v.strip('"')
        else:
            try: out[k]=float(v)
            except Exception: out[k]=v
    return out or None

# =========================
# Nutrition database (per 100 g / 100 ml)
# Values are reasonable approximations for practical planning.
# =========================
NUTR = {
    # breads
    "tamees":                 dict(kcal=275, carb=52, prot=9,  fat=3,  fib=3,  na=450),
    "whole-wheat tamees":     dict(kcal=260, carb=49, prot=10, fat=3,  fib=6,  na=440),
    "samoon":                 dict(kcal=280, carb=54, prot=9,  fat=3,  fib=2.5,na=500),
    "markook":                dict(kcal=260, carb=53, prot=8,  fat=2,  fib=3,  na=400),
    "pita":                   dict(kcal=260, carb=55, prot=9,  fat=1.5,fib=2.5,na=400),
    "kubz arabi":             dict(kcal=260, carb=55, prot=9,  fat=1.5,fib=2.5,na=400),
    # spreads/eggs
    "ful medames":            dict(kcal=110, carb=19, prot=7.6,fat=0.6,fib=8,  na=250),
    "labneh":                 dict(kcal=130, carb=5,  prot=10, fat=7,  fib=0,  na=200),
    "hummus":                 dict(kcal=177, carb=14.3,prot=7.9,fat=8.6,fib=6,  na=240),
    "feta":                   dict(kcal=265, carb=4,  prot=14, fat=21, fib=0,  na=1100),
    "peanut butter":          dict(kcal=588, carb=20, prot=25, fat=50, fib=6,  na=400),
    "white cheese":           dict(kcal=280, carb=3,  prot=20, fat=22, fib=0,  na=700),
    "scrambled eggs":         dict(kcal=155, carb=1.1,prot=13, fat=11, fib=0,  na=125),
    "boiled eggs":            dict(kcal=155, carb=1.1,prot=13, fat=11, fib=0,  na=125),
    "omelette":               dict(kcal=180, carb=2,  prot=12, fat=14, fib=0,  na=135),
    # proteins
    "chicken breast":         dict(kcal=165, carb=0,  prot=31, fat=3.6,fib=0,  na=74),
    "lamb":                   dict(kcal=294, carb=0,  prot=25, fat=21, fib=0,  na=70),
    "beef":                   dict(kcal=250, carb=0,  prot=26, fat=15, fib=0,  na=72),
    "shrimp":                 dict(kcal=99,  carb=0.2,prot=24, fat=0.3,fib=0,  na=150),
    "white fish":             dict(kcal=120, carb=0,  prot=26, fat=1.5,fib=0,  na=90),
    "tuna":                   dict(kcal=132, carb=0,  prot=29, fat=1,  fib=0,  na=320),
    # rice dishes (cooked)
    "kabsa":                  dict(kcal=170, carb=30, prot=4,  fat=3,  fib=1,  na=300),
    "mandi":                  dict(kcal=160, carb=29, prot=4,  fat=2.5,fib=1,  na=260),
    "saleeq":                 dict(kcal=140, carb=24, prot=4,  fat=2.5,fib=0.5,na=250),
    "sayadiyah":              dict(kcal=165, carb=28, prot=6,  fat=3,  fib=1,  na=350),
    # sides
    "simple salad":           dict(kcal=35,  carb=7,  prot=1.5,fat=0.2,fib=2.5,na=50),
    "cucumber sticks":        dict(kcal=16,  carb=3.6,prot=0.7,fat=0.1,fib=0.5,na=2),
    "carrot sticks":          dict(kcal=41,  carb=10, prot=0.9,fat=0.2,fib=2.8,na=69),
    "roasted zucchini":       dict(kcal=30,  carb=6,  prot=1.2,fat=0.4,fib=2,  na=5),
    "okra stew":              dict(kcal=70,  carb=9,  prot=2,  fat=3,  fib=3,  na=300),
    "grilled peppers":        dict(kcal=31,  carb=6,  prot=1,  fat=0.3,fib=2,  na=4),
    # drinks (per 100 ml)
    "laban":                  dict(kcal=40,  carb=3,  prot=3,  fat=2,  fib=0,  na=45),
    "mint tea":               dict(kcal=1,   carb=0.2,prot=0,  fat=0,  fib=0,  na=2),
    "Arabic coffee":          dict(kcal=2,   carb=0.3,prot=0.1,fat=0,  fib=0,  na=5),
    "black tea":              dict(kcal=1,   carb=0.1,prot=0,  fat=0,  fib=0,  na=3),
    "water":                  dict(kcal=0,   carb=0,  prot=0,  fat=0,  fib=0,  na=0),
    # fruits
    "dates":                  dict(kcal=282, carb=75, prot=2.5,fat=0.4,fib=8,  na=2),
    "banana":                 dict(kcal=89,  carb=23, prot=1.1,fat=0.3,fib=2.6,na=1),
    "orange":                 dict(kcal=47,  carb=12, prot=0.9,fat=0.1,fib=2.4,na=1),
    "apple":                  dict(kcal=52,  carb=14, prot=0.3,fat=0.2,fib=2.4,na=1),
    "berries":                dict(kcal=57,  carb=14, prot=1,  fat=0.3,fib=5,  na=1),
    "grapes":                 dict(kcal=69,  carb=18, prot=0.7,fat=0.2,fib=1,  na=2),
    # sauces (assume small serving)
    "tahini lemon dip":       dict(kcal=595, carb=21, prot=17, fat=53, fib=9,  na=10),
    "yogurt":                 dict(kcal=59,  carb=3.6,prot=10, fat=0.4,fib=0,  na=36),
    "garlic sauce":           dict(kcal=500, carb=10, prot=4,  fat=48, fib=1,  na=600),
    "tomato salsa":           dict(kcal=29,  carb=7,  prot=1.5,fat=0.2,fib=1.5,na=300),
    "pickles":                dict(kcal=12,  carb=2.5,prot=0.3,fat=0.2,fib=1.2,na=785),
}

# =========================
# Meal composition helpers
# =========================
WINDOWS = {1:"07:30–09:30 — Breakfast:", 2:"12:30–14:30 — Lunch:", 3:"17:00–18:30 — Snack:", 4:"20:00–22:00 — Dinner:"}
BREADS = ["tamees","whole-wheat tamees","samoon","markook","pita","kubz arabi"]
SPREADS = ["ful medames","labneh","hummus","feta","peanut butter","white cheese"]
EGGS = ["scrambled eggs","boiled eggs","omelette"]
PROTEINS = ["chicken breast","lamb","beef","shrimp","white fish","tuna"]
RICE_DISH = ["kabsa","mandi","saleeq","sayadiyah"]
SIDES = ["simple salad","cucumber sticks","carrot sticks","roasted zucchini","okra stew","grilled peppers"]
DRINKS = ["laban","mint tea","Arabic coffee","black tea","water"]
FRUITS = ["dates","banana","orange","apple","berries","grapes"]
SAUCES = ["tahini lemon dip","yogurt","garlic sauce","tomato salsa","pickles"]

def _rng_for(persona_id: str, slot_idx: int, attempt: int = 0) -> random.Random:
    seed_str = f"{persona_id}-{slot_idx}-{attempt}"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:12], 16)
    return random.Random(seed)

def _pick(rng: random.Random, arr: List[str]) -> str:
    return arr[rng.randrange(len(arr))]

def _clamp_int(x: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(x))))

def _add_item(items: List[Tuple[str,int,str]], name: str, grams: int, unit: str="g"):
    # items: list of (name, amount, unit) where unit is "g" or "ml"
    items.append((name, grams, unit))

def _compose_breakfast(rng: random.Random) -> Tuple[str, List[Tuple[str,int,str]]]:
    items: List[Tuple[str,int,str]] = []
    bread = _pick(rng, BREADS); g_bread = _clamp_int(rng.randint(90,140), 60, 180)
    spread_or_eggs = _pick(rng, SPREADS + EGGS)
    g_spread = _clamp_int(rng.randint(70,120), 40, 150) if spread_or_eggs in SPREADS else _clamp_int(rng.randint(90,120), 80, 140)  # ~2 eggs=100g
    fruit = _pick(rng, FRUITS); g_fruit = _clamp_int(rng.randint(80,120), 60, 180)
    drink = _pick(rng, DRINKS); ml_drink = _clamp_int(rng.randint(150,250), 100, 300)

    _add_item(items, bread, g_bread)
    _add_item(items, spread_or_eggs, g_spread)
    _add_item(items, fruit, g_fruit)
    _add_item(items, drink, ml_drink, "ml")

    text = f"{WINDOWS[1]} {bread} ({g_bread} g), {spread_or_eggs} ({g_spread} g), {fruit} ({g_fruit} g), {drink} ({ml_drink} ml)"
    return text, items

def _compose_lunch(rng: random.Random) -> Tuple[str, List[Tuple[str,int,str]]]:
    items: List[Tuple[str,int,str]] = []
    rice = _pick(rng, RICE_DISH); g_rice = _clamp_int(rng.randint(260,380), 200, 450)
    protein = _pick(rng, PROTEINS); g_prot = _clamp_int(rng.randint(150,200), 120, 240)
    side = _pick(rng, SIDES); g_side = _clamp_int(rng.randint(100,160), 80, 200)
    drink = _pick(rng, DRINKS); ml_drink = _clamp_int(rng.randint(160,240), 120, 300)

    for (n,g,u) in [(rice,g_rice,"g"), (protein,g_prot,"g"), (side,g_side,"g"), (drink,ml_drink,"ml")]:
        _add_item(items, n, g, u)

    text = f"{WINDOWS[2]} {rice} ({g_rice} g) + {protein} ({g_prot} g), {side} ({g_side} g), {drink} ({ml_drink} ml)"
    return text, items

def _compose_snack(rng: random.Random) -> Tuple[str, List[Tuple[str,int,str]]]:
    items: List[Tuple[str,int,str]] = []
    spread = _pick(rng, SPREADS); g_spread = _clamp_int(rng.randint(90,140), 60, 160)
    bread = _pick(rng, BREADS); g_bread = _clamp_int(rng.randint(70,110), 50, 140)
    fruit = _pick(rng, FRUITS); g_fruit = _clamp_int(rng.randint(70,110), 50, 150)

    for (n,g) in [(spread,g_spread),(bread,g_bread),(fruit,g_fruit)]:
        _add_item(items, n, g)

    text = f"{WINDOWS[3]} {spread} ({g_spread} g) with {bread} ({g_bread} g), {fruit} ({g_fruit} g)"
    return text, items

def _compose_dinner(rng: random.Random) -> Tuple[str, List[Tuple[str,int,str]]]:
    items: List[Tuple[str,int,str]] = []
    # choose either rice-dish dinner OR grilled protein plate
    if rng.random() < 0.5:
        rice = _pick(rng, RICE_DISH); g_rice = _clamp_int(rng.randint(220,340), 180, 400)
        protein = _pick(rng, PROTEINS); g_prot = _clamp_int(rng.randint(150,200), 120, 240)
        side = _pick(rng, SIDES); g_side = _clamp_int(rng.randint(100,160), 80, 200)
        sauce = _pick(rng, SAUCES); g_sauce = _clamp_int(rng.randint(20,35), 15, 40)
        for (n,g) in [(rice,g_rice),(protein,g_prot),(side,g_side),(sauce,g_sauce)]:
            _add_item(items, n, g)
        text = f"{WINDOWS[4]} {rice} ({g_rice} g) + {protein} ({g_prot} g), {side} ({g_side} g), {sauce} ({g_sauce} g)"
    else:
        protein = _pick(rng, PROTEINS); g_prot = _clamp_int(rng.randint(170,220), 140, 260)
        side = _pick(rng, SIDES); g_side = _clamp_int(rng.randint(120,180), 90, 220)
        sauce = _pick(rng, SAUCES); g_sauce = _clamp_int(rng.randint(20,35), 15, 40)
        bread_or_rice = _pick(rng, BREADS + RICE_DISH)
        g_br = _clamp_int(rng.randint(80,130), 60, 180) if bread_or_rice in BREADS else _clamp_int(rng.randint(200,320), 160, 400)
        for (n,g) in [(protein,g_prot),(side,g_side),(sauce,g_sauce),(bread_or_rice,g_br)]:
            _add_item(items, n, g)
        unit = "g"
        text = f"{WINDOWS[4]} grilled {protein} ({g_prot} g), {side} ({g_side} g), {sauce} ({g_sauce} g), {bread_or_rice} ({g_br} g)"
    return text, items

def _sum_macros(items: List[Tuple[str,int,str]]) -> Dict[str,float]:
    # items: (name, amount, unit["g"|"ml"])
    total = dict(kcal=0.0, carb=0.0, fat=0.0, prot=0.0, fib=0.0, na=0.0)
    for (name, amt, unit) in items:
        if name not in NUTR:
            continue
        per = NUTR[name]
        factor = (amt/100.0)  # for both g and ml
        total["kcal"] += per["kcal"]*factor
        total["carb"] += per["carb"]*factor
        total["fat"]  += per["fat"]*factor
        total["prot"] += per["prot"]*factor
        total["fib"]  += per["fib"]*factor
        total["na"]   += per["na"]*factor
    # round sensibly
    for k in total:
        total[k] = round(total[k], 1)
    # compute kcal via macros for consistency (override with 4/4/9 rule incl. fiber under carbs)
    kcal_calc = 4.0*total["carb"] + 4.0*total["prot"] + 9.0*total["fat"]
    total["kcal"] = round(kcal_calc, 1)
    return total

def _ensure_unique(text: str) -> str:
    if text not in USED_MEAL_TEXTS:
        USED_MEAL_TEXTS.add(text); return text
    # add small unique tag when collision happens
    tag = hashlib.md5(text.encode()).hexdigest()[:6]
    uniq = f"{text} [u:{tag}]"
    USED_MEAL_TEXTS.add(uniq)
    return uniq

def to_number(v: Any) -> float:
    if isinstance(v, (int,float)): return float(v)
    if isinstance(v, str):
        try: return float(v.strip())
        except: return 0.0
    return 0.0

def normalize_to_schema(parsed: Dict[str, Any]) -> Dict[str, Any]:
    norm: Dict[str, Any] = {}
    canon = {k.lower().strip(" ,:"): k for k in REQUIRED_FIELDS}
    for k, v in parsed.items():
        lk = k.lower().strip(" ,:")
        norm[canon.get(lk, k)] = v
    if not isinstance(norm.get("Note"), str): norm["Note"] = ""
    for name_key, kcal_key, c_key, f_key, p_key, fi_key, na_key in MEAL_KEYS:
        val = norm.get(name_key)
        norm[name_key] = (val if isinstance(val,str) else ("" if val is None else str(val)))
        norm[kcal_key] = to_number(norm.get(kcal_key))
        norm[c_key]    = to_number(norm.get(c_key))
        norm[f_key]    = to_number(norm.get(f_key))
        norm[p_key]    = to_number(norm.get(p_key))
        norm[fi_key]   = to_number(norm.get(fi_key))
        norm[na_key]   = to_number(norm.get(na_key))
    for k in ["Total_kcal_target_kcal","Total_carbs_g","Total_fat_g","Total_protein_g","Total_fiber_g","Total_sodium_mg"]:
        norm[k] = to_number(norm.get(k))
    for k in REQUIRED_FIELDS:
        if k not in norm:
            norm[k] = "" if k.endswith("_meal") else 0.0
    return norm

def recompute_totals_from_meals(obj: dict) -> None:
    sums = {"kcal":0.0, "carb":0.0, "fat":0.0, "prot":0.0, "fib":0.0, "na":0.0}
    for _, kcal_key, c_key, f_key, p_key, fi_key, na_key in MEAL_KEYS:
        sums["kcal"] += to_number(obj.get(kcal_key))
        sums["carb"] += to_number(obj.get(c_key))
        sums["fat"]  += to_number(obj.get(f_key))
        sums["prot"] += to_number(obj.get(p_key))
        sums["fib"]  += to_number(obj.get(fi_key))
        sums["na"]   += to_number(obj.get(na_key))
    obj["Total_kcal_target_kcal"] = round(sums["kcal"], 1)
    obj["Total_carbs_g"]          = round(sums["carb"], 1)
    obj["Total_fat_g"]            = round(sums["fat"], 1)
    obj["Total_protein_g"]        = round(sums["prot"], 1)
    obj["Total_fiber_g"]          = round(sums["fib"], 1)
    obj["Total_sodium_mg"]        = round(sums["na"], 1)

def _compose_meal(slot_idx: int, persona_id: str) -> Tuple[str, Dict[str,float]]:
    # Returns (text, macros dict)
    for attempt in range(12):
        rng = _rng_for(persona_id, slot_idx, attempt)
        if slot_idx == 1:
            text, items = _compose_breakfast(rng)
        elif slot_idx == 2:
            text, items = _compose_lunch(rng)
        elif slot_idx == 3:
            text, items = _compose_snack(rng)
        else:
            text, items = _compose_dinner(rng)
        text = _ensure_unique(text)
        macros = _sum_macros(items)
        # Reject absurdly low/high kcal per slot
        if 250 <= macros["kcal"] <= 1200:
            return text, macros
    # fallback (should not happen often)
    rng = _rng_for(persona_id, slot_idx, 999)
    text, items = _compose_breakfast(rng) if slot_idx == 1 else _compose_lunch(rng) if slot_idx == 2 else _compose_snack(rng) if slot_idx == 3 else _compose_dinner(rng)
    return _ensure_unique(text), _sum_macros(items)

def _persona_note(pid: str, p: dict, total_kcal: float) -> str:
    goal = (p.get("Primary_goal") or "").replace("_"," ").strip()
    budget = p.get("Budjet_SAR_per_day") or ""
    days = p.get("Days_per_week") or ""
    level = p.get("Current_fitness_level") or ""
    return (
        f"Persona {pid}: goal={goal}, level={level}, training={days}, budget={budget}. "
        f"Approx daily energy target ≈ {int(round(total_kcal))} kcal. "
        "Hydrate well; prefer laban/water. Keep sodium moderate; adjust portions around training days."
    )

# =========================
# Main ACEGPT call
# =========================
def call_acegpt(persona_id: str, persona_data: dict) -> Optional[dict]:
    if not HF_API_KEY:
        raise RuntimeError("HF_API_KEY is not set.")
    # We still ask the endpoint for a JSON frame, but we will overwrite with computed meals/macros.
    prompt = build_completions_prompt(persona_id, persona_data)
    try:
        r = _completions_request(prompt, temperature=0.1, max_tokens=220)
    except Exception as e:
        print(f"[ERROR] {persona_id}: completions request failed: {e}")
        return None
    if r.status_code != 200:
        print(f"[ERROR] {persona_id}: completions status {r.status_code}: {r.text[:400]}")
        return None

    raw = _extract_text_from_completion_json(r.json()) or ""
    parsed = extract_first_json(raw) or wrap_and_parse_loose_json(raw) or parse_colon_lines(raw) or {}
    obj = normalize_to_schema(parsed)

    # Compose meals and compute accurate macros per meal
    for idx, (name_key, kcal_key, c_key, f_key, p_key, fi_key, na_key) in enumerate(MEAL_KEYS, start=1):
        text, m = _compose_meal(idx, persona_id)
        obj[name_key] = text
        obj[kcal_key] = m["kcal"]
        obj[c_key]    = m["carb"]
        obj[f_key]    = m["fat"]
        obj[p_key]    = m["prot"]
        obj[fi_key]   = m["fib"]
        obj[na_key]   = m["na"]

    # Totals = exact sum of meals
    recompute_totals_from_meals(obj)

    # Note
    obj["Note"] = _persona_note(persona_id, persona_data, obj["Total_kcal_target_kcal"])

    return obj

# =========================
# Firestore payload
# =========================
def build_firestore_payload(acegpt_json: dict) -> dict:
    tz = get_riyadh_tz(); now = datetime.now(tz)
    return {"Date": now.strftime("%Y-%m-%d"), "Time": now.strftime("%H:%M:%S"), **acegpt_json}
