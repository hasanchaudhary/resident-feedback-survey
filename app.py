import os
import json
import io
import base64
import secrets
from datetime import datetime
from functools import wraps

import qrcode
from flask import Flask, render_template, request, redirect, jsonify, Response

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
DATABASE_URL = os.environ.get("DATABASE_URL")

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

# ---------------------------------------------------------------------------
# Database layer — PostgreSQL in production, JSON file for local development
# ---------------------------------------------------------------------------

if DATABASE_URL:
    import psycopg2
    from psycopg2.extras import RealDictCursor

    def get_db():
        return psycopg2.connect(DATABASE_URL)

    def init_db():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id SERIAL PRIMARY KEY,
                resident_name TEXT,
                q1 TEXT,
                q2 TEXT,
                q3 TEXT,
                q4 TEXT,
                q5 TEXT,
                submitted_at TEXT
            )
        """)
        conn.commit()
        cur.close()
        conn.close()

    def load_responses():
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM responses ORDER BY submitted_at ASC")
        rows = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return rows

    def save_response(entry):
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO responses (resident_name, q1, q2, q3, q4, q5, submitted_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (entry.get("resident_name", ""), entry.get("q1", ""), entry.get("q2", ""),
             entry.get("q3", ""), entry.get("q4", ""), entry.get("q5", ""), entry.get("submitted_at", "")),
        )
        conn.commit()
        cur.close()
        conn.close()

    def delete_response_by_id(response_id):
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM responses WHERE id = %s", (response_id,))
        conn.commit()
        cur.close()
        conn.close()

    def delete_all_responses():
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM responses")
        conn.commit()
        cur.close()
        conn.close()

    init_db()

else:
    # Local JSON fallback
    DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "responses.json")
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

    def load_responses():
        if not os.path.exists(DATA_FILE):
            return []
        with open(DATA_FILE) as f:
            rows = json.load(f)
        for i, r in enumerate(rows):
            r.setdefault("id", i)
        return rows

    def save_response(entry):
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE) as f:
                rows = json.load(f)
        else:
            rows = []
        clean = {k: v for k, v in entry.items() if k != "id"}
        rows.append(clean)
        with open(DATA_FILE, "w") as f:
            json.dump(rows, f, indent=2)

    def delete_response_by_id(response_id):
        rows = load_responses()
        rows = [{k: v for k, v in r.items() if k != "id"} for r in rows if r.get("id") != response_id]
        with open(DATA_FILE, "w") as f:
            json.dump(rows, f, indent=2)

    def delete_all_responses():
        with open(DATA_FILE, "w") as f:
            json.dump([], f, indent=2)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
        row = [str(r.get(h, "")).replace('"', '""') for h in headers]
        lines.append(",".join(f'"{v}"' for v in row))
    return Response(
        "\n".join(lines),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=resident_feedback.csv"},
    )


@app.route("/results/delete/<int:response_id>", methods=["POST"])
@require_auth
def delete_response(response_id):
    delete_response_by_id(response_id)
    return redirect("/results")


@app.route("/results/delete-all", methods=["POST"])
@require_auth
def delete_all():
    delete_all_responses()
    return redirect("/results")


@app.route("/qr")
def qr_code():
    base = request.host_url.rstrip("/")
    img = qrcode.make(base)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    return render_template("qr.html", qr_data=encoded, url=base)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(host="0.0.0.0", port=port, debug=True)
