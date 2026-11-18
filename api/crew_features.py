"""Crew features (Sprint III): readiness checklist and arrival confirmation (FR-09, FR-11)
and GPS location sharing (FR-03).

A crew member can only see and change their own transits. Only dispatchers can read locations.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, PositiveInt

from .auth import require_crew, require_dispatcher
from .db import fetch_all, fetch_one, get_conn

router = APIRouter()

# The fixed readiness tasks every transit has. Change the labels here to change the app.
CHECKLIST_TASKS = [
    ("UNIFORM", "Uniform collected"),
    ("MEDICAL", "Medical evaluation checked out"),
    ("DOCUMENTS", "ID and crew documents ready"),
]
TASK_CODES = {code for code, _ in CHECKLIST_TASKS}


class TaskUpdate(BaseModel):
    done: bool


def _own_transit(conn, transit_id: int, user_id: int):
    """The transit row if it belongs to this crew member, otherwise None."""
    return fetch_one(
        conn,
        """
        SELECT t.transit_id
        FROM transit_events t
        JOIN crew_profiles c ON c.crew_id = t.crew_id
        WHERE t.transit_id = %(tid)s AND c.user_id = %(uid)s AND t.split = 'test'
        """,
        {"tid": transit_id, "uid": user_id},
    )


def _checklist(conn, transit_id: int) -> dict:
    rows = fetch_all(
        conn,
        "SELECT task_code, done FROM transit_checklist WHERE transit_id = %s",
        (transit_id,),
    )
    state = {r["task_code"]: r["done"] for r in rows}
    arrival = fetch_one(
        conn,
        "SELECT confirmed_at FROM transit_arrival WHERE transit_id = %s",
        (transit_id,),
    )
    return {
        "transit_id": transit_id,
        "tasks": [
            {"code": code, "label": label, "done": state.get(code, False)}
            for code, label in CHECKLIST_TASKS
        ],
        "arrived": arrival is not None,
        "arrived_at": arrival["confirmed_at"] if arrival else None,
    }


@router.get("/api/my-transits/{transit_id}/checklist")
def get_checklist(transit_id: PositiveInt, user: dict = Depends(require_crew)):
    """The readiness checklist and arrival state of one of my transits."""
    with get_conn() as conn:
        if not _own_transit(conn, transit_id, user["user_id"]):
            raise HTTPException(status_code=404, detail="Transit not found.")
        return _checklist(conn, transit_id)


@router.put("/api/my-transits/{transit_id}/checklist/{task_code}")
def set_task(
    transit_id: PositiveInt,
    task_code: str,
    body: TaskUpdate,
    user: dict = Depends(require_crew),
):
    """Tick or untick one readiness task."""
    code = task_code.upper()
    if code not in TASK_CODES:
        raise HTTPException(status_code=404, detail="Unknown checklist task.")
    with get_conn() as conn:
        if not _own_transit(conn, transit_id, user["user_id"]):
            raise HTTPException(status_code=404, detail="Transit not found.")
        fetch_one(
            conn,
            """
            INSERT INTO transit_checklist (transit_id, task_code, done, done_at)
            VALUES (%(tid)s, %(code)s, %(done)s, CASE WHEN %(done)s THEN NOW() ELSE NULL END)
            ON CONFLICT (transit_id, task_code)
            DO UPDATE SET done = EXCLUDED.done, done_at = EXCLUDED.done_at
            RETURNING item_id
            """,
            {"tid": transit_id, "code": code, "done": body.done},
        )
        return _checklist(conn, transit_id)


@router.post("/api/my-transits/{transit_id}/arrived")
def confirm_arrival(transit_id: PositiveInt, user: dict = Depends(require_crew)):
    """Confirm arrival at the destination. Safe to call twice: the first time counts."""
    with get_conn() as conn:
        if not _own_transit(conn, transit_id, user["user_id"]):
            raise HTTPException(status_code=404, detail="Transit not found.")
        fetch_one(
            conn,
            """
            INSERT INTO transit_arrival (transit_id, confirmed_by)
            VALUES (%s, %s)
            ON CONFLICT (transit_id) DO NOTHING
            RETURNING transit_id
            """,
            (transit_id, user["user_id"]),
        )
        return _checklist(conn, transit_id)


# --------------------------------------------------------------------------
# GPS location sharing (FR-03)
class LocationPing(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    accuracy_m: Optional[float] = Field(None, ge=0, le=100000)


@router.post("/api/my-transits/{transit_id}/location")
def post_location(
    transit_id: PositiveInt,
    ping: LocationPing,
    user: dict = Depends(require_crew),
):
    """Store the phone's current position for one of my transits.

    Once arrival has been confirmed the transit is complete and sharing stops (409).
    """
    with get_conn() as conn:
        if not _own_transit(conn, transit_id, user["user_id"]):
            raise HTTPException(status_code=404, detail="Transit not found.")
        done = fetch_one(
            conn,
            "SELECT transit_id FROM transit_arrival WHERE transit_id = %s",
            (transit_id,),
        )
        if done:
            raise HTTPException(
                status_code=409,
                detail="This transit is already complete, so location sharing has stopped.",
            )
        row = fetch_one(
            conn,
            """
            INSERT INTO gps_pings (transit_id, user_id, latitude, longitude, accuracy_m)
            VALUES (%(tid)s, %(uid)s, %(lat)s, %(lon)s, %(acc)s)
            RETURNING recorded_at
            """,
            {
                "tid": transit_id,
                "uid": user["user_id"],
                "lat": ping.latitude,
                "lon": ping.longitude,
                "acc": ping.accuracy_m,
            },
        )
    return {"ok": True, "recorded_at": row["recorded_at"]}


@router.get("/api/crew-locations", dependencies=[Depends(require_dispatcher)])
def crew_locations(max_age_minutes: int = Query(120, ge=1, le=1440)):
    """The last known position of each transit that has shared one recently (dispatchers only)."""
    with get_conn() as conn:
        items = fetch_all(
            conn,
            """
            SELECT * FROM (
                SELECT DISTINCT ON (g.transit_id)
                       g.transit_id, t.corridor, u.full_name AS crew_name,
                       g.latitude, g.longitude, g.accuracy_m, g.recorded_at,
                       (a.transit_id IS NOT NULL) AS arrived
                FROM gps_pings g
                JOIN transit_events t ON t.transit_id = g.transit_id
                JOIN users u ON u.user_id = g.user_id
                LEFT JOIN transit_arrival a ON a.transit_id = g.transit_id
                WHERE g.recorded_at >= NOW() - (%(mins)s * INTERVAL '1 minute')
                ORDER BY g.transit_id, g.recorded_at DESC
            ) latest
            ORDER BY latest.recorded_at DESC
            LIMIT 200
            """,
            {"mins": max_age_minutes},
        )
    return {"total": len(items), "max_age_minutes": max_age_minutes, "items": items}