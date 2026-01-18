import streamlit as st
import pandas as pd
import gspread
import json
import math
import time

# --- הגדרות ---
SHEET_LIVESTOCK = "LIVESTOCK"
SHEET_ORDERS = "מערכת ליקוט WMS"

# --- פונקציה חכמה למציאת עמודות (גמישה) ---
def find_column(df, possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None

# --- התחברות לגוגל ---
def connect_google():
    try:
        if "textkey" in st.secrets:
            key_dict = json.loads(st.secrets["textkey"])
            gc = gspread.service_account_from_dict(key_dict)
            return gc
        else:
            st.error("חסר מפתח (textkey) בהגדרות ה-Secrets")
            return None
    except Exception as e:
        st.error(f"שגיאת חיבור למפתח של גוגל: {e}")
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
    .info-box {padding: 15px; background-color: #e2e3e5; color: #383d41; border-radius: 8px;}
</style>
""", unsafe_allow_html=True)

st.title("☁️ מערכת ליקוט ענן")

gc = connect_google()

if gc:
    try:
        # 1. טעינת המלאי (LIVESTOCK)
        try:
            sh_inv = gc.open(SHEET_LIVESTOCK)
            try:
                ws_inv = sh_inv.worksheet("LIVESTOCK")
            except:
                # אם לא מוצא את הלשונית בשם הזה, לוקח את הראשונה
                ws_inv = sh_inv.get_worksheet(0)
            df_inv = pd.DataFrame(ws_inv.get_all_records())
        except Exception as e:
            st.error(f"לא הצלחתי לפתוח את קובץ המלאי '{SHEET_LIVESTOCK}'. האם השם נכון? האם שיתפת עם הרובוט?")
            st.stop()

        # 2. טעינת ההזמנות (PICKTASKS)
        try:
            sh_ords = gc.open(SHEET_ORDERS)
            try:
                ws_ords = sh_ords.worksheet("PICKTASKS")
            except:
                ws_ords = sh_ords.sheet1 
            df_ords = pd.DataFrame(ws_ords.get_all_records())
        except Exception as e:
            st.error(f"לא הצלחתי לפתוח את קובץ ההזמנות: {e}")
            st.stop()

        if st.button("🔄 רענן נתונים"):
            st.rerun()

        # --- זיהוי עמודות חכם (התיקון הגדול) ---
        
        # זיהוי עמודת סטטוס
        col_status = find_column(df_ords, ['Status', 'סטטוס', 'מצב', 'status'])
        
        if not col_status:
            st.error(f"לא מצאתי עמודת סטטוס בהזמנות! העמודות שיש הן: {list(df_ords.columns)}")
        else:
            # סינון משימות פתוחות
            pending = df_ords[df_ords[col_status] != 'Done']

            if pending.empty:
                st.success("🎉 אין משימות פתוחות! המחסן נקי.")
            else:
                st.info(f"משימות לביצוע: {len(pending)}")
                
                for i, row in pending.iterrows():
                    with st.container(border=True):
                        # זיהוי שמות עמודות בהזמנה
                        col_pname_ord = find_column(df_ords, ['ProductName', 'שם מוצר', 'פריט', 'SKU'])
                        col_qty_ord = find_column(df_ords, ['QtyToPick', 'כמות', 'Quantity', 'Qty'])
                        
                        p_name = row.get(col_pname_ord, 'לא ידוע')
                        qty = row.get(col_qty_ord, 0)
                        
                        st.header(f"📦 {p_name}")
                        
                        c1, c2 = st.columns(2)
                        with c1:
                            # חישוב קרטונים
                            div = 24 if "מתוק וקל 1000" in str(p_name) else 12
                            try:
                                cartons = math.ceil(float(qty) / div)
                            except:
                                cartons = 0
                            
                            st.markdown(f"""
                            <div class="info-box">
                            להזמנה: <b>{qty}</b><br>
                            קרטונים: <b>{cartons}</b>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        with c2:
                            # --- חיפוש חכם במלאי ---
                            # המערכת מחפשת גם Quantity וגם כמות
                            col_qty_inv = find_column(df_inv, ['Quantity', 'Live_Qty', 'כמות', 'Qty', 'Amount'])
                            col_name_inv = find_column(df_inv, ['שם מוצר', 'ProductName', 'פריט'])
                            col_date_inv = find_column(df_inv, ['תאריך ושעה', 'EntryDate', 'Date', 'תאריך'])
                            col_exp_inv = find_column(df_inv, ['תאריך תפוגה', 'ExpiryDate', 'תוקף'])

                            # אם המערכת עדיין לא מוצאת, היא תגיד לך בדיוק מה הבעיה
                            if not col_qty_inv or not col_name_inv:
                                st.error("שגיאה: לא מצאתי עמודת 'שם מוצר' או 'כמות' בקובץ המלאי.")
                                st.warning(f"העמודות שמצאתי בקובץ שלך הן: {list(df_inv.columns)}")
                            else:
                                # סינון המלאי לפי המוצר
                                stock_found = df_inv[df_inv[col_name_inv] == p_name]
                                
                                # המרה למספרים וסיכום
                                total_stock = pd.to_numeric(stock_found[col_qty_inv], errors='coerce').sum()
                                
                                if total_stock >= float(qty):
                                    expiry_text = "לא צויין"
                                    # ניסיון למצוא תאריך (FIFO)
                                    if col_date_inv and not stock_found.empty:
                                        try:
                                            # מיון לפי תאריך כניסה
                                            stock_found = stock_found.sort_values(col_date_inv)
                                            # מציאת השורה הראשונה עם מלאי חיובי
                                            valid_batches = stock_found[pd.to_numeric(stock_found[col_qty_inv], errors='coerce') > 0]
                                            if not valid_batches.empty:
                                                if col_exp_inv:
                                                    expiry_text = valid_batches.iloc[0].get(col_exp_inv, 'לא ידוע')
                                        except:
                                            pass

                                    st.markdown(f"""
                                    <div class="success-box">
                                    ✅ <b>יש במלאי!</b> ({total_stock})<br>
                                    תוקף מומלץ: {expiry_text}
                                    </div>
                                    """, unsafe_allow_html=True)
                                    
                                    st.write("")
                                    if st.button("✅ אשר ליקוט", key=f"btn_{i}"):
                                        # עדכון גוגל שיטס
                                        try:
                                            row_num = i + 2 
                                            col_idx = df_ords.columns.get_loc(col_status) + 1
                                            ws_ords.update_cell(row_num, col_idx, "Done")
                                            st.success("עודכן בענן!")
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"שגיאה בעדכון: {e}")

                                else:
                                    st.markdown(f'<div class="error-box">❌ חסר במלאי (יש רק {total_stock})</div>', unsafe_allow_html=True)

    except Exception as main_e:
        st.error(f"שגיאה כללית בתוכנה: {main_e}")
