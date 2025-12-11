# app.py
import os
import sqlite3
from datetime import date, datetime, timedelta
from flask import (
    Flask, g, render_template, request, redirect, url_for,
    session, send_from_directory, jsonify, flash
)
from werkzeug.utils import secure_filename
from functools import wraps

# -------------------------
# Configuration
# -------------------------
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_ROOT, "instance", "database.db")
UPLOAD_PUBLIC = os.path.join(APP_ROOT, "static", "uploads", "public")
UPLOAD_PRIVATE = os.path.join(APP_ROOT, "static", "uploads", "private")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "pdf", "mp3", "wav", "mp4", "zip"}

os.makedirs(os.path.join(APP_ROOT, "instance"), exist_ok=True)
os.makedirs(UPLOAD_PUBLIC, exist_ok=True)
os.makedirs(UPLOAD_PRIVATE, exist_ok=True)

app = Flask(__name__)
app.secret_key = "replace-this-secret"  # change in production


# -------------------------
# DB helpers
# -------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db:
        db.close()


def init_tables():
    """Create tables if they don't exist."""
    db = get_db()
    c = db.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            name TEXT,
            role TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS practice_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            hours REAL,
            technique TEXT,
            notes TEXT,
            UNIQUE(user_id, date),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            piece TEXT,
            error_text TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS special_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            date TEXT,
            note_text TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            title TEXT,
            message TEXT,
            timestamp TEXT,
            attachment TEXT,
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS public_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            file_name TEXT,
            original_name TEXT,
            file_type TEXT,
            description TEXT,
            timestamp TEXT,
            FOREIGN KEY(teacher_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS private_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_name TEXT,
            original_name TEXT,
            file_type TEXT,
            description TEXT,
            timestamp TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            suggestion TEXT,
            timestamp TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    db.commit()


def ensure_default_users():
    """(If database has no users) insert default 50 students and 10 teachers."""
    db = get_db()
    c = db.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM users")
    r = c.fetchone()
    if r and r["cnt"] > 0:
        return  # already initialized

    # students 10001-10050
    for i in range(10001, 10051):
        c.execute(
            "INSERT OR IGNORE INTO users (id, username, password, name, role) VALUES (?, ?, ?, ?, 'student')",
            (i, str(i), str(i), f"Student {i}")
        )
        # create private folder for student
        student_folder = os.path.join(UPLOAD_PRIVATE, str(i))
        os.makedirs(student_folder, exist_ok=True)

    # teachers 70001-70010
    for i in range(70001, 70011):
        c.execute(
            "INSERT OR IGNORE INTO users (id, username, password, name, role) VALUES (?, ?, ?, ?, 'teacher')",
            (i, str(i), str(i), f"Teacher {i}")
        )
        teacher_folder = os.path.join(UPLOAD_PRIVATE, str(i))
        os.makedirs(teacher_folder, exist_ok=True)

    db.commit()


# initialize on startup
with app.app_context():
    init_tables()
    ensure_default_users()


# -------------------------
# Utilities & Auth
# -------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    return "." in filename and ext in ALLOWED_EXT


def get_user_by_username(username):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def get_user_by_id(uid):
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


# -------------------------
# Auth routes
# -------------------------
@app.route("/login", methods=["GET", "POST"])
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not (username.isdigit() and len(username) == 5):
            return render_template("login.html", error="Username must be 5 digits.")

        user = get_user_by_username(username)
        if not user or user["password"] != password:
            return render_template("login.html", error="Invalid username or password.")

        # set session
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["name"] = user["name"]
        # Redirect by role
        if user["role"] == "student":
            return redirect(url_for("dashboard_student"))
        else:
            return redirect(url_for("dashboard_teacher"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------------------------
# Dashboards
# -------------------------
@app.route("/dashboard_student")
@login_required
def dashboard_student():
    if session.get("role") != "student":
        return redirect(url_for("dashboard_teacher"))

    user_id = session["user_id"]
    db = get_db()
    today = date.today().isoformat()

    # today's hours
    row = db.execute(
        "SELECT hours FROM practice_entries WHERE user_id=? AND date=?",
        (user_id, today)
    ).fetchone()
    today_hours = float(row["hours"]) if row else 0.0

    # month total
    now = date.today()
    month_start = now.replace(day=1).isoformat()
    month_end = (now.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    month_end = month_end.isoformat()
    r = db.execute(
        "SELECT SUM(hours) as s FROM practice_entries WHERE user_id=? AND date BETWEEN ? AND ?",
        (user_id, month_start, month_end)
    ).fetchone()
    month_hours = float(r["s"]) if r and r["s"] else 0.0

    # notes this week (special_notes and practice_entries notes)
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    count_notes1 = db.execute(
        "SELECT COUNT(*) AS c FROM special_notes WHERE user_id=? AND date >= ?",
        (user_id, week_ago)
    ).fetchone()["c"]
    count_notes2 = db.execute(
        "SELECT COUNT(*) AS c FROM practice_entries WHERE user_id=? AND date >= ? AND notes IS NOT NULL AND notes != ''",
        (user_id, week_ago)
    ).fetchone()["c"]
    notes_week = int(count_notes1) + int(count_notes2)

    return render_template(
        "dashboard_student.html",
        title="Dashboard",
        active="dashboard",
        today_hours=round(today_hours, 2),
        month_hours=round(month_hours, 2),
        notes_week=notes_week,
    )


@app.route("/dashboard_teacher")
@login_required
def dashboard_teacher():
    if session.get("role") != "teacher":
        return redirect(url_for("dashboard_student"))
    # Simple teacher dashboard: show their name and count of public files and notifications
    db = get_db()
    teacher_id = session["user_id"]
    pub_files = db.execute("SELECT COUNT(*) AS c FROM public_files WHERE teacher_id=?", (teacher_id,)).fetchone()["c"]
    notes = db.execute("SELECT COUNT(*) AS c FROM notifications WHERE teacher_id=?", (teacher_id,)).fetchone()["c"]
    return render_template("dashboard_teacher.html",
                           title="Teacher Dashboard",
                           active="dashboard",
                           pub_files=pub_files,
                           notifications_count=notes)


# -------------------------
# Hours (Calendar) routes
# -------------------------
@app.route("/hours")
@login_required
def hours():
    # Student-only page
    if session.get("role") != "student":
        return redirect(url_for("dashboard_teacher"))

    user_id = session["user_id"]
    db = get_db()
    rows = db.execute(
        "SELECT date, hours, technique, notes FROM practice_entries WHERE user_id=?",
        (user_id,)
    ).fetchall()

    data = {}
    for r in rows:
        data[r["date"]] = {"hours": r["hours"], "technique": r["technique"], "notes": r["notes"]}

    return render_template("hours.html", title="Hours Practiced", active="hours", data=data)


@app.route("/save_hours", methods=["POST"])
@login_required
def save_hours():
    if session.get("role") != "student":
        return "forbidden", 403
    user_id = session["user_id"]
    date_str = request.form.get("date")
    hours = request.form.get("hours") or 0
    technique = request.form.get("technique") or ""
    notes = request.form.get("notes") or ""

    # normalize date format (YYYY-M-D or YYYY-MM-DD) -> YYYY-MM-DD
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        # try alternative parsing
        d = datetime.fromisoformat(date_str)
    date_key = d.date().isoformat()

    db = get_db()
    # upsert
    db.execute("""
        INSERT INTO practice_entries (user_id, date, hours, technique, notes)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, date) DO UPDATE SET hours=excluded.hours, technique=excluded.technique, notes=excluded.notes
    """, (user_id, float(hours), date_key, technique, notes))
    db.commit()
    return "ok", 200


@app.route("/delete_hours", methods=["POST"])
@login_required
def delete_hours():
    if session.get("role") != "student":
        return "forbidden", 403
    user_id = session["user_id"]
    date_str = request.form.get("date")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        d = datetime.fromisoformat(date_str)
    date_key = d.date().isoformat()

    db = get_db()
    db.execute("DELETE FROM practice_entries WHERE user_id=? AND date=?", (user_id, date_key))
    db.commit()
    return "ok", 200


# -------------------------
# Errors routes
# -------------------------
@app.route("/errors")
@login_required
def errors():
    if session.get("role") != "student":
        return redirect(url_for("dashboard_teacher"))
    user_id = session["user_id"]
    db = get_db()
    rows = db.execute("SELECT id, date, piece, error_text FROM errors WHERE user_id=? ORDER BY date DESC", (user_id,)).fetchall()
    return render_template("errors.html", title="Errors", active="errors", errors=rows)


@app.route("/add_error", methods=["POST"])
@login_required
def add_error():
    if session.get("role") != "student":
        return "forbidden", 403
    user_id = session["user_id"]
    piece = request.form.get("piece") or ""
    error_text = request.form.get("error_text") or ""
    date_str = date.today().isoformat()
    db = get_db()
    db.execute("INSERT INTO errors (user_id, date, piece, error_text) VALUES (?,?,?,?)",
               (user_id, date_str, piece, error_text))
    db.commit()
    return redirect(url_for("errors"))


# -------------------------
# Notes routes
# -------------------------
@app.route("/notes")
@login_required
def notes():
    if session.get("role") != "student":
        return redirect(url_for("dashboard_teacher"))
    user_id = session["user_id"]
    db = get_db()
    rows = db.execute("SELECT id, date, note_text FROM special_notes WHERE user_id=? ORDER BY date DESC", (user_id,)).fetchall()
    return render_template("notes.html", title="Notes", active="notes", notes=rows)


@app.route("/add_note", methods=["POST"])
@login_required
def add_note():
    if session.get("role") != "student":
        return "forbidden", 403
    user_id = session["user_id"]
    note_text = request.form.get("note_text") or ""
    date_str = date.today().isoformat()
    db = get_db()
    db.execute("INSERT INTO special_notes (user_id, date, note_text) VALUES (?,?,?)",
               (user_id, date_str, note_text))
    db.commit()
    return redirect(url_for("notes"))


# -------------------------
# Music Library routes
# -------------------------
@app.route("/music-library")
@login_required
def music_library():
    db = get_db()
    # public teacher files
    public = db.execute("SELECT pf.*, u.name as teacher_name FROM public_files pf LEFT JOIN users u ON u.id=pf.teacher_id ORDER BY pf.timestamp DESC").fetchall()
    # private files for this user
    user_id = session["user_id"]
    private = db.execute("SELECT * FROM private_files WHERE user_id=? ORDER BY timestamp DESC", (user_id,)).fetchall()
    return render_template("music_library.html", title="Music Library", active="library", public=public, private=private)


@app.route("/upload_public", methods=["POST"])
@login_required
def upload_public():
    # only teachers can upload public files
    if session.get("role") != "teacher":
        return "forbidden", 403

    if "file" not in request.files:
        flash("No file")
        return redirect(url_for("music_library"))

    f = request.files["file"]
    desc = request.form.get("description", "")
    if f and allowed_file(f.filename):
        filename = secure_filename(f.filename)
        timestamp = datetime.now().isoformat()
        save_name = f"{session['username']}_{int(datetime.now().timestamp())}_{filename}"
        save_path = os.path.join(UPLOAD_PUBLIC, save_name)
        f.save(save_path)

        db = get_db()
        db.execute("INSERT INTO public_files (teacher_id, file_name, original_name, file_type, description, timestamp) VALUES (?,?,?,?,?,?)",
                   (session["user_id"], save_name, filename, filename.rsplit(".", 1)[-1].lower(), desc, timestamp))
        db.commit()

    return redirect(url_for("music_library"))


@app.route("/upload_private", methods=["POST"])
@login_required
def upload_private():
    if "file" not in request.files:
        flash("No file")
        return redirect(url_for("music_library"))
    f = request.files["file"]
    desc = request.form.get("description", "")
    if f and allowed_file(f.filename):
        filename = secure_filename(f.filename)
        save_name = f"{session['username']}_{int(datetime.now().timestamp())}_{filename}"
        personal_folder = os.path.join(UPLOAD_PRIVATE, str(session["user_id"]))
        os.makedirs(personal_folder, exist_ok=True)
        save_path = os.path.join(personal_folder, save_name)
        f.save(save_path)

        db = get_db()
        db.execute("INSERT INTO private_files (user_id, file_name, original_name, file_type, description, timestamp) VALUES (?,?,?,?,?,?)",
                   (session["user_id"], save_name, filename, filename.rsplit(".", 1)[-1].lower(), desc, datetime.now().isoformat()))
        db.commit()

    return redirect(url_for("music_library"))


@app.route("/download/public/<filename>")
@login_required
def download_public(filename):
    return send_from_directory(UPLOAD_PUBLIC, filename, as_attachment=True)


@app.route("/download/private/<filename>")
@login_required
def download_private(filename):
    # only allow if file belongs to current user or teacher (owner)
    db = get_db()
    row = db.execute("SELECT * FROM private_files WHERE file_name=?", (filename,)).fetchone()
    if not row:
        return "Not found", 404
    if session.get("role") == "teacher" and row["user_id"] != session["user_id"]:
        # teachers cannot see student private files
        return "Forbidden", 403
    if session.get("role") == "student" and row["user_id"] != session["user_id"]:
        return "Forbidden", 403
    personal_folder = os.path.join(UPLOAD_PRIVATE, str(row["user_id"]))
    return send_from_directory(personal_folder, filename, as_attachment=True)


# delete public file (teacher)
@app.route("/delete_public_file/<int:file_id>", methods=["POST"])
@login_required
def delete_public_file(file_id):
    if session.get("role") != "teacher":
        return "forbidden", 403
    db = get_db()
    row = db.execute("SELECT * FROM public_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return "not found", 404
    if row["teacher_id"] != session["user_id"]:
        return "forbidden", 403
    # remove from disk
    try:
        os.remove(os.path.join(UPLOAD_PUBLIC, row["file_name"]))
    except Exception:
        pass
    db.execute("DELETE FROM public_files WHERE id=?", (file_id,))
    db.commit()
    return redirect(url_for("music_library"))


# delete private file (owner)
@app.route("/delete_private_file/<int:file_id>", methods=["POST"])
@login_required
def delete_private_file(file_id):
    db = get_db()
    row = db.execute("SELECT * FROM private_files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return "not found", 404
    if row["user_id"] != session["user_id"]:
        return "forbidden", 403
    try:
        personal_folder = os.path.join(UPLOAD_PRIVATE, str(row["user_id"]))
        os.remove(os.path.join(personal_folder, row["file_name"]))
    except Exception:
        pass
    db.execute("DELETE FROM private_files WHERE id=?", (file_id,))
    db.commit()
    return redirect(url_for("music_library"))


# -------------------------
# Notifications
# -------------------------
@app.route("/notifications")
@login_required
def notifications():
    db = get_db()
    if session.get("role") == "teacher":
        rows = db.execute("SELECT n.*, u.name as teacher_name FROM notifications n LEFT JOIN users u ON u.id=n.teacher_id WHERE n.teacher_id=? ORDER BY timestamp DESC", (session["user_id"],)).fetchall()
    else:
        # students see all teacher notifications
        rows = db.execute("SELECT n.*, u.name as teacher_name FROM notifications n LEFT JOIN users u ON u.id=n.teacher_id ORDER BY timestamp DESC").fetchall()
    return render_template("notifications.html", title="Notifications", active="notifications", notifications=rows)


@app.route("/create_notification", methods=["POST"])
@login_required
def create_notification():
    if session.get("role") != "teacher":
        return "forbidden", 403
    title = request.form.get("title") or ""
    message = request.form.get("message") or ""
    attach = request.files.get("attachment", None)
    filename = None
    if attach and allowed_file(attach.filename):
        orig = secure_filename(attach.filename)
        filename = f"{session['username']}_{int(datetime.now().timestamp())}_{orig}"
        p = os.path.join(UPLOAD_PUBLIC, filename)
        attach.save(p)
    db = get_db()
    db.execute("INSERT INTO notifications (teacher_id, title, message, timestamp, attachment) VALUES (?,?,?,?,?)",
               (session["user_id"], title, message, datetime.now().isoformat(), filename))
    db.commit()
    return redirect(url_for("notifications"))


@app.route("/edit_notification/<int:notif_id>", methods=["POST"])
@login_required
def edit_notification(notif_id):
    if session.get("role") != "teacher":
        return "forbidden", 403
    title = request.form.get("title") or ""
    message = request.form.get("message") or ""
    db = get_db()
    row = db.execute("SELECT * FROM notifications WHERE id=?", (notif_id,)).fetchone()
    if not row or row["teacher_id"] != session["user_id"]:
        return "forbidden", 403
    db.execute("UPDATE notifications SET title=?, message=? WHERE id=?", (title, message, notif_id))
    db.commit()
    return redirect(url_for("notifications"))


@app.route("/delete_notification/<int:notif_id>", methods=["POST"])
@login_required
def delete_notification(notif_id):
    if session.get("role") != "teacher":
        return "forbidden", 403
    db = get_db()
    row = db.execute("SELECT * FROM notifications WHERE id=?", (notif_id,)).fetchone()
    if not row or row["teacher_id"] != session["user_id"]:
        return "forbidden", 403
    # delete attachment from disk if exists
    if row["attachment"]:
        try:
            os.remove(os.path.join(UPLOAD_PUBLIC, row["attachment"]))
        except Exception:
            pass
    db.execute("DELETE FROM notifications WHERE id=?", (notif_id,))
    db.commit()
    return redirect(url_for("notifications"))


# -------------------------
# Suggestions (simple rule-based)
# -------------------------
@app.route("/suggestions")
@login_required
def suggestions():
    if session.get("role") != "student":
        return redirect(url_for("dashboard_teacher"))
    user_id = session["user_id"]
    db = get_db()

    # compute simple signals
    rows = db.execute("SELECT date, hours, technique FROM practice_entries WHERE user_id=? ORDER BY date DESC LIMIT 30", (user_id,)).fetchall()
    suggestions_list = []

    # 1) Consistency: compare last 7 days vs previous 7 days
    def sum_range(rows_list):
        s = 0
        for r in rows_list:
            try:
                s += float(r["hours"] or 0)
            except Exception:
                pass
        return s

    last_7 = rows[:7]
    prev_7 = rows[7:14]
    s_last = sum_range(last_7)
    s_prev = sum_range(prev_7)
    if s_prev > 0:
        pct = ((s_last - s_prev) / s_prev) * 100
        if pct >= 10:
            suggestions_list.append(("Consistency improved", f"Your practice time increased by {int(pct)}% vs previous week."))
        elif pct <= -10:
            suggestions_list.append(("Consistency drop", f"Your practice time dropped by {int(abs(pct))}% vs previous week. Try 3 short sessions."))
    elif s_last > 0:
        suggestions_list.append(("New streak", "Nice job starting a consistent practice! Keep going."))

    # 2) Weak area detection (technique keyword frequency)
    tech_freq = {}
    for r in rows:
        t = (r["technique"] or "").strip().lower()
        if not t:
            continue
        tech_freq[t] = tech_freq.get(t, 0) + 1
    if tech_freq:
        top = max(tech_freq.items(), key=lambda x: x[1])
        suggestions_list.append(("Focus area", f"You've practiced '{top[0]}' {top[1]} times recently — consider drilling it deliberately."))

    # 3) Low practice alert
    total_30 = sum_range(rows)
    if total_30 < 2:
        suggestions_list.append(("Low practice", "You practiced less than 2 hours in the last 30 recorded sessions. Try a 10-minute daily goal."))

    return render_template("suggestions.html", title="Smart Suggestions", active="suggestions", suggestions=suggestions_list)


# -------------------------
# Analytics API (returns JSON for Chart.js)
# -------------------------
@app.route("/api/hours_data")
@login_required
def api_hours_data():
    if session.get("role") != "student":
        return jsonify({"error": "forbidden"}), 403
    user_id = session["user_id"]
    db = get_db()
    # return last 30 days of data (date => hours)
    start = (date.today() - timedelta(days=29)).isoformat()
    rows = db.execute("SELECT date, hours FROM practice_entries WHERE user_id=? AND date>=? ORDER BY date", (user_id, start)).fetchall()
    data = {r["date"]: r["hours"] for r in rows}
    # ensure all days are present
    result = []
    for i in range(30):
        d = (date.today() - timedelta(days=29 - i)).isoformat()
        result.append({"date": d, "hours": float(data.get(d, 0))})
    return jsonify(result)


# -------------------------
# Profile (change password)
# -------------------------
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    user = get_user_by_id(session["user_id"])
    if request.method == "POST":
        current = request.form.get("current_password")
        newp = request.form.get("new_password")
        confirm = request.form.get("confirm_password")
        if current != user["password"]:
            return render_template("profile.html", title="Profile", active="profile", error="Current password incorrect.", user=user)
        if not newp or newp != confirm:
            return render_template("profile.html", title="Profile", active="profile", error="New passwords do not match.", user=user)
        db.execute("UPDATE users SET password=? WHERE id=?", (newp, session["user_id"]))
        db.commit()
        return render_template("profile.html", title="Profile", active="profile", success="Password changed.", user=get_user_by_id(session["user_id"]))
    return render_template("profile.html", title="Profile", active="profile", user=user)


# -------------------------
# Utility: serve uploaded files list (teacher's attachment files are in public folder)
# -------------------------
@app.route("/uploads/public/<filename>")
@login_required
def serve_public_upload(filename):
    return send_from_directory(UPLOAD_PUBLIC, filename)


# -------------------------
# Small helper routes for templates that expect certain names
# -------------------------
@app.context_processor
def inject_user():
    return dict(current_user={
        "id": session.get("user_id"),
        "username": session.get("username"),
        "role": session.get("role"),
        "name": session.get("name")
    })


# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)