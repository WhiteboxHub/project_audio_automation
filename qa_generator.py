import os
import time
import requests
import re
import itertools
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']# Load Environment Variables from .env file
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

# LM Studio local server endpoint (OpenAI compatible)
LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"

def login():
    """Authenticate with the WBL API and return a session/token."""
    login_url = f"{WBL_API_BASE_URL}/login"
    payload = {
        "username": WBL_EMAIL,
        "password": WBL_PASSWORD
    }
    
    print(f"Authenticating with Admin Portal...")
    try:
        response = requests.post(login_url, data=payload)
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token") or data.get("token")
        print("Authentication successful.")
        return token
    except Exception as e:
        print(f"Failed to authenticate: {e}")
        return None

def fetch_interviews(token):
    """Fetch all interviews from the backend."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    print("Fetching interviews...")
    
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

def fetch_api_keys(token):
    """Fetch candidate API keys from the backend."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    keys_url = f"{WBL_API_BASE_URL}/candidates/credentials?limit=100" 
    print("Fetching API keys for round robin...")
    
    try:
        response = requests.get(keys_url, headers=headers)
        response.raise_for_status()
        data_payload = response.json()
        
        # Extract key info from the payload
        keys_list = []
        data = data_payload.get("data", data_payload) if isinstance(data_payload, dict) else data_payload
        for item in data:
            if isinstance(item, dict) and "api_key" in item:
                keys_list.append({
                    "api_key": item["api_key"],
                    "provider_name": item.get("provider_name", "openai").lower(),
                    "model_name": item.get("model_name", "gpt-4o-mini")
                })
                
        return keys_list
    except Exception as e:
        print(f"Failed to fetch API keys: {e}")
        return []

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

def download_transcript(transcript_link):
    """
    Download the text content of the transcript from Google Drive using OAuth.
    """
    file_id = extract_drive_id(transcript_link)
    if not file_id:
        print(f"Could not extract Drive ID from {transcript_link}")
        return None

    try:
        service = get_drive_service()
        print(f"Downloading transcript for file ID: {file_id}...")
        
        # Export the Google Doc as plain text. This contains all text sequentially.
        response = service.files().export_media(fileId=file_id, mimeType='text/plain').execute()
        text = response.decode('utf-8')
        return text
    except Exception as e:
        print(f"Error downloading transcript via API: {e}")
        print("Ensure 'credentials.json' exists in this folder and your Google account has access to the file.")
        return None

def generate_qa_with_llm(transcript_text, key_info):
    """Send the entire transcript to the LLM to generate Q&A in one shot, using the provided API key info."""
    print(f"Generating Q&A with LLM ({key_info['provider_name']})...")
    
    # Isolate the transcript part if it has "Transcript" keyword
    transcript = transcript_text.split("Transcript")[1] if "Transcript" in transcript_text else transcript_text
    
    system_prompt = """You are an AI assistant that converts raw interview transcripts into high-quality interview preparation questions.

Objective:
Produce a concise, non-redundant, and interviewer-grade question set that covers distinct technical and conceptual areas.

Rules:
1. Rewrite questions into clear, grammatically correct, professional English.
2. Preserve the original intent of the questions while improving clarity and structure.
3. Strict grounding constraint: Do NOT introduce new topics, concepts, or questions that are not present in the transcript. Every question must be traceable to the source content.
4. Eliminate completely: duplicates, filler or meta questions (e.g., “can you hear me?”), vague or low-value questions.
5. Merge overlapping or fragmented questions into a single, stronger question.
6. Ensure each question tests a distinct dimension, only if supported by the transcript, such as: system design / architecture, scalability / performance, retrieval & ranking, evaluation & metrics, trade-offs / decision-making, implementation details.
7. Prefer depth over repetition: Combine related sub-parts into one well-structured question. Avoid splitting one idea into multiple weak questions.
8. Keep questions concise but complete (no unnecessary verbosity).
9. Maintain a logical flow from: high-level → detailed → system design → behavioral.
10. Do not include answers, explanations, or commentary.
11. If there are NO valid questions in this transcript, respond with exactly: NO_QUESTIONS_FOUND

Output Format:
<question>
<question>

(one per line, no labels, no extra text)"""

    api_key = key_info["api_key"].strip()
    provider = key_info["provider_name"].strip().lower()
    # Ensure model doesn't have trailing spaces which cause 404 errors in some APIs
    model = key_info["model_name"].strip() if key_info["model_name"] else ""
    
    try:
        ai_output = ""
        if provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            
            def make_openai_request(target_model):
                payload = {
                    "model": target_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Here is the full interview transcript:\n\n{transcript}"}
                    ],
                    "temperature": 0.1
                }
                return requests.post(url, json=payload, headers=headers)
                
            res = make_openai_request(model or "gpt-4o")
            
            # Handle fake models in database (like GPT-5.3) by retrying with gpt-4o-mini
            if res.status_code == 404:
                error_data = res.json()
                if error_data.get("error", {}).get("code") == "model_not_found":
                    print(f"Warning: Model '{model}' not found. Retrying with 'gpt-4o-mini'...")
                    res = make_openai_request("gpt-4o-mini")
            
            if not res.ok:
                print(f"OpenAI Error: {res.text}")
            res.raise_for_status()
            ai_output = res.json()["choices"][0]["message"]["content"].strip()
            
        elif provider in ["claude", "anthropic"]:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": api_key, 
                "anthropic-version": "2023-06-01", 
                "content-type": "application/json"
            }
            payload = {
                "model": model or "claude-3-5-sonnet-20240620",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": f"Here is the full interview transcript:\n\n{transcript}"}
                ],
                "temperature": 0.1
            }
            res = requests.post(url, json=payload, headers=headers)
            if not res.ok:
                print(f"Anthropic Error: {res.text}")
            res.raise_for_status()
            ai_output = res.json()["content"][0]["text"].strip()
            
        elif provider in ["gemini", "google"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or 'gemini-1.5-pro'}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "system_instruction": {
                    "parts": [{"text": system_prompt}]
                },
                "contents": [{
                    "parts": [{"text": f"Here is the full interview transcript:\n\n{transcript}"}]
                }],
                "generationConfig": {"temperature": 0.1}
            }
            res = requests.post(url, json=payload, headers=headers)
            if not res.ok:
                print(f"Gemini Error: {res.text}")
            res.raise_for_status()
            ai_output = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            
        else:
            # Fallback to openai-compatible endpoint
            url = "https://api.openai.com/v1/chat/completions" 
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            payload = {
                "model": model or "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Here is the full interview transcript:\n\n{transcript}"}
                ],
                "temperature": 0.1
            }
            res = requests.post(url, json=payload, headers=headers)
            if not res.ok:
                print(f"Fallback Provider Error: {res.text}")
            res.raise_for_status()
            ai_output = res.json()["choices"][0]["message"]["content"].strip()
        
        # Remove <think> tags if the model outputs internal reasoning
        ai_output = re.sub(r'<think>.*?</think>', '', ai_output, flags=re.DOTALL).strip()
        
        if ai_output and "NO_QUESTIONS_FOUND" not in ai_output:
            return ai_output
        else:
            return "NO_QUESTIONS_FOUND"
            
    except Exception as e:
        print(f"LLM API Error: {e}")
        return "NO_QUESTIONS_FOUND"

def update_interview_qa(token, row_id, qa_text):
    """Update the interview record in the database with the generated Q&A."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    update_url = f"{WBL_API_BASE_URL}/interviews/{row_id}"
    
    # We use q_a to match the database schema
    updates = {
        "q_a": qa_text
    }
    
    try:
        response = requests.put(update_url, json=updates, headers=headers)
        response.raise_for_status()
        print(f"✅ Successfully updated q_a for row {row_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to update q_a for row {row_id}: {e}")
        return False

def process_qa_jobs():
    print("=== QA Generation Script Started ===")
    token = login()
    if not token:
        return
        
    # Fetch API keys and create a round-robin cycler
    api_keys = fetch_api_keys(token)
    if not api_keys:
        print("No API keys available for processing. Exiting.")
        return
        
    print(f"Loaded {len(api_keys)} API keys for round-robin rotation.")
    key_cycler = itertools.cycle(api_keys)
        
    interviews = fetch_interviews(token)
    processed_count = 0
    
    for interview in interviews:
        row_id = interview.get("id")
        transcript_link = interview.get("transcript") # Pulling from the transcript column
        existing_qa = interview.get("q_a") # Checking if it already has QA
        
        # If there is a transcript link AND no q_a has been generated yet
        if transcript_link and not existing_qa:
            print(f"\n--- Processing Interview {row_id} ---")
            
            # 1. Download Transcript
            transcript_text = download_transcript(transcript_link)
            if not transcript_text:
                continue
                
            # 2. Generate QA with LLM using the next API key in the round-robin sequence
            current_api_key = next(key_cycler)
            qa_result = generate_qa_with_llm(transcript_text, current_api_key)
            if not qa_result:
                continue
                
            # 3. Update the Database
            success = update_interview_qa(token, row_id, qa_result)
            if success:
                processed_count += 1
                
            # Small delay to ensure the local server doesn't get overloaded
            time.sleep(2)
            
    print(f"\n=== QA Generation Complete. Processed {processed_count} files. ===")

if __name__ == "__main__":
    process_qa_jobs()
