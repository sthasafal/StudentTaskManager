# Student Task Manager

A polished academic productivity web app with user accounts, private task boards, and full CRUD task management.

## Features

- Register, sign in, and sign out
- Private tasks for each user
- Create, read, update, complete, and delete tasks
- Course, description, due date, priority, and status fields
- Kanban-style board inspired by modern productivity dashboards
- Search, status filter, priority filter, course summary, and dashboard counts
- SQLite database with no external dependencies

## Demo Account

```text
Email: demo@student.local
Password: demo1234
```

## Run

```powershell
cd "C:\Users\shre4420\Documents\lab project demo\lab project demo"
python server.py
```

Open:

```text
http://127.0.0.1:8001
```

## Documents
Any documents related to this porject is on the Docs folders


## Reset Database

Stop the server, delete `mvp_task_manager.db`, then run `python server.py` again.
