import os
import json
import re
import gspread
from flask import Flask, request
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import google.generativeai as genai
from google.oauth2.service_account import Credentials
import requests
from datetime import datetime

app = Flask(__name__)

# --- Config ---
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WA_NUMBER = os.environ.get("TWILIO_WA_NUMBER")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDS_JSON")
SPREADSHEET_ID = "1MzW9qwHZZjwj5sZkm4bMlvjFE8mBBJ4HokhMehS5sag"

genai.configure(api_key=GEMINI_API_KEY)

# --- Student list (44 students) ---
STUDENTS = [
    "Sameer Ahmad Khan", "Ali Raza", "Fatima Malik", "Usman Tariq", "Ayesha Siddiqui",
    "Hassan Raza", "Zainab Hussain", "Omar Farooq", "Maryam Nawaz", "Bilal Ahmed",
    "Sara Khan", "Hamza Sheikh", "Nadia Iqbal", "Fahad Mirza", "Sana Butt",
    "Asad Malik", "Hina Qureshi", "Talha Ahmad", "Rabia Noor", "Imran Ali",
    "Amna Riaz", "Kamran Hassan", "Saira Bano", "Junaid Akhtar", "Mehwish Tariq",
    "Arslan Baig", "Bushra Zafar", "Shahzad Ahmed", "Iqra Khalid", "Naveed Alam",
    "Madiha Shah", "Faisal Chaudhry", "Noor Fatima", "Waheed Anwar", "Sadia Perveen",
    "Adnan Hussain", "Rubab Haider", "Zubair Malik", "Uzma Jabeen", "Rizwan Saeed",
    "Fareeha Naz", "Salman Ghani", "Tooba Ashraf", "Muneeb ur Rehman"
]

# --- Google Sheets setup ---
def get_sheet_client():
    try:
        creds_data = json.loads(GOOGLE_CREDS_JSON)
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_data, scopes=scopes)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"Sheets auth error: {e}")
        return None

def save_attendance_to_sheet(subject, date_str, present_list, absent_list):
    try:
        client = get_sheet_client()
        if not client:
            return False

        spreadsheet = client.open_by_key(SPREADSHEET_ID)

        # Try to get existing sheet or create new one
        try:
            sheet = spreadsheet.worksheet(subject)
        except gspread.WorksheetNotFound:
            sheet = spreadsheet.add_worksheet(title=subject, rows=60, cols=50)
            # Set up headers
            sheet.update('A1', [['Roll No', 'Student Name']])

        # Get existing data
        all_data = sheet.get_all_values()

        # Find or create date column
        if len(all_data) == 0 or len(all_data[0]) < 2:
            # Initialize sheet
            headers = ['Roll No', 'Student Name', date_str]
            sheet.update('A1', [headers])
            # Add all students
            for i, student in enumerate(STUDENTS, start=2):
                sheet.update(f'A{i}', [[i-1, student]])
            date_col = 3
        else:
            headers = all_data[0]
            if date_str in headers:
                date_col = headers.index(date_str) + 1
            else:
                date_col = len(headers) + 1
                sheet.update_cell(1, date_col, date_str)

            # Make sure all students are listed
            if len(all_data) < 2:
                for i, student in enumerate(STUDENTS, start=2):
                    sheet.update(f'A{i}', [[i-1, student]])

        # Get current student rows
        all_data = sheet.get_all_values()
        student_rows = {}
        for i, row in enumerate(all_data[1:], start=2):
            if len(row) >= 2:
                student_rows[row[1].strip().lower()] = i

        # Mark attendance
        present_lower = [s.strip().lower() for s in present_list]

        for student in STUDENTS:
            row_num = student_rows.get(student.lower())
            if not row_num:
                # Add student if not found
                row_num = len(all_data) + 1
                sheet.update(f'A{row_num}', [[row_num - 1, student]])
                student_rows[student.lower()] = row_num

            status = 'P' if student.lower() in present_lower else 'A'
            sheet.update_cell(row_num, date_col, status)

        print(f"✅ Saved attendance for {subject} on {date_str}")
        return True

    except Exception as e:
        print(f"❌ Sheet save error: {e}")
        return False

# --- Process image with Gemini ---
def analyze_attendance_image(image_url, subject, date_str):
    try:
        # Download image
        auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        img_response = requests.get(image_url, auth=auth)
        image_data = img_response.content

        model = genai.GenerativeModel('gemini-1.5-flash')

        student_list_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(STUDENTS)])

        prompt = f"""You are analyzing a handwritten attendance register photo.

Subject: {subject}
Date: {date_str}

Here is the complete student list:
{student_list_text}

Look at the attendance register image carefully. Identify which students are marked PRESENT (P, ✓, tick, present) and which are ABSENT (A, absent, or unmarked).

Return ONLY a JSON object in this exact format:
{{
  "present": ["Full Name 1", "Full Name 2"],
  "absent": ["Full Name 3", "Full Name 4"],
  "notes": "any important notes or issues reading the register"
}}

Match names from the image to the student list above as closely as possible. Use the exact names from the student list."""

        image_part = {
            "mime_type": "image/jpeg",
            "data": image_data
        }

        response = model.generate_content([prompt, image_part])
        response_text = response.text.strip()

        # Extract JSON
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return result
        else:
            return None

    except Exception as e:
        print(f"Gemini error: {e}")
        return None

# --- WhatsApp webhook ---
@app.route('/webhook', methods=['POST'])
def webhook():
    incoming_msg = request.values.get('Body', '').strip()
    media_url = request.values.get('MediaUrl0', '')
    media_type = request.values.get('MediaContentType0', '')
    sender = request.values.get('From', '')

    resp = MessagingResponse()
    msg = resp.message()

    # If image received
    if media_url and 'image' in media_type:
        # Parse subject and date from message body
        # Expected format: "Subject Name DD/MM" or "Subject Name DD/MM/YYYY"
        subject = "General"
        date_str = datetime.now().strftime("%d/%m/%Y")

        if incoming_msg:
            # Try to extract date from message
            date_pattern = r'(\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?)'
            date_match = re.search(date_pattern, incoming_msg)

            if date_match:
                date_str = date_match.group(1)
                subject = incoming_msg[:date_match.start()].strip()
            else:
                subject = incoming_msg.strip()

        if not subject:
            subject = "General"

        msg.body(f"📸 Processing attendance for *{subject}* on {date_str}...\nReading register with AI...")

        # Analyze with Gemini
        result = analyze_attendance_image(media_url, subject, date_str)

        if result:
            present_list = result.get('present', [])
            absent_list = result.get('absent', [])
            notes = result.get('notes', '')

            # Save to Google Sheets
            saved = save_attendance_to_sheet(subject, date_str, present_list, absent_list)

            # Build reply
            absent_text = "\n".join([f"• {s}" for s in absent_list]) if absent_list else "None"
            present_count = len(present_list)
            absent_count = len(absent_list)
            total = present_count + absent_count

            reply = f"""✅ *Attendance Recorded!*

📚 Subject: {subject}
📅 Date: {date_str}
👥 Total: {total} students

✅ Present: {present_count}
❌ Absent: {absent_count}

*Absent Students:*
{absent_text}"""

            if saved:
                reply += "\n\n📊 *Saved to Google Sheet ✓*"
            else:
                reply += "\n\n⚠️ Sheet save failed - check bot logs"

            if notes:
                reply += f"\n\n📝 Notes: {notes}"

            # Send proper reply via Twilio (not TwiML for long messages)
            try:
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                client.messages.create(
                    body=reply,
                    from_=TWILIO_WA_NUMBER,
                    to=sender
                )
                return '', 204
            except:
                msg.body(reply)
        else:
            msg.body("❌ Could not read the register. Please make sure the image is clear and try again.")

    elif incoming_msg.lower() in ['hi', 'hello', 'help']:
        msg.body("""👋 *AIHS Attendance Bot*

To record attendance:
1. Take a photo of the register
2. Send it with the subject name and date as caption

*Example caption:*
Pharmacology 06/03

The bot will:
✅ Read the register using AI
✅ List absent students
✅ Save to Google Sheets automatically

Need help? Contact your admin.""")

    else:
        msg.body("📸 Please send a photo of the attendance register with the subject name and date as the caption.\n\nExample: *Pharmacology 06/03*")

    return str(resp)

@app.route('/')
def home():
    return "AIHS Attendance Bot is running! ✅"

@app.route('/health')
def health():
    return {"status": "ok", "students": len(STUDENTS)}, 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
