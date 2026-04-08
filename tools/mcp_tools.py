import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CALENDAR_FILE = DATA_DIR / "calendar.json"
TASKS_FILE = DATA_DIR / "tasks.json"
NOTES_FILE = DATA_DIR / "notes.json"

def ensure_files():
    for f in [CALENDAR_FILE, TASKS_FILE, NOTES_FILE]:
        if not f.exists():
            f.write_text("[]")

def calendar_create_event(title, start, end, desc=""):
    ensure_files()
    data = json.loads(CALENDAR_FILE.read_text())
    data.append({"id": len(data)+1, "title": title, "start": start, "end": end, "description": desc})
    CALENDAR_FILE.write_text(json.dumps(data, indent=2))

def calendar_get_events():
    ensure_files()
    return json.loads(CALENDAR_FILE.read_text())

def task_create(title, priority, assignee=None, due_date=None):
    ensure_files()
    data = json.loads(TASKS_FILE.read_text())
    data.append({"id": len(data)+1, "title": title, "priority": priority, "assignee": assignee, "due_date": due_date, "status": "pending"})
    TASKS_FILE.write_text(json.dumps(data, indent=2))
    return data[-1]

def task_list():
    ensure_files()
    return json.loads(TASKS_FILE.read_text())

def note_create(content, tags=None):
    ensure_files()
    data = json.loads(NOTES_FILE.read_text())
    data.append({"id": len(data)+1, "content": content, "tags": tags or [], "timestamp": datetime.now().isoformat()})
    NOTES_FILE.write_text(json.dumps(data, indent=2))

def note_search(keyword):
    ensure_files()
    return [n for n in json.loads(NOTES_FILE.read_text()) if keyword.lower() in n["content"].lower()]
