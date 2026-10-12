"""End-to-end checks of the HTTP API against a temporary database."""
import json
import threading
import urllib.error
import urllib.request

import pytest

from app import make_server

QUESTIONS = [
    {"id": "M1-Q1", "module": 1, "topic": "Layering", "answer": "A",
     "options": [{"key": k, "text": k} for k in "ABCD"]},
    {"id": "M2-Q1", "module": 2, "topic": "TCP", "answer": "True",
     "options": [{"key": "True", "text": "True"},
                 {"key": "False", "text": "False"}]},
]


@pytest.fixture
def base_url(tmp_path):
    """Run the server on a free port with a throwaway DB and pool."""
    questions_path = tmp_path / "questions.json"
    questions_path.write_text(json.dumps(QUESTIONS))
    server = make_server(tmp_path / "test.db", 0, questions_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(url: str, body: dict | None = None,
         method: str | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url, data, {"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def answer(question_id: str, chosen: str, **overrides) -> dict:
    return {"run_id": "run-1", "started_at": "2026-10-11T10:00:00.000Z",
            "modules": [1, 2], "question_count": 2,
            "question_id": question_id, "chosen": chosen,
            "duration_ms": 4000, **overrides}


def test_answers_are_scored_and_summarized(base_url):
    assert call(f"{base_url}/api/answers", answer("M1-Q1", "A")) == (
        200, {"is_correct": True})
    assert call(f"{base_url}/api/answers", answer("M2-Q1", "False")) == (
        200, {"is_correct": False})

    status, stats = call(f"{base_url}/api/stats")
    assert status == 200
    assert stats["totals"] == {"runs": 1, "answered": 2, "correct": 1,
                               "avg_ms": 4000, "seen": 2, "pool_size": 2}
    [run] = stats["runs"]
    assert (run["answered"], run["correct"], run["answer_ms"]) == (2, 1, 8000)
    assert run["modules"] == "1,2" and run["wall_ms"] > 0
    assert stats["by_topic"][0]["topic"] == "TCP"  # weakest first
    assert stats["most_missed"] == [
        {"question_id": "M2-Q1", "attempts": 1, "misses": 1}]


@pytest.mark.parametrize("body", [
    answer("M9-Q9", "A"),
    answer("M1-Q1", "E"),
    answer("M1-Q1", "A", duration_ms=-1),
    answer("M1-Q1", "A", started_at="yesterday"),
    answer("M1-Q1", "A", modules="1"),
])
def test_invalid_answers_are_rejected(base_url, body):
    status, response = call(f"{base_url}/api/answers", body)
    assert status == 400 and "error" in response


def test_same_question_twice_in_a_run_is_rejected(base_url):
    assert call(f"{base_url}/api/answers", answer("M1-Q1", "A"))[0] == 200
    assert call(f"{base_url}/api/answers", answer("M1-Q1", "B"))[0] == 400


def test_reset_deletes_every_run_and_answer(base_url):
    call(f"{base_url}/api/answers", answer("M1-Q1", "A"))
    call(f"{base_url}/api/answers", answer("M2-Q1", "True", run_id="run-2"))

    assert call(f"{base_url}/api/stats", method="DELETE") == (
        200, {"deleted_runs": 2, "deleted_answers": 2})

    _, stats = call(f"{base_url}/api/stats")
    assert stats["totals"]["answered"] == 0
    assert stats["runs"] == [] and stats["most_missed"] == []
