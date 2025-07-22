import requests
import time

# === CONFIG ===
URL = "https://genesis-1-snd7.onrender.com/swagger"  # Replace with your endpoint
INTERVAL = 300  # in seconds (every 5 minutes)

def keep_alive():
    while True:
        try:
            response = requests.get(URL)
            print(f"[✓] Pinged {URL} — Status {response.status_code}")
        except Exception as e:
            print(f"[x] Failed to ping: {e}")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    keep_alive()
