from google.colab import auth
from googleapiclient.discovery import build
import json
import re
import os
from google.colab import drive

# 1. Mount and Auth
drive.mount('/content/drive', force_remount=True)
auth.authenticate_user()
drive_service = build('drive', 'v3')

print(" Searching Google Drive for all Audio_Rec_*.mp3 files...")

# Search Google Drive for any files starting with Audio_Rec_
# We use pageSize=1000 to ensure we catch all of them
query = "name contains 'Audio_Rec_' and name contains '.mp3' and trashed=false"

# Handle pagination just in case you have more than 1000 files
all_files = []
page_token = None

while True:
    results = drive_service.files().list(
        q=query, 
        fields="nextPageToken, files(id, name, webViewLink)", 
        spaces='drive',
        pageSize=1000,
        pageToken=page_token
    ).execute()
    
    all_files.extend(results.get('files', []))
    page_token = results.get('nextPageToken')
    if not page_token:
        break

print(f"📦 Found {len(all_files)} audio files total!")

repaired_jobs = []

for f in all_files:
    name = f.get('name')
    link = f.get('webViewLink')
    
    # Extract the Row ID using regex (e.g., getting 2922 from Audio_Rec_2922.mp3)
    match = re.search(r'Audio_Rec_(\d+)\.mp3', name)
    if match:
        row_id = int(match.group(1))
        
        # We also want to re-apply the "Anyone with link can view" permission just in case
        try:
            drive_service.permissions().create(fileId=f['id'], body={'type': 'anyone', 'role': 'reader'}).execute()
        except:
             pass # Ignore if permission already exists
             
        # Add it to the Orchestrator's format
        repaired_jobs.append({
            "row_id": row_id,
            "status": "success",
            "audio_drive_link": link
        })

# Save the master payload to the automation folder
RESULT_FILE = "/content/drive/MyDrive/Audio_automation/completed_jobs.json"

with open(RESULT_FILE, 'w') as f:
    json.dump(repaired_jobs, f, indent=4)

print(f"✅ Successfully wrote {len(repaired_jobs)} exact links to completed_jobs.json!")
print("Drop back to your local PC and run `master_orchestrator.py`! The bot will instantly detect the file on startup and patch everything!")
