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
    # 1. 根據網址偵測貨幣並選擇對應的 JSON
    if "KRW" in category_url:
        auth_file = "weverse_env_KR.json"
        st.info("🇰🇷 偵測到韓國館別，正在載入韓國環境設定...")
    elif "JPY" in category_url:
        auth_file = "weverse_env_JP.json"
        st.info("🇯🇵 偵測到日本館別，正在載入日本環境設定...")
    else:
        st.error("❌ 無法從網址辨識貨幣類型 (需包含 KRW 或 JPY)")
        return None, None, None, None

    # 檢查檔案是否存在
    if not os.path.exists(auth_file):
        st.error(f"❌ 找不到設定檔: {auth_file}")
        return None, None, None, None

    with sync_playwright() as p:
        # 雲端環境安裝與啟動
        os.system("playwright install chromium")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=auth_file)
        page = context.new_page()

        # 提取參數
        url_match = re.search(r'artists/(\d+)/', category_url)
        artist_id = url_match.group(1) if url_match else "7"
        current_currency = "KRW" if "KRW" in category_url else "JPY"

        page.goto(category_url)
        page.wait_for_load_state("domcontentloaded")
        
        # 標題處理：保留 '-' 之後的內容
        full_title = page.title().replace("Weverse Shop :", "").strip()
        clean_title = full_title.split('-')[-1].strip() if '-' in full_title else full_title
        safe_title = re.sub(r'[\\/*?:"<>|]', "", clean_title).strip().replace(" ", "_")

        # 獲取商品清單
        page.wait_for_selector("#__NEXT_DATA__", state="attached")
        cat_json = json.loads(page.locator("#__NEXT_DATA__").inner_text())
        queries = cat_json['props']['pageProps']['$dehydratedState']['queries']
        basic_products = []
        for q in queries:
            if 'productCards' in q.get('state', {}).get('data', {}):
                basic_products = q['state']['data']['productCards']
                break

        rows = []
        image_list = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, item in enumerate(basic_products):
            p_name = item['name']
            safe_p_name = re.sub(r'[\\/*?:"<>|]', "", p_name).strip().replace(" ", "_")
            detail_url = f"https://shop.weverse.io/zh-cn/shop/{current_currency}/artists/{artist_id}/sales/{item['saleId']}"
            
            status_text.text(f"正在解析 ({i+1}/{len(basic_products)}): {p_name}")
            progress_bar.progress((i + 1) / len(basic_products))

            try:
                page.goto(detail_url)
                page.wait_for_selector("#__NEXT_DATA__", state="attached")
                prod_json = json.loads(page.locator("#__NEXT_DATA__").inner_text())
                prod_queries = prod_json['props']['pageProps']['$dehydratedState']['queries']
                
                detail = None
                for q in prod_queries:
                    d = q.get('state', {}).get('data', {})
                    if isinstance(d, dict) and str(d.get('saleId')) == str(item['saleId']):
                        detail = d
                        break
                
                if detail:
                    thumb_list = detail.get("thumbnailImageUrls", [])
                    img_url = thumb_list[0] if thumb_list else ""
                    
                    if img_url:
                        try:
                            img_res = requests.get(img_url, timeout=5)
                            if img_res.status_code == 200:
                                image_list.append((f"{safe_p_name}.jpg", img_res.content))
                        except: pass

                    limit = detail.get("goodsOrderLimit", {}).get("maxOrderQuantity", "N/A")
                    opts = detail.get("options", []) or detail.get("option", {}).get("options", [])
                    
                    if not opts:
                        rows.append([p_name, detail_url, img_url, "單種類", detail.get("price"), limit])
                    else:
                        for idx, opt in enumerate(opts):
                            spec = opt.get("saleOptionName")
                            price = opt.get("optionSalePrice")
                            opt_limit = opt.get("optionOrderLimit", {}).get("maxOrderQuantity")
                            row_limit = opt_limit if opt_limit else limit
                            if idx == 0:
                                rows.append([p_name, detail_url, img_url, spec, price, row_limit])
                            else:
                                rows.append(["", "", "", spec, price, ""])
            except: pass
            time.sleep(0.1)

        browser.close()
        return rows, image_list, safe_title, current_currency

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