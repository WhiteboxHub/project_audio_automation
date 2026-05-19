import os
import re
import requests
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# We MUST use the full drive scope to rename files. 
# Readonly scope will cause a 403 Forbidden error.
SCOPES = ['https://www.googleapis.com/auth/drive']

# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

def login():
    """Authenticate with the WBL API and return a session/token."""
    login_url = f"{WBL_API_BASE_URL}/login"
    payload = {"username": WBL_EMAIL, "password": WBL_PASSWORD}
    try:
        response = requests.post(login_url, data=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token") or data.get("token")
    except Exception as e:
        print(f"WBL Login failed: {e}")
        return None

def fetch_interviews(token):
    """Fetch all interviews from the backend."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    print("Fetching interviews from WBL API...")
    try:
        response = requests.get(interviews_url, headers=headers)
        response.raise_for_status()
        data_payload = response.json()
        if isinstance(data_payload, dict) and "data" in data_payload:
            return data_payload["data"]
        return data_payload
    except Exception as e:
        print(f"Failed to fetch interviews: {e}")
        return []

def extract_drive_id(url):
    """Extracts the file ID from a Google Drive URL."""
    if not url: return None
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", str(url))
    if match: return match.group(1)
    match = re.search(r"id=([a-zA-Z0-9-_]+)", str(url))
    if match: return match.group(1)
    return None

def get_drive_service():
    """Authenticate with Google Drive API and return the service object."""
    creds = None
    # Use a specific token name to ensure we get FULL read/write scope 
    # instead of the readonly scope from previous scripts.
    token_file = 'token_full_drive.json'
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            # This will pop open your browser to ask for permissions
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def sanitize_filename(name):
    """Removes invalid characters for filenames."""
    if name is None:
        return "Unknown"
    name = str(name)
    # Replace slashes, colons, and other forbidden characters with hyphens
    name = re.sub(r'[\\/*?:"<>|]', "-", name)
    # Remove newlines
    name = name.replace('\n', '').replace('\r', '')
    return name.strip()

def rename_file_on_drive(service, drive_id, base_new_name, file_type):
    """Renames a file on Google Drive while preserving its original extension."""
    if not drive_id:
        return

    try:
        # Get the original file name to preserve the extension
        file_metadata = service.files().get(fileId=drive_id, fields='name').execute()
        original_name = file_metadata.get('name', '')
        
        # Find the extension (e.g. .mp4, .mp3)
        ext = ""
        if '.' in original_name:
            ext = "." + original_name.split('.')[-1]
            
        # Optional: Add a suffix to differentiate Audio from Video if they have the exact same name
        # but usually the extension handles this. We will just use the exact base name requested.
        new_name = base_new_name + ext
        
        if original_name == new_name:
            print(f"   [Skipped] {file_type} is already named correctly.")
            return
            
        # Update the file name in Google Drive
        service.files().update(fileId=drive_id, body={'name': new_name}).execute()
        print(f"   [Renamed] {file_type}: {original_name} -> {new_name}")
        
    except Exception as e:
        if "404" in str(e):
            print(f"   [Error] {file_type} File not found (Deleted or no permission).")
        else:
            print(f"   [Error] Failed to rename {file_type} ({drive_id}): {e}")

def main():
    print("=== Google Drive Auto-Renamer ===")
    
    # 1. Login & Fetch Table
    token = login()
    if not token:
        return
        
    interviews = fetch_interviews(token)
    if not interviews:
        return
        
    # 2. Authenticate Google Drive
    print("\nAuthenticating with Google Drive (Full Permissions)...")
    try:
        drive_service = get_drive_service()
    except Exception as e:
        print(f"Failed to authenticate with Google Drive: {e}")
        print("Make sure credentials.json is in the folder!")
        return

    # 3. Iterate over the interviews
    print(f"\nProcessing {len(interviews)} records for renaming...\n")
    
    for row in interviews:
        interview_id = str(row.get('id', ''))
        
        candidate = row.get('candidate') or {}
        candidate_name = candidate.get('full_name', 'Unknown')
        
        interview_type = row.get('type_of_interview', 'Unknown')
        company_name = row.get('company', 'Unknown')
        interview_date = row.get('interview_date', 'Unknown')
        mode_of_interview = row.get('mode_of_interview', 'Unknown')
        
        # Build the exact naming convention string
        # interview_id_candidate_name_interview_type_company_name_interview_date_mode_of_interview
        base_name = f"{interview_id}_{candidate_name}_{interview_type}_{company_name}_{interview_date}_{mode_of_interview}"
        
        # Sanitize it so Google Drive doesn't throw errors
        safe_base_name = sanitize_filename(base_name)
        
        audio_link = row.get('audio_link')
        recording_link = row.get('recording_link')
        
        audio_id = extract_drive_id(audio_link)
        recording_id = extract_drive_id(recording_link)
        
        if not audio_id and not recording_id:
            continue
            
        print(f"Row {interview_id}: {candidate_name}")
        
        if audio_id:
            rename_file_on_drive(drive_service, audio_id, safe_base_name, "Audio")
            
        if recording_id:
            rename_file_on_drive(drive_service, recording_id, safe_base_name, "Video")

    print("\n=== All Renaming Complete! ===")

if __name__ == "__main__":
    main()
