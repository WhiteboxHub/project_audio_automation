import os
import json
import time
import io
from google.colab import drive, auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 1. Mount & Auth
drive.mount('/content/drive', force_remount=True)
auth.authenticate_user()
drive_service = build('drive', 'v3')

# 2. Config
BASE_PATH = "/content/drive/MyDrive/Audio_automation"
AUDIO_FOLDER_PATH = "/content/drive/MyDrive/Audio_Folder"
JOB_FILE = os.path.join(BASE_PATH, "pending_jobs.json")
RESULT_FILE = os.path.join(BASE_PATH, "completed_jobs.json")

def process_file(task):
    row_id = task['row_id']
    video_id = task['video_file_id']
    output_filename = f"Audio_Rec_{row_id}.mp3"
    temp_video = f"/content/temp_{row_id}.mp4"
    output_path = os.path.join(AUDIO_FOLDER_PATH, output_filename)

    try:
        # Step A: Download the file directly (Bypasses all Mount issues)
        print(f" Downloading Row {row_id} (ID: {video_id})...")
        request = drive_service.files().get_media(fileId=video_id)
        fh = io.FileIO(temp_video, 'wb')
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.close()

        # Step B: Convert
        print(f" Converting Row {row_id}...")
        cmd = f'ffmpeg -i "{temp_video}" -vn -acodec libmp3lame -q:a 4 -ar 44100 -y -loglevel error "{output_path}"'
        
        if os.system(cmd) == 0:
            time.sleep(2)
            # Step C: Get Link
            search = drive_service.files().list(q=f"name='{output_filename}'", fields="files(id, webViewLink)").execute()
            files = search.get('files', [])
            link = files[0].get('webViewLink') if files else "Link Pending Sync"
            
            # Cleanup
            if os.path.exists(temp_video): os.remove(temp_video)
            return {"row_id": row_id, "status": "success", "audio_drive_link": link}
        else:
            if os.path.exists(temp_video): os.remove(temp_video)
            return {"row_id": row_id, "status": "failed", "error": "FFmpeg conversion failed"}

    except Exception as e:
        if "404" in str(e):
            print(f"⚠️ Row {row_id}: File not found in Drive (Deleted).")
        else:
            print(f"⚠️ Row {row_id} Error: {e}")
        return {"row_id": row_id, "status": "failed", "error": str(e)}

def process_batch():
    if not os.path.exists(JOB_FILE):
        print(" No pending_jobs.json found.")
        return

    with open(JOB_FILE, 'r') as f:
        tasks = json.load(f)

    results = []
    for task in tasks:
        result = process_file(task)
        if result["status"] == "success":
            print(f" Row {task['row_id']} Complete")
            results.append(result)
        else:
            print(f" Row {task['row_id']} Failed")

    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=4)
    
    if os.path.exists(JOB_FILE): os.remove(JOB_FILE)
    print(" Batch complete.")

if __name__ == "__main__":
    process_batch()