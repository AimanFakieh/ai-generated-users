# AI generated users

This pipeline generates simulated **AI users** (LLM agents) who follow **weekly diet + workout plans** for a full year (**54 weeks**). Each “user” is defined by a rich **persona** (age band, budget, fitness level, adherence, etc.). A **Nutritionist LLM** designs the diet; a **User LLM** follows the plan, produces weekly **progress logs**, and updates the persona. All data is persisted in **Google Firestore**.

We ran three experiments:

1. **Experiment 1** — *User LLM:* Claude Sonnet · *Nutritionist:* OpenAI · *Workout plan:* from phone → Firestore  
2. **Experiment 2** — *User LLM:* Claude Sonnet · *Nutritionist:* **ACEgpt** (via Hugging Face) · *Workout plan:* from phone → Firestore  
3. **Experiment 3** — *User LLM:* **ACEgpt (via Hugging Face)** · *Nutritionist:* **ACEgpt (via Hugging Face)** · *Workout plan:* from phone → Firestore  

> **Note:** **ACEgpt is an Arabic LLM**, which we use partially in the **2nd experiment (as a nutritionist only)** and fully in the **3rd experiment (as both a nutritionist and the AI user)**.

---

## Every week the pipeline

1) **Generate a new diet plan by the Nutritionist LLM**  
   The Nutritionist LLM outputs **meals (names + details), total kcal (and per‑meal when available), macros (and per‑meal when available), and notes/comments**.  
   The plan is conditioned on **persona information** (e.g., age band, BMI, weight/muscle/fat, primary goal, fitness level, weekly training frequency, budget, cooking skill, allergies/dislikes, fasting windows, sodium/fiber/protein targets, language/dialect, motivation/coach tone) **and the workout plan** stored for that persona.

2) **Simulate adherence & outcomes by the User LLM**  
   The User LLM tries to follow the diet and workout plan and emits a **weekly log**:  
   - **Pre/Post:** `weight_kg`, `muscle_kg`, `fat_%`  
   - **Behavioral:** `daily_avg_kcal`, `sleep_avg_hours`  
   - **Free‑text feedback:** barriers/cravings/schedule issues—used to inform the next plan

3) **Update the persona for next week’s planning**  
   Persona fields are **refreshed** from outcomes and behavior so the next week’s plan can adapt. Typical updates include:  
   - **Body composition:** `Weight_kg`, `Muscle_mass_kg`, `Fat_percent`  
   - **Training & recovery:** realized days/week and `Sleep_hours` summaries  
   - **Adherence signal:** adjust **`Adherence_propensity`** based on how closely the user followed the plan  
   - **Notes:** carry forward **user reflections** to shape next‑week plans

**All updates are written each week to Firestore under:**
```
/experiments/<EXPERIMENT_NAME>/users/<PXX>/weeks/<Week_YYYY_WW>/
  ├─ diet/plan
  ├─ logs/plan
  └─ updated_persona/plan
```

---

## Folder structure (grouped by experiment)

```
.
├─ data/
│  └─ personas_v3_with_prefs_20251029.xlsx
│
├─ seeding/
│  ├─ seed_personas.py              # Push personas from Excel → Firestore
│  └─ seed_workouts.py              # Push workout templates → Firestore
│
├─ experiments/
│  ├─ exp1_openai_claude/
│  │  ├─ Experiment_OpenAI_Diet_Pipeline.py                 # Week 1: Nutritionist=OpenAI → diet/plan
│  │  ├─ Experiment_Week1_Claude_Logs_UpdatePersona_v4.py   # Week 1: User=Claude → logs/plan + updated_persona/plan
│  │  └─ Experiment_Yearly_Loop_OpenAI_Claude_v3.py         # Year‑long loop (weeks 1..54)
│  │
│  ├─ exp2_acegpt_claude/
│  │  ├─ experiment_acegpt.py                                # Week 1: Nutritionist=ACEgpt → diet/plan
│  │  ├─ acegpt_client.py                                    # ACEgpt client (HF) for week‑1
│  │  ├─ seed_week_updated_persona_v9.py                     # Week 1: User=Claude → logs/plan + updated_persona/plan
│  │  ├─ claude_client_seed_v9.py
│  │  ├─ firestore_io_seed_v9.py
│  │  ├─ config_seed_v9.py
│  │  ├─ config.py                                           # Experiment 2 config (HF / endpoints / switches)
│  │  ├─ year_orchestrator_v12.py                            # Year‑long loop (weeks 1..54)
│  │  ├─ firestore_io_year_v11.py
│  │  ├─ claude_client_v12.py
│  │  ├─ acegpt_client_v12.py
│  │  ├─ utils_json_v12.py
│  │  └─ config_year_v12.py
│  │
│  ├─ exp3_acegpt_acegpt/
│  │  ├─ year_orchestrator_dual_v2.py                        # Year‑long loop (ACEgpt as user + nutritionist)
│  │  ├─ week1_simulate_dual_v2.py                           # (Optional) week‑1 run (gives better results)
│  │  ├─ acegpt_client_dual_v2.py                            # ACEgpt client for dual‑role simulation
│  │  ├─ firestore_io_dual_v2.py
│  │  ├─ utils_sim_dual.py
│  │  ├─ utils_time_dual.py
│  │  └─ config_dual.py
│
├─ extractors/
│  ├─ extract_diet.py
│  ├─ extract_log.py
│  ├─ extract_updated_persona.py
│  ├─ extract_diet_ACEgpt_Claude.py
│  ├─ extract_log_ACEgpt_Claude.py
│  ├─ extract_updated_persona_ACEgpt_Claude.py
│  ├─ extract_diet_ACEgpt_ACEgpt.py
│  ├─ extract_log_ACEgpt_ACEgpt.py
│  └─ extract_updated_persona_ACEgpt_ACEgpt.py
│
├─ results/
│  ├─ diet_results.csv
│  ├─ logs_results.csv
│  ├─ updated_persona_results.csv
│  ├─ diet_ACEgpt_Claude_results.csv
│  ├─ logs_ACEgpt_Claude_results.csv
│  ├─ updated_persona_ACEgpt_Claude_results.csv
│  ├─ diet_ACEgpt_ACEgpt_results.csv
│  ├─ logs_ACEgpt_ACEgpt_results.csv
│  └─ updated_persona_ACEgpt_ACEgpt_results.csv
│
├─ figures/
│  ├─ Gaining_muscles.png
│  ├─ Losing_fat.png
│  └─ Losing_fat_&_gaining_muscles_in_the_same_time.png
│
├─ User_feedback_sample/
│  ├─ 1st_experiment_userP01_Week2025W47.png
│  └─ 3rd_experiment_userP07_Week2026W02.png
│
├─ config/
│  ├─ requirements.txt
│  └─ environment.yml
│
├─ service_accounts/                 # use your own service account
│
├─ .gitignore
└─ README.md
```

**About the PNG examples in `User_feedback_sample/`:**  
These are snapshots of the **AI user’s weekly feedback** after following its diet + workout plan:
- `1st_experiment_userP01_Week2025W47.png`  
- `3rd_experiment_userP07_Week2026W02.png`  

**Additional figure notes:**  
- `figures/Gaining_muscles.png`: *This .png file shows a plot of muscle mass progress in (kg) for 4 different personas in the different 3 experiments we applied for one full year simulation. These personas target is gaining muscles.*  
- `figures/Losing_fat.png`: *This .png file shows a plot of fat percentage progress for 4 different personas in the different 3 experiments we applied for one full year simulation. These personas target is losing fat.*  
- `figures/Losing_fat_&_gaining_muscles_in_the_same_time.png`: *This .png file shows a plot of muscle mass progress in (kg) and fat percentage progress for 2 different personas in the different 3 experiments we applied for one full year simulation. These personas target is gaining muscles and losing fat in the same time.*

---

## Data schema we store

### Diet (from Nutritionist LLM)
- Meal names & details (1st–4th meal)
- Total kcal (+ per‑meal kcal when available)
- Macros totals (+ per‑meal when available)
- Nutritionist notes/comments

### Weekly progress (from User LLM)
- Pre/Post: **weight (kg)**, **muscle (kg)**, **fat %**
- **Daily average kcal**, **sleep avg (h)**
- **Free‑text feedback** for next week

### Persona (seeded + updated)
- `Adherence_propensity` `[0..1]`
- Age band, Gender, BMI
- Budget (SAR/day), Cooking skill
- Fitness level, Days/week
- Muscle mass, Weight, Fat %
- Sleep hours, Primary goal
- Additional behavioral/preferences fields from the Excel sheet

---

## Requirements

Use **Conda** *or* **Python venv**.

### Conda
```bash
conda env create -f config/environment.yml
conda activate fitech-aiusers
# optional:
conda install ipykernel
python -m ipykernel install --user --name fitech-aiusers
```

### Python venv (Windows PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate
pip install --upgrade pip
pip install -r config/requirements.txt
```

### Credentials & inputs

- **Firestore project**: `Use_Your_Own_Firestore_Project_ID`
- **Service account JSON (local only; don’t commit):**
  ```powershell
  $env:GOOGLE_APPLICATION_CREDENTIALS = "C:\path\to\service_accounts\your-service-account.json"
  ```
- **API keys** (set as env vars as required by your experiment scripts):
  - `OPENAI_API_KEY` (OpenAI)
  - `ANTHROPIC_API_KEY` (Claude Sonnet)
  - `HF_API_TOKEN` and/or `ACEGPT_ENDPOINT_URL` (ACEgpt via Hugging Face)
- **Personas Excel**: `data/personas_v3_with_prefs_20251029.xlsx`

---

## How to run

### 0) Seed personas & workouts
```powershell
# Personas → Firestore
python seeding/seed_personas.py --project Use_Your_Own_Firestore_Project_ID --excel data/personas_v3_with_prefs_20251029.xlsx

# Workout templates → Firestore
python seeding/seed_workouts.py --project Use_Your_Own_Firestore_Project_ID
```

### 1) Experiment 1 — OpenAI (Nutritionist) + Claude (User)

**Week 1**
```powershell
# Create Week‑1 diets from OpenAI
python experiments/exp1_openai_claude/Experiment_OpenAI_Diet_Pipeline.py

# Simulate Week‑1 user behavior and update persona
python experiments/exp1_openai_claude/Experiment_Week1_Claude_Logs_UpdatePersona_v4.py
```

**Year‑long loop (weeks 1..54)**
```powershell
python experiments/exp1_openai_claude/Experiment_Yearly_Loop_OpenAI_Claude_v3.py
```

---

### 2) Experiment 2 — ACEgpt (Nutritionist via HF) + Claude (User)

**Week 1**
```powershell
# Diets from ACEgpt (Nutritionist)
python experiments/exp2_acegpt_claude/experiment_acegpt.py   # uses exp2_acegpt_claude/acegpt_client.py (HF) + config.py

# Simulate user + update persona
python experiments/exp2_acegpt_claude/seed_week_updated_persona_v9.py   # uses claude_client_seed_v9.py + firestore_io_seed_v9.py
```

**Year‑long loop (weeks 1..54)**
```powershell
python experiments/exp2_acegpt_claude/year_orchestrator_v12.py   # uses claude_client_v12.py + acegpt_client_v12.py + firestore_io_year_v11.py
```

---

### 3) Experiment 3 — ACEgpt (Nutritionist) + ACEgpt (User)

Reuses Week‑1 diets produced in **Experiment 2** (already in Firestore).

**Year‑long loop (weeks 1..54)**
```powershell
python experiments/exp3_acegpt_acegpt/year_orchestrator_dual_v2.py  # ACEgpt as both user + nutritionist
```

**(Optional) Week‑1 only — gives better results**
```powershell
python experiments/exp3_acegpt_acegpt/week1_simulate_dual_v2.py
```

---

## Extract outputs (CSVs)

```powershell
# Experiment 1
python extractors/extract_diet.py
python extractors/extract_log.py
python extractors/extract_updated_persona.py

# Experiment 2
python extractors/extract_diet_ACEgpt_Claude.py
python extractors/extract_log_ACEgpt_Claude.py
python extractors/extract_updated_persona_ACEgpt_Claude.py

# Experiment 3
python extractors/extract_diet_ACEgpt_ACEgpt.py
python extractors/extract_log_ACEgpt_ACEgpt.py
python extractors/extract_updated_persona_ACEgpt_ACEgpt.py
```

Outputs appear in `results/` and include:
1) **Diet**: meal names/details, total kcal, nutritionist notes  
2) **Progress**: pre/post weight, muscle, fat %, daily avg kcal, sleep hours, user notes  
3) **Updated persona**: adherence, age band, gender, BMI, budget, cooking skill, fitness level, days/week, muscle/weight/fat, sleep hours, primary goal, etc.

---

## What’s already plotted

- `figures/Gaining_muscles.png`
- `figures/Losing_fat.png`
- `figures/Losing_fat_&_gaining_muscles_in_the_same_time.png`

**Note:** The **full results for all personas** are available in the CSV files under `results/`.
