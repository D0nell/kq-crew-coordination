"""GPS location sharing and the dispatcher's last-known-position view (TC-78 and TC-79)."""

import pytest
from fastapi.testclient import TestClient

from api.main import app

NAIROBI_A = {"latitude": -1.2921, "longitude": 36.8219, "accuracy_m": 12.5}
NAIROBI_B = {"latitude": -1.3000, "longitude": 36.8300}


@pytest.fixture
def gps_crew(crew_client, q):
    """The test crew account, linked to the crew profile with the most test transits.

    Gives one transit that belongs to that crew member and one that belongs to someone
    else, and removes the link, the pings and the arrival rows afterwards.
    """
    uid = q("SELECT user_id FROM users WHERE email=%s", ("test.crew@example.com",))[0]["user_id"]
    crew_id = q("""SELECT crew_id FROM transit_events WHERE split='test'
                   GROUP BY crew_id ORDER BY COUNT(*) DESC, crew_id LIMIT 1""")[0]["crew_id"]
    mine = q("SELECT transit_id FROM transit_events WHERE crew_id=%s AND split='test' "
             "ORDER BY transit_id LIMIT 1", (crew_id,))[0]["transit_id"]
    other = q("SELECT transit_id FROM transit_events WHERE crew_id<>%s AND split='test' "
              "ORDER BY transit_id LIMIT 1", (crew_id,))[0]["transit_id"]
    q("UPDATE crew_profiles SET user_id=%s WHERE crew_id=%s", (uid, crew_id))
    for table in ("gps_pings", "transit_arrival", "transit_checklist"):
        q(f"DELETE FROM {table}")
    yield {"client": crew_client, "mine": mine, "other": other, "uid": uid}
    for table in ("gps_pings", "transit_arrival", "transit_checklist"):
        q(f"DELETE FROM {table}")
    q("UPDATE crew_profiles SET user_id=NULL WHERE crew_id=%s", (crew_id,))


def test_post_location_rules(gps_crew, client, q, actual):
    """TC-78 | A crew member sends their phone's position for a transit | their own transit stores it with a time; someone else's transit is 404; no login is 401; a dispatcher is 403; an impossible position is 422; after arrival is confirmed sharing stops with 409"""
    c, mine, other = gps_crew["client"], gps_crew["mine"], gps_crew["other"]
    url = f"/api/my-transits/{mine}/location"

    assert TestClient(app).post(url, json=NAIROBI_A).status_code == 401
    assert client.post(url, json=NAIROBI_A).status_code == 403
    assert c.post(f"/api/my-transits/{other}/location", json=NAIROBI_A).status_code == 404

    r = c.post(url, json=NAIROBI_A)
    assert r.status_code == 200 and r.json()["ok"] is True and r.json()["recorded_at"]
    row = q("SELECT latitude, longitude, accuracy_m FROM gps_pings WHERE transit_id=%s", (mine,))
    assert len(row) == 1 and row[0]["latitude"] == pytest.approx(-1.2921) and row[0]["accuracy_m"] == pytest.approx(12.5)
    assert c.post(url, json=NAIROBI_B).status_code == 200
    assert q("SELECT COUNT(*) n FROM gps_pings WHERE transit_id=%s", (mine,))[0]["n"] == 2
    assert q("SELECT COUNT(*) n FROM gps_pings WHERE transit_id=%s", (other,))[0]["n"] == 0

    for bad in ({"latitude": 91, "longitude": 36.8}, {"latitude": -1.3, "longitude": -181},
                {"latitude": "north", "longitude": 36.8}, {"longitude": 36.8}, {}):
        assert c.post(url, json=bad).status_code == 422
    assert q("SELECT COUNT(*) n FROM gps_pings WHERE transit_id=%s", (mine,))[0]["n"] == 2

    assert c.post(f"/api/my-transits/{mine}/arrived").status_code == 200
    stopped = c.post(url, json=NAIROBI_A)
    assert stopped.status_code == 409 and "complete" in stopped.json()["detail"].lower()
    assert q("SELECT COUNT(*) n FROM gps_pings WHERE transit_id=%s", (mine,))[0]["n"] == 2
    actual("two pings stored for the crew member's own transit; 404, 401, 403 and 422 refusals; sharing stopped with 409 after arrival")


def test_dispatcher_sees_last_known_position(gps_crew, client, q, actual):
    """TC-79 | The dispatcher asks for crew locations | each transit shows only its latest position with the crew name and corridor; old positions are left out unless the time window is widened; arrival is shown; crew and anonymous users are refused; a zero time window is 422"""
    c, mine, other, uid = gps_crew["client"], gps_crew["mine"], gps_crew["other"], gps_crew["uid"]

    assert TestClient(app).get("/api/crew-locations").status_code == 401
    assert c.get("/api/crew-locations").status_code == 403
    assert client.get("/api/crew-locations?max_age_minutes=0").status_code == 422

    assert c.post(f"/api/my-transits/{mine}/location", json=NAIROBI_A).status_code == 200
    assert c.post(f"/api/my-transits/{mine}/location", json=NAIROBI_B).status_code == 200
    q("INSERT INTO gps_pings (transit_id, user_id, latitude, longitude, recorded_at) "
      "VALUES (%s, %s, %s, %s, NOW() - INTERVAL '5 hours')", (other, uid, -1.1, 36.7))

    mine_rows = [i for i in client.get("/api/crew-locations").json()["items"] if i["transit_id"] in (mine, other)]
    assert [i["transit_id"] for i in mine_rows] == [mine]
    item = mine_rows[0]
    assert item["latitude"] == pytest.approx(-1.3000) and item["longitude"] == pytest.approx(36.8300)
    assert item["crew_name"] == "Test Crew Member" and item["corridor"] and item["arrived"] is False
    assert item["recorded_at"]

    wide = client.get("/api/crew-locations?max_age_minutes=600").json()
    assert {i["transit_id"] for i in wide["items"] if i["transit_id"] in (mine, other)} == {mine, other}

    assert c.post(f"/api/my-transits/{mine}/arrived").status_code == 200
    after = [i for i in client.get("/api/crew-locations").json()["items"] if i["transit_id"] == mine][0]
    assert after["arrived"] is True
    actual("latest position only, old position hidden until the window was widened, crew name and corridor shown, arrival shown, 401 and 403 and 422 as expected")