import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.services.groups import NORMAL
from apps.accounts.views import IPScopedRateThrottle

pytestmark = pytest.mark.django_db

User = get_user_model()
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture(autouse=True)
def clear_throttles():
    cache.clear()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def fan():
    return User.objects.create_user(username="fan", password=PASSWORD)


def test_me_is_null_when_signed_out(client):
    response = client.get("/api/auth/me/")
    assert response.status_code == 200
    assert response.json() == {"user": None}


def test_csrf_endpoint_sets_cookie(client):
    response = client.get("/api/auth/csrf/")
    assert response.status_code == 204
    assert "csrftoken" in response.cookies


def test_register_signs_in_and_joins_normal_group(client):
    response = client.post("/api/auth/register/", {"username": "newfan", "password": PASSWORD})
    assert response.status_code == 201
    assert response.json()["user"]["username"] == "newfan"
    assert response.json()["user"]["groups"] == [NORMAL]
    assert client.get("/api/auth/me/").json()["user"]["username"] == "newfan"
    assert "password" not in response.json()["user"]


@pytest.mark.parametrize("password", ["short", "password123", "newfan123"])
def test_register_rejects_weak_passwords(client, password):
    response = client.post("/api/auth/register/", {"username": "newfan", "password": password})
    assert response.status_code == 400
    assert not User.objects.filter(username="newfan").exists()


def test_register_rejects_taken_username(client, fan):
    response = client.post("/api/auth/register/", {"username": "fan", "password": PASSWORD})
    assert response.status_code == 400


def test_login_and_logout(client, fan):
    assert client.post("/api/auth/login/", {"username": "fan", "password": "wrong"}).status_code == 400
    response = client.post("/api/auth/login/", {"username": "fan", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "fan"
    assert client.post("/api/auth/logout/").status_code == 204
    assert client.get("/api/auth/me/").json() == {"user": None}


def test_logout_requires_sign_in(client):
    assert client.post("/api/auth/logout/").status_code == 403


def test_login_requires_csrf_token(fan):
    client = APIClient(enforce_csrf_checks=True)
    response = client.post("/api/auth/login/", {"username": "fan", "password": PASSWORD})
    assert response.status_code == 403

    client.get("/api/auth/csrf/")
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/api/auth/login/", {"username": "fan", "password": PASSWORD}, HTTP_X_CSRFTOKEN=token
    )
    assert response.status_code == 200


def test_register_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(IPScopedRateThrottle, "THROTTLE_RATES", {"register": "2/hour"})
    for i in range(2):
        assert client.post("/api/auth/register/", {"username": f"u{i}", "password": PASSWORD}).status_code == 201
    response = client.post("/api/auth/register/", {"username": "u3", "password": PASSWORD})
    assert response.status_code == 429


def test_login_is_rate_limited_per_ip(client, fan, monkeypatch):
    monkeypatch.setattr(IPScopedRateThrottle, "THROTTLE_RATES", {"login": "2/min"})
    for _ in range(2):
        client.post("/api/auth/login/", {"username": "fan", "password": "wrong"})
    response = client.post("/api/auth/login/", {"username": "fan", "password": PASSWORD})
    assert response.status_code == 429
