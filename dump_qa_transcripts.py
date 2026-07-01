import os
import json
import requests
import re
import io
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# Scope for Drive API (readonly is fine for downloading)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

def login():
    """Authenticate with the WBL API and return a session/token."""
    login_url = f"{WBL_API_BASE_URL}/login"
    payload = {
        "username": WBL_EMAIL,
        "password": WBL_PASSWORD
    }
    
    try:
        response = requests.post(login_url, data=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token") or data.get("token")
    except Exception as e:
        print(f"Login failed: {e}")
        return None

def fetch_interviews(token):
    """Fetch all interviews from the backend."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    print("Fetching interviews from API...")
    
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
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def get_drive_file_content(service, file_id):
    """Downloads the content of a Google Drive file."""
    try:
        # First get the metadata to know the mime type
        file_metadata = service.files().get(fileId=file_id, fields='mimeType').execute()
        mime_type = file_metadata.get('mimeType', '')

        if mime_type.startswith('application/vnd.google-apps.'):
            # It's a Google Workspace document (like Google Docs)
            if mime_type == 'application/vnd.google-apps.document':
                # Export Google Docs as plain text
                request = service.files().export_media(fileId=file_id, mimeType='text/plain')
            else:
                return f"[Unsupported Google Workspace file type: {mime_type}]"
        else:
            # It's a regular file (e.g., uploaded txt file), download directly
            request = service.files().get_media(fileId=file_id)
            
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            
        # Decode the file content as UTF-8 text
        return fh.getvalue().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"Error downloading file {file_id}: {e}")
        return None

def main():
    print("=== Fetching Q&A and Transcripts ===")
    
    # 1. Login to Backend API
    print("Authenticating with Admin Portal...")
    token = login()
    if not token:
        print("Could not authenticate. Exiting.")
        return
        
    # 2. Fetch interviews from API
    interviews_data = fetch_interviews(token)
    if not interviews_data:
        print("No interviews found or failed to fetch. Exiting.")
        return
        
    print(f"Total interviews fetched: {len(interviews_data)}")
    
    # Initialize Drive service
    print("Authenticating with Google Drive...")
    try:
        service = get_drive_service()
    except Exception as e:
        print(f"Failed to authenticate with Google Drive: {e}")
        return

    qa_results = []
    transcript_results = []
    
    for row in interviews_data:
        qa_text = row.get('q_a')
        
        # Check if q_a is not null and not empty
        if not qa_text or str(qa_text).strip() == "" or str(qa_text).strip() == "NO_QUESTIONS_FOUND":
            continue
            
        interview_id = row.get('id')
        transcript = row.get('transcript')
        company = row.get('company')
        mode_of_interview = row.get('mode_of_interview')
        interview_date = row.get('interview_date')
        type_of_interview = row.get('type_of_interview')
        # Add to Q&A results
        qa_results.append({
            "interview_id": interview_id,
            "q_a_text": qa_text,
            "company": company,
            "mode_of_interview": mode_of_interview,
            "interview_date": interview_date,
            "type_of_interview": type_of_interview
        })
        
        # Check for and skip OneDrive/SharePoint links for transcripts
        transcript_url_str = str(transcript_url).lower() if transcript_url else ""
        if 'onedrive.com' in transcript_url_str or 'sharepoint.com' in transcript_url_str or '1drv.ms' in transcript_url_str:
            print(f"Skipping Transcript for Interview ID {interview_id}: It is a OneDrive/SharePoint link.")
            continue
            
        transcript_id = extract_drive_id(transcript_url)
        
        print(f"\nProcessing Interview ID {interview_id}...")
        
        transcript_content = None
        if transcript_id:
            print(f"Fetching Drive content for transcript ID: {transcript_id}")
            transcript_content = get_drive_file_content(service, transcript_id)
            
            # Add to Transcripts results
            transcript_results.append({
                "interview_id": interview_id,
                "transcript_link": transcript_url,
                "transcript_content": transcript_content
            })
        else:
            print(f"No valid Drive link found for transcript: {transcript_url}")
            
    # Dump to JSON
    qa_filename = "qa_dump.json"
    transcript_filename = "transcripts_dump.json"
    
    print(f"\nWriting {len(qa_results)} Q&A records to {qa_filename}...")
    with open(qa_filename, 'w', encoding='utf-8') as f:
        json.dump(qa_results, f, indent=4, ensure_ascii=False)
        
    print(f"Writing {len(transcript_results)} transcript records to {transcript_filename}...")
    with open(transcript_filename, 'w', encoding='utf-8') as f:
        json.dump(transcript_results, f, indent=4, ensure_ascii=False)
        
    print(f"=== Dump Complete! ===")

if __name__ == "__main__":
    main()
