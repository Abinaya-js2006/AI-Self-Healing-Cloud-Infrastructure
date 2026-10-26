"""Flask API for the AI-based self-healing cloud demo."""
import json
import os
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request, session
from flask_cors import CORS
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

from database import db
from models import User, Server, Metric, RecoveryLog, Alert, Prediction, AppSetting
from ml_model import predict_failure, model_info
from monitoring import (validate_metrics, save_metric, evaluate_server, upsert_alert,
                         is_http_endpoint, probe_http_service, collect_host_metrics)
from recovery import recover_server, log_event


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DEFAULT_SETTINGS = {
    "auto_recovery_enabled": True,
    "monitoring_interval_seconds": 5,
    "cpu_warning": 80, "memory_warning": 85, "disk_warning": 90,
    "response_warning_ms": 800, "error_warning_percent": 10,
    "cpu_critical": 95, "memory_critical": 95, "disk_critical": 97,
    "response_critical_ms": 2000, "error_critical_percent": 20,
}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def json_error(message, status=400):
    return jsonify({"error": message}), status


def create_app(test_config=None):
    app = Flask(__name__)
    db_path = os.environ.get("DATABASE_PATH", str(BASE_DIR / "self_healing_cloud.db"))
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-demo-change-this-secret"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL") or
            "sqlite:///" + Path(db_path).resolve().as_posix(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    CORS(app, supports_credentials=True, origins=os.environ.get(
        "FRONTEND_ORIGIN", "http://localhost:5173"
    ).split(","), allow_headers=["Content-Type"], methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    db.init_app(app)

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("authenticated"):
                return json_error("Authentication required. Please log in.", 401)
            return fn(*args, **kwargs)
        return wrapped

    def get_settings():
        settings = dict(DEFAULT_SETTINGS)
        for row in AppSetting.query.all():
            try:
                settings[row.key] = json.loads(row.value)
            except (ValueError, TypeError):
                settings[row.key] = row.value
        return settings

    def save_settings(values):
        for key, value in values.items():
            row = db.session.get(AppSetting, key)
            encoded = json.dumps(value)
            if row:
                row.value = encoded
                row.updated_at = utcnow()
            else:
                db.session.add(AppSetting(key=key, value=encoded))
        db.session.commit()

    def save_prediction(server):
        metrics = {
            "cpu_usage": server.cpu_usage, "memory_usage": server.memory_usage,
            "disk_usage": server.disk_usage, "response_time": server.response_time,
            "error_rate": server.error_rate,
        }
        probability, risk = predict_failure(metrics)
        server.failure_probability = probability
        server.ai_risk = risk
        factors = []
        if server.cpu_usage >= 80: factors.append("CPU utilization is elevated")
        if server.memory_usage >= 85: factors.append("Memory utilization is elevated")
        if server.disk_usage >= 90: factors.append("Disk utilization is elevated")
        if server.response_time >= 800: factors.append("Response time is elevated")
        if server.error_rate >= 10: factors.append("Error rate is elevated")
        explanation = "; ".join(factors) if factors else "No configured metric threshold is currently elevated."
        pred = Prediction(server_id=server.id, probability=probability, risk=risk,
                          explanation=explanation)
        db.session.add(pred)
        return pred

    @app.get("/")
    def health():
        return jsonify({"message": "Self-Healing Cloud API is running",
                        "database": "connected", "mode": "local demo",
                        "authentication": "enabled"})

    @app.post("/api/auth/login")
    def login():
        data = request.get_json(silent=True) or {}
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        expected_user = os.environ.get("ADMIN_USERNAME", "admin")
        user = User.query.filter_by(username=username).first()
        if username != expected_user or user is None or not check_password_hash(user.password_hash, password):
            return json_error("Invalid username or password", 401)
        session.clear()
        session["authenticated"] = True
        session["username"] = username
        return jsonify({"message": "Login successful", "username": username})

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify({"message": "Logged out"})

    @app.get("/api/auth/me")
    def me():
        if not session.get("authenticated"):
            return json_error("Not authenticated", 401)
        return jsonify({"authenticated": True, "username": session.get("username", "admin")})

    @app.get("/api/servers")
    @login_required
    def get_servers():
        return jsonify([s.to_dict() for s in Server.query.order_by(Server.id.asc()).all()])

    @app.post("/api/servers")
    @login_required
    def add_server():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        ip = str(data.get("ip_address", "")).strip()
        if not name or not ip:
            return json_error("name and ip_address are required")
        if len(name) > 100 or len(ip) > 500:
            return json_error("name must be <= 100 chars and ip_address <= 500 chars")
        if Server.query.filter_by(name=name).first():
            return json_error("A server with this name already exists", 409)
        try:
            metrics = validate_metrics(data)
        except ValueError as exc:
            return json_error(str(exc))
        server = Server(name=name, ip_address=ip, last_checked=utcnow())
        for attr, value in metrics.items():
            setattr(server, attr, value)
        db.session.add(server)
        db.session.flush()
        save_metric(server)
        save_prediction(server)
        db.session.commit()
        return jsonify({"message": "Server added", "server": server.to_dict()}), 201

    @app.get("/api/servers/<int:server_id>")
    @login_required
    def get_server(server_id):
        server = db.session.get(Server, server_id)
        return jsonify(server.to_dict()) if server else json_error("Server not found", 404)

    @app.put("/api/servers/<int:server_id>")
    @login_required
    def update_server(server_id):
        server = db.session.get(Server, server_id)
        if not server: return json_error("Server not found", 404)
        data = request.get_json(silent=True) or {}
        if "name" in data:
            name = str(data["name"]).strip()
            other = Server.query.filter(Server.name == name, Server.id != server_id).first()
            if not name or other: return json_error("Invalid or duplicate server name")
            server.name = name
        if "ip_address" in data:
            ip = str(data["ip_address"]).strip()
            if not ip: return json_error("ip_address cannot be empty")
            if len(ip) > 500: return json_error("ip_address must be <= 500 chars")
            server.ip_address = ip
        try:
            metrics = validate_metrics(data)
        except ValueError as exc:
            return json_error(str(exc))
        for attr, value in metrics.items(): setattr(server, attr, value)
        server.last_checked = utcnow()
        save_metric(server)
        save_prediction(server)
        db.session.commit()
        return jsonify({"message": "Server updated", "server": server.to_dict()})

    @app.delete("/api/servers/<int:server_id>")
    @login_required
    def delete_server(server_id):
        server = db.session.get(Server, server_id)
        if not server: return json_error("Server not found", 404)
        Metric.query.filter_by(server_id=server_id).delete(synchronize_session=False)
        RecoveryLog.query.filter_by(server_id=server_id).delete(synchronize_session=False)
        Alert.query.filter_by(server_id=server_id).delete(synchronize_session=False)
        Prediction.query.filter_by(server_id=server_id).delete(synchronize_session=False)
        db.session.delete(server)
        db.session.commit()
        return jsonify({"message": "Server deleted"})

    @app.post("/api/seed")
    @login_required
    def seed_servers():
        if Server.query.count():
            return jsonify({"message": "Demo servers already exist", "count": Server.query.count()})
        examples = [
            ("server-01", "demo://server-01", 42, 38, 45, 120, 1),
            ("server-02", "demo://server-02", 67, 61, 55, 180, 3),
            ("server-03", "demo://server-03", 88, 82, 68, 450, 8),
            ("server-04", "demo://server-04", 96, 91, 78, 850, 15),
            ("server-05", "demo://server-05", 36, 41, 39, 100, 1),
        ]
        for name, ip, cpu, mem, disk, response, error in examples:
            s = Server(name=name, ip_address=ip, cpu_usage=cpu, memory_usage=mem,
                       disk_usage=disk, response_time=response, error_rate=error,
                       status="Healthy", last_checked=utcnow())
            db.session.add(s)
            db.session.flush()
            evaluation = evaluate_server(s, get_settings())
            s.status = "Failed" if evaluation["critical"] else ("Warning" if evaluation["warning"] else "Healthy")
            save_metric(s)
            save_prediction(s)
            if evaluation["warning"] or evaluation["critical"]:
                sev = "Critical" if evaluation["critical"] else "Warning"
                upsert_alert(s, sev, "Server health warning", "; ".join(evaluation["factors"]))
        db.session.commit()
        return jsonify({"message": "Five demo servers created. Metrics are simulated.", "count": 5}), 201

    @app.get("/api/servers/<int:server_id>/metrics")
    @login_required
    def get_metrics(server_id):
        if not db.session.get(Server, server_id): return json_error("Server not found", 404)
        rows = Metric.query.filter_by(server_id=server_id).order_by(Metric.timestamp.desc()).limit(100).all()
        return jsonify([row.to_dict() for row in reversed(rows)])

    @app.post("/api/servers/<int:server_id>/metrics")
    @login_required
    def add_metric(server_id):
        server = db.session.get(Server, server_id)
        if not server: return json_error("Server not found", 404)
        data = request.get_json(silent=True) or {}
        try:
            metrics = validate_metrics(data)
        except ValueError as exc:
            return json_error(str(exc))
        if not metrics: return json_error("At least one metric is required")
        for attr, value in metrics.items(): setattr(server, attr, value)
        server.last_checked = utcnow()
        settings = get_settings()
        evaluation = evaluate_server(server, settings)
        server.status = "Failed" if evaluation["critical"] else ("Warning" if evaluation["warning"] else "Healthy")
        pred = save_prediction(server)
        save_metric(server)
        if evaluation["warning"] or evaluation["critical"]:
            severity = "Critical" if evaluation["critical"] else "Warning"
            upsert_alert(server, severity, "Server health warning", "; ".join(evaluation["factors"]))
        if evaluation["critical"] and settings.get("auto_recovery_enabled", True):
            db.session.commit()
            if is_http_endpoint(server.ip_address):
                log_event(server, "Automatic recovery skipped: no real restart adapter is configured for this HTTP endpoint", "Skipped")
                upsert_alert(server, "Critical", "Recovery adapter not configured",
                             "The endpoint can be monitored, but no restart adapter is configured. The service remains unhealthy until a real health check passes.")
                db.session.commit()
                return jsonify({"message": "Critical condition detected; no real recovery adapter is configured",
                                "server": server.to_dict(), "recovery": {"success": False, "mode": "not-configured"},
                                "prediction": pred.to_dict()}), 200
            result = recover_server(server, thresholds=settings)
            return jsonify({"message": "Critical condition detected", "server": result["server"],
                            "recovery": result, "prediction": pred.to_dict()}), 200
        db.session.commit()
        return jsonify({"message": "Metrics saved", "server": server.to_dict(),
                        "prediction": pred.to_dict(), "evaluation": evaluation}), 201

    @app.post("/api/servers/<int:server_id>/simulate-failure")
    @login_required
    def simulate_failure(server_id):
        server = db.session.get(Server, server_id)
        if not server: return json_error("Server not found", 404)
        data = request.get_json(silent=True) or {}
        scenario = data.get("scenario", "critical")
        scenarios = {
            "cpu": {"cpu": 99, "memory": 45, "disk": 50, "response_time": 250, "error_rate": 2},
            "memory": {"cpu": 40, "memory": 99, "disk": 50, "response_time": 300, "error_rate": 2},
            "latency": {"cpu": 45, "memory": 50, "disk": 45, "response_time": 3500, "error_rate": 5},
            "errors": {"cpu": 45, "memory": 50, "disk": 45, "response_time": 500, "error_rate": 35},
            "unavailable": {"cpu": 100, "memory": 100, "disk": 99, "response_time": 60000, "error_rate": 100},
            "critical": {"cpu": 100, "memory": 98, "disk": 98, "response_time": 5000, "error_rate": 35},
        }
        if scenario not in scenarios: return json_error("Unknown scenario")
        for key, value in scenarios[scenario].items():
            setattr(server, {"cpu":"cpu_usage","memory":"memory_usage","disk":"disk_usage",
                             "response_time":"response_time","error_rate":"error_rate"}[key], value)
        server.status = "Failed"
        server.last_checked = utcnow()
        pred = save_prediction(server)
        save_metric(server)
        upsert_alert(server, "Critical", "Simulated server failure",
                     f"Scenario '{scenario}' was triggered. Metrics are simulated, not from a real cloud server.")
        log_event(server, f"Failure scenario simulated: {scenario}", "Critical")
        settings = get_settings()
        db.session.commit()
        recovery_result = None
        if settings.get("auto_recovery_enabled", True):
            if is_http_endpoint(server.ip_address):
                log_event(server, "Simulated failure did not restart the real HTTP endpoint; no restart adapter is configured", "Skipped")
                recovery_result = {"triggered": False, "success": False, "mode": "not-configured",
                                  "message": "The failure is simulated. No real HTTP service restart adapter is configured."}
            else:
                recovery_result = recover_server(server, thresholds=settings)
        else:
            server.status = "Failed"
        db.session.commit()
        return jsonify({"message": f"Scenario '{scenario}' simulated",
                        "server": server.to_dict(), "prediction": pred.to_dict(),
                        "recovery": recovery_result}), 200

    @app.post("/api/servers/<int:server_id>/recover")
    @login_required
    def recover(server_id):
        server = db.session.get(Server, server_id)
        if not server: return json_error("Server not found", 404)
        data = request.get_json(silent=True) or {}
        if is_http_endpoint(server.ip_address) and not data.get("force_failure", False):
            return jsonify({"error": "This is an HTTP(S) endpoint. A real restart adapter is not configured, so the service cannot be marked healthy by simulated recovery.",
                            "server": server.to_dict()}), 409
        result = recover_server(server, force_failure=bool(data.get("force_failure", False)),
                                thresholds=get_settings())
        return jsonify({"message": result["message"], "recovery": result,
                        "server": result.get("server", server.to_dict())}), 200 if result.get("success") else 409

    @app.get("/api/recovery-logs")
    @login_required
    def get_recovery_logs():
        limit = min(max(request.args.get("limit", default=100, type=int), 1), 500)
        rows = RecoveryLog.query.order_by(RecoveryLog.timestamp.desc()).limit(limit).all()
        return jsonify([r.to_dict() for r in rows])

    @app.get("/api/alerts")
    @login_required
    def get_alerts():
        query = Alert.query
        if request.args.get("resolved") in ("true", "false"):
            query = query.filter_by(resolved=request.args.get("resolved") == "true")
        return jsonify([a.to_dict() for a in query.order_by(Alert.created_at.desc()).limit(300).all()])

    @app.patch("/api/alerts/<int:alert_id>/resolve")
    @login_required
    def resolve_alert(alert_id):
        alert = db.session.get(Alert, alert_id)
        if not alert: return json_error("Alert not found", 404)
        alert.resolved = True
        alert.resolved_at = utcnow()
        db.session.commit()
        return jsonify({"message": "Alert resolved", "alert": alert.to_dict()})

    @app.get("/api/ai/predictions")
    @login_required
    def prediction_history():
        return jsonify([p.to_dict() for p in Prediction.query.order_by(Prediction.created_at.desc()).limit(200).all()])

    @app.post("/api/ai/predict")
    @login_required
    def predict_api():
        data = request.get_json(silent=True) or {}
        server_id = data.get("server_id")
        if server_id is not None:
            server = db.session.get(Server, server_id)
            if not server: return json_error("Server not found", 404)
        else:
            server = None
        try:
            if server:
                metrics = {"cpu_usage": server.cpu_usage, "memory_usage": server.memory_usage,
                           "disk_usage": server.disk_usage, "response_time": server.response_time,
                           "error_rate": server.error_rate}
            else:
                metrics = {key: data.get(key) for key in
                           ("cpu_usage", "memory_usage", "disk_usage", "response_time", "error_rate")}
            probability, risk = predict_failure(metrics)
        except ValueError as exc:
            return json_error(str(exc))
        factors = []
        for key, limit, label in [
            ("cpu_usage", 80, "High CPU usage"), ("memory_usage", 85, "High memory usage"),
            ("disk_usage", 90, "High disk usage"), ("response_time", 800, "High response time"),
            ("error_rate", 10, "High error rate")
        ]:
            if float(metrics[key]) >= limit: factors.append(label)
        explanation = "; ".join(factors) if factors else "No configured metric threshold is elevated."
        pred = None
        if server:
            server.failure_probability, server.ai_risk = probability, risk
            pred = Prediction(server_id=server.id, probability=probability, risk=risk, explanation=explanation)
            db.session.add(pred)
            db.session.commit()
        return jsonify({"probability": probability, "risk": risk, "model": "RandomForestClassifier",
                        "data_source": "synthetic training data; demo estimate only",
                        "metrics": metrics, "risk_factors": factors,
                        "prediction": pred.to_dict() if pred else None})

    @app.get("/api/ai/model-info")
    @login_required
    def ai_model_info():
        return jsonify(model_info())

    @app.get("/api/dashboard")
    @login_required
    def dashboard():
        servers = Server.query.all()
        logs = RecoveryLog.query.order_by(RecoveryLog.timestamp.desc()).limit(8).all()
        return jsonify({
            "total_servers": len(servers),
            "healthy_servers": sum(s.status == "Healthy" for s in servers),
            "failed_servers": sum(s.status == "Failed" for s in servers),
            "warning_servers": sum(s.status == "Warning" for s in servers),
            "recovering_servers": sum(s.status == "Recovering" for s in servers),
            "critical_alerts": Alert.query.filter_by(resolved=False, severity="Critical").count(),
            "open_alerts": Alert.query.filter_by(resolved=False).count(),
            "successful_recoveries": RecoveryLog.query.filter_by(status="Success").count(),
            "failed_recoveries": RecoveryLog.query.filter_by(status="Failed").count(),
            "recent_events": [row.to_dict() for row in logs],
            "monitoring_mode": "simulated demo metrics"
        })

    @app.get("/api/dashboard/history")
    @login_required
    def dashboard_history():
        rows = Metric.query.order_by(Metric.timestamp.desc()).limit(50).all()
        return jsonify([row.to_dict() for row in reversed(rows)])

    @app.get("/api/settings")
    @login_required
    def settings_get():
        return jsonify(get_settings())

    @app.put("/api/settings")
    @login_required
    def settings_put():
        data = request.get_json(silent=True) or {}
        allowed = set(DEFAULT_SETTINGS)
        unknown = set(data) - allowed
        if unknown: return json_error("Unknown settings: " + ", ".join(sorted(unknown)))
        for key, value in data.items():
            if key == "auto_recovery_enabled":
                if not isinstance(value, bool): return json_error(f"{key} must be boolean")
            elif isinstance(value, bool) or not isinstance(value, (int, float)):
                return json_error(f"{key} must be numeric")
            else:
                upper = 3600 if "interval" in key else (60000 if "response" in key else 100)
                if value < 0 or value > upper:
                    return json_error(f"{key} must be between 0 and {upper}")
        save_settings(data)
        return jsonify({"message": "Settings saved", "settings": get_settings()})

    @app.get("/api/monitoring/current")
    @login_required
    def monitoring_current():
        return jsonify({"mode": "mixed local monitoring and demo records",
                        "servers": [s.to_dict() for s in Server.query.order_by(Server.id).all()],
                        "host_metrics": collect_host_metrics(),
                        "note": "HTTP(S) endpoints are actively health-checked. CPU/memory/disk values on server records remain demo metrics unless a service agent is integrated."})

    @app.post("/api/monitoring/check")
    @login_required
    def monitoring_check():
        settings = get_settings()
        results = []
        critical_servers = []
        for server in Server.query.order_by(Server.id.asc()).all():
            probe = None
            if is_http_endpoint(server.ip_address):
                probe = probe_http_service(server.ip_address)
                server.response_time = float(probe["response_time_ms"] or 0)
                server.error_rate = 0 if probe["available"] else 100
                if not probe["available"]:
                    factors = [f"HTTP health check failed: {probe.get('error') or probe.get('status_code') or 'service unavailable'}"]
                    evaluation = {"critical": True, "warning": True, "factors": factors}
                else:
                    response = server.response_time
                    warning_limit = float(settings.get("response_warning_ms", 800))
                    critical_limit = float(settings.get("response_critical_ms", 2000))
                    factors = ["High response time"] if response >= warning_limit else []
                    evaluation = {"critical": response >= critical_limit,
                                  "warning": bool(factors), "factors": factors}
                server.status = "Failed" if evaluation["critical"] else ("Warning" if evaluation["warning"] else "Healthy")
            else:
                evaluation = evaluate_server(server, settings)
                server.status = "Failed" if evaluation["critical"] else ("Warning" if evaluation["warning"] else "Healthy")

            server.last_checked = utcnow()
            save_metric(server)
            pred = save_prediction(server)
            if evaluation["critical"] or evaluation["warning"]:
                severity = "Critical" if evaluation["critical"] else "Warning"
                upsert_alert(server, severity, "Monitoring threshold exceeded",
                             "; ".join(evaluation["factors"]) or "Configured health threshold exceeded")
            results.append({"server_id": server.id, "status": server.status,
                            "risk": pred.risk, "probability": pred.probability,
                            "factors": evaluation["factors"], "http_probe": probe})
            if evaluation["critical"] and settings.get("auto_recovery_enabled", True):
                if is_http_endpoint(server.ip_address):
                    log_event(server, "Automatic recovery skipped: no real restart adapter is configured for this HTTP endpoint", "Skipped")
                    upsert_alert(server, "Critical", "Recovery adapter not configured",
                                 "The endpoint was checked, but this project has no configured restart adapter for it. Status is not automatically changed to Healthy.")
                else:
                    critical_servers.append(server)
        db.session.commit()
        recovery_results = []
        for server in critical_servers:
            recovery_results.append(recover_server(server, thresholds=settings))
        return jsonify({"checked": len(results), "results": results,
                        "automatic_recoveries": recovery_results})

    @app.post("/api/simulation/start")
    @login_required
    def simulation_start():
        data = request.get_json(silent=True) or {}
        sid = data.get("server_id")
        server = db.session.get(Server, sid) if sid else Server.query.order_by(Server.id).first()
        if not server: return json_error("No server found. Create or seed a server first.", 404)
        scenario = data.get("scenario", "critical")
        # Reuse the exact simulation route logic without making an internal HTTP call.
        scenarios = {
            "cpu": {"cpu_usage": 99, "memory_usage": 45, "disk_usage": 50, "response_time": 250, "error_rate": 2},
            "memory": {"cpu_usage": 40, "memory_usage": 99, "disk_usage": 50, "response_time": 300, "error_rate": 2},
            "latency": {"cpu_usage": 45, "memory_usage": 50, "disk_usage": 45, "response_time": 3500, "error_rate": 5},
            "errors": {"cpu_usage": 45, "memory_usage": 50, "disk_usage": 45, "response_time": 500, "error_rate": 35},
            "unavailable": {"cpu_usage": 100, "memory_usage": 100, "disk_usage": 99, "response_time": 60000, "error_rate": 100},
            "critical": {"cpu_usage": 100, "memory_usage": 98, "disk_usage": 98, "response_time": 5000, "error_rate": 35},
        }
        if scenario not in scenarios: return json_error("Unknown scenario")
        for attr, value in scenarios[scenario].items(): setattr(server, attr, value)
        server.status, server.last_checked = "Failed", utcnow()
        save_metric(server); pred = save_prediction(server)
        upsert_alert(server, "Critical", "Simulated server failure",
                     f"Scenario '{scenario}' was triggered. Metrics are simulated.")
        log_event(server, f"Failure scenario simulated: {scenario}", "Critical")
        db.session.commit()
        recovery_result = None
        if get_settings().get("auto_recovery_enabled", True):
            if is_http_endpoint(server.ip_address):
                log_event(server, "Simulated failure did not restart the real HTTP endpoint; no restart adapter is configured", "Skipped")
                recovery_result = {"triggered": False, "success": False, "mode": "not-configured",
                                  "message": "The failure is simulated. No real HTTP service restart adapter is configured."}
            else:
                recovery_result = recover_server(server, thresholds=get_settings())
        db.session.commit()
        return jsonify({"message": "Failure simulation completed", "server": server.to_dict(),
                        "prediction": pred.to_dict(), "recovery": recovery_result})

    @app.post("/api/simulation/stop")
    @login_required
    def simulation_stop():
        # Simulation is event-based; stopping means no new scenario is triggered.
        return jsonify({"message": "No continuous simulation loop is running.",
                        "running": False})

    @app.get("/api/simulation/status")
    @login_required
    def simulation_status():
        return jsonify({"running": False, "mode": "manual event-based simulation"})

    with app.app_context():
        db.create_all()
        configured_username = os.environ.get("ADMIN_USERNAME", "admin")
        configured_password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
        configured_admin = User.query.filter_by(username=configured_username).first()
        if configured_admin is None:
            db.session.add(User(username=configured_username,
                                password_hash=generate_password_hash(configured_password)))
        elif not check_password_hash(configured_admin.password_hash, configured_password):
            configured_admin.password_hash = generate_password_hash(configured_password)
        if app.config.get("SEED_DEMO_DATA", True) and Server.query.count() == 0:
            examples = [
                ("server-01", "demo://server-01", 42, 38, 45, 120, 1),
                ("server-02", "demo://server-02", 67, 61, 55, 180, 3),
                ("server-03", "demo://server-03", 88, 82, 68, 450, 8),
            ]
            for name, ip, cpu, mem, disk, response, error in examples:
                server = Server(name=name, ip_address=ip, cpu_usage=cpu, memory_usage=mem,
                                disk_usage=disk, response_time=response, error_rate=error,
                                status="Healthy", last_checked=utcnow())
                db.session.add(server)
                db.session.flush()
                evaluation = evaluate_server(server, DEFAULT_SETTINGS)
                server.status = "Warning" if evaluation["warning"] else "Healthy"
                save_metric(server)
                save_prediction(server)
                if evaluation["warning"]:
                    upsert_alert(server, "Warning", "Server health warning", "; ".join(evaluation["factors"]))
            db.session.commit()
        for key, value in DEFAULT_SETTINGS.items():
            if db.session.get(AppSetting, key) is None:
                db.session.add(AppSetting(key=key, value=json.dumps(value)))
        db.session.commit()

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "Endpoint not found"}), 404

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"error": "Request body is too large"}), 413

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
