from fastapi.testclient import TestClient

from app.db.session import init_db
from app.main import app

init_db()
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_overview_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Overview" in response.text


def test_cmo_dashboard():
    response = client.get("/cmo/", follow_redirects=True)
    assert response.status_code == 200
    assert "Gharkaguru CMO" in response.text or "_dash" in response.text


def test_sync_job_status():
    response = client.get("/api/sync/job")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "job" in data


def test_sync_job_start(monkeypatch):
    from app.api import routes_sync

    fake_job = {
        "job_id": "test-job-id",
        "type": "insights",
        "status": "running",
        "progress": 0,
        "message": "Starting",
    }

    def _fake_start(settings, job_type, full=False):
        return fake_job

    monkeypatch.setattr(routes_sync, "start_sync_job", _fake_start)
    response = client.post("/api/sync/job", json={"type": "insights"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["job"]["job_id"] == "test-job-id"


def test_cmo_redirect():
    response = client.get("/cmo", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/cmo/"


def test_sync_status():
    response = client.get("/api/sync/status")
    assert response.status_code == 200
    assert "cursors" in response.json()


def test_services_page(monkeypatch):
    from app.main import list_cloud_run_services as lcr  # noqa: F401
    from app import main

    monkeypatch.setattr(
        main,
        "list_cloud_run_services",
        lambda _settings: {
            "project_id": "vertex-ai-learning-487906",
            "services": [
                {
                    "id": "meta-ads-manager",
                    "name": "Meta Ads Manager",
                    "region": "asia-south1",
                    "url": "https://meta-ads-manager.example.run.app",
                    "is_current": True,
                }
            ],
            "error": None,
            "current_service": "meta-ads-manager",
        },
    )
    response = client.get("/services")
    assert response.status_code == 200
    assert "Meta Ads Manager" in response.text
    assert "meta-ads-manager" in response.text


def test_cloud_run_services_api(monkeypatch):
    from app import main

    monkeypatch.setattr(
        main,
        "list_cloud_run_services",
        lambda _settings: {"project_id": "test", "services": [], "error": None, "current_service": None},
    )
    response = client.get("/api/cloud-run/services")
    assert response.status_code == 200
    assert response.json()["project_id"] == "test"


def test_book_parent_page():
    response = client.get("/book/parent")
    assert response.status_code == 200
    assert "Choose demo time" in response.text
    assert "Your mobile number" in response.text
    assert "local timezone" in response.text
    assert "summary-card" in response.text


def test_book_parent_slots():
    response = client.get("/api/book/parent/slots")
    assert response.status_code == 200
    data = response.json()
    assert data["client_local"] is True
    assert data["days_ahead"] == 7
    assert data["hours"] == list(range(10, 22))


def test_book_parent_submit_missing_phone():
    payload = {
        "slot_date": "2026-06-20",
        "slot_time": "7:00 PM",
    }
    response = client.post("/api/book/parent", json=payload)
    assert response.status_code == 422


def test_book_parent_submit():
    payload = {
        "phone": "9876543210",
        "slot_date": "2026-06-20",
        "slot_time": "7:00 PM",
        "user_timezone": "Asia/Kolkata",
    }
    response = client.post("/api/book/parent", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["booking_id"] > 0


def test_parent_bookings_list_page():
    response = client.get("/bookings/parent")
    assert response.status_code == 200
    assert "Parent demo bookings" in response.text


def test_parent_bookings_list_api():
    response = client.get("/api/book/parent")
    assert response.status_code == 200
    data = response.json()
    assert "bookings" in data
    assert "count" in data


def test_book_instagram_redirect():
    response = client.get("/book/instagram", follow_redirects=False)
    assert response.status_code == 302
    assert "utm_source=instagram" in response.headers["location"]
    assert "/book/parent" in response.headers["location"]
