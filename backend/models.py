from datetime import datetime, timezone
from database import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)


class Server(db.Model):
    __tablename__ = "servers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    ip_address = db.Column(db.String(500), nullable=False)
    cpu_usage = db.Column(db.Float, default=0, nullable=False)
    memory_usage = db.Column(db.Float, default=0, nullable=False)
    disk_usage = db.Column(db.Float, default=0, nullable=False)
    response_time = db.Column(db.Float, default=0, nullable=False)
    error_rate = db.Column(db.Float, default=0, nullable=False)
    status = db.Column(db.String(30), default="Healthy", nullable=False)
    ai_risk = db.Column(db.String(30), default="Low", nullable=False)
    failure_probability = db.Column(db.Float, default=0, nullable=False)
    last_checked = db.Column(db.DateTime, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "ip_address": self.ip_address,
            "cpu_usage": round(float(self.cpu_usage or 0), 2),
            "memory_usage": round(float(self.memory_usage or 0), 2),
            "disk_usage": round(float(self.disk_usage or 0), 2),
            "response_time": round(float(self.response_time or 0), 2),
            "error_rate": round(float(self.error_rate or 0), 2),
            "status": self.status, "ai_risk": self.ai_risk,
            "failure_probability": round(float(self.failure_probability or 0), 2),
            "last_checked": self.last_checked.isoformat() + "Z" if self.last_checked else None,
            "monitoring_mode": "simulated"
        }


class Metric(db.Model):
    __tablename__ = "metrics"
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)
    cpu = db.Column(db.Float, default=0)
    memory = db.Column(db.Float, default=0)
    disk = db.Column(db.Float, default=0)
    response_time = db.Column(db.Float, default=0)
    error_rate = db.Column(db.Float, default=0)

    def to_dict(self):
        return {"id": self.id, "server_id": self.server_id,
                "timestamp": self.timestamp.isoformat() + "Z" if self.timestamp else None,
                "cpu": self.cpu, "memory": self.memory, "disk": self.disk,
                "response_time": self.response_time, "error_rate": self.error_rate}


class RecoveryLog(db.Model):
    __tablename__ = "recovery_logs"
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    event = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), default="Started")
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "server_id": self.server_id, "event": self.event,
                "status": self.status, "timestamp": self.timestamp.isoformat() + "Z" if self.timestamp else None}


class Alert(db.Model):
    __tablename__ = "alerts"
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    severity = db.Column(db.String(20), default="Warning", nullable=False)
    message = db.Column(db.String(500), nullable=False)
    resolved = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)
    resolved_at = db.Column(db.DateTime)

    def to_dict(self):
        return {"id": self.id, "server_id": self.server_id, "title": self.title,
                "severity": self.severity, "message": self.message, "resolved": self.resolved,
                "created_at": self.created_at.isoformat() + "Z" if self.created_at else None,
                "resolved_at": self.resolved_at.isoformat() + "Z" if self.resolved_at else None}


class Prediction(db.Model):
    __tablename__ = "predictions"
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False, index=True)
    probability = db.Column(db.Float, nullable=False)
    risk = db.Column(db.String(20), nullable=False)
    model_name = db.Column(db.String(100), default="RandomForest / synthetic training data")
    explanation = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "server_id": self.server_id, "probability": self.probability,
                "risk": self.risk, "model_name": self.model_name, "explanation": self.explanation,
                "created_at": self.created_at.isoformat() + "Z" if self.created_at else None}


class AppSetting(db.Model):
    __tablename__ = "app_settings"
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.String(1000), nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
