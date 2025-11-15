# pip install google-cloud-firestore google-auth
# ^ Tip: these are the two packages you'll need to talk to Firestore from Python.

from google.cloud import firestore            # Import Firestore client (to read/write your database)
from google.oauth2 import service_account     # Import helper to load a service account JSON key
from datetime import datetime                 # (Not used here, but handy if you want to stamp local times)

# --- EDIT THESE TWO LINES TO MATCH YOUR SETUP ---
PROJECT_ID = "fitech-2nd-trail"              # Your Firebase/Google Cloud project ID
SERVICE_ACCOUNT = r"C:\Users\fakias0a\PycharmProjects\seed_personas\fitech-2nd-trail-firebase-adminsdk-yrpaq-40560d84e7.json"
# ^ Absolute path to your downloaded service account JSON (used for admin authentication)
# ------------------------------------------------

WORKOUTS = [                                  # A list of workout program tuples we will seed into Firestore
    # program_id, body_region, location, level, title, exercises
    ("W01","Chest","Gym","Beginner","Chest — Gym — Beginner",[
        "Smith Machine Bench Press","Incline Dumbbell Press","Decline Push-Ups",
        "Chest Fly Machine","Cable Crossover","Chest Dips"
    ]),
    ("W02","Chest","Home","Beginner","Chest — Home — Beginner",[
        "Push-Ups","Incline Push-Ups","Wide-Grip Push-Ups","Wall Push-Ups",
        "Chest Fly with Resistance Bands","Knee Push-Ups"
    ]),
    ("W03","Chest","Gym","Advanced","Chest — Gym — Advanced",[
        "Barbell Bench Press","Incline Barbell Press","Decline Dumbbell Press",
        "Cable Fly","Incline Dumbbell Fly","Bench Press Machine"
    ]),
    ("W04","Chest","Home","Advanced","Chest — Home — Advanced",[
        "Archer Push-Ups","Clap Push-Ups","One-Arm Push-Ups",
        "Resistance Band Push-Ups","Plyometric Push-Ups"
    ]),
    ("W05","Shoulders","Gym","Beginner","Shoulders — Gym — Beginner",[
        "Overhead Dumbbell Press","Front Raise with Dumbbells","Lateral Raises",
        "Face Pulls - Cable Machine","Shrugs with Dumbbells"
    ]),
    ("W06","Shoulders","Home","Beginner","Shoulders — Home — Beginner",[
        "Pike Push-Ups","Lateral Raise with Resistance Bands",
        "Reverse Flys with Resistance Bands","Wall Shrugs"
    ]),
    ("W07","Shoulders","Gym","Advanced","Shoulders — Gym — Advanced",[
        "Seated Overhead Barbell Press","Arnold Press","Cable Lateral Raise",
        "Incline Dumbbell Front Raise","Barbell Shrugs"
    ]),
    ("W08","Shoulders","Home","Advanced","Shoulders — Home — Advanced",[
        "Handstand Push-Ups","One-Arm Pike Push-Ups","Resistance Band Overhead Press",
        "Lateral Raise with Weighted Backpack","Wall Shrugs"
    ]),
    ("W09","Arms","Gym","Beginner","Arms — Gym — Beginner",[
        "Barbell Bicep Curl","Dumbbell Tricep Kickback","Dumbbell Wrist Curls",
        "Tricep Pushdowns - Cable Machine","Hammer Curls - Dumbbells",
        "Overhead Dumbbell Tricep Extension"
    ]),
    ("W10","Arms","Home","Beginner","Arms — Home — Beginner",[
        "Chair Dips","Resistance Band Curls","Push-Up to Plank Shoulder Taps",
        "Resistance Band Hammer Curls"
    ]),
    ("W11","Arms","Gym","Advanced","Arms — Gym — Advanced",[
        "Preacher Curl - Barbell","Skull Crushers - EZ Bar","Reverse Barbell Curl",
        "Cable Overhead Triceps Extension","Dumbbell Curl","Dumbbell Zottman Curl"
    ]),
    ("W12","Arms","Home","Advanced","Arms — Home — Advanced",[
        "Diamond Push-Ups","One-Arm Resistance Band Curls","Weighted Backpack Tricep Kickbacks",
        "Slow Negative Push-Ups","Band Overhead Tricep Extensions"
    ]),
    ("W13","Back","Gym","Beginner","Back — Gym — Beginner",[
        "Lat Pulldown","Seated Cable Row","Hyperextensions - Extension Machine",
        "Dumbbell Shrugs","Barbell Row","Face Pull - Cable Machine"
    ]),
    ("W14","Back","Home","Beginner","Back — Home — Beginner",[
        "Superman Hold","Resistance Band Rows","Back Extensions on Floor",
        "Reverse Snow Angels","Wall Shrugs"
    ]),
    ("W15","Back","Gym","Advanced","Back — Gym — Advanced",[
        "Pull-Ups","Deadlift","Barbell Bent-Over Row","Single-Arm Dumbbell Row",
        "Wide-Grip Pulldown","Cable Reverse Fly"
    ]),
    ("W16","Back","Home","Advanced","Back — Home — Advanced",[
        "Archer Push-Ups","Resistance Band Rows","Weighted Backpack Shrugs",
        "Superman with Resistance Band","Plank with Shoulder Taps"
    ]),
    ("W17","Core & Abs","Home","Beginner","Core & Abs — Home — Beginner",[
        "Leg Raises","Bicycle Crunches","Side Plank Hold","Reverse Crunches",
        "Flutter Kicks","Elbow-to-Knee Sit-Ups","Toe Touches"
    ]),
    ("W18","Core & Abs","Gym","Advanced","Core & Abs — Gym — Advanced",[
        "Weighted Plank","Hanging Leg Raises","Ab Wheel Rollout","Cable Side Crunch",
        "Decline Bench Sit-Ups","Ball Twists","Hollow Body Hold","Lunges - Dumbbells"
    ]),
    ("W19","Legs","Gym","Beginner","Legs — Gym — Beginner",[
        "Leg Press","Bodyweight Squats","Hamstring Curls - Machine",
        "Calf Raises","Glute Bridges"
    ]),
    ("W20","Legs","Home","Beginner","Legs — Home — Beginner",[
        "Wall Sit","Step-Ups","Sumo Squats","Glute Kickbacks",
        "Single-Leg Deadlift - No Weights","Calf Raises on Stairs","Side Lunges"
    ]),
    ("W21","Legs","Gym","Advanced","Legs — Gym — Advanced",[
        "Barbell Squats","Romanian Deadlifts","Walking Lunges - Barbell",
        "Leg Extensions - Machine","Bulgarian Split Squats","Standing Calf Raise Machine",
        "Good Mornings"
    ]),
    ("W22","Legs","Home","Advanced","Legs — Home — Advanced",[
        "Jump Squats","Single Leg Glute Bridge","Reverse Lunges",
        "Lateral Step-Ups - Higher Platform","Isometric Wall Squat with Weight",
        "Broad Jumps"
    ]),
    ("W23","Upper Body","Gym","Beginner","Upper Body — Gym — Beginner",[
        "Chest Press Machine","Dumbbell Chest Press","Biceps Curls","Dumbbell Shoulder Press",
        "Triceps Dips","Wrist Curls","Front Raises","Lat Pulldown - Machine","Dumbbell Rows"
    ]),
    ("W24","Upper Body","Home","Beginner","Upper Body — Home — Beginner",[
        "Push-Ups","Incline Push-Ups","Biceps Curles with Resistance Band","Pike Push-Ups",
        "Chair Dips","Wrist Curls with Resistance Band","Wall Push-Ups"
    ]),
    ("W25","Upper Body","Gym","Advanced","Upper Body — Gym — Advanced",[
        "Barbell Bench Press","Pull-Ups","Barbell Curl","Arnold Press","Triceps Skull Crushers",
        "Wrist Curls","Cable Face Pulls","Dumbbell Shrugs","Bar Row"
    ]),
    ("W26","Upper Body","Home","Advanced","Upper Body — Home — Advanced",[
        "Decline Push-ups","Diamond Push-Ups","Resistance Band Chest Fly","Handstand Push-Ups",
        "Triceps Dips - On Bench","Resistance Band Shoulder Press","Resistance Band Lateral Raise"
    ]),
    ("W27","Push","Gym","Beginner","Push — Gym — Beginner",[
        "Chest Press Machine","Dumbbell Chest Press","Machine Shoulder Press",
        "Triceps Pushdown","Chest Fly Machine","Dumbbell Front Raise","Dips - Machine"
    ]),
    ("W28","Push","Home","Beginner","Push — Home — Beginner",[
        "Push-Ups","Incline Push-Ups","Pike Push-Ups","Chair Dips","Decline Push-Ups",
        "Triceps Push-Ups","Diamond Push-Ups"
    ]),
    ("W29","Push","Gym","Advanced","Push — Gym — Advanced",[
        "Barbell Bench Press","Overhead Barbell Press","Dumbbell Chest Fly",
        "Triceps Skull Crushers","Dumbbell Arnold Press","Cable Chest Fly","Dips - Bodyweight"
    ]),
    ("W30","Push","Home","Advanced","Push — Home — Advanced",[
        "Handstand Push-Ups","Decline Push-ups with Clap","Resistance Band Chest Press",
        "Triceps Dips on Bench","Decline Push-Ups","Resistance Band Shoulder Press",
        "Resistance Band Lateral Raise"
    ]),
    ("W31","Pull","Gym","Beginner","Pull — Gym — Beginner",[
        "Lat Pulldown - Cable","Seated Row - Cable","Machine Rear Delt Fly",
        "Biceps Curl - Barbell","Hammer Curl - Dumbbells","Face Pull - Cable","Bar Row"
    ]),
    ("W32","Pull","Home","Beginner","Pull — Home — Beginner",[
        "Bodyweight Rows","Superman","Inverted Rows","Bicep Curls with Resistance Band",
        "Resistance Band Lat Pulldown","Reverse Snow Angels","Renegade Rows"
    ]),
    ("W33","Pull","Gym","Advanced","Pull — Gym — Advanced",[
        "Pull-ups - Bodyweight","Deadlift","Barbell Bent-Over Row","Lat Pulldown - Wide Grip",
        "Single-Arm Dumbbell Row","Barbell Shrugs","Cable Face Pull"
    ]),
    ("W34","Pull","Home","Advanced","Pull — Home — Advanced",[
        "Pull-ups - Bodyweight","Resistance Band Pull-Aparts","Single-Leg Deadlift - Dumbbell",
        "Resistance Band Single-Arm Row","Chin-Ups - Bodyweight","Deadlift - Resistance Band",
        "Band-Assisted Pull-Ups"
    ]),
]

def main():
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT)
    # ^ Load your service account JSON into a Credentials object (admin access to Firestore)

    db = firestore.Client(project=PROJECT_ID, credentials=creds)
    # ^ Create a Firestore client bound to your project, authenticated with the service account

    batch = db.batch()
    # ^ Start a batch write so we can commit all documents in a single network call (faster, atomic per doc)

    now = firestore.SERVER_TIMESTAMP
    # ^ Firestore sentinel value: server will fill this with its own timestamp when the write happens

    for prog in WORKOUTS:                      # Iterate all workout program tuples
        pid, region, loc, level, title, exs = prog
        # ^ Unpack tuple: program id, body region, location, difficulty, display title, and exercises list

        doc_ref = db.collection("workouts").document(pid)
        # ^ Reference to /workouts/{program_id}; this is where we will store each program

        data = {                               # Build the document payload for this program
            "program_id": pid,                 # Program stable ID (e.g., "W01")
            "title": title,                    # Human-readable name
            "body_region": region,             # Body region (Chest, Back, Legs, etc.)
            "location": loc,                   # "Gym" or "Home"
            "level": level,                    # "Beginner" or "Advanced"
            "exercises": exs,                  # List of exercise names (strings)
            "version": "v1",                   # Schema/version tag so you can evolve later
            "created_at": now,                 # Server-side timestamp when created
            "updated_at": now                  # Server-side timestamp when last updated
        }
        batch.set(doc_ref, data, merge=False)  # Queue a "set" write in the batch (replace if exists)

    batch.commit()                              # Execute the batch (actually writes all docs to Firestore)
    print(f"Seeded {len(WORKOUTS)} workout programs into /workouts")
    # ^ Log how many programs were written so you can verify success

if __name__ == "__main__":                      # Standard Python entry-point guard
    main()                                      # Run main() only when this file is executed directly
