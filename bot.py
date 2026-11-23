import os, sys, json, requests

BASE = "https://prepaid.desco.org.bd"
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
USER = os.environ["DESCO_USERNAME"]
PASSWORD = os.environ["DESCO_PASSWORD"]
ACCOUNT_ID = os.environ["DESCO_ACCOUNT_ID"]

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36",
}

def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text},
        timeout=20,
    )

def desco_login():
    s = requests.Session()
    s.headers.update(HEADERS)
    # ১) সেশন ও XSRF কুকি নেওয়া
    s.get(f"{BASE}/login", timeout=30)
    xsrf = s.cookies.get("XSRF-TOKEN")
    # ২) লগইন
    r = s.post(
        f"{BASE}/api/auth/login",
        json={"username": USER, "password": PASSWORD},
        headers={
            "Content-Type": "application/json",
            "Origin": BASE,
            "Referer": f"{BASE}/login",
            "X-XSRF-TOKEN": xsrf or "",
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"লগইন ব্যর্থ (HTTP {r.status_code})")
    return s

def find(d, keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return None

def main():
    s = desco_login()
    r = s.get(
        f"{BASE}/api/accounts/{ACCOUNT_ID}/balance",
        headers={"Referer": f"{BASE}/dashboard"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        data = data["data"]

    balance = find(data, ["balance", "currentBalance", "amount"])
    if balance is None:
        # কী নামে ফিল্ড আছে দেখার জন্য (পাসওয়ার্ড/টোকেন এতে থাকে না)
        print(json.dumps(data, ensure_ascii=False)[:1500])
        raise RuntimeError("রেসপন্সে ব্যালান্স ফিল্ড পাওয়া যায়নি")

    snap = find(data, ["snapshotAt", "readingTime", "lastReading"]) or "-"
    send(
        "⚡ DESCO প্রিপেইড ব্যালান্স\n"
        f"💰 ব্যালান্স: ৳{balance}\n"
        f"🕐 আপডেট: {snap}"
    )

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e)
        send(f"❌ DESCO ব্যালান্স আনা যায়নি: {e}")
        sys.exit(1)
