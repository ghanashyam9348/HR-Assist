# HR-ASSIST Agentic AI System

HR ASSIST is an MCP server project that helps HR teams automate repetitive workflows such as employee onboarding, ticketing, leave handling, and meeting scheduling.

This repository contains the MCP server implementation. You can connect it to an MCP client such as Claude Desktop.

## What This Project Does

- Exposes HR operations as MCP tools.
- Supports an onboarding prompt flow for new employees.
- Sends emails through SMTP (Gmail-compatible setup shown below).
- Seeds in-memory demo data so you can test quickly.

## Project Structure

- `server.py`: MCP server entry point and tool registrations.
- `hrms/`: Managers and schemas for employees, leaves, meetings, and tickets.
- `emails.py`: SMTP email sender utility.
- `utils.py`: Seed data setup for demo/testing.
- `sample.env`: Environment variable template.

## Prerequisites

- Python 3.10+
- `uv` installed
- Claude Desktop (or another MCP client)
- Gmail account with App Password (if you want email sending)

## Local Setup

1. Clone the repository and move into the project directory.
2. Create a virtual environment and install dependencies:

```bash
uv sync
```

3. Create your local environment file:

```bash
copy sample.env .env
```

4. Update `.env` values:

```env
CB_EMAIL=your-email@gmail.com
CB_EMAIL_PWD=your-app-password
```

## MCP Server Setup (Do Not Skip)

Add this configuration to your `claude_desktop_config.json`.

Use your own local paths for `command` and project directory in `args`.

```json
{
    "mcpServers": {
        "hr-assist": {
            "command": "C:\\Users\\<your-user>\\.local\\bin\\uv",
            "args": [
                "--directory",
                "C:\\all-codes\\codebasics_course\\Gen_ai\\17_GenAi_project_3",
                "run",
                "server.py"
            ],
            "env": {
                "CB_EMAIL": "YOUR_EMAIL",
                "CB_EMAIL_PWD": "YOUR_APP_PASSWORD"
            }
        }
    }
}
```

Notes:
- Replace `YOUR_EMAIL` with your actual email.
- Replace `YOUR_APP_PASSWORD` with an email app password (not your login password).
- On Windows, ensure the `uv` path is valid on your system.

## Run Server Manually (Optional)

```bash
uv run server.py
```

The server uses `stdio` transport and is intended to be launched by an MCP client.

## Available MCP Tools

- `add_employee`
- `get_employee_details`
- `send_email`
- `create_ticket`
- `update_ticket_status`
- `list_tickets`
- `schedule_meeting`
- `get_meetings`
- `cancel_meeting`
- `get_employee_leave_balance`
- `apply_leave`
- `get_leave_history`

## Prompt Included

- `onboard_new_employee(employee_name, manager_name)`

This prompt orchestrates onboarding tasks by calling the tools above.

## Usage with Claude Desktop

1. Open Claude Desktop.
2. Click `+` and choose `Add from hr-assist`.
3. Ask for onboarding actions or use the prompt directly.

Reference UI screenshot:

<img src="Resources/image.jpg" alt="Claude desktop prompt with fields" style="width:auto;height:300px;padding-left:30px">
