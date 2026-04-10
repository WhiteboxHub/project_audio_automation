# Video-to-Audio FFmpeg Conversion Pipeline (Colab + FastApi)

This pipeline automatically searches your backend database for new video interviews, queues them up via Google Drive, instructs a Google Colab notebook to convert them to MP3 files (using Google's free cloud computing), and pushes the new shareable Google Drive audio links back to your API.

---

## 🏗️ Architecture

1. **`master_orchestrator.py` (The Controller)**  
   An infinite-loop, crash-proof state machine designed to run fixed on a server or local machine. It fetches jobs from your backend, queues `pending_jobs.json`, triggers the Colab notebook via headless browser automation, waits for completion, and updates your API.
   
2. **`colab_script_template.py` (The Muscle)**  
   A script you paste into Google Colab. It mounts your Google Drive, uses FFmpeg to efficiently convert videos directly from Google Drive shortcut IDs, changes the permissions to "Anyone with the link can view", and leaves a `completed_jobs.json` receipt.

3. **Google Drive Desktop (The Bridge)**  
   By saving `.json` files to your Desktop's mapped Drive folder, the Orchestrator instantly syncs data to the cloud where Colab picks it up.

---

## 🛠️ Step 1: Pre-Requisites

1. **Google Drive Desktop:** Install Google Drive Desktop on the machine running the orchestrator. Ensure it is logged into the **same Google Account** that you use on Google Colab and that stores the recording files.
2. **Python:** Ensure Python 3.10+ is installed.
3. **Chrome Profile Data:** If deploying to a remote server, copy your existing local Chrome `User Data` folder from your PC to the server. This prevents captchas and skips manual Google logins for the automation bot.

---

## 📦 Step 2: Installation

1. Open your terminal in the project directory.
2. Install the necessary Python packages:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Copy `.env.example` to `.env`.

---

## ⚙️ Step 3: Configuration (`.env`)

Fill out your `.env` file with the exact paths:

- `WBL_API_BASE_URL`: Your FastAPI backend URL (e.g., `https://api.example.com/api`)
- `WBL_EMAIL` / `WBL_PASSWORD`: Your Admin credentials for the backend.
- `DRIVE_AUTOMATION_FOLDER`: The local system path to your Google Drive Desktop sync folder (e.g., `G:\My Drive\Automation`).
- `COLAB_URL`: The direct, shareable URL to your Colab notebook.
- `CHROME_USER_DATA_DIR`: The absolute path to your copied Chrome user data folder (e.g., `C:\Copied_User_Data`).

---

## 🚀 Step 4: Setting up Google Colab

1. Go to Google Colab and create a new notebook.
2. Copy all code from `colab_script_template.py` and paste it into the cell.
3. The very first time you run it, Colab will pop up a window asking you to authenticate with the Google Drive API. Validate the permissions.
4. Leave it! Your orchestrator will handle clicking "Run" from now on.

---

## 🏃 Step 5: Running the Orchestrator

Run the master script:

```bash
python master_orchestrator.py
```

**How it behaves (Fixed Time Mode):**
- It checks the API for new interviews needing conversion.
- If it finds zero interviews, it sleeps for 1 hour to save CPU.
- If it finds interviews, it writes the queue, wakes up your Chrome profile to push "Run All" on Colab, and monitors the Drive folder.
- Once Colab is finished (and deletes the pending file), the Orchestrator updates your database and waits again. 
- If the system crashes mid-process, resetting the script automatically recovers where it left off.
