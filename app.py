import os
import json
import io
import base64
import secrets
from datetime import datetime
from functools import wraps

import qrcode
from flask import Flask, render_template, request, redirect, url_for, jsonify, Response

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "responses.json")
ADMIN_PASSWORD = "emermed2026"

SCALE_OPTIONS = [
    {"value": "1", "label": "Performs basic tasks and E&M of common disease at very early level", "sublabel": "Needs continual guidance"},
    {"value": "2", "label": "Performs basic tasks and E&M of common disease with more independence", "sublabel": "May still require direct supervision"},
    {"value": "3", "label": "Performs more complex tasks and E&M of multisystem disease", "sublabel": "Requires indirect supervision"},
    {"value": "4", "label": "Performs more complex tasks and E&M of complex disease independently", "sublabel": "Ready to graduate"},
    {"value": "5", "label": "Functions as instructor or supervisor", "sublabel": "Aspirational performance"},
    {"value": "N/A", "label": "Not yet completed level 1 or Not yet assessable", "sublabel": ""},
]

QUESTIONS = [
    {
        "id": "q2",
        "number": 1,
        "title": "Data Gathering / Interpretation",
        "text": "Conducts a patient interview; performs a pertinent physical exam; appropriately prioritizes and interprets essential tests; synthesizes all information in a timely manner to generate a differential diagnosis; modifies differential diagnosis in response to new information.",
        "type": "scale",
    },
    {
        "id": "q3",
        "number": 2,
        "title": "Management Plans",
        "text": "With progressive independence, initiates, manages and modifies patient care plans for common through complex medical diseases (e.g. abnormal vital signs, sick vs not sick, cardiac vs noncardiac chest pain, arrhythmia, injury, altered mental status, decompensated liver disease) using appropriate resources and evidence-based medicine.",
        "type": "scale",
    },
    {
        "id": "q4",
        "number": 3,
        "title": "Consult Interactions",
        "text": "Asks the appropriate questions of consultants; weighs and implements recommendations.",
        "type": "scale",
    },
    {
        "id": "q5",
        "number": 4,
        "title": "Acute Care",
        "text": "Recognizes and manages acute clinical decompensations/emergencies (e.g. shock, ACS, respiratory failure, CVA); stabilizes the patient and escalates care when appropriate.",
        "type": "scale",
    },
    {
        "id": "q1",
        "number": 5,
        "title": "Strengths & Focused Feedback",
        "text": "Please document the resident's strengths, and provide focused feedback for development of knowledge, skills and attitude. This is the most meaningful portion of the evaluation.",
        "type": "textarea",
    },
]


def load_responses():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_response(entry):
    responses = load_responses()
    responses.append(entry)
    with open(DATA_FILE, "w") as f:
        json.dump(responses, f, indent=2)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.password != ADMIN_PASSWORD:
            return Response(
                "Login required.",
                401,
                {"WWW-Authenticate": 'Basic realm="Results Dashboard"'},
            )
        return f(*args, **kwargs)
    return decorated


@app.route("/")
def survey():
    return render_template("survey.html", questions=QUESTIONS, scale_options=SCALE_OPTIONS)


@app.route("/submit", methods=["POST"])
def submit():
    data = request.form.to_dict()
    data["submitted_at"] = datetime.now().isoformat()
    save_response(data)
    return render_template("thanks.html")


@app.route("/results")
@require_auth
def results():
    responses = load_responses()
    return render_template(
        "results.html",
        responses=responses,
        questions=QUESTIONS,
        scale_options=SCALE_OPTIONS,
    )


@app.route("/results/export")
@require_auth
def export_csv():
    responses = load_responses()
    if not responses:
        return "No responses yet.", 200

    headers = ["submitted_at", "resident_name", "q2", "q3", "q4", "q5", "q1"]
    lines = [",".join(headers)]
    for r in responses:
        row = [r.get(h, "").replace('"', '""') for h in headers]
        lines.append(",".join(f'"{v}"' for v in row))
    csv_text = "\n".join(lines)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=resident_feedback.csv"},
    )


@app.route("/qr")
def qr_code():
    """Generate QR code pointing to the public tunnel URL or local URL."""
    base = request.host_url.rstrip("/")
    img = qrcode.make(base)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    return render_template("qr.html", qr_data=encoded, url=base)


os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
