# RecoverAI – Stage 1 Foundation

## What is RecoverAI?
RecoverAI is an internship‑selection project that will eventually provide an AI‑powered revenue‑recovery system for Razorpay merchants.  This repository contains the **foundation** – a React + Vite frontend, a FastAPI backend, and a PostgreSQL database – ready for future stages.

## Current Stage 1 Architecture
```
React (Vite)  →  FastAPI  →  PostgreSQL (Docker)
```
Only the health‑check endpoint and database connectivity are implemented at this point.

## Technology Stack (Stage 1)
- **Frontend** – React, Vite, JavaScript, Tailwind CSS (installed in the existing Vite project).
- **Backend** – Python, FastAPI, Uvicorn, Pydantic.
- **Database** – PostgreSQL (Docker), SQLAlchemy 2.x, Alembic.

## Prerequisites
- **Docker Desktop** (or Docker Engine) installed and running on Windows.
- **Python 3.10+** and a virtual environment (`backend/venv`).
- **Node 22+** for the frontend (`npm install` inside `frontend`).

## PostgreSQL (Docker) Setup
1. **Start the database**
   ```cmd
   docker compose up -d db
   ```
2. **Check that it is running / healthy**
   ```cmd
   docker compose ps
   ```
   You should see a container named `recoverai_postgres` with `State: healthy`.
3. **Stop the database** (keeps the persistent volume)
   ```cmd
   docker compose down
   ```
   The volume `postgres_data` is **not** removed, so data persists across restarts.

## Backend Environment
Create (or copy) a `.env` file inside `backend/`:
```text
DATABASE_URL=postgresql+psycopg://recoverai_user:recoverai_password@localhost:5432/recoverai
```
The provided `.env.example` contains placeholders for other secrets.

## Running the FastAPI Backend
```cmd
cd backend
venv\Scripts\activate   # Windows CMD
uvicorn app.main:app --reload --port 8000
```
The API will be reachable at `http://localhost:8000`.

## Database Connectivity Test
A minimal pytest test is located at `backend/tests/test_db_connection.py`.  To run it:
```cmd
cd backend
pytest -q backend/tests/test_db_connection.py
```
The test creates a session, executes `SELECT 1`, and asserts the result – proving that SQLAlchemy can talk to the Dockerised PostgreSQL instance.

## What is NOT Implemented Yet (Stage 1 limits)
- LangGraph / Gemini AI integration
- Razorpay APIs or webhooks
- Business models (customers, orders, payments, etc.)
- Recovery‑workflow logic, dashboards, authentication, or any other domain‑specific features.

---
*Feel free to explore the code under `backend/app/` – the `database` module contains the SQLAlchemy engine and the FastAPI `get_db` dependency ready for future routes.*
