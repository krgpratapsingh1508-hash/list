import streamlit as st
import pandas as pd
import os
import io
import json
import time
from datetime import datetime

# ==========================================================
# ⚙️ STEP 1: PAGE CONFIG
# ==========================================================
st.set_page_config(layout="wide", page_title="Department Approval & Assignment System")

# ==========================================================
# 📁 FILE PATHS (Permanent Local Storage)
# ==========================================================
DB_FILE = "approval_workflow_database.csv"
CRED_FILE = "approval_workflow_credentials.json"
DEPT_FILE = "approval_workflow_departments.json"

# ==========================================================
# 🧾 COLUMN SCHEMA
# (Business columns — jitne columns chahiye utne yahan add/remove kiye ja sakte hain.
#  Print/Export ke waqt inme se koi bhi columns chune ja sakte hain — us par koi restriction nahi.)
# ==========================================================
DEFAULT_COLUMNS = [
    "Admission Year", "Admission Session", "Eligibility Name", "Admission Application Number",
    "Admission Date", "Unique ID", "Roll No.", "Application Enrollment No.",
    "Enrollment No.", "Student Name", "Father Name", "Mother Name", "Date of Birth",
    "Category", "Subject Code", "Subject", "Duration", "Mobile Number", "Email ID", "Address", "Status2",
    "Current Year", "Application Number", "Student Abc Id", "Gender", "Admission Category", "Degree",
    "Branch", "Minor Subjects", "Vocational Subjects", "MDC Subjects", "PW/Ap/CE Subjects",
    "Admission & Enrollment Fees", "Scholarship Name", "Payment Date", "Remarks"
]

# System / workflow columns — inhe app khud manage karti hai, user in par bharosa kare
SYSTEM_COLUMNS = ["Status", "Assigned Department", "Submitted By", "Submitted On", "Approved By", "Approved On"]
ALL_COLUMNS = DEFAULT_COLUMNS + SYSTEM_COLUMNS

DEFAULT_DEPARTMENTS = ["Examination Department", "Accounts Department", "Scholarship Department", "Registrar Office"]

DEFAULT_CREDENTIALS = {
    "admin": {"password": "admin123", "role": "admin", "label": "👑 Super Admin (P1–P6 Full Control)"}
}

# ==========================================================
# 📦 STEP 2: LOAD / SAVE HELPERS
# ==========================================================

def load_db():
    if os.path.exists(DB_FILE):
        try:
            df = pd.read_csv(DB_FILE, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame(columns=ALL_COLUMNS)
    else:
        df = pd.DataFrame(columns=ALL_COLUMNS)
    for c in ALL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[ALL_COLUMNS]


def save_db(df):
    df.to_csv(DB_FILE, index=False)


def load_credentials():
    if os.path.exists(CRED_FILE):
        try:
            with open(CRED_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return dict(DEFAULT_CREDENTIALS)


def save_credentials(creds):
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        json.dump(creds, f, ensure_ascii=False, indent=4)


def load_departments():
    if os.path.exists(DEPT_FILE):
        try:
            with open(DEPT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return list(DEFAULT_DEPARTMENTS)


def save_departments(depts):
    with open(DEPT_FILE, "w", encoding="utf-8") as f:
        json.dump(depts, f, ensure_ascii=False, indent=4)


def read_uploaded_table(uploaded_file):
    """CSV ya Excel (.csv/.xlsx/.xls) — dono ko ek DataFrame (sab text) me badalta hai."""
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl" if name.endswith("xlsx") else None).fillna("")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc).fillna("")
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    return pd.DataFrame()


# ==========================================================
# 🔐 SESSION STATE INIT
# ==========================================================
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "username" not in st.session_state:
    st.session_state.username = None
if "user_department" not in st.session_state:
    st.session_state.user_department = None
if "credentials" not in st.session_state:
    st.session_state.credentials = load_credentials()
if "departments" not in st.session_state:
    st.session_state.departments = load_departments()

# ==========================================================
# 🎨 STEP 3: THEME CSS (Navy + Gold institutional theme)
# ==========================================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');

    :root {
        --pg-navy: #0F2A4A;
        --pg-navy-light: #1D4A7A;
        --pg-gold: #C9973F;
        --pg-gold-dark: #A97A25;
        --pg-bg: #F5F7FA;
        --pg-surface: #FFFFFF;
        --pg-border: #DCE3EC;
        --pg-text: #1B2430;
    }

    [data-testid="stAppViewContainer"], .main, body {
        background: var(--pg-bg) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
        color: var(--pg-text) !important;
    }
    [data-testid="stHeader"] { background: transparent !important; }
    .block-container { padding-top: 2rem !important; }

    h1, h2, h3, h4 {
        font-family: 'Poppins', 'Inter', sans-serif !important;
        color: var(--pg-navy) !important;
        font-weight: 600 !important;
    }
    .stMarkdown h1, .stMarkdown h2, div[data-testid="stHeadingWithActionElements"] h1,
    div[data-testid="stHeadingWithActionElements"] h2 {
        display: inline-block; padding-bottom: 6px;
        border-bottom: 3px solid var(--pg-gold); margin-bottom: 16px !important;
    }

    .stButton > button, .stDownloadButton > button {
        border-radius: 8px !important; font-weight: 600 !important;
        padding: 0.55rem 1.2rem !important;
        transition: transform 0.12s ease, box-shadow 0.12s ease !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--pg-navy) 0%, var(--pg-navy-light) 100%) !important;
        border: none !important; color: #fff !important;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 4px 14px rgba(15,42,74,0.30) !important; transform: translateY(-1px);
    }
    .stButton > button[kind="secondary"] {
        background: var(--pg-surface) !important; color: var(--pg-navy) !important;
        border: 1.5px solid var(--pg-navy) !important;
    }
    .stButton > button[kind="secondary"]:hover { background: #EEF2F8 !important; }
    .stDownloadButton > button {
        background: linear-gradient(135deg, var(--pg-gold-dark) 0%, var(--pg-gold) 100%) !important;
        color: #fff !important; border: none !important;
    }
    .stDownloadButton > button:hover {
        box-shadow: 0 4px 14px rgba(201,151,63,0.38) !important; transform: translateY(-1px);
    }

    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
        border: 1px solid var(--pg-border) !important; border-radius: 10px !important;
        overflow: hidden !important; box-shadow: 0 1px 4px rgba(15,42,74,0.07) !important;
    }
    div[data-testid="stDataFrame"] [role="columnheader"],
    div[data-testid="stDataEditor"] [role="columnheader"] {
        background: var(--pg-navy) !important; color: #fff !important; font-weight: 600 !important;
    }

    div[data-testid="stAlert"] { border-radius: 8px !important; border-left-width: 5px !important; }

    .stTextInput input, .stNumberInput input, .stTextArea textarea,
    .stSelectbox div[data-baseweb="select"] > div {
        border-radius: 6px !important; border-color: var(--pg-border) !important;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus {
        border-color: var(--pg-gold) !important; box-shadow: 0 0 0 1px var(--pg-gold) !important;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F2A4A 0%, #0A1E33 100%) !important;
        border-right: 1px solid #0A1E33 !important;
    }
    [data-testid="stSidebar"] * { color: #F2F5FA !important; }
    [data-testid="stSidebar"] hr { border-top: 1px solid rgba(255,255,255,0.15) !important; }
    [data-testid="stSidebar"] label[data-testid="stWidgetLabel"] p {
        font-family: 'Poppins','Inter',sans-serif !important;
        font-size: 16px !important; font-weight: 700 !important;
        color: #E9C989 !important; letter-spacing: 0.2px;
        padding-bottom: 10px !important; margin-bottom: 4px !important;
        border-bottom: 2px solid rgba(233,201,137,0.35);
    }
    [data-testid="stSidebar"] div[role="radiogroup"] {
        display: flex !important; flex-direction: column !important; gap: 7px !important; margin-top: 6px !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label {
        background: rgba(255,255,255,0.06) !important; border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 9px !important; padding: 11px 14px !important; margin: 0 !important; width: 100% !important;
        transition: background 0.15s ease, border-color 0.15s ease, transform 0.1s ease !important; cursor: pointer !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:hover {
        background: rgba(201,151,63,0.18) !important; border-color: #C9973F !important; transform: translateX(2px);
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(135deg, #C9973F 0%, #A97A25 100%) !important;
        border-color: #E9C989 !important; box-shadow: 0 2px 8px rgba(0,0,0,0.25) !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p {
        color: #0F2A4A !important; font-weight: 700 !important;
    }
    [data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child { display: none !important; }

    @media print {
        header, [data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stDecoration"],
        [data-testid="stNotification"], [data-testid="stForm"], .print-hide, iframe,
        div.element-container:has(> div[data-testid="stDataFrame"]) { display: none !important; }
        .print-only-container { display: block !important; }
        .print-only-container table {
            display: table !important; width: 100% !important; border-collapse: collapse !important;
            font-family: Arial, sans-serif !important; font-size: 11px !important; color: #000 !important;
        }
        .print-only-container th { background-color: #f2f2f2 !important; border: 1px solid #111 !important; padding: 6px !important; font-weight: bold !important; text-align: center !important; }
        .print-only-container td { border: 1px solid #111 !important; padding: 5px !important; text-align: left !important; }
        @page { margin: 8mm; size: A4 landscape; }
    }
    .print-only-container { display: none; }
    </style>
""", unsafe_allow_html=True)

# ==========================================================
# 🛑 STEP 4: LOGIN GATEWAY
# ==========================================================
if st.session_state.user_role is None:
    header_html = """
    <div style="display:flex; align-items:center; gap:20px; margin-bottom:20px; font-family:'Poppins','Inter',sans-serif;
        background: linear-gradient(135deg, #FFFFFF 0%, #F5F7FA 100%); border: 1px solid #DCE3EC; border-radius: 12px; padding: 16px 20px;">
        <div style="flex-shrink:0; width:70px; height:70px; display:flex; align-items:center; justify-content:center;
            border-radius:10px; box-shadow:0 4px 12px rgba(15,42,74,0.18); border:2px solid #C9973F;">
            <h1 style="margin:0;">🏛️</h1>
        </div>
        <div style="display:flex; flex-direction:column; justify-content:center;">
            <h1 style="margin:0 !important; padding:0 !important; color:#0F2A4A; font-size:30px; font-weight:700; border:none !important;">
                Department Approval &amp; Assignment System</h1>
            <h3 style="margin:2px 0 0 0 !important; padding:0 !important; color:#A97A25; font-weight:600 !important; font-size:15px;">
                Entry → Approval → Department-wise Distribution</h3>
        </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    login_col, _ = st.columns([1, 1.4])
    with login_col:
        st.subheader("🔐 Login")
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        if submitted:
            creds = st.session_state.credentials
            entry = creds.get(u.strip())
            if entry and entry.get("password") == p:
                st.session_state.user_role = entry.get("role")
                st.session_state.username = u.strip()
                st.session_state.user_department = entry.get("department")
                st.success(f"स्वागत है, {u.strip()}!")
                time.sleep(0.4)
                st.rerun()
            else:
                st.error("❌ गलत Username या Password। कृपया दोबारा कोशिश करें।")
        st.caption("Default admin login → **admin / admin123** (पहली बार login करने के बाद P6 → Admin Panel से password बदल लें)")
    st.stop()

# ==========================================================
# 🧭 STEP 5: SIDEBAR NAVIGATION
# ==========================================================
role = st.session_state.user_role
username = st.session_state.username
user_dept = st.session_state.user_department

with st.sidebar:
    st.markdown(f"### 👤 {username}")
    st.caption(st.session_state.credentials.get(username, {}).get("label", role))
    st.markdown("---")
    if role == "admin":
        panel_options = [
            "P1 — Entry & Upload",
            "P2 — Approve List",
            "P3 — Approved List",
            "P4 — Department Panel",
            "P5 — Print Panel",
            "P6 — Admin Panel",
        ]
    else:
        panel_options = ["P4 — My Department List"]
    choice = st.radio("Navigate Panels", panel_options, label_visibility="visible")
    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.user_role = None
        st.session_state.username = None
        st.session_state.user_department = None
        st.rerun()

db = load_db()

# ==========================================================
# 📝 P1 — ENTRY & UPLOAD  (Admin only)
# ==========================================================
if choice == "P1 — Entry & Upload":
    st.header("📝 P1 — Data Entry & Upload")
    mode = st.radio("तरीका चुनें", ["✍️ Single Entry (Form)", "📤 Bulk Upload (CSV/Excel)"], horizontal=True)

    if mode == "✍️ Single Entry (Form)":
        with st.form("single_entry_form"):
            st.caption("नीचे जितने columns भरने हैं भरें — बाकी खाली छोड़ सकते हैं।")
            values = {}
            cols = st.columns(3)
            for i, col_name in enumerate(DEFAULT_COLUMNS):
                with cols[i % 3]:
                    values[col_name] = st.text_input(col_name, key=f"p1_field_{col_name}")
            submit_entry = st.form_submit_button("➕ Submit for Approval", type="primary", use_container_width=True)
        if submit_entry:
            if not any(str(v).strip() for v in values.values()):
                st.warning("⚠️ कृपया कम से कम एक फ़ील्ड भरें।")
            else:
                new_row = {c: "" for c in ALL_COLUMNS}
                new_row.update(values)
                new_row["Status"] = "Pending"
                new_row["Submitted By"] = username
                new_row["Submitted On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                db = pd.concat([db, pd.DataFrame([new_row])], ignore_index=True)
                save_db(db)
                st.success("✅ Entry सफलतापूर्वक Submit हुई — अब यह P2 (Approve List) में Admin approval के लिए दिखेगी।")
                st.balloons()

    else:
        st.info("CSV या Excel (.csv/.xlsx/.xls) फ़ाइल अपलोड करें। कॉलम नाम ऊपर वाली list से मैच होंगे तो अपने आप भर जाएंगे — बाकी खाली रहेंगे।")
        up_file = st.file_uploader("फ़ाइल चुनें", type=["csv", "xlsx", "xls"])
        if up_file is not None:
            try:
                raw_df = read_uploaded_table(up_file)
                if raw_df.empty:
                    st.error("❌ फ़ाइल में डेटा नहीं मिला या फ़ॉर्मेट पढ़ा नहीं जा सका।")
                else:
                    st.write(f"पहचाने गए {raw_df.shape[0]} rows, {raw_df.shape[1]} columns। नीचे preview:")
                    st.dataframe(raw_df.head(20), use_container_width=True)
                    if st.button("📥 इन सभी Rows को Pending List में जोड़ें", type="primary"):
                        aligned = pd.DataFrame(columns=ALL_COLUMNS)
                        for c in DEFAULT_COLUMNS:
                            aligned[c] = raw_df[c] if c in raw_df.columns else ""
                        aligned["Status"] = "Pending"
                        aligned["Assigned Department"] = ""
                        aligned["Submitted By"] = username
                        aligned["Submitted On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        aligned["Approved By"] = ""
                        aligned["Approved On"] = ""
                        db = pd.concat([db, aligned], ignore_index=True)
                        save_db(db)
                        st.success(f"✅ {aligned.shape[0]} rows जोड़ दी गई हैं — अब P2 में Approval के लिए उपलब्ध हैं।")
                        st.balloons()
            except Exception as e:
                st.error(f"फ़ाइल पढ़ने में समस्या: {e}")

# ==========================================================
# ✅ P2 — APPROVE LIST  (Admin only)
# ==========================================================
elif choice == "P2 — Approve List":
    st.header("✅ P2 — Pending List (Approve Karein)")
    pending = db[db["Status"] == "Pending"].copy()
    if pending.empty:
        st.info("📭 फ़िलहाल कोई Pending entry नहीं है।")
    else:
        st.caption(f"कुल {len(pending)} entries Approval का इंतज़ार कर रही हैं। हर entry के सामने Department चुनें, फिर 'Select' टिक करें और Approve दबाएँ।")
        pending.insert(0, "Select", False)
        dept_options = st.session_state.departments
        display_cols = ["Select", "Student Name", "Father Name", "Mobile Number", "Assigned Department", "Submitted By", "Submitted On"]
        display_cols = [c for c in display_cols if c in pending.columns]
        edited = st.data_editor(
            pending[display_cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Select": st.column_config.CheckboxColumn("Select"),
                "Assigned Department": st.column_config.SelectboxColumn("Assign to Department", options=dept_options, required=False),
            },
            key="p2_approve_editor",
        )
        with st.expander("🔍 पूरी row details देखें (सभी columns)"):
            st.dataframe(pending.drop(columns=["Select"]), use_container_width=True)

        if st.button("✅ चुनी गई Entries Approve करें", type="primary"):
            selected_idx = edited[edited["Select"] == True].index
            if len(selected_idx) == 0:
                st.warning("⚠️ पहले कम से कम एक entry Select करें।")
            else:
                missing_dept = [i for i in selected_idx if not str(edited.loc[i, "Assigned Department"]).strip()]
                if missing_dept:
                    st.error("❌ Approve करने से पहले हर चुनी गई entry के लिए एक Department चुनना ज़रूरी है।")
                else:
                    for i in selected_idx:
                        db.at[i, "Status"] = "Approved"
                        db.at[i, "Assigned Department"] = edited.loc[i, "Assigned Department"]
                        db.at[i, "Approved By"] = username
                        db.at[i, "Approved On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                    save_db(db)
                    st.success(f"🎉 {len(selected_idx)} entries Approve होकर संबंधित Department को भेज दी गई हैं।")
                    st.balloons()
                    st.rerun()

# ==========================================================
# 📋 P3 — APPROVED LIST
# ==========================================================
elif choice == "P3 — Approved List":
    st.header("📋 P3 — Approved List (सभी Departments)")
    approved = db[db["Status"] == "Approved"].copy()
    if approved.empty:
        st.info("📭 अभी तक कोई entry Approve नहीं हुई है।")
    else:
        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            dept_filter = st.selectbox("Department से फ़िल्टर करें", ["सभी"] + st.session_state.departments)
        with f_col2:
            search = st.text_input("🔎 Student Name / Roll No. / Unique ID से खोजें")

        view = approved.copy()
        if dept_filter != "सभी":
            view = view[view["Assigned Department"] == dept_filter]
        if search.strip():
            s = search.strip().lower()
            mask = view.apply(lambda r: s in " ".join(str(v).lower() for v in r.values), axis=1)
            view = view[mask]

        st.caption(f"कुल {len(view)} Approved records मिले।")
        st.dataframe(view, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("🖨️ Export / Print")
        chosen_cols = st.multiselect("Print/Export के लिए Columns चुनें", ALL_COLUMNS,
                                      default=["Student Name", "Father Name", "Roll No.", "Subject", "Assigned Department", "Status"])
        if chosen_cols:
            print_df = view[chosen_cols]
            d_col1, d_col2 = st.columns(2)
            with d_col1:
                st.download_button("⬇️ CSV Download करें", print_df.to_csv(index=False).encode("utf-8-sig"),
                                    file_name="approved_list.csv", mime="text/csv", use_container_width=True)
            with d_col2:
                if st.button("🖨️ Print View तैयार करें", use_container_width=True):
                    table_html = print_df.to_html(index=False, escape=True)
                    st.markdown(f'<div class="print-only-container">{table_html}</div>', unsafe_allow_html=True)
                    st.info("Print view नीचे तैयार है — अब Browser से Ctrl+P / Cmd+P दबाएँ (सिर्फ़ यह टेबल print होगी)।")
                    st.markdown(f'<div class="print-hide">{print_df.to_html(index=False, escape=True)}</div>', unsafe_allow_html=True)

# ==========================================================
# 🏢 P4 — DEPARTMENT PANEL
# ==========================================================
elif choice in ("P4 — Department Panel", "P4 — My Department List"):
    st.header("🏢 P4 — Department-wise List")
    approved = db[db["Status"] == "Approved"].copy()

    if role == "admin":
        target_dept = st.selectbox("Department चुनें", st.session_state.departments)
    else:
        target_dept = user_dept
        st.caption(f"आप लॉगिन हैं: **{target_dept}** — आपको सिर्फ़ इसी Department को Assign की गई entries दिखेंगी।")

    dept_view = approved[approved["Assigned Department"] == target_dept]
    st.subheader(f"📂 {target_dept} — कुल {len(dept_view)} Students")
    if dept_view.empty:
        st.info("📭 इस Department को अभी तक कोई entry Assign नहीं हुई है।")
    else:
        st.dataframe(dept_view, use_container_width=True, hide_index=True)
        st.download_button(f"⬇️ {target_dept} की List Download करें",
                            dept_view.to_csv(index=False).encode("utf-8-sig"),
                            file_name=f"{target_dept.replace(' ', '_')}_list.csv", mime="text/csv")

# ==========================================================
# 🖨️ P5 — PRINT PANEL  (Admin only)
# ==========================================================
elif choice == "P5 — Print Panel":
    st.header("🖨️ P5 — Print Panel")
    st.caption("यहाँ से आप किसी भी List को अपने institute के letterhead-style header के साथ खूबसूरती से Print कर सकते हैं।")

    # ---- Print Header Customizer ----
    st.subheader("📝 Print Header Customizer")
    if "ph_line1" not in st.session_state:
        st.session_state.ph_line1 = "Department Approval & Assignment System"
    if "ph_line2" not in st.session_state:
        st.session_state.ph_line2 = "Entry → Approval → Department-wise Distribution"
    if "ph_size1" not in st.session_state:
        st.session_state.ph_size1 = 22
    if "ph_size2" not in st.session_state:
        st.session_state.ph_size2 = 13
    if "ph_color1" not in st.session_state:
        st.session_state.ph_color1 = "#0F2A4A"
    if "ph_color2" not in st.session_state:
        st.session_state.ph_color2 = "#A97A25"

    ph_c1, ph_c2 = st.columns(2)
    with ph_c1:
        st.session_state.ph_line1 = st.text_input("Header Line 1 (Institute / Report Title)", value=st.session_state.ph_line1)
        s1a, s1b = st.columns(2)
        with s1a:
            st.session_state.ph_size1 = st.slider("Line 1 Font Size (px)", 12, 40, st.session_state.ph_size1)
        with s1b:
            st.session_state.ph_color1 = st.color_picker("Line 1 Color", st.session_state.ph_color1)
    with ph_c2:
        st.session_state.ph_line2 = st.text_input("Header Line 2 (Subtitle / Address)", value=st.session_state.ph_line2)
        s2a, s2b = st.columns(2)
        with s2a:
            st.session_state.ph_size2 = st.slider("Line 2 Font Size (px)", 8, 30, st.session_state.ph_size2)
        with s2b:
            st.session_state.ph_color2 = st.color_picker("Line 2 Color", st.session_state.ph_color2)

    st.markdown(
        f"""
        <div style="border:1px solid var(--pg-border); border-radius:10px; padding:14px 18px;
            background:var(--pg-surface); text-align:center; margin-top:6px;">
            <div style="font-family:'Poppins','Inter',sans-serif; font-weight:700;
                font-size:{st.session_state.ph_size1}px; color:{st.session_state.ph_color1};">
                {st.session_state.ph_line1 or "&nbsp;"}
            </div>
            <div style="font-family:'Inter',sans-serif; font-weight:600;
                font-size:{st.session_state.ph_size2}px; color:{st.session_state.ph_color2}; margin-top:4px;">
                {st.session_state.ph_line2 or "&nbsp;"}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ---- Data selection ----
    st.subheader("📂 Data चुनें")
    d_col1, d_col2, d_col3 = st.columns([1, 1, 2])
    with d_col1:
        status_choice = st.selectbox("Status", ["Approved", "Pending", "सभी"])
    with d_col2:
        if role == "admin":
            dept_choice = st.selectbox("Department", ["सभी"] + st.session_state.departments)
        else:
            dept_choice = user_dept
            st.caption(f"Department: **{user_dept}**")
    with d_col3:
        pp_search = st.text_input("🔎 Student Name / Roll No. / Unique ID से खोजें", key="pp_search")

    pp_view = db.copy()
    if status_choice != "सभी":
        pp_view = pp_view[pp_view["Status"] == status_choice]
    if role != "admin":
        pp_view = pp_view[pp_view["Assigned Department"] == user_dept]
    elif dept_choice != "सभी":
        pp_view = pp_view[pp_view["Assigned Department"] == dept_choice]
    if pp_search.strip():
        s = pp_search.strip().lower()
        pp_view = pp_view[pp_view.apply(lambda r: s in " ".join(str(v).lower() for v in r.values), axis=1)]

    st.caption(f"कुल {len(pp_view)} records मिले।")

    if pp_view.empty:
        st.info("📭 चुने गए Filters से कोई record नहीं मिला।")
    else:
        pp_cols = st.multiselect(
            "Print के लिए Columns चुनें", ALL_COLUMNS,
            default=["Student Name", "Father Name", "Roll No.", "Subject", "Assigned Department", "Status"],
            key="pp_cols",
        )
        if pp_cols:
            pp_print_df = pp_view[pp_cols]

            st.markdown("---")
            st.subheader("👁️ Preview")
            st.dataframe(pp_print_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🖨️ Print / Export")
            pr_col1, pr_col2 = st.columns(2)
            with pr_col1:
                st.download_button(
                    "⬇️ CSV Download करें",
                    pp_print_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="print_panel_list.csv", mime="text/csv", use_container_width=True,
                )
            with pr_col2:
                do_print = st.button("🖨️ Print View तैयार करें", type="primary", use_container_width=True)

            if do_print:
                table_html = pp_print_df.to_html(index=False, escape=True)
                header_html = f"""
                <div style="text-align:center; margin-bottom:14px;">
                    <div style="font-family:Arial, sans-serif; font-weight:700;
                        font-size:{st.session_state.ph_size1}px; color:{st.session_state.ph_color1};">
                        {st.session_state.ph_line1}
                    </div>
                    <div style="font-family:Arial, sans-serif; font-weight:600;
                        font-size:{st.session_state.ph_size2}px; color:{st.session_state.ph_color2}; margin-top:2px;">
                        {st.session_state.ph_line2}
                    </div>
                    <hr style="border:none; border-top:2px solid {st.session_state.ph_color1}; margin-top:10px;">
                </div>
                """
                st.markdown(f'<div class="print-only-container">{header_html}{table_html}</div>', unsafe_allow_html=True)
                st.info("Print view नीचे तैयार है — अब Browser से Ctrl+P / Cmd+P दबाएँ (सिर्फ़ header + यह टेबल print होगी)।")
                st.markdown(f'<div class="print-hide">{header_html}{table_html}</div>', unsafe_allow_html=True)
        else:
            st.warning("⚠️ Print करने के लिए कम से कम एक Column चुनें।")

# ==========================================================
# 🛠️ P6 — ADMIN PANEL  (Admin only)
# ==========================================================
elif choice == "P6 — Admin Panel":
    st.header("🛠️ P6 — Admin Panel")

    tab_dash, tab_users, tab_depts, tab_data = st.tabs(
        ["📊 Dashboard", "👤 Users / Credentials", "🏢 Departments", "🗄️ Database"]
    )

    with tab_dash:
        c1, c2, c3 = st.columns(3)
        c1.metric("कुल Records", len(db))
        c2.metric("Pending", int((db["Status"] == "Pending").sum()))
        c3.metric("Approved", int((db["Status"] == "Approved").sum()))
        if not db.empty:
            st.markdown("**Department-wise Approved Count:**")
            dept_counts = db[db["Status"] == "Approved"]["Assigned Department"].value_counts()
            st.dataframe(dept_counts.rename_axis("Department").reset_index(name="Count"), use_container_width=True, hide_index=True)

    with tab_users:
        st.subheader("मौजूदा Users")
        creds = st.session_state.credentials
        users_table = pd.DataFrame([
            {"Username": u, "Role": v.get("role"), "Department": v.get("department", "-"), "Label": v.get("label", "")}
            for u, v in creds.items()
        ])
        st.dataframe(users_table, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("**➕ नया Department User बनाएँ**")
        with st.form("new_user_form"):
            nu_col1, nu_col2 = st.columns(2)
            with nu_col1:
                new_username = st.text_input("Username")
                new_password = st.text_input("Password")
            with nu_col2:
                new_dept = st.selectbox("Department", st.session_state.departments)
                new_label = st.text_input("Display Label (optional)", value="")
            add_user_btn = st.form_submit_button("➕ User जोड़ें", type="primary")
        if add_user_btn:
            if not new_username.strip() or not new_password.strip():
                st.warning("⚠️ Username और Password दोनों भरना ज़रूरी है।")
            elif new_username.strip() in creds:
                st.error("❌ यह Username पहले से मौजूद है।")
            else:
                creds[new_username.strip()] = {
                    "password": new_password,
                    "role": "department",
                    "department": new_dept,
                    "label": new_label.strip() or f"🏢 {new_dept}",
                }
                st.session_state.credentials = creds
                save_credentials(creds)
                st.success(f"✅ User '{new_username.strip()}' बन गया — यह सिर्फ़ '{new_dept}' का P4 देख पाएगा।")
                st.rerun()

        st.markdown("---")
        st.markdown("**🗑️ User हटाएँ**")
        deletable_users = [u for u in creds.keys() if u != "admin"]
        if deletable_users:
            del_user = st.selectbox("हटाने के लिए User चुनें", deletable_users)
            if st.button("🗑️ Delete User", type="secondary"):
                creds.pop(del_user, None)
                st.session_state.credentials = creds
                save_credentials(creds)
                st.success(f"🗑️ User '{del_user}' हटा दिया गया।")
                st.rerun()
        else:
            st.caption("कोई अतिरिक्त User नहीं है (Admin नहीं हटाया जा सकता)।")

        st.markdown("---")
        st.markdown("**🔑 Admin Password बदलें**")
        with st.form("change_admin_pw"):
            cur_pw = st.text_input("Current Password", type="password")
            new_pw = st.text_input("New Password", type="password")
            change_btn = st.form_submit_button("Password अपडेट करें", type="primary")
        if change_btn:
            if creds.get("admin", {}).get("password") != cur_pw:
                st.error("❌ Current Password ग़लत है।")
            elif not new_pw.strip():
                st.warning("⚠️ नया Password खाली नहीं हो सकता।")
            else:
                creds["admin"]["password"] = new_pw
                st.session_state.credentials = creds
                save_credentials(creds)
                st.success("✅ Admin Password अपडेट हो गया।")

    with tab_depts:
        st.subheader("Departments की List")
        depts = st.session_state.departments
        st.dataframe(pd.DataFrame({"Department": depts}), use_container_width=True, hide_index=True)
        add_col, del_col = st.columns(2)
        with add_col:
            new_dept_name = st.text_input("नया Department नाम")
            if st.button("➕ Department जोड़ें", type="primary"):
                if new_dept_name.strip() and new_dept_name.strip() not in depts:
                    depts.append(new_dept_name.strip())
                    st.session_state.departments = depts
                    save_departments(depts)
                    st.success(f"✅ '{new_dept_name.strip()}' जोड़ दिया गया।")
                    st.rerun()
                else:
                    st.warning("⚠️ नाम खाली है या पहले से मौजूद है।")
        with del_col:
            if depts:
                rm_dept = st.selectbox("Department हटाएँ", depts, key="rm_dept_select")
                if st.button("🗑️ हटाएँ", type="secondary"):
                    depts.remove(rm_dept)
                    st.session_state.departments = depts
                    save_departments(depts)
                    st.success(f"🗑️ '{rm_dept}' हटा दिया गया।")
                    st.rerun()

    with tab_data:
        st.subheader("पूरा Database")
        st.dataframe(db, use_container_width=True, hide_index=True)
        st.download_button("⬇️ पूरा Database Backup (CSV) Download करें",
                            db.to_csv(index=False).encode("utf-8-sig"),
                            file_name="full_database_backup.csv", mime="text/csv")
