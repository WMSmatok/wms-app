import streamlit as st
import pandas as pd
import gspread
import json
import math
import time

# --- הגדרות ---
# וודא שהשמות האלו זהים בול לשמות בדרייב שלך
SHEET_LIVESTOCK = "LIVESTOCK"
SHEET_ORDERS = "מערכת ליקוט WMS"

# --- פונקציות חיבור ---
def connect_google():
    try:
        if "textkey" in st.secrets:
            key_dict = json.loads(st.secrets["textkey"])
            gc = gspread.service_account_from_dict(key_dict)
            return gc
        else:
            st.error("❌ שגיאה: חסר מפתח 'textkey' בהגדרות ה-Secrets של האתר.")
            return None
    except Exception as e:
        st.error(f"❌ שגיאה בקריאת המפתח הסודי: {e}")
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
    div[data-testid="stTextInput"] input {font-size: 20px; text-align: center; border: 2px solid #28a745;}
</style>
""", unsafe_allow_html=True)

st.title("🔫 מערכת ליקוט בסריקה")

gc = connect_google()

if not gc:
    st.stop()

# --- טעינת נתונים עם דיווח שגיאות מפורט ---
# שלב 1: טעינת מלאי
try:
    sh_inv = gc.open(SHEET_LIVESTOCK)
except Exception as e:
    st.error(f"❌ לא הצלחתי למצוא את קובץ המלאי בשם: '{SHEET_LIVESTOCK}'")
    st.info(f"הודעת השגיאה המקורית: {e}")
    st.warning("טיפ: וודא שהקובץ קיים בדרייב וששיתפת אותו עם המייל של הרובוט.")
    st.stop()

try: 
    ws_inv = sh_inv.worksheet("LIVESTOCK")
except: 
    # גיבוי: אם השם לא תואם, לוקח את הלשונית הראשונה
    ws_inv = sh_inv.get_worksheet(0)

df_inv = pd.DataFrame(ws_inv.get_all_records())

# שלב 2: טעינת הזמנות
try:
    sh_ords = gc.open(SHEET_ORDERS)
except Exception as e:
    st.error(f"❌ לא הצלחתי למצוא את קובץ ההזמנות בשם: '{SHEET_ORDERS}'")
    st.info(f"הודעת השגיאה המקורית: {e}")
    st.stop()

try: 
    ws_ords = sh_ords.worksheet("PICKTASKS")
except: 
    # גיבוי: לוקח לשונית ראשונה
    ws_ords = sh_ords.get_worksheet(0)

df_ords = pd.DataFrame(ws_ords.get_all_records())


# --- המשך התוכנה (רק אם הכל נטען תקין) ---

# זיהוי עמודות
col_status = find_column(df_ords, ['Status', 'סטטוס', 'מצב'])
col_pname_ord = find_column(df_ords, ['ProductName', 'שם מוצר', 'פריט', 'SKU'])
col_qty_ord = find_column(df_ords, ['QtyToPick', 'כמות', 'Quantity'])

col_name_inv = find_column(df_inv, ['שם מוצר', 'ProductName', 'פריט'])
col_qty_inv = find_column(df_inv, ['Quantity', 'Live_Qty', 'כמות'])
col_batch_inv = find_column(df_inv, ['אצווה', 'BatchNumber', 'Batch', 'תאריך תפוגה', 'תוקף']) 
col_date_inv = find_column(df_inv, ['תאריך ושעה', 'EntryDate', 'Date'])

if col_status:
    pending = df_ords[df_ords[col_status] != 'Done']

    if pending.empty:
        st.success("🎉 כל המשימות הושלמו! המחסן נקי.")
        st.balloons()
    else:
        current_task = pending.iloc[0]
        task_index = pending.index[0]

        p_name = str(current_task.get(col_pname_ord, 'Unknown')).strip()
        qty_needed = float(current_task.get(col_qty_ord, 0))

        div = 24 if "מתוק וקל 1000" in p_name else 12
        try: cartons = math.ceil(qty_needed / div)
        except: cartons = 0

        target_batch = "לא נמצא"
        target_stock = 0
        
        # חיפוש חכם במלאי (טיפול ברווחים)
        if col_name_inv:
             # מנקים רווחים משם המוצר במלאי כדי למצוא התאמה
             df_inv['clean_name'] = df_inv[col_name_inv].astype(str).str.strip()
             stock_subset = df_inv[df_inv['clean_name'] == p_name]
             
             if not stock_subset.empty and col_date_inv:
                try:
                    stock_subset = stock_subset.sort_values(col_date_inv)
                    valid_stock = stock_subset[pd.to_numeric(stock_subset[col_qty_inv], errors='coerce') > 0]
                    if not valid_stock.empty:
                        target_batch = str(valid_stock.iloc[0].get(col_batch_inv, 'General')).strip()
                        target_stock = valid_stock.iloc[0].get(col_qty_inv, 0)
                except: pass
        
        # תצוגה
        st.info(f"משימות שנותרו: {len(pending)}")
        st.markdown("---")
        st.markdown(f'<p class="big-font">📦 {p_name}</p>', unsafe_allow_html=True)
        
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("כמות להזמנה", qty_needed)
        with c2: st.metric("מספר קרטונים", cartons)
        with c3: st.metric("מלאי במדף", target_stock)

        st.markdown("---")
        st.markdown(f"""
        <div class="batch-box">
            <h3>🛡️ בקרת FIFO</h3>
            <p>האצווה הישנה ביותר במדף היא: <b>{target_batch}</b></p>
            <p class="scan-instruction">אנא סרוק את המוצר לאישור 👇</p>
        </div>
        """, unsafe_allow_html=True)

        st.write("")
        scanned_code = st.text_input("סרוק ברקוד כאן:", key=f"scan_{task_index}")

        if scanned_code:
            scanned_clean = scanned_code.strip()
            target_clean = target_batch.strip()

            if scanned_clean == target_clean:
                st.success(f"✅ סריקה תקינה! ({scanned_clean})")
                try:
                    # עדכון מלאי
                    # לוגיקה משופרת למציאת השורה לעדכון
                    inv_row_to_update = None
                    all_records = ws_inv.get_all_records()
                    
                    for i, record in enumerate(all_records):
                        r_name = str(record.get(col_name_inv)).strip()
                        r_batch = str(record.get(col_batch_inv)).strip()
                        if r_name == p_name and r_batch == scanned_clean:
                            inv_row_to_update = i + 2
                            break
                    
                    if inv_row_to_update:
                        col_idx_qty = df_inv.columns.get_loc(col_qty_inv) + 1
                        current_qty = float(ws_inv.cell(inv_row_to_update, col_idx_qty).value)
                        new_qty = max(0, current_qty - qty_needed) # מונע ירידה מתחת לאפס
                        ws_inv.update_cell(inv_row_to_update, col_idx_qty, new_qty)
                        st.info(f"המלאי עודכן: {current_qty} -> {new_qty}")
                    
                    # סגירת הזמנה
                    row_num_ord = task_index + 2
                    col_idx_status = df_ords.columns.get_loc(col_status) + 1
                    ws_ords.update_cell(row_num_ord, col_idx_status, "Done")
                    
                    st.toast("עודכן בהצלחה!")
                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    st.error(f"שגיאה בעדכון הנתונים: {e}")
            
            elif scanned_clean.upper() == "OK":
                row_num_ord = task_index + 2
                col_idx_status = df_ords.columns.get_loc(col_status) + 1
                ws_ords.update_cell(row_num_ord, col_idx_status, "Done")
                st.warning("אושר ידנית.")
                time.sleep(1)
                st.rerun()

            else:
                st.error(f"⛔ שגיאה: סרקת '{scanned_clean}' במקום '{target_clean}'")
else:
    st.error("לא נמצאה עמודת סטטוס בקובץ ההזמנות.")
