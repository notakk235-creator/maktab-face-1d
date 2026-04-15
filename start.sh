#!/bin/bash
# Railway server da 8000 port FastAPI ga beriladi (Backend Webhook)
# 8501 port Streamlit ga beriladi (Frontend)
# E'tibor bering: Railway standart sozlamalarda faqat bitta public port beradi ($PORT).
# Agar /webhook ishlashi zarur bo'lsa, u kutilgan asosiy port bo'lishi kerak.
uvicorn webhook:app --host 0.0.0.0 --port $PORT &
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
