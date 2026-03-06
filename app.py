from flask import Flask, request
import anthropic
import gspread
from google.oauth2.service_account import Credentials
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import os, json, re
from datetime import datetime
from difflib import get_close_matches

app = Flask(__name__)

# ── CONFIG (fill these in) ──────────────────────────────────────
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WA_NUMBER   = os.environ.get("TWILIO_WA_NUMBER")   # e.g. whatsapp:+14155238886
ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY")
GOOGLE_CREDS_JSON  = os.environ.get("GOOGLE_CREDS_JSON")   # full JSON string
SPREADSHEET_NAME   = "AIHS Attendance PDS24 S3"
# ───────────────────────────────────────────────────────────────

# ── STUDENT LIST ───────────────────────────────────────────────
STUDENTS = [
    {"roll":"PDS23001","name":"ABDUL REHMAN","gender":"M"},
    {"roll":"PDS23002","name":"ABDUL HADI","gender":"M"},
    {"roll":"PDS23003","name":"SAKIA KANWAL","gender":"F"},
    {"roll":"PDS23004","name":"MADIHA BEGUM","gender":"F"},
    {"roll":"PDS23005","name":"ISMA KHAN","gender":"F"},
    {"roll":"PDS23006","name":"AIMEN WAJID","gender":"F"},
    {"roll":"PDS23007","name":"AROOJ IMRAN","gender":"F"},
    {"roll":"PDS23008","name":"AREEBA SABIR","gender":"F"},
    {"roll":"PDS23009","name":"SHEHRYAR NAZIR","gender":"M"},
    {"roll":"PDS23010","name":"SAKHAWAT ALI","gender":"M"},
    {"roll":"PDS23011","name":"ZARRAR HAIDER","gender":"M"},
    {"roll":"PDS23012","name":"YASMEEN QAISER","gender":"F"},
    {"roll":"PDS23013","name":"IQRA KIRAN","gender":"F"},
    {"roll":"PDS23014","name":"LAIBA AYAZ","gender":"F"},
    {"roll":"PDS23015","name":"SHANAB AHMED","gender":"M"},
    {"roll":"PDS23016","name":"UBAID-ULLAH","gender":"M"},
    {"roll":"PDS23017","name":"MUHAMMAD UMAR","gender":"M"},
    {"roll":"PDS23018","name":"IQRA IBRAHIM","gender":"F"},
    {"roll":"PDS24019","name":"AZKA WAHID","gender":"F"},
    {"roll":"PDS24020","name":"MUHAMMAD HUZAIFA MALIK","gender":"M"},
    {"roll":"PDS24021","name":"FARRUKH HUSSAIN SHAH","gender":"M"},
    {"roll":"PDS24022","name":"SAMEER AHMAD KHAN","gender":"M"},
    {"roll":"PDS24023","name":"NIMRA YASIN","gender":"F"},
    {"roll":"PDS24024","name":"AREESHA KAINAT","gender":"F"},
    {"roll":"PDS24025","name":"KAINAT","gender":"F"},
    {"roll":"PDS24026","name":"GUL-E-SEHAR","gender":"F"},
    {"roll":"PDS24027","name":"SANA FAREED","gender":"F"},
    {"roll":"PDS24028","name":"ANSA SAMEER","gender":"F"},
    {"roll":"PDS24029","name":"EHTISHAM ALI","gender":"M"},
    {"roll":"PDS24030","name":"IQRA MUBEEN","gender":"F"},
    {"roll":"PDS24031","name":"NAZIA PARVEEN","gender":"F"},
    {"roll":"PDS24032","name":"ALISHBA SHAKIR","gender":"F"},
    {"roll":"PDS24033","name":"MUHAMMAD TARIQ","gender":"M"},
    {"roll":"PDS24034","name":"SAWAIRA BEGUM","gender":"F"},
    {"roll":"PDS24035","name":"SEHRISH NADEEM","gender":"F"},
    {"roll":"PDS24036","name":"AYESHA NAVEED","gender":"F"},
    {"roll":"PDS24037","name":"SHAHID KHAN","gender":"M"},
    {"roll":"PDS24038","name":"SAFINA NISAR","gender":"F"},
    {"roll":"PDS24039","name":"MUHAMMAD UMER MOBEEN","gender":"M"},
    {"roll":"PDS24040","name":"FATIMA JAVERIA HASHMI","gender":"F"},
    {"roll":"PDS24041","name":"NIMRA HAIDER","gender":"F"},
    {"roll":"PDS24042","name":"KHADIJA BIBI","gender":"F"},
    {"roll":"PDS24043","name":"MUHAMMAD HASSAM HAMEED KHAN","gender":"M"},
    {"roll":"PDS24044","name":"TEHREEM ASIM","gender":"F"},
]

# ── SUBJECT ALIASES ────────────────────────────────────────────
SUBJECTS = {
    "pharmacology":       ["pharmacology", "pharma", "pharmacology-i", "pharmacology 1"],
    "pharmacognosy":      ["pharmacognosy", "cognosy", "pharmacognosy-i", "pharmacognosy 1"],
    "pharmacology lab":   ["pharmacology lab", "pharma lab", "pharm lab"],
    "pharmaceutics lab":  ["pharmaceutics lab", "pharma lab", "pharmaceutics l"],
    "pharmaceutics-i":    ["pharmaceutics", "pharmaceutics-i", "pharmaceutics 1", "pharma-i"],
    "pharmacognosy lab":  ["pharmacognosy lab", "cognosy lab"],
    "microbiology lab":   ["microbiology lab", "micro lab", "micro l"],
    "microbiology":       ["microbiology", "micro", "microbio"],
    "islamic studies":    ["islamic", "islamic studies", "islamiat"],
    "maths":              ["maths", "math", "mathematics"],
}

TEACHER_MAP = {
    "pharmacology":      "Miss Khadija Ijaz",
    "pharmacology lab":  "Miss Khadija Ijaz",
    "pharmacognosy":     "Miss Sabina Nazish",
    "pharmacognosy lab": "Miss Sabina Nazish",
    "pharmaceutics lab": "Miss Ushna Ejaz",
    "pharmaceutics-i":   "Miss Ushna Ejaz",
    "microbiology lab":  "Miss Khadija Ijaz",
    "microbiology":      "Miss Khadija Ijaz",
    "islamic studies":   "Mr. Muhammad Farooq",
    "maths":             "Mr. Anwar ul Mehmood",
}

# ── HELPERS ────────────────────────────────────────────────────
def match_subject(text):
    text = text.lower().strip()
    for canonical, aliases in SUBJECTS.items():
        for alias in aliases:
            if alias in text:
                return canonical
    # fuzzy fallback
    all_aliases = [a for aliases in SUBJECTS.values() for a in aliases]
    matches = get_close_matches(text, all_aliases, n=1, cutoff=0.6)
    if matches:
        for canonical, aliases in SUBJECTS.items():
            if matches[0] in aliases:
                return canonical
    return None

def get_sheets_client():
    creds_dict = json.loads(GOOGLE_CREDS_JSON)
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def save_to_sheets(subject, date, lecture, records):
    try:
        gc = get_sheets_client()
        sh = gc.open(SPREADSHEET_NAME)
        try:
            ws = sh.worksheet(subject.title())
        except:
            ws = sh.add_worksheet(title=subject.title(), rows=500, cols=10)
            ws.append_row(["Date","Lecture #","Roll No","Student Name","Gender","Status"])

        for s in STUDENTS:
            status = "P" if records.get(s["roll"]) else "A"
            ws.append_row([date, lecture, s["roll"], s["name"], s["gender"], status])
        return True
    except Exception as e:
        print(f"Sheets error: {e}")
        return False

def scan_register_photo(image_url):
    """Download image and send to Claude for scanning"""
    import urllib.request, base64, mimetypes
    try:
        req = urllib.request.Request(image_url, headers={
            "Authorization": f"Basic {base64.b64encode(f'{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}'.encode()).decode()}"
        })
        with urllib.request.urlopen(req) as r:
            image_data = base64.b64encode(r.read()).decode()
            content_type = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
    except Exception as e:
        print(f"Image download error: {e}")
        return None

    student_list = "\n".join([f"{s['roll']} — {s['name']}" for s in STUDENTS])
    prompt = f"""You are reading a handwritten or printed class attendance register photo from a pharmacy college in Pakistan.

Here is the complete student list (PDS24 Semester 3, Pharm-D):
{student_list}

Instructions:
1. Look at the register photo carefully
2. Identify which students are marked present (tick, P, checkmark) and absent (cross, A, blank)
3. Match names to the student list above
4. Return ONLY valid JSON:
{{
  "present": ["PDS23001", "PDS23003", ...],
  "absent": ["PDS23002", ...],
  "unmatched": ["names you saw but couldn't match"],
  "lecture_no": 1
}}
Only include roll numbers from the list. If you can see a lecture number in the register, include it."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": image_data}},
                {"type": "text", "text": prompt}
            ]
        }]
    )
    text = "".join(b.text for b in response.content if hasattr(b, "text"))
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        return json.loads(match.group())
    return None

def send_whatsapp(to, message):
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    client.messages.create(body=message, from_=TWILIO_WA_NUMBER, to=to)

# ── MAIN WEBHOOK ───────────────────────────────────────────────
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    sender     = request.form.get("From", "")
    body       = request.form.get("Body", "").strip()
    num_media  = int(request.form.get("NumMedia", 0))
    media_url  = request.form.get("MediaUrl0", "")

    resp = MessagingResponse()

    # ── No image sent ──
    if num_media == 0:
        resp.message(
            "👋 *AIHS Attendance Bot*\n\n"
            "To mark attendance, send a *photo* of the register with the subject name in the caption.\n\n"
            "Example caption:\n_Pharmacology_ or _Microbiology Lab_\n\n"
            "Available subjects:\n" +
            "\n".join([f"• {s.title()}" for s in SUBJECTS.keys()])
        )
        return str(resp)

    # ── Image received ──
    subject = match_subject(body)
    if not subject:
        resp.message(
            "⚠️ Couldn't identify the subject from your caption.\n\n"
            "Please resend the photo with a clearer caption like:\n"
            "_Pharmacology_\n_Microbiology Lab_\n_Islamic Studies_"
        )
        return str(resp)

    # Acknowledge immediately
    send_whatsapp(sender,
        f"📸 Received! Scanning the *{subject.title()}* register...\n"
        f"This takes about 15 seconds ⏳"
    )

    # Scan with AI
    result = scan_register_photo(media_url)
    if not result:
        send_whatsapp(sender,
            "❌ Couldn't read the register clearly.\n"
            "Please try again with a clearer, well-lit photo."
        )
        return str(resp)

    # Build records
    present_set = set(result.get("present", []))
    records = {s["roll"]: (s["roll"] in present_set) for s in STUDENTS}
    present_count = sum(1 for v in records.values() if v)
    absent_count  = len(STUDENTS) - present_count
    pct           = round(present_count / len(STUDENTS) * 100)
    date          = datetime.now().strftime("%Y-%m-%d")
    lecture_no    = result.get("lecture_no", "?")

    # Get absent names
    absent_names = [s["name"] for s in STUDENTS if not records.get(s["roll"])]
    absent_preview = "\n".join([f"  ✗ {n}" for n in absent_names[:10]])
    if len(absent_names) > 10:
        absent_preview += f"\n  ...and {len(absent_names)-10} more"

    # Save to Google Sheets
    saved = save_to_sheets(subject, date, lecture_no, records)
    sheets_status = "✅ Saved to Google Sheets" if saved else "⚠️ Sheets sync failed — contact admin"

    # Send confirmation
    unmatched = result.get("unmatched", [])
    unmatched_note = f"\n⚠️ Unmatched names: {', '.join(unmatched)}" if unmatched else ""

    send_whatsapp(sender,
        f"✅ *{subject.title()}* — Attendance Recorded\n"
        f"📅 {date}  |  Lecture #{lecture_no}\n"
        f"👨‍🎓 Present: *{present_count}*  |  Absent: *{absent_count}*  |  Rate: *{pct}%*\n\n"
        f"*Absent students:*\n{absent_preview}\n\n"
        f"{sheets_status}{unmatched_note}\n\n"
        f"_— AIHS Attendance Bot_"
    )

    return str(resp)

@app.route("/", methods=["GET"])
def health():
    return "AIHS Attendance Bot is running ✅", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
