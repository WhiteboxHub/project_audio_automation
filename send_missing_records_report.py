import os
import smtplib
import requests
import pandas as pd
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from dotenv import load_dotenv
from fpdf import FPDF

# Load Environment Variables
load_dotenv()

WBL_API_BASE_URL = os.getenv("WBL_API_BASE_URL", "https://api.whitebox-learning.com/api")
WBL_EMAIL = os.getenv("WBL_EMAIL")
WBL_PASSWORD = os.getenv("WBL_PASSWORD")

# SMTP Configuration for Gmail App Passwords
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
REPORT_RECIPIENT_EMAILS = os.getenv("REPORT_RECIPIENT_EMAILS", "")

def login_wbl():
    login_url = f"{WBL_API_BASE_URL}/login"
    try:
        response = requests.post(login_url, data={"username": WBL_EMAIL, "password": WBL_PASSWORD})
        response.raise_for_status()
        return response.json().get("access_token") or response.json().get("token")
    except Exception as e:
        print(f"Failed to login to WBL API: {e}")
        return None

def fetch_interviews(token):
    interviews_url = f"{WBL_API_BASE_URL}/interviews"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = requests.get(interviews_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "data" in data:
            return data["data"]
        return data
    except Exception as e:
        print(f"Failed to fetch interviews: {e}")
        return []

class PDFReport(FPDF):
    def header(self):
        self.set_font("helvetica", "B", 14)
        self.cell(0, 10, "Missing Interview Recordings Report", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def draw_table(self, title, df):
        self.set_font("helvetica", "B", 12)
        self.cell(0, 8, f"{title} ({len(df)} records)", new_x="LMARGIN", new_y="NEXT")
        
        if df.empty:
            self.set_font("helvetica", "I", 10)
            self.cell(0, 8, "No missing records for this time period.", new_x="LMARGIN", new_y="NEXT")
            self.ln(5)
            return
            
        # Table Header
        self.set_font("helvetica", "B", 8)
        self.set_fill_color(0, 152, 121) # #009879
        self.set_text_color(255, 255, 255)
        
        # Column widths for Landscape A4 (297mm width -> ~277mm usable, minus margins)
        col_widths = [15, 25, 55, 30,30 , 110]
        headers = ["ID", "Date", "Candidate", "Type of Interview", "Mode of Interview", "Company"]
        
        for w, h in zip(col_widths, headers):
            self.cell(w, 7, h, border=1, fill=True, align="C")
        self.ln()
        
        # Table Body
        self.set_font("helvetica", "", 8)
        self.set_text_color(0, 0, 0)
        fill = False
        
        for _, row in df.iterrows():
            if fill:
                self.set_fill_color(243, 243, 243)
            else:
                self.set_fill_color(255, 255, 255)
                
            candidate_info = row.get("candidate") or {}
            # Truncate strings to fit the PDF columns nicely
            candidate_name = str(candidate_info.get("full_name", "Unknown"))[:30]
            
            raw_date = str(row.get("interview_date", ""))
            clean_date = raw_date.split('T')[0] if raw_date else "Unknown"
            
            comp = str(row.get("company", "Unknown"))[:80]
            
            self.cell(col_widths[0], 6, str(row.get("id", "")), border=1, fill=fill, align="C")
            self.cell(col_widths[1], 6, clean_date, border=1, fill=fill, align="C")
            self.cell(col_widths[2], 6, candidate_name, border=1, fill=fill)
            self.cell(col_widths[3], 6, str(row.get("type_of_interview", "Unknown"))[:15], border=1, fill=fill)
            self.cell(col_widths[4], 6, comp, border=1, fill=fill)
            self.cell(col_widths[5], 6, str(row.get("mode_of_interview", "Unknown"))[:15], border=1, fill=fill)
            self.ln()
            fill = not fill
            
        self.ln(6)

def main():
    print("Fetching data from WBL...")
    token = login_wbl()
    if not token: return
    interviews = fetch_interviews(token)
    if not interviews: return
    
    print("Processing data with Pandas...")
    df = pd.DataFrame(interviews)
    if df.empty: return
    
    # 1. Safely parse dates using Pandas to_datetime
    df['parsed_date'] = pd.to_datetime(df['interview_date'].astype(str).str.split('T').str[0], errors='coerce')
    
    # 2. Safely extract missing recordings (null or empty string)
    df['recording_link_str'] = df['recording_link'].fillna("").astype(str).str.strip()
    
    # 2.1 Safely extract mode of interview and filter out 'in person' (since they won't have recordings)
    df['mode_str'] = df.get('mode_of_interview', pd.Series(dtype=str)).fillna("").astype(str).str.lower().str.replace("-", " ").str.strip()
    
    missing_mask = (df['recording_link_str'] == "") & (~df['mode_str'].str.contains("in person", na=False))
    df_missing = df[missing_mask].copy()
    
    # 3. Calculate exactly when "Today", "7 Days Ago", and "1 Month Ago" are
    today = pd.Timestamp.now().normalize()
    date_7_days_ago = today - pd.Timedelta(days=7)
    date_1_month_ago = today - pd.DateOffset(months=1)
    
    # 4. INCLUSIVE Filtering
    # Bounded to today to ensure we don't accidentally flag future scheduled interviews
    mask_today = df_missing['parsed_date'] == today
    mask_last_7 = (df_missing['parsed_date'] >= date_7_days_ago) & (df_missing['parsed_date'] <= today)
    mask_last_month = (df_missing['parsed_date'] >= date_1_month_ago) & (df_missing['parsed_date'] <= today)
    
    df_today = df_missing[mask_today].sort_values('type_of_interview', ascending=False)
    df_7_days = df_missing[mask_last_7].sort_values('type_of_interview', ascending=False)
    df_month = df_missing[mask_last_month].sort_values('type_of_interview', ascending=False)
    
    print(f"   - Missing Today: {len(df_today)}")
    print(f"   - Missing Last 7 Days (Inclusive): {len(df_7_days)}")
    print(f"   - Missing Last Month (Inclusive): {len(df_month)}")
    
    # 5. Generate Landscape PDF
    print("Generating PDF Attachment...")
    pdf = PDFReport(orientation="L", unit="mm", format="A4")
    # Automatically add new pages if the tables get too long
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.draw_table("Missing from Today", df_today)
    pdf.draw_table("Missing from Last 7 Days (Inclusive)", df_7_days)
    pdf.draw_table("Missing from Last 1 Month (Inclusive)", df_month)
    
    pdf_filename = f"Missing_Recordings_{today.strftime('%Y-%m-%d')}.pdf"
    pdf.output(pdf_filename)
    print(f"PDF Saved locally as {pdf_filename}")
    
    # 6. Send Email via SMTP
    if not SMTP_EMAIL or not SMTP_PASSWORD or not REPORT_RECIPIENT_EMAILS:
        print("\nEmail credentials not fully configured in .env! Halting here.")
        return
        
    print("\nSending email via SMTP...")
    msg = MIMEMultipart()
    msg["Subject"] = f"Missing Recordings Report - {today.strftime('%Y-%m-%d')}"
    msg["From"] = SMTP_EMAIL
    
    recipients = [e.strip() for e in REPORT_RECIPIENT_EMAILS.split(',') if e.strip()]
    msg["To"] = ", ".join(recipients)
    
    # Simple email body referencing the PDF
    body = f"""
    Hello Kumar,
    
    Please look into this attached PDF report containing missing interview recordings.
    
    Summary:
    - Today: {len(df_today)} records
    - Last 7 Days: {len(df_7_days)} records 
    - Last 1 Month: {len(df_month)} records 
    
    Thank you.
    """
    msg.attach(MIMEText(body, "plain"))
    
    # Attach the PDF
    with open(pdf_filename, "rb") as f:
        pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
        pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
        msg.attach(pdf_attachment)
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_EMAIL, recipients, msg.as_string())
        server.quit()
        print(f"Successfully sent PDF report to {len(recipients)} recipients!")
    except Exception as e:
        print(f"Failed to send email via SMTP: {e}")

if __name__ == "__main__":
    main()
