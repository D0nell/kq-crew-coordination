"""Choosing Crew or Dispatcher on the sign-in screen (TC-76 and TC-77)."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

ROLE_TEST_DOMAIN = "@rtest.example"
CREW = ("test.crew@example.com", "TestCrew-Only-For-Tests-123!")
DISPATCHER = ("test.dispatcher@example.com", "TestDispatcher-Only-For-Tests-123!")
TOKEN = "x" * 40


@pytest.fixture
def role_clean(loaded_db, q):
    """Remove the accounts these tests create so other tests see an untouched users table."""
    def wipe():
        q("UPDATE crew_profiles SET user_id = NULL WHERE user_id IN (SELECT user_id FROM users WHERE email LIKE %s)", ("%" + ROLE_TEST_DOMAIN,))
        q("DELETE FROM users WHERE email LIKE %s", ("%" + ROLE_TEST_DOMAIN,))
    wipe()
    yield
    wipe()


def _claims(sub, email):
    return {"sub": sub, "email": email, "name": "Role Test", "email_verified": True,
            "aud": "test-client-id.apps.googleusercontent.com", "iss": "https://accounts.google.com"}


def _login(account, role=None, password=None):
    body = {"email": account[0], "password": password or account[1]}
    if role:
        body["role"] = role
    c = TestClient(app)
    return c, c.post("/login", json=body)


def test_password_sign_in_checks_chosen_role(client, crew_client, actual):
    """TC-76 | Sign in with a password after choosing Crew or Dispatcher | a matching choice or no choice signs in; a wrong choice is refused with 403 and a clear message and no session; a wrong password stays 401; an unknown role is 422"""
    c, r = _login(CREW, "CREW")
    assert r.status_code == 200 and r.json()["role"] == "CREW" and c.get("/api/me").status_code == 200
    c, r = _login(DISPATCHER, "DISPATCHER")
    assert r.status_code == 200 and r.json()["role"] == "DISPATCHER"
    assert _login(CREW)[1].status_code == 200 and _login(DISPATCHER)[1].status_code == 200

    c, r = _login(CREW, "DISPATCHER")
    assert r.status_code == 403 and "crew account" in r.json()["detail"].lower()
    assert c.get("/api/me").status_code == 401
    c, r = _login(DISPATCHER, "CREW")
    assert r.status_code == 403 and "dispatcher account" in r.json()["detail"].lower()
    assert c.get("/api/me").status_code == 401

    assert _login(CREW, "DISPATCHER", password="not-the-password")[1].status_code == 401
    assert _login(CREW, "ADMIN")[1].status_code == 422
    actual("matching or missing choice signed in; wrong choice 403 with a clear message and no session; wrong password 401; unknown role 422")


def test_google_sign_in_checks_chosen_role(role_clean, monkeypatch, q, actual):
    """TC-77 | Sign in with Google after choosing Crew or Dispatcher | choosing Dispatcher never creates an account and only works for an existing dispatcher; choosing Crew for a dispatcher is refused; choosing Crew for a new person creates a crew account"""
    import api.main as m
    dispatcher_email = "disp" + ROLE_TEST_DOMAIN
    new_email = "newcomer" + ROLE_TEST_DOMAIN
    q("INSERT INTO users (full_name, role, email) VALUES ('Role Dispatcher','DISPATCHER',%s)", (dispatcher_email,))

    def count(email):
        return q("SELECT COUNT(*) n FROM users WHERE email=%s", (email,))[0]["n"]

    # A new person who picks Dispatcher is refused and no account is created.
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-77a", new_email))
    c = TestClient(app)
    r = c.post("/auth/google", json={"credential": TOKEN, "role": "DISPATCHER"})
    assert r.status_code == 403 and "no dispatcher account" in r.json()["detail"].lower()
    assert count(new_email) == 0 and c.get("/api/me").status_code == 401

    # An existing dispatcher who picks Dispatcher signs in; the same person picking Crew is refused.
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-77b", dispatcher_email))
    r = TestClient(app).post("/auth/google", json={"credential": TOKEN, "role": "DISPATCHER"})
    assert r.status_code == 200 and r.json()["role"] == "DISPATCHER"
    c = TestClient(app)
    r = c.post("/auth/google", json={"credential": TOKEN, "role": "CREW"})
    assert r.status_code == 403 and "dispatcher account" in r.json()["detail"].lower()
    assert c.get("/api/me").status_code == 401

    # A new person who picks Crew gets a crew account, as before.
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-77c", new_email))
    c = TestClient(app)
    r = c.post("/auth/google", json={"credential": TOKEN, "role": "CREW"})
    assert r.status_code == 200 and r.json()["role"] == "CREW" and r.json()["created"] is True
    assert count(new_email) == 1 and c.get("/api/transits").status_code == 403
    actual("Dispatcher choice refused for a new person with no account created; allowed for an existing dispatcher; Crew choice refused for a dispatcher; Crew choice created a crew account")