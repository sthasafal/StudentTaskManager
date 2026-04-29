from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "source"
DB_PATH = BASE_DIR / "mvp_task_manager.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"
HOST = "127.0.0.1"
PORT = 8001
SESSION_COOKIE = "student_task_session"
SESSION_DAYS = 7
DEMO_EMAIL = "demo@student.local"
DEMO_PASSWORD = "demo1234"


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, expected = stored_hash.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), f"{salt}${expected}")


def init_database() -> None:
    connection = get_connection()
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrate_task_status_schema(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_due_date ON tasks(user_id, due_date)")
        demo_user_id = ensure_demo_user(connection)
        if count_tasks(connection, demo_user_id) == 0:
            insert_sample_tasks(connection, demo_user_id)
        connection.commit()
    finally:
        connection.close()


def migrate_task_status_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'tasks'").fetchone()
    table_sql = row["sql"] if row else ""
    if "inprogress" in table_sql:
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("ALTER TABLE tasks RENAME TO tasks_old")
    connection.execute(
        """
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            course TEXT NOT NULL DEFAULT 'General',
            description TEXT NOT NULL DEFAULT '',
            due_date TEXT NOT NULL,
            priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
            status TEXT NOT NULL CHECK (status IN ('pending', 'inprogress', 'done')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        INSERT INTO tasks (id, user_id, title, course, description, due_date, priority, status, created_at, updated_at)
        SELECT id, user_id, title, course, description, due_date, priority, status, created_at, updated_at
        FROM tasks_old
        """
    )
    connection.execute("DROP TABLE tasks_old")
    connection.execute("PRAGMA foreign_keys = ON")


def ensure_demo_user(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo Student", DEMO_EMAIL, hash_password(DEMO_PASSWORD)),
    )
    return int(cursor.lastrowid)


def count_tasks(connection: sqlite3.Connection, user_id: int) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,)).fetchone()[0])


def insert_sample_tasks(connection: sqlite3.Connection, user_id: int) -> None:
    today = date.today()
    sample_tasks = [
        (user_id, "Finish database ER diagram", "Database Systems", "Draw users, sessions, and tasks tables.", today.isoformat(), "high", "pending"),
        (user_id, "Prepare project presentation", "Software Engineering", "Summarize objective, scope, CRUD, auth, and screenshots.", (today + timedelta(days=1)).isoformat(), "medium", "inprogress"),
        (user_id, "Review JavaScript DOM events", "Web Development", "Practice forms, click handlers, and fetch API.", (today + timedelta(days=3)).isoformat(), "low", "pending"),
        (user_id, "Submit task manager report", "Capstone", "Add screenshots and final conclusion.", (today - timedelta(days=1)).isoformat(), "high", "pending"),
        (user_id, "Complete HTML wireframe", "Web Development", "Dashboard view, task form, and responsive layout.", (today - timedelta(days=3)).isoformat(), "medium", "done"),
    ]
    connection.executemany(
        """
        INSERT INTO tasks (user_id, title, course, description, due_date, priority, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        sample_tasks,
    )


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    payload = handler.rfile.read(content_length) if content_length else b"{}"
    return json.loads(payload.decode("utf-8"))


def serialize_user(row: sqlite3.Row) -> dict[str, object]:
    return {"id": row["id"], "name": row["name"], "email": row["email"]}


def serialize_task(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "title": row["title"],
        "course": row["course"],
        "description": row["description"],
        "dueDate": row["due_date"],
        "priority": row["priority"],
        "status": row["status"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def fetch_tasks(user_id: int) -> list[dict[str, object]]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, title, course, description, due_date, priority, status, created_at, updated_at
            FROM tasks
            WHERE user_id = ?
            ORDER BY
                CASE status WHEN 'pending' THEN 1 WHEN 'inprogress' THEN 2 ELSE 3 END,
                due_date ASC,
                CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                id DESC
            """,
            (user_id,),
        ).fetchall()
        return [serialize_task(row) for row in rows]
    finally:
        connection.close()


def fetch_summary(tasks: list[dict[str, object]]) -> dict[str, int]:
    today = date.today()
    completed = sum(1 for task in tasks if task["status"] == "done")
    pending = sum(1 for task in tasks if task["status"] == "pending")
    in_progress = sum(1 for task in tasks if task["status"] == "inprogress")
    active_statuses = {"pending", "inprogress"}
    overdue = sum(1 for task in tasks if task["status"] in active_statuses and date.fromisoformat(str(task["dueDate"])) < today)
    due_today = sum(1 for task in tasks if task["status"] in active_statuses and date.fromisoformat(str(task["dueDate"])) == today)
    return {
        "total": len(tasks),
        "completed": completed,
        "pending": pending,
        "inProgress": in_progress,
        "overdue": overdue,
        "dueToday": due_today,
    }


class StudentTaskManagerHandler(BaseHTTPRequestHandler):
    server_version = "StudentTaskManager/2.1"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/session":
            user = self.get_current_user()
            self.send_json({"authenticated": bool(user), "user": serialize_user(user) if user else None})
            return
        if path == "/api/tasks":
            user = self.require_user()
            if user:
                self.send_task_payload(int(user["id"]))
            return
        self.serve_static(path)

    def do_HEAD(self) -> None:
        self.serve_static(urlparse(self.path).path, body=False)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/register":
            self.register_user()
            return
        if path == "/api/login":
            self.login_user()
            return
        if path == "/api/logout":
            self.logout_user()
            return
        if path == "/api/tasks":
            user = self.require_user()
            if user:
                self.create_task(int(user["id"]))
            return
        if path.startswith("/api/tasks/") and path.endswith("/toggle"):
            user = self.require_user()
            if user:
                self.toggle_task(int(user["id"]))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def do_PUT(self) -> None:
        if urlparse(self.path).path.startswith("/api/tasks/"):
            user = self.require_user()
            if user:
                self.update_task(int(user["id"]))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def do_DELETE(self) -> None:
        if urlparse(self.path).path.startswith("/api/tasks/"):
            user = self.require_user()
            if user:
                self.delete_task(int(user["id"]))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found.")

    def log_message(self, format: str, *args: object) -> None:
        return

    def send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK, cookie: str | None = None) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(encoded)

    def serve_static(self, requested_path: str, body: bool = True) -> None:
        file_path = SOURCE_DIR / "index.html" if requested_path == "/" else (SOURCE_DIR / Path(unquote(requested_path.lstrip("/")))).resolve()
        if SOURCE_DIR.resolve() not in file_path.parents and file_path != SOURCE_DIR.resolve():
            self.send_error(HTTPStatus.FORBIDDEN, "Access denied.")
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found.")
            return
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if body:
            self.wfile.write(content)

    def register_user(self) -> None:
        try:
            payload = read_json(self)
            name = str(payload.get("name", "")).strip()
            email = str(payload.get("email", "")).strip().lower()
            password = str(payload.get("password", ""))
            if len(name) < 2:
                raise ValueError("Name must be at least 2 characters.")
            if "@" not in email or "." not in email:
                raise ValueError("Enter a valid email address.")
            if len(password) < 6:
                raise ValueError("Password must be at least 6 characters.")
        except (ValueError, json.JSONDecodeError) as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        connection = get_connection()
        try:
            cursor = connection.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)", (name, email, hash_password(password)))
            user_id = int(cursor.lastrowid)
            insert_sample_tasks(connection, user_id)
            connection.commit()
        except sqlite3.IntegrityError:
            self.send_json({"error": "An account with this email already exists."}, HTTPStatus.CONFLICT)
            return
        finally:
            connection.close()
        self.create_session_response(user_id, HTTPStatus.CREATED)

    def login_user(self) -> None:
        try:
            payload = read_json(self)
            email = str(payload.get("email", "")).strip().lower()
            password = str(payload.get("password", ""))
        except json.JSONDecodeError as error:
            self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        connection = get_connection()
        try:
            user = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        finally:
            connection.close()
        if not user or not verify_password(password, str(user["password_hash"])):
            self.send_json({"error": "Email or password is incorrect."}, HTTPStatus.UNAUTHORIZED)
            return
        self.create_session_response(int(user["id"]))

    def logout_user(self) -> None:
        session_id = self.get_session_id()
        if session_id:
            connection = get_connection()
            try:
                connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                connection.commit()
            finally:
                connection.close()
        self.send_json({"message": "Signed out."}, cookie=f"{SESSION_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax")

    def create_session_response(self, user_id: int, status: HTTPStatus = HTTPStatus.OK) -> None:
        session_id = uuid.uuid4().hex
        expires_at = datetime.utcnow() + timedelta(days=SESSION_DAYS)
        connection = get_connection()
        try:
            connection.execute("INSERT INTO sessions (id, user_id, expires_at) VALUES (?, ?, ?)", (session_id, user_id, expires_at.isoformat()))
            user = connection.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,)).fetchone()
            connection.commit()
        finally:
            connection.close()
        cookie = f"{SESSION_COOKIE}={session_id}; Max-Age={SESSION_DAYS * 86400}; Path=/; HttpOnly; SameSite=Lax"
        self.send_json({"user": serialize_user(user), "message": "Signed in."}, status, cookie)

    def get_session_id(self) -> str | None:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie(cookie_header)
        return cookie[SESSION_COOKIE].value if SESSION_COOKIE in cookie else None

    def get_current_user(self) -> sqlite3.Row | None:
        session_id = self.get_session_id()
        if not session_id:
            return None
        connection = get_connection()
        try:
            user = connection.execute(
                """
                SELECT users.id, users.name, users.email
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.id = ? AND sessions.expires_at > ?
                """,
                (session_id, datetime.utcnow().isoformat()),
            ).fetchone()
            if user is None:
                connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                connection.commit()
            return user
        finally:
            connection.close()

    def require_user(self) -> sqlite3.Row | None:
        user = self.get_current_user()
        if user is None:
            self.send_json({"error": "Please sign in first."}, HTTPStatus.UNAUTHORIZED)
        return user

    def send_task_payload(self, user_id: int, status: HTTPStatus = HTTPStatus.OK) -> None:
        tasks = fetch_tasks(user_id)
        self.send_json({"tasks": tasks, "summary": fetch_summary(tasks)}, status)

    def create_task(self, user_id: int) -> None:
        validated = self.validate_task_payload()
        if "error" in validated:
            self.send_json({"error": validated["error"]}, HTTPStatus.BAD_REQUEST)
            return
        connection = get_connection()
        try:
            connection.execute(
                "INSERT INTO tasks (user_id, title, course, description, due_date, priority, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (user_id, validated["title"], validated["course"], validated["description"], validated["due_date"], validated["priority"]),
            )
            connection.commit()
        finally:
            connection.close()
        self.send_task_payload(user_id, HTTPStatus.CREATED)

    def update_task(self, user_id: int) -> None:
        task_id = self.get_task_id()
        validated = self.validate_task_payload(allow_status=True)
        if task_id is None or "error" in validated:
            self.send_json({"error": validated.get("error", "Invalid task id.")}, HTTPStatus.BAD_REQUEST)
            return
        connection = get_connection()
        try:
            updated = connection.execute(
                """
                UPDATE tasks
                SET title = ?, course = ?, description = ?, due_date = ?, priority = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ?
                """,
                (validated["title"], validated["course"], validated["description"], validated["due_date"], validated["priority"], validated["status"], task_id, user_id),
            )
            if updated.rowcount == 0:
                self.send_json({"error": "Task not found."}, HTTPStatus.NOT_FOUND)
                return
            connection.commit()
        finally:
            connection.close()
        self.send_task_payload(user_id)

    def toggle_task(self, user_id: int) -> None:
        task_id = self.get_task_id()
        if task_id is None:
            self.send_json({"error": "Invalid task id."}, HTTPStatus.BAD_REQUEST)
            return
        connection = get_connection()
        try:
            row = connection.execute("SELECT status FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)).fetchone()
            if row is None:
                self.send_json({"error": "Task not found."}, HTTPStatus.NOT_FOUND)
                return
            next_status = "done" if row["status"] != "done" else "pending"
            connection.execute("UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?", (next_status, task_id, user_id))
            connection.commit()
        finally:
            connection.close()
        self.send_task_payload(user_id)

    def delete_task(self, user_id: int) -> None:
        task_id = self.get_task_id()
        if task_id is None:
            self.send_json({"error": "Invalid task id."}, HTTPStatus.BAD_REQUEST)
            return
        connection = get_connection()
        try:
            deleted = connection.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
            if deleted.rowcount == 0:
                self.send_json({"error": "Task not found."}, HTTPStatus.NOT_FOUND)
                return
            connection.commit()
        finally:
            connection.close()
        self.send_task_payload(user_id)

    def validate_task_payload(self, allow_status: bool = False) -> dict[str, str]:
        try:
            payload = read_json(self)
            title = str(payload.get("title", "")).strip()
            course = str(payload.get("course", "General")).strip() or "General"
            description = str(payload.get("description", "")).strip()
            due_date = str(payload.get("dueDate", "")).strip()
            priority = str(payload.get("priority", "medium")).strip()
            status = str(payload.get("status", "pending")).strip()
            if len(title) < 3:
                raise ValueError("Task title must be at least 3 characters.")
            if len(course) > 60:
                raise ValueError("Course name must be 60 characters or fewer.")
            if len(description) > 500:
                raise ValueError("Description must be 500 characters or fewer.")
            date.fromisoformat(due_date)
            if priority not in {"low", "medium", "high"}:
                raise ValueError("Priority must be low, medium, or high.")
            if allow_status and status not in {"pending", "inprogress", "done"}:
                raise ValueError("Status must be pending, in progress, or done.")
        except (ValueError, json.JSONDecodeError) as error:
            return {"error": str(error)}
        return {"title": title, "course": course, "description": description, "due_date": due_date, "priority": priority, "status": status if allow_status else "pending"}

    def get_task_id(self) -> int | None:
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) < 3 or parts[0] != "api" or parts[1] != "tasks":
            return None
        try:
            task_id = int(parts[2])
        except ValueError:
            return None
        return task_id if task_id > 0 else None


def run() -> None:
    init_database()
    server = ThreadingHTTPServer((HOST, PORT), StudentTaskManagerHandler)
    print(f"Student Task Manager running on http://{HOST}:{PORT}")
    print(f"Demo login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
