from collections import defaultdict
from datetime import date
from typing import Dict, Optional
from .schemas import LeaveApplyRequest
from .database import HRDatabase


class LeaveManager:
    def __init__(self, database: Optional[HRDatabase] = None):
        self.database = database or HRDatabase()
        self.employee_leaves: Dict[str, Dict] = self.database.load_leave()
        if not isinstance(self.employee_leaves, defaultdict):
            self.employee_leaves = defaultdict(lambda: {"balance": 20, "history": []}, self.employee_leaves)

    def get_leave_balance(self, employee_id: str) -> str:
        data = self.employee_leaves.get(employee_id)
        if data:
            return f"{employee_id} has {data['balance']} leave days remaining."
        return "Employee ID not found."

    def apply_leave(self, req: LeaveApplyRequest) -> str:
        employee_id = req.emp_id
        leave_dates = [d.isoformat() for d in req.leave_dates]
        if employee_id not in self.employee_leaves:
            return "Employee ID not found."
        requested = len(leave_dates)
        available = self.employee_leaves[employee_id]["balance"]
        if available < requested:
            return f"Insufficient leave balance: requested {requested}, available {available}."
        self.employee_leaves[employee_id]["balance"] -= requested
        history = self.employee_leaves[employee_id]["history"]
        history_id = max(
            (record.get("history_id", 0) for record in history if isinstance(record, dict)),
            default=0,
        )
        request_id = max(
            (record.get("request_id", 0) for record in history if isinstance(record, dict)),
            default=0,
        ) + 1
        history.extend(
            {
                "history_id": history_id + index,
                "emp_id": employee_id,
                "leave_date": date.fromisoformat(leave_date),
                "request_id": request_id,
            }
            for index, leave_date in enumerate(leave_dates, start=1)
        )
        self.database.save_leave(self.employee_leaves)
        return (f"Leave applied for {requested} day(s). Remaining balance: "
                f"{self.employee_leaves[employee_id]['balance']}")

    def get_leave_history(self, employee_id: str) -> str:
        data = self.employee_leaves.get(employee_id)
        if data:
            hist = data['history']
            entries = [
                "history_id={0}, request_id={1}, date={2}".format(
                    record["history_id"],
                    record["request_id"],
                    record["leave_date"].strftime("%B %d, %Y"),
                )
                for record in hist
            ]
            if not entries:
                return f"No leave history found for {employee_id}."
            return f"Leave history for {employee_id}: {'; '.join(entries)}."
        return "Employee ID not found."

    def edit_leave_history(
        self,
        employee_id: str,
        history_id: int,
        new_leave_date: Optional[date] = None,
    ) -> str:
        if employee_id not in self.employee_leaves:
            raise ValueError(f"Employee ID '{employee_id}' not found.")
        if history_id <= 0:
            raise ValueError("history_id must be a positive integer.")

        history = self.employee_leaves[employee_id]["history"]
        record = next(
            (entry for entry in history if entry.get("history_id") == history_id),
            None,
        )
        if record is None:
            raise ValueError(
                f"Leave history record '{history_id}' not found for employee '{employee_id}'."
            )

        if new_leave_date is not None:
            if not isinstance(new_leave_date, date):
                raise ValueError("new_leave_date must be a valid ISO date.")
            previous_date = record["leave_date"]
            record["leave_date"] = new_leave_date
            self.database.save_leave(self.employee_leaves)
            return (
                f"Updated leave record {history_id} for {employee_id} "
                f"from {previous_date.isoformat()} to {new_leave_date.isoformat()}."
            )

        history.remove(record)
        self.employee_leaves[employee_id]["balance"] += 1
        self.database.save_leave(self.employee_leaves)
        return (
            f"Removed leave record {history_id} for {employee_id}; "
            "1 leave day was restored to the balance."
        )

if __name__ == "__main__":
    lm = LeaveManager()
    print(lm.get_leave_history("E004"))