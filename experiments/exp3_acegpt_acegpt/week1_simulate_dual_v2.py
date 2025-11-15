# --- Acegpt_Acegpt/week1_simulate_dual_v2.py ---
from typing import Dict, Any
from config_dual import START_WEEK_ID
from firestore_io_dual import (
    list_persona_ids,
    read_persona,
    read_legacy_week46_diet,
    write_logs,
    write_updated_persona,
)
from acegpt_client_dual import simulate_week_with_ace
from utils_sim_dual import build_week1_payloads

def _build_sim_prompt(pid: str, persona: Dict[str, Any], diet: Dict[str, Any]) -> str:
    # minimal but informative; you can expand if you want more realism
    return f"""You are Persona {pid}. Follow this ONE-WEEK plan (repeat daily):

Persona:
- Age_band: {persona.get('Age_band')}
- Sex: {persona.get('Sex')}
- BMI: {persona.get('BMI')}
- Days_per_week: {persona.get('Days_per_week')}
- Current_fitness_level: {persona.get('Current_fitness_level')}
- Primary_goal: {persona.get('Primary_goal')}
- Adherence_propensity: {persona.get('Adherence_propensity')}
- Sleep_hours: {persona.get('Sleep_hours')}
- Biggest_barrier: {persona.get('Biggest_barrier')}

Diet (per day):
- Total_kcal_target_kcal: {diet.get('Total_kcal_target_kcal')}
- Total_protein_g: {diet.get('Total_protein_g')}
- Total_carbs_g: {diet.get('Total_carbs_g')}
- Total_fat_g: {diet.get('Total_fat_g')}
- Total_fiber_g: {diet.get('Total_fiber_g')}
- Total_sodium_mg: {diet.get('Total_sodium_mg')}

Give a short reflection on how the week went in first person, then stop.
"""

def run_week1():
    week_id = START_WEEK_ID  # Week_2025_46
    personas = list_persona_ids()
    print("[INFO] Personas found:", personas)

    for pid in personas:
        print(f"\n[INFO] Week {week_id} -> persona {pid}")

        persona = read_persona(pid)
        diet    = read_legacy_week46_diet(pid)  # existing diet from Experiment_ACEGPT

        # 1) Ask AceGPT for a small reflection paragraph (text)
        prompt = _build_sim_prompt(pid, persona, diet)
        sim_text = simulate_week_with_ace(prompt, pre_metrics={
            "Weight_kg": persona.get("Weight_kg"),
            "Muscle_mass_kg": persona.get("Muscle_mass_kg"),
            "Fat_percent": persona.get("Fat_percent"),
        }, retries=3)

        # 2) Convert to structured logs + build updated_persona
        logs_payload, updated_payload = build_week1_payloads(
            pid=pid, week_id=week_id, persona=persona, diet=diet, sim_text=sim_text
        )

        # 3) Write Firestore docs
        write_logs(pid, week_id, logs_payload)
        print(f"[OK] logs saved @ {week_id} for {pid}")

        write_updated_persona(pid, week_id, updated_payload)
        print(f"[OK] updated_persona saved @ {week_id} for {pid}")

if __name__ == "__main__":
    run_week1()
