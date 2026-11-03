import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from hrms.database import HRDatabase
from hrms.directory import build_employee_directory
from hrms.employee_manager import EmployeeManager
from hrms.leave_manager import LeaveManager
from hrms.meeting_manager import MeetingManager
from hrms.schemas import EmployeeCreate, LeaveApplyRequest, MeetingCreate, TicketCreate, TicketStatusUpdate
from hrms.reports import build_hr_overview
from hrms.ticket_manager import TicketManager
from utils import seed_services


class HRDatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "hr_assist.sqlite3"

    def create_managers(self):
        database = HRDatabase(self.database_path)
        return (
            database,
            EmployeeManager(database),
            LeaveManager(database),
            MeetingManager(database),
            TicketManager(database),
        )

    def test_seeded_and_updated_records_survive_restart(self):
        database, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)

        original_ticket_count = len(tickets.tickets)
        employees.add_employee(EmployeeCreate(
            emp_id=employees.get_next_emp_id(),
            name="Alex Rivera",
            manager_id="E001",
            email="alex.rivera@example.test",
        ))
        leaves.apply_leave(LeaveApplyRequest(
            emp_id="E001",
            leave_dates=[date(2026, 12, 24)],
        ))
        meetings.schedule_meeting(MeetingCreate(
            emp_id="E001",
            meeting_dt=datetime(2026, 12, 1, 10, 0),
            topic="Persistence check",
        ))
        tickets.create_ticket(TicketCreate(
            emp_id="E001",
            item="Monitor",
            reason="Persistence check",
        ))
        tickets.update_ticket_status(
            TicketStatusUpdate(status="In Progress"),
            tickets.tickets[-1]["ticket_id"],
        )

        _, reloaded_employees, reloaded_leaves, reloaded_meetings, reloaded_tickets = self.create_managers()
        seeded_counts = seed_services(
            reloaded_employees,
            reloaded_leaves,
            reloaded_meetings,
            reloaded_tickets,
        )

        self.assertEqual(
            reloaded_employees.get_employee_details("E009")["name"],
            "Alex Rivera",
        )
        self.assertIn("December 24, 2026", reloaded_leaves.get_leave_history("E001"))
        self.assertTrue(any(
            meeting.get("topic") == "Persistence check"
            for meeting in reloaded_meetings.get_meetings("E001")
        ))
        self.assertEqual(reloaded_tickets.tickets[-1]["status"], "In Progress")
        self.assertEqual(len(reloaded_tickets.tickets), original_ticket_count + 1)
        self.assertEqual(seeded_counts["employees"], 9)

    def test_existing_database_is_not_reseeded_on_restart(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)
        original_ticket_count = len(tickets.tickets)

        _, employees, leaves, meetings, tickets = self.create_managers()
        result = seed_services(employees, leaves, meetings, tickets)

        self.assertEqual(result["tickets"], original_ticket_count)
        self.assertEqual(len(tickets.tickets), original_ticket_count)

    def test_employee_directory_includes_profile_and_related_records(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)

        directory = build_employee_directory(
            employees,
            leaves,
            meetings,
            tickets,
            include_details=True,
        )

        self.assertEqual(len(directory), 8)
        sarah = next(employee for employee in directory if employee["emp_id"] == "E001")
        david = next(employee for employee in directory if employee["emp_id"] == "E003")
        self.assertEqual(sarah["name"], "Sarah Johnson")
        self.assertIsNone(sarah["manager"])
        self.assertIn("email", sarah)
        self.assertIn("balance", sarah["leave"])
        self.assertTrue(sarah["leave"]["history"])
        self.assertTrue(sarah["meetings"])
        self.assertIn("tickets", sarah)
        self.assertEqual(david["manager"]["emp_id"], "E001")
        self.assertIn(
            {"emp_id": "E004", "name": "Tony Sharma", "email": "tony.sharma@atliq.com"},
            david["direct_reports"],
        )

    def test_employee_directory_summary_includes_manager_without_large_details(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)

        directory = build_employee_directory(employees, leaves, meetings, tickets)

        self.assertEqual(len(directory), 8)
        david = next(employee for employee in directory if employee["emp_id"] == "E003")
        self.assertEqual(david["manager"]["emp_id"], "E001")
        self.assertEqual(david["manager"]["name"], "Sarah Johnson")
        self.assertNotIn("meetings", david)
        self.assertNotIn("tickets", david)

    def test_search_employees_matches_name_id_and_email(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)

        self.assertEqual(
            [employee["emp_id"] for employee in employees.search_employees("E004")],
            ["E004"],
        )
        self.assertEqual(
            [employee["emp_id"] for employee in employees.search_employees("sharma")],
            ["E004"],
        )
        self.assertEqual(
            [employee["emp_id"] for employee in employees.search_employees("@atliq.com")],
            [f"E{number:03d}" for number in range(1, 9)],
        )
        with self.assertRaises(ValueError):
            employees.search_employees(" ")

    def test_hr_overview_reports_counts_and_upcoming_meetings(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)

        meetings.meetings = {
            "E001": [
                {"date": "2026-03-10", "time": "09:00", "title": "Within window"},
                {"date": "2026-03-18", "time": "09:00", "title": "Outside window"},
            ],
            "E002": [
                {"date": "2026-03-10T11:00:00", "topic": "ISO meeting"},
            ],
        }
        tickets.tickets = [
            {"status": "Open"},
            {"status": "Open"},
            {"status": "Closed"},
        ]

        overview = build_hr_overview(
            employees,
            leaves,
            meetings,
            tickets,
            today=date(2026, 3, 10),
        )

        self.assertEqual(overview["headcount"], 8)
        self.assertEqual(overview["manager_count"], 4)
        self.assertEqual(overview["tickets"], {
            "total": 3,
            "by_status": {"Closed": 1, "Open": 2},
        })
        self.assertEqual(overview["upcoming_meetings_next_7_days"]["count"], 2)
        self.assertEqual(
            overview["upcoming_meetings_next_7_days"]["items"][0]["topic"],
            "Within window",
        )

    def test_edit_leave_history_corrects_date_and_persists(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)
        record = leaves.employee_leaves["E001"]["history"][0]
        history_id = record["history_id"]
        original_balance = leaves.employee_leaves["E001"]["balance"]
        corrected_date = date(2026, 2, 20)

        result = leaves.edit_leave_history("E001", history_id, corrected_date)

        self.assertIn("Updated leave record", result)
        self.assertEqual(record["leave_date"], corrected_date)
        self.assertEqual(leaves.employee_leaves["E001"]["balance"], original_balance)
        _, _, reloaded_leaves, _, _ = self.create_managers()
        reloaded_record = next(
            item for item in reloaded_leaves.employee_leaves["E001"]["history"]
            if item["history_id"] == history_id
        )
        self.assertEqual(reloaded_record["leave_date"], corrected_date)

    def test_removing_leave_history_restores_balance_and_persists(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)
        record = leaves.employee_leaves["E001"]["history"][0]
        history_id = record["history_id"]
        original_balance = leaves.employee_leaves["E001"]["balance"]
        original_history_count = len(leaves.employee_leaves["E001"]["history"])

        result = leaves.edit_leave_history("E001", history_id)

        self.assertIn("1 leave day was restored", result)
        self.assertEqual(leaves.employee_leaves["E001"]["balance"], original_balance + 1)
        self.assertEqual(len(leaves.employee_leaves["E001"]["history"]), original_history_count - 1)
        _, _, reloaded_leaves, _, _ = self.create_managers()
        self.assertEqual(
            reloaded_leaves.employee_leaves["E001"]["balance"],
            original_balance + 1,
        )
        self.assertNotIn(
            history_id,
            [
                item["history_id"]
                for item in reloaded_leaves.employee_leaves["E001"]["history"]
            ],
        )

    def test_edit_leave_history_rejects_unknown_record(self):
        _, employees, leaves, meetings, tickets = self.create_managers()
        seed_services(employees, leaves, meetings, tickets)

        with self.assertRaises(ValueError):
            leaves.edit_leave_history("E001", 99999, date(2026, 2, 20))


if __name__ == "__main__":
    unittest.main()
