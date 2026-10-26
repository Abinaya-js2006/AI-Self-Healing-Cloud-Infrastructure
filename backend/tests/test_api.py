import pytest
from app import create_app
from database import db
from models import Server, Alert, RecoveryLog


@pytest.fixture()
def app(tmp_path):
    test_db = tmp_path / "test_project.db"
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{test_db.as_posix()}",
        "SEED_DEMO_DATA": False,
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    client = app.test_client()
    response = client.post("/api/auth/login", json={"username": "admin", "password": "ChangeMe123!"})
    assert response.status_code == 200
    return client


def add_demo_server(client, name="test-server"):
    response = client.post("/api/servers", json={"name": name, "ip_address": "demo://test"})
    assert response.status_code == 201
    return response.get_json()["server"]


def test_authentication_required(app):
    client = app.test_client()
    assert client.get("/api/servers").status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}).status_code == 401


def test_server_create_and_metrics_validation(client):
    server = add_demo_server(client)
    assert server["status"] == "Healthy"
    bad = client.post(f"/api/servers/{server['id']}/metrics", json={"cpu": 150})
    assert bad.status_code == 400
    good = client.post(f"/api/servers/{server['id']}/metrics", json={"cpu": 50, "memory": 60})
    assert good.status_code in (200, 201)
    assert good.get_json()["server"]["cpu_usage"] == 50


def test_ai_prediction_and_model_info(client):
    server = add_demo_server(client)
    response = client.post("/api/ai/predict", json={"server_id": server["id"]})
    assert response.status_code == 200
    body = response.get_json()
    assert 0 <= body["probability"] <= 100
    assert body["risk"] in {"Low", "Medium", "High", "Critical"}
    assert client.get("/api/ai/model-info").status_code == 200


def test_simulation_and_successful_recovery(client):
    server = add_demo_server(client)
    response = client.post(f"/api/servers/{server['id']}/simulate-failure", json={"scenario": "critical"})
    assert response.status_code == 200
    body = response.get_json()
    assert body["recovery"]["success"] is True
    assert body["server"]["status"] == "Healthy"
    assert body["server"]["cpu_usage"] < 80
    assert client.get("/api/recovery-logs").get_json()


def test_failed_recovery_does_not_mark_healthy(client):
    server = add_demo_server(client)
    client.post(f"/api/servers/{server['id']}/simulate-failure",
                json={"scenario": "critical"})
    # Disable auto recovery so the failure remains available for the negative test.
    client.put("/api/settings", json={"auto_recovery_enabled": False})
    metrics = client.post(f"/api/servers/{server['id']}/metrics", json={
        "cpu": 100, "memory": 99, "disk": 99, "response_time": 5000, "error_rate": 40
    })
    failed_server = metrics.get_json()["server"]
    response = client.post(f"/api/servers/{failed_server['id']}/recover",
                           json={"force_failure": True})
    assert response.status_code == 409
    assert response.get_json()["server"]["status"] == "Failed"


def test_alerts_and_settings_persist(client):
    server = add_demo_server(client)
    client.post(f"/api/servers/{server['id']}/simulate-failure", json={"scenario": "critical"})
    assert len(client.get("/api/alerts").get_json()) >= 1
    response = client.put("/api/settings", json={"auto_recovery_enabled": False, "cpu_warning": 75})
    assert response.status_code == 200
    assert response.get_json()["settings"]["auto_recovery_enabled"] is False
    assert client.get("/api/settings").get_json()["cpu_warning"] == 75



def test_alert_resolution_and_server_delete_cleanup(client):
    server = add_demo_server(client)
    client.put("/api/settings", json={"auto_recovery_enabled": False})
    client.post(f"/api/servers/{server['id']}/simulate-failure", json={"scenario": "critical"})
    alerts = client.get("/api/alerts").get_json()
    assert alerts
    open_alert = next((a for a in alerts if not a["resolved"]), None)
    if open_alert:
        response = client.patch(f"/api/alerts/{open_alert['id']}/resolve")
        assert response.status_code == 200
        assert response.get_json()["alert"]["resolved"] is True
    assert client.delete(f"/api/servers/{server['id']}").status_code == 200
    assert client.get(f"/api/servers/{server['id']}").status_code == 404


def test_settings_reject_invalid_threshold(client):
    response = client.put("/api/settings", json={"cpu_warning": 150})
    assert response.status_code == 400
    assert client.put("/api/settings", json={"monitoring_interval_seconds": 10}).status_code == 200


def test_monitoring_check_records_samples(client):
    server = add_demo_server(client)
    response = client.post("/api/monitoring/check", json={})
    assert response.status_code == 200
    assert response.get_json()["checked"] == 1
    assert client.get(f"/api/servers/{server['id']}/metrics").status_code == 200
