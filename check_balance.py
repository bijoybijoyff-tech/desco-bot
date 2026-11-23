import os, sys, json, requests
from pathlib import Path

BASE = "https://prepaid.desco.org.bd"
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
USER = os.environ["DESCO_USERNAME"]
PASSWORD = os.environ["DESCO_PASSWORD"]
ACCOUNT_ID = os.environ["DESCO_ACCOUNT_ID"]
LOW = float(os.environ.get("LOW_BALANCE", "100"))   # এর নিচে নামলে সতর্কবার্তা
STATE = Path("state.json")

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
    s.get(f"{BASE}/login", timeout=30)
    xsrf = s.cookies.get("XSRF-TOKEN")
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

def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}

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

    raw = find(data, ["balance", "currentBalance", "amount"])
    if raw is None:
        print(json.dumps(data, ensure_ascii=False)[:1500])
        raise RuntimeError("রেসপন্সে ব্যালান্স ফিল্ড পাওয়া যায়নি")
    balance = float(raw)
    snap = str(find(data, ["snapshotAt", "readingTime", "lastReading"]) or "")

    state = load_state()
    prev = state.get("balance")
    lines = [
        "⚡ DESCO প্রিপেইড ব্যালান্স",
        f"💰 ব্যালান্স: ৳{balance:.2f}",
        f"🕐 আপডেট: {snap or '-'}",
    ]

    if prev is not None:
        if state.get("snapshot") == snap:
            lines.append("ℹ️ নতুন স্ন্যাপশট আসেনি, খরচের হিসাব নেই")
        else:
            diff = round(prev - balance, 2)
            if diff >= 0:
                lines.append(f"📉 আগের রিডিং থেকে খরচ: ৳{diff:.2f}")
                if diff > 0:
                    lines.append(f"⏳ এই হারে প্রায় {int(balance // diff)} দিন চলবে")
            else:
                lines.append(f"🔋 ব্যালান্স ৳{-diff:.2f} বেড়েছে (সম্ভবত রিচার্জ), তাই খরচের হিসাব নেই")

    send("\n".join(lines))

    # আলাদা সতর্কবার্তা
    if balance < LOW:
        send(f"⚠️ সতর্কতা: ব্যালান্স মাত্র ৳{balance:.2f}। শীঘ্রই রিচার্জ করুন!")

    if state.get("snapshot") != snap:
        STATE.write_text(json.dumps({"balance": balance, "snapshot": snap}))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("ERROR:", e)
        send(f"❌ DESCO ব্যালান্স আনা যায়নি: {e}")
        sys.exit(1)
