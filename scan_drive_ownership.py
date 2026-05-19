import os
import re
import json
import requests
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# We only need readonly scope just to check ownership metadata
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

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
    token_file = 'token.json'  # Standard readonly token
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def check_ownership(service, drive_id, file_type, row_id):
    """Queries Drive API to see if you are the owner."""
    if not drive_id:
        return None
        
    try:
        # Ask Google Drive specifically for the 'ownedByMe' boolean and 'owners' array
        metadata = service.files().get(fileId=drive_id, fields='name, ownedByMe, owners').execute()
        
        owned_by_me = metadata.get('ownedByMe', False)
        
        if not owned_by_me:
            # Extract the owner email if available
            owners = metadata.get('owners', [])
            owner_email = owners[0].get('emailAddress', 'Unknown') if owners else 'Unknown'
            
            return {
                "interview_id": row_id,
                "file_type": file_type,
                "drive_id": drive_id,
                "file_name": metadata.get('name', 'Unknown'),
                "current_owner_email": owner_email
            }
            
    except Exception as e:
        if "404" in str(e):
            print(f"   [Error] Row {row_id} {file_type} not found (Deleted or no access).")
        else:
            print(f"   [Error] Drive API failed for Row {row_id} {file_type}: {e}")
            
    return None

def main():
    print("=== Google Drive Ownership Scanner ===")
    
    token = login()
    if not token:
        return
        
    interviews = fetch_interviews(token)
    if not interviews:
        return
        
    print("\nAuthenticating with Google Drive...")
    try:
        drive_service = get_drive_service()
    except Exception as e:
        print(f"Failed to authenticate with Google Drive: {e}")
        return

    not_owned_files = []
    total_scanned = 0
    
    print(f"\nScanning {len(interviews)} records to verify ownership...\n")
    
    for row in interviews:
        interview_id = row.get('id')
        
        audio_link = row.get('audio_link')
        recording_link = row.get('recording_link')
        
        audio_id = extract_drive_id(audio_link)
        recording_id = extract_drive_id(recording_link)
        
        if audio_id:
            total_scanned += 1
            result = check_ownership(drive_service, audio_id, "Audio", interview_id)
            if result:
                print(f"⚠️ Row {interview_id}: AUDIO is owned by {result['current_owner_email']}")
                not_owned_files.append(result)
                
        if recording_id:
            total_scanned += 1
            result = check_ownership(drive_service, recording_id, "Video", interview_id)
            if result:
                print(f"⚠️ Row {interview_id}: VIDEO is owned by {result['current_owner_email']}")
                not_owned_files.append(result)

    print(f"\n=== Scan Complete ===")
    print(f"Scanned {total_scanned} total files.")
    print(f"Found {len(not_owned_files)} files that you DO NOT own.")
    
    output_file = "not_owned_files.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(not_owned_files, f, indent=4, ensure_ascii=False)
        
    print(f"Saved the list of files to download/reupload to {output_file}")

if __name__ == "__main__":
    main()
