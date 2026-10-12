# CS 6250 Study

A local quiz app built from the six "Module N Question Pool.pdf" files.
It asks random questions, times each answer, shows the explanation, and
saves every answer to SQLite (`study.db`). A dashboard shows your
results over time.

## Setup

```bash
python3 -m venv env
source env/bin/activate
pip install pip -U
pip install -r requirements.txt
python parse_pdfs.py   # PDFs -> static/questions.json + static/img/
```

Run `python parse_pdfs.py` again whenever the PDFs change.

## Study

```bash
python app.py          # http://127.0.0.1:8000
```

Choose modules and a question count, then answer with the mouse or keys:
A–D or 1–4 (T/F for true/false), and Enter for the next question.
Each answer is saved as soon as you give it, so a run you end early
still counts.

## Test

```bash
python -m pytest
```

## Files

- `parse_pdfs.py`: PDF parser (PyMuPDF)
- `app.py`: stdlib HTTP server, `POST /api/answers`, `GET /api/stats`
- `static/`: page (`index.html`, `app.js`) and generated questions/figures
- `study.db`: your results (tables `runs` and `answers`)
