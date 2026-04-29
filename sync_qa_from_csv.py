import os
import pandas as pd
import requests
import re
import io
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


# Scope for Drive API (same as qa_generator.py)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# The specific Google Sheet provided
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1zGSD-AjirKUt0dMNHzm5KpBSZH3jXFJ3hTWIUcCTJcU/edit?usp=sharing"

# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

def login():
    """Authenticate with the WBL API and return a session/token."""
    login_url = f"{WBL_API_BASE_URL}/login"
    # Some older endpoints might use x-www-form-urlencoded
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

def update_interview_qa(token, row_id, qa_text):
    """Update the interview record in the database with the provided Q&A."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    update_url = f"{WBL_API_BASE_URL}/interviews/{row_id}"
    
    updates = {
        "q_a": qa_text
    }
    
    try:
        response = requests.put(update_url, json=updates, headers=headers)
        response.raise_for_status()
        print(f"✅ Successfully updated q_a for Interview ID {row_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to update q_a for row {row_id}: {e}")
        return False

def extract_drive_id(url):
    """Extracts the file ID from a Google Drive URL."""
    if not url: return None
    match = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    if match: return match.group(1)
    match = re.search(r"id=([a-zA-Z0-9-_]+)", url)
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

def download_sheet_as_df(sheet_url):
    """Download Google Sheet as a CSV via Google Drive API and load into Pandas."""
    file_id = extract_drive_id(sheet_url)
    if not file_id:
        print(f"Could not extract Drive ID from {sheet_url}")
        return None

    try:
        service = get_drive_service()
        print(f"Downloading Google Sheet (ID: {file_id}) via Drive API...")
        
        # Export the Google Sheet as CSV
        request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        response = request.execute()
        
        # Load the raw CSV bytes directly into pandas
        return pd.read_csv(io.BytesIO(response))
    except Exception as e:
        print(f"Error downloading Google Sheet via Drive API: {e}")
        return None

def main():
    print("=== Automated Google Sheets to Database Sync ===")
    
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
        
    # Convert API data to Pandas DataFrame
    df_interviews = pd.DataFrame(interviews_data)
    
    # 3. Download Google Sheet dynamically
    df_sheet = download_sheet_as_df(GOOGLE_SHEET_URL)
    if df_sheet is None:
        print("Failed to download Google Sheet. Exiting.")
        return
        
    # Clean column names just in case there are trailing spaces
    df_sheet.columns = df_sheet.columns.str.strip().str.lower()
    df_interviews.columns = df_interviews.columns.str.strip().str.lower()
    
    # Ensure required columns exist
    if 'links' not in df_sheet.columns or 'questions' not in df_sheet.columns:
        print("Error: Google Sheet must contain 'links' and 'questions' columns.")
        return
        
    if 'id' not in df_interviews.columns or 'transcript' not in df_interviews.columns:
        print("Error: API payload must contain 'id' and 'transcript' columns.")
        return
        
    # 4. Clean up the link strings to ensure perfect matching
    df_sheet['links'] = df_sheet['links'].astype(str).str.strip()
    df_interviews['transcript'] = df_interviews['transcript'].astype(str).str.strip()
    
    # Drop rows where links or transcript are missing
    df_sheet = df_sheet.dropna(subset=['links', 'questions'])
    df_interviews = df_interviews.dropna(subset=['id', 'transcript'])
    
    print(f"Found {len(df_sheet)} rows in Google Sheet, and {len(df_interviews)} rows from the API.")
    
    # 5. Merge DataFrames on the transcript link
    merged_df = pd.merge(df_interviews, df_sheet, left_on='transcript', right_on='links', how='inner')
    
    match_count = len(merged_df)
    print(f"\nFound {match_count} exact matches based on the transcript link!")
    
    if match_count == 0:
        print("No matches found. Exiting.")
        return
        
    # 6. Push updates to backend
    print("\nPushing matched Q&A data to the server...")
    success_count = 0
    for index, row in merged_df.iterrows():
        interview_id = int(row['id'])
        qa_text = str(row['questions'])
        
        # Call API to update this specific row
        if update_interview_qa(token, interview_id, qa_text):
            success_count += 1
            
    print(f"\n=== Sync Complete! Successfully updated {success_count}/{match_count} matches. ===")

if __name__ == "__main__":
    main()
