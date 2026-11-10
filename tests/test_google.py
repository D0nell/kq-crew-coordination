"""Google sign-in and sign-up (TC-67 to TC-72)."""

import pytest
from fastapi.testclient import TestClient

from api.main import app


# ------------------------------------------------------------------ Google sign-in and sign-up
GOOGLE_TEST_DOMAIN = "@gtest.example"


@pytest.fixture
def google_clean(loaded_db, q):
    """Remove any account these tests create so other tests see an untouched users table."""
    def wipe():
        q("UPDATE crew_profiles SET user_id = NULL WHERE user_id IN (SELECT user_id FROM users WHERE email LIKE %s)", ("%" + GOOGLE_TEST_DOMAIN,))
        q("DELETE FROM users WHERE email LIKE %s", ("%" + GOOGLE_TEST_DOMAIN,))
    wipe()
    yield
    wipe()


def _claims(sub, email, name="Test Person", verified=True):
    return {"sub": sub, "email": email, "name": name, "email_verified": verified,
            "aud": "test-client-id.apps.googleusercontent.com", "iss": "https://accounts.google.com"}


TOKEN = "x" * 40


def test_google_signup_creates_crew_only(google_clean, monkeypatch, q, actual):
    """TC-67 | A new person signs up with a verified Google account | a CREW account is created and signed in, with no password and no dispatcher access"""
    import api.main as m
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-67", "new.crew" + GOOGLE_TEST_DOMAIN, "New Crew"))
    c = TestClient(app)
    r = c.post("/auth/google", json={"credential": TOKEN})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["role"] == "CREW" and body["created"] is True and body["redirect"] == "/predict"
    assert c.get("/api/me").json()["role"] == "CREW"
    assert c.get("/api/transits").status_code == 403 and c.get("/api/alerts").status_code == 403
    row = q("SELECT role, password_hash, google_sub FROM users WHERE email=%s", ("new.crew" + GOOGLE_TEST_DOMAIN,))[0]
    assert row["role"] == "CREW" and row["password_hash"] is None and row["google_sub"] == "g-sub-67"
    pw = TestClient(app).post("/login", json={"email": "new.crew" + GOOGLE_TEST_DOMAIN, "password": "anything-at-all"})
    assert pw.status_code == 401
    actual("account created as CREW, signed in, dispatcher endpoints 403, password sign-in impossible")


def test_google_second_signin_reuses_account(google_clean, monkeypatch, q, actual):
    """TC-68 | The same Google account signs in twice | one account only; the second time created is false and the user id is unchanged"""
    import api.main as m
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-68", "repeat" + GOOGLE_TEST_DOMAIN))
    first = TestClient(app).post("/auth/google", json={"credential": TOKEN}).json()
    c = TestClient(app)
    second = c.post("/auth/google", json={"credential": TOKEN}).json()
    assert first["created"] is True and second["created"] is False
    assert c.get("/api/me").json()["user_id"] == q("SELECT user_id FROM users WHERE google_sub=%s", ("g-sub-68",))[0]["user_id"]
    assert q("SELECT COUNT(*) n FROM users WHERE email=%s", ("repeat" + GOOGLE_TEST_DOMAIN,))[0]["n"] == 1
    actual("one account for two sign-ins")


def test_google_links_existing_account_and_keeps_role(google_clean, monkeypatch, q, actual):
    """TC-69 | A Google account whose verified email matches an existing dispatcher | it signs in to that account and keeps the DISPATCHER role; no duplicate is created; an email already linked to another Google account is refused"""
    import api.main as m
    email = "disp" + GOOGLE_TEST_DOMAIN
    q("INSERT INTO users (full_name, role, email) VALUES ('Linked Dispatcher','DISPATCHER',%s)", (email,))
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-69", email))
    c = TestClient(app)
    r = c.post("/auth/google", json={"credential": TOKEN})
    assert r.status_code == 200 and r.json()["role"] == "DISPATCHER" and r.json()["created"] is False
    assert r.json()["redirect"] == "/dashboard" and c.get("/api/alerts").status_code == 200
    assert q("SELECT COUNT(*) n FROM users WHERE email=%s", (email,))[0]["n"] == 1
    monkeypatch.setattr(m, "verify_google_credential", lambda c: _claims("g-sub-OTHER", email))
    assert TestClient(app).post("/auth/google", json={"credential": TOKEN}).status_code == 403
    actual("linked by verified email, role kept, second Google account on the same email refused (403)")


def test_google_rejections(google_clean, monkeypatch, q, actual):
    """TC-70 | Google sign-in with a bad token, an unverified email, no server setup, or a malformed body | 401, 401, 503, 422; no session and no account is created"""
    import api.main as m
    from api.auth import GoogleNotConfigured, GoogleSignInError

    def bad(c):
        raise GoogleSignInError("Google sign-in could not be verified.")

    def unverified(c):
        raise GoogleSignInError("Your Google email address is not verified.")

    def unconfigured(c):
        raise GoogleNotConfigured()

    c = TestClient(app)
    for fn, code in ((bad, 401), (unverified, 401), (unconfigured, 503)):
        monkeypatch.setattr(m, "verify_google_credential", fn)
        assert c.post("/auth/google", json={"credential": TOKEN}).status_code == code
    assert c.post("/auth/google", json={}).status_code == 422
    assert c.post("/auth/google", json={"credential": "short"}).status_code == 422
    assert c.get("/api/me").status_code == 401
    assert q("SELECT COUNT(*) n FROM users WHERE email LIKE %s", ("%" + GOOGLE_TEST_DOMAIN,))[0]["n"] == 0
    actual("401, 401, 503, 422, 422; no session; no account created")


def test_google_token_checks(monkeypatch, actual):
    """TC-71 | The server's own token checks | a token for a different app, a different issuer, or an unverified email is refused; a correct one is accepted; with no client id configured nothing is accepted"""
    import api.auth as a
    good = _claims("g-71", "ok" + GOOGLE_TEST_DOMAIN)

    def run(claims, client_id="test-client-id.apps.googleusercontent.com"):
        if client_id:
            monkeypatch.setenv("GOOGLE_CLIENT_ID", client_id)
        else:
            monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.setattr(a.google_id_token, "verify_oauth2_token", lambda *args, **kw: dict(claims))
        return a.verify_google_credential(TOKEN)

    assert run(good)["sub"] == "g-71"
    for broken in (dict(good, aud="someone-elses-app"), dict(good, iss="evil.example"), dict(good, email_verified=False)):
        with pytest.raises(a.GoogleSignInError):
            run(broken)
    with pytest.raises(a.GoogleNotConfigured):
        run(good, client_id="")

    def invalid(*args, **kw):
        raise ValueError("Token expired")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(a.google_id_token, "verify_oauth2_token", invalid)
    with pytest.raises(a.GoogleSignInError):
        a.verify_google_credential(TOKEN)
    actual("wrong app, wrong issuer, unverified email, expired token and missing setup all refused; a correct token accepted")


def test_signup_page_and_config(google_clean, client, monkeypatch, actual):
    """TC-72 | GET /signup and /api/auth-config | the sign-up page is public and says new accounts are crew accounts; a signed-in user is redirected away; the config shows the Google client id only when one is set"""
    anon = TestClient(app)
    page = anon.get("/signup", follow_redirects=False)
    assert page.status_code == 200 and 'id="google-btn"' in page.text and "crew account" in page.text.lower()
    assert client.get("/signup", follow_redirects=False).status_code == 303
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    assert anon.get("/api/auth-config").json() == {"google_client_id": None}
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com,other")
    assert anon.get("/api/auth-config").json() == {"google_client_id": "abc.apps.googleusercontent.com"}
    actual("sign-up page served, signed-in user redirected, client id shown only when configured")
