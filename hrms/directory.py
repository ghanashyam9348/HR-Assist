from typing import Dict, List


def build_employee_directory(
    employee_manager,
    leave_manager,
    meeting_manager,
    ticket_manager,
    include_details: bool = False,
) -> List[Dict]:
    directory = []
    employees = employee_manager.employees

    for employee in employee_manager.list_employees():
        emp_id = employee["emp_id"]
        manager_id = employee.get("manager_id")
        manager_record = employees.get(manager_id) if manager_id else None
        employee_entry = {
            **employee,
            "manager": (
                {
                    "emp_id": manager_id,
                    "name": manager_record["name"],
                    "email": manager_record.get("email"),
                }
                if manager_record else None
            ),
        }

        if include_details:
            leave_record = leave_manager.employee_leaves.get(emp_id)
            leave_history = []
            leave_balance = None
            if leave_record is not None:
                leave_balance = leave_record["balance"]
                for entry in leave_record["history"]:
                    leave_date = entry["leave_date"]
                    leave_history.append({
                        "history_id": entry.get("history_id"),
                        "request_id": entry.get("request_id"),
                        "leave_date": (
                            leave_date.isoformat()
                            if hasattr(leave_date, "isoformat")
                            else str(leave_date)
                        ),
                    })

            employee_entry.update({
                "direct_reports": [
                    {
                        "emp_id": report_id,
                        "name": employees[report_id]["name"],
                        "email": employees[report_id].get("email"),
                    }
                    for report_id in employee_manager.get_direct_reports(emp_id)
                ],
                "leave": {
                    "balance": leave_balance,
                    "history": leave_history,
                },
                "meetings": meeting_manager.get_meetings(emp_id),
                "tickets": ticket_manager.list_tickets(employee_id=emp_id),
            })

        directory.append(employee_entry)

    return directory
