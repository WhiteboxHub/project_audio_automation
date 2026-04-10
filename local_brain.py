import os
import time
import json
import requests
import re
from datetime import datetime
from dotenv import load_dotenv

# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

# Configuration for Google Drive path
# If using Google Drive Desktop, adjust this path to your local Drive folder.
# Example Windows: "G:\\My Drive\\Automation"
# Example Mac: "/Users/username/Google Drive/My Drive/Automation"
DRIVE_AUTOMATION_FOLDER = os.getenv("DRIVE_AUTOMATION_FOLDER", r"G:\My Drive\Automation")

JOB_FILE_PATH = os.path.join(DRIVE_AUTOMATION_FOLDER, "pending_jobs.json")
RESULT_FILE_PATH = os.path.join(DRIVE_AUTOMATION_FOLDER, "completed_jobs.json")


def login():
    """Authenticate with the WBL API and return a session/token."""
    # Assuming the login endpoint is '/login' (adjust if it's '/auth/login' or similar)
    login_url = f"{WBL_API_BASE_URL}/login"
    
    # FastAPI OAuth2 token endpoints typically expect form data with 'username' and 'password'
    payload = {
        "username": WBL_EMAIL,
        "password": WBL_PASSWORD
    }
    
    print(f"Authenticating with Admin Portal: {login_url}")
    
    try:
        response = requests.post(login_url, data=payload)
        response.raise_for_status()
        
        # Typical JWT token response
        data = response.json()
        token = data.get("access_token") or data.get("token")
        print("Authentication successful.")
        return token
    except Exception as e:
        print(f"Failed to authenticate: {e}")
        return None


def extract_google_drive_id(url):
    """Extracts the file ID from a Google Drive URL."""
    if not url: return None
    
    # Match /d/ID/view format
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    
    # Match ?id=ID format
    match = re.search(r"id=([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
        
    return None


def fetch_pending_interviews(token):
    """Fetch interviews and filter for date >= '2026-03-30' and empty audio_link."""
    headers = {}
    if token:
         headers["Authorization"] = f"Bearer {token}"
         
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    print(f"Fetching interviews from {interviews_url}...")
    
    try:
        response = requests.get(interviews_url, headers=headers)
        response.raise_for_status()
        interviews = response.json()
        
        # In case the API returns wrapped data
        if isinstance(interviews, dict) and "data" in interviews:
            interviews = interviews["data"]

        pending_jobs = []
        
        for interview in interviews:
            i_date_str = interview.get("interview_date", "")
            audio_link = interview.get("audio_link", "")
            recording_link = interview.get("recording_link", "")
            row_id = interview.get("id")
            
            if not i_date_str:
                continue
                
            try:
                # Handle dates like '2026-03-30T14:30:00Z'
                date_part = i_date_str.split('T')[0]
                i_date = datetime.fromisoformat(date_part)
                cutoff_date = datetime(2026, 3, 30)
                
                if i_date >= cutoff_date and not audio_link and recording_link:
                    video_id = extract_google_drive_id(recording_link)
                    
                    if video_id:
                        pending_jobs.append({
                            "row_id": row_id,
                            "video_file_id": video_id
                        })
            except Exception as e:
                print(f"Error parsing date for interview {row_id}: {e}")
                
        return pending_jobs
        
    except Exception as e:
        print(f"Failed to fetch interviews: {e}")
        return []


def submit_completed_jobs(token, completed_jobs):
    """Update interviews in the backend using PUT /interviews/{id}."""
    headers = {}
    if token:
         headers["Authorization"] = f"Bearer {token}"
         
    for job in completed_jobs:
        row_id = job.get("row_id")
        status = job.get("status")
        audio_drive_link = job.get("audio_drive_link")
        
        if status == "success" and audio_drive_link:
            print(f"Updating row {row_id} with new audio link...")
            update_url = f"{WBL_API_BASE_URL}/interviews/{row_id}"
            
            updates = {
                "audio_link": audio_drive_link 
            }
            
            try:
                response = requests.put(update_url, json=updates, headers=headers)
                response.raise_for_status()
                print(f"Successfully updated row {row_id}")
            except Exception as e:
                print(f"Failed to update row {row_id}: {e}")


def main():
    print("=== Local Brain Script Started ===")
    
    # 1. Authenticate with your existing API
    token = login()
    
    # 2. Sync: Check for completed jobs first before fetching new ones
    if os.path.exists(RESULT_FILE_PATH):
        print(f"Found completed jobs file at {RESULT_FILE_PATH}. Processing...")
        try:
            with open(RESULT_FILE_PATH, 'r') as f:
                completed_jobs = json.load(f)
                
            submit_completed_jobs(token, completed_jobs)
            
            # Optional: Move or delete the processed file to avoid double-processing
            processed_file_path = RESULT_FILE_PATH + ".processed"
            os.rename(RESULT_FILE_PATH, processed_file_path)
            print("Finished processing completed_jobs.json")
        except Exception as e:
            print(f"Error handling completed jobs: {e}")
    
    # 3. Fetch & Prepare: Request pending jobs and populate JSON
    jobs = fetch_pending_interviews(token)
    
    if jobs:
        print(f"Found {len(jobs)} pending jobs to process.")
        
        # Ensure the Google Drive directory exists path-wise locally
        try:
            os.makedirs(DRIVE_AUTOMATION_FOLDER, exist_ok=True)
            
            # Write to Google drive sync folder
            with open(JOB_FILE_PATH, 'w') as f:
                json.dump(jobs, f, indent=4)
            print(f"Saved {len(jobs)} jobs to {JOB_FILE_PATH}. Waiting for Colab...")
        except Exception as e:
            print(f"Failed to write to Google Drive folder: {e}")
            print("Make sure your DRIVE_AUTOMATION_FOLDER in `.env` is correct!")
    else:
        print("No new pending jobs found.")
        
    print("Done.")

if __name__ == "__main__":
    main()
