import streamlit as st
import json
import os
import time

st.set_page_config(page_title="Face ID Admin Panel", page_icon="👤", layout="wide")

CONFIG_FILE = "config.json"
LAST_STUDENT_FILE = "last_student.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            return {"sheet_url": ""}
    return {"sheet_url": ""}

def save_config(sheet_url):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"sheet_url": sheet_url}, f)

def load_last_student():
    if os.path.exists(LAST_STUDENT_FILE):
        try:
            with open(LAST_STUDENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return None
    return None

config = load_config()

if "kiosk_mode" not in st.session_state:
    st.session_state.kiosk_mode = False

if st.session_state.kiosk_mode:
    # KIOSK MODE UI
    # Provide an exit button at the top right
    col1, col2 = st.columns([9, 1])
    with col2:
        if st.button("❌ Chiqish"):
            st.session_state.kiosk_mode = False
            st.rerun()
            
    st.markdown("<h1 style='text-align: center; font-size: 50px;'>Maktab Face ID Tizimi</h1>", unsafe_allow_html=True)
    
    student = load_last_student()
    if student:
        st.markdown(f"""
        <div style='text-align: center; padding: 60px; background-color: #262730; border-radius: 20px; border: 3px solid #4CAF50; margin-top: 50px; box-shadow: 0px 4px 15px rgba(0,0,0,0.5);'>
            <h1 style='font-size: 90px; color: #4CAF50; margin-bottom: 20px;'>{student.get('Ism', 'Nomalum')}</h1>
            <p style='font-size: 45px; color: #E0E0E0;'>ID: {student.get('ID', '')}</p>
            <p style='font-size: 35px; color: #888888;'>Qayd etilgan vaqt: {student.get('time', '')}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='text-align: center; margin-top: 150px;'>
            <h2 style='font-size: 50px; color: #888;'>Hozircha ma'lumot yo'q, o'quvchi kutilmoqda...</h2>
        </div>
        """, unsafe_allow_html=True)

    # Auto-refresh every 2 seconds
    time.sleep(2)
    st.rerun()

else:
    # ADMIN PANEL UI
    st.title("⚙️ Face ID - Boshqaruv Paneli")
    st.write("Bu yerda terminal ulangan Google Sheets jadval linkini kiritishingiz mumkin.")
    
    with st.form("config_form"):
        st.subheader("📊 Google Sheets Sozlamalari")
        st.markdown("""
        **Eslatma:** Google Sheets hammaga ochiq (public) bo'lishi va URL oxiri `/export?format=csv` bilan tugashi kerak.
        Jadval strukturasi quyidagi tartibda bo'lishi shart:
        - **A ustun**: O'quvchi ID raqami
        - **B ustun**: F.I.O (Ism)
        - **C ustun**: Xabar (Masalan: _Farzandingiz {ism} maktabga yetib keldi_)
        - **D ustun**: ChatID (Telegram foydalanuvchi ID si)
        """)
        sheet_url = st.text_input("CSV Export Linkni kiriting (Masalan: https://docs.google.com/.../export?format=csv)", value=config.get("sheet_url", ""))
        submitted = st.form_submit_button("✅ Saqlash va Qo'llash")
        
        if submitted:
            if sheet_url.strip():
                save_config(sheet_url.strip())
                st.success("Sozlamalar muvaffaqiyatli saqlandi!")
            else:
                st.error("Iltimos, linkni kiriting.")

    st.markdown("---")
    st.subheader("🖥 Kiosk Rejimi")
    st.write("Barcha o'zgarishlarni terminal ekranida to'liq interfeysda ko'rsatish uchun Kiosk rejimiga o'ting.")
    res = st.button("🚀 Kiosk rejimini yoqish (Full Screen)")
    if res:
        st.session_state.kiosk_mode = True
        st.rerun()
