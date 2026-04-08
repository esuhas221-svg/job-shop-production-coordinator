# Job Shop Production Coordinator – Multi‑Agent AI System

## Overview
An intelligent, API‑first production coordination system that automates order‑to‑dispatch workflows for a small manufacturing job shop. It uses a primary agent that orchestrates sub‑agents (Order, Material, Planning, Scheduler, Production, Dispatch) to handle order intake, material checks, planning, scheduling, work orders, production simulation, and dispatch.

## Features
- Multi‑agent coordination with n8n‑style workflow diagram and glowing nodes
- Gantt chart for workstation vs. date scheduling
- Factory simulation with continuous part flow
- Database toggle (SQLite / AlloyDB)
- REST API with Swagger docs
- Deployed on Google Cloud Run

## Live Demo
[https://your-cloud-run-url](https://your-cloud-run-url)

## Tech Stack
- FastAPI, Uvicorn
- SQLite / AlloyDB
- HTML/CSS/JS dashboard
- MCP tools (Calendar, Task Manager, Notes)

## Run Locally
```bash
git clone <your-repo-url>
cd job-shop-production-coordinator
pip install -r requirements.txt
python database/init_master_data.py
uvicorn api.main:app --reload
Environment Variables
Variable	Description	Default
DB_TYPE	sqlite or alloydb	sqlite
ALLOYDB_HOST	AlloyDB IP	–
ALLOYDB_PASSWORD	AlloyDB password	–
API Endpoints
POST /agent/command – natural language command

GET /orders – list orders

GET /inventory – current stock

GET /tasks – MCP tasks

GET /calendar – MCP calendar

GET /notes – MCP notes

GET /gantt_data – work orders for Gantt

POST /reset – clear all orders

POST /toggle_database?db_type=... – switch database

Judges’ Requirements Met
✅ Primary agent + sub‑agents

✅ Database storage & retrieval

✅ MCP tools integration

✅ Multi‑step workflows

✅ API‑based deployment

License
MIT
