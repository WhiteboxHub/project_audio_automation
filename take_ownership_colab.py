import os
import json
import io
import requests
import time
from google.colab import drive, auth, userdata
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Paste the Google Drive Folder ID where you want the NEW files saved
# (You can get this from the URL when you open the folder in Drive)
TARGET_FOLDER_ID = "PASTE_YOUR_FOLDER_ID_HERE"

WBL_API_BASE_URL = "https://api.whitebox-learning.com/api"
JSON_FILE_PATH = "/content/drive/MyDrive/Audio_automation/not_owned_files.json"

# ==========================================
# 2. AUTHENTICATION
# ==========================================
print("Mounting Drive...")
drive.mount('/content/drive', force_remount=True)

print("Authenticating Google User...")
auth.authenticate_user()
drive_service = build('drive', 'v3')

print("Fetching WBL Secrets...")
WBL_EMAIL = userdata.get('WBL_EMAIL')
WBL_PASSWORD = userdata.get('WBL_PASSWORD')

def login_wbl():
    login_url = f"{WBL_API_BASE_URL}/login"
    try:
        response = requests.post(login_url, data={"username": WBL_EMAIL, "password": WBL_PASSWORD})
        response.raise_for_status()
        return response.json().get("access_token")
    except Exception as e:
        print(f"❌ Failed to login to WBL: {e}")
        return None

def update_db_link(token, row_id, file_type, new_link):
    update_url = f"{WBL_API_BASE_URL}/interviews/{row_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    # Decide which field to update
    updates = {}
    if file_type == "Audio":
        updates = {"audio_link": new_link}
    elif file_type == "Video":
        updates = {"recording_link": new_link}
        
    for attempt in range(3):
        try:
            response = requests.put(update_url, json=updates, headers=headers, timeout=60)
            response.raise_for_status()
            return True
        except Exception as e:
            time.sleep(3)
    return False

# ==========================================
# 3. PROCESSING
# ==========================================
def main():
    if not os.path.exists(JSON_FILE_PATH):
        print(f"❌ Cannot find {JSON_FILE_PATH}")
        print("Please make sure you moved the file to the Audio_automation folder!")
        return
        
    with open(JSON_FILE_PATH, 'r') as f:
        not_owned = json.load(f)
        
    print(f"📋 Found {len(not_owned)} files to clone and take ownership of.")
    
    token = login_wbl()
    if not token:
        return
        
    for index, task in enumerate(not_owned):
        row_id = task['interview_id']
        file_type = task['file_type']
        drive_id = task['drive_id']
        original_name = task['file_name']
        
        print(f"\n--- Processing {index+1}/{len(not_owned)}: Row {row_id} ({file_type}) ---")
        
        temp_file = f"/content/temp_download_{row_id}.tmp"
        
        try:
            # 1. DOWNLOAD
            print(f"📥 Downloading {original_name}...")
            request = drive_service.files().get_media(fileId=drive_id)
            fh = io.FileIO(temp_file, 'wb')
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.close()
            
            # 2. UPLOAD (Takes ownership)
            print("📤 Uploading as New Owner...")
            file_metadata = {
                'name': original_name,
                'parents': [TARGET_FOLDER_ID] if TARGET_FOLDER_ID and TARGET_FOLDER_ID != "PASTE_YOUR_FOLDER_ID_HERE" else []
            }
            media = MediaFileUpload(temp_file, resumable=True)
            
            uploaded_file = drive_service.files().create(
                body=file_metadata, 
                media_body=media, 
                fields='id, webViewLink'
            ).execute()
            
            new_drive_id = uploaded_file.get('id')
            new_link = uploaded_file.get('webViewLink')
            
            # Since you requested RESTRICTED permissions, we intentionally skip creating any 'anyone' or 'domain' permission links.
            # Google Drive defaults newly uploaded files to Restricted (Only the owner can view).
            
            # 3. UPDATE DATABASE
            print(f"🔗 Updating DB with new link...")
            if update_db_link(token, row_id, file_type, new_link):
                print("✅ Database successfully updated!")
            else:
                print("❌ Failed to update Database.")
                
            # 4. CLEANUP
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
        except Exception as e:
            print(f"⚠️ Error processing row {row_id}: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

if __name__ == "__main__":
    main()
