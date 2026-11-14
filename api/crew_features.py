"""Crew readiness checklist and arrival confirmation (Sprint III: FR-09 and FR-11).

A crew member can only see and change the checklist of their own transits.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, PositiveInt

from .auth import require_crew
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