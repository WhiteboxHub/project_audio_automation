import os
import json
import time
from google.colab import drive, auth
from googleapiclient.discovery import build

# 1. Mount Drive
drive.mount('/content/drive', force_remount=True)
auth.authenticate_user()
drive_service = build('drive', 'v3')

# 2. Config - MUST MATCH YOUR ORCHESTRATOR

BASE_PATH = "/content/drive/MyDrive/Audio_automation"
VIDEO_FOLDERS = [
    "/content/drive/MyDrive/Interview Recordings",
    "/content/drive/MyDrive/Meet Recordings"
]
AUDIO_FOLDER_PATH = "/content/drive/MyDrive/Audio_Folder"

JOB_FILE = os.path.join(BASE_PATH, "pending_jobs.json")
RESULT_FILE = os.path.join(BASE_PATH, "completed_jobs.json")

def find_file_path(video_id):
    """Uses API to get the name, then searches folders for the real mount path."""
    try:
        meta = drive_service.files().get(fileId=video_id, fields="name").execute()
        name = meta.get('name')

        # Check each folder for the file
        for folder in VIDEO_FOLDERS:
            # We check for the name exactly as it appears in the Drive Mount
            for root, dirs, files in os.walk(folder):
                if name in files:
                    return os.path.join(root, name)
        return None
    except Exception as e:
        print(f"Lookup error: {e}")
        return None

def process_batch():
    if not os.path.exists(JOB_FILE):
        print("No pending_jobs.json found.")
        return

    with open(JOB_FILE, 'r') as f:
        tasks = json.load(f)

    results = []
    print(f"🎬 Processing {len(tasks)} files via Mount...")

    for task in tasks:
        row_id = task['row_id']
        video_id = task['video_file_id']
        output_filename = f"Audio_Rec_{row_id}.mp3"
        output_path = os.path.join(AUDIO_FOLDER_PATH, output_filename)

        # Step A: Find the actual path on the mount
        input_path = find_file_path(video_id)

        if not input_path:
            # Fallback to shortcut ID if walk fails
            input_path = f"/content/drive/MyDrive/.shortcut-targets-by-id/{video_id}"

        if os.path.exists(input_path):
            print(f"✅ Found: {input_path}")
            # Step B: Convert
            cmd = f'ffmpeg -i "{input_path}" -vn -acodec libmp3lame -b:a 128k -ar 44100 -y -loglevel error "{output_path}"'

            if os.system(cmd) == 0:
                time.sleep(2)
                # Step C: Get restricted link
                search = drive_service.files().list(
                    q=f"name='{output_filename}'", fields="files(id, webViewLink)"
                ).execute()
                files = search.get('files', [])
                link = files[0].get('webViewLink') if files else "Link Pending Sync"

                results.append({"row_id": row_id, "status": "success", "audio_drive_link": link})
                print(f"✨ Row {row_id} Done")
            else:
                print(f"❌ FFmpeg failed for Row {row_id}")
        else:
            print(f"❌ Mount Path Not Found for Row {row_id}")

    # Finalize
    with open(RESULT_FILE, 'w') as f:
        json.dump(results, f, indent=4)

    if os.path.exists(JOB_FILE):
        os.remove(JOB_FILE)
    print("🏁 Batch complete.")

process_batch()