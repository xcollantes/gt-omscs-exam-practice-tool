"""Parse the "Module N Question Pool.pdf" files into static/questions.json.

Figures are written to static/img/. Run once, or again whenever the
PDFs change:

    python parse_pdfs.py
"""
import json
import re
from collections import Counter
from pathlib import Path

import pymupdf

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
IMG_DIR = STATIC / "img"
QUESTIONS_JSON = STATIC / "questions.json"

HEADER = re.compile(r"Q(\d+)\.\s+\[(MCQ|TF)\]$")
OPTION = re.compile(r"([A-D])\.\s+(.*)")
CAPTION = re.compile(r"Figure:\s*(.*?)\s*(\(Module \d+\))?$")
HEADING_COLOR = 0x365F91
HEADING_MIN_SIZE = 13
TITLE_MIN_SIZE = 20


def join(text: str, more: str, sep: str = " ") -> str:
    """Append a wrapped line, keeping hyphenated words intact."""
    if not text:
        return more
    # Reason: Word wraps after hard hyphens ("best-" / "effort").
    if text.endswith("-") and more[:1].islower():
        return text + more
    return text + sep + more


def page_events(page: pymupdf.Page):
    """Yield ("block",), ("image", block) and ("line", text, span).

    Blocks are sorted top to bottom because image blocks come last in
    PyMuPDF's output.
    """
    blocks = page.get_text("dict")["blocks"]
    for block in sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0])):
        if block["type"] == 1:
            yield ("image", block)
            continue
        yield ("block",)
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"]).strip()
            if text:
                yield ("line", text, line["spans"][0])


class PoolParser:
    """State machine that turns one module's lines into questions."""

    def __init__(self, module: int):
        self.module = module
        self.lesson = ""
        self.topic = ""
        self.questions: list[dict] = []
        self.q: dict | None = None
        self.field: str | None = None  # "stem", "option", "why" or None
        self.bullet = False
        self.new_block = False
        self.new_page = False

    def feed_page(self, page: pymupdf.Page) -> None:
        self.new_page = True
        for kind, *rest in page_events(page):
            if kind == "block":
                self.new_block = True
            elif kind == "image":
                self.image(rest[0])
            else:
                self.line(*rest)
                self.new_block = self.new_page = False

    def image(self, block: dict) -> None:
        if self.q is None or self.field != "stem":
            return
        name = f"m{self.module}_q{self.q['number']}.{block['ext']}"
        (IMG_DIR / name).write_bytes(block["image"])
        self.q["figure"] = f"img/{name}"

    def line(self, text: str, span: dict) -> None:
        if span["size"] >= TITLE_MIN_SIZE:
            return
        if (span["color"] == HEADING_COLOR
                and span["size"] >= HEADING_MIN_SIZE):
            self.topic, self.field = text, None
        elif m := HEADER.match(text):
            self.start_question(int(m[1]), m[2])
        elif self.q is None:
            if text.startswith("Lesson "):
                self.lesson = text
        elif text == "•":
            self.bullet = True
        elif self.bullet:
            self.start_option(text)
        elif m := re.match(r"Correct answer:\s*(\S+)", text):
            self.q["answer"], self.field = m[1], None
        elif text.startswith("Why:"):
            self.q["why"] = text.removeprefix("Why:").strip()
            self.field = "why"
        elif (m := CAPTION.match(text)) and not self.q["stem"]:
            self.q["caption"] = m[1]
        else:
            self.append(text)

    def start_question(self, number: int, qtype: str) -> None:
        self.q = {
            "id": f"M{self.module}-Q{number}", "module": self.module,
            "number": number, "lesson": self.lesson, "topic": self.topic,
            "type": qtype, "stem": "", "options": [], "answer": "",
            "why": "", "figure": None, "caption": None,
        }
        self.questions.append(self.q)
        self.field = "stem"

    def start_option(self, text: str) -> None:
        self.bullet = False
        if m := OPTION.match(text):
            key, text = m[1], m[2]
        else:
            key = text  # True / False
        self.q["options"].append({"key": key, "text": text})
        self.field = "option"

    def append(self, text: str) -> None:
        if self.field == "stem":
            sep = "\n" if self.new_block else " "
            # Reason: a paragraph split by a page break is still one
            # paragraph.
            if self.new_page and not self.q["stem"].endswith(
                    (".", "?", ":")):
                sep = " "
            self.q["stem"] = join(self.q["stem"], text, sep)
        elif self.field == "option":
            opt = self.q["options"][-1]
            opt["text"] = join(opt["text"], text)
        elif self.field == "why":
            self.q["why"] = join(self.q["why"], text)


def parse_pdf(path: Path) -> list[dict]:
    """Parse one module PDF into a list of question dicts."""
    module = int(re.search(r"Module (\d+)", path.name)[1])
    parser = PoolParser(module)
    with pymupdf.open(path) as doc:
        for page in doc:
            parser.feed_page(page)
    return parser.questions


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(ROOT.glob("Module * Question Pool.pdf"),
                  key=lambda p: int(re.search(r"Module (\d+)", p.name)[1]))
    questions = [q for pdf in pdfs for q in parse_pdf(pdf)]
    QUESTIONS_JSON.write_text(json.dumps(questions, indent=1))
    counts = Counter(q["module"] for q in questions)
    figures = sum(1 for q in questions if q["figure"])
    print(f"{len(questions)} questions, {figures} figures: "
          + ", ".join(f"M{m}={n}" for m, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
