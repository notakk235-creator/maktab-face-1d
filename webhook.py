from fastapi import FastAPI, Request
import pandas as pd
import requests
import json
import os
import datetime

app = FastAPI()

TOKEN = "8719042929:AAGkYoexkpMerPvdGRO7cscjdzIGsmxQULc"
CONFIG_FILE = "config.json"
LAST_STUDENT_FILE = "last_student.json"

def get_sheet_url():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return data.get("sheet_url")
        except:
            return None
    return None

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print("Telegram yuborishda xatolik:", e)

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        return {"status": "error", "message": "JSON o'qishda xatolik yuz berdi"}

    # Hikvision kabi turli terminallardan kelishi mumkin bo'lgan ID larni qidirish
    def find_id(data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k in ["employeeNoString", "id", "empNo", "userID", "ID"]:
                    return str(v)
                res = find_id(v)
                if res: return res
        elif isinstance(data, list):
            for item in data:
                res = find_id(item)
                if res: return res
        return None

    user_id = find_id(payload)
    
    if not user_id:
        return {"status": "error", "message": "Payload ichidan ID topilmadi"}

    sheet_url = get_sheet_url()
    if not sheet_url:
        return {"status": "error", "message": "Google Sheets manzili kiritilmagan. Iltimos Admin paneldan kiriting."}

    # CSV faylni internetdan o'qish
    try:
        df = pd.read_csv(sheet_url, dtype=str)
    except Exception as e:
        return {"status": "error", "message": f"CSV o'qishda xatolik: {e}"}

    if len(df.columns) < 4:
         return {"status": "error", "message": "Jadvalda yetarli ustunlar mavjud emas. Kamida 4 ta ustun kerak."}

    # Ustun nomlari har xil bo'lishi mumkinligi uchun aniqlashtiramiz (A: ID, B: Ism, C: Xabar, D: ChatID)
    df.columns = ["ID", "Ism", "Xabar", "ChatID"] + list(df.columns[4:])
    df["ID"] = df["ID"].astype(str).str.strip()

    # ID bo'yicha bazada qidirish
    match = df[df["ID"] == user_id]

    if match.empty:
        return {"status": "success", "message": f"O'quvchi jadvaldan topilmadi (ID: {user_id})"}

    row = match.iloc[0]
    name = str(row["Ism"])
    message_text = str(row["Xabar"])
    chat_id = str(row["ChatID"]).strip()

    # Streamlit paneli (Kiosk) uchun oxirgi o'quvchi ma'lumotini saqlash
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LAST_STUDENT_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "ID": user_id,
                "Ism": name,
                "time": now
            }, f, ensure_ascii=False)
    except Exception as e:
        print("Faylga saqlashda xatolik:", e)

    # Telegram xabar yuborish
    if pd.notna(chat_id) and chat_id != "" and chat_id.lower() != "nan":
        # Xabardagi {ism} ni amaldagi ismga almashtiramiz
        text = message_text.replace("{ism}", name).replace("{Ism}", name)
        send_telegram_message(chat_id, text)

    return {"status": "success", "message": "Jarayon muvaffaqiyatli bajarildi", "student": name}
