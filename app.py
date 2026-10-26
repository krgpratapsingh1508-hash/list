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
SYSTEM_COLUMNS = ["Status", "Assigned Department", "Submitted By", "Submitted On", "Approved By", "Approved On", "Show In Panels", "Assigned Tutor"]
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


# Allotted Class text (jaise "PGDCA I Year") ke andar se Year-wala hissa dhoondhne ke liye
# — sabse lambe alias pehle, taaki "1st year" jaisa poora phrase "1" se pehle match ho
_ALLOTTED_CLASS_YEAR_PATTERN = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in _COURSE_YEAR_ALIASES.keys()), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def parse_allotted_class(cls_text):
    """'PGDCA I Year' jaise text ko (Course, Canonical Year) me todta hai — jaise ('PGDCA', '1st Year').
    Year na mile to Year khaali rahega; jo Course text bache use jaisa likha hai waisa hi rakha jaata hai
    (jab tak wo COURSE_NAME_OPTIONS ki kisi entry se match na kare, tab canonical spelling use hoti hai)."""
    s = str(cls_text).strip()
    if not s:
        return "", ""
    m = _ALLOTTED_CLASS_YEAR_PATTERN.search(s)
    if m:
        year_canon = normalize_course_year(m.group(1))
        course_part = (s[:m.start()] + " " + s[m.end():]).strip(" ,.-")
    else:
        course_part = s
        year_canon = ""
    course_key = re.sub(r"[^a-z0-9]", "", course_part.lower())
    course_final = course_part
    for _opt in COURSE_NAME_OPTIONS:
        if re.sub(r"[^a-z0-9]", "", _opt.lower()) == course_key:
            course_final = _opt
            break
    return course_final, year_canon


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
FACULTY_COLUMNS = [
    "Department", "Faculty Name", "Designation", "Mobile Number", "Number of Students", "Tutor Department", "Serial No",
    # Major (upar wale "Department"/"Serial No"/"Number of Students") ke alawa baaki Subject Types ke apne column —
    # S.N. / DEPARTMENT / NAME / MOBILE NO. sabke liye SAME rehte hain (ek hi row me), sirf Allotted Class + SERIAL
    # NO. har Subject Type ke liye alag column me save hote hain.
    "Minor Class", "Minor Serial No", "Minor Number of Students",
    "Vocational Class", "Vocational Serial No", "Vocational Number of Students",
    "MDC Class", "MDC Serial No", "MDC Number of Students",
    "PWApCE Class", "PWApCE Serial No", "PWApCE Number of Students",
    # Branch (har Class-line ke saath ek line) — Degree aur Year "Allotted Class" text se alag karke dikhaye jaate hain
    "Branch", "Minor Branch", "Vocational Branch", "MDC Branch", "PWApCE Branch",
]

# Subject Type चुनें dropdown se ye तय होता है ki List Table aur Add/Edit form me
# "Allotted Class" + "SERIAL NO." + "TOTAL" kis column-set ko padhein/likhein
SUBJECT_TYPE_FIELDS = {
    "Major Subject":       {"class": "Department", "branch": "Branch",     "serial": "Serial No",           "total": "Number of Students"},
    "Minor Subjects":      {"class": "Minor Class", "branch": "Minor Branch",     "serial": "Minor Serial No",     "total": "Minor Number of Students"},
    "Vocational Subjects": {"class": "Vocational Class", "branch": "Vocational Branch","serial": "Vocational Serial No","total": "Vocational Number of Students"},
    "MDC Subjects":        {"class": "MDC Class", "branch": "MDC Branch",       "serial": "MDC Serial No",       "total": "MDC Number of Students"},
    "PW/Ap/CE Subjects":   {"class": "PWApCE Class", "branch": "PWApCE Branch",    "serial": "PWApCE Serial No",    "total": "PWApCE Number of Students"},
}


def _p3_total_from_serial(serial_str):
    """'1-10, 5-21' (ya '1-10\\n5-21') jaisi Serial No. range(s) se total students count khud nikaalta hai
    (a-b range ka size, ya sirf ek number ho to 1). Comma/newline se multiple ranges ka jod ho jaata hai.
    Agar kuch bhi valid range/number nahi mila to khaali string lautata hai."""
    s = str(serial_str).strip()
    if not s:
        return ""
    total = 0
    found = False
    for part in re.split(r"[,\n]", s):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bits = part.split("-")
            if len(bits) == 2 and bits[0].strip().isdigit() and bits[1].strip().isdigit():
                a, b = int(bits[0].strip()), int(bits[1].strip())
                if b >= a:
                    total += (b - a + 1)
                    found = True
        elif part.isdigit():
            total += 1
            found = True
    return str(total) if found else ""


def _p3_parse_ranges(serial_str):
    """'1-10, 15' jaisi Serial text ko [(1,10),(15,15)] me badalta hai. Galat part mile to bad=True."""
    out, bad = [], False
    for part in re.split(r"[,\n]", str(serial_str)):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m and int(m.group(1)) >= 1 and int(m.group(2)) >= int(m.group(1)):
            out.append((int(m.group(1)), int(m.group(2))))
        elif part.isdigit() and int(part) >= 1:
            out.append((int(part), int(part)))
        else:
            bad = True
    return out, bad


def _p3_compress(nums):
    """[1,2,3,7,8] -> '1-3, 7-8'"""
    nums = sorted(set(nums))
    if not nums:
        return ""
    parts, a, b = [], nums[0], nums[0]
    for n in nums[1:]:
        if n == b + 1:
            b = n
        else:
            parts.append(f"{a}-{b}" if a != b else str(a))
            a = b = n
    parts.append(f"{a}-{b}" if a != b else str(a))
    return ", ".join(parts)


def _p3_compose_serial(f, t):
    """FROM SERIAL NO. + TO SERIAL NO. -> '1-10' (dono same ho to '5', sirf FROM ho to bhi '5')"""
    f, t = str(f).strip(), str(t).strip()
    if f and t:
        return f if f == t else f"{f}-{t}"
    return f if f else (f"-{t}" if t else "")


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
    "majorsubject": "Branch", "majorsub": "Branch", "mainsubject": "Branch",
    "major": "Branch", "majorbranch": "Branch", "branchmajor": "Branch",
    "streamname": "Branch", "stream": "Branch",
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
if "user_department" not in st.session_state:
    st.session_state.user_department = None
if "credentials" not in st.session_state:
    st.session_state.credentials = load_credentials()
if "departments" not in st.session_state:
    st.session_state.departments = load_departments()
remove_old_default_departments()

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
# ✨ THEME CSS v2 — Buttons / Inputs / Cards / Metrics ka premium look (upar wali theme ke upar lagta hai)
# ==========================================================
st.markdown("""
    <style>
    :root {
        --pg-radius: 12px;
        --pg-shadow-sm: 0 1px 2px rgba(15,42,74,.06), 0 2px 8px rgba(15,42,74,.06);
        --pg-shadow-md: 0 6px 18px rgba(15,42,74,.14);
        --pg-ring: 0 0 0 3px rgba(201,151,63,.28);
    }

    /* ---------- Page background: halka gradient ---------- */
    [data-testid="stAppViewContainer"] {
        background: radial-gradient(1200px 500px at 85% -10%, rgba(201,151,63,.10), transparent 60%),
                    radial-gradient(900px 500px at -10% 0%, rgba(29,74,122,.08), transparent 55%),
                    var(--pg-bg) !important;
    }
    .block-container { max-width: 1250px !important; }

    /* ---------- Buttons (sabhi) ---------- */
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, .stLinkButton > a {
        min-height: 44px !important; border-radius: 12px !important;
        font-family: 'Poppins','Inter',sans-serif !important; font-size: 14.5px !important;
        font-weight: 600 !important; letter-spacing: .15px !important;
        padding: .55rem 1.25rem !important; line-height: 1.2 !important;
        box-shadow: var(--pg-shadow-sm) !important;
        transition: transform .14s ease, box-shadow .18s ease, background .18s ease, border-color .18s ease, filter .18s ease !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover, .stFormSubmitButton > button:hover {
        transform: translateY(-2px) !important; box-shadow: var(--pg-shadow-md) !important;
    }
    .stButton > button:active, .stDownloadButton > button:active, .stFormSubmitButton > button:active {
        transform: translateY(0) scale(.985) !important; box-shadow: var(--pg-shadow-sm) !important; filter: brightness(.96);
    }
    .stButton > button:focus-visible, .stDownloadButton > button:focus-visible { outline: none !important; box-shadow: var(--pg-ring) !important; }
    .stButton > button:disabled, .stDownloadButton > button:disabled {
        opacity: .45 !important; transform: none !important; box-shadow: none !important; cursor: not-allowed !important;
    }
    /* Primary — Navy */
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
        background: linear-gradient(135deg, #0F2A4A 0%, #1D4A7A 60%, #2A5E96 100%) !important;
        color: #fff !important; border: 1px solid rgba(255,255,255,.12) !important;
    }
    .stButton > button[kind="primary"]:hover { box-shadow: 0 8px 22px rgba(15,42,74,.34) !important; filter: brightness(1.06); }
    /* Secondary — Clean outline */
    .stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondary"] {
        background: #fff !important; color: var(--pg-navy) !important; border: 1.5px solid #C5D0DE !important;
    }
    .stButton > button[kind="secondary"]:hover { background: #F2F6FC !important; border-color: var(--pg-navy) !important; }
    /* Download — Gold */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #A97A25 0%, #C9973F 55%, #E0B35E 100%) !important;
        color: #fff !important; border: 1px solid rgba(255,255,255,.25) !important; text-shadow: 0 1px 0 rgba(0,0,0,.12);
    }
    .stDownloadButton > button:hover { box-shadow: 0 8px 22px rgba(201,151,63,.45) !important; filter: brightness(1.05); }

    /* ---------- Table ke Actions: chhote icon buttons (✏️ Edit / 📌 Assign) ---------- */
    [class*="st-key-p3_edit_btn_"] button, [class*="st-key-p3_assign_btn_"] button {
        min-height: 38px !important; padding: .3rem .4rem !important; border-radius: 10px !important; font-size: 17px !important;
    }
    [class*="st-key-p3_edit_btn_"] button { background: #EAF2FF !important; border: 1.5px solid #B9D3F5 !important; color: #1D4A7A !important; }
    [class*="st-key-p3_edit_btn_"] button:hover { background: #1D4A7A !important; border-color: #1D4A7A !important; }
    [class*="st-key-p3_assign_btn_"] button { background: #FFF5DF !important; border: 1.5px solid #EBD39B !important; color: #A97A25 !important; }
    [class*="st-key-p3_assign_btn_"] button:hover { background: #C9973F !important; border-color: #C9973F !important; }
    /* Delete / Cancel / Remove — alag pehchaan */
    [class*="st-key-p3_edit_delete_btn"] button {
        background: #FFF0F0 !important; color: #B42318 !important; border: 1.5px solid #F4B9B4 !important;
    }
    [class*="st-key-p3_edit_delete_btn"] button:hover { background: #B42318 !important; color: #fff !important; border-color: #B42318 !important; }
    [class*="st-key-p3_edit_cancel_btn"] button, [class*="st-key-p3_cancel_assign_"] button {
        background: #F3F5F8 !important; color: #4A5568 !important; border: 1.5px solid #D5DBE4 !important;
    }
    [class*="st-key-p3_add_rmcls_btn"] button, [class*="st-key-p3_edit_rmcls_btn"] button { color: #B42318 !important; border-color: #F0C4C0 !important; }
    [class*="st-key-p3_add_addcls_btn"] button, [class*="st-key-p3_edit_addcls_btn"] button {
        background: #F1FAF4 !important; color: #1B6B3A !important; border: 1.5px dashed #8AC9A0 !important;
    }

    /* ---------- Inputs / Dropdowns ---------- */
    .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input,
    .stSelectbox div[data-baseweb="select"] > div, .stMultiSelect div[data-baseweb="select"] > div {
        background: #fff !important; border: 1.5px solid #D5DEEA !important; border-radius: 10px !important;
        min-height: 44px !important; transition: border-color .15s ease, box-shadow .15s ease !important;
    }
    .stTextInput input:hover, .stSelectbox div[data-baseweb="select"] > div:hover, .stMultiSelect div[data-baseweb="select"] > div:hover { border-color: #9FB3CC !important; }
    .stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus,
    .stSelectbox div[data-baseweb="select"] > div:focus-within, .stMultiSelect div[data-baseweb="select"] > div:focus-within {
        border-color: var(--pg-gold) !important; box-shadow: var(--pg-ring) !important;
    }
    label[data-testid="stWidgetLabel"] p {
        font-family: 'Poppins','Inter',sans-serif !important; font-size: 12.5px !important; font-weight: 600 !important;
        color: #35506F !important; letter-spacing: .25px; text-transform: none;
    }
    .stMultiSelect span[data-baseweb="tag"] {
        background: linear-gradient(135deg, #0F2A4A, #1D4A7A) !important; color: #fff !important; border-radius: 8px !important;
    }
    div[data-baseweb="popover"] ul[role="listbox"] { border-radius: 12px !important; box-shadow: var(--pg-shadow-md) !important; }
    div[data-baseweb="popover"] li[role="option"]:hover { background: #FFF5DF !important; }
    div[data-baseweb="popover"] li[aria-selected="true"] { background: #EAF2FF !important; font-weight: 600 !important; }

    /* ---------- Checkbox / Radio ---------- */
    .stCheckbox label { padding: 2px 0; }
    .stCheckbox input:checked + div, .stCheckbox [data-baseweb="checkbox"] div[role="checkbox"][aria-checked="true"] {
        background-color: var(--pg-navy) !important; border-color: var(--pg-navy) !important;
    }
    /* Main area ka horizontal radio = segmented control */
    section.main div[role="radiogroup"][aria-orientation="horizontal"], [data-testid="stMain"] div[role="radiogroup"][aria-orientation="horizontal"],
    [data-testid="stMain"] div[role="radiogroup"]:has(> label):not([aria-orientation="vertical"]) {
        gap: 6px !important; background: #E9EEF5; padding: 5px; border-radius: 14px; display: inline-flex; flex-wrap: wrap;
    }
    [data-testid="stMain"] div[role="radiogroup"]:not([aria-orientation="vertical"]) > label {
        background: transparent; padding: 7px 16px; border-radius: 10px; margin: 0 !important; cursor: pointer; transition: all .15s ease;
    }
    [data-testid="stMain"] div[role="radiogroup"]:not([aria-orientation="vertical"]) > label:has(input:checked) {
        background: #fff; box-shadow: var(--pg-shadow-sm); color: var(--pg-navy);
    }
    [data-testid="stMain"] div[role="radiogroup"]:not([aria-orientation="vertical"]) > label:has(input:checked) p { font-weight: 700 !important; color: var(--pg-navy) !important; }
    [data-testid="stMain"] div[role="radiogroup"]:not([aria-orientation="vertical"]) > label > div:first-child { display: none !important; }

    /* ---------- Metric cards (kul Students / Year-wise) ---------- */
    [data-testid="stMetric"] {
        background: linear-gradient(180deg, #fff 0%, #F8FAFD 100%); border: 1px solid var(--pg-border);
        border-left: 5px solid var(--pg-gold); border-radius: var(--pg-radius); padding: 14px 18px !important;
        box-shadow: var(--pg-shadow-sm); transition: transform .15s ease, box-shadow .15s ease;
    }
    [data-testid="stMetric"]:hover { transform: translateY(-2px); box-shadow: var(--pg-shadow-md); }
    [data-testid="stMetricLabel"] p { font-weight: 600 !important; color: #5B6B80 !important; font-size: 13px !important; }
    [data-testid="stMetricValue"] { font-family: 'Poppins',sans-serif !important; color: var(--pg-navy) !important; font-weight: 700 !important; }

    /* ---------- Expander = card ---------- */
    [data-testid="stExpander"] {
        background: #fff; border: 1px solid var(--pg-border) !important; border-radius: 14px !important;
        box-shadow: var(--pg-shadow-sm); overflow: hidden;
    }
    [data-testid="stExpander"] summary { font-family: 'Poppins',sans-serif; font-weight: 600; color: var(--pg-navy); padding: 12px 16px !important; }
    [data-testid="stExpander"] summary:hover { background: #F5F8FC; }
    [data-testid="stExpander"] details[open] > summary { border-bottom: 1px solid var(--pg-border); background: #F8FAFD; }

    /* ---------- Alerts / captions / tables ---------- */
    div[data-testid="stAlert"] { border-radius: 12px !important; box-shadow: var(--pg-shadow-sm); border: 1px solid rgba(15,42,74,.08) !important; }
    [data-testid="stCaptionContainer"] { line-height: 1.55; }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] { border-radius: 14px !important; box-shadow: var(--pg-shadow-sm) !important; }
    hr { border-color: #E3E9F1 !important; }
    .stSpinner, [data-testid="stStatusWidget"] { color: var(--pg-gold-dark) !important; }

    /* ---------- Scrollbar ---------- */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-thumb { background: #C3CEDC; border-radius: 10px; border: 2px solid transparent; background-clip: content-box; }
    ::-webkit-scrollbar-thumb:hover { background: #9FB0C6; background-clip: content-box; border: 2px solid transparent; }

    /* ---------- Mobile ---------- */
    @media (max-width: 640px) {
        .block-container { padding: 1rem .8rem 3rem !important; }
        .stButton > button, .stDownloadButton > button { width: 100% !important; min-height: 48px !important; }
        [data-testid="stMetric"] { padding: 10px 12px !important; }
        [data-testid="stMain"] div[role="radiogroup"]:not([aria-orientation="vertical"]) { display: flex !important; width: 100%; }
    }
    @media print { .stButton, .stDownloadButton { display: none !important; } }
    </style>
""", unsafe_allow_html=True)

# ==========================================================
# 🖨️ PRINT HELPER — button dabate hi browser ka Print dialog khulta hai
# (sirf diya gaya HTML print hota hai; Streamlit page ka baaki hissa nahi)
# ==========================================================
def print_button(body_html, label="🖨️ Print करें", height=52):
    doc = (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>Print</title><style>'
        '@page { margin: 8mm; }'
        '* { -webkit-print-color-adjust: exact; print-color-adjust: exact; }'
        'body { font-family: Arial, sans-serif; color: #000; }'
        'table { width: 100%; border-collapse: collapse; font-size: 11px; }'
        'th { background: #f2f2f2; border: 1px solid #111; padding: 6px; text-align: center; }'
        'td { border: 1px solid #111; padding: 5px; text-align: left; }'
        'thead { display: table-header-group; } tr { page-break-inside: avoid; }'
        '</style></head><body>' + body_html + '</body></html>'
    )
    payload = json.dumps(doc).replace("</", "<\\/")
    components.html(f"""
    <style>
      body {{ margin:0; }}
      #pb {{ width:100%; min-height:44px; padding:10px 16px; border:1px solid rgba(255,255,255,.14); border-radius:12px; cursor:pointer;
             background:linear-gradient(135deg,#0F2A4A 0%,#1D4A7A 60%,#2A5E96 100%); color:#fff; font-size:14.5px; font-weight:600;
             letter-spacing:.15px; font-family:'Poppins','Inter',Arial,sans-serif;
             box-shadow:0 1px 2px rgba(15,42,74,.06),0 2px 8px rgba(15,42,74,.10);
             transition:transform .14s ease, box-shadow .18s ease, filter .18s ease; }}
      #pb:hover {{ transform:translateY(-2px); box-shadow:0 8px 22px rgba(15,42,74,.34); filter:brightness(1.06); }}
      #pb:active {{ transform:scale(.985); filter:brightness(.96); }}
      #pb:focus-visible {{ outline:none; box-shadow:0 0 0 3px rgba(201,151,63,.35); }}
    </style>
    <button id="pb">{label}</button>
    <script>
    const DOC = {payload};
    document.getElementById('pb').addEventListener('click', function() {{
        const old = document.getElementById('pf'); if (old) old.remove();
        const f = document.createElement('iframe');
        f.id = 'pf';
        f.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
        document.body.appendChild(f);
        const d = f.contentWindow.document;
        d.open(); d.write(DOC); d.close();
        setTimeout(function() {{ f.contentWindow.focus(); f.contentWindow.print(); }}, 300);
    }});
    </script>
    """, height=height)


# ==========================================================
# 📗 EXCEL (.xlsx) BANANE KA HELPER — P3 ke "Upload Format (Template)" aur "Backup Export" ke liye
# Header rang-bira, text wrap, sahi column width, borders, freeze row, filter; sab cells TEXT format me
# (taaki Excel "1-10" ko date ya mobile number ko 9.1E+09 na bana de) aur wapas Upload karne par data jaisa ka taisa aaye.
# ==========================================================
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def df_to_formatted_xlsx(df, sheet_name="Sheet1", header_notes=None, highlight_rows=0, group_colors=None):
    """df (sab text) -> sundar formatted .xlsx bytes.
    header_notes: {column: help text} — header par Excel Note (hover karne par dikhta hai)
    highlight_rows: shuru ki itni rows halke peele rang me (Sample rows — hatane ke liye)
    group_colors: [(column_prefix_ya_naam_ka_tuple, hex_color)] — header ka rang group ke hisaab se"""
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.comments import Comment
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.astype(str).to_excel(xw, index=False, sheet_name=sheet_name[:31])
        ws = xw.sheets[sheet_name[:31]]
        thin = Side(style="thin", color="B8C4D6")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        default_hdr = "0F2A4A"
        n_cols = len(df.columns)
        for ci, col in enumerate(df.columns, start=1):
            color = default_hdr
            for keys, hexc in (group_colors or []):
                if col in keys:
                    color = hexc
                    break
            c = ws.cell(row=1, column=ci)
            c.fill = PatternFill("solid", fgColor=color)
            c.font = Font(bold=True, color="FFFFFF", size=11, name="Calibri")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = border
            if header_notes and col in header_notes:
                note = Comment(header_notes[col], "Guardian Tutors")
                note.width, note.height = 280, 110
                c.comment = note
            # column width: sabse lambi line ke hisaab se
            longest = max([len(str(col))] + [len(line) for v in df[col].astype(str) for line in v.split("\n")] or [8])
            ws.column_dimensions[get_column_letter(ci)].width = max(11, min(longest + 3, 42))
        ws.row_dimensions[1].height = 34
        for ri in range(2, len(df) + 2):
            fill = None
            if highlight_rows and ri - 1 <= highlight_rows:
                fill = PatternFill("solid", fgColor="FFF6D6")
            elif ri % 2 == 1:
                fill = PatternFill("solid", fgColor="F4F7FB")
            max_lines = 1
            for ci in range(1, n_cols + 1):
                c = ws.cell(row=ri, column=ci)
                c.number_format = "@"
                c.alignment = Alignment(vertical="center", wrap_text=True)
                c.font = Font(name="Calibri", size=11)
                c.border = border
                if fill:
                    c.fill = fill
                max_lines = max(max_lines, str(c.value or "").count("\n") + 1)
            ws.row_dimensions[ri].height = max(22, 17 * max_lines + 4)
        ws.freeze_panes = "A2"
        if n_cols:
            ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{len(df) + 1}"
        ws.sheet_view.zoomScale = 100
    return buf.getvalue()


# ==========================================================
# 👩‍🏫 GUARDIAN TUTORS LIST UPLOAD (P3 aur P4 dono me use hota hai)
# ==========================================================
def faculty_upload_ui(key_prefix):
    st.caption("Excel/CSV फ़ाइल अपलोड करें जिसमें 'Name of Guardians Tutors' (या 'Faculty Name') और 'Department' / 'Allotted Class' "
               "कॉलम हों — जैसे 'LIST OF GUARDIANS TUTORS' शीट में होता है "
               "(S.N., Department, Name of Guardians Tutors, Mobile No., Allotted Class, Number of Student)। "
               "Designation, Mobile Number वैकल्पिक हैं। ⚠️ नई फ़ाइल पुरानी List को replace कर देगी।")
    # Upload Format (Template): khaali format + 2 sample rows — isi columns ke hisaab se apna data bharke upload karein
    _tpl = pd.DataFrame([
        {"S.No.": "1", "Name of Faculty": "Dr. Sample Name", "Department": "Commerce", "Mobile No.": "9876543210",
         "Degree": "B.Com.", "Branch": "Commerce", "Year": "1st Year", "Serial No": "1-10", "Total Number of Students": "10"},
        {"S.No.": "2", "Name of Faculty": "Dr. Sample Two", "Department": "Computer Science", "Mobile No.": "9123456780",
         "Degree": "PGDCA\nPGDCA", "Branch": "Computer Science\nComputer Science", "Year": "1st Year\n2nd Year",
         "Serial No": "11-20\n1-5", "Total Number of Students": "15"},
    ])
    _tpl_notes = {
        "S.No.": "क्रम संख्या (वैकल्पिक)।",
        "Name of Faculty": "Guardian Tutor का नाम।",
        "Department": "Tutor का Department (जैसे Commerce)।",
        "Mobile No.": "Tutor का मोबाइल नंबर (वैकल्पिक)।",
        "Degree": "Degree/Course (जैसे B.Com., PGDCA)। एक से ज़्यादा Class हों तो हर Class नई लाइन (Alt+Enter) पर लिखें।",
        "Branch": "Branch / Major Subject (जैसे Commerce) — या सभी Branch के लिए ALL। Degree की हर लाइन के सामने की लाइन में।",
        "Year": "1st Year / 2nd Year / 3rd Year … हर Class के लिए नई लाइन (Alt+Enter) पर।",
        "Serial No": "यहाँ से-यहाँ तक, जैसे 1-10। हर Class का Serial उसी क्रम की नई लाइन पर।",
        "Total Number of Students": "वैकल्पिक — Save करने पर Serial No से अपने आप निकल आता है।",
    }
    st.download_button(
        "📥 Upload Format (Template) Download करें",
        df_to_formatted_xlsx(_tpl, sheet_name="Guardian Tutors", header_notes=_tpl_notes, highlight_rows=len(_tpl)),
        file_name="guardian_tutors_upload_format.xlsx", mime=XLSX_MIME, key=f"{key_prefix}_fac_tpl_dl",
        help="इस फ़ाइल में दिए columns वैसे ही रखें, Sample rows हटाकर अपना data भरें, फिर नीचे Upload करें। "
             "एक Tutor की एक से ज़्यादा Class हों तो Allotted Class और Serial No में हर Class नई लाइन (Excel में Alt+Enter) पर लिखें।")
    st.caption("ℹ️ Template में 2 Sample rows हैं (दूसरी row में एक Tutor की 2 Class दिखाई गई हैं) — इन्हें हटाकर अपना data भरें। "
               "Department = Tutor का Department; Degree + Year मिलकर Major Subject की Allotted Class बनते हैं। "
               "इसी Template जैसे columns वाला '💾 Backup Export' भी यहीं Upload किया जा सकता है।")
    fac_file = st.file_uploader("Guardian Tutors List फ़ाइल चुनें", type=["csv", "xlsx", "xls"], key=f"{key_prefix}_fac_upload")
    if fac_file is None:
        return
    try:
        fac_raw = read_uploaded_table(fac_file)
    except Exception as e:
        st.error(f"❌ फ़ाइल पढ़ने में समस्या: {e}")
        return
    if fac_raw.empty:
        st.error("❌ फ़ाइल में कोई मान्य डेटा नहीं मिला।")
        return

    # ✅ P3 के "Backup Export" (ya purane CSV) me app ke apne column naam hote hain — unhe jaisa hai waisa hi padho.
    # Warna "Department" (= Allotted Class) aur "Tutor Department" dono ek hi column me badal jaate aur data bigad jaata.
    _is_backup_format = {"Faculty Name", "Tutor Department", "Department"} <= set(map(str, fac_raw.columns))
    if _is_backup_format:
        st.success("✅ यह P3 का Backup Export फ़ाइल है — सभी Subject Types (Major/Minor/Vocational/MDC/PW-Ap-CE) का "
                   "Allotted Class + SERIAL NO. जैसा था वैसा ही वापस आएगा।")

    fac_rename = {}
    for col in ([] if _is_backup_format else fac_raw.columns):
        key = re.sub(r"[^a-z0-9]", "", str(col).strip().lower())
        if key in ("allottedclass", "class", "allottedclassname"):
            fac_rename[col] = "Department"                 # Allotted Class
        elif key in ("department", "dept", "departmentname", "tutordepartment", "deptname"):
            fac_rename[col] = "Tutor Department"           # naya DEPARTMENT column
        elif key in ("facultyname", "faculty", "teachername", "mentorname", "tutorname", "guardiantutorname",
                     "nameofguardianstutors", "nameofguardiantutor", "guardianstutors", "guardiantutors",
                     "nameofguardian", "nameofguardianstutor", "guardiantutor", "nameofguardiantutors",
                     "nameoffaculty", "nameoffacultymember"):
            fac_rename[col] = "Faculty Name"
        elif key in ("designation", "post", "role"):
            fac_rename[col] = "Designation"
        elif key in ("mobilenumber", "mobileno", "mobile", "phone", "phonenumber", "contactno", "mobno"):
            fac_rename[col] = "Mobile Number"
        elif key == "degree":
            fac_rename[col] = "Degree"                      # temporary — neeche Allotted Class me jud jaayega
        elif key in ("year", "currentyear", "classyear", "courseyear"):
            fac_rename[col] = "Year"                        # temporary — neeche Allotted Class me jud jaayega
        elif key in ("branch", "branchname", "majorsubject", "majorbranch"):
            fac_rename[col] = "Branch"
        elif key in ("serialno", "serialnumber", "srno", "serial", "serialnos"):
            fac_rename[col] = "Serial No"
        elif key in ("numberofstudent", "numberofstudents", "totalstudents", "studentcount", "noofstudents",
                     "nostudents", "noofstudent", "totalnumberofstudents", "totalnumberofstudent"):
            fac_rename[col] = "Number of Students"
    fac_raw = fac_raw.rename(columns=fac_rename)
    # Degree + Year columns ho to unhe jodkar "Allotted Class" (jaise "PGDCA 1st Year") banao — line-by-line
    # (ek cell me ek se zyada Class nayi line par likhi ho to har line apne Year ke saath judti hai)
    if not _is_backup_format and ("Degree" in fac_raw.columns or "Year" in fac_raw.columns) and "Department" not in fac_raw.columns:
        def _join_deg_year(r):
            _dl = str(r.get("Degree", "")).split("\n")
            _yl = [normalize_course_year(y) for y in str(r.get("Year", "")).split("\n")]
            return "\n".join(f"{(_dl[i] if i < len(_dl) else '').strip()} {(_yl[i] if i < len(_yl) else '').strip()}".strip()
                             for i in range(max(len(_dl), len(_yl))))
        fac_raw["Department"] = fac_raw.apply(_join_deg_year, axis=1)

    if "Faculty Name" not in fac_raw.columns or not ({"Department", "Tutor Department"} & set(fac_raw.columns)):
        st.error("❌ फ़ाइल में 'Name of Guardians Tutors' (या 'Faculty Name') और 'Department' या 'Allotted Class' "
                 "में से कम से कम एक कॉलम ज़रूर होना चाहिए। "
                 f"फ़ाइल के columns: {', '.join(map(str, fac_raw.columns))}")
        return

    st.dataframe(fac_raw.head(20), use_container_width=True)
    if st.button("💾 यह List Save करें", type="primary", key=f"{key_prefix}_fac_save_upload"):
        aligned_fac = pd.DataFrame(index=fac_raw.index)
        for c in FACULTY_COLUMNS:
            aligned_fac[c] = fac_raw[c] if c in fac_raw.columns else ""
        aligned_fac = aligned_fac.fillna("").astype(str).reset_index(drop=True)
        for _c in ("Mobile Number", "Number of Students"):          # Excel के "9876543210.0" जैसे मान साफ़ करें
            aligned_fac[_c] = aligned_fac[_c].str.strip().str.replace(r"\.0$", "", regex=True)
        aligned_fac = aligned_fac[(aligned_fac["Department"].str.strip() != "") | (aligned_fac["Faculty Name"].str.strip() != "")
                                  | (aligned_fac["Tutor Department"].str.strip() != "")]
        save_faculty(aligned_fac.reset_index(drop=True))
        st.session_state["p3_fac_n"] = st.session_state.get("p3_fac_n", 0) + 1
        st.session_state["p3_fac_flash"] = f"✅ {len(aligned_fac)} Guardian Tutors की List Save हो गई है।"
        st.rerun()


# ==========================================================
# 🏢 DEPARTMENT RENAME HELPER — naam har jagah ek saath badalta hai
# (Departments list, P1 se save records, Department users, P3 Tutors list)
# ==========================================================
def rename_department(old, new):
    depts = [new if d == old else d for d in st.session_state.departments]
    st.session_state.departments = depts
    save_departments(depts)

    _db = load_db()
    if not _db.empty:
        _db.loc[_db["Assigned Department"] == old, "Assigned Department"] = new
        save_db(_db)

    creds = st.session_state.credentials
    for _u, _v in creds.items():
        if _v.get("department") == old:
            _v["department"] = new
            if old in str(_v.get("label", "")):
                _v["label"] = str(_v["label"]).replace(old, new)
    st.session_state.credentials = creds
    save_credentials(creds)

    _fac = load_faculty()
    if not _fac.empty:
        _fac.loc[_fac["Tutor Department"] == old, "Tutor Department"] = new
        _fac.loc[_fac["Department"] == old, "Department"] = new
        save_faculty(_fac)


# ==========================================================
# 🖼️ LOGO — app.py wale folder me (ya uske assets/images/static folder me) jis image file ke naam me "logo" ya "pratap"
# likha ho (jaise "logo pratap.png"), wahi Login panel par dikhta hai
# ==========================================================
def find_logo_data_uri():
    import base64
    exts = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
            ".gif": "image/gif", ".svg": "image/svg+xml"}
    try:
        base = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        base = os.getcwd()
    folders = []
    for root in dict.fromkeys([base, os.getcwd()]):
        folders.append(root)
        folders += [os.path.join(root, sub) for sub in ("assets", "images", "image", "static", "logo", "logos")]
    cands = []
    for d in folders:
        if not os.path.isdir(d):
            continue
        for n in os.listdir(d):
            low = n.lower()
            ext = os.path.splitext(low)[1]
            if ext in exts and ("logo" in low or "pratap" in low):
                score = 0 if ("logo" in low and "pratap" in low) else (1 if "logo" in low else 2)
                cands.append((score, os.path.join(d, n), exts[ext]))
    for _, path, mime in sorted(cands):
        try:
            with open(path, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode()
        except Exception:
            continue
    return ""


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
    _logo_uri = find_logo_data_uri()
    if _logo_uri:
        header_html = header_html.replace(
            '<h1 style="margin:0;">🏛️</h1>',
            f'<img src="{_logo_uri}" alt="Logo" style="max-width:100%; max-height:100%; object-fit:contain; border-radius:8px;">'
        ).replace("flex-shrink:0; width:70px; height:70px;", "flex-shrink:0; width:92px; height:92px; background:#fff; padding:4px;")
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
            "P2 — List",
            "P3 — Guardian Tutors List",
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
    _flash = st.session_state.pop("p1_flash", None)
    if _flash:
        st.success(_flash)
    mode = st.radio("तरीका चुनें", ["✍️ Single Entry (Form)", "📤 Bulk Upload (CSV/Excel)"], horizontal=True)

    if mode == "✍️ Single Entry (Form)":
        p1_single_panels = st.multiselect(
            "यह Entry किन Panels में दिखे?", list(PANEL_OPTIONS.keys()), default=list(PANEL_OPTIONS.keys()),
            format_func=lambda k: PANEL_OPTIONS[k], key="p1_single_panels",
        )
        if "P4" in p1_single_panels:
            p1_single_dept = st.selectbox("P4 के लिए Department (Approve होकर यहीं भेजी जाएगी)", st.session_state.departments, key="p1_single_dept")
        else:
            p1_single_dept = ""
        with st.form("single_entry_form"):
            st.caption("नीचे जितने columns भरने हैं भरें — बाकी खाली छोड़ सकते हैं।")
            values = {}
            cols = st.columns(3)
            for i, col_name in enumerate(DEFAULT_COLUMNS):
                with cols[i % 3]:
                    if col_name == "Current Year":
                        values[col_name] = st.selectbox(
                            "🎓 Current Year (1st/2nd/3rd/4th/5th)",
                            [""] + COURSE_YEAR_OPTIONS,
                            key=f"p1_field_{col_name}",
                        )
                    else:
                        values[col_name] = st.text_input(col_name, key=f"p1_field_{col_name}")
            submit_entry = st.form_submit_button("✅ Submit & Approve", type="primary", use_container_width=True)
        if submit_entry:
            if not any(str(v).strip() for v in values.values()):
                st.warning("⚠️ कृपया कम से कम एक फ़ील्ड भरें।")
            elif not p1_single_panels:
                st.warning("⚠️ कम से कम एक Panel चुनें जहाँ यह Entry दिखे।")
            else:
                new_row = {c: "" for c in ALL_COLUMNS}
                new_row.update(values)
                new_row["Status"] = "Approved"
                new_row["Assigned Department"] = p1_single_dept
                new_row["Show In Panels"] = ",".join(p1_single_panels)
                new_row["Submitted By"] = username
                new_row["Submitted On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                new_row["Approved By"] = username
                new_row["Approved On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                db = pd.concat([db, pd.DataFrame([new_row])], ignore_index=True)
                save_db(db)
                st.success("🎉 Entry सफलतापूर्वक Submit होकर सीधे Approve हो गई — "
                           f"{', '.join(p1_single_panels)} में दिखेगी" + (f" (Department: '{p1_single_dept}')।" if p1_single_dept else "।"))
                st.balloons()

    else:
        st.info("CSV या Excel (.csv/.xlsx/.xls) फ़ाइलें अपलोड करें — एक साथ कई फ़ाइलें भी चुन सकते हैं। "
                "मिलते-जुलते नाम वाले कॉलम (जैसे DOB, Email, Mobile No) अपने आप सही जगह मैच हो जाएंगे — बाकी खाली रहेंगे।")

        oc1, oc2, oc3, oc4 = st.columns(4)
        with oc1:
            _p1_year_now = datetime.now().year
            _p1_year_options = [str(y) for y in range(_p1_year_now + 2, _p1_year_now - 8, -1)]
            p1_common_year = st.selectbox(
                "📅 यह List किस Admission Year की है?",
                _p1_year_options,
                index=_p1_year_options.index(str(_p1_year_now)) if str(_p1_year_now) in _p1_year_options else 0,
                key="p1_common_year",
            )
        with oc2:
            _p1_course_year_options = ["-- लागू न करें --"] + COURSE_YEAR_OPTIONS
            p1_common_course_year = st.selectbox(
                "🎓 यह List किस Year (1st/2nd/3rd/4th/5th) की है?",
                _p1_course_year_options,
                key="p1_common_course_year",
            )
        with oc3:
            p1_common_session = st.text_input("Admission Session (सभी rows पर लागू करें, वैकल्पिक)", key="p1_common_session")
        with oc4:
            p1_bulk_panels = st.multiselect(
                "यह List किन Panels में दिखे?", list(PANEL_OPTIONS.keys()), default=list(PANEL_OPTIONS.keys()),
                format_func=lambda k: PANEL_OPTIONS[k], key="p1_bulk_panels",
            )
        st.caption(f"ऊपर चुना गया Admission Year ('{p1_common_year}') इस पूरी अपलोड होने वाली List की सभी rows में लागू होगा "
                   "(भले ही फ़ाइल में पहले से कुछ भरा हो) — ताकि P2 में हर list का सही Year साफ़ दिखे। "
                   "अगर 'Year (1st/2nd/3rd/4th/5th)' भी चुना जाए, तो वह भी सभी rows के 'Current Year' कॉलम में इसी तरह लागू होगा। "
                   "Admission Session सिर्फ़ उन्हीं rows में भरा जाएगा जहाँ फ़ाइल में वह कॉलम पहले से खाली है।")
        if not p1_bulk_panels:
            st.warning("⚠️ कम से कम एक Panel चुनें, तभी List जोड़ी जा सकेगी।")
        if "P4" in p1_bulk_panels:
            p1_bulk_dept = st.selectbox("P4 के लिए Department (सभी rows Approve होकर यहीं जाएंगी)", st.session_state.departments, key="p1_bulk_dept")
        else:
            p1_bulk_dept = ""

        up_files = st.file_uploader("फ़ाइलें चुनें", type=["csv", "xlsx", "xls"], accept_multiple_files=True,
                                    key=f"p1_bulk_up_{st.session_state.get('p1_bulk_up_n', 0)}")

        if up_files:
            all_new_rows = []
            for up_file in up_files:
                try:
                    raw_df = read_uploaded_table(up_file)
                except Exception as e:
                    st.error(f"❌ '{up_file.name}' पढ़ने में समस्या: {e}")
                    continue

                if raw_df.empty:
                    st.error(f"❌ '{up_file.name}' में कोई मान्य डेटा नहीं मिला या फ़ॉर्मेट पढ़ा नहीं जा सका।")
                    if _UPLOAD_DIAG["info"]:
                        st.caption(f"🔎 Diagnostic: {_UPLOAD_DIAG['info']}")
                    continue

                raw_df = smart_align_columns(raw_df)
                with st.expander(f"👁️ '{up_file.name}' — {raw_df.shape[0]} rows, {raw_df.shape[1]} columns (Preview)"):
                    st.dataframe(raw_df.head(20), use_container_width=True)

                _matched = [c for c in DEFAULT_COLUMNS if c in raw_df.columns]
                _ignored = [str(c) for c in raw_df.columns if c not in DEFAULT_COLUMNS]
                if not _matched:
                    st.error(f"❌ '{up_file.name}' का कोई भी column पहचाना नहीं गया, इसलिए यह फ़ाइल नहीं जोड़ी जाएगी। "
                             f"फ़ाइल के columns: {', '.join(map(str, raw_df.columns))}")
                    continue
                st.caption(f"✅ '{up_file.name}' — पहचाने गए columns: {', '.join(_matched)}"
                           + (f"  |  ⚠️ पहचाने नहीं गए (छोड़ दिए जाएंगे): {', '.join(_ignored)}" if _ignored else ""))
                aligned = pd.DataFrame(index=raw_df.index)
                for c in DEFAULT_COLUMNS:
                    aligned[c] = raw_df[c] if c in raw_df.columns else ""
                aligned = aligned.reindex(columns=ALL_COLUMNS).fillna("").reset_index(drop=True)
                aligned["Admission Year"] = p1_common_year.strip()   # is upload/list ka year — sabhi rows par lagu (overwrite)
                # File me "Current Year" jaise bhi likha ho (First Year / Second Year / II Year / 2 ...) — canonical form me badlo
                aligned["Current Year"] = aligned["Current Year"].map(normalize_course_year)
                if p1_common_course_year != "-- लागू न करें --":
                    aligned["Current Year"] = p1_common_course_year   # 1st/2nd/3rd/4th/5th Year — sabhi rows par lagu (overwrite)
                if p1_common_session.strip():
                    aligned.loc[aligned["Admission Session"].astype(str).str.strip() == "", "Admission Session"] = p1_common_session.strip()
                aligned["Status"] = "Approved"
                aligned["Assigned Department"] = p1_bulk_dept
                aligned["Show In Panels"] = ",".join(p1_bulk_panels)
                aligned["Submitted By"] = username
                aligned["Submitted On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                aligned["Approved By"] = username
                aligned["Approved On"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                all_new_rows.append(aligned)

            if all_new_rows:
                total_rows = sum(len(a) for a in all_new_rows)
                _p1_cy_note = f", Year: **{p1_common_course_year}**" if p1_common_course_year != "-- लागू न करें --" else ""
                st.success(f"✅ कुल {len(all_new_rows)} फ़ाइलों से {total_rows} rows पढ़ ली गई हैं (Admission Year: **{p1_common_year}**{_p1_cy_note}) — नीचे बटन दबाकर पक्का जोड़ें।")
                if st.button(f"📥 इन सभी {total_rows} Rows को Year '{p1_common_year}' के साथ सीधे Approve करके जोड़ें" + (f" ('{p1_bulk_dept}' में)" if p1_bulk_dept else ""), type="primary", disabled=not p1_bulk_panels):
                    db = pd.concat([db] + all_new_rows, ignore_index=True)
                    save_db(db)
                    _p1_cy_flash_note = f", Year: '{p1_common_course_year}'" if p1_common_course_year != "-- लागू न करें --" else ""
                    st.session_state["p1_flash"] = (
                        f"🎉 {total_rows} rows (Admission Year: '{p1_common_year}'{_p1_cy_flash_note}) Approve होकर save हो गईं — {', '.join(p1_bulk_panels)} में दिखेंगी"
                        + (f" (Department: '{p1_bulk_dept}')" if p1_bulk_dept else "")
                        + f"। Database में अब कुल {len(db)} records हैं।"
                    )
                    st.session_state["p1_bulk_up_n"] = st.session_state.get("p1_bulk_up_n", 0) + 1
                    st.rerun()

# ==========================================================
# 📋 P2 — LIST  (Admin only)
# ==========================================================
elif choice == "P2 — List":
    st.header("📋 P2 — List (सभी Entries)")
    if db.empty:
        st.info("📭 अभी तक कोई entry नहीं है।")
    else:
        st.caption(f"कुल {len(db)} entries मौजूद हैं — सभी columns नीचे दिख रहे हैं।")
        p2_view = filter_for_panel(db, "P2").copy()
        _p2_sc1, _p2_sc2 = st.columns([3, 1])
        with _p2_sc1:
            p2_search = st.text_input("🔎 किसी भी field से खोजें", key="p2_search")
        with _p2_sc2:
            _p2_years = ["सभी"] + sorted(
                [y for y in p2_view["Admission Year"].astype(str).str.strip().unique() if y], reverse=True
            )
            p2_year_filter = st.selectbox("📅 Year से Filter करें", _p2_years, key="p2_year_filter")
        if p2_year_filter != "सभी":
            p2_view = p2_view[p2_view["Admission Year"].astype(str).str.strip() == p2_year_filter]
        if p2_search.strip():
            s = p2_search.strip().lower()
            p2_view = p2_view[p2_view.apply(lambda r: s in " ".join(str(v).lower() for v in r.values), axis=1)]
        st.caption(f"{len(p2_view)} entries मिलीं।")
        st.data_editor(
            p2_view,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Admission Year": st.column_config.TextColumn("📅 Admission Year", width="small"),
                "Assigned Department": st.column_config.SelectboxColumn("Assigned Department", options=st.session_state.departments, required=False),
            },
            key="p2_full_list_editor",
        )
        st.download_button(
            "⬇️ पूरी List CSV Download करें",
            p2_view.to_csv(index=False).encode("utf-8-sig"),
            file_name="p2_full_list.csv", mime="text/csv",
        )

# ==========================================================
# 👩‍🏫 P3 — GUARDIAN TUTORS LIST  (Admin only)
# ==========================================================
elif choice == "P3 — Guardian Tutors List":
    st.header("👩‍🏫 P3 — Guardian Tutors List")
    _fac_flash = st.session_state.pop("p3_fac_flash", None)
    if _fac_flash:
        st.success(_fac_flash)

    _fac = load_faculty().reset_index(drop=True)

    _p3_subj_type = "Major Subject"
    _p3_fields = SUBJECT_TYPE_FIELDS[_p3_subj_type]
    _p3_class_col, _p3_serial_col, _p3_total_col = _p3_fields["class"], _p3_fields["serial"], _p3_fields["total"]
    _p3_branch_col = _p3_fields["branch"]

    with st.expander("📤 फ़ाइल से List अपलोड करें (Excel / CSV)", expanded=_fac.empty):
        faculty_upload_ui("p3")

    st.caption("यहाँ से आप Text बदल सकते हैं, नई Row जोड़ सकते हैं (टेबल के नीचे ➕) और Row हटा सकते हैं "
               "(Row चुनकर 🗑️)। बदलाव के बाद **💾 Save Changes** ज़रूर दबाएँ। "
               "**Major Subject** के Allotted Class का नाम वही रखें जो P4 में Department का नाम है, ताकि P4 में यह Tutor सही जगह दिखे "
               "(Minor/Vocational/MDC/PW-Ap-CE ke Allotted Class par ye restriction lagu nahi hoti)।")
    if _fac.empty:
        st.info("📭 अभी List खाली है — ऊपर से फ़ाइल अपलोड करें, या नीचे टेबल में ➕ से Row जोड़ें।")

    # DEPARTMENT dropdown: app ke Departments + list me pehle se maujood koi bhi purana naam
    _dept_opts = list(dict.fromkeys(
        list(st.session_state.departments) + [d for d in _fac["Tutor Department"].astype(str).str.strip() if d]))

    st.caption("ℹ️ **TOTAL NUMBER OF STUDENTS** अपने आप **SERIAL NO.** से calculate होता है (जैसे '1-10, 5-21' लिखने पर total = 27) — "
               "इसे हाथ से भरने की ज़रूरत नहीं। किसी Tutor की Details बदलने या उसे Students Assign करने के लिए "
               "उसकी लाइन के सामने **Actions** में ✏️ Edit / 📌 Assign दबाएँ।")

    # ----------------------------------------------------------------
    # 📋 LIST TABLE — TOTAL NUMBER OF STUDENTS ke baad Actions column
    # (Actions me ✏️ Edit aur 📌 Assign button — Streamlit ki grid me
    #  seedhe button nahi daal sakte, isliye table row-by-row banti hai)
    # ----------------------------------------------------------------
    # ---- 📊 P2 ki List se TOTAL aur YEAR-WISE TOTAL (table ke upar) ----
    _p3_yr_series = (db["Current Year"].astype(str).map(normalize_course_year).str.strip()
                     if "Current Year" in db.columns else pd.Series([], dtype=str))
    _p3_yr_counts = _p3_yr_series[_p3_yr_series != ""].value_counts()
    _p3_yr_order = ([y for y in COURSE_YEAR_OPTIONS if y in _p3_yr_counts.index]
                    + [y for y in _p3_yr_counts.index if y not in COURSE_YEAR_OPTIONS])
    _p3_yr_blank = int((_p3_yr_series == "").sum())
    _sm_cols = st.columns(1 + len(_p3_yr_order) + (1 if _p3_yr_blank else 0))
    _sm_cols[0].metric("👥 कुल Students (P2 List)", len(db))
    for _i, _y in enumerate(_p3_yr_order, start=1):
        _sm_cols[_i].metric(_y, int(_p3_yr_counts[_y]))
    if _p3_yr_blank:
        _sm_cols[-1].metric("Year खाली", _p3_yr_blank)

    if _fac.empty:
        st.info("📭 अभी List खाली है — ऊपर से फ़ाइल अपलोड करें, या नीचे ➕ से नया Tutor जोड़ें।")
    else:
        _col_widths = [0.5, 2.0, 1.3, 1.2, 1.0, 1.3, 1.0, 1.1, 1.1, 1.2]
        _headers = ["S.No.", "Name of Faculty", "Department", "Mobile No.", "Degree", "Branch", "Year",
                    "Serial No.", "Total Number of Students", "⚙️ Actions"]
        _hcols = st.columns(_col_widths)
        for _hc, _htxt in zip(_hcols, _headers):
            _hc.markdown(f"**{_htxt}**")
        st.markdown("<hr style='margin:2px 0 8px 0;'>", unsafe_allow_html=True)

        for _aidx, _arow in _fac.iterrows():
            _mob_disp = _arow["Mobile Number"].strip() or MOBILE_BLANK
            _tot_disp = _p3_total_from_serial(_arow[_p3_serial_col]) or _arow[_p3_total_col] or "—"
            _rc = st.columns(_col_widths)
            _rc[0].write(_aidx + 1)
            # Degree aur Year — Allotted Class text (jaise "PGDCA I Year") se alag-alag nikalte hain, har line ke liye
            _deg_lines, _yr_lines = [], []
            for _cl in str(_arow[_p3_class_col]).split("\n"):
                if _cl.strip():
                    _dg, _yr = parse_allotted_class(_cl)
                    _deg_lines.append(_dg or _cl.strip())
                    _yr_lines.append(_yr or "—")
            _rc[1].write(_arow["Faculty Name"].strip() or "(बिना नाम)")
            _rc[2].write(_arow["Tutor Department"].strip() or "—")
            _rc[3].write(_mob_disp)
            _rc[4].markdown("  \n".join(_deg_lines) or "—")
            _rc[5].markdown(str(_arow[_p3_branch_col]).replace("\n", "  \n") or "—")
            _rc[6].markdown("  \n".join(_yr_lines) or "—")
            _rc[7].markdown((_arow[_p3_serial_col].replace("\n", "  \n") or "—"))
            _rc[8].write(_tot_disp)
            with _rc[9]:
                _ea1, _ea2 = st.columns(2)
                with _ea1:
                    if st.button("✏️", key=f"p3_edit_btn_{_aidx}", use_container_width=True, help="Edit"):
                        st.session_state["p3_edit_idx"] = _aidx
                        st.session_state.pop("p3_assign_idx", None)
                        st.rerun()
                with _ea2:
                    if st.button("📌", key=f"p3_assign_btn_{_aidx}", use_container_width=True, help="Assign"):
                        st.session_state["p3_assign_idx"] = _aidx
                        st.session_state.pop("p3_edit_idx", None)
                        st.rerun()
            st.markdown("<hr style='margin:2px 0 8px 0;'>", unsafe_allow_html=True)

        _dl = _fac.reset_index(drop=True).copy()
        _dl.insert(0, "S.N.", range(1, len(_dl) + 1))
        _dl["Mobile Number"] = _dl["Mobile Number"].map(lambda v: "" if str(v).strip("_ ").strip() == "" else v)
        # ---- 🖨️ Print: P3 ki List ko seedha browser Print dialog se print karna ----
        import html as _html
        _pr_rows = []
        for _pi, _pr in _fac.reset_index(drop=True).iterrows():
            _dg_l, _yr_l = [], []
            for _cl in str(_pr[_p3_class_col]).split("\n"):
                if _cl.strip():
                    _dg, _yr = parse_allotted_class(_cl)
                    _dg_l.append(_dg or _cl.strip())
                    _yr_l.append(_yr or "")
            _mob = str(_pr["Mobile Number"]).strip()
            _tot = _p3_total_from_serial(_pr[_p3_serial_col]) or str(_pr[_p3_total_col]).strip()
            _ml = lambda v: "<br>".join(_html.escape(x.strip()) for x in str(v).split("\n"))
            _pr_rows.append(
                "<tr>" + "".join(f"<td>{c}</td>" for c in [
                    _pi + 1, _html.escape(str(_pr["Faculty Name"]).strip()), _html.escape(str(_pr["Tutor Department"]).strip()),
                    _html.escape(_mob) or MOBILE_BLANK, "<br>".join(_html.escape(x) for x in _dg_l),
                    _ml(_pr[_p3_branch_col]), "<br>".join(_html.escape(x) for x in _yr_l),
                    _ml(_pr[_p3_serial_col]), _html.escape(_tot)]) + "</tr>")
        _pr_head = "".join(f"<th>{h}</th>" for h in ["S.No.", "Name of Faculty", "Department", "Mobile No.", "Degree",
                                                       "Major Subject" if _p3_subj_type == "Major Subject" else "Branch",
                                                       "Year", "Serial No.", "Total Number of Students"])
        _pr_title = _html.escape(st.session_state.get("ph_line1", "") or "")
        _pr_summary = " &nbsp;|&nbsp; ".join(
            [f"<b>Total Students:</b> {len(db)}"]
            + [f"<b>{_html.escape(str(_y))}:</b> {int(_p3_yr_counts[_y])}" for _y in _p3_yr_order]
            + ([f"<b>Year Blank:</b> {_p3_yr_blank}"] if _p3_yr_blank else []))
        _pr_html = (f'<div style="text-align:center; font-family:Arial,sans-serif; margin-bottom:10px;">'
                    f'<div style="font-weight:700; font-size:18px;">{_pr_title}</div>'
                    f'<div style="font-weight:600; font-size:15px; margin-top:4px;">LIST OF GUARDIAN TUTORS</div></div>'
                    f'<div style="font-family:Arial,sans-serif; font-size:13px; margin:6px 0 10px 0;">{_pr_summary}</div>'
                    f'<table><thead><tr>{_pr_head}</tr></thead><tbody>{"".join(_pr_rows)}</tbody></table>')
        print_button(_pr_html, label="🖨️ Print करें (यह List)")

        _dlc1, _dlc2 = st.columns(2)
        with _dlc1:
            st.download_button("⬇️ CSV Download करें (सिर्फ़ देखने/print के लिए)", _dl.to_csv(index=False).encode("utf-8-sig"),
                               file_name="guardian_tutors_list.csv", mime="text/csv", use_container_width=True)
        with _dlc2:
            # Backup Export: wahi columns jo P3 ki table me dikhte hain (Template jaisa format) —
            # isi file ko "📤 फ़ाइल से List अपलोड करें" me dobara upload karke List wapas laayi ja sakti hai.
            _bk_rows = []
            for _bi, _br in _fac.reset_index(drop=True).iterrows():
                _bd, _by = [], []
                for _bc in str(_br[_p3_class_col]).split("\n"):
                    if _bc.strip():
                        _dg_b, _yr_b = parse_allotted_class(_bc)
                        _bd.append(_dg_b or _bc.strip())
                        _by.append(_yr_b or "")
                _bmob = str(_br["Mobile Number"]).strip()
                _bk_rows.append({
                    "S.No.": str(_bi + 1),
                    "Name of Faculty": str(_br["Faculty Name"]).strip(),
                    "Department": str(_br["Tutor Department"]).strip(),
                    "Mobile No.": "" if _bmob.strip("_ ") == "" else re.sub(r"\.0$", "", _bmob),
                    "Degree": "\n".join(_bd),
                    "Branch": "\n".join(x.strip() for x in str(_br[_p3_branch_col]).split("\n")),
                    "Year": "\n".join(_by),
                    "Serial No": "\n".join(x.strip() for x in str(_br[_p3_serial_col]).split("\n")),
                    "Total Number of Students": _p3_total_from_serial(_br[_p3_serial_col]) or str(_br[_p3_total_col]).strip(),
                })
            _bk = pd.DataFrame(_bk_rows, columns=["S.No.", "Name of Faculty", "Department", "Mobile No.", "Degree", "Branch",
                                                    "Year", "Serial No", "Total Number of Students"])
            st.download_button("💾 Backup Export (Excel)",
                               df_to_formatted_xlsx(_bk, sheet_name="Guardian Tutors"),
                               file_name=f"guardian_tutors_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                               mime=XLSX_MIME, use_container_width=True, type="primary",
                               help="P3 की table वाले ही columns। इसी फ़ाइल को P3 → '📤 फ़ाइल से List अपलोड करें' में डालकर List वापस ला सकते हैं।")

    # Degree -> Branch -> Year: teeno dropdown P2 ki List (database) se aate hain aur ek doosre par depend karte hain —
    # Degree chunne par sirf usi Degree ki Branch, Branch chunne par sirf usi (Degree + Branch) ka Year dikhta hai.
    P3_ALL_BRANCH = "ALL"      # Branch dropdown ka "ALL" option: us Degree + Year ki saari Branch ke Students

    def _p3_match(df, col, val):
        if not val or col not in df.columns or (col == "Branch" and val == P3_ALL_BRANCH):
            return df
        return df[df[col].astype(str).str.strip() == val]

    def _p3_uniq(df, col, norm=None):
        if col not in df.columns:
            return []
        # Value ko comma par todna nahi hai — Branch ke naam me khud comma ho sakta hai (jaise "B. Com in Banking, Financial Services ...")
        vals = [v.strip() for v in df[col].astype(str) if v.strip()]
        if norm:
            vals = [norm(v) for v in vals]
        return list(dict.fromkeys(sorted(vals)))

    _p3_deg_base = _p3_uniq(db, "Degree")

    def _p3_branch_base(deg):
        _b = _p3_uniq(_p3_match(db, "Degree", deg), "Branch")
        return ([P3_ALL_BRANCH] + _b) if _b else _b

    def _p3_year_base(deg, br):
        sub = _p3_match(_p3_match(db, "Degree", deg), "Branch", br)
        found = _p3_uniq(sub, "Current Year", normalize_course_year)
        ordered = [y for y in COURSE_YEAR_OPTIONS if y in found] + [y for y in found if y not in COURSE_YEAR_OPTIONS]
        return ordered or list(COURSE_YEAR_OPTIONS)

    def _p3_opts(base, extra=""):
        extra = str(extra).strip()
        return [""] + list(base) + ([extra] if extra and extra not in base else [])

    def _p3_guard(key, opts):
        # Upar wali choice badalne par agar neeche wali purani choice ab list me nahi hai to use khaali kar do
        if st.session_state.get(key, "") not in opts:
            st.session_state[key] = ""

    # ---- Serial No.: chune hue (Degree + Branch + Year) ke Students ko Name se A-Z karke 1..N Serial milta hai;
    # ek baar jo Serial kisi Tutor ko diya gaya wo usi Class me kisi aur Tutor ko nahi mil sakta ----
    def _p3_class_key(cls_text, br):
        _dg, _yr = parse_allotted_class(cls_text)
        return (_dg.strip().lower(), str(br).strip().lower(), _yr)

    def _p3_class_students(deg, br, yr):
        # Degree ka naam save hote waqt thoda badal sakta hai (B.Com -> B.Com.), isliye symbols/case ignore karke match karte hain
        _nk = lambda v: re.sub(r"[^a-z0-9]", "", str(v).lower())
        sub = _p3_match(db, "Branch", br)
        if "Degree" in sub.columns:
            sub = sub[sub["Degree"].map(_nk) == _nk(deg)]
        if "Current Year" in sub.columns:
            sub = sub[sub["Current Year"].astype(str).map(normalize_course_year).str.strip() == yr]
        sub = sub.assign(_k=sub["Student Name"].astype(str).str.strip().str.lower()).sort_values("_k", kind="stable")
        return sub.reset_index(drop=True)

    def _p3_taken(key, exclude_idx):
        """Isi Class (key) ke wo Serial jo dusre Tutors ko mil chuke: {serial_no: tutor_name}"""
        taken = {}
        for _ti, _tr in _fac.iterrows():
            if _ti == exclude_idx:
                continue
            _cl = str(_tr[_p3_class_col]).split("\n")
            _bl = str(_tr[_p3_branch_col]).split("\n")
            _sl = str(_tr[_p3_serial_col]).split("\n")
            for _li, _c in enumerate(_cl):
                if not _c.strip() or _li >= len(_sl):
                    continue
                if _p3_class_key(_c, _bl[_li] if _li < len(_bl) else "") == key:
                    for _a, _b in _p3_parse_ranges(_sl[_li])[0]:
                        for _n in range(_a, _b + 1):
                            taken[_n] = str(_tr["Faculty Name"]).strip() or "(बिना नाम)"
        return taken

    def _p3_serial_choices(deg, br, yr, exclude_idx, frm, extra=()):
        """FROM / TO dropdown ke options: sirf wahi Serial jo is Class me khaali hain (type karke bhi dhoondh sakte hain).
        TO me FROM se aage ke wahi Serial aate hain jo FROM se lagatar khaali hon (beech me kisi aur Tutor ka Serial na aaye)."""
        if not (deg and br and yr):
            return [""], [""]
        _n = len(_p3_class_students(deg, br, yr))
        _tk = _p3_taken(_p3_class_key(f"{deg} {yr}", br), exclude_idx)
        for _x in extra:                       # isi form ki pichhli lines me jo Serial is Class ke liye diye ja chuke
            _tk.setdefault(_x, "इसी Tutor की पिछली लाइन")
        _free = [n for n in range(1, _n + 1) if n not in _tk]
        _to = []
        if str(frm).strip().isdigit():
            _f = int(str(frm).strip())
            _n2 = _f + 1                       # TO me FROM ke BAAD ke Serial (sirf ek Serial ho to TO khaali chhodein)
            while _n2 <= _n and _n2 not in _tk:
                _to.append(_n2)
                _n2 += 1
        return [""] + [str(n) for n in _free], [""] + [str(n) for n in _to]

    def _p3_serial_panel(deg, br, yr, exclude_idx, uid, extra=()):
        if not (deg and br and yr):
            st.caption("ℹ️ Degree, Branch aur Year तीनों चुनने पर यहाँ उस Class के Serial No. की जानकारी दिखेगी।")
            return
        _stu = _p3_class_students(deg, br, yr)
        _tk = _p3_taken(_p3_class_key(f"{deg} {yr}", br), exclude_idx)
        for _x in extra:
            _tk.setdefault(_x, "इसी Tutor की पिछली लाइन")
        _free = [n for n in range(1, len(_stu) + 1) if n not in _tk]
        _msg = (f"📋 इस Class में कुल **{len(_stu)}** Students (नाम के A–Z क्रम में Serial 1–{len(_stu)}) · "
                f"✅ खाली Serial: **{_p3_compress(_free) or 'कोई नहीं'}**")
        if _tk:
            _by = {}
            for _n, _t in _tk.items():
                _by.setdefault(_t, []).append(_n)
            _msg += " · 🔒 पहले से दिए गए: " + "; ".join(f"{_p3_compress(v)} → {k}" for k, v in _by.items())
        st.caption(_msg)
        if len(_stu) and st.checkbox("👁️ इस Class के Students (Serial के साथ) दिखाएँ", key=f"p3_show_stu_{uid}"):
            _tbl = pd.DataFrame({
                "Serial No.": range(1, len(_stu) + 1),
                "Student Name": _stu["Student Name"].astype(str).str.strip(),
                "Father Name": _stu["Father Name"].astype(str).str.strip() if "Father Name" in _stu.columns else "",
                "Tutor": [_tk.get(n, "—") for n in range(1, len(_stu) + 1)],
            })
            st.dataframe(_tbl, hide_index=True, use_container_width=True)

    def _p3_validate(rows, exclude_idx):
        """rows = [(class_text, branch, serial_text)] — galtiyon ki list lautata hai (khaali = sab theek)"""
        errs, own = [], {}
        for _c, _b, _srl in rows:
            if not str(_srl).strip():
                continue
            _ranges, _bad = _p3_parse_ranges(_srl)
            if _bad:
                errs.append(f"'{_srl}' सही Serial No. नहीं है — FROM और TO में सिर्फ़ अंक (number) भरें, और TO, FROM से छोटा न हो।")
                continue
            _key = _p3_class_key(_c, _b)
            if not all(_key):
                continue
            _deg_raw, _yr_raw = parse_allotted_class(_c)
            _n_stu = len(_p3_class_students(_deg_raw, _b, _yr_raw))
            _tk = _p3_taken(_key, exclude_idx)
            _used = own.setdefault(_key, set())
            for _a, _z in _ranges:
                if _n_stu and _z > _n_stu:
                    errs.append(f"{_c} / {_b}: Serial {_a}-{_z} इस Class के कुल {_n_stu} Students से बाहर है।")
                for _n in range(_a, _z + 1):
                    if _n in _tk:
                        errs.append(f"{_c} / {_b}: Serial {_n} पहले से '{_tk[_n]}' को दिया जा चुका है।")
                        break
                    if _n in _used:
                        errs.append(f"{_c} / {_b}: Serial {_n} इसी Tutor की दूसरी लाइन में भी आ गया है।")
                        break
                _used.update(range(_a, _z + 1))
        return errs

    # ----------------------------------------------------------------
    # ➕ NAYA TUTOR JODEIN
    # ----------------------------------------------------------------
    with st.expander(f"➕ नया Tutor जोड़ें ({_p3_subj_type})"):
        _n_dept_opts = _dept_opts if _dept_opts else [""]
        if "p3_add_cls_n" not in st.session_state:
            st.session_state["p3_add_cls_n"] = 1
        with st.container():
            _n_tdept = st.selectbox("DEPARTMENT", _n_dept_opts, key="p3_add_tdept")
            _n_name = st.text_input("NAME OF GUARDIANS TUTORS", key="p3_add_name")
            _n_mob = st.text_input("MOBILE NO.", key="p3_add_mob")
            st.markdown(f"**Degree + Year + Branch + SERIAL NO. ({_p3_subj_type})** — हर Class के साथ उसका SERIAL NO. भी साथ में लिखें; "
                        "एक से ज़्यादा Class हों तो नीचे ➕ से और जोड़ी जोड़ें (जोड़ी हटाने पर Class के साथ उसका SERIAL NO. भी हट जाएगा)")
            _n_cls_vals, _n_srl_vals, _n_br_vals = [], [], []
            _n_used = {}      # {Class key: us Class ke wo Serial jo isi form ki pichhli lines me de diye}
            for _ci in range(st.session_state["p3_add_cls_n"]):
                _cc1, _cc3, _cc1y, _cc2, _cc2b = st.columns(5)
                with _cc1:
                    _n_deg = st.selectbox(f"Degree {_ci + 1}", _p3_opts(_p3_deg_base), key=f"p3_add_cls_{_ci}",
                                          help="P2 की List के Degree column से" if _ci == 0 else None)
                with _cc3:
                    _o = _p3_opts(_p3_branch_base(_n_deg))
                    _p3_guard(f"p3_add_br_{_ci}", _o)
                    _n_br = st.selectbox(f"Branch {_ci + 1}", _o, key=f"p3_add_br_{_ci}",
                                         help="चुने गए Degree की ही Branch दिखेंगी" if _ci == 0 else None)
                    _n_br_vals.append(_n_br)
                with _cc1y:
                    _o = _p3_opts(_p3_year_base(_n_deg, _n_br))
                    _p3_guard(f"p3_add_yr_{_ci}", _o)
                    _n_yr = st.selectbox(f"Year {_ci + 1}", _o, key=f"p3_add_yr_{_ci}",
                                         help="चुने गए Degree + Branch का ही Year दिखेगा" if _ci == 0 else None)
                _n_cls_vals.append(f"{_n_deg.strip()} {_n_yr}".strip())
                with _cc2:
                    _ck = _p3_class_key(f"{_n_deg} {_n_yr}", _n_br)
                    _of, _ = _p3_serial_choices(_n_deg, _n_br, _n_yr, None, "", _n_used.get(_ck, ()))
                    _p3_guard(f"p3_add_srl_{_ci}", _of)
                    _n_sf = st.selectbox(f"FROM SERIAL NO. {_ci + 1}", _of, key=f"p3_add_srl_{_ci}",
                                         help="सिर्फ़ खाली Serial दिखते हैं — scroll करें या number type करें" if _ci == 0 else None)
                with _cc2b:
                    _, _ot = _p3_serial_choices(_n_deg, _n_br, _n_yr, None, _n_sf, _n_used.get(_ck, ()))
                    _p3_guard(f"p3_add_srl_to_{_ci}", _ot)
                    _n_st = st.selectbox(f"TO SERIAL NO. {_ci + 1}", _ot, key=f"p3_add_srl_to_{_ci}",
                                         help="FROM से लगातार खाली Serial ही दिखते हैं" if _ci == 0 else None)
                _n_srl_vals.append(_p3_compose_serial(_n_sf, _n_st))
                _p3_serial_panel(_n_deg, _n_br, _n_yr, None, f"add_{_ci}", _n_used.get(_ck, ()))
                if all(_ck):
                    for _ra, _rb in _p3_parse_ranges(_n_srl_vals[-1])[0]:
                        _n_used.setdefault(_ck, set()).update(range(_ra, _rb + 1))
            _fb1, _fb2, _fb3 = st.columns(3)
            with _fb1:
                _n_save = st.button("💾 जोड़ें", type="primary", use_container_width=True, key="p3_add_save_btn")
            with _fb2:
                _n_add_cls = st.button("➕ Class + SERIAL जोड़ें", use_container_width=True, key="p3_add_addcls_btn")
            with _fb3:
                _n_rm_cls = st.button("➖ Class + SERIAL हटाएँ", use_container_width=True, key="p3_add_rmcls_btn",
                                                    disabled=st.session_state["p3_add_cls_n"] <= 1)
        if _n_add_cls:
            st.session_state["p3_add_cls_n"] += 1
            st.rerun()
        if _n_rm_cls and st.session_state["p3_add_cls_n"] > 1:
            _n_last = st.session_state["p3_add_cls_n"] - 1
            st.session_state.pop(f"p3_add_cls_{_n_last}", None)
            st.session_state.pop(f"p3_add_srl_{_n_last}", None)
            st.session_state.pop(f"p3_add_srl_to_{_n_last}", None)
            st.session_state.pop(f"p3_add_br_{_n_last}", None)
            st.session_state.pop(f"p3_add_yr_{_n_last}", None)
            st.session_state["p3_add_cls_n"] -= 1
            st.rerun()
        if _n_save:
            _n_errs = _p3_validate(list(zip(_n_cls_vals, _n_br_vals, _n_srl_vals)), None)
            if not _n_name.strip() and not _n_tdept.strip():
                st.warning("⚠️ कम से कम NAME या DEPARTMENT भरें।")
            elif _n_errs:
                for _m in _n_errs:
                    st.error("❌ " + _m)
            else:
                _n_pairs = [(c.strip(), s.strip(), b.strip()) for c, s, b in zip(_n_cls_vals, _n_srl_vals, _n_br_vals)
                            if c.strip() or s.strip() or b.strip()]
                _n_cls_ml = "\n".join(c for c, s, b in _n_pairs)
                _n_srl_ml = "\n".join(s for c, s, b in _n_pairs)
                _n_br_ml = "\n".join(b for c, s, b in _n_pairs)
                _new_row = {col: "" for col in FACULTY_COLUMNS}
                _new_row.update({
                    "Faculty Name": _n_name.strip(),
                    "Designation": "",
                    "Mobile Number": _n_mob.strip(),
                    "Tutor Department": _n_tdept.strip(),
                    _p3_class_col: _n_cls_ml,
                    _p3_serial_col: _n_srl_ml,
                    _p3_branch_col: _n_br_ml,
                    _p3_total_col: _p3_total_from_serial(_n_srl_ml),
                })
                _fac2 = pd.concat([_fac, pd.DataFrame([_new_row])], ignore_index=True)
                save_faculty(_fac2[FACULTY_COLUMNS])
                for _k in [k for k in list(st.session_state.keys())
                           if k.startswith("p3_add_cls_") or k.startswith("p3_add_srl_") or k.startswith("p3_add_br_")
                           or k.startswith("p3_add_yr_")]:
                    st.session_state.pop(_k, None)
                st.session_state["p3_add_cls_n"] = 1
                st.session_state["p3_fac_flash"] = f"✅ '{_n_name.strip() or '(बिना नाम)'}' जुड़ गए।"
                st.rerun()

    # ---- ✏️ EDIT FORM (Actions column ke ✏️ Edit button se khulta hai) ----
    _eidx = st.session_state.get("p3_edit_idx")
    if _eidx is not None and _eidx in _fac.index:
        _erow = _fac.loc[_eidx]
        st.markdown(f"### ✏️ Tutor की Details Edit करें — Subject Type: **{_p3_subj_type}**")
        st.caption("ℹ️ NAME / MOBILE NO. / DEPARTMENT badalne se sabhi Subject Types ke liye badal jayenge (ye common hain); "
                   "'Allotted Class + SERIAL NO.' sirf upar chuni gayi Subject Type ('" + _p3_subj_type + "') ke liye save hoga, "
                   "baaki Subject Types ka data chhua nahi jaayega.")
        _ecls_key = f"p3_edit_cls_n_{_eidx}_{_p3_subj_type}"
        if _ecls_key not in st.session_state:
            _raw_cls = [c for c in _erow[_p3_class_col].split("\n")]
            _raw_srl = [x for x in _erow[_p3_serial_col].split("\n")]
            _raw_br = [b for b in str(_erow[_p3_branch_col]).split("\n")]
            # Ek line me ek se zyada Serial range ho (jaise "1-10, 15-20") to har range ki alag line banti hai
            _existing_cls, _existing_br, _existing_from, _existing_to = [], [], [], []
            for _i in range(max(1, len(_raw_cls), len(_raw_srl), len(_raw_br))):
                _c = _raw_cls[_i] if _i < len(_raw_cls) else ""
                _b = _raw_br[_i] if _i < len(_raw_br) else ""
                _sr = _raw_srl[_i] if _i < len(_raw_srl) else ""
                _rg, _bad = _p3_parse_ranges(_sr)
                if _bad or not _rg:
                    _pieces = [(_sr.strip(), "")]
                else:
                    _pieces = [(str(x), "" if x == y else str(y)) for x, y in _rg]
                for _pf, _pt in _pieces:
                    _existing_cls.append(_c); _existing_br.append(_b)
                    _existing_from.append(_pf); _existing_to.append(_pt)
            _n_pairs_init = len(_existing_cls)
            st.session_state[_ecls_key] = _n_pairs_init
            for _ci in range(_n_pairs_init):
                _ex_deg, _ex_yr = parse_allotted_class(_existing_cls[_ci])
                st.session_state[f"p3_edit_cls_{_eidx}_{_p3_subj_type}_{_ci}"] = _ex_deg
                st.session_state[f"p3_edit_yr_{_eidx}_{_p3_subj_type}_{_ci}"] = _ex_yr if _ex_yr in COURSE_YEAR_OPTIONS else ""
                st.session_state[f"p3_edit_orig_{_eidx}_{_p3_subj_type}_{_ci}"] = (
                    _ex_deg, _existing_br[_ci], _ex_yr if _ex_yr in COURSE_YEAR_OPTIONS else "")
                st.session_state[f"p3_edit_srl_{_eidx}_{_p3_subj_type}_{_ci}"] = _existing_from[_ci]
                st.session_state[f"p3_edit_srl_to_{_eidx}_{_p3_subj_type}_{_ci}"] = _existing_to[_ci]
                st.session_state[f"p3_edit_br_{_eidx}_{_p3_subj_type}_{_ci}"] = _existing_br[_ci]
        with st.container():
            _e_name = st.text_input("NAME OF GUARDIANS TUTORS", value=_erow["Faculty Name"])
            _e_mob = st.text_input("MOBILE NO.", value=_erow["Mobile Number"])
            _e_dept_opts = _dept_opts if _dept_opts else [""]
            _e_dept_idx = _e_dept_opts.index(_erow["Tutor Department"]) if _erow["Tutor Department"] in _e_dept_opts else 0
            _e_tdept = st.selectbox("DEPARTMENT", _e_dept_opts, index=_e_dept_idx)
            st.markdown(f"**Allotted Class ({_p3_subj_type}) + SERIAL NO.** — हर Class के साथ उसका SERIAL NO. भी साथ में लिखें; "
                        "जोड़ी हटाने पर Class के साथ उसका SERIAL NO. भी हट जाएगा")
            _e_cls_vals, _e_srl_vals, _e_br_vals = [], [], []
            _e_used = {}
            for _ci in range(st.session_state[_ecls_key]):
                _ecc1, _ecc3, _ecc1y, _ecc2, _ecc2b = st.columns(5)
                _orig = st.session_state.get(f"p3_edit_orig_{_eidx}_{_p3_subj_type}_{_ci}", ("", "", ""))
                with _ecc1:
                    _e_deg = st.selectbox(f"Degree {_ci + 1}", _p3_opts(_p3_deg_base, _orig[0]),
                                          key=f"p3_edit_cls_{_eidx}_{_p3_subj_type}_{_ci}")
                with _ecc3:
                    _o = _p3_opts(_p3_branch_base(_e_deg), _orig[1] if _e_deg == _orig[0] else "")
                    _p3_guard(f"p3_edit_br_{_eidx}_{_p3_subj_type}_{_ci}", _o)
                    _e_br = st.selectbox(f"Branch {_ci + 1}", _o, key=f"p3_edit_br_{_eidx}_{_p3_subj_type}_{_ci}")
                    _e_br_vals.append(_e_br)
                with _ecc1y:
                    _o = _p3_opts(_p3_year_base(_e_deg, _e_br), _orig[2] if (_e_deg == _orig[0] and _e_br == _orig[1]) else "")
                    _p3_guard(f"p3_edit_yr_{_eidx}_{_p3_subj_type}_{_ci}", _o)
                    _e_yr = st.selectbox(f"Year {_ci + 1}", _o, key=f"p3_edit_yr_{_eidx}_{_p3_subj_type}_{_ci}")
                _e_cls_vals.append(f"{_e_deg.strip()} {_e_yr}".strip())
                with _ecc2:
                    _ck = _p3_class_key(f"{_e_deg} {_e_yr}", _e_br)
                    _of, _ = _p3_serial_choices(_e_deg, _e_br, _e_yr, _eidx, "", _e_used.get(_ck, ()))
                    _same_cls = (_e_deg, _e_br, _e_yr) == tuple(_orig)
                    _cur_f = st.session_state.get(f"p3_edit_srl_{_eidx}_{_p3_subj_type}_{_ci}", "")
                    if _same_cls and _cur_f and _cur_f not in _of:
                        _of = _of + [_cur_f]      # purana (P2 se na milne wala) Serial ud na jaye
                    _p3_guard(f"p3_edit_srl_{_eidx}_{_p3_subj_type}_{_ci}", _of)
                    _e_sf = st.selectbox(f"FROM SERIAL NO. {_ci + 1}", _of, key=f"p3_edit_srl_{_eidx}_{_p3_subj_type}_{_ci}")
                with _ecc2b:
                    _, _ot = _p3_serial_choices(_e_deg, _e_br, _e_yr, _eidx, _e_sf, _e_used.get(_ck, ()))
                    _cur_t = st.session_state.get(f"p3_edit_srl_to_{_eidx}_{_p3_subj_type}_{_ci}", "")
                    if _same_cls and _cur_t and _cur_t not in _ot:
                        _ot = _ot + [_cur_t]
                    _p3_guard(f"p3_edit_srl_to_{_eidx}_{_p3_subj_type}_{_ci}", _ot)
                    _e_st = st.selectbox(f"TO SERIAL NO. {_ci + 1}", _ot, key=f"p3_edit_srl_to_{_eidx}_{_p3_subj_type}_{_ci}")
                _e_srl_vals.append(_p3_compose_serial(_e_sf, _e_st))
                _p3_serial_panel(_e_deg, _e_br, _e_yr, _eidx, f"edit_{_eidx}_{_ci}", _e_used.get(_ck, ()))
                if all(_ck):
                    for _ra, _rb in _p3_parse_ranges(_e_srl_vals[-1])[0]:
                        _e_used.setdefault(_ck, set()).update(range(_ra, _rb + 1))
            st.caption("ℹ️ TOTAL NUMBER OF STUDENTS Save karne par SERIAL NO. se apne aap calculate ho jayega — "
                       "abhi ke hisaab se: **" + (_p3_total_from_serial(_erow[_p3_serial_col]) or _erow[_p3_total_col] or "—") + "**")
            _ef1, _ef2, _ef3 = st.columns(3)
            with _ef1:
                _e_save = st.button("💾 Save", type="primary", use_container_width=True, key="p3_edit_save_btn")
            with _ef2:
                _e_cancel = st.button("✖️ Cancel", use_container_width=True, key="p3_edit_cancel_btn")
            with _ef3:
                _e_delete = st.button("🗑️ Delete करें", use_container_width=True, key="p3_edit_delete_btn")
            _ef4, _ef5 = st.columns(2)
            with _ef4:
                _e_add_cls = st.button("➕ Class + SERIAL जोड़ें", use_container_width=True, key="p3_edit_addcls_btn")
            with _ef5:
                _e_rm_cls = st.button("➖ Class + SERIAL हटाएँ", use_container_width=True, key="p3_edit_rmcls_btn",
                                                    disabled=st.session_state[_ecls_key] <= 1)

        def _p3_edit_reset_cls_state():
            st.session_state.pop(_ecls_key, None)
            for _k in [k for k in list(st.session_state.keys())
                       if k.startswith(f"p3_edit_cls_{_eidx}_{_p3_subj_type}_") or k.startswith(f"p3_edit_srl_{_eidx}_{_p3_subj_type}_")
                       or k.startswith(f"p3_edit_br_{_eidx}_{_p3_subj_type}_") or k.startswith(f"p3_edit_yr_{_eidx}_{_p3_subj_type}_")
                       or k.startswith(f"p3_edit_orig_{_eidx}_{_p3_subj_type}_")
                       or k.startswith(f"p3_edit_srl_to_{_eidx}_{_p3_subj_type}_")]:
                st.session_state.pop(_k, None)

        if _e_add_cls:
            st.session_state[_ecls_key] += 1
            st.rerun()
        if _e_rm_cls and st.session_state[_ecls_key] > 1:
            _e_last = st.session_state[_ecls_key] - 1
            st.session_state.pop(f"p3_edit_cls_{_eidx}_{_p3_subj_type}_{_e_last}", None)
            st.session_state.pop(f"p3_edit_srl_{_eidx}_{_p3_subj_type}_{_e_last}", None)
            st.session_state.pop(f"p3_edit_srl_to_{_eidx}_{_p3_subj_type}_{_e_last}", None)
            st.session_state.pop(f"p3_edit_br_{_eidx}_{_p3_subj_type}_{_e_last}", None)
            st.session_state.pop(f"p3_edit_yr_{_eidx}_{_p3_subj_type}_{_e_last}", None)
            st.session_state[_ecls_key] -= 1
            st.rerun()
        _e_errs = _p3_validate(list(zip(_e_cls_vals, _e_br_vals, _e_srl_vals)), _eidx) if _e_save else []
        if _e_save and _e_errs:
            for _m in _e_errs:
                st.error("❌ " + _m)
            _e_save = False
        if _e_save:
            _e_pairs = [(c.strip(), s.strip(), b.strip()) for c, s, b in zip(_e_cls_vals, _e_srl_vals, _e_br_vals)
                        if c.strip() or s.strip() or b.strip()]
            _e_cls_ml = "\n".join(c for c, s, b in _e_pairs)
            _e_srl_ml = "\n".join(s for c, s, b in _e_pairs)
            _e_br_ml = "\n".join(b for c, s, b in _e_pairs)
            _fac.loc[_eidx, "Faculty Name"] = _e_name.strip()
            _fac.loc[_eidx, "Mobile Number"] = _e_mob.strip()
            _fac.loc[_eidx, "Tutor Department"] = _e_tdept.strip()
            _fac.loc[_eidx, _p3_class_col] = _e_cls_ml
            _fac.loc[_eidx, _p3_serial_col] = _e_srl_ml
            _fac.loc[_eidx, _p3_branch_col] = _e_br_ml
            _fac.loc[_eidx, _p3_total_col] = _p3_total_from_serial(_e_srl_ml) or _erow[_p3_total_col]
            save_faculty(_fac)
            _p3_edit_reset_cls_state()
            st.session_state.pop("p3_edit_idx", None)
            st.session_state["p3_fac_flash"] = f"✅ '{_e_name.strip() or '(बिना नाम)'}' की Details Update हो गईं।"
            st.rerun()
        if _e_cancel:
            _p3_edit_reset_cls_state()
            st.session_state.pop("p3_edit_idx", None)
            st.rerun()
        if _e_delete:
            _p3_edit_reset_cls_state()
            _fac = _fac.drop(index=_eidx).reset_index(drop=True)
            save_faculty(_fac)
            st.session_state.pop("p3_edit_idx", None)
            st.session_state["p3_fac_flash"] = "🗑️ Tutor हटा दिया गया।"
            st.rerun()

    # ---- 📌 ASSIGN FORM (Actions column ke 📌 Assign button se khulta hai — P4 jaisi Assign process) ----
    _asidx = st.session_state.get("p3_assign_idx")
    if _asidx is not None and _asidx in _fac.index:
        _asrow = _fac.loc[_asidx]
        _as_name = _asrow["Faculty Name"].strip() or "(बिना नाम)"
        st.markdown(f"### 📌 **{_as_name}** को Students Assign करें")
        _as_dept_opts = st.session_state.departments if st.session_state.departments else [""]
        _as_dept_default = _asrow["Tutor Department"] if _asrow["Tutor Department"] in _as_dept_opts else (
            _asrow["Department"] if _asrow["Department"] in _as_dept_opts else _as_dept_opts[0])
        _as_dept = st.selectbox("किस Department के Students में से चुनना है?", _as_dept_opts,
                                 index=_as_dept_opts.index(_as_dept_default), key=f"p3_assign_dept_{_asidx}")
        _pool = db[(db["Assigned Department"] == _as_dept) & (db["Status"] == "Approved")].copy()
        _only_unassigned = st.checkbox(
            "सिर्फ़ वो Students दिखाएँ जो अभी तक किसी Tutor को Assign नहीं हुए",
            value=True, key=f"p3_assign_only_unassigned_{_asidx}")
        if _only_unassigned:
            _pool = _pool[_pool["Assigned Tutor"].astype(str).str.strip() == ""]
        if _pool.empty:
            st.info("📭 इस Department में Assign करने के लिए कोई Student नहीं मिला।")
        else:
            _pool_disp = _pool.reset_index()   # 'index' column me asli db index safe rehta hai
            _pool_disp.insert(0, "चुनें", False)
            _pick_cols = ["चुनें", "Student Name", "Father Name", "Mobile Number", "Assigned Tutor"]
            _picked = st.data_editor(
                _pool_disp[_pick_cols],
                hide_index=True, use_container_width=True,
                disabled=["Student Name", "Father Name", "Mobile Number", "Assigned Tutor"],
                column_config={"चुनें": st.column_config.CheckboxColumn("चुनें")},
                key=f"p3_assign_editor_{_asidx}",
            )
            _sel_pos = _picked.index[_picked["चुनें"] == True].tolist()
            _af1, _af2 = st.columns(2)
            with _af1:
                _do_assign = st.button(f"📌 चुने गए {len(_sel_pos)} Students को Assign करें", type="primary",
                                        use_container_width=True, disabled=not _sel_pos, key=f"p3_do_assign_{_asidx}")
            with _af2:
                _cancel_assign = st.button("✖️ Cancel", use_container_width=True, key=f"p3_cancel_assign_{_asidx}")
            if _do_assign:
                _orig_idx = _pool_disp.loc[_sel_pos, "index"].tolist()
                db.loc[_orig_idx, "Assigned Tutor"] = _as_name
                save_db(db)
                st.session_state.pop("p3_assign_idx", None)
                st.session_state["p3_fac_flash"] = f"✅ {len(_orig_idx)} Students '{_as_name}' को Assign कर दिए गए।"
                st.rerun()
            if _cancel_assign:
                st.session_state.pop("p3_assign_idx", None)
                st.rerun()


# ==========================================================
# 🏢 P4 — DEPARTMENT PANEL
# ==========================================================
elif choice in ("P4 — Department Panel", "P4 — My Department List"):
    st.header("🏢 P4 — Department-wise List")
    _p4_rows = filter_for_panel(db, "P4")
    approved = _p4_rows[_p4_rows["Status"] == "Approved"].copy()
    faculty_db = load_faculty()

    if role == "admin":
        with st.expander("📤 Department – Faculty Mapping अपलोड/अपडेट करें"):
            faculty_upload_ui("p4")

            if not faculty_db.empty:
                st.markdown("**मौजूदा Faculty Mapping:**")
                st.dataframe(faculty_db, use_container_width=True, hide_index=True)

    if role == "admin":
        target_dept = st.selectbox("Department चुनें", st.session_state.departments)
    else:
        target_dept = user_dept
        st.caption(f"आप लॉगिन हैं: **{target_dept}** — आपको सिर्फ़ इसी Department को Assign की गई entries दिखेंगी।")

    dept_faculty = faculty_db[(faculty_db["Tutor Department"] == target_dept) | (faculty_db["Department"] == target_dept)]
    if not dept_faculty.empty:
        for _, frow in dept_faculty.iterrows():
            line = f"👩‍🏫 **{frow['Faculty Name']}**"
            if str(frow.get("Designation", "")).strip():
                line += f" ({frow['Designation']})"
            if str(frow.get("Mobile Number", "")).strip():
                line += f" — 📱 {frow['Mobile Number']}"
            if str(frow.get("Number of Students", "")).strip():
                line += f" — 👥 {frow['Number of Students']} Students"
            st.info(line)
    else:
        st.caption("ℹ️ इस Department के लिए अभी कोई Faculty mapping उपलब्ध नहीं है (ऊपर 'Department – Faculty Mapping' से अपलोड करें)।")

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
    st.caption("यहाँ से आप किसी भी List को अपने college के letterhead-style header के साथ खूबसूरती से Print कर सकते हैं।")

    # ---- Print Header Customizer (3 lines + Guardian Tutor info row) ----
    st.subheader("📝 Print Header Customizer")
    _ph_defaults = {
        "ph_line1": "GOVERNMENT KAMLARAJA GIRLS POST GRADUATE (AUTO.) COLLEGE, GWALIOR",
        "ph_size1": 20, "ph_color1": "#0F2A4A",
        "ph_line2": "B.Com. FIRST YEAR (SESSION: 2025-26)",
        "ph_course": "B.Com. FIRST YEAR",
        "ph_size2": 16, "ph_color2": "#0F2A4A",
        "ph_line3": "Mentor/Guardian Tutor List, Major Subject - Commerce",
        "ph_title3": "Mentor/Guardian Tutor List",
        "ph_size3": 14, "ph_color3": "#A97A25",
        "ph_guardian_name": "", "ph_guardian_mobile": "",
    }
    for _k, _v in _ph_defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    # ---- Guardian Tutor ke P3 wale Allotted Class (jaise "PGDCA\nPGDCA\nPGDCA" +
    # Serial No "1-10\n16-20\n11-15") se Course/Class dropdown auto-fill karna, aur
    # agar ek se zyada Allotted Class/Serial No pairs hon to unhe Header me stacked
    # (ek ke niche ek, apne Serial No ke saath) print karne ke liye taiyaar karna ----
    _PH_OTHER_OPT = "✍️ अन्य (खुद लिखें)"
    _p5_fac_early = load_faculty().reset_index(drop=True)
    _p5_fac_early = _p5_fac_early[_p5_fac_early["Faculty Name"].astype(str).str.strip() != ""]
    _p5_opts_early = {}
    for _i, _r in _p5_fac_early.iterrows():
        _lbl = str(_r["Faculty Name"]).strip()
        _lbl_extra = str(_r["Tutor Department"]).strip() or str(_r["Department"]).strip()
        if _lbl_extra:
            _lbl += f" — {_lbl_extra}"
        if _lbl in _p5_opts_early:
            _lbl += f" (#{_i + 1})"
        _p5_opts_early[_lbl] = _r
    _p5_current_pick = st.session_state.get("ph_guardian_pick")
    st.session_state["ph_allotted_lines"] = []
    st.session_state["ph_sel_defs"] = []
    st.session_state["ph_line_opts"] = []
    if _p5_current_pick and _p5_current_pick in _p5_opts_early:
        _p5_row_early = _p5_opts_early[_p5_current_pick]
        _cls_lines = [c.strip() for c in str(_p5_row_early["Department"]).split("\n")]
        _srl_lines = [s.strip() for s in str(_p5_row_early["Serial No"]).split("\n")]
        _pair_n = max(len(_cls_lines), len(_srl_lines))
        _allotted_pairs = []
        for _pi in range(_pair_n):
            _c = _cls_lines[_pi] if _pi < len(_cls_lines) else ""
            _s = _srl_lines[_pi] if _pi < len(_srl_lines) else ""
            if _c or _s:
                _allotted_pairs.append((_c, _s))
        _br_lines_early = [b.strip() for b in str(_p5_row_early["Branch"]).split("\n")]
        _defs = []
        for _pi in range(_pair_n):
            _c = _cls_lines[_pi] if _pi < len(_cls_lines) else ""
            if not _c:
                continue
            _s = _srl_lines[_pi] if _pi < len(_srl_lines) else ""
            _b = _br_lines_early[_pi] if _pi < len(_br_lines_early) else ""
            _p_course, _p_year = parse_allotted_class(_c)
            _p_year_lbl = COURSE_YEAR_PRINT_LABELS.get(_p_year, _p_year)
            _line_txt = f"{_p_course} {_p_year_lbl}".strip()
            if _s:
                _line_txt += f" ({_s})"
            _defs.append({"c": _c, "s": _s, "b": _b, "label": _line_txt})
        # Ek se zyada List (Class line) ho to pehle puchha jaata hai ki kaun si List print karni hai
        _ALL_LISTS_OPT = "📚 सभी Lists (एक साथ)"
        _line_opts = []
        if len(_defs) > 1:
            _line_opts = [f"{_n + 1}. {_d['label']}" + (f" — {_d['b']}" if _d["b"] else "") for _n, _d in enumerate(_defs)]
            _line_opts.append(_ALL_LISTS_OPT)
            if st.session_state.get("ph_line_pick") not in _line_opts:
                st.session_state["ph_line_pick"] = _line_opts[0]
            _pk = st.session_state["ph_line_pick"]
            _sel_defs = _defs if _pk == _ALL_LISTS_OPT else [_defs[_line_opts.index(_pk)]]
        else:
            _sel_defs = _defs
        st.session_state["ph_line_opts"] = _line_opts
        st.session_state["ph_sel_defs"] = _sel_defs
        _built_lines = [_d["label"] for _d in _sel_defs]
        st.session_state["ph_allotted_lines"] = _built_lines
        # Sirf tab auto-fill karo jab Tutor ki selection abhi-abhi badli ho — taaki
        # baad me haath se badla gaya Course/Class dobara reset na ho
        _auto_key = f"{_p5_current_pick}|{_sel_defs[0]['c'] if _sel_defs else ''}"
        if st.session_state.get("ph_last_auto_guardian") != _auto_key and _allotted_pairs:
            _auto_course, _auto_year = parse_allotted_class(_sel_defs[0]["c"] if _sel_defs else _allotted_pairs[0][0])
            if _auto_course:
                if _auto_course in COURSE_NAME_OPTIONS:
                    st.session_state["ph_course_pick"] = _auto_course
                    st.session_state.pop("ph_course_custom", None)
                else:
                    st.session_state["ph_course_pick"] = _PH_OTHER_OPT
                    st.session_state["ph_course_custom"] = _auto_course
            if _auto_year:
                if _auto_year in COURSE_YEAR_OPTIONS:
                    st.session_state["ph_class_pick"] = _auto_year
                    st.session_state.pop("ph_class_custom", None)
                else:
                    st.session_state["ph_class_pick"] = _PH_OTHER_OPT
                    st.session_state["ph_class_custom"] = _auto_year
            st.session_state["ph_last_auto_guardian"] = _auto_key
    else:
        st.session_state["ph_last_auto_guardian"] = _p5_current_pick

    st.session_state.ph_line1 = st.text_input("Header Line 1 (College Name)", value=st.session_state.ph_line1)
    l1a, l1b = st.columns(2)
    with l1a:
        st.session_state.ph_size1 = st.slider("Line 1 Font Size (px)", 12, 40, st.session_state.ph_size1)
    with l1b:
        st.session_state.ph_color1 = st.color_picker("Line 1 Color", st.session_state.ph_color1)

    ph_c1, ph_c2 = st.columns(2)
    with ph_c1:
        st.markdown("**Header Line 2 — Course / Class**")
        cc1, cc2 = st.columns(2)
        _course_other = _PH_OTHER_OPT
        with cc1:
            _course_all_opts = COURSE_NAME_OPTIONS + [_course_other]
            _course_default_idx = COURSE_NAME_OPTIONS.index("B.Com.") if "B.Com." in COURSE_NAME_OPTIONS else 0
            _course_pick = st.selectbox("Course चुनें", _course_all_opts, index=_course_default_idx, key="ph_course_pick")
            if _course_pick == _course_other:
                _course_val = st.text_input("Course खुद लिखें", key="ph_course_custom").strip()
            else:
                _course_val = _course_pick
        with cc2:
            _class_all_opts = COURSE_YEAR_OPTIONS + [_course_other]
            _class_pick = st.selectbox("Class / Year चुनें", _class_all_opts, key="ph_class_pick")
            if _class_pick == _course_other:
                _class_val = st.text_input("Class / Year खुद लिखें", key="ph_class_custom").strip()
            else:
                _class_val = COURSE_YEAR_PRINT_LABELS.get(_class_pick, _class_pick)
        st.session_state.ph_course = f"{_course_val} {_class_val}".strip()
        st.caption(f"➡️ Course / Class Line: **{st.session_state.ph_course or '—'}**")
        # SESSION: aap se puchha jaata hai — list me se chunein (jaise 2026-27, 1999-00) ya "अन्य" me khud likhein
        _sess_other = "✍️ अन्य (खुद लिखें)"
        _sess_opts = [f"{y}-{str(y + 1)[-2:]}" for y in range(1990, 2041)] + [_sess_other]
        _sess_pick = st.selectbox("SESSION कौन सा है?", _sess_opts, index=_sess_opts.index("2025-26"), key="ph_session_pick")
        if _sess_pick == _sess_other:
            _sess_val = st.text_input("Session खुद लिखें (जैसे 2026-27)", key="ph_session_custom").strip()
        else:
            _sess_val = _sess_pick
        _course_txt = st.session_state.ph_course.strip()
        _sess_txt = f"SESSION: {_sess_val}" if _sess_val else ""
        st.session_state.ph_line2 = (f"{_course_txt} ({_sess_txt})" if _course_txt and _sess_txt
                                     else (_course_txt or _sess_txt))
        s2a, s2b = st.columns(2)
        with s2a:
            st.session_state.ph_size2 = st.slider("Line 2 Font Size (px)", 8, 30, st.session_state.ph_size2)
        with s2b:
            st.session_state.ph_color2 = st.color_picker("Line 2 Color", st.session_state.ph_color2)
    with ph_c2:
        st.session_state.ph_title3 = st.text_input("Header Line 3 — List Title", value=st.session_state.ph_title3)
        st.caption("📘 Line 3 में ', Major Subject - …' अपने आप जुड़ता है — चुने गए Guardian Tutor की P3 वाली Branch से "
                   "(Tutor न चुना हो तो List के Students की Branch से)।")
        s3a, s3b = st.columns(2)
        with s3a:
            st.session_state.ph_size3 = st.slider("Line 3 Font Size (px)", 8, 30, st.session_state.ph_size3)
        with s3b:
            st.session_state.ph_color3 = st.color_picker("Line 3 Color", st.session_state.ph_color3)

    # ---- Guardian Tutor: naam aur mobile P3 ki Guardian Tutors List se aate hain ----
    _p5_fac = load_faculty().reset_index(drop=True)
    _p5_fac = _p5_fac[_p5_fac["Faculty Name"].astype(str).str.strip() != ""]
    _p5_blank_opt = "— खाली छोड़ें (Print में हाथ से लिखने की जगह) —"
    _p5_opts = {}
    for _i, _r in _p5_fac.iterrows():
        _lbl = str(_r["Faculty Name"]).strip()
        _lbl_extra = str(_r["Tutor Department"]).strip() or str(_r["Department"]).strip()
        if _lbl_extra:
            _lbl += f" — {_lbl_extra}"
        if _lbl in _p5_opts:
            _lbl += f" (#{_i + 1})"
        _p5_opts[_lbl] = _r
    _p5_choices = [_p5_blank_opt] + list(_p5_opts.keys())
    if st.session_state.get("ph_guardian_pick") not in _p5_choices:
        st.session_state.pop("ph_guardian_pick", None)        # List बदल गई हो तो पुरानी चॉइस हटाएँ
    _p5_pick = st.selectbox("Guardian Tutor चुनें (P3 की List से)", _p5_choices, key="ph_guardian_pick",
                            index=1 if len(_p5_opts) == 1 else 0)
    if _p5_pick == _p5_blank_opt:
        st.session_state.ph_guardian_name = ""
        st.session_state.ph_guardian_mobile = ""
        if _p5_fac.empty:
            st.caption("📭 P3 की Guardian Tutors List अभी खाली है — पहले P3 में List जोड़ें।")
        else:
            st.caption("कोई Tutor नहीं चुना — Print में Name और Mobile की जगह हाथ से लिखने के लिए खाली रहेगी।")
    else:
        _p5_row = _p5_opts[_p5_pick]
        st.session_state.ph_guardian_name = str(_p5_row["Faculty Name"]).strip()
        st.session_state.ph_guardian_mobile = re.sub(r"\.0$", "", str(_p5_row["Mobile Number"]).strip())
        st.caption(f"👩‍🏫 **{st.session_state.ph_guardian_name}** — 📱 "
                   + (st.session_state.ph_guardian_mobile or "Mobile No. P3 की List में खाली है (P3 में भरें)"))
        if st.session_state.get("ph_allotted_lines"):
            st.caption("📚 इस Tutor के Allotted Class (P3 से) — Header में यह सब ek ke niche ek print होंगे:  \n"
                       + "  \n".join(f"• {_l}" for _l in st.session_state["ph_allotted_lines"]))

    if st.session_state.get("ph_line_opts"):
        st.selectbox("📋 इस Tutor की एक से ज़्यादा List हैं — कौन सी List Print करनी है?",
                     st.session_state["ph_line_opts"], key="ph_line_pick")

    _blank_line = "&nbsp;" * 22

    def _build_header_html(font_family, line2_override=None):
        guardian_val = st.session_state.ph_guardian_name.strip() or _blank_line
        mobile_val = st.session_state.ph_guardian_mobile.strip() or MOBILE_BLANK
        _allotted_lines = st.session_state.get("ph_allotted_lines") or []
        if line2_override is not None:
            _line2_html = line2_override
        elif _allotted_lines:
            # Ek se zyada Allotted Class + Serial No hon to sab ek ke niche ek print honge
            _stacked = "<br>".join(_allotted_lines)
            _line2_html = f"{_stacked}<br>{_sess_txt}" if _sess_txt else _stacked
        else:
            _line2_html = st.session_state.ph_line2
        return f"""
        <div style="text-align:center; font-family:{font_family};">
            <div style="font-weight:700; font-size:{st.session_state.ph_size1}px; color:{st.session_state.ph_color1};">
                {st.session_state.ph_line1 or "&nbsp;"}
            </div>
            <div style="font-weight:700; font-size:{st.session_state.ph_size2}px; color:{st.session_state.ph_color2}; margin-top:4px;">
                {_line2_html or "&nbsp;"}
            </div>
            <div style="font-weight:600; font-size:{st.session_state.ph_size3}px; color:{st.session_state.ph_color3}; margin-top:4px;">
                {st.session_state.ph_line3 or "&nbsp;"}
            </div>
            <div style="display:flex; justify-content:space-between; margin-top:12px; font-size:14px; text-align:left;">
                <div>Name of Guardian Tutor - <b>{guardian_val}</b></div>
                <div>Mobile No- <b>{mobile_val}</b></div>
            </div>
        </div>
        """

    st.markdown("---")

    # ---- Data: P5 poore database se list uthata hai (Status / Department / Search ke filters hata diye gaye hain).
    # Sirf non-admin user ko uske apne Department ke records hi milte hain. ----
    pp_view = db.copy()
    if role != "admin":
        pp_view = pp_view[pp_view["Assigned Department"] == user_dept]
        st.caption(f"Department: **{user_dept}**")

    # ---- Upar jo Guardian Tutor chuna gaya hai, uske P3 wale Allotted Class (Degree + Branch + Year) aur
    # FROM-TO SERIAL NO. ke hisaab se Students apne aap aate hain: us Class ke Students ko Name se A-Z karke
    # 1..N Serial milta hai, aur Tutor ke Serial range wale Students hi List me aate hain. ----
    _p5_guardian_active = st.session_state.ph_guardian_name.strip()
    _serial_map = {}      # {db index: us Student ka P3 wala Serial No. (apni Class ki A-Z list me)}
    if _p5_guardian_active and _p5_pick != _p5_blank_opt:
        _p5_trow = _p5_opts[_p5_pick]
        _nk5 = lambda v: re.sub(r"[^a-z0-9]", "", str(v).lower())
        _keep5, _diag5 = [], []
        for _d5 in st.session_state.get("ph_sel_defs", []):
            _c5, _b5, _s5 = _d5["c"], _d5["b"].strip(), _d5["s"]
            _dg5, _yr5 = parse_allotted_class(_c5)
            _rg5 = _p3_parse_ranges(_s5)[0]
            _cls5 = db
            if _b5 and _b5 != "ALL" and "Branch" in _cls5.columns:
                _cls5 = _cls5[_cls5["Branch"].astype(str).str.strip() == _b5]
            if _dg5 and "Degree" in _cls5.columns:
                _cls5 = _cls5[_cls5["Degree"].map(_nk5) == _nk5(_dg5)]
            if _yr5 and "Current Year" in _cls5.columns:
                _cls5 = _cls5[_cls5["Current Year"].astype(str).map(normalize_course_year).str.strip() == _yr5]
            _cls5 = _cls5.assign(_k=_cls5["Student Name"].astype(str).str.strip().str.lower()).sort_values("_k", kind="stable")
            _idx5 = list(_cls5.index)
            for _a5, _z5 in _rg5:
                for _n5 in range(_a5, min(_z5, len(_idx5)) + 1):
                    _keep5.append(_idx5[_n5 - 1])
                    _serial_map[_idx5[_n5 - 1]] = _n5
            _diag5.append(f"{_c5.strip()} / Branch: {_b5 or '—'} → P2 में {len(_idx5)} Students, "
                          f"Serial: {_s5.strip() or 'खाली'}")
        pp_view = pp_view[pp_view.index.isin(_keep5)]
        if not _keep5:
            st.warning("⚠️ इस Tutor के लिए कोई Student नहीं मिला। P3 में इसकी हर लाइन की स्थिति:  \n"
                       + "  \n".join(f"• {_d}" for _d in _diag5 or ["P3 में इस Tutor का कोई Allotted Class / Serial नहीं भरा है"])
                       + "  \n\nजाँचें: P3 → ✏️ Edit में Degree, Branch, Year और FROM/TO SERIAL NO. भरे हों, और P2 की List में वही Degree/Branch/Year हो।")
        st.caption(f"👩‍🏫 **{_p5_guardian_active}** — P3 में दिए गए Class + SERIAL NO. के Students (नाम के A–Z क्रम में) दिखाए जा रहे हैं।")

    pp_view = pp_view.copy()
    pp_view["_p5_serial"] = [_serial_map.get(_i, 0) for _i in pp_view.index]

    st.caption(f"कुल {len(pp_view)} records मिले।")

    # ---- Header Line 3: "<Title 3>, Major Subject - <Branch>" ----
    # Branch: chune gaye Guardian Tutor ki P3 wali Branch(es); Tutor nahi chuna to is List ke Students ki Branch
    if _p5_pick != _p5_blank_opt:
        _ms_src = [d["b"].strip() for d in st.session_state.get("ph_sel_defs", []) if d["b"].strip().upper() != "ALL"]
    else:
        _ms_src = [str(b).strip() for b in pp_view["Branch"]] if "Branch" in pp_view.columns else []
    _major_subj = ", ".join(dict.fromkeys(b for b in _ms_src if b))
    _title3 = st.session_state.ph_title3.strip()
    if _title3 and _major_subj:
        st.session_state.ph_line3 = f"{_title3}, Major Subject - {_major_subj}"
    elif _major_subj:
        st.session_state.ph_line3 = f"Major Subject - {_major_subj}"
    else:
        st.session_state.ph_line3 = _title3

    st.markdown(
        f"""<div style="border:1px solid var(--pg-border); border-radius:10px; padding:14px 18px;
            background:var(--pg-surface); margin-top:6px;">{_build_header_html("'Poppins','Inter',sans-serif")}</div>""",
        unsafe_allow_html=True,
    )

    # प्रिंट में दिखने वाले कॉलम-लेबल (असली internal column names वही रहते हैं)
    PRINT_LABEL_OVERRIDES = {
        "S.No": "S.No.",
        "Unique ID": "Unique Id",
        "Student Name": "Full Name",
        "Father Name": "Father Name",
        "Mobile Number": "Mob. No.",
        "Branch": "Major Subject",
    }

    if pp_view.empty:
        st.info("📭 कोई record नहीं मिला। अगर Guardian Tutor चुना है, तो P3 में उसका Degree + Branch + Year और FROM–TO SERIAL NO. भरा होना चाहिए।")
        if db.empty:
            st.warning("⚠️ Database बिल्कुल खाली है (कुल 0 records)। पहले P1 से data Upload/Entry करें — "
                       f"या `{DB_FILE}` फ़ाइल app वाले folder में मौजूद नहीं है।")
        else:
            _counts = db["Status"].astype(str).replace("", "(खाली)").value_counts().to_dict()
            st.caption(f"Database में कुल {len(db)} records हैं। Status-wise: {_counts}.")
    else:
        default_print_cols = [c for c in ["Unique ID", "Student Name", "Father Name", "Mobile Number"] if c in ALL_COLUMNS]
        # Branch ALL wali List ho to aakhri column me "Major Subject" (Student ki Branch) apne aap judta hai;
        # kisi khaas Branch wali List me ye tab tak nahi aata jab tak aap Columns me haath se na jodein
        _p5_all_branch = any(d["b"].strip().upper() == "ALL" for d in st.session_state.get("ph_sel_defs", []))
        if "pp_cols" not in st.session_state:
            st.session_state["pp_cols"] = default_print_cols + (["Branch"] if _p5_all_branch and "Branch" in ALL_COLUMNS else [])
        else:
            _cur_cols = list(st.session_state["pp_cols"])
            _prev_auto = st.session_state.get("pp_branch_auto_prev", False)
            if _p5_all_branch and not _prev_auto and "Branch" not in _cur_cols and "Branch" in ALL_COLUMNS:
                st.session_state["pp_cols"] = _cur_cols + ["Branch"]
            elif _prev_auto and not _p5_all_branch and "Branch" in _cur_cols:
                st.session_state["pp_cols"] = [c for c in _cur_cols if c != "Branch"]
        st.session_state["pp_branch_auto_prev"] = _p5_all_branch
        _SNO_SERIAL = "🔢 P3 के Serial No. के अनुसार (जैसे 5, 6, 7 … 10)"
        _SNO_SEQ = "1, 2, 3 … से शुरू (manual)"
        _p5_serial_mode = False
        if _serial_map:
            _p5_serial_mode = st.radio("S.No कैसे दिखे?", [_SNO_SERIAL, _SNO_SEQ], key="pp_sno_mode",
                                       horizontal=True) == _SNO_SERIAL
        pp_cols = st.multiselect(
            "Print के लिए Columns चुनें (S.No अपने आप जुड़ जाएगा)", ALL_COLUMNS,
            format_func=lambda c: PRINT_LABEL_OVERRIDES.get(c, c),
            key="pp_cols",
        )
        if pp_cols:
            # Student Name A→Z (alphabetical) — khaali naam sabse neeche; phir S.No 1,2,3... us order me
            _pp_sorted = pp_view.reset_index(drop=True)
            _name_key = _pp_sorted["Student Name"].astype(str).str.strip().str.lower()
            _order = pd.DataFrame({"empty": _name_key == "", "ser": _pp_sorted["_p5_serial"] if _p5_serial_mode else 0,
                                   "name": _name_key}).sort_values(["empty", "ser", "name"], kind="stable").index
            _serial_ordered = _pp_sorted.loc[_order, "_p5_serial"].reset_index(drop=True)
            _raw_print_df = _pp_sorted.loc[_order, pp_cols].reset_index(drop=True)
            _cy_ordered = (
                _pp_sorted.loc[_order, "Current Year"].astype(str).map(normalize_course_year).reset_index(drop=True)
                if "Current Year" in _pp_sorted.columns else pd.Series([""] * len(_raw_print_df))
            )

            pp_print_df = _raw_print_df.copy()
            pp_print_df.insert(0, "S.No", list(_serial_ordered) if _p5_serial_mode else range(1, len(pp_print_df) + 1))
            preview_df = pp_print_df.rename(columns=PRINT_LABEL_OVERRIDES)

            # Sirf Print/Preview/Download ke liye — har text column ka 1st letter capital, baaki small
            # (Database "db" mein asli data bilkul waisa hi rehta hai, isse yahan chhua nahi jaata)
            def _p5_name_case(val):
                s = str(val).strip()
                if not s or s.replace(".", "", 1).isdigit():   # khaali ya pure numbers/decimal ko chhedo nahi
                    return val
                return " ".join(w[0].upper() + w[1:].lower() if w else w for w in s.split(" "))

            for _pcol in preview_df.columns:
                if _pcol == "S.No":
                    continue
                preview_df[_pcol] = preview_df[_pcol].map(_p5_name_case)

            st.markdown("---")
            st.subheader("👁️ Preview")
            st.dataframe(preview_df, use_container_width=True, hide_index=True)

            # ---- Agar chuni gayi Guardian Tutor ke Students me ek se zyada Class (Current Year)
            # mili, to Print me har Class ke liye yeh Header dobara shuru hoga (S.No bhi 1 se) ----
            _p5_classes_present = []
            if _p5_guardian_active:
                for _v in _cy_ordered:
                    _vv = str(_v).strip()
                    if _vv and _vv not in _p5_classes_present:
                        _p5_classes_present.append(_vv)
                _p5_classes_present.sort(key=lambda v: COURSE_YEAR_OPTIONS.index(v) if v in COURSE_YEAR_OPTIONS else 99)

            st.markdown("---")
            st.subheader("🖨️ Print / Export")
            pr_col1, pr_col2 = st.columns(2)
            with pr_col1:
                st.download_button(
                    "⬇️ CSV Download करें",
                    preview_df.to_csv(index=False).encode("utf-8-sig"),
                    file_name="print_panel_list.csv", mime="text/csv", use_container_width=True,
                )
            with pr_col2:
                if len(_p5_classes_present) > 1:
                    st.caption(f"ℹ️ इस Tutor की {len(_p5_classes_present)} अलग-अलग Class मिलीं — Print में हर Class के लिए "
                               "यह Header (ऊपर वाला) दोबारा शुरू होगा, अपने S.No के साथ।")
                    _sections = []
                    for _cls_val in _p5_classes_present:
                        _cls_mask = (_cy_ordered == _cls_val).values
                        _cls_raw = _raw_print_df[_cls_mask].reset_index(drop=True)
                        if _cls_raw.empty:
                            continue
                        _cls_print_df = _cls_raw.copy()
                        _cls_print_df.insert(0, "S.No", list(_serial_ordered[_cls_mask]) if _p5_serial_mode
                                            else range(1, len(_cls_print_df) + 1))
                        _cls_preview = _cls_print_df.rename(columns=PRINT_LABEL_OVERRIDES)
                        for _pcol in _cls_preview.columns:
                            if _pcol == "S.No":
                                continue
                            _cls_preview[_pcol] = _cls_preview[_pcol].map(_p5_name_case)
                        _cls_label = COURSE_YEAR_PRINT_LABELS.get(_cls_val, _cls_val.upper())
                        _cls_line2 = (f"{_course_txt} {_cls_label} ({_sess_txt})" if _course_txt and _sess_txt
                                      else (f"{_cls_label} ({_sess_txt})" if _sess_txt
                                            else f"{_course_txt} {_cls_label}".strip()))
                        _cls_hdr = (f'<div style="margin-bottom:10px; margin-top:18px;">'
                                    f'{_build_header_html("Arial, sans-serif", line2_override=_cls_line2)}'
                                    f'<hr style="border:none; border-top:2px solid {st.session_state.ph_color1}; margin-top:10px;"></div>')
                        _sections.append(_cls_hdr + _cls_preview.to_html(index=False, escape=True))
                    print_button("".join(_sections), label="🖨️ Print करें (हर Class अलग से)")
                else:
                    _table_html = preview_df.to_html(index=False, escape=True)
                    _hdr = (f'<div style="margin-bottom:10px;">{_build_header_html("Arial, sans-serif")}'
                            f'<hr style="border:none; border-top:2px solid {st.session_state.ph_color1}; margin-top:10px;"></div>')
                    print_button(_hdr + _table_html, label="🖨️ Print करें")
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

        st.markdown("---")
        st.markdown("**🎓 Degree / Major / Minor / MDC / Vocational / PW-AP-CE — कितनी-कितनी हैं**")
        if db.empty:
            st.caption("📭 Database खाली है।")
        else:
            _p6_summary_cols = {
                "Degree": "Degree",
                "Major Subject": "Branch",
                "Minor Subjects": "Minor Subjects",
                "Vocational Subjects": "Vocational Subjects",
                "MDC Subjects": "MDC Subjects",
                "PW/Ap/CE Subjects": "PW/Ap/CE Subjects",
                "Current Year": "Current Year",
            }
            _p6_sum_layout = st.columns(3)
            for _p6_i, (_p6_label, _p6_col) in enumerate(_p6_summary_cols.items()):
                with _p6_sum_layout[_p6_i % 3]:
                    st.caption(f"**{_p6_label}**")
                    if _p6_col not in db.columns:
                        st.caption("— कॉलम मौजूद नहीं।")
                        continue
                    # comma se split — agar kisi record me ek se zyada Minor/Voc/MDC/PW subject saath likhe hon
                    _p6_split = db[_p6_col].astype(str).str.split(",")
                    _p6_flat = [v.strip() for sub in _p6_split for v in sub if v.strip()]
                    if _p6_col == "Current Year":
                        # First Year / Second Year / II Year / 2 ... jaisa bhi purana likha ho, sab ek jaisi form me count ho
                        _p6_flat = [normalize_course_year(v) for v in _p6_flat]
                    if _p6_flat:
                        _p6_vc = pd.Series(_p6_flat).value_counts().rename_axis(_p6_label).reset_index(name="कितने Students")
                        st.dataframe(_p6_vc, use_container_width=True, hide_index=True)
                    else:
                        st.caption("कोई data भरा नहीं मिला।")

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
        _dflash = st.session_state.pop("p6_dept_flash", None)
        if _dflash:
            st.success(_dflash)
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

        st.markdown("---")
        st.markdown("**✏️ Department का नाम बदलें** (Records, Users और Tutors List में भी नया नाम अपने आप लग जाएगा)")
        if depts:
            rn_c1, rn_c2 = st.columns(2)
            with rn_c1:
                rn_old = st.selectbox("कौन सा Department बदलना है", depts, key="rn_dept_old")
            with rn_c2:
                rn_new = st.text_input("नया नाम", key="rn_dept_new")
            if st.button("✏️ नाम बदलें", key="rn_dept_btn"):
                _n = rn_new.strip()
                if not _n:
                    st.warning("⚠️ नया नाम खाली नहीं हो सकता।")
                elif _n in depts:
                    st.warning("⚠️ यह नाम पहले से मौजूद है।")
                else:
                    rename_department(rn_old, _n)
                    st.session_state["p6_dept_flash"] = f"✅ '{rn_old}' का नाम बदलकर '{_n}' हो गया।"
                    st.rerun()

        st.markdown("---")
        st.markdown("**📝 पूरी Departments List एक साथ बदलें** (हर लाइन में एक Department)")
        bulk_txt = st.text_area("Departments", value="\n".join(depts), height=180,
                                key=f"p6_dept_bulk_{abs(hash(tuple(depts)))}",
                                help="जैसे: Commerce, Science, Arts — हर नाम अलग लाइन में लिखें।")
        if st.button("💾 यह List Save करें", type="primary", key="p6_dept_bulk_btn"):
            _new_list = list(dict.fromkeys([x.strip() for x in bulk_txt.split("\n") if x.strip()]))
            if not _new_list:
                st.warning("⚠️ कम से कम एक Department होना ज़रूरी है।")
            else:
                save_departments(_new_list)
                st.session_state.departments = _new_list
                _orphans = int((~db["Assigned Department"].isin(_new_list + [""])).sum()) if not db.empty else 0
                st.session_state["p6_dept_flash"] = (
                    f"✅ Departments List बदल गई — अब {len(_new_list)} Departments हैं।"
                    + (f" ⚠️ {_orphans} पुराने records के Department का नाम नई List में नहीं है (नाम बदलने के लिए ऊपर '✏️ नाम बदलें' इस्तेमाल करें)।" if _orphans else "")
                )
                st.rerun()

    with tab_data:
        st.subheader("पूरा Database")
        if db.empty:
            st.info("📭 Database खाली है।")
        else:
            _p6d_flash = st.session_state.pop("p6_data_flash", None)
            if _p6d_flash:
                st.success(_p6d_flash)
            st.caption("नीचे टेबल में किसी भी row के शुरू में checkbox से एक या कई rows select करें, "
                       "फिर नीचे '🗑️ Selected Rows Delete करें' बटन से उन्हें हमेशा के लिए हटाएँ।")
            _p6d_search = st.text_input("🔎 Database में खोजें (select करने से पहले छाँटने के लिए)", key="p6_data_search")
            _p6d_view = db.copy()
            if _p6d_search.strip():
                _s = _p6d_search.strip().lower()
                _p6d_view = _p6d_view[_p6d_view.apply(lambda r: _s in " ".join(str(v).lower() for v in r.values), axis=1)]
            st.caption(f"{len(_p6d_view)} rows दिख रही हैं।")
            _p6d_key = f"p6_data_select_{st.session_state.get('p6_data_select_n', 0)}"
            _p6d_event = st.dataframe(
                _p6d_view,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="multi-row",
                key=_p6d_key,
            )
            _p6d_sel_positions = list(_p6d_event.selection.rows) if _p6d_event and getattr(_p6d_event, "selection", None) else []
            if _p6d_sel_positions:
                _p6d_sel_orig_idx = _p6d_view.iloc[_p6d_sel_positions].index.tolist()
                st.warning(f"⚠️ {len(_p6d_sel_positions)} row(s) select की गई हैं — Delete करने से पहले ध्यान से देख लें, यह Database से हमेशा के लिए हट जाएँगी।")
                with st.expander("👁️ Select की गई rows देखें"):
                    st.dataframe(_p6d_view.loc[_p6d_sel_orig_idx], use_container_width=True, hide_index=True)
                if st.button(f"🗑️ Selected {len(_p6d_sel_positions)} Row(s) Delete करें", type="secondary", key="p6_data_delete_btn"):
                    db = db.drop(index=_p6d_sel_orig_idx).reset_index(drop=True)
                    save_db(db)
                    st.session_state["p6_data_flash"] = f"🗑️ {len(_p6d_sel_orig_idx)} row(s) Database से हटा दी गई हैं। अब कुल {len(db)} records हैं।"
                    st.session_state["p6_data_select_n"] = st.session_state.get("p6_data_select_n", 0) + 1
                    st.rerun()
            else:
                st.caption("अभी कोई row select नहीं की गई है।")
        st.download_button("⬇️ पूरा Database Backup (CSV) Download करें",
                            db.to_csv(index=False).encode("utf-8-sig"),
                            file_name="full_database_backup.csv", mime="text/csv")
