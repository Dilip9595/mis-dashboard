import os
import sqlite3
import csv
import io
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, Response, session

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mis_portal_secret_2026")

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
DB_NAME = "mis_data.db"

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            department TEXT NOT NULL,
            designation TEXT NOT NULL,
            salary INTEGER NOT NULL,
            status TEXT DEFAULT 'Active'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id INTEGER NOT NULL,
            att_date TEXT NOT NULL,
            status TEXT NOT NULL,
            UNIQUE(emp_id, att_date),
            FOREIGN KEY (emp_id) REFERENCES employees(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form["username"] == ADMIN_USER and request.form["password"] == ADMIN_PASS:
            session["logged_in"] = True
            return redirect(url_for("home"))
        else:
            error = "Galat Username ya Password!"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    conn = get_db()
    total_emp = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    active_emp = conn.execute("SELECT COUNT(*) FROM employees WHERE status='Active'").fetchone()[0]
    dept_rows = conn.execute("SELECT department, COUNT(*) as count FROM employees GROUP BY department").fetchall()
    conn.close()

    dept_labels = [row["department"] for row in dept_rows]
    dept_counts = [row["count"] for row in dept_rows]
    total_depts = len(dept_labels)

    return render_template(
        "index.html",
        total_emp=total_emp,
        active_emp=active_emp,
        total_depts=total_depts,
        dept_labels=dept_labels,
        dept_counts=dept_counts
    )

@app.route("/employees", methods=["GET", "POST"])
@login_required
def employees():
    conn = get_db()
    if request.method == "POST":
        conn.execute(
            "INSERT INTO employees (name, department, designation, salary, status) VALUES (?, ?, ?, ?, ?)",
            (
                request.form["name"],
                request.form["department"],
                request.form["designation"],
                request.form["salary"],
                request.form["status"]
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("employees"))

    search = request.args.get("search", "")
    if search:
        emp_list = conn.execute(
            "SELECT * FROM employees WHERE name LIKE ? OR department LIKE ? ORDER BY id DESC",
            (f"%{search}%", f"%{search}%")
        ).fetchall()
    else:
        emp_list = conn.execute("SELECT * FROM employees ORDER BY id DESC").fetchall()

    conn.close()
    return render_template("employees.html", employees=emp_list, search=search)

@app.route("/delete/<int:emp_id>")
@login_required
def delete_employee(emp_id):
    conn = get_db()
    conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("employees"))

@app.route("/attendance", methods=["GET", "POST"])
@login_required
def attendance():
    conn = get_db()
    today = request.args.get("date", str(date.today()))

    if request.method == "POST":
        att_date = request.form["att_date"]
        emp_id = request.form["emp_id"]
        status = request.form["status"]
        conn.execute("""
            INSERT INTO attendance (emp_id, att_date, status)
            VALUES (?, ?, ?)
            ON CONFLICT(emp_id, att_date) DO UPDATE SET status=excluded.status
        """, (emp_id, att_date, status))
        conn.commit()
        conn.close()
        return redirect(url_for("attendance", date=att_date))

    emp_list = conn.execute("""
        SELECT e.id, e.name, e.department, a.status as att_status
        FROM employees e
        LEFT JOIN attendance a ON e.id = a.emp_id AND a.att_date = ?
        ORDER BY e.name
    """, (today,)).fetchall()
    conn.close()
    return render_template("attendance.html", employees=emp_list, today=today)

@app.route("/reports")
@login_required
def reports():
    conn = get_db()
    dept_summary = conn.execute("""
        SELECT department, COUNT(*) as emp_count, SUM(salary) as total_salary, ROUND(AVG(salary), 0) as avg_salary
        FROM employees
        GROUP BY department
    """).fetchall()
    conn.close()
    return render_template("reports.html", dept_summary=dept_summary)

@app.route("/export/employees")
@login_required
def export_employees():
    conn = get_db()
    rows = conn.execute("SELECT id, name, department, designation, salary, status FROM employees").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Department", "Designation", "Salary", "Status"])
    for r in rows:
        writer.writerow([r["id"], r["name"], r["department"], r["designation"], r["salary"], r["status"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=MIS_Employees_Report.csv"}
    )

@app.route("/export/attendance")
@login_required
def export_attendance():
    conn = get_db()
    rows = conn.execute("""
        SELECT a.att_date, e.name, e.department, a.status
        FROM attendance a
        JOIN employees e ON a.emp_id = e.id
        ORDER BY a.att_date DESC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Employee Name", "Department", "Attendance Status"])
    for r in rows:
        writer.writerow([r["att_date"], r["name"], r["department"], r["status"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=MIS_Attendance_Report.csv"}
    )

if __name__ == "__main__":
    app.run(debug=True)