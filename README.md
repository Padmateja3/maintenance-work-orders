🛠️ Maintenance Work Order Management

  A Full-Stack Maintenance Management Application
  
  Manage assets, technicians, work orders, assignments, and maintenance history in one place.


  
  
  
  
  


📌 Project Overview
Maintenance Work Order Management is a web application built to simplify maintenance operations. It provides a centralized way to register assets, manage technicians, create maintenance work orders, track progress, and review maintenance history.
The application combines a browser-based frontend with a Python Flask backend and an SQLite database, with an emphasis on business-rule validation, data integrity, and traceable work order updates.
✨ Key Features



Feature
Description




🏭 Asset Management
Register assets and maintain asset details and status.


👷 Technician Management
Register technicians, maintain skills, and track availability status.


📝 Work Order Management
Create, view, update, and assign maintenance work orders.


🚦 Status & Priority Tracking
Track work order progress and priority.


🔎 Search & Filtering
Search, filter, sort, and paginate work orders.


📚 Maintenance History
Review work orders and maintenance summaries for assets.


🧾 Audit Trail
Record work order creation, edits, status changes, and reassignments.


🛡️ Validation & Error Handling
Return structured errors for invalid requests and business-rule violations.


🧪 Automated Testing
Test business rules and API behavior with Python unittest.



🧰 Technology Stack



Layer
Technologies




Frontend
HTML5, CSS3, JavaScript


Backend
Python, Flask


Database
SQLite, Python sqlite3, raw SQL


Request Validation
Pydantic v2


API
JSON-based REST-style endpoints


Testing
Python unittest



⚙️ Business Rules & Data Integrity
The application enforces the following key business rules:

Unique work order numbers: Duplicate work order numbers are rejected.
Critical priority: A critical work order must have an assigned technician.
Completed work orders: Completed orders cannot be reopened.
Cancelled work orders: Cancelled orders cannot transition to in-progress.
Scheduled dates: New or rescheduled work cannot be scheduled in the past.
Out-of-service assets: Only maintenance types explicitly marked as emergency are allowed.

Database constraints, foreign keys, indexes, and transactions provide additional protection for data integrity.
🔄 Work Order Lifecycle
OPEN ──► ASSIGNED ──► IN_PROGRESS ──► COMPLETED
  │           │
  └───────────┴─────────────────────► CANCELLED

Note: Completed and cancelled work orders are terminal states.
🗄️ Database Design
The application uses SQLite with five main tables:

assets — registered assets and their status
technicians — technician details, skills, and status
maintenance_types — maintenance categories and emergency classification
work_orders — work order details, priority, assignment, and status
work_order_events — work order audit history

The schema includes relational constraints and indexes to support consistency and common query patterns.
🔌 API Overview
All API request bodies use JSON. List endpoints support pagination, and relevant endpoints support filtering.



Method
Endpoint
Purpose




GET
/api/work-orders
List, search, and filter work orders


POST
/api/work-orders
Create a work order


GET
/api/work-orders/{id}
Retrieve work order details


PUT
/api/work-orders/{id}
Update permitted work order fields


GET
/api/work-orders/{id}/events
Retrieve work order audit history


GET
/api/assets
List assets


POST
/api/assets
Register an asset


GET
/api/assets/{id}/history
View asset maintenance history


GET
/api/technicians
List technicians


POST
/api/technicians
Register a technician


GET
/api/maintenance-types
Retrieve maintenance types



Additional asset and technician detail and update endpoints are also available.
🚀 Getting Started
Prerequisites

Python 3.10 or later
pip
Git (for cloning the repository)

1. Clone the Repository
git clone https://github.com/Padmateja3/maintenance-work-orders.git
cd maintenance-work-orders

2. Create a Virtual Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

3. Install Dependencies
pip install -r requirements.txt

4. Load Optional Demo Data
python seed.py

5. Start the Application
python run.py

Open your browser and visit:
http://127.0.0.1:8000
6. Run the Automated Tests
python -m unittest -v

🧪 Testing Strategy
The test suite uses Python's built-in unittest framework and covers business-rule validation, API behavior, database operations, and concurrency scenarios.
Run all tests using:
python -m unittest -v

📁 Project Structure
maintenance-work-orders/
├── app/
│   ├── db.py
│   ├── rules.py
│   ├── schemas.py
│   ├── services.py
│   ├── routes.py
│   ├── errors.py
│   └── clock.py
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── tests/
├── seed.py
├── run.py
├── requirements.txt
└── README.md

🔐 Limitations & Future Improvements
This project is designed as a software engineering assessment and demonstration.

Authentication and authorization are not currently implemented.
The current database uses SQLite.
A production deployment would require additional security controls, a production WSGI server, and a suitable database and migration strategy.

👨‍💻 Developer
Padma Teja
🔗 Project Links

GitHub Repository: Maintenance Work Order Management



  Built with Python, Flask, SQLite, HTML, CSS, and JavaScript.

