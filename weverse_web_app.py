import streamlit as st
import json, time, re, os, requests, io, zipfile
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

# --- 頁面設定 ---
st.set_page_config(page_title="Weverse Web 搜集器", page_icon="🛍️")
st.title("🛍️ Weverse Shop 商品搜集助手")

# --- 初始化 Session State (防止下載重整) ---
if 'data_ready' not in st.session_state:
    st.session_state.data_ready = False
    st.session_state.excel_data = None
    st.session_state.zip_data = None
    st.session_state.title = ""
    st.session_state.currency = ""

# --- 核心搜集函式 ---
def fetch_weverse_data(category_url):
    # ... (前面的貨幣偵測邏輯不變) ...

    with sync_playwright() as p:
        # --- 修正後的啟動邏輯 ---
        st.info("🛠️ 正在初始化瀏覽器核心 (首次執行較久)...")
        
        # 強制安裝 chromium 與其必要的系統依賴
        try:
            # 加上 --with-deps 確保系統依賴被安裝
            os.system("python -m playwright install chromium --with-deps")
        except:
            pass
            
        try:
            # 使用更穩定的啟動參數
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", 
                    "--disable-setuid-sandbox", 
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            # ... 接下來的 context 建立與 page 邏輯 ...
            
# --- UI 介面 ---
target_url = st.text_input("🔗 請貼上館別網址:", placeholder="https://shop.weverse.io/...")

if st.button("🚀 開始擷取數據"):
    if target_url:
        with st.spinner('爬蟲運作中，請稍候...'):
            rows, images, title, currency = fetch_weverse_data(target_url)
            if rows:
                # 處理 Excel 緩存
                df = pd.DataFrame(rows, columns=["商品名稱", "網址url", "照片url", "規格/種類", "價格", "購買上限"])
                excel_buffer = io.BytesIO()
                df.to_excel(excel_buffer, index=False)
                
                # 處理 ZIP 緩存
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                    for img_name, img_content in images:
                        zip_file.writestr(img_name, img_content)

                st.session_state.excel_data = excel_buffer.getvalue()
                st.session_state.zip_data = zip_buffer.getvalue()
                st.session_state.title = title
                st.session_state.currency = currency
                st.session_state.data_ready = True
                st.success("✅ 擷取完成！")

if st.session_state.data_ready:
    st.divider()
    st.subheader(f"📂 下載區: {st.session_state.title}")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="📥 下載 Excel 報表",
            data=st.session_state.excel_data,
            file_name=f"{st.session_state.title}_{st.session_state.currency}.xlsx",
            mime="application/vnd.ms-excel"
        )
    with col2:
        st.download_button(
            label="🖼️ 下載全部圖片 (ZIP)",
            data=st.session_state.zip_data,
            file_name=f"{st.session_state.title}_images.zip",
            mime="application/zip"
        )