from emails import EmailSender
from hrms import *
from typing import List, Dict, Optional
from mcp.server.fastmcp import FastMCP
from datetime import date
import json
import hmac
import os
import uvicorn

# load the env
from dotenv import load_dotenv
load_dotenv()

from utils import seed_services
from hrms.database import HRDatabase
from hrms.directory import build_employee_directory
from hrms.policy_rag import OpenAIPolicyRAG
from hrms.reports import build_hr_overview

hr_database = HRDatabase()
employee_manager = EmployeeManager(hr_database)
meeting_manager = MeetingManager(hr_database)
leave_manager = LeaveManager(hr_database)
ticket_manager = TicketManager(hr_database)
policy_rag = OpenAIPolicyRAG()

seed_services(employee_manager, leave_manager, meeting_manager, ticket_manager)

emailer = EmailSender(
    smtp_server="smtp.gmail.com",
    port=587,
    username=os.getenv("CB_EMAIL"),
    password=os.getenv("CB_EMAIL_PWD"),
    use_tls=True
)

mcp = FastMCP("hr-assist")

@mcp.tool()
def search_hr_policies(question: str, top_k: int = 3, category: Optional[str] = None) -> str:
    """Retrieve semantically relevant synthetic policy passages and citations."""
    results = policy_rag.search(question, top_k=top_k, category=category)
    return json.dumps({
        "question": question,
        "results": results,
        "message": (
            "These are synthetic demonstrations, not authoritative HR guidance."
            if results else
            "No matching policy passages were found. Do not infer a policy answer; ask HR."
        ),
    }, ensure_ascii=False)

@mcp.tool()
def answer_hr_policy(question: str, top_k: int = 3, category: Optional[str] = None) -> str:
    """Answer an HR policy question from retrieved synthetic policy passages."""
    return json.dumps(
        policy_rag.answer(question, top_k=top_k, category=category),
        ensure_ascii=False,
    )

class BearerTokenMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        authorization = next(
            (value for name, value in scope.get("headers", []) if name.lower() == b"authorization"),
            b"",
        )
        scheme, separator, supplied_token = authorization.partition(b" ")
        if (
            not separator
            or scheme.lower() != b"bearer"
            or not hmac.compare_digest(supplied_token, self.token)
        ):
            body = b'{"error":"Unauthorized"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        await self.app(scope, receive, send)

@mcp.tool()
def add_employee(emp_name:str, manager_id:str, email:str) -> str:
    """
    Add a new employee to the hrms system.
    :param emp_name: Employee name
    :param manager_id: Manager ID (optional)
    :return: Confirmation message
    """
    emp = EmployeeCreate(
        emp_id=employee_manager.get_next_emp_id(),
        name=emp_name,
        manager_id=manager_id,
        email=email
    )
    employee_manager.add_employee(emp)
    return f"Employee {emp_name} added successfully."

@mcp.tool()
def get_employee_details(name: str) -> Dict[str, str]:
    """
    Get employee details by name.
    :param name: Name of the employee
    :return: Employee ID and manager ID
    """
    matches = employee_manager.search_employee_by_name(name)

    if len(matches) == 0:
        raise ValueError(f"No employees found with name {name}.")

    emp_id = matches[0]
    emp_details = employee_manager.get_employee_details(emp_id)
    return emp_details

@mcp.tool()
def list_employees(include_details: bool = False) -> Dict[str, object]:
    """List employees with IDs, names, email, and managers; optionally include HR records."""
    employees = build_employee_directory(
        employee_manager,
        leave_manager,
        meeting_manager,
        ticket_manager,
        include_details=include_details,
    )
    return {"count": len(employees), "employees": employees}

@mcp.tool()
def search_employees(query: str) -> Dict[str, object]:
    """Search employees by ID, name, or email and include their manager."""
    matches = employee_manager.search_employees(query)
    employees = []
    for employee in matches:
        manager_id = employee.get("manager_id")
        manager = employee_manager.employees.get(manager_id) if manager_id else None
        employees.append({
            **employee,
            "manager": (
                {
                    "emp_id": manager_id,
                    "name": manager["name"],
                    "email": manager.get("email"),
                }
                if manager else None
            ),
        })
    return {"count": len(employees), "employees": employees}

@mcp.tool()
def get_hr_overview() -> Dict[str, object]:
    """Summarize headcount, managers, leave, ticket statuses, and upcoming meetings."""
    return build_hr_overview(
        employee_manager,
        leave_manager,
        meeting_manager,
        ticket_manager,
    )

@mcp.tool()
def send_email(to_emails: List[str], subject: str, body: str, html: bool = False) -> None:
    emailer.send_email(subject, body, to_emails, from_email=emailer.username, html=html)
    return "Email sent successfully."


@mcp.tool()
def create_ticket(emp_id: str, item: str, reason:str) -> str:
    """
    Create a ticket for buying required items for an employee.
    :param emp_id: Employee ID
    :param item: Item requested (Laptop, ID Card, etc.)
    :param reason: Reason for the request
    :return: Confirmation message
    """
    ticket_req = TicketCreate(emp_id=emp_id, item=item, reason=reason)
    return ticket_manager.create_ticket(ticket_req)

@mcp.tool()
def update_ticket_status(ticket_id: str, status: str) -> str:
    """
    Update the status of a ticket.
    :param ticket_id: Ticket ID
    :param status: New status of the ticket
    :return: Confirmation message
    """
    ticket_status_update = TicketStatusUpdate(status=status)
    return ticket_manager.update_ticket_status(ticket_status_update, ticket_id)

@mcp.tool()
def list_tickets(employee_id: str, status: str) -> str:
    """
    List tickets for an employee with optional status filter.
    :param employee_id: Employee ID
    :param status: Ticket status (optional)
    :return: List of tickets
    """
    return ticket_manager.list_tickets(employee_id=employee_id, status=status)


@mcp.tool()
def schedule_meeting(employee_id: str, meeting_datetime: str, topic: str) -> str:
    """
    Schedule a meeting for an employee.
    :param employee_id: Employee ID
    :param meeting_datetime: Date and time of the meeting in python datetime format
    :param topic: Topic of the meeting
    :return: Confirmation message
    """
    meeting_req = MeetingCreate(
        emp_id=employee_id,
        meeting_dt=datetime.fromisoformat(meeting_datetime),
        topic=topic
    )
    return meeting_manager.schedule_meeting(meeting_req)


@mcp.tool()
def get_meetings(employee_id: str) -> str:
    """
    Get the list of meetings scheduled for an employee.
    :param employee_id: Employee ID
    :return: List of meetings
    """
    return meeting_manager.get_meetings(employee_id)


@mcp.tool()
def cancel_meeting(employee_id: str, meeting_datetime: str, topic: str) -> str:
    """
    Cancel a scheduled meeting for an employee.
    :param employee_id: Employee ID
    :param meeting_datetime: Date and time of the meeting in python datetime format
    :param topic: Topic of the meeting (optional)
    :return: Confirmation message
    """
    meeting_req = MeetingCancelRequest(
        emp_id=employee_id,
        meeting_dt=meeting_datetime,
        topic=topic
    )
    return meeting_manager.cancel_meeting(meeting_req)


@mcp.tool()
def get_employee_leave_balance(emp_id: str) -> str:
    """
    Get the leave balance of an employee.
    :param emp_id: Employee ID
    :return: Leave balance message
    """
    return leave_manager.get_leave_balance(emp_id)

@mcp.tool()
def apply_leave(emp_id: str, leave_dates: list) -> str:
    """
    Apply for leave for an employee.
    :param emp_id: Employee ID
    :param leave_dates: List of leave dates
    :return: Leave application status message
    """
    req = LeaveApplyRequest(emp_id=emp_id, leave_dates=leave_dates)
    return leave_manager.apply_leave(req)


@mcp.tool()
def get_leave_history(emp_id: str) -> str:
    """
    Get the leave history of an employee.
    :param emp_id: Employee ID
    :return: Leave history message
    """
    return leave_manager.get_leave_history(emp_id)

@mcp.tool()
def edit_leave_history(
    emp_id: str,
    history_id: int,
    new_leave_date: Optional[str] = None,
) -> str:
    """Correct a leave date, or remove that leave day and restore one balance day."""
    parsed_leave_date = date.fromisoformat(new_leave_date) if new_leave_date else None
    return leave_manager.edit_leave_history(
        emp_id,
        history_id,
        new_leave_date=parsed_leave_date,
    )


@mcp.prompt("onboard_new_employee")
def onboard_new_employee(employee_name: str, manager_name: str):
    return f"""Onboard a new employee with the following details:
    - Name: {employee_name}
    - Manager Name: {manager_name}
    Steps to follow:
    - Add the employee to the HRMS system.
    - Send a welcome email to the employee with their login credentials. (Format: employee_name@atliq.com)
    - Notify the manager about the new employee's onboarding.
    - Raise tickets for a new laptop, id card, and other necessary equipment.
    - Schedule an introductory meeting between the employee and the manager.
    """



if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "streamable-http":
        auth_token = os.getenv("MCP_AUTH_TOKEN")
        if not auth_token:
            raise RuntimeError("MCP_AUTH_TOKEN is required for streamable HTTP transport.")

        app = BearerTokenMiddleware(mcp.streamable_http_app(), auth_token)
        uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
    else:
        raise ValueError(f"Unsupported MCP_TRANSPORT: {transport}")
