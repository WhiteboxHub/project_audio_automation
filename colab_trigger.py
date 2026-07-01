import os
import time
import subprocess
import pyautogui
from dotenv import load_dotenv

# Load Environment Variables from .env file
load_dotenv()

COLAB_URL = os.getenv("COLAB_URL")
CHROME_PROFILE_NAME = os.getenv("CHROME_PROFILE_NAME", "Default")

def run_browser_bot():
    """Launch Chrome natively, press Ctrl+F9 to trigger Colab, wait, then close."""
    print("===========================================")
    print("         Colab Local Trigger Bot           ")
    print("===========================================")
    print("🚀 Firing up Chrome...")
    
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    
    if not os.path.exists(chrome_path):
        print(f"❌ Error: Could not find Google Chrome installed at {chrome_path}")
        return False

    if not COLAB_URL:
        print("❌ Error: COLAB_URL not found in .env file.")
        return False

    print("Booting Chrome natively...")
    try:
        # Force close all existing Chromes first to ensure a clean window pops up
        os.system("taskkill /f /im chrome.exe >nul 2>&1")
        time.sleep(2)
        
        # Start Chrome, opening straight to Colab
        proc = subprocess.Popen([
            chrome_path,
            "--start-maximized",
            f"--profile-directory={CHROME_PROFILE_NAME}",
            COLAB_URL
        ])
    except Exception as e:
        print(f"⚠️ Failed to launch Chrome process: {e}")
        return False
        
    print("⏳ Waiting 18 seconds for the Google Colab UI to fully load on screen...")
    time.sleep(18)
    
    # Force focus by clicking the middle of the screen
    try:
        width, height = pyautogui.size()
        pyautogui.click(width / 2, height / 2)
        time.sleep(1)
    except:
        pass
    
    print("⌨️ Simulating 'Ctrl + F9' (Run All)...")
    pyautogui.hotkey('ctrl', 'f9')
    time.sleep(2)
    
    print("⌨️ Simulating 'Ctrl + Enter' (Run Selected Cell) just in case F9 was blocked...")
    pyautogui.hotkey('ctrl', 'enter')
    
    # Handle the "Run anyway" warning popup from Google
    time.sleep(3)
    print("⌨️ Pressing 'Enter' just in case a warning popup appeared...")
    pyautogui.press('enter')
    
    print("✅ Colab is running!")
    
    # The Colab script has its own internal timeout of 115 minutes.
    # We will wait 120 minutes here (7200 seconds) to ensure Colab has enough time to finish.
    print("⏳ Waiting 2 hours for Colab to finish converting all jobs...")
    time.sleep(7200)
    
    print("🧹 Time's up! Closing the Chrome tab...")
    # Make sure we focus the screen one more time just in case
    try:
        pyautogui.click(width / 2, height / 2)
        time.sleep(1)
    except:
        pass
    
    # Close tab
    pyautogui.hotkey('ctrl', 'w')
    print("✅ Finished clean up. Script complete!")
    return True

if __name__ == "__main__":
    run_browser_bot()
