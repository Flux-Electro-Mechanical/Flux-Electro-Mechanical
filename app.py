from __future__ import annotations

import os
import hashlib
import base64
import secrets
import smtplib
import sqlite3
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path
from uuid import uuid4

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
UPLOAD_DIR = BASE_DIR / "uploads"
MEMBER_DIR = BASE_DIR / "member_files"
PROJECT_IMAGE_DIR = BASE_DIR / "project_images"
STAFF_PHOTO_DIR = BASE_DIR / "staff_photos"
DATABASE_PATH = INSTANCE_DIR / "flux_website.sqlite3"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

ALLOWED_EXTENSIONS = {
    "pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg", "zip", "dwg"
}

PHONE = "+251976141102"
EMAIL = "solutions@fluxelectromechanical.enginner.et"
ADDRESS = "Summit, Addis Ababa, Ethiopia"
WHATSAPP_NUMBER = "251976141102"

DEFAULT_ADMIN_EMAIL = os.getenv("FLUX_ADMIN_EMAIL", EMAIL)
DEFAULT_ADMIN_PASSWORD = os.getenv("FLUX_ADMIN_PASSWORD", "ChangeMe123!")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
MAIL_FROM = os.getenv("MAIL_FROM", DEFAULT_ADMIN_EMAIL)
MAIL_TO = os.getenv("MAIL_TO", DEFAULT_ADMIN_EMAIL)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000")


def create_app() -> Flask:
    app = Flask(__name__, instance_path=str(INSTANCE_DIR))
    app.config.update(
        SECRET_KEY=os.getenv("FLASK_SECRET_KEY", secrets.token_hex(32)),
        DATABASE=str(DATABASE_PATH),
        DATABASE_URL=DATABASE_URL,
        USE_POSTGRES=USE_POSTGRES,
        UPLOAD_FOLDER=str(UPLOAD_DIR),
        MEMBER_FOLDER=str(MEMBER_DIR),
        PROJECT_IMAGE_FOLDER=str(PROJECT_IMAGE_DIR),
        STAFF_PHOTO_FOLDER=str(STAFF_PHOTO_DIR),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    )

    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    MEMBER_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    STAFF_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    ensure_runtime_tables()
    ensure_default_admin()
    ensure_sample_member_resource()
    ensure_sample_project()
    ensure_sample_staff_members()
    ensure_sample_testimonials()
    print(f"Database mode: {'PostgreSQL' if USE_POSTGRES else 'SQLite'}")

    @app.before_request
    def load_current_users():
        g.admin_user = None
        g.client_user = None

        admin_id = session.get("admin_user_id")
        client_id = session.get("client_user_id")

        conn = get_db()
        if admin_id:
            g.admin_user = conn.execute(
                "SELECT id, full_name, email, role, is_active FROM admins WHERE id = %s",
                (admin_id,),
            ).fetchone()

        if client_id:
            g.client_user = conn.execute(
                "SELECT id, full_name, email, phone_number, company_name, is_active FROM clients WHERE id = %s",
                (client_id,),
            ).fetchone()

        if g.admin_user is None and g.client_user is not None:
            admin_match = conn.execute(
                "SELECT id, full_name, email, role, is_active FROM admins WHERE lower(email) = lower(%s)",
                (g.client_user["email"],),
            ).fetchone()
            if admin_match is not None and admin_match["is_active"]:
                g.admin_user = admin_match

    @app.context_processor
    def inject_company_info() -> dict:
        return {
            "company_phone": PHONE,
            "company_email": EMAIL,
            "company_address": ADDRESS,
            "company_whatsapp_url": f"https://wa.me/{WHATSAPP_NUMBER}",
            "current_admin": g.get("admin_user"),
            "current_client": g.get("client_user"),
        }

    @app.route("/")
    def index():
        conn = get_db()
        testimonials = conn.execute(
            """
            SELECT id, client_name, company_name, role_title, testimonial_text, rating, photo_url
            FROM testimonials
            WHERE is_active = 1 AND is_featured = 1
            ORDER BY created_at DESC, id DESC
            LIMIT 6
            """
        ).fetchall()
        return render_template("index.html", testimonials=testimonials)

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/services")
    def services():
        return render_template("services.html")

    @app.route("/projects")
    def projects():
        conn = get_db()
        project_rows = conn.execute(
            """
            SELECT id, title, category, location, summary, image_url, created_at
            FROM projects
            WHERE is_active = 1
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        return render_template("projects.html", projects=project_rows)

    @app.route("/contact")
    def contact():
        return render_template("contact.html")

    @app.route("/thank-you")
    def thank_you():
        return render_template("thank_you.html")

    @app.route("/members")
    @client_login_required
    def members():
        conn = get_db()

        if USE_POSTGRES:
            my_quotes = conn.execute(
                """
                SELECT *
                FROM inquiries
                WHERE client_id = %s
                ORDER BY created_at DESC
                """,
                (session["client_user_id"],),
            ).fetchall()
        else:
            my_quotes = conn.execute(
                """
                SELECT *
                FROM inquiries
                WHERE client_id = ?
                ORDER BY created_at DESC
                """,
                (session["client_user_id"],),
            ).fetchall()

        return render_template("members.html", my_quotes=my_quotes)

    @app.route("/members/profile", methods=["GET", "POST"])
    @client_login_required
    def client_profile():
        conn = get_db()
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            company_name = request.form.get("company_name", "").strip()

            if not full_name:
                flash("Full name is required.", "error")
                return redirect(url_for("client_profile"))

            conn.execute(
                """
                UPDATE clients
                SET full_name = ?, phone_number = ?, company_name = ?
                WHERE id = %s
                """,
                (full_name, phone_number, company_name, g.client_user["id"]),
            )
            conn.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("client_profile"))

        fresh_client = conn.execute(
            """
            SELECT id, full_name, email, phone_number, company_name, is_active
            FROM clients
            WHERE id = %s
            """,
            (g.client_user["id"],),
        ).fetchone()
        return render_template("client_profile.html", client=fresh_client)

    @app.route("/members/register", methods=["GET", "POST"])
    def client_register():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone_number = request.form.get("phone_number", "").strip()
            company_name = request.form.get("company_name", "").strip()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not full_name or not email or not password:
                flash("Full name, email, and password are required.", "error")
                return render_template("client_register.html")

            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("client_register.html")

            if len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
                return render_template("client_register.html")

            conn = get_db()
            existing = conn.execute("SELECT id FROM clients WHERE lower(email) = lower(%s)", (email,)).fetchone()
            if existing:
                flash("That email is already registered. Please log in.", "error")
                return redirect(url_for("client_login"))

            if USE_POSTGRES:
                cursor = conn.execute(
                    """
                    INSERT INTO clients (full_name, email, phone_number, company_name, password_hash, is_active)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    RETURNING id
                    """,
                    (full_name, email, phone_number, company_name, generate_password_hash(password)),
                )
                new_client_id = cursor.fetchone()["id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO clients (full_name, email, phone_number, company_name, password_hash, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (full_name, email, phone_number, company_name, generate_password_hash(password)),
                )
                new_client_id = cursor.lastrowid
            conn.commit()

            session.clear()
            session["client_user_id"] = new_client_id
            flash("Member account created successfully.", "success")
            return redirect(url_for("members"))

        return render_template("client_register.html")

    @app.route("/members/login", methods=["GET", "POST"])
    def client_login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            conn = get_db()

            admin = conn.execute(
                """
                SELECT id, full_name, email, password_hash, role, is_active
                FROM admins
                WHERE lower(email) = %s
                """,
                (email,),
            ).fetchone()

            if admin is not None and admin["is_active"] and admin["password_hash"] and check_password_hash(admin["password_hash"], password):
                session.clear()
                session["admin_user_id"] = admin["id"]

                client_match = conn.execute(
                    """
                    SELECT id
                    FROM clients
                    WHERE lower(email) = %s
                    """,
                    (email,),
                ).fetchone()
                if client_match is not None:
                    session["client_user_id"] = client_match["id"]

                flash("Logged in successfully. Admin privileges enabled.", "success")
                return redirect(url_for("admin_dashboard"))

            client = conn.execute(
                """
                SELECT id, full_name, email, phone_number, company_name, password_hash, is_active
                FROM clients
                WHERE lower(email) = %s
                """,
                (email,),
            ).fetchone()

            if client is None or not client["is_active"] or not check_password_hash(client["password_hash"], password):
                flash("Invalid email or password.", "error")
                return render_template("client_login.html")

            session.clear()
            session["client_user_id"] = client["id"]

            admin_match = conn.execute(
                "SELECT id, email, is_active FROM admins WHERE lower(email) = lower(%s)",
                (client["email"],),
            ).fetchone()
            if admin_match is not None and admin_match["is_active"]:
                session["admin_user_id"] = admin_match["id"]
                flash("Logged in successfully. Admin privileges enabled.", "success")
                return redirect(url_for("admin_dashboard"))

            flash("Logged in successfully.", "success")
            return redirect(url_for("members"))

        return render_template("client_login.html")

    @app.route("/members/logout")
    def client_logout():
        session.pop("client_user_id", None)
        flash("You have been logged out.", "success")
        return redirect(url_for("client_login"))

    @app.route("/members/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            conn = get_db()
            client = conn.execute(
                """
                SELECT id, full_name, email
                FROM clients
                WHERE lower(email) = %s
                """,
                (email,),
            ).fetchone()

            if client is not None:
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat()
                conn.execute(
                    """
                    INSERT INTO password_reset_tokens (client_id, token, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (client["id"], token, expires_at),
                )
                conn.commit()
                send_password_reset_email(client["email"], token)

            flash("If that email is registered, a password reset link has been sent.", "success")
            return redirect(url_for("client_login"))

        return render_template("forgot_password.html")

    @app.route("/members/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token: str):
        conn = get_db()
        token_row = conn.execute(
            """
            SELECT prt.id, prt.client_id, prt.token, prt.expires_at, prt.used_at, c.email
            FROM password_reset_tokens prt
            JOIN clients c ON c.id = prt.client_id
            WHERE prt.token = %s
            """,
            (token,),
        ).fetchone()

        if token_row is None or token_row["used_at"] is not None or datetime.fromisoformat(token_row["expires_at"]) < datetime.utcnow():
            flash("This reset link is invalid or has expired.", "error")
            return redirect(url_for("client_login"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if len(password) < 8:
                flash("Password must be at least 8 characters.", "error")
                return render_template("reset_password.html", token=token)

            if password != confirm_password:
                flash("Passwords do not match.", "error")
                return render_template("reset_password.html", token=token)

            conn.execute(
                "UPDATE clients SET password_hash = ? WHERE id = %s",
                (generate_password_hash(password), token_row["client_id"]),
            )
            conn.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE id = %s",
                (datetime.utcnow().isoformat(), token_row["id"]),
            )
            conn.commit()
            flash("Password updated successfully. Please log in.", "success")
            return redirect(url_for("client_login"))

        return render_template("reset_password.html", token=token)

    @app.route("/members/files/<path:filename>")
    @client_login_required
    def member_file(filename: str):
        return send_from_directory(app.config["MEMBER_FOLDER"], filename, as_attachment=True)

    @app.route("/project-images/<path:filename>")
    def project_image(filename: str):
        return send_from_directory(app.config["PROJECT_IMAGE_FOLDER"], filename)

    @app.route("/staff-photos/<path:filename>")
    def staff_photo(filename: str):
        return send_from_directory(app.config["STAFF_PHOTO_FOLDER"], filename)

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            conn = get_db()
            admin = conn.execute(
                """
                SELECT id, full_name, email, password_hash, role, is_active
                FROM admins
                WHERE lower(email) = %s
                """,
                (email,),
            ).fetchone()

            if admin is None or not admin["is_active"] or not admin["password_hash"] or not check_password_hash(admin["password_hash"], password):
                flash("Invalid email or password.", "error")
                return render_template("admin_login.html")

            session.pop("client_user_id", None)
            session["admin_user_id"] = admin["id"]
            flash("Logged in successfully.", "success")
            return redirect(url_for("admin_dashboard"))

        return render_template("admin_login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("admin_user_id", None)
        flash("You have been logged out.", "success")
        return redirect(url_for("client_login"))

    @app.route("/admin")
    @admin_login_required
    def admin_dashboard():
        conn = get_db()
        stats = {
            "total": fetch_count(conn, "SELECT COUNT(*) AS count FROM inquiries"),
            "new": fetch_count(conn, "SELECT COUNT(*) AS count FROM inquiries WHERE status = 'new'"),
            "reviewed": fetch_count(conn, "SELECT COUNT(*) AS count FROM inquiries WHERE status = 'reviewed'"),
            "contacted": fetch_count(conn, "SELECT COUNT(*) AS count FROM inquiries WHERE status = 'contacted'"),
            "closed": fetch_count(conn, "SELECT COUNT(*) AS count FROM inquiries WHERE status = 'closed'"),
            "members": fetch_count(conn, "SELECT COUNT(*) AS count FROM clients"),
            "resources": fetch_count(conn, "SELECT COUNT(*) AS count FROM member_resources WHERE is_active = 1"),
        }
        recent = conn.execute(
            """
            SELECT id, full_name, company_name, service_required, status, created_at
            FROM inquiries
            ORDER BY created_at DESC
            LIMIT 8
            """
        ).fetchall()
        return render_template("admin_dashboard.html", stats=stats, recent=recent)

    @app.route("/admin/inquiries")
    @admin_login_required
    def admin_inquiries():
        status = request.args.get("status", "").strip()
        q = request.args.get("q", "").strip()
        conn = get_db()

        query = """
            SELECT id, full_name, company_name, phone_number, email_address,
                   service_required, project_location, status, created_at
            FROM inquiries
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if q:
            query += """
                AND (
                    full_name LIKE ?
                    OR company_name LIKE ?
                    OR email_address LIKE ?
                    OR phone_number LIKE ?
                    OR service_required LIKE ?
                )
            """
            like_q = f"%{q}%"
            params.extend([like_q, like_q, like_q, like_q, like_q])

        query += " ORDER BY created_at DESC"
        inquiries = conn.execute(query, params).fetchall()
        return render_template("admin_inquiries.html", inquiries=inquiries, active_status=status, search_query=q)

    @app.route("/admin/inquiries/<int:inquiry_id>")
    @admin_login_required
    def admin_inquiry_detail(inquiry_id: int):
        conn = get_db()
        inquiry = conn.execute(
            """
            SELECT id, inquiry_type, full_name, company_name, phone_number,
                   email_address, service_required, project_location, message,
                   status, source, created_at, updated_at
            FROM inquiries
            WHERE id = %s
            """,
            (inquiry_id,),
        ).fetchone()

        files = conn.execute(
            """
            SELECT id, original_filename, stored_filename, file_type,
                   file_size_bytes, upload_path, created_at
            FROM inquiry_files
            WHERE inquiry_id = %s
            ORDER BY created_at DESC
            """,
            (inquiry_id,),
        ).fetchall()

        if inquiry is None:
            flash("Inquiry not found.", "error")
            return redirect(url_for("admin_inquiries"))

        return render_template("admin_inquiry_detail.html", inquiry=inquiry, files=files)

    @app.post("/admin/inquiries/<int:inquiry_id>/status")
    @admin_login_required
    def update_inquiry_status(inquiry_id: int):
        new_status = request.form.get("status", "").strip()
        allowed = {"new", "reviewed", "contacted", "closed"}
        if new_status not in allowed:
            flash("Invalid status.", "error")
            return redirect(url_for("admin_inquiry_detail", inquiry_id=inquiry_id))

        conn = get_db()
        conn.execute("UPDATE inquiries SET status = ? WHERE id = %s", (new_status, inquiry_id))
        conn.execute(
            """
            INSERT INTO activity_log (inquiry_id, action_type, action_note, actor_email)
            VALUES (%s, %s, %s, %s)
            """,
            (
                inquiry_id,
                "status_updated",
                f"Inquiry status changed to {new_status}",
                g.admin_user["email"] if g.admin_user else "system",
            ),
        )
        conn.commit()
        flash("Inquiry status updated.", "success")
        return redirect(url_for("admin_inquiry_detail", inquiry_id=inquiry_id))

    @app.route("/admin/members")
    @admin_login_required
    def admin_members():
        conn = get_db()
        members = conn.execute(
            """
            SELECT id, full_name, email, phone_number, company_name, is_active, created_at
            FROM clients
            ORDER BY created_at DESC
            """
        ).fetchall()
        resources = conn.execute(
            """
            SELECT id, title, description, file_name, category, is_active, created_at
            FROM member_resources
            ORDER BY created_at DESC
            """
        ).fetchall()
        return render_template("admin_members.html", members=members, resources=resources)

    @app.route("/admin/members/create", methods=["GET", "POST"])
    @admin_login_required
    def admin_create_member():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone_number = request.form.get("phone_number", "").strip()
            company_name = request.form.get("company_name", "").strip()
            password = request.form.get("password", "").strip()

            if not full_name or not email or not password:
                flash("Full name, email, and password are required.", "error")
                return redirect(url_for("admin_create_member"))

            conn = get_db()
            if USE_POSTGRES:
                existing = conn.execute(
                    "SELECT id FROM clients WHERE lower(email)=lower(%s)",
                    (email,),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM clients WHERE lower(email)=lower(?)",
                    (email,),
                ).fetchone()

            if existing:
                flash("A member with that email already exists.", "error")
                return redirect(url_for("admin_create_member"))

            if USE_POSTGRES:
                conn.execute(
                    """
                    INSERT INTO clients (full_name, email, phone_number, company_name, password_hash, is_active)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    """,
                    (full_name, email, phone_number, company_name, generate_password_hash(password)),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO clients (full_name, email, phone_number, company_name, password_hash, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (full_name, email, phone_number, company_name, generate_password_hash(password)),
                )
            conn.commit()
            flash("Member account created successfully.", "success")
            return redirect(url_for("admin_members"))

        return render_template("admin_create_member.html")

    @app.route("/admin/member-resources/create", methods=["GET", "POST"])
    @admin_login_required
    def admin_create_member_resource():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "").strip() or "document"
            upload = request.files.get("resource_file")

            if not title or not upload or not upload.filename:
                flash("Title and file are required.", "error")
                return redirect(url_for("admin_create_member_resource"))

            original_filename = upload.filename
            safe_name = secure_filename(original_filename)
            ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else "bin"
            stored_filename = f"{uuid4().hex}.{ext}"
            file_path = MEMBER_DIR / stored_filename
            upload.save(file_path)

            conn = get_db()
            if USE_POSTGRES:
                conn.execute(
                    """
                    INSERT INTO member_resources (title, description, file_name, category, is_active)
                    VALUES (%s, %s, %s, %s, 1)
                    """,
                    (title, description, stored_filename, category),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO member_resources (title, description, file_name, category, is_active)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (title, description, stored_filename, category),
                )
            conn.commit()
            flash("Member resource uploaded successfully.", "success")
            return redirect(url_for("admin_members"))

        return render_template("admin_create_member_resource.html")

    @app.route("/admin/projects")
    @admin_login_required
    def admin_projects():
        conn = get_db()
        project_rows = conn.execute(
            """
            SELECT id, title, category, location, summary, image_url, is_active, created_at, updated_at
            FROM projects
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        return render_template("admin_projects.html", projects=project_rows)

    @app.route("/admin/projects/create", methods=["GET", "POST"])
    @admin_login_required
    def admin_create_project():
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            category = request.form.get("category", "").strip()
            location = request.form.get("location", "").strip()
            summary = request.form.get("summary", "").strip()
            image_url = request.form.get("image_url", "").strip()
            image_upload = request.files.get("image_upload")

            if not title:
                flash("Project title is required.", "error")
                return redirect(url_for("admin_create_project"))

            if image_upload and image_upload.filename:
                safe_name = secure_filename(image_upload.filename)
                ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else "jpg"
                stored_filename = f"{uuid4().hex}.{ext}"
                file_path = PROJECT_IMAGE_DIR / stored_filename
                image_upload.save(file_path)
                image_url = f"/project-images/{stored_filename}"

            conn = get_db()
            if USE_POSTGRES:
                conn.execute(
                    """
                    INSERT INTO projects (title, category, location, summary, image_url, is_active)
                    VALUES (%s, %s, %s, %s, %s, 1)
                    """,
                    (title, category, location, summary, image_url),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO projects (title, category, location, summary, image_url, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)
                    """,
                    (title, category, location, summary, image_url),
                )
            conn.commit()
            flash("Project saved successfully.", "success")
            return redirect(url_for("admin_projects"))

        return render_template("admin_project_form.html", project=None, form_action=url_for("admin_create_project"), page_title="Create Project")

    @app.route("/admin/projects/<int:project_id>/edit", methods=["GET", "POST"])
    @admin_login_required
    def admin_edit_project(project_id: int):
        conn = get_db()
        project = conn.execute(
            """
            SELECT id, title, category, location, summary, image_url, is_active, created_at, updated_at
            FROM projects
            WHERE id = %s
            """,
            (project_id,),
        ).fetchone()

        if project is None:
            flash("Project not found.", "error")
            return redirect(url_for("admin_projects"))

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            category = request.form.get("category", "").strip()
            location = request.form.get("location", "").strip()
            summary = request.form.get("summary", "").strip()
            image_url = request.form.get("image_url", "").strip()
            image_upload = request.files.get("image_upload")
            is_active = 1 if request.form.get("is_active") == "1" else 0

            if not title:
                flash("Project title is required.", "error")
                return redirect(url_for("admin_edit_project", project_id=project_id))

            if image_upload and image_upload.filename:
                safe_name = secure_filename(image_upload.filename)
                ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else "jpg"
                stored_filename = f"{uuid4().hex}.{ext}"
                file_path = PROJECT_IMAGE_DIR / stored_filename
                image_upload.save(file_path)
                image_url = f"/project-images/{stored_filename}"

            conn.execute(
                """
                UPDATE projects
                SET title = ?, category = ?, location = ?, summary = ?, image_url = ?, is_active = ?
                WHERE id = %s
                """,
                (title, category, location, summary, image_url, is_active, project_id),
            )
            conn.commit()
            flash("Project updated successfully.", "success")
            return redirect(url_for("admin_projects"))

        return render_template("admin_project_form.html", project=project, form_action=url_for("admin_edit_project", project_id=project_id), page_title="Update Project")

    @app.post("/admin/projects/<int:project_id>/delete")
    @admin_login_required
    def admin_delete_project(project_id: int):
        conn = get_db()
        project = conn.execute(
            "SELECT image_url FROM projects WHERE id = %s",
            (project_id,),
        ).fetchone()
        conn.execute("DELETE FROM projects WHERE id = %s", (project_id,))
        conn.commit()

        if project and project["image_url"] and project["image_url"].startswith("/project-images/"):
            stored_name = project["image_url"].split("/project-images/", 1)[1]
            image_path = PROJECT_IMAGE_DIR / stored_name
            if image_path.exists():
                try:
                    image_path.unlink()
                except OSError:
                    pass

        flash("Project deleted successfully.", "success")
        return redirect(url_for("admin_projects"))


    @app.route("/admin/testimonials")
    @admin_login_required
    def admin_testimonials():
        conn = get_db()
        items = conn.execute(
            """
            SELECT id, client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active, created_at
            FROM testimonials
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        return render_template("admin_testimonials.html", testimonials=items)

    @app.route("/admin/testimonials/create", methods=["GET", "POST"])
    @admin_login_required
    def admin_create_testimonial():
        if request.method == "POST":
            client_name = request.form.get("client_name", "").strip()
            company_name = request.form.get("company_name", "").strip()
            role_title = request.form.get("role_title", "").strip()
            testimonial_text = request.form.get("testimonial_text", "").strip()
            rating = request.form.get("rating", "5").strip()
            photo_url = request.form.get("photo_url", "").strip()
            is_featured = 1 if request.form.get("is_featured") == "1" else 0
            is_active = 1 if request.form.get("is_active") == "1" else 0

            if not client_name or not testimonial_text:
                flash("Client name and testimonial text are required.", "error")
                return redirect(url_for("admin_create_testimonial"))

            try:
                rating_int = max(1, min(5, int(rating)))
            except Exception:
                rating_int = 5

            conn = get_db()
            if USE_POSTGRES:
                conn.execute(
                    """
                    INSERT INTO testimonials (
                        client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (client_name, company_name, role_title, testimonial_text, rating_int, photo_url, is_featured, is_active),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO testimonials (
                        client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (client_name, company_name, role_title, testimonial_text, rating_int, photo_url, is_featured, is_active),
                )
            conn.commit()
            flash("Testimonial created successfully.", "success")
            return redirect(url_for("admin_testimonials"))

        return render_template("admin_testimonial_form.html", item=None, page_title="Create Testimonial", form_action=url_for("admin_create_testimonial"))

    @app.route("/admin/testimonials/<int:testimonial_id>/edit", methods=["GET", "POST"])
    @admin_login_required
    def admin_edit_testimonial(testimonial_id: int):
        conn = get_db()
        if USE_POSTGRES:
            item = conn.execute(
                """
                SELECT id, client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active
                FROM testimonials
                WHERE id = %s
                """,
                (testimonial_id,),
            ).fetchone()
        else:
            item = conn.execute(
                """
                SELECT id, client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active
                FROM testimonials
                WHERE id = ?
                """,
                (testimonial_id,),
            ).fetchone()

        if item is None:
            flash("Testimonial not found.", "error")
            return redirect(url_for("admin_testimonials"))

        if request.method == "POST":
            client_name = request.form.get("client_name", "").strip()
            company_name = request.form.get("company_name", "").strip()
            role_title = request.form.get("role_title", "").strip()
            testimonial_text = request.form.get("testimonial_text", "").strip()
            rating = request.form.get("rating", "5").strip()
            photo_url = request.form.get("photo_url", "").strip()
            is_featured = 1 if request.form.get("is_featured") == "1" else 0
            is_active = 1 if request.form.get("is_active") == "1" else 0

            if not client_name or not testimonial_text:
                flash("Client name and testimonial text are required.", "error")
                return redirect(url_for("admin_edit_testimonial", testimonial_id=testimonial_id))

            try:
                rating_int = max(1, min(5, int(rating)))
            except Exception:
                rating_int = 5

            if USE_POSTGRES:
                conn.execute(
                    """
                    UPDATE testimonials
                    SET client_name = %s, company_name = %s, role_title = %s, testimonial_text = %s, rating = %s, photo_url = %s, is_featured = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (client_name, company_name, role_title, testimonial_text, rating_int, photo_url, is_featured, is_active, testimonial_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE testimonials
                    SET client_name = ?, company_name = ?, role_title = ?, testimonial_text = ?, rating = ?, photo_url = ?, is_featured = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (client_name, company_name, role_title, testimonial_text, rating_int, photo_url, is_featured, is_active, testimonial_id),
                )
            conn.commit()
            flash("Testimonial updated successfully.", "success")
            return redirect(url_for("admin_testimonials"))

        return render_template("admin_testimonial_form.html", item=item, page_title="Update Testimonial", form_action=url_for("admin_edit_testimonial", testimonial_id=testimonial_id))

    @app.post("/admin/testimonials/<int:testimonial_id>/delete")
    @admin_login_required
    def admin_delete_testimonial(testimonial_id: int):
        conn = get_db()
        if USE_POSTGRES:
            conn.execute("DELETE FROM testimonials WHERE id = %s", (testimonial_id,))
        else:
            conn.execute("DELETE FROM testimonials WHERE id = ?", (testimonial_id,))
        conn.commit()
        flash("Testimonial deleted successfully.", "success")
        return redirect(url_for("admin_testimonials"))

    @app.route("/admin/staff")
    @admin_login_required
    def admin_staff():
        conn = get_db()
        staff_rows = conn.execute(
            """
            SELECT id, staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active, created_at
            FROM staff_members
            ORDER BY created_at DESC, id DESC
            """
        ).fetchall()
        return render_template("admin_staff.html", staff_members=staff_rows)

    @app.route("/admin/staff/create", methods=["GET", "POST"])
    @admin_login_required
    def admin_create_staff():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            role_title = request.form.get("role_title", "").strip()
            department = request.form.get("department", "").strip()
            email = request.form.get("email", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            photo_url = request.form.get("photo_url", "").strip()
            photo_upload = request.files.get("photo_upload")

            if not full_name or not role_title:
                flash("Full name and role title are required.", "error")
                return redirect(url_for("admin_create_staff"))

            if photo_upload and photo_upload.filename:
                safe_name = secure_filename(photo_upload.filename)
                ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else "jpg"
                stored_filename = f"{uuid4().hex}.{ext}"
                file_path = STAFF_PHOTO_DIR / stored_filename
                photo_upload.save(file_path)
                photo_url = f"/staff-photos/{stored_filename}"

            conn = get_db()
            staff_code = generate_staff_code(conn)
            if USE_POSTGRES:
                conn.execute(
                    """
                    INSERT INTO staff_members (
                        staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                    """,
                    (staff_code, full_name, role_title, department, email, phone_number, photo_url),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO staff_members (
                        staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (staff_code, full_name, role_title, department, email, phone_number, photo_url),
                )
            conn.commit()
            flash(f"Staff member created successfully with ID {staff_code}.", "success")
            return redirect(url_for("admin_staff"))

        return render_template("admin_staff_form.html", staff=None, page_title="Create Staff Member", form_action=url_for("admin_create_staff"))

    @app.route("/admin/staff/<int:staff_id>/edit", methods=["GET", "POST"])
    @admin_login_required
    def admin_edit_staff(staff_id: int):
        conn = get_db()
        if USE_POSTGRES:
            staff = conn.execute(
                """
                SELECT id, staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                FROM staff_members
                WHERE id = %s
                """,
                (staff_id,),
            ).fetchone()
        else:
            staff = conn.execute(
                """
                SELECT id, staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                FROM staff_members
                WHERE id = ?
                """,
                (staff_id,),
            ).fetchone()

        if staff is None:
            flash("Staff member not found.", "error")
            return redirect(url_for("admin_staff"))

        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            role_title = request.form.get("role_title", "").strip()
            department = request.form.get("department", "").strip()
            email = request.form.get("email", "").strip()
            phone_number = request.form.get("phone_number", "").strip()
            photo_url = request.form.get("photo_url", "").strip()
            photo_upload = request.files.get("photo_upload")
            is_active = 1 if request.form.get("is_active") == "1" else 0

            if photo_upload and photo_upload.filename:
                safe_name = secure_filename(photo_upload.filename)
                ext = safe_name.rsplit(".", 1)[1].lower() if "." in safe_name else "jpg"
                stored_filename = f"{uuid4().hex}.{ext}"
                file_path = STAFF_PHOTO_DIR / stored_filename
                photo_upload.save(file_path)
                photo_url = f"/staff-photos/{stored_filename}"

            if not full_name or not role_title:
                flash("Full name and role title are required.", "error")
                return redirect(url_for("admin_edit_staff", staff_id=staff_id))

            if USE_POSTGRES:
                conn.execute(
                    """
                    UPDATE staff_members
                    SET full_name = %s, role_title = %s, department = %s, email = %s, phone_number = %s, photo_url = %s, is_active = %s
                    WHERE id = %s
                    """,
                    (full_name, role_title, department, email, phone_number, photo_url, is_active, staff_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE staff_members
                    SET full_name = ?, role_title = ?, department = ?, email = ?, phone_number = ?, photo_url = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (full_name, role_title, department, email, phone_number, photo_url, is_active, staff_id),
                )
            conn.commit()
            flash("Staff member updated successfully.", "success")
            return redirect(url_for("admin_staff"))

        return render_template("admin_staff_form.html", staff=staff, page_title="Update Staff Member", form_action=url_for("admin_edit_staff", staff_id=staff_id))

    @app.post("/admin/staff/<int:staff_id>/delete")
    @admin_login_required
    def admin_delete_staff(staff_id: int):
        conn = get_db()
        if USE_POSTGRES:
            conn.execute("DELETE FROM staff_members WHERE id = %s", (staff_id,))
        else:
            conn.execute("DELETE FROM staff_members WHERE id = ?", (staff_id,))
        conn.commit()
        flash("Staff member deleted successfully.", "success")
        return redirect(url_for("admin_staff"))

    @app.route("/admin/staff/<int:staff_id>/id-card")
    @admin_login_required
    def admin_staff_id_card(staff_id: int):
        conn = get_db()
        if USE_POSTGRES:
            staff = conn.execute(
                """
                SELECT id, staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                FROM staff_members
                WHERE id = %s
                """,
                (staff_id,),
            ).fetchone()
        else:
            staff = conn.execute(
                """
                SELECT id, staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                FROM staff_members
                WHERE id = ?
                """,
                (staff_id,),
            ).fetchone()

        if staff is None:
            flash("Staff member not found.", "error")
            return redirect(url_for("admin_staff"))

        verify_token = build_staff_verify_token(staff)
        qr_payload = build_staff_qr_svg_payload(staff)
        return render_template("admin_staff_id_card.html", staff=staff, verify_token=verify_token, qr_payload=qr_payload)

    @app.route("/uploads/<path:filename>")
    @admin_login_required
    def uploaded_file(filename: str):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

    @app.post("/submit-quote")
    @client_login_required
    def submit_quote():
        full_name = request.form.get("full_name", "").strip()
        company_name = request.form.get("company_name", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        email_address = request.form.get("email_address", "").strip()
        service_required = request.form.get("service_required", "").strip()
        project_location = request.form.get("project_location", "").strip()
        message = request.form.get("message", "").strip()
        upload = request.files.get("project_file")

        required_fields = {
            "Full name": full_name,
            "Phone number": phone_number,
            "Email address": email_address,
            "Service required": service_required,
            "Message": message,
        }
        missing = [label for label, value in required_fields.items() if not value]
        if missing:
            flash("Please fill in all required fields: " + ", ".join(missing), "error")
            return redirect(url_for("contact"))

        conn = get_db()
        if USE_POSTGRES:
            cursor = conn.execute(
                """
                INSERT INTO inquiries (
                    inquiry_type, full_name, company_name, phone_number, email_address,
                    service_required, project_location, message, status, source
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    "quote",
                    full_name,
                    company_name,
                    phone_number,
                    email_address,
                    service_required,
                    project_location,
                    message,
                    "new",
                    "website",
                ),
            )
            inquiry_id = cursor.fetchone()["id"]
        else:
            cursor = conn.execute(
                """
                INSERT INTO inquiries (
                    inquiry_type, full_name, company_name, phone_number, email_address,
                    service_required, project_location, message, status, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "quote",
                    full_name,
                    company_name,
                    phone_number,
                    email_address,
                    service_required,
                    project_location,
                    message,
                    "new",
                    "website",
                ),
            )
            inquiry_id = cursor.lastrowid

        uploaded_original_name = None
        if upload and upload.filename:
            original_filename = upload.filename
            uploaded_original_name = original_filename
            if allowed_file(original_filename):
                safe_name = secure_filename(original_filename)
                ext = safe_name.rsplit(".", 1)[1].lower()
                stored_filename = f"{uuid4().hex}.{ext}"
                file_path = UPLOAD_DIR / stored_filename
                upload.save(file_path)

                conn.execute(
                    """
                    INSERT INTO inquiry_files (
                        inquiry_id, original_filename, stored_filename, file_type,
                        file_size_bytes, upload_path
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        inquiry_id,
                        original_filename,
                        stored_filename,
                        ext,
                        file_path.stat().st_size,
                        str(file_path),
                    ),
                )
            else:
                flash("File type not allowed. Accepted: PDF, DOC, DOCX, XLS, XLSX, PNG, JPG, JPEG, ZIP, DWG.", "error")
                conn.commit()
                return redirect(url_for("contact"))

        conn.execute(
            """
            INSERT INTO activity_log (inquiry_id, action_type, action_note, actor_email)
            VALUES (%s, %s, %s, %s)
            """,
            (
                inquiry_id,
                "created",
                "Quote request submitted from website form",
                "system",
            ),
        )
        conn.commit()

        email_sent = send_new_inquiry_email(
            inquiry_id=inquiry_id,
            full_name=full_name,
            company_name=company_name,
            phone_number=phone_number,
            email_address=email_address,
            service_required=service_required,
            project_location=project_location,
            message=message,
            uploaded_original_name=uploaded_original_name,
        )
        if not email_sent:
            print("SMTP email notification was not sent. Check SMTP settings.")

        flash("Your quote request was submitted successfully.", "success")
        return redirect(url_for("thank_you"))

    return app


def admin_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.get("admin_user") is None:
            flash("Please log in to access the admin area.", "error")
            return redirect(url_for("client_login"))
        return view(*args, **kwargs)
    return wrapped_view


def client_login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.get("client_user") is None:
            flash("Please log in to access member-only features.", "error")
            return redirect(url_for("client_login"))
        return view(*args, **kwargs)
    return wrapped_view


def get_db():
    if USE_POSTGRES:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        conn.autocommit = False
        return conn

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    if USE_POSTGRES:
        init_postgres_db()
        return

    schema = (BASE_DIR / "schema.sql").read_text(encoding="utf-8")
    conn = get_db()
    conn.executescript(schema)
    conn.commit()
    conn.close()




def init_postgres_db() -> None:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS inquiries (
                id SERIAL PRIMARY KEY,
                inquiry_type TEXT NOT NULL DEFAULT 'quote',
                full_name TEXT NOT NULL,
                company_name TEXT,
                phone_number TEXT NOT NULL,
                email_address TEXT NOT NULL,
                service_required TEXT NOT NULL,
                project_location TEXT,
                message TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                source TEXT NOT NULL DEFAULT 'website',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS inquiry_files (
                id SERIAL PRIMARY KEY,
                inquiry_id INTEGER NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
                original_filename TEXT NOT NULL,
                stored_filename TEXT,
                file_type TEXT,
                file_size_bytes BIGINT,
                upload_path TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS admins (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'admin',
                password_hash TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                inquiry_id INTEGER REFERENCES inquiries(id) ON DELETE SET NULL,
                action_type TEXT NOT NULL,
                action_note TEXT,
                actor_email TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone_number TEXT,
                company_name TEXT,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS member_resources (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                file_name TEXT,
                category TEXT NOT NULL DEFAULT 'document',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                token TEXT NOT NULL UNIQUE,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                category TEXT,
                location TEXT,
                summary TEXT,
                image_url TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS staff_members (
                id SERIAL PRIMARY KEY,
                staff_code TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                role_title TEXT NOT NULL,
                department TEXT,
                email TEXT,
                phone_number TEXT,
                photo_url TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_inquiries_created_at ON inquiries(created_at);
            CREATE INDEX IF NOT EXISTS idx_inquiries_status ON inquiries(status);
            CREATE INDEX IF NOT EXISTS idx_inquiry_files_inquiry_id ON inquiry_files(inquiry_id);
            CREATE INDEX IF NOT EXISTS idx_admins_email ON admins(email);
            CREATE INDEX IF NOT EXISTS idx_clients_email ON clients(email);
            CREATE INDEX IF NOT EXISTS idx_member_resources_active ON member_resources(is_active);
            CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
            CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);
            CREATE INDEX IF NOT EXISTS idx_staff_members_staff_code ON staff_members(staff_code);
            CREATE INDEX IF NOT EXISTS idx_staff_members_active ON staff_members(is_active);
            """
        )
    conn.commit()
    conn.close()

def ensure_runtime_tables() -> None:
    conn = get_db()

    if USE_POSTGRES:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    category TEXT,
                    location TEXT,
                    summary TEXT,
                    image_url TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);

                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id SERIAL PRIMARY KEY,
                    client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                    token TEXT NOT NULL UNIQUE,
                    expires_at TIMESTAMP NOT NULL,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
                """
            )
        conn.commit()
        conn.close()
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT,
            location TEXT,
            summary TEXT,
            image_url TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);

        CREATE TRIGGER IF NOT EXISTS trg_projects_updated_at
        AFTER UPDATE ON projects
        FOR EACH ROW
        BEGIN
            UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
        END;

        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            used_at DATETIME,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token);
        """
    )
    conn.commit()
    conn.close()


def sql_placeholder() -> str:
    return "%s" if USE_POSTGRES else "?"


def ensure_default_admin() -> None:
    conn = get_db()
    if USE_POSTGRES:
        existing = conn.execute(
            "SELECT id FROM admins WHERE lower(email) = lower(%s)",
            (DEFAULT_ADMIN_EMAIL,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO admins (full_name, email, role, password_hash, is_active)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    "Flux Admin",
                    DEFAULT_ADMIN_EMAIL,
                    "admin",
                    generate_password_hash(DEFAULT_ADMIN_PASSWORD),
                    1,
                ),
            )
    else:
        existing = conn.execute(
            "SELECT id FROM admins WHERE lower(email) = lower(?)",
            (DEFAULT_ADMIN_EMAIL,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO admins (full_name, email, role, password_hash, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "Flux Admin",
                    DEFAULT_ADMIN_EMAIL,
                    "admin",
                    generate_password_hash(DEFAULT_ADMIN_PASSWORD),
                    1,
                ),
            )
    conn.commit()
    conn.close()


def ensure_sample_project() -> None:

    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO projects (title, category, location, summary, image_url, is_active)
                VALUES (%s, %s, %s, %s, %s, 1)
                """,
                (
                    "Commercial Electrical & HVAC Installation",
                    "Commercial",
                    "Addis Ababa",
                    "Sample project entry managed from the database. Replace with your real project details from the admin panel.",
                    "",
                ),
            )
            conn.commit()
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def ensure_sample_member_resource() -> None:
    sample_file = MEMBER_DIR / "welcome-member-guide.txt"
    if not sample_file.exists():
        sample_file.write_text(
            "Welcome to the Flux member area.\n\nUse this section for member-only files, proposal guides, technical documents, and service updates.\n",
            encoding="utf-8",
        )

    conn = get_db()
    if USE_POSTGRES:
        existing = conn.execute(
            "SELECT id FROM member_resources WHERE title = %s",
            ("Member Welcome Guide",),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO member_resources (title, description, file_name, category, is_active)
                VALUES (%s, %s, %s, %s, 1)
                """,
                (
                    "Member Welcome Guide",
                    "Starter member-only document for registered clients.",
                    "welcome-member-guide.txt",
                    "document",
                ),
            )
    else:
        existing = conn.execute(
            "SELECT id FROM member_resources WHERE title = ?",
            ("Member Welcome Guide",),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO member_resources (title, description, file_name, category, is_active)
                VALUES (?, ?, ?, ?, 1)
                """,
                (
                    "Member Welcome Guide",
                    "Starter member-only document for registered clients.",
                    "welcome-member-guide.txt",
                    "document",
                ),
            )

    conn.commit()
    conn.close()






def ensure_sample_testimonials() -> None:
    conn = get_db()

    if USE_POSTGRES:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS testimonials (
                    id SERIAL PRIMARY KEY,
                    client_name TEXT NOT NULL,
                    company_name TEXT,
                    role_title TEXT,
                    testimonial_text TEXT NOT NULL,
                    rating INTEGER NOT NULL DEFAULT 5,
                    photo_url TEXT,
                    is_featured INTEGER NOT NULL DEFAULT 1,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        row = conn.execute("SELECT COUNT(*) AS count FROM testimonials").fetchone()
        try:
            count = int(row["count"])
        except Exception:
            count = int(row[0]) if row else 0

        if count == 0:
            conn.execute(
                """
                INSERT INTO testimonials (
                    client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, 1, 1)
                """,
                (
                    "Sample Client",
                    "Addis Industrial Group",
                    "Project Manager",
                    "FLUX delivered our electro-mechanical works professionally, on schedule, and with excellent technical quality.",
                    5,
                    "",
                ),
            )
            conn.commit()
        conn.close()
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS testimonials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            company_name TEXT,
            role_title TEXT,
            testimonial_text TEXT NOT NULL,
            rating INTEGER NOT NULL DEFAULT 5,
            photo_url TEXT,
            is_featured INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    row = conn.execute("SELECT COUNT(*) AS count FROM testimonials").fetchone()
    try:
        count = int(row["count"])
    except Exception:
        count = int(row[0]) if row else 0

    if count == 0:
        conn.execute(
            """
            INSERT INTO testimonials (
                client_name, company_name, role_title, testimonial_text, rating, photo_url, is_featured, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 1)
            """,
            (
                "Sample Client",
                "Addis Industrial Group",
                "Project Manager",
                "FLUX delivered our electro-mechanical works professionally, on schedule, and with excellent technical quality.",
                5,
                "",
            ),
        )
        conn.commit()
    conn.close()


def generate_staff_code(conn) -> str:
    prefix = "FLX-STF-"
    row = conn.execute("SELECT COUNT(*) AS count FROM staff_members").fetchone()
    try:
        count = int(row["count"])
    except Exception:
        count = int(row[0]) if row else 0
    return f"{prefix}{count + 1:03d}"


def ensure_sample_staff_members() -> None:
    conn = get_db()

    if USE_POSTGRES:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_members (
                    id SERIAL PRIMARY KEY,
                    staff_code TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    role_title TEXT NOT NULL,
                    department TEXT,
                    email TEXT,
                    phone_number TEXT,
                    photo_url TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        existing = conn.execute("SELECT COUNT(*) AS count FROM staff_members").fetchone()
        try:
            count = int(existing["count"])
        except Exception:
            count = int(existing[0]) if existing else 0

        if count == 0:
            conn.execute(
                """
                INSERT INTO staff_members (
                    staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    "FLX-STF-001",
                    "Sample Staff Member",
                    "Operations Engineer",
                    "Engineering",
                    "staff@fluxelectromechanical.enginner.et",
                    "+251900000000",
                    "",
                ),
            )
        conn.commit()
        conn.close()
        return

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS staff_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff_code TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            role_title TEXT NOT NULL,
            department TEXT,
            email TEXT,
            phone_number TEXT,
            photo_url TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    existing = conn.execute("SELECT COUNT(*) AS count FROM staff_members").fetchone()
    try:
        count = int(existing["count"])
    except Exception:
        count = int(existing[0]) if existing else 0

    if count == 0:
        conn.execute(
            """
            INSERT INTO staff_members (
                staff_code, full_name, role_title, department, email, phone_number, photo_url, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                "FLX-STF-001",
                "Sample Staff Member",
                "Operations Engineer",
                "Engineering",
                "staff@fluxelectromechanical.enginner.et",
                "+251900000000",
                "",
            ),
        )
        conn.commit()
    conn.close()


def allowed_file(filename: str) -> bool:

    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS



def fetch_count(conn, query: str) -> int:
    row = conn.execute(query).fetchone()
    if row is None:
        return 0
    if isinstance(row, dict):
        return int(row.get("count", 0))
    try:
        return int(row["count"])
    except Exception:
        return int(row[0])




def build_staff_verify_token(staff_row) -> str:
    raw = f"{staff_row['staff_code']}|{staff_row['full_name']}|{staff_row['role_title']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16].upper()


def build_staff_qr_svg_payload(staff_row) -> str:
    token = build_staff_verify_token(staff_row)
    text = f"FLUX STAFF ID\nCode: {staff_row['staff_code']}\nName: {staff_row['full_name']}\nRole: {staff_row['role_title']}\nVerify: {token}"
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"data:text/plain;base64,{encoded}"

def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and MAIL_TO)


def send_new_inquiry_email(
    *,
    inquiry_id: int,
    full_name: str,
    company_name: str,
    phone_number: str,
    email_address: str,
    service_required: str,
    project_location: str,
    message: str,
    uploaded_original_name: str | None,
) -> bool:
    if not smtp_configured():
        return False

    body = f"""
New inquiry received from the Flux website.

Inquiry ID: {inquiry_id}
Name: {full_name}
Company: {company_name or '-'}
Phone: {phone_number}
Email: {email_address}
Service: {service_required}
Project Location: {project_location or '-'}
Uploaded File: {uploaded_original_name or 'No file uploaded'}

Message:
{message}
""".strip()

    msg = EmailMessage()
    msg["Subject"] = f"New website inquiry #{inquiry_id} - {service_required}"
    msg["From"] = MAIL_FROM
    msg["To"] = MAIL_TO
    msg["Reply-To"] = email_address
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"SMTP send failed: {exc}")
        return False


def send_password_reset_email(email: str, token: str) -> bool:
    if not smtp_configured():
        print("SMTP not configured, password reset email not sent.")
        print(f"Manual reset link: {PUBLIC_BASE_URL}/members/reset-password/{token}")
        return False

    reset_link = f"{PUBLIC_BASE_URL}/members/reset-password/{token}"
    body = f"""
A password reset was requested for your Flux member account.

Use the link below to reset your password:
{reset_link}

This link expires in 1 hour.

If you did not request this, you can ignore this email.
""".strip()

    msg = EmailMessage()
    msg["Subject"] = "Reset your Flux member password"
    msg["From"] = MAIL_FROM
    msg["To"] = email
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"SMTP send failed: {exc}")
        print(f"Manual reset link: {reset_link}")
        return False


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
app = create_app()
