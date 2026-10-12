"""Local study server: static quiz page, answer logging and stats.

    python app.py   # then open http://127.0.0.1:8000
"""
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
QUESTIONS_JSON = STATIC / "questions.json"
DB_PATH = ROOT / "study.db"
HOST, PORT = "127.0.0.1", 8000

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    modules TEXT NOT NULL,
    question_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS answers (
    answer_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    question_id TEXT NOT NULL,
    module INTEGER NOT NULL,
    topic TEXT NOT NULL,
    chosen TEXT NOT NULL,
    is_correct INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    answered_at TEXT NOT NULL,
    UNIQUE (run_id, question_id)
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database with dict-like rows."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds")


def record_answer(conn: sqlite3.Connection, questions: dict[str, dict],
                  data: dict) -> dict:
    """
    Validate and store one answer, creating its run on first use.

    Args:
        conn: Open database connection
        questions: Question pool keyed by question id
        data: Decoded POST body from the quiz page

    Returns:
        {"is_correct": bool}

    Raises:
        ValueError: If any field is missing or invalid
        sqlite3.IntegrityError: If the question was already answered
            in this run
    """
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    q = questions.get(data.get("question_id"))
    if q is None:
        raise ValueError("unknown question_id")
    chosen = data.get("chosen")
    if chosen not in [o["key"] for o in q["options"]]:
        raise ValueError("chosen is not an option of this question")
    run_id, modules = data.get("run_id"), data.get("modules")
    duration_ms, count = data.get("duration_ms"), data.get("question_count")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id is required")
    if not isinstance(modules, list) or not all(
            isinstance(m, int) for m in modules):
        raise ValueError("modules must be a list of ints")
    if not isinstance(count, int) or count < 1:
        raise ValueError("question_count must be a positive int")
    if not isinstance(duration_ms, int) or duration_ms < 0:
        raise ValueError("duration_ms must be a non-negative int")
    started_at = utc_iso(
        datetime.fromisoformat(str(data.get("started_at", ""))))

    is_correct = chosen == q["answer"]
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO runs VALUES (?, ?, ?, ?)",
            (run_id, started_at, ",".join(map(str, modules)), count))
        conn.execute(
            "INSERT INTO answers (run_id, question_id, module, topic, chosen,"
            " is_correct, duration_ms, answered_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, q["id"], q["module"], q["topic"], chosen, is_correct,
             duration_ms, utc_iso(datetime.now(UTC))))
    return {"is_correct": is_correct}


def get_stats(conn: sqlite3.Connection, pool_size: int) -> dict:
    """Aggregate all recorded answers for the dashboard."""
    def rows(sql: str) -> list[dict]:
        return [dict(r) for r in conn.execute(sql)]

    totals = rows("""
        SELECT COUNT(DISTINCT run_id) AS runs, COUNT(*) AS answered,
               COALESCE(SUM(is_correct), 0) AS correct,
               COALESCE(AVG(duration_ms), 0) AS avg_ms,
               COUNT(DISTINCT question_id) AS seen
        FROM answers""")[0]
    totals["pool_size"] = pool_size
    return {
        "totals": totals,
        "runs": rows("""
            SELECT r.run_id, r.started_at, r.modules, r.question_count,
                   COUNT(*) AS answered, SUM(a.is_correct) AS correct,
                   SUM(a.duration_ms) AS answer_ms,
                   CAST((julianday(MAX(a.answered_at))
                         - julianday(r.started_at)) * 86400000 AS INTEGER)
                       AS wall_ms
            FROM runs r JOIN answers a USING (run_id)
            GROUP BY r.run_id ORDER BY r.started_at"""),
        "by_module": rows("""
            SELECT module, COUNT(*) AS answered, SUM(is_correct) AS correct,
                   AVG(duration_ms) AS avg_ms
            FROM answers GROUP BY module ORDER BY module"""),
        "by_topic": rows("""
            SELECT module, topic, COUNT(*) AS answered,
                   SUM(is_correct) AS correct, AVG(duration_ms) AS avg_ms
            FROM answers GROUP BY module, topic
            ORDER BY 1.0 * SUM(is_correct) / COUNT(*), COUNT(*) DESC"""),
        "most_missed": rows("""
            SELECT question_id, COUNT(*) AS attempts,
                   SUM(1 - is_correct) AS misses
            FROM answers GROUP BY question_id HAVING misses > 0
            ORDER BY misses DESC, attempts LIMIT 10"""),
    }


def reset_stats(conn: sqlite3.Connection) -> dict:
    """Delete every recorded run and answer; return how many went."""
    with conn:
        answers = conn.execute("DELETE FROM answers").rowcount
        runs = conn.execute("DELETE FROM runs").rowcount
    return {"deleted_runs": runs, "deleted_answers": answers}


class Handler(SimpleHTTPRequestHandler):
    """Serves static/ plus /api/stats (GET, DELETE) and POST /api/answers."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def do_GET(self):
        if self.path != "/api/stats":
            return super().do_GET()
        with closing(connect(self.server.db_path)) as conn:
            self.send_json(get_stats(conn, len(self.server.questions)))

    def do_DELETE(self):
        if self.path != "/api/stats":
            return self.send_json({"error": "not found"}, 404)
        with closing(connect(self.server.db_path)) as conn:
            self.send_json(reset_stats(conn))

    def do_POST(self):
        if self.path != "/api/answers":
            return self.send_json({"error": "not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            with closing(connect(self.server.db_path)) as conn:
                result = record_answer(conn, self.server.questions, data)
        except (ValueError, sqlite3.IntegrityError) as e:
            return self.send_json({"error": str(e)}, 400)
        self.send_json(result)

    def send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(db_path: Path = DB_PATH, port: int = PORT,
                questions_path: Path = QUESTIONS_JSON) -> ThreadingHTTPServer:
    """Create the server with its question pool and an initialized DB."""
    server = ThreadingHTTPServer((HOST, port), Handler)
    server.questions = {
        q["id"]: q for q in json.loads(questions_path.read_text())}
    server.db_path = db_path
    with closing(connect(db_path)) as conn:
        conn.executescript(SCHEMA)
    return server


def main() -> None:
    if not QUESTIONS_JSON.exists():
        sys.exit("static/questions.json is missing: run python parse_pdfs.py")
    server = make_server()
    print(f"Studying at http://{HOST}:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
