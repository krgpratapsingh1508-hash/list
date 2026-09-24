import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
import re
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
DEPT_CLEANUP_FLAG = "approval_workflow_dept_cleanup_done.flag"   # purani 4 default Departments ek baar hatane ka nishaan
FACULTY_FILE = "approval_workflow_faculty.csv"

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
SYSTEM_COLUMNS = ["Status", "Assigned Department", "Submitted By", "Submitted On", "Approved By", "Approved On", "Show In Panels"]
ALL_COLUMNS = DEFAULT_COLUMNS + SYSTEM_COLUMNS

# Mobile No. khaali ho to P3 (dikhane ke liye) aur P5 header (print ke liye) me yah line aati hai. Data me ye save nahi hoti.
MOBILE_BLANK = "_" * 14

# P1 me har upload ke saath chuna jaata hai ki wo kin panels me dikhe (P1/P6 hamesha admin ke liye hain)
PANEL_OPTIONS = {
    "P2": "P2 — List",
    "P4": "P4 — Department Panel",
    "P5": "P5 — Print Panel",
}

# "Current Year" (course year) ke liye standard 5 values — "1st Year" hi asli/canonical form hai.
COURSE_YEAR_OPTIONS = ["1st Year", "2nd Year", "3rd Year", "4th Year", "5th Year"]
# P5 Print Header me "FIRST YEAR" jaise pooray-word, capital style me dikhane ke liye
COURSE_YEAR_PRINT_LABELS = {
    "1st Year": "FIRST YEAR", "2nd Year": "SECOND YEAR", "3rd Year": "THIRD YEAR",
    "4th Year": "FOURTH YEAR", "5th Year": "FIFTH YEAR",
}
# P5 Print Header ke "Course" dropdown ke liye common course names
COURSE_NAME_OPTIONS = ["B.A.", "B.Com.", "B.Sc.", "BBA", "BCA", "B.Ed.", "M.A.", "M.Com.", "M.Sc.", "LL.B.", "PGDCA"]
# Bahut saare likhne ke tareeke (First Year, 1, I Year, Year-1, आदि) — sabko upar wali canonical form me badalne ke liye.
_COURSE_YEAR_ALIASES = {
    "1st year": "1st Year", "first year": "1st Year", "1": "1st Year", "1st": "1st Year",
    "i year": "1st Year", "year 1": "1st Year", "year1": "1st Year", "year-1": "1st Year", "प्रथम वर्ष": "1st Year",
    "2nd year": "2nd Year", "second year": "2nd Year", "2": "2nd Year", "2nd": "2nd Year",
    "ii year": "2nd Year", "year 2": "2nd Year", "year2": "2nd Year", "year-2": "2nd Year", "द्वितीय वर्ष": "2nd Year",
    "3rd year": "3rd Year", "third year": "3rd Year", "3": "3rd Year", "3rd": "3rd Year",
    "iii year": "3rd Year", "year 3": "3rd Year", "year3": "3rd Year", "year-3": "3rd Year", "तृतीय वर्ष": "3rd Year",
    "4th year": "4th Year", "fourth year": "4th Year", "4": "4th Year", "4th": "4th Year",
    "iv year": "4th Year", "year 4": "4th Year", "year4": "4th Year", "year-4": "4th Year", "चतुर्थ वर्ष": "4th Year",
    "5th year": "5th Year", "fifth year": "5th Year", "5": "5th Year", "5th": "5th Year",
    "v year": "5th Year", "year 5": "5th Year", "year5": "5th Year", "year-5": "5th Year", "पंचम वर्ष": "5th Year",
}


def normalize_course_year(value):
    """'First Year', 'second year', '2', 'II Year' jaise kisi bhi likhne ke tareeke ko
    canonical '1st Year' / '2nd Year' / ... form me badal deta hai. Na-pehchaana gaya text jaisa hai waisa hi rehta hai."""
    s = str(value).strip()
    if not s:
        return s
    key = re.sub(r"\s+", " ", s.lower().replace(".", "").strip())
    return _COURSE_YEAR_ALIASES.get(key, s)

DEFAULT_DEPARTMENTS = [
    "Hindi", "Sanskrit", "Urdu", "English",
    "Economics", "History", "Philosophy", "Political Science",
    "Psychology", "Sociology", "Geography", "Drawing and Painting",
    "Music & Dance", "Home Science", "Chemistry", "Physics",
    "Mathematics", "Zoology", "Botany", "Biotechnology",
    "Computer Science", "Commerce & Management", "Institute of Law",
]
# App ki purani (shuruati) default list — agar saved list bilkul yahi hai (kabhi badli nahi gayi), to nayi list se replace hogi
OLD_DEFAULT_DEPARTMENTS = ["Examination Department", "Accounts Department", "Scholarship Department", "Registrar Office"]

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
        except pd.errors.EmptyDataError:
            df = pd.DataFrame(columns=ALL_COLUMNS)
        except Exception as e:
            st.error(f"❌ Database फ़ाइल `{DB_FILE}` पढ़ी नहीं जा सकी: {e}. "
                     "फ़ाइल को Excel/किसी दूसरे program में बंद करें या ठीक करें — तब तक app रुकी रहेगी ताकि पुराना data overwrite न हो।")
            st.stop()
    else:
        df = pd.DataFrame(columns=ALL_COLUMNS)
    for c in ALL_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[ALL_COLUMNS]


def save_db(df):
    df.to_csv(DB_FILE, index=False)


def filter_for_panel(df, panel_code):
    """Sirf wahi rows lautata hai jinhe P1 me is panel (P2/P3/P4/P5) ke liye tick kiya gaya tha.
    Purane records jinme 'Show In Panels' khaali hai, sabhi panels me dikhte rahenge."""
    if df.empty:
        return df
    col = df["Show In Panels"].astype(str).str.strip()
    ok = (col == "") | col.apply(lambda v: panel_code in [x.strip() for x in v.split(",")])
    return df[ok]


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
                saved = json.load(f)
            if saved == OLD_DEFAULT_DEPARTMENTS:          # kabhi customize nahi ki gayi purani default list
                new_list = list(DEFAULT_DEPARTMENTS)
                save_departments(new_list)
                return new_list
            return saved
        except Exception:
            pass
    return list(DEFAULT_DEPARTMENTS)


def save_departments(depts):
    with open(DEPT_FILE, "w", encoding="utf-8") as f:
        json.dump(depts, f, ensure_ascii=False, indent=4)


def remove_old_default_departments():
    """Purani 4 default Departments (Examination/Accounts/Scholarship/Registrar) ek baar hata deta hai.
    Baad me agar koi inhe khud dobara jode to wo hatayi nahi jaati (flag file ki wajah se)."""
    if os.path.exists(DEPT_CLEANUP_FLAG):
        return
    cleaned = [d for d in st.session_state.departments if d not in OLD_DEFAULT_DEPARTMENTS]
    if not cleaned:
        cleaned = list(DEFAULT_DEPARTMENTS)
    if cleaned != st.session_state.departments:
        st.session_state.departments = cleaned
        save_departments(cleaned)
    try:
        with open(DEPT_CLEANUP_FLAG, "w", encoding="utf-8") as f:
            f.write("done")
    except Exception:
        pass


# NOTE: "Department" = Allotted Class (purana naam, data na tootne ke liye); "Tutor Department" = P3 ka naya DEPARTMENT column
FACULTY_COLUMNS = ["Department", "Faculty Name", "Designation", "Mobile Number", "Number of Students", "Tutor Department"]


def load_faculty():
    if os.path.exists(FACULTY_FILE):
        try:
            df = pd.read_csv(FACULTY_FILE, dtype=str).fillna("")
        except Exception:
            df = pd.DataFrame(columns=FACULTY_COLUMNS)
    else:
        df = pd.DataFrame(columns=FACULTY_COLUMNS)
    for c in FACULTY_COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[FACULTY_COLUMNS]


def save_faculty(df):
    df.to_csv(FACULTY_FILE, index=False)


# ==========================================================
# 🔄 UNIVERSAL UPLOAD CONVERTER (P1 style): CSV / XLSX / असली-पुराना XLS /
# Excel-XML / HTML "fake xls" — सब कुछ एक साफ़ DataFrame में
# फ़ाइल का असली type extension से नहीं, अंदर के content (signature) से पहचाना जाता है।
# ==========================================================

def _clean_raw_table(raw):
    """खाली rows/columns हटाओ, ऊपर के title-rows छोड़ो, सही header row ढूंढो।"""
    raw = raw.fillna("").astype(str).apply(lambda col: col.str.strip())
    raw = raw.loc[:, (raw != "").any(axis=0)]
    raw = raw.loc[(raw != "").any(axis=1)].reset_index(drop=True)
    if raw.empty:
        return pd.DataFrame()
    counts = (raw != "").sum(axis=1)
    hdr = int(counts[counts >= max(1, counts.max() * 0.5)].index[0])
    header = [h if h else f"Unnamed_{i}" for i, h in enumerate(raw.iloc[hdr].tolist())]
    body = raw.iloc[hdr + 1:].reset_index(drop=True)
    body.columns = header
    return body


def _best_frame(frames):
    """कई sheets/tables में से सबसे ज़्यादा data वाली चुनो।"""
    best, best_cells = pd.DataFrame(), 0
    for f in frames:
        cleaned = _clean_raw_table(f)
        cells = cleaned.shape[0] * cleaned.shape[1]
        if cells > best_cells:
            best, best_cells = cleaned, cells
    return best


_UPLOAD_DIAG = {"info": ""}


def _decode_text(raw):
    for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="ignore"), "latin-1"


def _parse_spreadsheetml(text):
    """Excel 2003 'XML Spreadsheet' (.xls नाम से save हुई XML फ़ाइल)।"""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(text.encode("utf-8"))
    frames = []
    for ws in root.iter():
        if ws.tag.split("}")[-1] != "Worksheet":
            continue
        rows = []
        for row in ws.iter():
            if row.tag.split("}")[-1] != "Row":
                continue
            cells = []
            for cell in row:
                if cell.tag.split("}")[-1] != "Cell":
                    continue
                idx = None
                for k, v in cell.attrib.items():
                    if k.split("}")[-1] == "Index":
                        idx = int(v)
                if idx:
                    cells += [""] * (idx - 1 - len(cells))
                data = next((d for d in cell if d.tag.split("}")[-1] == "Data"), None)
                cells.append("".join(data.itertext()) if data is not None else "")
            rows.append(cells)
        if rows:
            width = max(len(r) for r in rows)
            frames.append(pd.DataFrame([r + [""] * (width - len(r)) for r in rows]))
    return frames


def _parse_delimited_text(raw):
    text, enc = _decode_text(raw)
    first = "\n".join(text.splitlines()[:20])
    seps = {"\t": first.count("\t"), ",": first.count(","), ";": first.count(";"), "|": first.count("|")}
    sep = max(seps, key=seps.get)
    df_t = pd.read_csv(io.StringIO(text), sep=sep, engine="python", dtype=str,
                        header=None, on_bad_lines="skip")
    return [df_t]


def read_uploaded_table(uploaded_file):
    """CSV/XLSX/असली पुराना XLS/Excel-XML/HTML "fake xls" — किसी भी फ़ॉर्मेट की फ़ाइल को
    एक साफ़ DataFrame (सब text) में बदलता है। कई college/university software 'Excel' export
    करते वक़्त असल में xlsx, या HTML table, या XML file को ही .xls नाम दे देते हैं —
    इसलिए extension पर भरोसा करने के बजाय फ़ाइल के असली binary content से type पहचाना जाता है।
    """
    name = uploaded_file.name.lower()
    raw = uploaded_file.getvalue()

    if name.endswith(".csv"):
        for enc in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc).fillna("")
                if not df.empty:
                    return df
            except UnicodeDecodeError:
                continue
            except pd.errors.EmptyDataError:
                return pd.DataFrame()
        return pd.DataFrame()

    if not name.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.DataFrame()

    head = raw[:8192].lstrip()
    head_l = head.lower()
    frames, kind = [], "unknown"
    try:
        if raw[:4] == b"PK\x03\x04":                                          # असली .xlsx
            kind = "xlsx"
            frames = list(pd.read_excel(io.BytesIO(raw), engine="openpyxl", dtype=str,
                                         header=None, sheet_name=None).values())
        elif raw[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":                   # असली पुराना .xls
            kind = "xls"
            try:
                frames = list(pd.read_excel(io.BytesIO(raw), engine="xlrd", dtype=str,
                                             header=None, sheet_name=None).values())
            except ImportError:
                raise ValueError(
                    "यह पुराने फ़ॉर्मेट (.xls) की असली Excel फ़ाइल है, इसे पढ़ने के लिए सर्वर पर "
                    "'xlrd' पैकेज इंस्टॉल होना ज़रूरी है (pip install xlrd)।"
                )
        elif b"urn:schemas-microsoft-com:office:spreadsheet" in raw[:8192]:    # Excel 2003 XML
            kind = "spreadsheetml-xml"
            frames = _parse_spreadsheetml(_decode_text(raw)[0])
        elif head_l.startswith(b"<") or b"<table" in head_l:                  # HTML वाली "fake xls"
            kind = "html"
            text = _decode_text(raw)[0]
            for t in pd.read_html(io.StringIO(text)):
                if not isinstance(t.columns, pd.RangeIndex):
                    hdr_row = [str(c[-1] if isinstance(c, tuple) else c) for c in t.columns]
                    t = pd.concat([pd.DataFrame([hdr_row]),
                                   t.set_axis(range(t.shape[1]), axis=1).astype(str)], ignore_index=True)
                frames.append(t)
        else:                                                                  # plain CSV/TSV text
            kind = "text"
            frames = _parse_delimited_text(raw)
    except Exception as parse_err:
        _UPLOAD_DIAG["info"] = f"type={kind}, size={len(raw)} bytes, parse error: {parse_err}"
        raise ValueError(
            f"फ़ाइल पढ़ने में समस्या (पहचाना गया type: {kind}): {parse_err}. कृपया फ़ाइल को Excel/किसी "
            f"भी spreadsheet software में खोलकर 'Save As' → .xlsx फ़ॉर्मेट में दोबारा Save करें।"
        )

    df_x = _best_frame(frames)
    preview = raw[:120].decode("latin-1", errors="replace").replace("\n", " ").replace("\r", " ")
    _UPLOAD_DIAG["info"] = (f"type={kind}, size={len(raw)} bytes, sheets/tables={len(frames)}, "
                             f"rows x cols after cleanup={df_x.shape}, file start: {preview!r}")
    return df_x


# ==========================================================
# 🧠 SMART COLUMN MATCHING: अपलोड फ़ाइल के headers अलग-अलग तरीकों से लिखे हो सकते
# हैं (जैसे "DOB", "Email", "Mobile No", "Scholarship") — इन्हें सही internal
# column नाम से automatically match करके डेटा गायब होने से बचाता है।
# ==========================================================

def _normalize_col_name(name):
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


MANUAL_COLUMN_ALIASES = {
    "enrollmentno": "Enrollment No.", "enrollmentnumber": "Enrollment No.",
    "enrollmentnum": "Enrollment No.", "universityenrollmentno": "Enrollment No.",
    "applicationenrollmentno": "Application Enrollment No.",
    "dob": "Date of Birth", "dateofbirth": "Date of Birth", "birthdate": "Date of Birth",
    "email": "Email ID", "emailid": "Email ID", "emailaddress": "Email ID", "mailid": "Email ID",
    "mobile": "Mobile Number", "mobileno": "Mobile Number", "mobilenumber": "Mobile Number",
    "phone": "Mobile Number", "phonenumber": "Mobile Number", "contactno": "Mobile Number",
    "scholarship": "Scholarship Name", "scholarshipname": "Scholarship Name",
    "scholarshiptitle": "Scholarship Name",
    "rollno": "Roll No.", "rollnumber": "Roll No.",
    "studentname": "Student Name", "name": "Student Name",
    "fathername": "Father Name", "mothername": "Mother Name",
    "applicationno": "Application Number", "applicationnumber": "Application Number",
    "admissionno": "Admission Application Number", "admissionapplicationno": "Admission Application Number",
    "uniqueid": "Unique ID", "abcid": "Student Abc Id", "studentabcid": "Student Abc Id",
    "admissiondate": "Admission Date", "admissionyear": "Admission Year",
    "admissionsession": "Admission Session", "subjectcode": "Subject Code",
    "currentyear": "Current Year", "admissioncategory": "Admission Category",
    "paymentdate": "Payment Date",
    # आम तौर पर मिलने वाले दूसरे header-नाम
    "fullname": "Student Name", "nameofstudent": "Student Name", "nameofthestudent": "Student Name",
    "studentsname": "Student Name", "candidatename": "Student Name", "nameofcandidate": "Student Name",
    "studentfullname": "Student Name", "applicantname": "Student Name",
    "fathersname": "Father Name", "nameoffather": "Father Name", "fathername": "Father Name",
    "mothersname": "Mother Name", "nameofmother": "Mother Name",
    "mobno": "Mobile Number", "mobnumber": "Mobile Number", "mobilenum": "Mobile Number",
    "contactnumber": "Mobile Number", "phoneno": "Mobile Number", "contact": "Mobile Number",
    "mobilenumber1": "Mobile Number", "studentmobileno": "Mobile Number", "studentmobile": "Mobile Number",
    "majorsubject": "Subject", "majorsub": "Subject", "mainsubject": "Subject",
    "uid": "Unique ID", "uniqueno": "Unique ID", "uniqueidno": "Unique ID",
    "rollnumber": "Roll No.", "rno": "Roll No.",
}


def smart_align_columns(df):
    normalized_lookup = {}
    for internal_col in DEFAULT_COLUMNS:
        normalized_lookup[_normalize_col_name(internal_col)] = internal_col
    for alias_key, alias_target in MANUAL_COLUMN_ALIASES.items():
        normalized_lookup.setdefault(alias_key, alias_target)

    rename_map = {}
    for col in df.columns:
        if col in DEFAULT_COLUMNS:
            continue
        key = _normalize_col_name(col)
        if key in normalized_lookup:
            target = normalized_lookup[key]
            if target in df.columns:
                continue
            rename_map[col] = target
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


# ==========================================================
# 🔐 SESSION STATE INIT
# ==========================================================
if "user_role" not in st.session_state:
    st.session_state.user_role = None
if "username" not in st.session_state:
    st.session_state.username = None
if "user_department" not in st.session_st
