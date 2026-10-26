"""Monitoring helpers for simulated server records."""
from datetime import datetime, timezone
import os
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from models import Metric, Alert
from database import db


def is_http_endpoint(value):
    """Return True only for explicitly configured HTTP(S) health-check URLs."""
    parsed = urlparse(str(value or ""))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def probe_http_service(url, timeout=3.0):
    """Probe a configured HTTP(S) endpoint without executing remote commands."""
    if not is_http_endpoint(url):
        return {"is_http": False, "available": None, "status_code": None,
                "response_time_ms": None, "error": None}
    started = perf_counter()
    request = Request(url, headers={"User-Agent": "SelfHealingCloudMonitor/1.0"}, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            elapsed = round((perf_counter() - started) * 1000, 2)
            code = int(response.status)
            return {"is_http": True, "available": 200 <= code < 400,
                    "status_code": code, "response_time_ms": elapsed, "error": None}
    except HTTPError as exc:
        elapsed = round((perf_counter() - started) * 1000, 2)
        return {"is_http": True, "available": False, "status_code": int(exc.code),
                "response_time_ms": elapsed, "error": f"HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        elapsed = round((perf_counter() - started) * 1000, 2)
        reason = getattr(exc, "reason", exc)
        return {"is_http": True, "available": False, "status_code": None,
                "response_time_ms": elapsed, "error": str(reason)[:250]}


def collect_host_metrics():
    """Collect actual local host metrics; these are not remote server metrics."""
    try:
        import psutil
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.path.abspath(os.sep))
        return {
            "available": True,
            "cpu_percent": round(float(psutil.cpu_percent(interval=0.1)), 2),
            "memory_percent": round(float(memory.percent), 2),
            "disk_percent": round(float(disk.percent), 2),
            "memory_total_bytes": int(memory.total),
            "memory_available_bytes": int(memory.available),
            "note": "These values describe the machine running the Flask backend, not each remote service.",
        }
    except (ImportError, OSError, RuntimeError) as exc:
        return {"available": False, "error": str(exc),
                "note": "Install psutil to enable local host metrics."}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_metrics(data):
    mapping = {
        "cpu": ("cpu_usage", 0, 100),
        "memory": ("memory_usage", 0, 100),
        "disk": ("disk_usage", 0, 100),
        "response_time": ("response_time", 0, 60000),
        "error_rate": ("error_rate", 0, 100),
    }
    output = {}
    for incoming, (attr, low, high) in mapping.items():
        if incoming not in data:
            continue
        try:
            value = float(data[incoming])
        except (TypeError, ValueError):
            raise ValueError(f"{incoming} must be numeric")
        if not low <= value <= high:
            raise ValueError(f"{incoming} must be between {low} and {high}")
        output[attr] = value
    return output


def save_metric(server):
    metric = Metric(
        server_id=server.id, cpu=server.cpu_usage, memory=server.memory_usage,
        disk=server.disk_usage, response_time=server.response_time,
        error_rate=server.error_rate, timestamp=utcnow()
    )
    db.session.add(metric)
    return metric


def evaluate_server(server, thresholds=None):
    thresholds = thresholds or {}
    rules = [
        ("cpu_usage", float(thresholds.get("cpu_warning", 80)), "High CPU utilization"),
        ("memory_usage", float(thresholds.get("memory_warning", 85)), "High memory utilization"),
        ("disk_usage", float(thresholds.get("disk_warning", 90)), "High disk utilization"),
        ("response_time", float(thresholds.get("response_warning_ms", 800)), "High response time"),
        ("error_rate", float(thresholds.get("error_warning_percent", 10)), "High error rate"),
    ]
    factors = [label for attr, limit, label in rules if float(getattr(server, attr) or 0) >= limit]
    critical = (
        server.cpu_usage >= float(thresholds.get("cpu_critical", 95)) or
        server.memory_usage >= float(thresholds.get("memory_critical", 95)) or
        server.disk_usage >= float(thresholds.get("disk_critical", 97)) or
        server.response_time >= float(thresholds.get("response_critical_ms", 2000)) or
        server.error_rate >= float(thresholds.get("error_critical_percent", 20))
    )
    return {"critical": critical, "warning": bool(factors), "factors": factors}


def upsert_alert(server, severity, title, message):
    # Keep one unresolved alert for the same server/title to avoid alert storms.
    existing = Alert.query.filter_by(server_id=server.id, title=title, resolved=False).first()
    if existing:
        existing.severity = severity
        existing.message = message
        return existing
    alert = Alert(server_id=server.id, severity=severity, title=title, message=message)
    db.session.add(alert)
    return alert
