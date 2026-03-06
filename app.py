import os
import json
import re
import gspread
from gspread.utils import rowcol_to_a1
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import google.generativeai as genai
from google.oauth2.service_account import Credentials
import requests
from datetime import datetime

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WA_NUMBER   = os.environ.get("TWILIO_WA_NUMBER")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY")
GOOGLE_CREDS_JSON  = os.environ.get("GOOGLE_CREDS_JSON")
SPREADSHEET_ID     = "1MzW9qwHZZjwj5sZkm4bMlvjFE8mBBJ4HokhMehS5sag"

genai.configure(api_key=GEMINI_API_KEY)

# ── REAL STUDENT DATA — PDS24 S3 ──
STUDENTS = [
    {"roll": "PDS23001", "name": "ABDUL REHMAN",                "gender": "M"},
    {"roll": "PDS23002", "name": "ABDUL HADI",                  "gender": "M"},
    {"roll": "PDS23003", "name": "SAKIA KANWAL",                "gender": "F"},
    {"roll": "PDS23004", "name": "MADIHA BEGUM",                "gender": "F"},
    {"roll": "PDS23005", "name": "ISMA KHAN",                   "gender": "F"},
    {"roll": "PDS23006", "name": "AIMEN WAJID",                 "gender": "F"},
    {"roll": "PDS23007", "name": "AROOJ IMRAN",                 "gender": "F"},
    {"roll": "PDS23008", "name": "AREEBA SABIR",                "gender": "F"},
    {"roll": "PDS23009", "name": "SHEHRYAR NAZIR",              "gender": "M"},
    {"roll": "PDS23010", "name": "SAKHAWAT ALI",                "gender": "M"},
    {"roll": "PDS23011", "name": "ZARRAR HAIDER",               "gender": "M"},
    {"roll": "PDS23012", "name": "YASMEEN QAISER",              "gender": "F"},
    {"roll": "PDS23013", "name": "IQRA KIRAN",                  "gender": "F"},
    {"roll": "PDS23014", "name": "LAIBA AYAZ",                  "gender": "F"},
    {"roll": "PDS23015", "name": "SHANAB AHMED",                "gender": "M"},
    {"roll": "PDS23016", "name": "UBAID-ULLAH",                 "gender": "M"},
    {"roll": "PDS23017", "name": "MUHAMMAD UMAR",               "gender": "M"},
    {"roll": "PDS23018", "name": "IQRA IBRAHIM",                "gender": "F"},
    {"roll": "PDS24019", "name": "AZKA WAHID",                  "gender": "F"},
    {"roll": "PDS24020", "name": "MUHAMMAD HUZAIFA MALIK",      "gender": "M"},
    {"roll": "PDS24021", "name": "FARRUKH HUSSAIN SHAH",        "gender": "M"},
    {"roll": "PDS24022", "name": "SAMEER AHMAD KHAN",           "gender": "M"},
    {"roll": "PDS24023", "name": "NIMRA YASIN",                 "gender": "F"},
    {"roll": "PDS24024", "name": "AREESHA KAINAT",              "gender": "F"},
    {"roll": "PDS24025", "name": "KAINAT",                      "gender": "F"},
    {"roll": "PDS24026", "name": "GUL-E-SEHAR",                 "gender": "F"},
    {"roll": "PDS24027", "name": "SANA FAREED",                 "gender": "F"},
    {"roll": "PDS24028", "name": "ANSA SAMEER",                 "gender": "F"},
    {"roll": "PDS24029", "name": "EHTISHAM ALI",                "gender": "M"},
    {"roll": "PDS24030", "name": "IQRA MUBEEN",                 "gender": "F"},
    {"roll": "PDS24031", "name": "NAZIA PARVEEN",               "gender": "F"},
    {"roll": "PDS24032", "name": "ALISHBA SHAKIR",              "gender": "F"},
    {"roll": "PDS24033", "name": "MUHAMMAD TARIQ",              "gender": "M"},
    {"roll": "PDS24034", "name": "SAWAIRA BEGUM",               "gender": "F"},
    {"roll": "PDS24035", "name": "SEHRISH NADEEM",              "gender": "F"},
    {"roll": "PDS24036", "name": "AYESHA NAVEED",               "gender": "F"},
    {"roll": "PDS24037", "name": "SHAHID KHAN",                 "gender": "M"},
    {"roll": "PDS24038", "name": "SAFINA NISAR",                "gender": "F"},
    {"roll": "PDS24039", "name": "MUHAMMAD UMER MOBEEN",        "gender": "M"},
    {"roll": "PDS24040", "name": "FATIMA JAVERIA HASHMI",       "gender": "F"},
    {"roll": "PDS24041", "name": "NIMRA HAIDER",                "gender": "F"},
    {"roll": "PDS24042", "name": "KHADIJA BIBI",                "gender": "F"},
    {"roll": "PDS24043", "name": "MUHAMMAD HASSAM HAMEED KHAN", "gender": "M"},
    {"roll": "PDS24044", "name": "TEHREEM ASIM",                "gender": "F"},
]

SUBJECTS = {
    "pharmacology lab":  "Pharmacology Lab",
    "pharmacology":      "Pharmacology-I",
    "pharmacognosy lab": "Pharmacognosy-I LAB",
    "pharmacognosy":     "Pharmacognosy-I",
    "pharmaceutics lab": "Pharmaceutics Lab",
    "pharmaceutics":     "Pharmaceutics-I",
    "microbiology lab":  "Microbiology Lab",
    "microbiology":      "Microbiology",
    "islamic":           "Islamic Studies",
    "maths":             "Maths",
}

SUBJECT_TEACHERS = {
    "Pharmacology-I":      "Miss Khadija Ijaz",
    "Pharmacognosy-I":     "Miss Sabina Nazish",
    "Pharmacology Lab":    "Miss Khadija Ijaz",
    "Pharmaceutics Lab":   "Miss Ushna Ejaz",
    "Pharmaceutics-I":     "Miss Ushna Ejaz",
    "Microbiology Lab":    "Miss Khadija Ijaz",
    "Microbiology":        "Miss Khadija Ijaz",
    "Islamic Studies":     "Mr. Muhammad Farooq",
    "Maths":               "Mr. Anwar ul Mehmood",
    "Pharmacognosy-I LAB": "Miss Sabina Nazish",
}

def normalize_subject(text):
    t = text.lower().strip()
    for key, full_name in SUBJECTS.items():
        if key in t:
            return full_name
    return text.strip().title()

# ── GOOGLE SHEETS ──
def get_sheet_client():
    try:
        creds_data = json.loads(GOOGLE_CREDS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        print(f"Sheets auth error: {e}")
        return None

def apply_sheet_formatting(spreadsheet, sheet, num_date_cols):
    """Apply blue header, alternating rows, bold summary cols via Sheets API."""
    try:
        sheet_id = sheet.id
        n_students = len(STUDENTS)
        # Total columns: Roll(1) + Name(1) + Gender(1) + dates + Total Present + Total Classes + %
        total_cols = 3 + num_date_cols + 3

        requests_body = []

        # Row 1 (index 0): Title — dark blue background, white bold text
        requests_body.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1,
                      "startColumnIndex": 0, "endColumnIndex": total_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.145, "green": 0.376, "blue": 0.933},
                "textFormat": {"bold": True, "fontSize": 11,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }})

        # Row 2 (index 1): Headers — dark navy
        requests_body.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2,
                      "startColumnIndex": 0, "endColumnIndex": total_cols},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 0.059, "green": 0.090, "blue": 0.165},
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                "horizontalAlignment": "CENTER"
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
        }})

        # Student rows: alternating white / very light blue
        for i in range(n_students):
            row_idx = i + 2  # 0-indexed, rows 2..45
            bg = {"red": 1, "green": 1, "blue": 1} if i % 2 == 0 \
                 else {"red": 0.949, "green": 0.965, "blue": 0.996}
            requests_body.append({"repeatCell": {
                "range": {"sheetId": sheet_id,
                          "startRowIndex": row_idx, "endRowIndex": row_idx + 1,
                          "startColumnIndex": 0, "endColumnIndex": total_cols},
                "cell": {"userEnteredFormat": {
                    "backgroundColor": bg,
                    "textFormat": {"fontSize": 10},
                    "horizontalAlignment": "CENTER"
                }},
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
            }})

        # Summary columns (last 3): light yellow background
        summary_start = 3 + num_date_cols
        requests_body.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 2 + n_students,
                      "startColumnIndex": summary_start, "endColumnIndex": summary_start + 3},
            "cell": {"userEnteredFormat": {
                "backgroundColor": {"red": 1, "green": 0.984, "blue": 0.824},
                "textFormat": {"bold": True, "fontSize": 10}
            }},
            "fields": "userEnteredFormat(backgroundColor,textFormat)"
        }})

        # Conditional formatting: % column < 75 → red background
        pct_col = summary_start + 2  # 0-indexed
        requests_body.append({"addConditionalFormatRule": {
            "rule": {
                "ranges": [{"sheetId": sheet_id,
                            "startRowIndex": 2, "endRowIndex": 2 + n_students,
                            "startColumnIndex": pct_col, "endColumnIndex": pct_col + 1}],
                "booleanRule": {
                    "condition": {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "75"}]},
                    "format": {
                        "backgroundColor": {"red": 1, "green": 0.8, "blue": 0.8},
                        "textFormat": {"bold": True,
                                       "foregroundColor": {"red": 0.72, "green": 0.11, "blue": 0.11}}
                    }
                }
            },
            "index": 0
        }})

        # Freeze rows 1-2 and cols A-C
        requests_body.append({"updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 2, "frozenColumnCount": 3}
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
        }})

        # Column widths
        col_widths = [(0, 90), (1, 220), (2, 65)]  # Roll, Name, Gender
        for ci, w in col_widths:
            requests_body.append({"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                          "startIndex": ci, "endIndex": ci + 1},
                "properties": {"pixelSize": w},
                "fields": "pixelSize"
            }})

        spreadsheet.batch_update({"requests": requests_body})
        print(f"    Formatting applied ✓")
    except Exception as e:
        print(f"    Formatting error (non-critical): {e}")

def init_sheet(spreadsheet, subject):
    """Create and initialize a subject sheet from scratch."""
    teacher = SUBJECT_TEACHERS.get(subject, "")
    try:
        sheet = spreadsheet.worksheet(subject)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=subject, rows=50, cols=60)

    sheet.clear()

    # Row 1: Title
    sheet.update("A1", [[f"{subject}  |  {teacher}  |  PDS24 — Semester 3  |  Fall 2024"]])

    # Row 2: Headers (date cols added dynamically)
    sheet.update("A2", [["Roll No", "Student Name", "Gender"]])

    # Rows 3–46: Students
    rows = [[s["roll"], s["name"], s["gender"]] for s in STUDENTS]
    sheet.update("A3", rows)

    return sheet

def save_attendance_to_sheet(subject, date_str, present_names):
    try:
        client = get_sheet_client()
        if not client:
            return False

        spreadsheet = client.open_by_key(SPREADSHEET_ID)

        # Get or create sheet
        try:
            sheet = spreadsheet.worksheet(subject)
            all_data = sheet.get_all_values()
            # Re-init if empty/broken
            if len(all_data) < 2:
                sheet = init_sheet(spreadsheet, subject)
                all_data = sheet.get_all_values()
        except gspread.WorksheetNotFound:
            sheet = init_sheet(spreadsheet, subject)
            all_data = sheet.get_all_values()

        # Row 2 (index 1) = headers
        headers = all_data[1] if len(all_data) > 1 else []

        # Find or add date column (after Roll, Name, Gender = col 4+)
        if date_str in headers:
            date_col = headers.index(date_str) + 1  # 1-indexed
        else:
            date_col = len(headers) + 1
            sheet.update_cell(2, date_col, date_str)
            headers = sheet.row_values(2)

        # Number of date columns (everything after col 3)
        num_date_cols = max(1, len([h for h in headers[3:] if h and h not in
                                    ["Total Present", "Total Classes", "%"]]))

        # Summary columns always at the end (after all date cols)
        summary_start_col = 3 + num_date_cols + 1  # 1-indexed

        # Write headers for summary cols
        sheet.update_cell(2, summary_start_col,     "Total Present")
        sheet.update_cell(2, summary_start_col + 1, "Total Classes")
        sheet.update_cell(2, summary_start_col + 2, "%")

        # Build present set
        present_lower = {n.strip().lower() for n in present_names}

        updates = []
        for i, student in enumerate(STUDENTS):
            row = i + 3  # rows start at 3

            # Mark P or A for this date
            status = "P" if student["name"].lower() in present_lower else "A"
            updates.append({
                "range": rowcol_to_a1(row, date_col),
                "values": [[status]]
            })

            # Calculate totals from all date columns (cols 4 to summary_start_col-1)
            if num_date_cols > 0:
                first_date_col_letter = rowcol_to_a1(row, 4).rstrip("0123456789")
                last_date_col_letter  = rowcol_to_a1(row, 3 + num_date_cols).rstrip("0123456789")

                total_present_formula = (
                    f'=COUNTIF({first_date_col_letter}{row}:'
                    f'{last_date_col_letter}{row},"P")'
                )
                total_classes_formula = (
                    f'=COUNTA({first_date_col_letter}{row}:'
                    f'{last_date_col_letter}{row})'
                )
                pct_formula = (
                    f'=IFERROR(ROUND({rowcol_to_a1(row, summary_start_col)}'
                    f'/{rowcol_to_a1(row, summary_start_col+1)}*100,0),0)'
                )

                updates.append({"range": rowcol_to_a1(row, summary_start_col),     "values": [[total_present_formula]]})
                updates.append({"range": rowcol_to_a1(row, summary_start_col + 1), "values": [[total_classes_formula]]})
                updates.append({"range": rowcol_to_a1(row, summary_start_col + 2), "values": [[pct_formula]]})

        sheet.batch_update(updates, value_input_option="USER_ENTERED")

        # Apply formatting
        apply_sheet_formatting(spreadsheet, sheet, num_date_cols)

        print(f"✅ Saved {subject} — {date_str}")
        return True

    except Exception as e:
        print(f"❌ Sheet error: {e}")
        return False

# ── GEMINI IMAGE ANALYSIS ──
def analyze_attendance_image(image_url, subject, date_str):
    try:
        img_data = requests.get(
            image_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        ).content

        model = genai.GenerativeModel("gemini-1.5-flash")
        student_list = "\n".join([f"{s['roll']} - {s['name']}" for s in STUDENTS])

        prompt = f"""You are reading a handwritten attendance register for a Pharm-D class.

Subject: {subject}
Date: {date_str}

Student list:
{student_list}

Identify PRESENT (P / tick / checkmark) and ABSENT (A / cross / blank) students.

Return ONLY valid JSON:
{{
  "present": ["ABDUL REHMAN", "SAKIA KANWAL"],
  "absent": ["MADIHA BEGUM"],
  "notes": "any issues reading the register"
}}

Use EXACT names from the student list. Do not invent names."""

        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": img_data}
        ])

        match = re.search(r'\{.*\}', response.text.strip(), re.DOTALL)
        return json.loads(match.group()) if match else None

    except Exception as e:
        print(f"Gemini error: {e}")
        return None

# ── WEBHOOK ──
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    media_url    = request.values.get("MediaUrl0", "")
    media_type   = request.values.get("MediaContentType0", "")
    sender       = request.values.get("From", "")

    resp = MessagingResponse()
    msg  = resp.message()

    if media_url and "image" in media_type:
        date_str    = datetime.now().strftime("%d/%m/%Y")
        subject_raw = "General"

        if incoming_msg:
            m = re.search(r'(\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?)', incoming_msg)
            if m:
                date_str    = m.group(1)
                subject_raw = incoming_msg[:m.start()].strip()
            else:
                subject_raw = incoming_msg.strip()

        subject = normalize_subject(subject_raw) if subject_raw else "General"
        msg.body(f"📸 Reading *{subject}* register for {date_str}... ⏳")

        result = analyze_attendance_image(media_url, subject, date_str)

        if result:
            present_list = result.get("present", [])
            absent_list  = result.get("absent", [])
            notes        = result.get("notes", "")

            saved       = save_attendance_to_sheet(subject, date_str, present_list)
            absent_text = "\n".join([f"• {s}" for s in absent_list]) if absent_list else "None ✅"

            reply = (
                f"✅ *Attendance Recorded!*\n\n"
                f"📚 *{subject}*\n"
                f"📅 {date_str}\n"
                f"👥 Present: {len(present_list)}  |  Absent: {len(absent_list)}\n\n"
                f"❌ *Absent Students:*\n{absent_text}\n\n"
            )
            reply += "📊 *Saved to Google Sheet ✓*" if saved else "⚠️ Sheet save failed"
            if notes:
                reply += f"\n\n📝 {notes}"

            try:
                Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN).messages.create(
                    body=reply, from_=TWILIO_WA_NUMBER, to=sender
                )
                return "", 204
            except Exception:
                msg.body(reply)
        else:
            msg.body("❌ Could not read the register. Please send a clearer photo.")

    elif incoming_msg.lower() in ["hi", "hello", "help"]:
        msg.body(
            "👋 *AIHS Attendance Bot — PDS24 S3*\n\n"
            "Send a photo of the register with subject + date as caption.\n\n"
            "*Example:* Pharmacology 06/03\n\n"
            "*Available subjects:*\n"
            "• Pharmacology-I\n• Pharmacognosy-I\n• Pharmaceutics-I\n"
            "• Microbiology\n• Islamic Studies\n• Maths\n"
            "• Pharmacology Lab\n• Pharmaceutics Lab\n"
            "• Microbiology Lab\n• Pharmacognosy-I LAB"
        )
    else:
        msg.body(
            "📸 Send a photo of the register with subject + date as caption.\n\n"
            "Example: *Pharmacology 06/03*"
        )

    return str(resp)

@app.route("/")
def home():
    return "AIHS Attendance Bot ✅ Running — PDS24 S3"

@app.route("/health")
def health():
    return {"status": "ok", "students": len(STUDENTS), "subjects": len(SUBJECTS)}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
