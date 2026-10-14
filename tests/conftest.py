"""
Test fixtures and the automatic test log.

Safety: the suite never touches your real database. It builds its own throw-away
database called `kq_test` on the same PostgreSQL server (connection details come
from DATABASE_URL / .env), generates a small synthetic dataset, loads it, and trains
a small model. Every run starts from a fresh `kq_test`.

Each test documents itself in its docstring as:
    TC-NN | what is being tested | expected result
and may call the `actual` fixture to record what really happened. After the run,
docs/test_log.md is written with test, expected result, actual result, outcome and
corrective action.
"""

import datetime
import os
import re
import subprocess
import sys

import psycopg2
import psycopg2.extensions
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

TEST_DB = "kq_test"


# ---------------------------------------------------------------- test log
_DOCS, _RESULTS = {}, {}


def pytest_addoption(parser):
    parser.addoption("--test-log", default=os.path.join(ROOT, "docs", "test_log.md"),
                     help="Where to write the test log (markdown).")


def pytest_collection_modifyitems(items):
    for item in items:
        _DOCS[item.nodeid] = (item.function.__doc__ or "").strip()


def pytest_runtest_logreport(report):
    failed_setup = report.when == "setup" and report.outcome != "passed"
    if report.when == "call" or failed_setup:
        msg = ""
        if report.failed and getattr(report.longrepr, "reprcrash", None):
            msg = report.longrepr.reprcrash.message
        elif report.failed:
            msg = str(report.longrepr)[-300:]
        _RESULTS[report.nodeid] = {
            "outcome": "ERROR" if failed_setup else report.outcome.upper(),
            "actual": dict(report.user_properties).get("actual", ""),
            "message": msg}


def _cell(text):
    return re.sub(r"\s+", " ", str(text)).replace("|", "\\|").strip()


def _corrections():
    path = os.path.join(ROOT, "tests", "corrections.md")
    out = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            m = re.match(r"\s*[-*]?\s*(TC-\d+)\s*:\s*(.+)", line)
            if m:
                out[m.group(1)] = m.group(2).strip()
    return out


def pytest_sessionfinish(session, exitstatus):
    if not _RESULTS:
        return
    path = session.config.getoption("--test-log")
    fixes = _corrections()
    rows = []
    for nodeid, doc in _DOCS.items():
        if nodeid not in _RESULTS:
            continue
        parts = [p.strip() for p in doc.split("|")]
        tc, what, expected = (parts + ["", "", ""])[:3]
        r = _RESULTS[nodeid]
        actual = r["actual"] or ("As expected" if r["outcome"] == "PASSED" else "")
        if r["outcome"] != "PASSED":
            actual = (actual + " " + r["message"]).strip()
        action = fixes.get(tc) or ("None needed" if r["outcome"] == "PASSED" else "Open: investigate")
        rows.append((tc, what, expected, actual, r["outcome"], action))
    rows.sort(key=lambda x: int(re.sub(r"\D", "", x[0]) or 0))
    passed = sum(1 for r in rows if r[4] == "PASSED")
    lines = [
        "# Test log",
        "",
        f"Generated {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')} by `pytest`. "
        f"Result: **{passed} of {len(rows)} checks passed** across {len({r[0] for r in rows})} test cases "
        "(a test case with several inputs counts one check per input).",
        "",
        "Run against a throw-away database (`kq_test`) with a small synthetic dataset and a model "
        "trained on it, so the suite never touches the working database.",
        "",
        "| ID | Test | Expected result | Actual result | Outcome | Corrective action |",
        "|---|---|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


@pytest.fixture
def actual(request):
    """Call actual('what really happened') to record it in the test log."""
    def record(text):
        request.node.user_properties.append(("actual", text))
    return record


# ---------------------------------------------------------------- environment
@pytest.fixture(scope="session")
def test_db_url():
    from api.config import get_database_url
    dsn = psycopg2.extensions.parse_dsn(get_database_url())
    if dsn.get("dbname") == TEST_DB:
        pytest.exit(f"DATABASE_URL must not point at '{TEST_DB}': the tests recreate that database.", 2)
    try:
        admin = psycopg2.connect(**dict(dsn, dbname="postgres"), connect_timeout=5)
    except psycopg2.OperationalError as e:
        pytest.exit("Cannot reach PostgreSQL to build the test database. Is it running, and is "
                    f"DATABASE_URL (or .env) correct?\n{e}", 2)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    admin.close()
    return psycopg2.extensions.make_dsn(**dict(dsn, dbname=TEST_DB))


@pytest.fixture(scope="session")
def dataset_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("dataset")
    subprocess.run([sys.executable, os.path.join(ROOT, "data", "generate_dataset.py"),
                    "--n-transit", "1500", "--n-flights", "400", "--n-crew", "60",
                    "--n-vehicles", "20", "--outdir", str(out)],
                   check=True, capture_output=True)
    return str(out)


@pytest.fixture(scope="session")
def model_file(dataset_dir, tmp_path_factory):
    path = str(tmp_path_factory.mktemp("model") / "xgb_test.pkl")
    subprocess.run([sys.executable, os.path.join(ROOT, "ml", "training", "train_xgboost.py"),
                    "--data-dir", dataset_dir, "--out", path, "--skip-tuning"],
                   check=True, capture_output=True)
    return path


@pytest.fixture(scope="session")
def env(test_db_url, model_file):
    keys = ("DATABASE_URL", "MODEL_PATH", "ALERT_THRESHOLD")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["DATABASE_URL"], os.environ["MODEL_PATH"] = test_db_url, model_file
    os.environ.pop("ALERT_THRESHOLD", None)
    yield
    for k, v in saved.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


@pytest.fixture(scope="session")
def loaded_db(env, test_db_url, dataset_dir):
    from db.load_data import load_all
    return load_all(test_db_url, dataset_dir, quiet=True)


@pytest.fixture(autouse=True)
def clean_model_state(loaded_db, test_db_url):
    """Every test starts with no predictions and no model-raised alerts."""
    conn = psycopg2.connect(test_db_url)
    with conn, conn.cursor() as cur:
        cur.execute("TRUNCATE predictions RESTART IDENTITY")
        cur.execute("DELETE FROM alerts WHERE source = 'model'")
    conn.close()


@pytest.fixture
def q(test_db_url):
    """Run SQL against the test database and get a list of dict rows."""
    def run(sql, params=None):
        conn = psycopg2.connect(test_db_url)
        try:
            with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()] if cur.description else []
        finally:
            conn.close()
    return run


@pytest.fixture
def client(loaded_db):
    from api.main import app
    return TestClient(app)


def first_ids(client, n=100):
    """First n held-out test-split transit ids, in pickup order."""
    items = client.get(f"/api/transits?limit={min(n, 200)}").json()["items"]
    return [i["transit_id"] for i in items]
