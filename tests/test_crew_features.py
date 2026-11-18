"""Crew readiness checklist and arrival confirmation (TC-73 to TC-75)."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

TASKS = ["UNIFORM", "MEDICAL", "DOCUMENTS"]


@pytest.fixture
def linked_crew(crew_client, q):
    """The test crew account, linked to the crew profile with the most test transits.

    Gives one transit that belongs to that crew member and one that belongs to someone
    else, and undoes the link and the saved ticks afterwards.
    """
    uid = q("SELECT user_id FROM users WHERE email=%s", ("test.crew@example.com",))[0]["user_id"]
    crew_id = q("""SELECT crew_id FROM transit_events WHERE split='test'
                   GROUP BY crew_id ORDER BY COUNT(*) DESC, crew_id LIMIT 1""")[0]["crew_id"]
    mine = q("SELECT transit_id FROM transit_events WHERE crew_id=%s AND split='test' "
             "ORDER BY transit_id LIMIT 1", (crew_id,))[0]["transit_id"]
    other = q("SELECT transit_id FROM transit_events WHERE crew_id<>%s AND split='test' "
              "ORDER BY transit_id LIMIT 1", (crew_id,))[0]["transit_id"]
    q("UPDATE crew_profiles SET user_id=%s WHERE crew_id=%s", (uid, crew_id))
    q("DELETE FROM transit_checklist")
    q("DELETE FROM transit_arrival")
    yield {"client": crew_client, "mine": mine, "other": other}
    q("DELETE FROM transit_checklist")
    q("DELETE FROM transit_arrival")
    q("UPDATE crew_profiles SET user_id=NULL WHERE crew_id=%s", (crew_id,))


def _done(body):
    return {t["code"]: t["done"] for t in body["tasks"]}


def test_checklist_access_and_ownership(linked_crew, client, actual):
    """TC-73 | GET the readiness checklist of a transit | no login gives 401, a dispatcher 403, a crew member 404 for someone else's transit and 200 for their own, with every task not done and arrival not confirmed"""
    c, mine, other = linked_crew["client"], linked_crew["mine"], linked_crew["other"]
    url = "/api/my-transits/{}/checklist"
    assert TestClient(app).get(url.format(mine)).status_code == 401
    assert client.get(url.format(mine)).status_code == 403
    assert c.get(url.format(other)).status_code == 404
    r = c.get(url.format(mine))
    assert r.status_code == 200
    body = r.json()
    assert [t["code"] for t in body["tasks"]] == TASKS
    assert all(t["label"] for t in body["tasks"])
    assert not any(_done(body).values())
    assert body["arrived"] is False and body["arrived_at"] is None
    actual("401 without login, 403 for a dispatcher, 404 for another crew member's transit, 200 with three open tasks for their own")


def test_checklist_tick_and_untick(linked_crew, q, actual):
    """TC-74 | Tick a readiness task, then untick it | the tick is saved and shown on the next read, unticking clears it, an unknown task is 404, a bad body is 422, and another crew member's transit cannot be changed"""
    c, mine, other = linked_crew["client"], linked_crew["mine"], linked_crew["other"]
    base = f"/api/my-transits/{mine}/checklist"

    r = c.put(f"{base}/UNIFORM", json={"done": True})
    assert r.status_code == 200
    assert _done(r.json()) == {"UNIFORM": True, "MEDICAL": False, "DOCUMENTS": False}
    assert _done(c.get(base).json())["UNIFORM"] is True
    row = q("SELECT done, done_at FROM transit_checklist WHERE transit_id=%s AND task_code='UNIFORM'", (mine,))[0]
    assert row["done"] is True and row["done_at"] is not None

    assert c.put(f"{base}/medical", json={"done": True}).status_code == 200
    off = c.put(f"{base}/UNIFORM", json={"done": False}).json()
    assert _done(off) == {"UNIFORM": False, "MEDICAL": True, "DOCUMENTS": False}
    row = q("SELECT done, done_at FROM transit_checklist WHERE transit_id=%s AND task_code='UNIFORM'", (mine,))[0]
    assert row["done"] is False and row["done_at"] is None
    assert q("SELECT COUNT(*) n FROM transit_checklist WHERE transit_id=%s AND task_code='UNIFORM'", (mine,))[0]["n"] == 1

    assert c.put(f"{base}/BOGUS", json={"done": True}).status_code == 404
    assert c.put(f"{base}/UNIFORM", json={}).status_code == 422
    assert c.put(f"{base}/UNIFORM", json={"done": "maybe"}).status_code == 422
    assert c.put(f"/api/my-transits/{other}/checklist/UNIFORM", json={"done": True}).status_code == 404
    assert q("SELECT COUNT(*) n FROM transit_checklist WHERE transit_id=%s", (other,))[0]["n"] == 0
    actual("tick saved with a time, untick cleared it, one row per task, unknown task 404, bad body 422, other crew member's transit untouched")


def test_arrival_confirmation(linked_crew, client, q, actual):
    """TC-75 | Confirm arrival at the destination | the first confirmation is stored with a time, repeating it keeps the first time and adds no second row, another crew member's transit is 404, no login is 401 and a dispatcher is 403"""
    c, mine, other = linked_crew["client"], linked_crew["mine"], linked_crew["other"]
    url = f"/api/my-transits/{mine}/arrived"
    assert TestClient(app).post(url).status_code == 401
    assert client.post(url).status_code == 403
    assert c.post(f"/api/my-transits/{other}/arrived").status_code == 404

    first = c.post(url)
    assert first.status_code == 200
    assert first.json()["arrived"] is True and first.json()["arrived_at"]
    again = c.post(url).json()
    assert again["arrived_at"] == first.json()["arrived_at"]
    assert q("SELECT COUNT(*) n FROM transit_arrival WHERE transit_id=%s", (mine,))[0]["n"] == 1
    assert c.get(f"/api/my-transits/{mine}/checklist").json()["arrived"] is True
    assert q("SELECT COUNT(*) n FROM transit_arrival WHERE transit_id=%s", (other,))[0]["n"] == 0
    actual("arrival stored once with a time, repeat kept the first time, other crew member's transit 404, 401 and 403 as expected")