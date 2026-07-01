import os
import time
import requests
import re
from datetime import datetime
from google.colab import drive, auth, userdata
from googleapiclient.discovery import build
import google.auth

# 1. Mount Drive & Authenticate
drive.mount('/content/drive', force_remount=True)

try:
    auth.authenticate_user()
except Exception as e:
    print(f"Authentication warning (can be ignored if running scheduled): {e}")

BASE_PATH = "/content/drive/MyDrive/Do not touch/Audio_automation"
TOKEN_FILE = os.path.join(BASE_PATH, "token.json")

if os.path.exists(TOKEN_FILE):
    print("✅ Found token.json on Drive. Building Drive API Service with explicit credentials.")
    try:
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        drive_service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"⚠️ Failed to load credentials from token.json: {e}")
        creds, _ = google.auth.default()
        drive_service = build('drive', 'v3', credentials=creds)
else:
    print("⚠️ token.json not found! Falling back to Colab default auth.")
    creds, _ = google.auth.default()
    drive_service = build('drive', 'v3', credentials=creds)

# 2. Config & Secrets
try:
    WBL_EMAIL = userdata.get('WBL_EMAIL')
    WBL_PASSWORD = userdata.get('WBL_PASSWORD')
    WBL_API_BASE_URL = userdata.get('WBL_API_BASE_URL')
    if not WBL_API_BASE_URL:
        WBL_API_BASE_URL = "https://api.whitebox-learning.com/api"
    else:
        # Normalize URL to ensure it ends with /api and no trailing slash
        WBL_API_BASE_URL = WBL_API_BASE_URL.rstrip('/')
        if not WBL_API_BASE_URL.endswith('/api'):
            WBL_API_BASE_URL += '/api'
except userdata.SecretNotFoundError as e:
    print(f"❌ Secret not found: {e}")
    print("Please ensure WBL_EMAIL, WBL_PASSWORD, and WBL_API_BASE_URL are defined in Colab Secrets.")
    raise

VIDEO_FOLDERS = [
    "/content/drive/MyDrive/Do not touch/Interview Recordings",
    "/content/drive/MyDrive/Do not touch/Meet Recordings"
]
AUDIO_FOLDER_PATH = "/content/drive/MyDrive/Do not touch/Audio_automation/Audio_Folder"

if not os.path.exists(AUDIO_FOLDER_PATH):
    os.makedirs(AUDIO_FOLDER_PATH, exist_ok=True)

# 3. WBL API Functions
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
            cutoff_date = datetime(2026, 2, 1)
            
            # If the audio link is completely empty OR contains trash (no 'http'), queue it!
            if (i_date >= cutoff_date) and ("http" not in str(audio_link).lower()) and recording_link:
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
            if "http" not in str(audio_drive_link).lower():
                print(f"⚠️ Skipping DB update for row {row_id} - Audio link is trash (no HTTP).")
                continue
                
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

def find_file_path(video_id):
    """Uses API to get the name, then searches folders for the real mount path."""
    try:
        meta = drive_service.files().get(fileId=video_id, fields="name").execute()
        name = meta.get('name')

        # Check each folder for the file
        for folder in VIDEO_FOLDERS:
            # We check for the name exactly as it appears in the Drive Mount
            for root, dirs, files in os.walk(folder):
                if name in files:
                    return os.path.join(root, name)
        return None
    except Exception as e:
        print(f"Lookup error: {e}")
        return None

# 4. Main Processing Flow
def process_batch():
    print("🔍 Logging into WBL API...")
    token = login()
    if not token:
        print("Login failed. Exiting.")
        return

    print("🔍 Fetching pending jobs...")
    tasks = fetch_pending_interviews(token)

    if not tasks:
        print("🛏️ No new jobs found today. Exiting script.")
        return

    print(f"🎬 Processing {len(tasks)} files via Mount...")
    results = []
    
    start_time = time.time()
    # 2 hours max, leave 5 minutes buffer (115 minutes = 6900 seconds)
    TIMEOUT_SECONDS = 6900

    for task in tasks:
        elapsed = time.time() - start_time
        if elapsed > TIMEOUT_SECONDS:
            print("⚠️ Reached max execution time (near 2 hours). Stopping batch early to submit current results.")
            break
        row_id = task['row_id']
        video_id = task['video_file_id']
        output_filename = f"Audio_Rec_{row_id}.mp3"
        output_path = os.path.join(AUDIO_FOLDER_PATH, output_filename)

        # Step A: Find the actual path on the mount
        input_path = find_file_path(video_id)

        if not input_path:
            input_path = f"/content/drive/MyDrive/.shortcut-targets-by-id/{video_id}"

        # Step A.1: If it's STILL not found on the mount, download it directly via the API!
        temp_download_path = None
        if not os.path.exists(input_path):
            print(f"⚠️ Mount Path Not Found for Row {row_id}. Attempting direct API download...")
            try:
                from googleapiclient.http import MediaIoBaseDownload
                import io
                
                temp_download_path = f"/content/temp_video_{row_id}"
                request = drive_service.files().get_media(fileId=video_id)
                fh = io.FileIO(temp_download_path, 'wb')
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                
                input_path = temp_download_path
                print("✅ Successfully downloaded video directly via API!")
            except Exception as e:
                print(f"❌ API Download Failed: {e}")
                
        if os.path.exists(input_path):
            print(f"✅ Found: {input_path}")
            # Step B: Convert
            cmd = f'ffmpeg -i "{input_path}" -vn -acodec libmp3lame -b:a 128k -ar 44100 -y -loglevel error "{output_path}"'

            if os.system(cmd) == 0:
                # Step C: Get restricted link (Poll until Google Drive indexes the new file)
                link = "Link Pending Sync"
                for attempt in range(15):
                    time.sleep(2)
                    try:
                        search = drive_service.files().list(
                            q=f"name='{output_filename}'", fields="files(id, webViewLink)"
                        ).execute()
                        files_res = search.get('files', [])
                        if files_res and files_res[0].get('webViewLink'):
                            link = files_res[0].get('webViewLink')
                            break
                    except Exception as api_err:
                        pass
                
                if link == "Link Pending Sync":
                    print(f"⚠️ Drive API failed to index {output_filename} in time.")

                results.append({"row_id": row_id, "status": "success", "audio_drive_link": link})
                print(f"✨ Row {row_id} Done")
            else:
                print(f"❌ FFmpeg failed for Row {row_id}")
        else:
            print(f"❌ Mount Path Not Found for Row {row_id}")
            
        # Step D: Cleanup direct API downloads
        if temp_download_path and os.path.exists(temp_download_path):
            os.remove(temp_download_path)

    # 5. Submit Completed Jobs
    if results:
        print(f"📤 Submitting {len(results)} completed jobs to WBL API...")
        submit_completed_jobs(token, results)
        print("✅ Batch complete and synced!")
    else:
        print("🏁 Batch complete (no successful jobs to sync).")

if __name__ == "__main__":
    process_batch()