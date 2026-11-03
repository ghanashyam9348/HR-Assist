from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Dict, Optional


def _meeting_datetime(meeting: Dict[str, str]) -> Optional[datetime]:
    meeting_date = meeting.get("date")
    if not meeting_date:
        return None

    try:
        parsed_date = datetime.fromisoformat(meeting_date)
    except ValueError:
        return None

    if "T" in meeting_date:
        return parsed_date.replace(tzinfo=None)

    meeting_time = meeting.get("time", "00:00")
    try:
        parsed_time = time.fromisoformat(meeting_time)
    except ValueError:
        return None
    return datetime.combine(parsed_date.date(), parsed_time)


def build_hr_overview(
    employee_manager,
    leave_manager,
    meeting_manager,
    ticket_manager,
    today: Optional[date] = None,
) -> Dict[str, object]:
    today = today or date.today()
    employees = employee_manager.employees
    manager_ids = {
        manager_id
        for manager_id in employee_manager.manager_map.values()
        if manager_id in employees
    }

    leave_balances = [
        record["balance"]
        for record in leave_manager.employee_leaves.values()
    ]
    tickets_by_status = Counter(
        ticket["status"] for ticket in ticket_manager.tickets
    )
    upcoming_meetings = []
    start = datetime.combine(today, time.min)
    end = start + timedelta(days=7)

    for emp_id, meetings in meeting_manager.meetings.items():
        employee = employees.get(emp_id)
        for meeting in meetings:
            meeting_dt = _meeting_datetime(meeting)
            if meeting_dt is None or not start <= meeting_dt < end:
                continue
            upcoming_meetings.append({
                "emp_id": emp_id,
                "employee_name": employee["name"] if employee else None,
                "topic": meeting.get("topic") or meeting.get("title"),
                "date": meeting_dt.isoformat(),
            })

    upcoming_meetings.sort(key=lambda meeting: (meeting["date"], meeting["emp_id"]))

    return {
        "as_of": today.isoformat(),
        "headcount": len(employees),
        "manager_count": len(manager_ids),
        "employees_without_manager": [
            {"emp_id": employee["emp_id"], "name": employee["name"]}
            for employee in employee_manager.list_employees()
            if not employee.get("manager_id")
        ],
        "leave": {
            "employees_with_balance_records": len(leave_balances),
            "total_days_available": sum(leave_balances),
            "average_days_available": (
                round(sum(leave_balances) / len(leave_balances), 2)
                if leave_balances else None
            ),
        },
        "tickets": {
            "total": len(ticket_manager.tickets),
            "by_status": dict(sorted(tickets_by_status.items())),
        },
        "upcoming_meetings_next_7_days": {
            "count": len(upcoming_meetings),
            "items": upcoming_meetings,
        },
    }
