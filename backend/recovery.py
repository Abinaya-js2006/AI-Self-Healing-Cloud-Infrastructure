"""Recovery adapters. The default adapter only heals simulated demo metrics.

A real infrastructure adapter must be explicitly configured and should be restricted
to a named test service/container. This module intentionally never runs arbitrary commands.
"""
from datetime import datetime, timezone
from database import db
from models import RecoveryLog, Alert, Prediction
from monitoring import save_metric, evaluate_server, upsert_alert
from ml_model import predict_failure


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log_event(server, event, status):
    item = RecoveryLog(server_id=server.id, event=event, status=status, timestamp=utcnow())
    db.session.add(item)
    return item


def recover_server(server, force_failure=False, thresholds=None):
    if server.status == "Healthy" and not force_failure and not evaluate_server(server, thresholds)["critical"]:
        return {"triggered": False, "success": True, "mode": "simulated",
                "message": "Service is already healthy", "server": server.to_dict()}

    log_event(server, "Recovery requested (simulated adapter)", "Started")
    server.status = "Recovering"
    db.session.flush()

    if force_failure:
        # Used to test a failed recovery path; no actual service is affected.
        server.status = "Failed"
        server.last_checked = utcnow()
        log_event(server, "Recovery verification failed (test scenario)", "Failed")
        upsert_alert(server, "Critical", "Recovery failed", "Simulated recovery did not pass health verification.")
        db.session.commit()
        return {"triggered": True, "success": False, "mode": "simulated",
                "message": "Recovery failed health verification; service remains Failed",
                "server": server.to_dict()}

    # Simulated adapter restores demo metrics; it does not restart an OS/cloud server.
    server.cpu_usage = 32
    server.memory_usage = 41
    server.disk_usage = 44
    server.response_time = 110
    server.error_rate = 1
    server.last_checked = utcnow()

    verification = evaluate_server(server, thresholds)
    if verification["critical"] or verification["warning"]:
        server.status = "Failed"
        log_event(server, "Post-recovery health verification failed", "Failed")
        upsert_alert(server, "Critical", "Recovery failed", "Metrics remained outside the configured health policy.")
        db.session.commit()
        return {"triggered": True, "success": False, "mode": "simulated",
                "message": "Health verification failed; service remains Failed",
                "server": server.to_dict()}

    server.status = "Healthy"
    probability, risk = predict_failure({
        "cpu_usage": server.cpu_usage, "memory_usage": server.memory_usage,
        "disk_usage": server.disk_usage, "response_time": server.response_time,
        "error_rate": server.error_rate,
    })
    server.ai_risk = risk
    server.failure_probability = probability
    save_metric(server)
    db.session.add(Prediction(server_id=server.id, probability=probability, risk=risk,
                              explanation="Prediction recorded after simulated recovery health verification."))
    for alert in Alert.query.filter_by(server_id=server.id, resolved=False).all():
        alert.resolved = True
        alert.resolved_at = utcnow()
    log_event(server, "Simulated recovery completed", "Success")
    log_event(server, "Post-recovery health verification passed", "Success")
    db.session.commit()
    return {"triggered": True, "success": True, "mode": "simulated",
            "message": "Simulated recovery completed and health verification passed",
            "server": server.to_dict()}
