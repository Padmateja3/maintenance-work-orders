Maintenance Work Order Management
A full-stack web application for managing maintenance work orders, assets, and technicians. The application supports work order creation, technician assignment, status tracking, search, filtering, and maintenance history.
Technology Stack

Frontend: HTML, CSS, JavaScript
Backend: Python, Flask
Database: SQLite using Python's built-in sqlite3
Validation: Pydantic v2
Testing: Python unittest
API: REST-style JSON endpoints

Features

Register and manage assets and technicians
Create and assign maintenance work orders
Track work order status and priority
Search, filter, sort, and paginate work orders
View asset maintenance history
Maintain an audit trail of work order changes
Validate requests and return structured API errors
Enforce business rules in the service layer and database
Run automated unit and API tests

Business Rules

Work order numbers must be unique.
Critical-priority work orders require an assigned technician.
Completed work orders cannot be reopened.
Cancelled work orders cannot move to in-progress.
Scheduled dates cannot be in the past.
Out-of-service assets can only receive emergency maintenance types.

Database constraints and transactions help protect data integrity.
Getting Started
Requirements

Python 3.10 or later
pip

Installation on Windows
Clone the repository:
git clone https://github.com/Padmateja3/maintenance-work-orders.git
cd maintenance-work-orders

Create and activate a virtual environment:
python -m venv .venv
.\.venv\Scripts\Activate.ps1

Install dependencies:
pip install -r requirements.txt

Optionally create demo data:
python seed.py

Start the application:
python run.py

Open http://127.0.0.1:8000 in your browser.
Run the automated tests:
python -m unittest -v

API Overview



Method
Endpoint
Purpose




GET
/api/work-orders
List and filter work orders


POST
/api/work-orders
Create a work order


GET
/api/work-orders/{id}
Get work order details


PUT
/api/work-orders/{id}
Update a work order


GET
/api/work-orders/{id}/events
View work order audit history


GET
/api/assets
List assets


POST
/api/assets
Register an asset


GET
/api/technicians
List technicians


POST
/api/technicians
Register a technician


GET
/api/maintenance-types
List maintenance types



Database Design
The application uses SQLite with tables for:

Assets
Technicians
Maintenance types
Work orders
Work order events

Foreign keys, unique constraints, validation rules, indexes, and transactions support data integrity.
Testing
Automated tests cover business rules, API behavior, database operations, and concurrency scenarios.
Limitations
This project is intended as a software engineering assessment and demonstration. It does not currently include authentication or authorization. SQLite and the Flask development server are suitable for local assessment use; a production deployment would require additional security, a production WSGI server, and an appropriate database strategy.
Repository
View the source code on GitHub
