import os
import json
import requests
from dotenv import load_dotenv

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

def main():
    print("=== Finding Interviews Missing Recording Links ===")
    
    token = login()
    if not token:
        print("Could not authenticate. Exiting.")
        return
        
    interviews_data = fetch_interviews(token)
    if not interviews_data:
        print("No interviews found or failed to fetch. Exiting.")
        return
        
    missing_recordings = []
    
    for interview in interviews_data:
        recording_link = interview.get("recording_link")
        
        # Check if the recording link is completely missing or just an empty string
        if not recording_link or str(recording_link).strip() == "":
            
            # The candidate data is nested in a dictionary under the 'candidate' key
            candidate_dict = interview.get("candidate") or {}
            candidate_name = candidate_dict.get("full_name", "Unknown")
            
            missing_recordings.append({
                "interview_id": interview.get("id"),
                "candidate_name": candidate_name,
                "interview_type": interview.get("type_of_interview", "Unknown"),
                "company_name": interview.get("company", "Unknown"),
                "interview_date": interview.get("interview_date", "Unknown"),
                "mode_of_interview": interview.get("mode_of_interview", "Unknown")
            })
            
    output_file = "missing_recordings.json"
    print(f"\nFound {len(missing_recordings)} interviews with missing recording links.")
    print(f"Saving to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(missing_recordings, f, indent=4, ensure_ascii=False)
        
    print("=== Complete! ===")

if __name__ == "__main__":
    main()
