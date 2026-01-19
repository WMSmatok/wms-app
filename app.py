import streamlit as st
import pandas as pd
import gspread
import json
import math
import time

# --- הגדרות ---
SHEET_LIVESTOCK = "LIVESTOCK"
SHEET_ORDERS = "מערכת ליקוט WMS"

# --- פונקציות חיבור ---
def connect_google():
    try:
        if "textkey" in st.secrets:
            key_dict = json.loads(st.secrets["textkey"])
            gc = gspread.service_account_from_dict(key_dict)
            return gc
    except: return None
    return None

def find_column(df, possible_names):
    for name in possible_names:
        if name in df.columns: return name
    return None

# --- עיצוב ---
st.set_page_config(page_title="WMS Scanner", layout="wide")
st.markdown("""
<style>
    .stApp {direction: rtl;}
    div {text-align: right;}
    .big-font {font-size: 30px !important; font-weight: bold; color: #1f77b4;}
    .batch-box {padding: 20px; background-color: #fff3cd; border: 2px solid #ffeeba; border-radius: 10px; text-align: center;}
    .scan-instruction {font-size: 24px; font-weight: bold; color: #dc3545;}
    /* עיצוב שדה הסריקה */
    div[data-testid="stTextInput"] input {
        font-size: 20px; 
        text-align: center; 
        border: 2px solid #28a745;
    }
</style>
""", unsafe_allow_html=True)

st.title("🔫 מערכת ליקוט בסריקה")

gc = connect_google()

if not gc:
    st.error("שגיאת חיבור לגוגל")
    st.stop()

# --- טעינת נתונים ---
try:
    # מלאי
    sh_inv = gc.open(SHEET_LIVESTOCK)
    try: ws_inv = sh_inv.worksheet("LIVESTOCK")
    except: ws_inv = sh_inv.get_worksheet(0)
    df_inv = pd.DataFrame(ws_inv.get_all_records())

    # הזמנות
    sh_ords = gc.open(SHEET_ORDERS)
    try: ws_ords = sh_ords.worksheet("PICKTASKS")
    except: ws_ords = sh_ords.sheet1
    df_ords = pd.DataFrame(ws_ords.get_all_records())
except:
    st.error("שגיאה בטעינת הקבצים. בדוק שמות ושיתוף.")
    st.stop()

# --- זיהוי עמודות ---
col_status = find_column(df_ords, ['Status', 'סטטוס', 'מצב'])
col_pname_ord = find_column(df_ords, ['ProductName', 'שם מוצר', 'פריט'])
col_qty_ord = find_column(df_ords, ['QtyToPick', 'כמות', 'Quantity'])

col_name_inv = find_column(df_inv, ['שם מוצר', 'ProductName', 'פריט'])
col_qty_inv = find_column(df_inv, ['Quantity', 'Live_Qty', 'כמות'])
# המערכת תחפש את הברקוד בעמודות האלו (אצווה או תוקף)
col_batch_inv = find_column(df_inv, ['אצווה', 'BatchNumber', 'Batch', 'תאריך תפוגה', 'תוקף']) 
col_date_inv = find_column(df_inv, ['תאריך ושעה', 'EntryDate', 'Date'])

# --- לוגיקה ---
if col_status:
    # לוקחים רק משימות פתוחות
    pending = df_ords[df_ords[col_status] != 'Done']

    if pending.empty:
        st.success("🎉 כל המשימות הושלמו! המחסן נקי.")
        st.balloons()
    else:
        # 1. לוקחים רק את המשימה הראשונה בתור (Focus Mode)
        current_task = pending.iloc[0]
        task_index = pending.index[0] # שומרים את מספר השורה המקורי

        p_name = str(current_task.get(col_pname_ord, 'Unknown')).strip()
        qty_needed = float(current_task.get(col_qty_ord, 0))

        # 2. מחשבים קרטונים
        div = 24 if "מתוק וקל 1000" in p_name else 12
        try: cartons = math.ceil(qty_needed / div)
        except: cartons = 0

        # 3. מוצאים את האצווה הישנה ביותר במלאי (FIFO)
        target_batch = "לא נמצא"
        target_stock = 0
        
        # סינון המלאי לפי שם מדוייק
        stock_subset = df_inv[df_inv[col_name_inv].astype(str).str.strip() == p_name]
        
        if not stock_subset.empty and col_date_inv:
            # מיון מהישן לחדש
            try:
                stock_subset = stock_subset.sort_values(col_date_inv)
                # סינון רק מה שיש בו מלאי חיובי
                valid_stock = stock_subset[pd.to_numeric(stock_subset[col_qty_inv], errors='coerce') > 0]
                
                if not valid_stock.empty:
                    # הנתון שאנחנו מצפים שהסורק יקרא (למשל מספר אצווה או תוקף)
                    target_batch = str(valid_stock.iloc[0].get(col_batch_inv, 'General')).strip()
                    target_stock = valid_stock.iloc[0].get(col_qty_inv, 0)
            except: pass

        # --- התצוגה למלקט ---
        st.info(f"משימות שנותרו: {len(pending)}")
        st.markdown("---")
        
        # כותרת ענקית של המוצר
        st.markdown(f'<p class="big-font">📦 {p_name}</p>', unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("כמות להזמנה", qty_needed)
        with c2:
            st.metric("מספר קרטונים", cartons)
        with c3:
            st.metric("מלאי במדף", target_stock)

        st.markdown("---")

        # קופסת FIFO צהובה
        st.markdown(f"""
        <div class="batch-box">
            <h3>🛡️ בקרת FIFO</h3>
            <p>האצווה הישנה ביותר במדף היא: <b>{target_batch}</b></p>
            <p class="scan-instruction">אנא סרוק את המוצר לאישור 👇</p>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        
        # --- השדה של הסורק ---
        # הסורק "מקליד" לתוך השדה הזה ועושה אנטר. key דינמי מנקה את השדה אחרי רענון
        scanned_code = st.text_input("סרוק ברקוד כאן:", key=f"scan_{task_index}")

        if scanned_code:
            # ניקוי הקלט מהסורק
            scanned_clean = scanned_code.strip()
            target_clean = target_batch.strip()

            # --- מנגנון הבדיקה ---
            
            # בדיקה 1: האם הסריקה תואמת לאצווה המצופה?
            if scanned_clean == target_clean:
                st.success(f"✅ סריקה תקינה! ({scanned_clean})")
                
                try:
                    # שלב א': עדכון כמות במלאי (הפחתה)
                    # מחפשים את השורה באקסל המלאי שמתאימה למוצר ולאצווה
                    cell_found = ws_inv.find(p_name) # חיפוש ראשוני לפי שם
                    
                    # חיפוש מדוייק יותר בתוך הרשומות
                    all_records = ws_inv.get_all_records()
                    inv_row_to_update = None
                    
                    for i, record in enumerate(all_records):
                        # שורה באקסל היא אינדקס + 2
                        current_row = i + 2
                        r_name = str(record.get(col_name_inv)).strip()
                        r_batch = str(record.get(col_batch_inv)).strip()
                        
                        # מחפשים שורה שיש בה גם את שם המוצר וגם את האצווה שנסרקה
                        if r_name == p_name and r_batch == scanned_clean:
                            inv_row_to_update = current_row
                            break
                    
                    if inv_row_to_update:
                        # מצאנו את השורה! עכשיו נעדכן כמות
                        col_idx_qty = df_inv.columns.get_loc(col_qty_inv) + 1
                        current_qty = float(ws_inv.cell(inv_row_to_update, col_idx_qty).value)
                        new_qty = current_qty - qty_needed
                        ws_inv.update_cell(inv_row_to_update, col_idx_qty, new_qty)
                        st.info(f"המלאי עודכן: {current_qty} -> {new_qty}")
                    else:
                        st.warning("המוצר אושר, אך לא נמצאה שורת המלאי המדויקת לעדכון הכמות.")

                    # שלב ב': סגירת ההזמנה
                    row_num_ord = task_index + 2
                    col_idx_status = df_ords.columns.get_loc(col_status) + 1
                    ws_ords.update_cell(row_num_ord, col_idx_status, "Done")
                    
                    st.toast("עודכן בהצלחה! עובר למוצר הבא...")
                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    st.error(f"שגיאה בעדכון הנתונים: {e}")
            
            # בדיקה 2: האם המלקט כתב ידנית 'OK' לאישור חריג?
            elif scanned_clean.upper() == "OK":
                row_num_ord = task_index + 2
                col_idx_status = df_ords.columns.get_loc(col_status) + 1
                ws_ords.update_cell(row_num_ord, col_idx_status, "Done")
                st.warning("הליקוט אושר ידנית (עקיפה).")
                time.sleep(1)
                st.rerun()

            else:
                # אם הסריקה לא תואמת
                st.error(f"⛔ שגיאת FIFO! סרקת '{scanned_clean}' אך המערכת מצפה ל-'{target_clean}'.")
                st.warning("נא לחפש את הסחורה הישנה יותר.")
                st.info("אם אין ברירה, הקלד OK בשדה הסריקה כדי לאלץ אישור.")

else:
    st.error("לא נמצאה עמודת סטטוס בקובץ ההזמנות.")
