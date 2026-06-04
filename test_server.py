
import subprocess
import time
import requests
import sys

print("Starting app.py...")
proc = subprocess.Popen([sys.executable, "app.py"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

time.sleep(5) # Wait for startup

try:
    print("Attempting to get /...")
    r = requests.get("http://127.0.0.1:8080/", timeout=5)
    print(f"Status Code: {r.status_code}")
    print(f"Response Body: {r.text[:500]}")
except Exception as e:
    print(f"Request failed: {e}")

# Kill the process
proc.terminate()
stdout, stderr = proc.communicate()
print("\n--- STDOUT ---")
print(stdout)
print("\n--- STDERR ---")
print(stderr)
