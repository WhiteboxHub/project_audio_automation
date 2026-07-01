import os
import json
import base64
import re
import time
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

# Scope for reading Gmail
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """Authenticate with Gmail API and return the service object."""
    creds = None
    token_file = 'token_gmail.json'
    
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
            
    return build('gmail', 'v1', credentials=creds)

def login():
    """Authenticate with the WBL API and return a session/token."""
    login_url = f"{WBL_API_BASE_URL}/login"
    payload = {"username": WBL_EMAIL, "password": WBL_PASSWORD}
    try:
        response = requests.post(login_url, data=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token") or data.get("token")
    except Exception as e:
        print(f"❌ WBL Login failed: {e}")
        return None

def fetch_interviews(token):
    """Fetch all interviews from the WBL API."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    try:
        response = requests.get(interviews_url, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    except Exception as e:
        print(f"❌ Failed to fetch interviews: {e}")
        return []

def update_interview(token, row_id, update_payload):
    """Update the interview record with only the provided fields."""
    if not update_payload:
        return False
        
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    update_url = f"{WBL_API_BASE_URL}/interviews/{row_id}"
    
    try:
        response = requests.put(update_url, json=update_payload, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"✅ Successfully updated row {row_id} in WBL database.")
        return True
    except Exception as e:
        return False

def extract_meet_id(text):
    """Extracts a Google Meet ID (abc-defg-hij) from text."""
    if not text:
        return None
    match = re.search(r'\b[a-z]{3}-[a-z]{4}-[a-z]{3}\b', str(text).lower())
    if match:
        return match.group(0)
    return None

def extract_links_from_email(service, message_id):
    """Fetches the email body and extracts the Video and Docs Drive links."""
    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        
        # Traverse the payload parts to find the HTML body
        parts = [msg['payload']]
        html_body = ""
        
        while parts:
            part = parts.pop(0)
            if part.get('parts'):
                parts.extend(part['parts'])
            elif part.get('mimeType') == 'text/html':
                data = part['body'].get('data')
                if data:
                    html_body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break
        
        if not html_body:
            return None, None
            
        soup = BeautifulSoup(html_body, 'html.parser')
        links = [a['href'] for a in soup.find_all('a', href=True)]
        
        video_link = None
        docs_link = None
        
        for link in links:
            if 'drive.google.com/file/d/' in link and not video_link:
                video_link = link
            elif 'docs.google.com/document/d/' in link and not docs_link:
                docs_link = link
                
        return video_link, docs_link
        
    except Exception as e:
        print(f"⚠️ Error parsing email {message_id}: {e}")
        return None, None

def search_gmail_for_recap(service, search_term):
    """Searches Gmail for the Gemini notes email for a specific candidate name."""
    query = f'from:gemini-notes@google.com "{search_term}" newer_than:4d'
    
    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
        messages = results.get('messages', [])
        
        if not messages:
            return None, None
            
        return extract_links_from_email(service, messages[0]['id'])
        
    except Exception as e:
        print(f"⚠️ Gmail API Search failed for '{search_term}': {e}")
        return None, None

def main():
    print("===========================================")
    print("    Gemini Meet Notes Sync Automation      ")
    print("===========================================")
    
    # 1. Login to WBL
    print("🔑 Authenticating with WBL API...")
    wbl_token = login()
    if not wbl_token:
        return
        
    # 2. Login to Gmail
    print("📧 Authenticating with Gmail API...")
    try:
        gmail_service = get_gmail_service()
    except Exception as e:
        print(f"❌ Failed to authenticate Gmail API: {e}")
        print("Please ensure credentials.json exists and you authorize the prompt.")
        return
        
    # 3. Fetch Interviews
    print("📡 Fetching interviews from WBL database...")
    interviews = fetch_interviews(wbl_token)
    
    # Filter bounds
    cutoff_date = datetime.today() - timedelta(days=4)
    cutoff_date_str = cutoff_date.strftime('%Y-%m-%d')
    
    processed_count = 0
    
    for row in interviews:
        row_id = row.get("id")
        
        # Check Date Limit
        raw_date = str(row.get('interview_date', ''))
        interview_date = raw_date.split('T')[0] if raw_date else "Unknown"
        
        if interview_date == "Unknown" or interview_date < cutoff_date_str:
            continue
            
        # Check if recording_link is empty
        recording_link = str(row.get('recording_link', '')).strip()
        has_recording = recording_link and recording_link.lower() != "none" and "http" in recording_link
        
        if has_recording:
            continue
            
        transcript_link = str(row.get('transcript', '')).strip()
        has_transcript = transcript_link and transcript_link.lower() != "none" and "http" in transcript_link
            
        # Extract Meet ID from 'notes'
        notes = str(row.get('notes', ''))
        meet_id = extract_meet_id(notes)
        
        # If there's no Meet ID in the notes, skip this row.
        if not meet_id:
            continue
            
        # The Gemini email contains the full metadata string (base_name) in the subject.
        candidate = row.get('candidate', {})
        candidate_name = str(candidate.get('full_name', '')).strip()
        
        if not candidate_name:
            continue
            
        interview_id = str(row.get('id', ''))
        interview_type = str(row.get('type_of_interview', 'Unknown'))
        company_name = str(row.get('company', 'Unknown'))
        mode_of_interview = str(row.get('mode_of_interview', 'Unknown'))
        
        # Build the metadata string exactly as it appears in the email subject
        base_name = f"{interview_id}_{candidate_name}_{interview_type}_{company_name}_{interview_date}_{mode_of_interview}"
            
        print(f"\n🔍 Found candidate row {row_id} with missing links (Meet ID: {meet_id}).")
        print(f"   Searching Gmail for metadata string: {base_name}")
        
        video_url, docs_url = search_gmail_for_recap(gmail_service, base_name)
        
        if video_url or docs_url:
            update_payload = {}
            if not has_recording and video_url:
                update_payload["recording_link"] = video_url
                print(f"   🎥 Found New Video: {video_url}")
            if not has_transcript and docs_url:
                update_payload["transcript"] = docs_url
                print(f"   📄 Found New Notes: {docs_url}")
            
            if update_payload:
                update_interview(wbl_token, row_id, update_payload)
                processed_count += 1
                time.sleep(2)
            else:
                print("   ⚠️ Links already exist in DB. Skipping overwrite.")
        else:
            print(f"   ⚠️ No Gemini recap email found containing candidate name '{candidate_name}'.")

    print(f"\n🏁 Sync Complete! Total records updated: {processed_count}")

if __name__ == "__main__":
    main()
