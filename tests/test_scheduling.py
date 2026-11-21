"""Scheduling board endpoints (FR-06, Sprint II): generate, proposals, approve, replan, my-transits."""

import pytest

from fastapi.testclient import TestClient

from api.main import app

# ---------------------------------------------------------------- helpers ----


def _set_status(q, tid, status):
    q("UPDATE transit_events SET schedule_status = %s WHERE transit_id = %s", (status, tid))


def _clear_assignment(q, tid):
    q("UPDATE transit_events SET crew_id = NULL, vehicle_id = NULL WHERE transit_id = %s", (tid,))


def _assigned(q, tid):
    return q("SELECT crew_id, vehicle_id, schedule_status FROM transit_events WHERE transit_id = %s",
             (tid,))[0]


def _window(q, tid):
    row = q("SELECT scheduled_pickup_time, scheduled_arrival_time FROM transit_events WHERE transit_id=%s",
            (tid,))
    return row[0]


def _overlaps(a, b):
    return a["scheduled_pickup_time"] < b["scheduled_arrival_time"] and b["scheduled_pickup_time"] < a["scheduled_arrival_time"]


def _crew_double_booked(q, transit_ids):
    """True if any crew is assigned to two transits whose time windows overlap."""
    windows = {tid: _window(q, tid) for tid in transit_ids}
    for tid in transit_ids:
        crew = _assigned(q, tid)["crew_id"]
        if crew is None:
            continue
        for o in transit_ids:
            if o != tid and _assigned(q, o)["crew_id"] == crew and _overlaps(windows[tid], windows[o]):
                return True
    return False


# ------------------------------------------------------------------- TC-80 ----


def test_generate_assigns_unassigned_transits(client, q, actual):
    """TC-80 | POST /api/scheduling/generate assigns unassigned transits and sets PROPOSED.

    Pick out test transits, clear their crew/vehicle and mark them PROPOSED, then
    generate. Every unassigned transit must end up with a crew, a vehicle and
    schedule_status=PROPOSED.
    """
    ids = client.get("/api/transits?limit=100").json()["items"]
    unassigned = []
    for i, item in enumerate(ids[:30]):
        tid = item["transit_id"]
        _clear_assignment(q, tid)
        _set_status(q, tid, "PROPOSED")
        unassigned.append(tid)
    before = q("SELECT COUNT(*) n FROM transit_events WHERE schedule_status = 'PROPOSED' AND crew_id IS NOT NULL")[0]["n"]
    resp = client.post("/api/scheduling/generate").json()
    after = q("SELECT COUNT(*) n FROM transit_events WHERE schedule_status = 'PROPOSED' AND crew_id IS NOT NULL")
    assert all(tid in resp["transit_ids"] for tid in unassigned), "a cleared transit was not scheduled"
    for tid in unassigned:
        row = _assigned(q, tid)
        assert row["crew_id"] is not None, f"transit {tid} missing crew"
        assert row["vehicle_id"] is not None, f"transit {tid} missing vehicle"
        assert row["schedule_status"] == "PROPOSED", f"transit {tid} status"
    actual(f"generated {resp['scheduled']} proposals for {len(unassigned)} unassigned transits")


def test_generate_respects_existing_assignments(client, q, actual):
    """TC-81 | An already-assigned PROPOSED transit is left alone on a generate pass."""
    ids = client.get("/api/transits?limit=100").json()["items"]
    tid = ids[0]["transit_id"]
    _set_status(q, tid, "PROPOSED")          # keep its crew/vehicle
    crew_before = _assigned(q, tid)["crew_id"]
    vehicle_before = _assigned(q, tid)["vehicle_id"]
    resp = client.post("/api/scheduling/generate").json()
    row = _assigned(q, tid)
    assert tid not in resp["transit_ids"], "an already-assigned transit was rescheduled"
    assert row["crew_id"] == crew_before, "crew changed for an existing assignment"
    assert row["vehicle_id"] == vehicle_before, "vehicle changed for an existing assignment"
    actual(f"generate {resp['scheduled']} scheduled; existing assignment kept")


def test_generate_never_doubles_up_on_one_crew(client, q, actual):
    """TC-82 | A crew is not assigned to two transits whose time windows overlap."""
    rows = client.get("/api/transits?limit=100").json()["items"]
    transit_ids = [r["transit_id"] for r in rows[:30]]
    for tid in transit_ids:
        _clear_assignment(q, tid)
        _set_status(q, tid, "PROPOSED")
    resp = client.post("/api/scheduling/generate").json()
    assert resp["scheduled"] == len(transit_ids), resp
    assert not _crew_double_booked(q, transit_ids), "a crew ended up double-booked"
    actual(f"generated {resp['scheduled']} with no crew overlaps")


def test_proposals_lists_proposed_with_crew_and_vehicle(client, q, actual):
    """TC-83 | GET /api/scheduling/proposals returns PROPOSED transits with crew/vehicle details."""
    ids = client.get("/api/transits?limit=100").json()["items"]
    for item in ids[:10]:
        _clear_assignment(q, item["transit_id"])
        _set_status(q, item["transit_id"], "PROPOSED")
    resp = client.post("/api/scheduling/generate").json()
    cleared = [item["transit_id"] for item in ids[:10]]
    for tid in cleared:
        assert tid in resp["transit_ids"], f"cleared transit {tid} was not scheduled"
    proposals = client.get("/api/scheduling/proposals").json()["items"]
    proposed_ids = {p["transit_id"] for p in proposals}
    for tid in cleared:
        assert tid in proposed_ids, f"cleared transit {tid} missing from proposals"
    for p in proposals:
        assert p["crew_id"] is not None, f"proposal {p['transit_id']} missing crew_id"
        assert p["vehicle_id"] is not None, f"proposal {p['transit_id']} missing vehicle_id"
        assert p["rank"] and p["vehicle_type"], f"proposal {p['transit_id']} missing details"
    actual(f"proposals returned {len(proposals)} transits with crew/vehicle")


def test_approve_sets_approved_and_relaces_assignment(client, q, actual):
    """TC-84 | POST /api/transits/{id}/approve locks in PROPOSED as APPROVED and re-latches crew/vehicle."""
    ids = client.get("/api/transits?limit=100").json()["items"]
    tid = ids[0]["transit_id"]
    _clear_assignment(q, tid)
    _set_status(q, tid, "PROPOSED")
    crew = _assigned(q, tid)["crew_id"]
    assert crew is None, "clean the assignment first"
    # re-latch a specific crew and vehicle
    crew_row = q("SELECT crew_id, rank FROM crew_profiles WHERE crew_id = %s LIMIT 1",
                 (q("SELECT MIN(crew_id) AS m FROM crew_profiles")[0]["m"],))[0]
    vehicle_row = q("SELECT vehicle_id FROM vehicles WHERE vehicle_id = %s LIMIT 1",
                    (q("SELECT MIN(vehicle_id) AS m FROM vehicles")[0]["m"],))[0]
    resp = client.post(f"/api/transits/{tid}/approve",
                       json={"crew_id": crew_row["crew_id"], "vehicle_id": vehicle_row["vehicle_id"]}).json()
    row = _assigned(q, tid)
    assert resp["schedule_status"] == "APPROVED"
    assert row["crew_id"] == crew_row["crew_id"]
    assert row["vehicle_id"] == vehicle_row["vehicle_id"]
    # approving without a body leaves the assignment untouched
    resp2 = client.post(f"/api/transits/{tid}/approve").json()
    assert resp2["schedule_status"] == "APPROVED"
    assert row["crew_id"] == resp2["crew_id"]
    actual(f"approved transit {tid}; crew/vehicle re-latched")


def test_replan_resets_and_reproposes(client, q, actual):
    """TC-85 | POST /api/transits/{id}/replan clears the assignment and sets PROPOSED."""
    ids = client.get("/api/transits?limit=100").json()["items"]
    tid = ids[0]["transit_id"]
    _clear_assignment(q, tid)
    _set_status(q, tid, "PROPOSED")
    crew_row = q("SELECT crew_id FROM crew_profiles WHERE crew_id = %s LIMIT 1", (q("SELECT MIN(crew_id) AS m FROM crew_profiles")[0]["m"],))[0]
    # assign then approve so we have a real APPROVED assignment to replan
    vehicle_row = q("SELECT vehicle_id FROM vehicles WHERE vehicle_id = %s LIMIT 1",
                    (q("SELECT MIN(vehicle_id) AS m FROM vehicles")[0]["m"],))[0]
    client.post(f"/api/transits/{tid}/approve",
                json={"crew_id": crew_row["crew_id"], "vehicle_id": vehicle_row["vehicle_id"]}).json()
    assert _assigned(q, tid)["schedule_status"] == "APPROVED"
    resp = client.post(f"/api/transits/{tid}/replan").json()
    row = _assigned(q, tid)
    assert resp["schedule_status"] == "PROPOSED"
    assert row["crew_id"] is None, "replan must clear the crew assignment"
    assert row["vehicle_id"] is None, "replan must clear the vehicle assignment"
    actual(f"replanned transit {tid}: PROPOSED with no assignment")


def test_my_transits_shows_approved_only(client, crew_client, q, actual):
    """TC-86 | GET /api/my-transits returns only APPROVED test-split transits for the crew.

    A PROPOSED or REJECTED transit must not appear, and the filter still applies
    to the signed-in crew's own transits and the test split.
    """
    # the crew account must be linked to a crew profile before my-transits sees it
    crew_me = crew_client.get("/api/me").json()
    uid = crew_me["user_id"]
    crew_id_row = q(
        "SELECT crew_id, user_id FROM crew_profiles "
        "WHERE crew_id IN ("
        "  SELECT crew_id FROM transit_events "
        "  WHERE split = 'test' AND schedule_status = 'APPROVED' "
        "  GROUP BY crew_id HAVING COUNT(*) >= 3"
        ") ORDER BY crew_id LIMIT 1")[0]
    orig_user_id = crew_id_row["user_id"]
    q("UPDATE crew_profiles SET user_id = %s WHERE crew_id = %s", (uid, crew_id_row["crew_id"]))

    # base: every test transit of this crew is APPROVED by default
    base_total = crew_client.get("/api/my-transits").json()["total"]
    assert base_total > 0

    # crew's visible transits BEFORE any change
    before_items = crew_client.get("/api/my-transits").json()["items"]
    if len(before_items) < 2:
        actual(f"crew {uid} has only {len(before_items)} transits; skipping TC-86")
        q("UPDATE crew_profiles SET user_id = %s WHERE crew_id = %s", (orig_user_id, crew_id_row["crew_id"]))
        return

    # pick two transit_ids from the crew's pre-change visible list
    replan_tid, reject_tid = before_items[0]["transit_id"], before_items[1]["transit_id"]

    # mark one PROPOSED and one REJECTED
    _clear_assignment(q, replan_tid)
    _set_status(q, replan_tid, "PROPOSED")
    _set_status(q, reject_tid, "REJECTED")

    # replan makes it PROPOSED again -> must vanish from my-transits (seen as crew)
    client.post(f"/api/transits/{replan_tid}/replan")
    items = crew_client.get("/api/my-transits").json()["items"]
    ids = {i["transit_id"] for i in items}
    assert replan_tid not in ids, "PROPOSED transit leaked into crew view"
    assert reject_tid not in ids, "REJECTED transit leaked into crew view"
    assert len(items) == base_total - 2, "my-transits size changed unexpectedly"
    actual(f"crew {uid} sees {len(items)} APPROVED test transits; proposed/rejected excluded")

    # restore crew_profiles.user_id to its original value
    q("UPDATE crew_profiles SET user_id = %s WHERE crew_id = %s", (orig_user_id, crew_id_row["crew_id"]))

def test_approve_invalid_assignment_returns_404(client, q, actual):
    """TC-87 | POST approve with a crew_id or vehicle_id that does not exist returns 404."""
    ids = client.get("/api/transits?limit=100").json()["items"]
    tid = ids[0]["transit_id"]
    _clear_assignment(q, tid)
    _set_status(q, tid, "PROPOSED")

    resp = client.post(f"/api/transits/{tid}/approve", json={"crew_id": 999999})
    assert resp.status_code == 404, resp.text
    resp = client.post(f"/api/transits/{tid}/approve", json={"vehicle_id": 999999})
    assert resp.status_code == 404, resp.text

    # the existing (clean) assignment is untouched
    row = _assigned(q, tid)
    assert row["crew_id"] is None
    assert row["vehicle_id"] is None
    actual("unknown crew_id/vehicle_id rejected with 404; assignment untouched")
