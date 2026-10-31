from datetime import date
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import (
    Flask, request, redirect, url_for,
    session, flash, render_template_string
)
from werkzeug.security import generate_password_hash, check_password_hash

from config import (
    users, students, teachers, subjects, attendance,
    SECRET_KEY
)


app = Flask(__name__)
app.secret_key = SECRET_KEY or "change-this-secret-key-for-local-development"


# =========================================================
# COMMON PAGE TEMPLATE
# =========================================================

STYLE = """
<style>
* { box-sizing: border-box; }
body { margin: 0; font-family: Arial, sans-serif; background: #f3f6fb; color: #1e293b; }
nav { background: #172554; color: white; padding: 16px 25px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
nav a { color: white; text-decoration: none; margin-right: 15px; }
.container { max-width: 1100px; margin: 30px auto; padding: 0 18px; }
.card { background: white; padding: 22px; border-radius: 12px; box-shadow: 0 3px 12px #00000010; margin-bottom: 20px; overflow-x: auto; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 15px; }
.stat { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 3px 12px #00000010; }
.stat h2 { color: #2563eb; }
input, select, button { padding: 10px; margin: 5px 0; border: 1px solid #cbd5e1; border-radius: 7px; font-size: 14px; }
input:not([type=radio]):not([type=checkbox]), select { width: 100%; }
button, .btn { background: #2563eb; color: white; border: none; cursor: pointer; padding: 10px 15px; border-radius: 7px; text-decoration: none; display: inline-block; }
.danger { background: #dc2626; }
.secondary { background: #475569; }
table { width: 100%; border-collapse: collapse; background: white; min-width: 650px; }
th, td { padding: 11px; border-bottom: 1px solid #e2e8f0; text-align: left; }
th { background: #eff6ff; }
.flash { padding: 12px; margin-bottom: 12px; background: #dbeafe; border-radius: 7px; }
.muted { color: #64748b; }
.center { max-width: 450px; margin: 60px auto; }
.attendance-choice { display: flex; gap: 16px; align-items: center; }
.attendance-choice input { width: 18px; height: 18px; }
.actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
</style>
"""


def render_page(title, body, **kwargs):
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ title }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        """ + STYLE + """
    </head>
    <body>
        <nav>
            <strong>Student Attendance System</strong>
            <div>
                {% if session.get('user_id') %}
                    <a href="{{ url_for('dashboard') }}">Dashboard</a>
                    <a href="{{ url_for('logout') }}">Logout</a>
                {% endif %}
            </div>
        </nav>

        <div class="container">
            {% with messages = get_flashed_messages() %}
                {% for message in messages %}
                    <div class="flash">{{ message }}</div>
                {% endfor %}
            {% endwith %}

            """ + body + """
        </div>
    </body>
    </html>
    """
    return render_template_string(html, title=title, **kwargs)


# =========================================================
# AUTHORIZATION
# =========================================================

def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            flash("Please log in first.")
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                flash("Please log in first.")
                return redirect(url_for("login"))

            if session.get("role") not in roles:
                flash("You do not have permission to access this page.")
                return redirect(url_for("dashboard"))

            return function(*args, **kwargs)
        return wrapper
    return decorator


def current_student():
    return students.find_one({
        "email": session.get("email", "").lower()
    })


def current_teacher():
    return teachers.find_one({
        "email": session.get("email", "").lower()
    })


# =========================================================
# HOME, LOGIN, LOGOUT
# =========================================================

@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = users.find_one({"email": email})

        if user and check_password_hash(user.get("password", ""), password):
            session["user_id"] = str(user["_id"])
            session["name"] = user.get("name", "User")
            session["role"] = user.get("role", "").lower()
            session["email"] = user.get("email", "").lower()

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    body = """
    <div class="center card">
        <h2>Login</h2>
        <form method="POST">
            <label>Email</label>
            <input type="email" name="email" required>

            <label>Password</label>
            <input type="password" name="password" required>

            <button type="submit">Login</button>
        </form>
    </div>
    """
    return render_page("Login", body)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# DASHBOARD REDIRECT
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():
    role = session.get("role")
    print("CURRENT USER ROLE:", role)

    if role == "admin":
        return redirect(url_for("admin_dashboard"))

    if role == "teacher":
        return redirect(url_for("teacher_dashboard"))

    if role == "student":
        return redirect(url_for("student_dashboard"))

    flash("Unknown account role.")
    return redirect(url_for("logout"))


# =========================================================
# STUDENT DASHBOARD
# =========================================================

@app.route("/student")
@login_required
@role_required("student")
def student_dashboard():
    student = current_student()

    if not student:
        flash("Student profile not found.")
        return redirect(url_for("logout"))

    student_id = str(student["_id"])
    selected_subject_id = request.args.get("subject_id", "").strip()

    records = list(attendance.find({"student_id": student_id}))

    # Build subject list from attendance records
    subject_ids = {
        record.get("subject_id")
        for record in records
        if record.get("subject_id")
    }

    subject_documents = []

    for subject_id in subject_ids:
        try:
            subject = subjects.find_one({"_id": ObjectId(subject_id)})
            if subject:
                subject_documents.append(subject)
        except Exception:
            continue

    subject_documents.sort(key=lambda item: item.get("name", ""))

    # If no subject selected, select the first available subject
    if not selected_subject_id and subject_documents:
        selected_subject_id = str(subject_documents[0]["_id"])

    selected_subject = None

    if selected_subject_id:
        try:
            selected_subject = subjects.find_one({
                "_id": ObjectId(selected_subject_id)
            })
        except Exception:
            selected_subject = None

    subject_records = []

    if selected_subject:
        subject_records = [
            record for record in records
            if record.get("subject_id") == str(selected_subject["_id"])
        ]

    total_classes = len(subject_records)

    present_count = sum(
        1 for record in subject_records
        if record.get("status", "").lower() == "present"
    )

    absent_count = sum(
        1 for record in subject_records
        if record.get("status", "").lower() == "absent"
    )

    percentage = (
        round((present_count / total_classes) * 100, 2)
        if total_classes else 0
    )

    overall_total = len(records)

    overall_present = sum(
        1 for record in records
        if record.get("status", "").lower() == "present"
    )

    overall_percentage = (
        round((overall_present / overall_total) * 100, 2)
        if overall_total else 0
    )

    subject_records.sort(
        key=lambda record: record.get("date", ""),
        reverse=True
    )

    subject_options = ""

    for subject in subject_documents:
        subject_id = str(subject["_id"])
        selected = "selected" if subject_id == selected_subject_id else ""

        subject_options += f"""
        <option value="{subject_id}" {selected}>
            {subject.get("name", "")} — {subject.get("code", "")}
        </option>
        """

    history_rows = ""

    for record in subject_records:
        history_rows += f"""
        <tr>
            <td>{record.get("date", "-")}</td>
            <td>{record.get("status", "Unknown").title()}</td>
        </tr>
        """

    if not history_rows:
        history_rows = """
        <tr>
            <td colspan="2">No attendance records for this subject yet.</td>
        </tr>
        """

    body = f"""
    <div class="card">
        <h2>Student Dashboard</h2>

        <p>
            <strong>Name:</strong> {student.get("name", "")}<br>
            <strong>USN:</strong> {student.get("usn", "Not available")}
        </p>

        <form method="GET" action="{url_for('student_dashboard')}">
            <label for="subject_id">Select Subject</label>
            <select name="subject_id" id="subject_id"
                    onchange="this.form.submit()">
                <option value="">Select subject</option>
                {subject_options}
            </select>
        </form>
    </div>

    <div class="grid">
        <div class="stat">
            <p>Selected Subject</p>
            <h2>{selected_subject.get("name", "No subject") if selected_subject else "No subject"}</h2>
        </div>

        <div class="stat">
            <p>Total Classes</p>
            <h2>{total_classes}</h2>
        </div>

        <div class="stat">
            <p>Present</p>
            <h2>{present_count}</h2>
        </div>

        <div class="stat">
            <p>Absent</p>
            <h2>{absent_count}</h2>
        </div>

        <div class="stat">
            <p>Subject Attendance</p>
            <h2>{percentage}%</h2>
        </div>

        <div class="stat">
            <p>Overall Attendance</p>
            <h2>{overall_percentage}%</h2>
        </div>
    </div>

    <div class="card">
        <h3>Subject Attendance Analysis</h3>

        <div style="max-width:350px; margin:auto;">
            <canvas id="attendanceChart"></canvas>
        </div>

        <p style="text-align:center;">
            Present: {present_count} |
            Absent: {absent_count}
        </p>
    </div>

    <div class="card">
        <h3>Attendance History</h3>

        <table>
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                {history_rows}
            </tbody>
        </table>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        const ctx = document.getElementById("attendanceChart");

        if (ctx) {{
            new Chart(ctx, {{
                type: "pie",
                data: {{
                    labels: ["Present", "Absent"],
                    datasets: [{{
                        data: [{present_count}, {absent_count}],
                        backgroundColor: ["#22c55e", "#ef4444"]
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: "bottom"
                        }}
                    }}
                }}
            }});
        }}
    </script>
    """

    return render_page("Student Dashboard", body)


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@login_required
@role_required("admin")
def admin_dashboard():
    student_count = students.count_documents({})
    teacher_count = teachers.count_documents({})
    subject_count = subjects.count_documents({})
    attendance_count = attendance.count_documents({})

    body = """
    <h1>Admin Dashboard</h1>
    <p>Welcome, {{ session.get('name') }}</p>

    <div class="grid">
        <div class="stat">
            <p>Total Students</p>
            <h2>{{ student_count }}</h2>
        </div>

        <div class="stat">
            <p>Total Teachers</p>
            <h2>{{ teacher_count }}</h2>
        </div>

        <div class="stat">
            <p>Total Subjects</p>
            <h2>{{ subject_count }}</h2>
        </div>

        <div class="stat">
            <p>Attendance Records</p>
            <h2>{{ attendance_count }}</h2>
        </div>
    </div>

    <div class="card">
        <h3>Manage System</h3>
        <a class="btn" href="{{ url_for('manage_students') }}">Manage Students</a>
        <a class="btn" href="{{ url_for('manage_teachers') }}">Manage Teachers</a>
        <a class="btn" href="{{ url_for('manage_subjects') }}">Manage Subjects</a>
        <a class="btn" href="{{ url_for('admin_reports') }}">Attendance Reports</a>
        <a class="btn" href="{{ url_for('manage_attendance') }}">Mark Attendance</a>
    </div>
    """

    return render_page(
        "Admin Dashboard",
        body,
        student_count=student_count,
        teacher_count=teacher_count,
        subject_count=subject_count,
        attendance_count=attendance_count
    )


# =========================================================
# ADMIN: STUDENTS — ADD, EDIT, DELETE
# =========================================================

@app.route("/admin/students", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_students():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        usn = request.form.get("usn", "").strip().upper()
        password = "Student@123"

        if not name or not email or not usn:
            flash("Please fill in all fields.")

        elif users.find_one({"email": email}):
            flash("This email already exists.")

        elif students.find_one({"usn": usn}):
            flash("This USN already exists.")

        else:
            student_result = students.insert_one({
                "name": name,
                "email": email,
                "usn": usn
            })

            users.insert_one({
                "name": name,
                "email": email,
                "password": generate_password_hash(password),
                "role": "student",
                "student_id": str(student_result.inserted_id)
            })

            flash("Student added successfully.")

        return redirect(url_for("manage_students"))

    student_list = list(students.find().sort("name", 1))

    body = """
    <h1>Manage Students</h1>

    <div class="card">
        <h3>Add Student</h3>

        <form method="POST">
            <input name="name" placeholder="Student name" required>
            <input type="email" name="email" placeholder="Student email" required>
            <input name="usn" placeholder="USN" required>
            <button type="submit">Add Student</button>
        </form>

        <p class="muted">Default student password: Student@123</p>
    </div>

    <div class="card">
        <h3>Student List</h3>

        <table>
            <tr>
                <th>Name</th>
                <th>Email</th>
                <th>USN</th>
                <th>Actions</th>
            </tr>

            {% for student in student_list %}
            <tr>
                <td>{{ student.get('name', '') }}</td>
                <td>{{ student.get('email', '') }}</td>
                <td>{{ student.get('usn', '') }}</td>

                <td>
                    <div class="actions">
                        <a class="btn"
                           href="{{ url_for('edit_student', student_id=student['_id']) }}">
                           Edit
                        </a>

                        <form method="POST"
                              action="{{ url_for('delete_student', student_id=student['_id']) }}"
                              onsubmit="return confirm('Delete this student?')">
                            <button class="danger" type="submit">Delete</button>
                        </form>
                    </div>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    """

    return render_page(
        "Manage Students",
        body,
        student_list=student_list
    )


@app.route("/admin/students/edit/<student_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_student(student_id):
    try:
        student = students.find_one({"_id": ObjectId(student_id)})
    except Exception:
        student = None

    if not student:
        flash("Student not found.")
        return redirect(url_for("manage_students"))

    old_email = student.get("email", "").strip().lower()
    linked_user = users.find_one({
        "email": old_email,
        "role": "student"
    })

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        usn = request.form.get("usn", "").strip().upper()

        if not name or not email or not usn:
            flash("Please fill in all student details.")

        elif students.find_one({
            "usn": usn,
            "_id": {"$ne": student["_id"]}
        }):
            flash("Another student already has this USN.")

        elif users.find_one({
            "email": email,
            "role": "student",
            **({"_id": {"$ne": linked_user["_id"]}} if linked_user else {})
        }):
            flash("Another student login already uses this email.")

        else:
            students.update_one(
                {"_id": student["_id"]},
                {"$set": {
                    "name": name,
                    "email": email,
                    "usn": usn
                }}
            )

            if linked_user:
                users.update_one(
                    {"_id": linked_user["_id"]},
                    {"$set": {
                        "name": name,
                        "email": email
                    }}
                )

            flash("Student details updated successfully.")
            return redirect(url_for("manage_students"))

    body = """
    <h1>Edit Student</h1>

    <div class="card">
        <form method="POST">
            <label>Name</label>
            <input name="name" value="{{ student.get('name', '') }}" required>

            <label>Email</label>
            <input type="email" name="email"
                   value="{{ student.get('email', '') }}" required>

            <label>USN</label>
            <input name="usn" value="{{ student.get('usn', '') }}" required>

            <button type="submit">Save Changes</button>
            <a class="btn secondary" href="{{ url_for('manage_students') }}">Cancel</a>
        </form>
    </div>
    """

    return render_page(
        "Edit Student",
        body,
        student=student
    )


@app.route("/admin/students/delete/<student_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_student(student_id):
    try:
        student = students.find_one({"_id": ObjectId(student_id)})

        if student:
            students.delete_one({"_id": student["_id"]})

            users.delete_one({
                "email": student.get("email", "").lower(),
                "role": "student"
            })

            attendance.delete_many({
                "student_id": str(student["_id"])
            })

            flash("Student deleted.")
        else:
            flash("Student not found.")

    except Exception:
        flash("Invalid student ID.")

    return redirect(url_for("manage_students"))


# =========================================================
# ADMIN: SUBJECTS — ADD, DELETE
# =========================================================

@app.route("/admin/subjects", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_subjects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()

        if not name or not code:
            flash("Enter both subject name and subject code.")

        elif subjects.find_one({
            "$or": [
                {"name": name},
                {"code": code}
            ]
        }):
            flash("Subject name or code already exists.")

        else:
            subjects.insert_one({
                "name": name,
                "code": code
            })

            flash("Subject added successfully.")

        return redirect(url_for("manage_subjects"))

    subject_list = list(subjects.find().sort("name", 1))

    body = """
    <h1>Manage Subjects</h1>

    <div class="card">
        <h3>Add Subject</h3>

        <form method="POST">
            <label>Subject Name</label>
            <input name="name" required>

            <label>Subject Code</label>
            <input name="code" required>

            <button type="submit">Add Subject</button>
        </form>
    </div>

    <div class="card">
        <h3>Subject List</h3>

        <table>
            <tr>
                <th>Subject Name</th>
                <th>Code</th>
                <th>Action</th>
            </tr>

            {% for subject in subject_list %}
            <tr>
                <td>{{ subject.get('name', '') }}</td>
                <td>{{ subject.get('code', '') }}</td>
                <td>
                    <form method="POST"
                          action="{{ url_for('delete_subject', subject_id=subject['_id']) }}"
                          onsubmit="return confirm('Delete this subject?')">
                        <button class="danger" type="submit">Delete</button>
                    </form>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    """

    return render_page(
        "Manage Subjects",
        body,
        subject_list=subject_list
    )


@app.route("/admin/subjects/delete/<subject_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_subject(subject_id):
    try:
        subject = subjects.find_one({"_id": ObjectId(subject_id)})

        if subject:
            subject_id_string = str(subject["_id"])
            subject_name = subject.get("name", "")

            assigned_teacher = teachers.find_one({
                "$or": [
                    {"assigned_subject_id": subject_id_string},
                    {"assigned_subjects.subject_id": subject_id_string}
                ]
            })

            if assigned_teacher:
                flash("This subject is assigned to a teacher. Reassign that teacher first.")
                return redirect(url_for("manage_subjects"))

            subjects.delete_one({"_id": subject["_id"]})

            attendance.delete_many({"subject_id": subject_id_string})
            attendance.delete_many({"subject": subject_name})

            flash("Subject deleted.")

        else:
            flash("Subject not found.")

    except Exception:
        flash("Invalid subject ID.")

    return redirect(url_for("manage_subjects"))


# =========================================================
# ADMIN: TEACHERS — ADD, EDIT, DELETE
# =========================================================

@app.route("/admin/teachers", methods=["GET", "POST"])
@login_required
@role_required("admin")
def manage_teachers():
    subject_list = list(subjects.find().sort("name", 1))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        subject_id = request.form.get("subject_id", "").strip()
        password = "Teacher@123"

        if not name or not email or not subject_id:
            flash("Fill in all fields and select a subject.")
            return redirect(url_for("manage_teachers"))

        if users.find_one({"email": email}):
            flash("This email already exists.")
            return redirect(url_for("manage_teachers"))

        try:
            selected_subject = subjects.find_one({
                "_id": ObjectId(subject_id)
            })
        except Exception:
            selected_subject = None

        if not selected_subject:
            flash("Select a valid subject.")
            return redirect(url_for("manage_teachers"))

        already_assigned = teachers.find_one({
            "assigned_subject_id": str(selected_subject["_id"])
        })

        if already_assigned:
            flash("This subject is already assigned to another teacher.")
            return redirect(url_for("manage_teachers"))

        teachers.insert_one({
            "name": name,
            "email": email,
            "assigned_subject_id": str(selected_subject["_id"]),
            "assigned_subject_name": selected_subject.get("name", ""),
            "assigned_subject_code": selected_subject.get("code", "")
        })

        users.insert_one({
            "name": name,
            "email": email,
            "password": generate_password_hash(password),
            "role": "teacher"
        })

        flash("Teacher added and subject assigned successfully.")
        return redirect(url_for("manage_teachers"))

    teacher_list = list(teachers.find().sort("name", 1))

    body = """
    <h1>Manage Teachers</h1>

    <div class="card">
        <h3>Add Teacher and Assign Subject</h3>

        <form method="POST">
            <label>Teacher Name</label>
            <input name="name" required>

            <label>Teacher Email</label>
            <input type="email" name="email" required>

            <label>Assign Subject</label>
            <select name="subject_id" required>
                <option value="">Select subject</option>
                {% for subject in subject_list %}
                <option value="{{ subject['_id'] }}">
                    {{ subject.get('name', '') }} — {{ subject.get('code', '') }}
                </option>
                {% endfor %}
            </select>

            <button type="submit">Add Teacher</button>
        </form>

        <p class="muted">Default teacher password: Teacher@123</p>
    </div>

    <div class="card">
        <h3>Teacher List</h3>

        <table>
            <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Assigned Subject</th>
                <th>Code</th>
                <th>Actions</th>
            </tr>

            {% for teacher in teacher_list %}
            <tr>
                <td>{{ teacher.get('name', '') }}</td>
                <td>{{ teacher.get('email', '') }}</td>
                <td>{{ teacher.get('assigned_subject_name', 'Not assigned') }}</td>
                <td>{{ teacher.get('assigned_subject_code', '—') }}</td>

                <td>
                    <div class="actions">
                        <a class="btn"
                           href="{{ url_for('edit_teacher', teacher_id=teacher['_id']) }}">
                           Edit
                        </a>

                        <form method="POST"
                              action="{{ url_for('delete_teacher', teacher_id=teacher['_id']) }}"
                              onsubmit="return confirm('Delete this teacher?')">
                            <button class="danger" type="submit">Delete</button>
                        </form>
                    </div>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    """

    return render_page(
        "Manage Teachers",
        body,
        subject_list=subject_list,
        teacher_list=teacher_list
    )


@app.route("/admin/teachers/edit/<teacher_id>", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_teacher(teacher_id):
    try:
        teacher = teachers.find_one({"_id": ObjectId(teacher_id)})
    except Exception:
        teacher = None

    if not teacher:
        flash("Teacher not found.")
        return redirect(url_for("manage_teachers"))

    old_email = teacher.get("email", "").strip().lower()

    linked_user = users.find_one({
        "email": old_email,
        "role": "teacher"
    })

    subject_list = list(subjects.find().sort("name", 1))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        subject_id = request.form.get("subject_id", "").strip()

        if not name or not email or not subject_id:
            flash("Please fill in the teacher name, email, and subject.")

        elif users.find_one({
            "email": email,
            **({"_id": {"$ne": linked_user["_id"]}} if linked_user else {})
        }):
            flash("This email is already used by another login account.")

        else:
            try:
                selected_subject = subjects.find_one({
                    "_id": ObjectId(subject_id)
                })
            except Exception:
                selected_subject = None

            if not selected_subject:
                flash("Please select a valid subject.")

            else:
                other_teacher = teachers.find_one({
                    "assigned_subject_id": str(selected_subject["_id"]),
                    "_id": {"$ne": teacher["_id"]}
                })

                if other_teacher:
                    flash("This subject is already assigned to another teacher.")

                else:
                    teachers.update_one(
                        {"_id": teacher["_id"]},
                        {"$set": {
                            "name": name,
                            "email": email,
                            "assigned_subject_id": str(selected_subject["_id"]),
                            "assigned_subject_name": selected_subject.get("name", ""),
                            "assigned_subject_code": selected_subject.get("code", "")
                        }}
                    )

                    if linked_user:
                        users.update_one(
                            {"_id": linked_user["_id"]},
                            {"$set": {
                                "name": name,
                                "email": email
                            }}
                        )

                    flash("Teacher details updated successfully.")
                    return redirect(url_for("manage_teachers"))

    body = """
    <h1>Edit Teacher</h1>

    <div class="card">
        <form method="POST">
            <label>Teacher Name</label>
            <input name="name" value="{{ teacher.get('name', '') }}" required>

            <label>Teacher Email</label>
            <input type="email" name="email"
                   value="{{ teacher.get('email', '') }}" required>

            <label>Assigned Subject</label>
            <select name="subject_id" required>
                <option value="">Select subject</option>

                {% for subject in subject_list %}
                <option value="{{ subject['_id'] }}"
                    {% if teacher.get('assigned_subject_id') == (subject['_id'] | string) %}selected{% endif %}>
                    {{ subject.get('name', '') }} — {{ subject.get('code', '') }}
                </option>
                {% endfor %}
            </select>

            <button type="submit">Save Changes</button>
            <a class="btn secondary" href="{{ url_for('manage_teachers') }}">Cancel</a>
        </form>
    </div>
    """

    return render_page(
        "Edit Teacher",
        body,
        teacher=teacher,
        subject_list=subject_list
    )


@app.route("/admin/teachers/delete/<teacher_id>", methods=["POST"])
@login_required
@role_required("admin")
def delete_teacher(teacher_id):
    try:
        teacher = teachers.find_one({"_id": ObjectId(teacher_id)})

        if teacher:
            teachers.delete_one({"_id": teacher["_id"]})

            users.delete_one({
                "email": teacher.get("email", "").lower(),
                "role": "teacher"
            })

            flash("Teacher deleted.")

        else:
            flash("Teacher not found.")

    except Exception:
        flash("Invalid teacher ID.")

    return redirect(url_for("manage_teachers"))


# =========================================================
# TEACHER DASHBOARD
# =========================================================

@app.route("/teacher")
@login_required
@role_required("teacher")
def teacher_dashboard():
    teacher = current_teacher()

    if not teacher:
        return render_page(
            "Teacher Not Found",
            "<div class='card'><h2>Teacher record not found. Contact admin.</h2></div>"
        )

    assigned_subject_id = teacher.get("assigned_subject_id")

    if not assigned_subject_id:
        return render_page(
            "Subject Not Assigned",
            "<div class='card'><h2>No subject assigned. Contact admin.</h2></div>"
        )

    try:
        assigned_subject = subjects.find_one({
            "_id": ObjectId(assigned_subject_id)
        })
    except Exception:
        assigned_subject = None

    if not assigned_subject:
        return render_page(
            "Subject Not Found",
            "<div class='card'><h2>Your assigned subject was not found.</h2></div>"
        )

    body = """
    <h1>Teacher Dashboard</h1>

    <p>Welcome, <strong>{{ teacher.get('name', '') }}</strong></p>

    <div class="card">
        <h3>Your Assigned Subject</h3>

        <h2>{{ assigned_subject.get('name', '') }}</h2>

        <p>
            Subject Code:
            <strong>{{ assigned_subject.get('code', '') }}</strong>
        </p>

        <a class="btn" href="{{ url_for('manage_attendance') }}">
            Mark Attendance
        </a>
    </div>
    """

    return render_page(
        "Teacher Dashboard",
        body,
        teacher=teacher,
        assigned_subject=assigned_subject
    )

# =========================================================
# ATTENDANCE — PRESENT / ABSENT + EDIT EXISTING ATTENDANCE
# =========================================================

@app.route("/attendance", methods=["GET", "POST"])
@login_required
@role_required("admin", "teacher")
def manage_attendance():

    student_list = list(students.find().sort("name", 1))
    selected_date = request.values.get("date", str(date.today()))
    subject_list = list(subjects.find().sort("name", 1))
    selected_subject = None

    # -----------------------------------------------------
    # GET THE SUBJECT
    # -----------------------------------------------------

    if session.get("role") == "teacher":

        teacher = current_teacher()

        if not teacher or not teacher.get("assigned_subject_id"):
            flash("No subject assigned to your account.")
            return redirect(url_for("teacher_dashboard"))

        try:
            selected_subject = subjects.find_one({
                "_id": ObjectId(teacher["assigned_subject_id"])
            })
        except Exception:
            selected_subject = None

        if not selected_subject:
            flash("Assigned subject not found.")
            return redirect(url_for("teacher_dashboard"))

    else:
        subject_id = request.values.get("subject_id", "").strip()

        if subject_id:
            try:
                selected_subject = subjects.find_one({
                    "_id": ObjectId(subject_id)
                })
            except Exception:
                selected_subject = None

    # -----------------------------------------------------
    # SAVE OR UPDATE ATTENDANCE
    # -----------------------------------------------------

    if request.method == "POST":

        if not selected_subject:
            flash("Please select a subject.")
            return redirect(url_for("manage_attendance"))

        subject_name = selected_subject.get("name", "")
        subject_code = selected_subject.get("code", "")
        subject_id_string = str(selected_subject["_id"])

        # STEP 1: Validate every student's status first.
        # Nothing will be saved if even one student is unmarked.
        attendance_data = {}

        for student in student_list:

            student_id = str(student["_id"])
            status = request.form.get(f"status_{student_id}", "")
            print("ADMIN ATTENDANCE UPDATE:", student_id, status)

            if status not in ["Present", "Absent"]:

                flash(
                    f"Please mark attendance for every student. "
                    f"Not marked: {student.get('name', '')}"
                )

                if session.get("role") == "teacher":
                    return redirect(url_for(
                        "manage_attendance",
                        date=selected_date
                    ))

                return redirect(url_for(
                    "manage_attendance",
                    subject_id=subject_id_string,
                    date=selected_date
                ))

            attendance_data[student_id] = status



        # STEP 2: Save only after all students are validated.
        # Existing records are updated; new records are inserted.
        for student in student_list:

            student_id = str(student["_id"])
            status = attendance_data[student_id]

            attendance.update_one(
                {
                    "student_id": student_id,
                    "subject_id": subject_id_string,
                    "date": selected_date
                },
                {
                    "$set": {
                        "student_id": student_id,
                        "student_name": student.get("name", ""),
                        "usn": student.get("usn", ""),
                        "subject": subject_name,
                        "subject_code": subject_code,
                        "subject_id": subject_id_string,
                        "date": selected_date,
                        "status": status,
                        "marked_by": session.get("email", "")
                    }
                },
                upsert=True
            )

        flash("Attendance saved or updated successfully.")

        if session.get("role") == "teacher":
            return redirect(url_for(
                "manage_attendance",
                date=selected_date
            ))

        return redirect(url_for(
            "manage_attendance",
            subject_id=subject_id_string,
            date=selected_date
        ))


    # -----------------------------------------------------
    # LOAD EXISTING ATTENDANCE FOR EDITING
    # -----------------------------------------------------

    status_by_student = {}

    if selected_subject:

        subject_id_string = str(selected_subject["_id"])

        existing_records = attendance.find({
            "subject_id": subject_id_string,
            "date": selected_date
        })

        for record in existing_records:

            student_id = record.get("student_id", "")
            status = record.get("status", "")

            status_by_student[student_id] = status

    # -----------------------------------------------------
    # ATTENDANCE PAGE HTML
    # -----------------------------------------------------

    body = """
    <h1>Mark Attendance</h1>

    <div class="card">

        {% if session.get('role') == 'admin' %}

        <form method="GET">

            <label>Select Subject</label>

            <select name="subject_id" required>
                <option value="">Select subject</option>

                {% for subject in subject_list %}
                <option
                    value="{{ subject['_id'] }}"
                    {% if selected_subject and subject['_id'] == selected_subject['_id'] %}
                        selected
                    {% endif %}
                >
                    {{ subject.get('name', '') }} —
                    {{ subject.get('code', '') }}
                </option>
                {% endfor %}

            </select>

            <label>Date</label>

            <input
                type="date"
                name="date"
                value="{{ selected_date }}"
                required
            >

            <button type="submit">Load Students</button>

        </form>

        {% else %}

        <h3>
            {{ selected_subject.get('name', '') }} —
            {{ selected_subject.get('code', '') }}
        </h3>

        <form method="GET">

            <label>Attendance Date</label>

            <input
                type="date"
                name="date"
                value="{{ selected_date }}"
                required
            >

            <button type="submit">Load Date</button>

        </form>

        {% endif %}

    </div>


    {% if selected_subject %}

    <div class="card">

        <h3>Student Attendance — {{ selected_date }}</h3>

        {% if status_by_student %}
            <p class="muted">
                Existing attendance loaded. You can change any status and save again.
            </p>
        {% else %}
            <p class="muted">
                New attendance. Select Present or Absent for every student.
            </p>
        {% endif %}

        <form method="POST">

            <input
                type="hidden"
                name="date"
                value="{{ selected_date }}"
            >

            {% if session.get('role') == 'admin' %}

            <input
                type="hidden"
                name="subject_id"
                value="{{ selected_subject['_id'] }}"
            >

            {% endif %}

            <table>

                <tr>
                    <th>USN</th>
                    <th>Student Name</th>
                    <th>Present</th>
                    <th>Absent</th>
                    <th>History</th>
                </tr>

                {% for student in student_list %}

                {% set sid = student['_id'] | string %}

                <tr>

                    <td>{{ student.get('usn', '') }}</td>

                    <td>{{ student.get('name', '') }}</td>

                    <td>
                        <label class="attendance-choice">

                            <input
                                type="radio"
                                name="status_{{ sid }}"
                                value="Present"
                                {% if status_by_student.get(sid) == 'Present' %}
                                    checked
                                {% endif %}
                                required
                            >

                            Present

                        </label>
                    </td>

                    <td>
                        <label class="attendance-choice">

                            <input
                                type="radio"
                                name="status_{{ sid }}"
                                value="Absent"
                                {% if status_by_student.get(sid) == 'Absent' %}
                                    checked
                                {% endif %}
                                required
                            >

                            Absent

                        </label>
                    </td>

                    <td>

                        {% if session.get('role') == 'teacher' %}

                        <a
                            class="btn"
                            href="{{ url_for(
                                'teacher_student_history',
                                student_id=sid
                            ) }}"
                        >
                            View History
                        </a>

                        {% else %}

                        <span class="muted">Admin</span>

                        {% endif %}

                    </td>

                </tr>

                {% endfor %}

            </table>

<button type="submit">
    Save / Update Attendance
</button>

</form>

{% if session.get('role') == 'admin' %}

<form
    method="POST"
    action="{{ url_for('delete_attendance') }}"
    onsubmit="return confirm('Are you sure you want to delete all attendance for this subject and date?');"
>

    <input
        type="hidden"
        name="subject_id"
        value="{{ selected_subject['_id'] }}"
    >

    <input
        type="hidden"
        name="date"
        value="{{ selected_date }}"
    >

    <button type="submit" class="btn btn-danger">
        Delete Marked Attendance
    </button>

</form>

{% endif %}

{% if session.get('role') == 'admin' %}

</form>

<form
    method="POST"
    action="{{ url_for('delete_attendance') }}"
    onsubmit="return confirm(
        'Are you sure you want to delete all attendance for this subject and date?'
    );"

</form>

{% else %}

</form>

{% endif %}

        </form>

    </div>

    {% endif %}
    """

    return render_page(
        "Mark Attendance",
        body,
        subject_list=subject_list,
        selected_subject=selected_subject,
        selected_date=selected_date,
        student_list=student_list,
        status_by_student=status_by_student
    )

@app.route("/attendance/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_attendance():

    subject_id = request.form.get("subject_id", "").strip()
    selected_date = request.form.get("date", "").strip()

    if not subject_id or not selected_date:
        flash("Please select a subject and date.")
        return redirect(url_for("manage_attendance"))

    try:
        subject = subjects.find_one({
            "_id": ObjectId(subject_id)
        })
    except Exception:
        subject = None

    if not subject:
        flash("Subject not found.")
        return redirect(url_for("manage_attendance"))

    result = attendance.delete_many({
        "subject_id": subject_id,
        "date": selected_date
    })

    flash(
        f"Deleted {result.deleted_count} attendance record(s) "
        f"for {subject.get('name', '')} on {selected_date}."
    )

    return redirect(url_for(
        "manage_attendance",
        subject_id=subject_id,
        date=selected_date
    ))

@app.route("/attendance-reports")
@login_required
@role_required("admin")
def attendance_reports():

    subject_list = list(subjects.find().sort("name", 1))
    selected_subject = None

    subject_id = request.args.get("subject_id", "").strip()
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")

    report_records = []
    student_reports = []

    if subject_id and start_date and end_date:

        try:
            selected_subject = subjects.find_one({
                "_id": ObjectId(subject_id)
            })
        except Exception:
            selected_subject = None

        if selected_subject:

            report_records = list(attendance.find({
                "subject_id": subject_id,
                "date": {
                    "$gte": start_date,
                    "$lte": end_date
                }
            }).sort("date", 1))

            report_data = {}

            for record in report_records:

                student_id = record.get("student_id", "")

                if student_id not in report_data:
                    report_data[student_id] = {
                        "student_name": record.get("student_name", ""),
                        "usn": record.get("usn", ""),
                        "present": 0,
                        "absent": 0
                    }

                if record.get("status") == "Present":
                    report_data[student_id]["present"] += 1

                elif record.get("status") == "Absent":
                    report_data[student_id]["absent"] += 1

            for student_id, data in report_data.items():

                total_classes = data["present"] + data["absent"]

                percentage = (
                    (data["present"] / total_classes) * 100
                    if total_classes > 0 else 0
                )

                student_reports.append({
                    "student_name": data["student_name"],
                    "usn": data["usn"],
                    "present": data["present"],
                    "absent": data["absent"],
                    "total_classes": total_classes,
                    "percentage": round(percentage, 2)
                })

            student_reports.sort(key=lambda x: x["student_name"].lower())

    body = """
    <h1>Attendance Reports</h1>

    <div class="card">

        <form method="GET">

            <label>Select Subject</label>

            <select name="subject_id" required>
                <option value="">Select subject</option>

                {% for subject in subject_list %}
                <option
                    value="{{ subject['_id'] }}"
                    {% if selected_subject and subject['_id'] == selected_subject['_id'] %}
                        selected
                    {% endif %}
                >
                    {{ subject.get('name', '') }} —
                    {{ subject.get('code', '') }}
                </option>
                {% endfor %}
            </select>

            <label>Start Date</label>
            <input
                type="date"
                name="start_date"
                value="{{ start_date }}"
                required
            >

            <label>End Date</label>
            <input
                type="date"
                name="end_date"
                value="{{ end_date }}"
                required
            >

            <button type="submit">Generate Report</button>

        </form>

    </div>

    {% if selected_subject %}

    <div class="card">

        <h3>
            {{ selected_subject.get('name', '') }}
            — {{ selected_subject.get('code', '') }}
        </h3>

        <p class="muted">
            Report period: {{ start_date }} to {{ end_date }}
        </p>

        {% if student_reports %}

        <table>

            <tr>
                <th>USN</th>
                <th>Student Name</th>
                <th>Present</th>
                <th>Absent</th>
                <th>Total Classes</th>
                <th>Attendance %</th>
            </tr>

            {% for student in student_reports %}

            <tr>
                <td>{{ student.usn }}</td>
                <td>{{ student.student_name }}</td>
                <td>{{ student.present }}</td>
                <td>{{ student.absent }}</td>
                <td>{{ student.total_classes }}</td>
                <td>{{ student.percentage }}%</td>
            </tr>

            {% endfor %}

        </table>

        {% else %}

        <p>No attendance records found for this subject and date range.</p>

        {% endif %}

    </div>

    {% endif %}
    """

    return render_page(
        "Attendance Reports",
        body,
        subject_list=subject_list,
        selected_subject=selected_subject,
        start_date=start_date,
        end_date=end_date,
        student_reports=student_reports
    )

# =========================================================
# TEACHER: STUDENT ATTENDANCE HISTORY
# =========================================================

@app.route("/teacher/student-history/<student_id>")
@login_required
@role_required("teacher")
def teacher_student_history(student_id):
    try:
        student = students.find_one({
            "_id": ObjectId(student_id)
        })
    except InvalidId:
        student = None

    if not student:
        flash("Student not found.")
        return redirect(url_for("teacher_dashboard"))

    teacher = current_teacher()

    if not teacher or not teacher.get("assigned_subject_id"):
        flash("No subject assigned to your account.")
        return redirect(url_for("teacher_dashboard"))

    try:
        subject = subjects.find_one({
            "_id": ObjectId(teacher["assigned_subject_id"])
        })
    except InvalidId:
        subject = None

    if not subject:
        flash("Assigned subject not found.")
        return redirect(url_for("teacher_dashboard"))

    subject_id_string = str(subject["_id"])

    records = list(attendance.find({
        "student_id": str(student["_id"]),
        "subject_id": subject_id_string
    }).sort("date", -1))

    total_classes = len(records)

    present_count = sum(
        1 for record in records
        if record.get("status", "").lower() == "present"
    )

    absent_count = sum(
        1 for record in records
        if record.get("status", "").lower() == "absent"
    )

    percentage = (
        round((present_count / total_classes) * 100, 2)
        if total_classes else 0
    )

    

    body = """
    <h1>Student Attendance History</h1>

    <div class="card">
        <h3>Student Details</h3>

        <p><strong>Name:</strong> {{ student.get('name', '') }}</p>
        <p><strong>USN:</strong> {{ student.get('usn', 'Not available') }}</p>
        <p><strong>Subject:</strong> {{ subject.get('name', '') }}</p>
        <p><strong>Subject Code:</strong> {{ subject.get('code', '') }}</p>
    </div>

    <div class="grid">
        <div class="stat">
            <p>Total Classes</p>
            <h2>{{ total_classes }}</h2>
        </div>

        <div class="stat">
            <p>Present</p>
            <h2>{{ present_count }}</h2>
        </div>

        <div class="stat">
            <p>Absent</p>
            <h2>{{ absent_count }}</h2>
        </div>

        <div class="stat">
            <p>Attendance Percentage</p>
            <h2>{{ percentage }}%</h2>
        </div>
    </div>

    <div class="card">
        <h3>Date-wise Attendance</h3>

        <table>
            <tr>
                <th>Date</th>
                <th>Status</th>
                <th>Action</th>
            </tr>

        {% for record in records %}
<tr>
    <td>{{ record.get('date', '') }}</td>
    <td>{{ record.get('status', '') }}</td>
    <td>
        <a class="btn"
           href="{{ url_for('manage_attendance', date=record.get('date', '')) }}">
            Edit
        </a>
    </td>
</tr>
{% else %}
<tr>
    <td colspan="3">No attendance records found.</td>
</tr>
{% endfor %}

        <br>

        <a class="btn secondary" href="{{ url_for('teacher_dashboard') }}">
            Back to Teacher Dashboard
        </a>

        <a class="btn" href="{{ url_for('manage_attendance') }}">
            Back to Mark Attendance
        </a>
    </div>
    """

    return render_page(
        "Student Attendance History",
        body,
        student=student,
        subject=subject,
        records=records,
        total_classes=total_classes,
        present_count=present_count,
        absent_count=absent_count,
        percentage=percentage
    )

# =========================================================
# ADMIN ATTENDANCE REPORTS
# =========================================================

@app.route("/admin/reports")
@login_required
@role_required("admin")
def admin_reports():
    selected_subject = request.args.get("subject", "")
    selected_date = request.args.get("date", "")

    query = {}

    if selected_subject:
        query["subject"] = selected_subject

    if selected_date:
        query["date"] = selected_date

    records = list(attendance.find(query).sort("date", -1))
    subject_list = list(subjects.find().sort("name", 1))

    body = """
    <h1>Attendance Reports</h1>

    <div class="card">
        <form method="GET">
            <label>Subject</label>

            <select name="subject">
                <option value="">All Subjects</option>

                {% for subject in subject_list %}
                <option value="{{ subject.get('name', '') }}"
                    {% if subject.get('name') == selected_subject %}selected{% endif %}>
                    {{ subject.get('name', '') }} — {{ subject.get('code', '') }}
                </option>
                {% endfor %}
            </select>

            <label>Date</label>
            <input type="date" name="date" value="{{ selected_date }}">

            <button type="submit">Filter</button>
        </form>
    </div>

    <div class="card">
        <table>
            <tr>
                <th>Student</th>
                <th>USN</th>
                <th>Subject</th>
                <th>Code</th>
                <th>Date</th>
                <th>Status</th>
            </tr>

            {% for record in records %}
            <tr>
                <td>{{ record.get('student_name', '') }}</td>
                <td>{{ record.get('usn', '') }}</td>
                <td>{{ record.get('subject', '') }}</td>
                <td>{{ record.get('subject_code', '') }}</td>
                <td>{{ record.get('date', '') }}</td>
                <td>{{ record.get('status', '') }}</td>
            </tr>
            {% endfor %}
        </table>

        {% if not records %}
        <p>No attendance records found.</p>
        {% endif %}
    </div>
    """

    return render_page(
        "Attendance Reports",
        body,
        records=records,
        subject_list=subject_list,
        selected_subject=selected_subject,
        selected_date=selected_date
    )


# =========================================================
# RUN FLASK
# =========================================================

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)