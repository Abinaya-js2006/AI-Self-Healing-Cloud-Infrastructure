# Architecture

React/Vite UI → Flask REST API → validation and policy services → SQLAlchemy/SQLite (including a users table with hashed passwords). The AI module loads a Random Forest model and estimates risk from CPU, memory, disk, response time, and error rate. The monitoring module evaluates configurable thresholds and deduplicates unresolved alerts. The recovery adapter only changes demo metrics, records each stage, and verifies the restored metrics against configured thresholds. It intentionally does not execute shell commands or control real cloud instances.

## End-to-end flow

1. An operator triggers a demo failure scenario.
2. The API stores metric history, creates a model prediction and alert, and logs the incident.
3. If automatic recovery is enabled, the simulated adapter sets an intermediate Recovering status, restores safe sample metrics, and evaluates them against thresholds.
4. The service becomes Healthy only if verification passes. A forced failed-recovery test leaves it Failed and writes a critical alert.
5. The dashboard reads persisted API data and refreshes periodically.
