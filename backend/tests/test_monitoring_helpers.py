from monitoring import is_http_endpoint, probe_http_service


def test_http_endpoint_validation():
    assert is_http_endpoint("http://localhost:8000/health")
    assert is_http_endpoint("https://example.com/status")
    assert not is_http_endpoint("demo://server-01")
    assert not is_http_endpoint("localhost:5000/health")


def test_http_probe_success(monkeypatch):
    class FakeResponse:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    monkeypatch.setattr("monitoring.urlopen", lambda *args, **kwargs: FakeResponse())
    result = probe_http_service("http://localhost:5000/health")
    assert result["is_http"] is True
    assert result["available"] is True
    assert result["status_code"] == 200
    assert result["response_time_ms"] >= 0


def test_http_probe_non_http_is_not_probed():
    result = probe_http_service("demo://server-01")
    assert result["is_http"] is False
    assert result["available"] is None
