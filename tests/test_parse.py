"""Checks parse_pdfs.py against the six module PDFs."""
from collections import Counter

import pytest

from parse_pdfs import IMG_DIR, ROOT, STATIC, parse_pdf

EXPECTED_COUNTS = {1: 35, 2: 55, 3: 30, 4: 39, 5: 39, 6: 28}


@pytest.fixture(scope="module")
def questions():
    """Parse every module PDF once."""
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    return [q for pdf in ROOT.glob("Module * Question Pool.pdf")
            for q in parse_pdf(pdf)]


@pytest.fixture(scope="module")
def by_id(questions):
    return {q["id"]: q for q in questions}


def test_question_count_per_module(questions):
    assert Counter(q["module"] for q in questions) == EXPECTED_COUNTS


def test_every_question_is_complete(questions):
    for q in questions:
        keys = [o["key"] for o in q["options"]]
        expected = ["A", "B", "C", "D"] if q["type"] == "MCQ" else [
            "True", "False"]
        assert keys == expected, q["id"]
        assert all(o["text"] for o in q["options"]), q["id"]
        assert q["answer"] in keys, q["id"]
        assert q["stem"] and q["why"] and q["topic"] and q["lesson"], q["id"]


def test_every_caption_has_a_figure_file(questions):
    for q in questions:
        assert bool(q["caption"]) == bool(q["figure"]), q["id"]
        if q["figure"]:
            assert (STATIC / q["figure"]).is_file(), q["id"]


def test_stem_lines_that_look_like_headers_stay_in_stem(by_id):
    assert "\nQ1 = 1*\n" in by_id["M5-Q23"]["stem"]


def test_indented_stem_lines_keep_their_line_breaks(by_id):
    stem = by_id["M4-Q24"]["stem"]
    assert "\nRoute 1: LocalPref 100" in stem
    assert "\nRoute 3: LocalPref 80" in stem
