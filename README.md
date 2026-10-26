# AI-Based Self-Healing Cloud Infrastructure

A local final-year project demonstrating server-health monitoring, Random Forest failure-risk estimation, failure simulation, alerts, recovery workflow, health verification, and a React dashboard backed by Flask and SQLite.

> **Important scope statement:** The included service metrics and default recovery adapter are simulations. The project does not monitor or restart real cloud instances. The AI model is trained on generated synthetic labels, so its scores are educational estimates—not validated production predictions.

## Features
- Flask REST API with session-based admin login and password hashing.
- React/Vite responsive dashboard with Dashboard, Servers, Monitoring, AI Prediction, Failure Simulation, Recovery, Alerts & Logs, and Settings views.
- SQLite persistence for servers, metrics, AI predictions, alerts, recovery logs, and settings.
- Actual local host CPU, memory, and disk metrics using `psutil`.
- Active HTTP(S) health checks for configured service endpoints, including response time and availability/error status.
- Periodic monitoring checks initiated by the open dashboard; a manual check is also available.
- Random Forest classifier with a generated synthetic dataset and an evaluation report.
- Failure scenarios for high CPU, high memory, high latency, high error rate, and unavailable service.
- Recovery logs and post-recovery metric verification. A failed-recovery test path preserves the Failed status.
- Input validation, API error responses, configurable risk thresholds, and automated backend tests.

## Requirements
- Python 3.11–3.13 recommended. Python 3.14 may work when compatible NumPy/scikit-learn wheels are available for your system.
- Node.js 22 LTS recommended.
- npm.
- Windows 10/11, macOS, or Linux.

## Windows setup

### Quick start (Windows)

Double-click `scripts/start_backend.bat` and `scripts/start_frontend.bat` in two separate terminal windows. On first run they create/install the local environments. Alternatively, follow the manual steps below.

## 1. Backend
Open PowerShell:

```powershell
cd D:\Downloads\self_healing_cloud_project\backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Backend health endpoint: http://localhost:5000/

The first start creates the SQLite tables, demo services, a trained model (if needed), and `model_metrics.json`. To regenerate the model and synthetic evaluation report manually, run `python ml_model.py` from the backend directory.

### 2. Frontend
Open a second PowerShell terminal:

```powershell
cd D:\Downloads\self_healing_cloud_project\frontend
npm ci
npm run dev
```

Open the local URL printed by Vite, normally http://localhost:5173.

### 3. Demo login
- Username: `admin`
- Password: `ChangeMe123!`

This is a local demo credential. Change `ADMIN_PASSWORD` and `SECRET_KEY` in the environment before exposing the app or sharing a deployment. Never use the demo credentials in production.

### 4. Run tests
In the backend virtual environment:

```powershell
python -m pytest -q
```

Tests use a temporary SQLite database and do not restart real services.

## Configuration
The backend reads environment variables:
- `ADMIN_USERNAME` — demo administrator name (default `admin`).
- `ADMIN_PASSWORD` — demo password (default `ChangeMe123!`; change it).
- `SECRET_KEY` — Flask session secret (set a long random value).
- `DATABASE_PATH` — optional SQLite file path.
- `DATABASE_URL` — optional SQLAlchemy database URL; takes precedence over `DATABASE_PATH`.
- `FRONTEND_ORIGIN` — allowed frontend origins, comma-separated (default `http://localhost:5173`).
- `COOKIE_SECURE` — set `true` only when serving over HTTPS.
- `HOST` and `PORT` — bind address/port (Docker Compose sets `HOST=0.0.0.0`).

`backend/.env.example` is a template. For simple local execution, copy `.env.example` to `.env` and edit the values; the backend loads `.env` with python-dotenv.

## Demonstration workflow
1. Sign in.
2. Open **Failure Simulation**, select a service and a scenario, then trigger it.
3. The API records simulated metrics, generates a model prediction, writes an alert and event log, and—if enabled—runs the simulated recovery adapter.
4. The adapter restores the demo metric values and performs a threshold-based verification.
5. Open **Recovery** and **Alerts & Logs** to review outcomes.
6. Disable automatic recovery in **Settings** and test a failure manually.
7. Use **Test failed recovery path** to confirm that failed verification keeps the service Failed.

## Main API routes
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- `GET/POST /api/servers`, `GET/PUT/DELETE /api/servers/<id>`
- `GET/POST /api/servers/<id>/metrics`
- `POST /api/servers/<id>/simulate-failure`, `POST /api/servers/<id>/recover`
- `GET /api/dashboard`, `GET /api/dashboard/history`
- `POST /api/ai/predict`, `GET /api/ai/predictions`, `GET /api/ai/model-info`
- `GET /api/alerts`, `PATCH /api/alerts/<id>/resolve`
- `GET /api/recovery-logs`, `GET/PUT /api/settings`
- `GET /api/monitoring/current`, `POST /api/monitoring/check`
- `POST /api/simulation/start`, `POST /api/simulation/stop`, `GET /api/simulation/status`

Protected endpoints require a logged-in session cookie.

## Project layout
```text
self_healing_cloud_project/
  backend/
    app.py
    database.py
    models.py
    ml_model.py
    monitoring.py
    recovery.py
    requirements.txt
    tests/
  frontend/
    package.json
    package-lock.json
    src/
  docs/
  scripts/
  README.md
```

## Known limitations / future work
- Local host CPU/memory/disk values are real metrics from the machine running Flask. Configured HTTP(S) service endpoints are actively health-checked for availability and response time. Per-service CPU/memory/disk metrics remain simulated unless a service agent or cloud monitoring integration is added.
- Recovery is intentionally simulated and cannot stop/start actual cloud infrastructure.
- Model labels are generated from synthetic rules; model metrics do not measure real-world predictive performance.
- Authentication is a small local-project session implementation, not a complete enterprise identity system.
- For a production extension, implement a least-privilege adapter for an explicitly allowlisted test container or cloud resource, real telemetry collection, incident data, CSRF protections, HTTPS, audit retention, and deployment-specific secret management.
