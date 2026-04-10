import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()

# We will store the Chrome Profile right in our project folder so it doesn't 
# conflict with your regular open Chrome browser!
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROME_PROFILE_DIR = os.path.join(PROJECT_DIR, "Colab_Chrome_Profile")

COLAB_URL = os.getenv("COLAB_URL")

def run_colab_automation():
    if not COLAB_URL:
        print("Error: COLAB_URL is not set in your .env file!")
        return

    print("🚀 Launching Headed Browser Automation...")
    with sync_playwright() as p:
        # Use a persistent context so it remembers your Google Login
        # We use channel="chrome" so it just grabs your installed Google Chrome.
        context = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE_DIR,
            headless=False,
            channel="chrome",
            args=["--start-maximized"]
        )
        
        # The persistent context usually spawns a blank page
        page = context.pages[0]
        
        print(f"🌍 Navigating directly to Colab Notebook...")
        page.goto(COLAB_URL, timeout=60000)
        
        # 1. CHECK FOR LOGIN
        print("Checking if we need to log in...")
        time.sleep(5)
        # A simple check: if the URL redirected to accounts.google.com, we aren't logged in.
        if "accounts.google.com" in page.url or page.locator("text=Sign in").is_visible():
            print("==================================================================")
            print("🚨 YOU NEED TO LOG IN! 🚨")
            print("Please log in to your Google Account in the browser window.")
            print("Once you are logged in and see the Colab notebook, the script will continue.")
            print("Waiting for up to 5 minutes...")
            print("==================================================================")
            
            # Wait for the url to return to colab
            page.wait_for_url("**/colab.research.google.com/**", timeout=300000)
            print("Login detected! Proceeding...")
        
        print("⏳ Waiting for Colab UI to fully load...")
        page.wait_for_load_state("networkidle", timeout=60000)
        time.sleep(5)  # Extra buffer for Colab's heavy JS
        
        print("⌨️ Pressing 'Ctrl + F9' to Run All...")
        page.keyboard.press("Control+F9")
        
        print("👀 Watching for 'Run anyway' warning popup...")
        try:
            # Look for a button containing the text "Run anyway"
            run_anyway = page.locator("button:has-text('Run anyway')")
            run_anyway.wait_for(timeout=8000, state="visible")
            if run_anyway.is_visible():
                print("Popup detected! Clicking 'Run anyway'...")
                run_anyway.click()
        except:
            print("No warning popup appeared, moving on!")

        print("✅ The Colab notebook has been triggered!")
        print("Closing the automation browser in 10 seconds. Colab will continue to run as long as the tab lived or the local brain waits, wait actually we should leave it open!")
        
        # CRITICAL: We need the browser to stay open so Colab continues processing!
        # Instead of closing, we will monitor the local Drive sync folder for the completed_jobs.json
        AUTOMATION_FOLDER = os.getenv("DRIVE_AUTOMATION_FOLDER", r"G:\My Drive\Automation")
        RESULT_FILE = os.path.join(AUTOMATION_FOLDER, "completed_jobs.json")
        
        print(f"🕵️‍♂️ Monitoring {AUTOMATION_FOLDER} for completion...")
        print("Feel free to minimize the browser, it will close automatically when done.")
        
        # Wait until the file appears
        timeout = 60 * 60  # Wait up to 1 hour
        poll_interval = 5
        elapsed = 0
        while elapsed < timeout:
            if os.path.exists(RESULT_FILE):
                print(f"🎉 completed_jobs.json detected! Colab finished its job!")
                time.sleep(5) # Let google drive fully sync the file
                break
            time.sleep(poll_interval)
            elapsed += poll_interval
            
        print("Browser closing...")
        context.close()

if __name__ == "__main__":
    run_colab_automation()
