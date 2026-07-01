import os, requests, pandas as pd
from dotenv import load_dotenv

load_dotenv()
url = os.getenv('WBL_API_BASE_URL')

# Login
login_res = requests.post(f"{url}/login", data={'username': os.getenv('WBL_EMAIL'), 'password': os.getenv('WBL_PASSWORD')}).json()
token = login_res.get('token') or login_res.get('access_token')

# Fetch
res = requests.get(f"{url}/interviews", headers={'Authorization': f'Bearer {token}'}).json()
data = res.get('data', res)
df = pd.DataFrame(data)

# Find trash
mask = df['audio_link'].fillna('').astype(str).str.startswith('ERROR:')
bad_rows = df[mask]
print(f'Found {len(bad_rows)} rows to clean.')


# Clean
for _, r in bad_rows.iterrows():
    print(f"Cleaning row {r['id']}")
    requests.put(f"{url}/interviews/{r['id']}", json={'audio_link': ''}, headers={'Authorization': f'Bearer {token}'})
print('Done cleaning!')
