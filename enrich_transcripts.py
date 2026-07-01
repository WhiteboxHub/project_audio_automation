import os
import json
import requests
import pandas as pd
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
    print("=== Enriching Transcripts with type_of_interview ===")
    
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
        
    print(f"Total interviews fetched from API: {len(interviews_data)}")
    
    # 3. Convert API data to Pandas DataFrame
    # We only need the 'id' and 'type_of_interview' columns
    df_api = pd.DataFrame(interviews_data)
    if 'id' not in df_api.columns or 'type_of_interview' not in df_api.columns:
        print("Required columns missing from API data. Exiting.")
        return
        
    # Filter the API dataframe to just what we need to merge
    df_api = df_api[['id', 'type_of_interview', 'company', 'mode_of_interview', 'interview_date']]
    
    # Rename 'id' to 'interview_id' so it matches the transcripts file column exactly
    df_api.rename(columns={'id': 'interview_id', 'type_of_interview': 'type_of_interview', 'company': 'company', 'mode_of_interview': 'mode_of_interview', 'interview_date': 'interview_date'}, inplace=True)
    
    # 4. Load the transcripts JSON file
    transcripts_file = "questions_dump.json"
    if not os.path.exists(transcripts_file):
        print(f"File {transcripts_file} not found. Exiting.")
        return
        
    print(f"Loading {transcripts_file}...")
    df_transcripts = pd.read_json(transcripts_file)
    print(f"Loaded {len(df_transcripts)} transcripts.")
    
    # 5. Merge the DataFrames on 'interview_id' using Pandas Left Join
    print("Merging datasets using pandas...")
    # 'left' join means we keep all rows from df_transcripts, even if the API data is missing
    df_enriched = pd.merge(df_transcripts, df_api, on='interview_id', how='left')
    
    # Provide a default value for missing 'type_of_interview' as defined in your DB schema
    df_enriched['type_of_interview'].fillna('Recruiter Call', inplace=True)
    
    # 6. Save the enriched dataset
    output_json = "questions_enriched.json"
    output_csv = "questions_enriched.csv"
    
    print(f"Saving enriched data to {output_json} and {output_csv}...")
    
    # Convert back to dict and dump to handle unicode properly
    enriched_data = df_enriched.to_dict(orient='records')
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(enriched_data, f, indent=4, ensure_ascii=False)
        
    # Also save as CSV for easy viewing in Excel/Pandas analysis
    df_enriched.to_csv(output_csv, index=False, encoding='utf-8')
    
    print("=== Enrichment Complete! ===")

if __name__ == "__main__":
    main()
