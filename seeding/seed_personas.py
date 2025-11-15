# Import the Firestore client to read/write documents in Google Cloud Firestore
from google.cloud import firestore
# Import helper to load Google service account credentials from a JSON key file
from google.oauth2 import service_account
# Import the standard library's JSON module for reading the personas file
import json

# ---- Configuration constants (edit to your project/paths) ----

# Your Google Cloud / Firebase project ID (must match the project of your Firestore)
PROJECT_ID = "fitech-2nd-trail"
# Absolute path to the local JSON file that contains your 24 persona rows
PERSONAS_JSON = r"C:\Users\fakias0a\PycharmProjects\seed_personas\personas_v3_with_prefs_20251029.json"
# Absolute path to the service account key JSON for authenticated Firestore access
SERVICE_ACCOUNT = r"C:\Users\fakias0a\PycharmProjects\seed_personas\fitech-2nd-trail-firebase-adminsdk-yrpaq-40560d84e7.json"

# Define the main entry function that seeds personas into Firestore
def main():
    # Create credential object from the service account JSON so the client can authenticate
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT)
    # Create a Firestore client bound to your project and using those credentials
    db = firestore.Client(project=PROJECT_ID, credentials=creds)

    # Open the personas JSON file for reading with UTF-8 encoding
    with open(PERSONAS_JSON, "r", encoding="utf-8") as f:
        # Load the entire JSON array (list of persona dicts) into memory as Python objects
        rows = json.load(f)

    # Start a Firestore batch so multiple writes can be committed atomically
    batch = db.batch()
    # Iterate over each persona row (each row should be a dict with keys like "ID", etc.)
    for row in rows:
        # Extract the persona ID (e.g., "P01" .. "P24") which will be the Firestore doc ID
        pid = row["ID"]                 # "P01".."P24"
        # Add/overwrite a schema version marker so you can track this persona format in Firestore
        row["schema_version"] = "v3"
        # Add a frozen timestamp/string to record when this snapshot was seeded
        row["frozen_at"] = "2025-10-29"
        # Queue a write in the batch: set the document at personas/{pid} to exactly this row
        # merge=False ensures the document is replaced by 'row' (not merged with existing fields)
        batch.set(db.collection("personas").document(pid), row, merge=False)
    # Execute all queued writes in a single network commit
    batch.commit()
    # Print a simple success message with the number of personas seeded
    print("Seeded", len(rows), "personas")

# Standard Python pattern: run main() only if this file is executed directly
if __name__ == "__main__":
    main()
