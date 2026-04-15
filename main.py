from fastapi import FastAPI, Request, Form, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd
import requests
import json
import os
import shutil
import datetime
import asyncio
from typing import Optional

app = FastAPI()

# Static files for student photos
PHOTOS_DIR = "photos"
os.makedirs(PHOTOS_DIR, exist_ok=True)

app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
templates = Jinja2Templates(directory="templates")

CONFIG_FILE = "config.json"
LAST_STUDENT_FILE = "last_student.json"

# ─────────────────────── Models ───────────────────────
class Settings(BaseModel):
    sheet_url: str
    telegram_token: Optional[str] = None

class DeviceAction(BaseModel):
    ip: str
    port: Optional[int] = 80
    username: Optional[str] = "admin"
    password: Optional[str] = "admin"

class StudentUpdate(BaseModel):
    ID: str
    Ism: str
    Xabar: Optional[str] = ""
    ChatID: Optional[str] = ""

# ─────────────────────── Helpers ────────────────────────
def format_sheet_url(url: str) -> str:
    """Google Sheets havolasini CSV export formatiga o'tkazadi"""
    url = url.strip()
    if "/export?format=csv" in url:
        return url
    if "/edit" in url:
        base_url = url.split("/edit")[0]
        gid = "0"
        if "gid=" in url:
            gid = url.split("gid=")[1].split("&")[0].split("#")[0]
        return f"{base_url}/export?format=csv&gid={gid}"
    if "spreadsheets/d/" in url:
        # URL faqat spreadsheet ID bilan keladigan holat
        base_url = url.rstrip("/")
        return f"{base_url}/export?format=csv&gid=0"
    return url

def get_config():
    default = {
        "sheet_url": "",
        "original_url": "",
        "telegram_token": ""
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            for k, v in default.items():
                if k not in config:
                    config[k] = v
            return config
        except:
            return default
    return default

def save_config(url: str, token: Optional[str] = None):
    formatted_url = format_sheet_url(url)
    config = get_config()
    config["sheet_url"] = formatted_url
    config["original_url"] = url
    if token is not None:
        config["telegram_token"] = token
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config

def load_last_student():
    if os.path.exists(LAST_STUDENT_FILE):
        try:
            with open(LAST_STUDENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def fetch_sheet_df():
    """Google Sheets dan DataFrame ga o'qish - Yanada mustahkamroq versiya"""
    config = get_config()
    sheet_url = config.get("sheet_url", "")
    if not sheet_url:
        raise ValueError("Google Sheets URL kiritilmagan")
    
    # URL formatni tekshirish va tuzatish
    if "docs.google.com" in sheet_url and "/export" not in sheet_url:
        sheet_url = format_sheet_url(sheet_url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/csv,*/*"
    }
    
    try:
        response = requests.get(sheet_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        from io import StringIO
        # UTF-8 bilan o'qishga harakat qilamiz
        content = response.content.decode('utf-8')
        df = pd.read_csv(StringIO(content), dtype=str)
        
        if len(df.columns) < 2:
            # Balki format boshqachadir?
            raise ValueError("Jadvalda ustunlar yetarli emas (kamida ID va Ism kerak)")
        
        # Ustun nomlarini qat'iy o'rnatish
        new_columns = ["ID", "Ism", "Xabar", "ChatID"]
        # Faqat mavjud ustunlarni rename qilamiz
        mapping = {df.columns[i]: new_columns[i] for i in range(min(len(df.columns), len(new_columns)))}
        df.rename(columns=mapping, inplace=True)
        
        df["ID"] = df["ID"].astype(str).str.strip()
        df["Ism"] = df["Ism"].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"Sheets Fetch Error: {e}")
        # Agar requests fail bo'lsa, pandas read_csv ni to'g'ridan-to'g'ri sinab ko'ramiz
        try:
            df = pd.read_csv(sheet_url, dtype=str)
            new_columns = ["ID", "Ism", "Xabar", "ChatID"]
            mapping = {df.columns[i]: new_columns[i] for i in range(min(len(df.columns), len(new_columns)))}
            df.rename(columns=mapping, inplace=True)
            df["ID"] = df["ID"].astype(str).str.strip()
            df["Ism"] = df["Ism"].astype(str).str.strip()
            return df
        except:
            raise e

def send_telegram_message(chat_id, text):
    config = get_config()
    token = config.get("telegram_token", "")
    if not token:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=5)
    except Exception as e:
        print("Telegram xatosi:", e)

def hikvision_get_device_info(ip: str, port: int, username: str, password: str):
    """Hikvision qurilmasidan ma'lumot olish (HTTP ISAPI)"""
    url = f"http://{ip}:{port}/ISAPI/System/deviceInfo"
    try:
        # Digest auth Hikvision uchun standart
        from requests.auth import HTTPDigestAuth
        resp = requests.get(url, auth=HTTPDigestAuth(username, password), timeout=3)
        if resp.ok:
            import xmltodict
            data = xmltodict.parse(resp.text)
            info = data.get("DeviceInfo", {})
            return {
                "status": "online",
                "model": info.get("model", "Noma'lum"),
                "serialNumber": info.get("serialNumber", ""),
                "firmwareVersion": info.get("firmwareVersion", ""),
                "ip": ip,
                "port": port
            }
        else:
            return {"status": "error", "message": f"HTTP {resp.status_code}", "ip": ip}
    except Exception as e:
        return {"status": "offline", "message": str(e), "ip": ip}

def get_student_photo_url(student_id: str) -> Optional[str]:
    # Kengaytmalarni tekshirish
    for ext in ["jpg", "jpeg", "png", "JPG", "PNG"]:
        path = os.path.join(PHOTOS_DIR, f"{student_id}.{ext}")
        if os.path.exists(path):
            return f"/photos/{student_id}.{ext}?v={int(datetime.datetime.now().timestamp())}"
    return None

# ─────────────────────── Routes ─────────────────────────

@app.get("/", response_class=HTMLResponse)
async def admin_panel(request: Request):
    config = get_config()
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "sheet_url": config.get("original_url", ""),
        "telegram_token": config.get("telegram_token", "")
    })

@app.post("/save_settings")
async def save_settings(settings: Settings):
    try:
        config = save_config(settings.sheet_url, settings.telegram_token)
        return {"status": "success", "config": config}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ─── Student Search & CRUD ───
@app.get("/api/students")
async def get_all_students(query: Optional[str] = None):
    try:
        df = fetch_sheet_df()
        if query and query.strip():
            q = query.strip()
            mask = (
                df["ID"].str.contains(q, case=False, na=False) |
                df["Ism"].str.contains(q, case=False, na=False)
            )
            df = df[mask]
        
        records = df.head(100).to_dict(orient="records")
        for r in records:
            r["photo"] = get_student_photo_url(str(r.get("ID", "")))
        return {"status": "success", "students": records}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/search")
async def search_students(query: str = Query(...)):
    try:
        df = fetch_sheet_df()
        q = query.strip()
        if not q:
            return []
        mask = (
            df["ID"].str.contains(q, case=False, na=False) |
            df["Ism"].str.contains(q, case=False, na=False)
        )
        results = df[mask].head(15).to_dict(orient="records")
        for r in results:
            r["photo"] = get_student_photo_url(str(r.get("ID", "")))
        return results
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/student/photo/{student_id}")
async def upload_student_photo(student_id: str, file: UploadFile = File(...)):
    """O'quvchi fotosuratini yuklash"""
    # Eski rasmlarni o'chirish
    for ext in ["jpg", "jpeg", "png"]:
        old = os.path.join(PHOTOS_DIR, f"{student_id}.{ext}")
        if os.path.exists(old):
            os.remove(old)
    
    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ["jpg", "jpeg", "png"]:
        return {"status": "error", "message": "Faqat JPG yoki PNG ruxsat etiladi"}
    
    save_name = f"{student_id}.{ext}"
    save_path = os.path.join(PHOTOS_DIR, save_name)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    return {"status": "success", "url": f"/photos/{save_name}"}

# ─── Hikvision Device Discovery & Management ───
@app.get("/api/discover")
async def api_discover():
    """SADP multicast qidirish (LAN kerak)"""
    import socket, uuid
    try:
        import xmltodict
    except ImportError:
        return {"status": "error", "message": "xmltodict not installed", "devices": []}
    
    probe = f'''<?xml version="1.0" encoding="utf-8"?>
    <Probe>
        <Uuid>{uuid.uuid4()}</Uuid>
        <Types>inquiry</Types>
    </Probe>'''
    
    devices = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.settimeout(2.0)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(probe.encode("utf-8"), ("239.255.255.250", 37020))
        while True:
            try:
                data, addr = sock.recvfrom(4096)
                try:
                    pm = xmltodict.parse(data).get("ProbeMatch", {})
                    devices.append({
                        "model": pm.get("DeviceDescription", "Hikvision"),
                        "ip": pm.get("IPv4Address", addr[0]),
                        "mac": pm.get("MAC", ""),
                        "port": pm.get("HttpPort", "80"),
                        "source": "sadp"
                    })
                except:
                    pass
            except socket.timeout:
                break
    except Exception as e:
        return {"status": "note", "message": f"SADP: {e}", "devices": devices}
    finally:
        try: sock.close()
        except: pass
    
    return {"status": "success", "devices": devices}

@app.post("/api/device/check")
async def check_device(device: DeviceAction):
    """IP orqali Hikvision qurilmasini tekshirish"""
    info = hikvision_get_device_info(device.ip, device.port, device.username, device.password)
    return info

@app.post("/api/device/scan_range")
async def scan_ip_range(data: dict):
    """IP oralig'ini skanerlash (masalan: 192.168.1.1-254)"""
    import xmltodict
    base_ip = data.get("base", "192.168.1")
    start = int(data.get("start", 1))
    end = int(data.get("end", 20))
    username = data.get("username", "admin")
    password = data.get("password", "admin")
    
    found = []
    
    async def check_one(ip):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, hikvision_get_device_info, ip, 80, username, password)
        if result.get("status") == "online":
            found.append(result)
    
    tasks = [check_one(f"{base_ip}.{i}") for i in range(start, end + 1)]
    await asyncio.gather(*tasks)
    
    return {"status": "success", "devices": found}

# ─── Kiosk & Webhook ───
@app.get("/kiosk", response_class=HTMLResponse)
async def kiosk_mode(request: Request):
    return templates.TemplateResponse("kiosk.html", {"request": request})

@app.get("/api/last_student")
async def api_last_student():
    return JSONResponse(content=load_last_student())

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        payload = await request.json()
        print("Webhook Payload:", payload)
    except Exception:
        body = await request.body()
        print("Raw body:", body)
        return {"status": "error", "message": "Yaroqsiz JSON format"}

    def find_id(data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k.lower() in ["employeenostring", "id", "empno", "userid", "user_id", "pin", "employeeid", "cardno"]:
                    return str(v).strip()
                res = find_id(v)
                if res:
                    return res
        elif isinstance(data, list):
            for item in data:
                res = find_id(item)
                if res:
                    return res
        return None

    user_id = find_id(payload)
    if not user_id:
        user_id = request.query_params.get("id") or request.query_params.get("userID")

    if not user_id:
        return {"status": "error", "message": "Payload ichida ID topilmadi", "received": payload}

    try:
        df = fetch_sheet_df()
        match = df[df["ID"] == user_id]
    except Exception as e:
        return {"status": "error", "message": f"Sheet xatolik: {e}"}

    if match.empty:
        # O'quvchi topilmadi — lekin kiosk ga noma'lum deb ko'rsatamiz
        unknown_data = {"ID": user_id, "Ism": "Noma'lum", "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        with open(LAST_STUDENT_FILE, "w", encoding="utf-8") as f:
            json.dump(unknown_data, f, ensure_ascii=False)
        return {"status": "success", "message": "O'quvchi bazada topilmadi", "id": user_id}

    row = match.iloc[0]
    name = str(row.get("Ism", "Noma'lum"))
    message_text = str(row.get("Xabar", ""))
    chat_id = str(row.get("ChatID", "")).strip()

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    student_data = {
        "ID": user_id,
        "Ism": name,
        "time": now,
        "photo": get_student_photo_url(user_id)
    }

    with open(LAST_STUDENT_FILE, "w", encoding="utf-8") as f:
        json.dump(student_data, f, ensure_ascii=False)

    if chat_id and chat_id.lower() not in ["", "nan"]:
        text = message_text.replace("{ism}", name).replace("{Ism}", name).replace("{ID}", user_id)
        send_telegram_message(chat_id, text)

    return {"status": "success", "student": name}
