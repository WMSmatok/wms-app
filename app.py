import streamlit as st
import pandas as pd
import gspread
import json
import math
import time

# --- הגדרות ---
# וודא שהשמות כאן זהים ב-100% לשמות הקבצים שלך בדרייב
SHEET_LIVESTOCK = "LIVESTOCK"
SHEET_ORDERS = "מערכת ליקוט WMS"

# --- התחברות לגוגל ---
def connect_google():
    try:
        # קריאת המפתח מהסודות (נגדיר את זה תכף)
        key_dict = json.loads(st.secrets["textkey"])
        gc = gspread.service_account_from_dict(key_dict)
        return gc
    except Exception as e:
        st.error(f"שגיאת חיבור: {e}")
        return None

# --- עיצוב האפליקציה ---
st.set_page_config(page_title="WMS Cloud", layout="wide")
st.markdown("""
<style>
    .stApp {direction: rtl;}
    h1, h2, h3, p, div {text-align: right; font-family: sans-serif;}
    .stButton>button {width: 100%; height: 70px; font-size: 22px; font-weight: bold; border-radius: 12px;}
    .success-box {padding: 15px; background-color: #d4edda; color: #155724; border-radius: 8px; border: 1px solid #c3e6cb;}
    .error-box {padding: 15px; background-color: #f8d7da; color: #721c24; border-radius: 8px; border: 1px solid #f5c6cb;}
</style>
""", unsafe_allow_html=True)

st.title("☁️ מערכת ליקוט ענן")

gc = connect_google()

if gc:
    # טעינת נתונים
    try:
        sh_inv = gc.open(SHEET_LIVESTOCK)
        ws_inv = sh_inv.worksheet("LIVESTOCK")
        df_inv = pd.DataFrame(ws_inv.get_all_records())

        sh_ords = gc.open(SHEET_ORDERS)
        # מנסה למצוא את הלשונית הנכונה (PICKTASKS או הראשונה)
        try:
            ws_ords = sh_ords.worksheet("PICKTASKS")
        except:
            ws_ords = sh_ords.sheet1
        
        df_ords = pd.DataFrame(ws_ords.get_all_records())

        if st.button("🔄 רענן נתונים"):
            st.rerun()

        # --- לוגיקת המערכת ---
        # בדיקה שהעמודות קיימות (תומך בעברית ואנגלית)
        col_status = 'Status' if 'Status' in df_ords.columns else 'סטטוס'
        
        # סינון משימות פתוחות
        if col_status not in df_ords.columns:
            st.error(f"לא מצאתי עמודת סטטוס ({col_status}) בקובץ.")
        else:
            pending = df_ords[df_ords[col_status] != 'Done']

            if pending.empty:
                st.success("🎉 אין משימות פתוחות! המחסן נקי.")
            else:
                st.write(f"משימות לביצוע: {len(pending)}")
                
                for i, row in pending.iterrows():
                    with st.container(border=True):
                        # זיהוי שמות עמודות גמיש
                        p_name = row.get('ProductName') or row.get('שם מוצר')
                        qty = row.get('QtyToPick') or row.get('כמות') or 0
                        
                        st.header(f"📦 {p_name}")
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            # חישוב קרטונים (מתוק וקל = 24, כל השאר 12)
                            div = 24 if "מתוק וקל 1000" in str(p_name) else 12
                            cartons = math.ceil(float(qty) / div)
                            
                            st.info(f"להזמנה: **{qty}** | קרטונים: **{cartons}**")
                        
                        with c2:
                            # בדיקת מלאי
                            stock_found = df_inv[df_inv['שם מוצר'] == p_name]
                            
                            # סיכום כמות (Live_Qty או כמות)
                            col_qty_stock = 'Live_Qty' if 'Live_Qty' in df_inv.columns else 'כמות'
                            total_stock = pd.to_numeric(stock_found[col_qty_stock], errors='coerce').sum()
                            
                            if total_stock >= float(qty):
                                # חיפוש תאריך תפוגה (FIFO)
                                try:
                                    stock_found = stock_found.sort_values('תאריך ושעה') # מיון לפי תאריך כניסה
                                    best_batch = stock_found[pd.to_numeric(stock_found[col_qty_stock], errors='coerce') > 0].iloc[0]
                                    expiry = best_batch.get('תאריך תפוגה', 'לא ידוע')
                                except:
                                    expiry = "לא נמצא תאריך"

                                st.markdown(f"""
                                <div class="success-box">
                                ✅ <b>יש במלאי!</b> ({total_stock})<br>
                                תוקף מומלץ: {expiry}
                                </div>
                                """, unsafe_allow_html=True)
                                
                                st.write("")
                                if st.button("✅ אשר ליקוט", key=f"btn_{i}"):
                                    # עדכון גוגל שיטס
                                    # חישוב מספר השורה (אינדקס + 2 בגלל כותרות)
                                    row_num = i + 2
                                    col_num = df_ords.columns.get_loc(col_status) + 1
                                    
                                    ws_ords.update_cell(row_num, col_num, "Done")
                                    st.success("עודכן בענן!")
                                    time.sleep(1)
                                    st.rerun()
                            else:
                                st.markdown(f'<div class="error-box">❌ חסר במלאי (יש רק {total_stock})</div>', unsafe_allow_html=True)

    except Exception as e:
        st.error(f"שגיאה בטעינת קבצים: {e}")
        st.warning("טיפ: בדוק ששיתפת את הקבצים עם המייל של הרובוט!")
