# API reference

All `/api/*` endpoints except `/api/auth/login` require a session cookie.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/login` | Create admin session |
| POST | `/api/auth/logout` | Clear session |
| GET | `/api/auth/me` | Check current session |
| GET, POST | `/api/servers` | List/create services |
| GET, PUT, DELETE | `/api/servers/<id>` | Read/update/delete service |
| GET, POST | `/api/servers/<id>/metrics` | Read or submit metrics |
| POST | `/api/servers/<id>/simulate-failure` | Trigger a simulated failure scenario |
| POST | `/api/servers/<id>/recover` | Request recovery; `force_failure` is for testing |
| GET | `/api/dashboard` | Summary counts and recent events |
| GET | `/api/dashboard/history` | Recent metric samples |
| POST | `/api/ai/predict` | Predict risk for `server_id` or five metrics |
| GET | `/api/ai/predictions` | Prediction history |
| GET | `/api/ai/model-info` | Model and synthetic evaluation report |
| GET | `/api/alerts` | List alerts; optional `?resolved=true/false` |
| PATCH | `/api/alerts/<id>/resolve` | Resolve an alert |
| GET | `/api/recovery-logs` | Recovery and incident logs |
| GET, PUT | `/api/settings` | Read/update validated policy settings |
| GET | `/api/monitoring/current` | Current demo metrics |
| POST | `/api/monitoring/check` | Evaluate all services and record samples |
| POST | `/api/simulation/start` | Trigger an event-based simulation |
| POST | `/api/simulation/stop` | Confirm no continuous simulation loop is active |
| GET | `/api/simulation/status` | Simulation status |

Metrics request keys are `cpu`, `memory`, `disk`, `response_time`, and `error_rate`. Prediction inputs are `cpu_usage`, `memory_usage`, `disk_usage`, `response_time`, and `error_rate`.
