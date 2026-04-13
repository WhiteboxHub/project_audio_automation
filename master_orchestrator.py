import os
import time
import json
import requests
import re
from datetime import datetime
from dotenv import load_dotenv
import pyautogui

# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

DRIVE_AUTOMATION_FOLDER = os.getenv("DRIVE_AUTOMATION_FOLDER", r"G:\My Drive\Automation")
COLAB_URL = os.getenv("COLAB_URL")
CHROME_USER_DATA_DIR = os.getenv("CHROME_USER_DATA_DIR")
CHROME_PROFILE_NAME = os.getenv("CHROME_PROFILE_NAME", "Default")

JOB_FILE_PATH = os.path.join(DRIVE_AUTOMATION_FOLDER, "pending_jobs.json")
RESULT_FILE_PATH = os.path.join(DRIVE_AUTOMATION_FOLDER, "completed_jobs.json")

def login():
    """Authenticate with the WBL API and return a session/token."""
    login_url = f"{WBL_API_BASE_URL}/login"
    payload = {"username": WBL_EMAIL, "password": WBL_PASSWORD}
    
    for attempt in range(3):
        try:
            response = requests.post(login_url, data=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data.get("access_token") or data.get("token")
        except Exception as e:
            print(f"⚠️ Login attempt {attempt+1} failed: {e}")
            time.sleep(4)
            
    print("❌ Critical: Failed to authenticate to WBL API after 3 retries.")
    return None

def extract_google_drive_id(url):
    """Extracts the file ID from a Google Drive URL."""
    if not url: return None
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match: return match.group(1)
    match = re.search(r"id=([a-zA-Z0-9-_]+)", url)
    if match: return match.group(1)
    return None

def fetch_pending_interviews(token):
    """Fetch interviews and filter for date >= '2026-03-30' and empty audio_link."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    
    interviews = None
    for attempt in range(3):
        try:
            response = requests.get(interviews_url, headers=headers, timeout=60)
            response.raise_for_status()
            data_payload = response.json()
            if isinstance(data_payload, dict) and "data" in data_payload:
                interviews = data_payload["data"]
            else:
                interviews = data_payload
            break
        except Exception as e:
            print(f"⚠️ Fetch attempt {attempt+1} failed: {e}")
            time.sleep(4)
            
    if interviews is None:
        print("❌ Critical: Failed to fetch interviews after 3 retries.")
        return []

    pending_jobs = []
    for interview in interviews:
        i_date_str = interview.get("interview_date", "")
        audio_link = interview.get("audio_link", "")
        recording_link = interview.get("recording_link", "")
        row_id = interview.get("id")
        
        if not i_date_str: continue
            
        try:
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
        except:
            pass
    return pending_jobs

def submit_completed_jobs(token, completed_jobs):
    """Update interviews in the backend using PUT /interviews/{id}."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
         
    for job in completed_jobs:
        row_id = job.get("row_id")
        status = job.get("status")
        audio_drive_link = job.get("audio_drive_link")
        
        if status == "success" and audio_drive_link:
            print(f"Updating row {row_id} with new audio link...")
            update_url = f"{WBL_API_BASE_URL}/interviews/{row_id}"
            updates = {"audio_link": audio_drive_link}
            
            job_success = False
            for attempt in range(3):
                try:
                    response = requests.put(update_url, json=updates, headers=headers, timeout=60)
                    response.raise_for_status()
                    print(f"Successfully updated row {row_id}")
                    job_success = True
                    break
                except Exception as e:
                    print(f"⚠️ Attempt {attempt+1} failed to update row {row_id}: {e}")
                    time.sleep(4)
                    
            if not job_success:
                print(f"❌ Failed to update row {row_id} after 3 retries. Skipping.")

def run_browser_bot():
    """Launch Chrome natively and use PyAutoGUI to physically press Ctrl+F9."""
    print("🚀 Firing up Chrome...")
    
    import subprocess
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    if not os.path.exists(chrome_path):
        print(f"❌ Error: Could not find Google Chrome installed at {chrome_path}")
        return False

    print("Booting Chrome natively...")
    try:
        # CRITICAL FIX: Force close all existing Chromes first to ensure a clean window pops up
        os.system("taskkill /f /im chrome.exe >nul 2>&1")
        time.sleep(2)
        
        # We start Chrome just like Windows does, opening straight to Colab
        proc = subprocess.Popen([
            chrome_path,
            "--start-maximized",
            f"--profile-directory={CHROME_PROFILE_NAME}",
            COLAB_URL
        ])
    except Exception as e:
        print(f"⚠️ Failed to launch Chrome process: {e}")
        return False
        
    print("⏳ Waiting 18 seconds for the Google Colab UI to fully load on screen...")
    time.sleep(18)
    
    # Force focus by clicking the middle of the screen
    try:
        width, height = pyautogui.size()
        pyautogui.click(width / 2, height / 2)
        time.sleep(1)
    except:
        pass
    
    print("⌨️ Simulating 'Ctrl + F9' (Run All)...")
    pyautogui.hotkey('ctrl', 'f9')
    time.sleep(2)
    
    print("⌨️ Simulating 'Ctrl + Enter' (Run Selected Cell) just in case F9 was blocked...")
    pyautogui.hotkey('ctrl', 'enter')
    
    # Just in case there is a "Run anyway" warning popup from Google, we wait 3 seconds and press Enter
    time.sleep(3)
    print("⌨️ Pressing 'Enter' just in case a warning popup appeared...")
    pyautogui.press('enter')
    
    print("✅ Colab is running. Leaving the browser open to process.")
    return True

def process_single_run():
    print("===========================================")
    print("      Orchestrator (Single Run Mode)      ")
    print("===========================================")
    
    # 1. CLEANUP PREVIOUS RUN
    if os.path.exists(RESULT_FILE_PATH):
        print("⚠️ Found old completed_jobs.json. Updating Database...")
        token = login()
        if token:
           with open(RESULT_FILE_PATH, 'r') as f:
               completed_jobs = json.load(f)
           submit_completed_jobs(token, completed_jobs)
           os.remove(RESULT_FILE_PATH)
           print("✅ Database updated.")
        else:
           print("Login failed. Exiting.")
           return

    if os.path.exists(JOB_FILE_PATH):
        print("⏳ pending_jobs.json exists. Wait for Colab to finish or manually delete it to restart. Exiting.")
        return

    # 2. FETCH NEW JOBS
    print("🔍 Checking API for new interviews...")
    token = login()
    if not token:
        print("Login failed. Exiting.")
        return
        
    jobs = fetch_pending_interviews(token)
    
    if not jobs:
        print("🛏️ No new jobs found today. Exiting script.")
        return
        
    # 3. QUEUE JOBS
    print(f"📦 Found {len(jobs)} jobs. Writing to Drive...")
    os.makedirs(DRIVE_AUTOMATION_FOLDER, exist_ok=True)
    with open(JOB_FILE_PATH, 'w') as f:
        json.dump(jobs, f, indent=4)
        
    print("Syncing file to cloud...")
    time.sleep(15) 
    
    # 4. TRIGGER COLAB
    success = run_browser_bot()
    if not success:
       print("Browser launch failed. Exiting.")
       return
       
    # 5. WAIT FOR RESULT
    print(f"⏳ Waiting for Colab to finish converting {len(jobs)} jobs...")
    timeout = 60 * 60 * 2 # Wait up to 2 hours
    elapsed = 0
    poll_interval = 10
    
    while elapsed < timeout:
        if os.path.exists(RESULT_FILE_PATH):
            print("🎉 completed_jobs.json detected in Drive!")
            time.sleep(5) # buffer to ensure download is complete
            
            with open(RESULT_FILE_PATH, 'r') as f:
                completed_jobs = json.load(f)
                
            submit_completed_jobs(token, completed_jobs)
            os.remove(RESULT_FILE_PATH)
            
            print("✅ Everything finished successfully. Script complete!")
            return
            
        time.sleep(poll_interval)
        elapsed += poll_interval
        
    print("❌ Timeout reached. Exiting.")

if __name__ == "__main__":
    process_single_run()
