from datetime import datetime, timezone
from typing import Dict, List, Optional
from .schemas import TicketCreate, TicketStatusUpdate
from .database import HRDatabase


class TicketManager:
    def __init__(self, database: Optional[HRDatabase] = None):
        self.database = database or HRDatabase()
        self.tickets: List[Dict[str, str]] = self.database.load_tickets()
        numeric_ids = []
        for ticket in self.tickets:
            ticket_number = ticket["ticket_id"].removeprefix("T")
            if ticket_number.isdigit():
                numeric_ids.append(int(ticket_number))
        self._next_id = max(numeric_ids, default=0) + 1

    def create_ticket(self, req: TicketCreate) -> str:
        ticket_id = f"T{self._next_id:04d}"
        ticket = {
            "ticket_id": ticket_id,
            "emp_id": req.emp_id,
            "item": req.item,
            "reason": req.reason,
            "status": "Open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        self.tickets.append(ticket)
        self.database.save_tickets(self.tickets)
        self._next_id += 1
        return f"Ticket {ticket_id} created for {req.emp_id}."

    def update_ticket_status(self, req: TicketStatusUpdate, ticket_id: str) -> str:
        for t in self.tickets:
            if t["ticket_id"] == ticket_id:
                t["status"] = req.status
                t["updated_at"] = datetime.now(timezone.utc).isoformat()
                self.database.save_tickets(self.tickets)
                return f"Ticket {ticket_id} status updated to {req.status}."
        raise ValueError(f"Ticket '{ticket_id}' not found.")

    def list_tickets(
            self,
            employee_id: Optional[str] = None,
            status: Optional[str] = None
    ) -> List[Dict[str, str]]:
        results = self.tickets
        if employee_id:
            results = [t for t in results if t["emp_id"] == employee_id]
        if status:
            results = [t for t in results if t["status"].lower() == status.lower()]
        return results
