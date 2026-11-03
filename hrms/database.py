import json
import os
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from .storage_paths import get_data_directory


DEFAULT_DATABASE_PATH = get_data_directory() / "hr_assist.sqlite3"


class HRDatabase:
    """SQLite persistence for employee, leave, meeting, and ticket records."""

    def __init__(self, path: Optional[Path] = None):
        configured_path = os.getenv("HR_DATABASE_PATH")
        self.path = Path(path or configured_path or DEFAULT_DATABASE_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(str(self.path))
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS employees (
                    emp_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    manager_id TEXT,
                    email TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_employees_name ON employees(name);

                CREATE TABLE IF NOT EXISTS leave_balances (
                    emp_id TEXT PRIMARY KEY,
                    balance INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS leave_history (
                    emp_id TEXT NOT NULL,
                    history_id INTEGER NOT NULL,
                    leave_date TEXT NOT NULL,
                    request_id INTEGER NOT NULL,
                    PRIMARY KEY (emp_id, history_id)
                );

                CREATE TABLE IF NOT EXISTS meetings (
                    meeting_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    emp_id TEXT NOT NULL,
                    meeting_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_meetings_employee ON meetings(emp_id);

                CREATE TABLE IF NOT EXISTS tickets (
                    ticket_id TEXT PRIMARY KEY,
                    emp_id TEXT NOT NULL,
                    item TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tickets_employee ON tickets(emp_id);
                """
            )

    def load_employees(self) -> Dict[str, Dict[str, Optional[str]]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT emp_id, name, manager_id, email FROM employees ORDER BY emp_id"
            ).fetchall()
        return {
            emp_id: {"emp_id": emp_id, "name": name, "manager_id": manager_id, "email": email}
            for emp_id, name, manager_id, email in rows
        }

    def save_employee(self, employee: Dict[str, Optional[str]]) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO employees (emp_id, name, manager_id, email)
                VALUES (?, ?, ?, ?)
                """,
                (
                    employee["emp_id"],
                    employee["name"],
                    employee.get("manager_id"),
                    employee.get("email"),
                ),
            )

    def save_employees(self, employees: Dict[str, Dict[str, Optional[str]]]) -> None:
        rows = [
            (emp_id, employee["name"], employee.get("manager_id"), employee.get("email"))
            for emp_id, employee in employees.items()
        ]
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM employees")
            connection.executemany(
                "INSERT INTO employees (emp_id, name, manager_id, email) VALUES (?, ?, ?, ?)",
                rows,
            )

    def load_leave(self):
        leaves = defaultdict(lambda: {"balance": 20, "history": []})
        with closing(self._connect()) as connection:
            balances = connection.execute(
                "SELECT emp_id, balance FROM leave_balances"
            ).fetchall()
            history = connection.execute(
                """
                SELECT emp_id, history_id, leave_date, request_id
                FROM leave_history ORDER BY emp_id, history_id
                """
            ).fetchall()
        for emp_id, balance in balances:
            leaves[emp_id]["balance"] = balance
        for emp_id, history_id, leave_date, request_id in history:
            leaves[emp_id]["history"].append({
                "history_id": history_id,
                "emp_id": emp_id,
                "leave_date": date.fromisoformat(leave_date),
                "request_id": request_id,
            })
        return leaves

    def save_leave(self, leave_records) -> None:
        balance_rows = [(emp_id, record["balance"]) for emp_id, record in leave_records.items()]
        history_rows = []
        for emp_id, record in leave_records.items():
            for index, entry in enumerate(record["history"], start=1):
                leave_date = entry["leave_date"]
                if isinstance(leave_date, date):
                    leave_date = leave_date.isoformat()
                history_rows.append((
                    emp_id,
                    entry.get("history_id", index),
                    leave_date,
                    entry.get("request_id", index),
                ))
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM leave_balances")
            connection.execute("DELETE FROM leave_history")
            connection.executemany(
                "INSERT INTO leave_balances (emp_id, balance) VALUES (?, ?)",
                balance_rows,
            )
            connection.executemany(
                """
                INSERT INTO leave_history (emp_id, history_id, leave_date, request_id)
                VALUES (?, ?, ?, ?)
                """,
                history_rows,
            )

    def load_meetings(self):
        meetings = defaultdict(list)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT emp_id, meeting_json FROM meetings ORDER BY meeting_id"
            ).fetchall()
        for emp_id, meeting_json in rows:
            meetings[emp_id].append(json.loads(meeting_json))
        return meetings

    def save_meetings(self, meetings) -> None:
        rows = [
            (emp_id, json.dumps(meeting, ensure_ascii=False))
            for emp_id, records in meetings.items()
            for meeting in records
        ]
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM meetings")
            connection.executemany(
                "INSERT INTO meetings (emp_id, meeting_json) VALUES (?, ?)",
                rows,
            )

    def load_tickets(self) -> List[Dict[str, str]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT ticket_id, emp_id, item, reason, status, created_at, updated_at
                FROM tickets ORDER BY rowid
                """
            ).fetchall()
        return [
            {
                "ticket_id": ticket_id,
                "emp_id": emp_id,
                "item": item,
                "reason": reason,
                "status": status,
                "created_at": created_at,
                "updated_at": updated_at,
            }
            for ticket_id, emp_id, item, reason, status, created_at, updated_at in rows
        ]

    def save_tickets(self, tickets: Iterable[Dict[str, str]]) -> None:
        rows = [
            (
                ticket["ticket_id"],
                ticket["emp_id"],
                ticket["item"],
                ticket["reason"],
                ticket["status"],
                ticket["created_at"],
                ticket["updated_at"],
            )
            for ticket in tickets
        ]
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM tickets")
            connection.executemany(
                """
                INSERT INTO tickets
                    (ticket_id, emp_id, item, reason, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
