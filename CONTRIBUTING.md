# Contributing to ColorComic

Thanks for your interest in improving ColorComic! This guide covers the essentials.

## Development setup

```bash
git clone https://github.com/vikast908/ColorComic.git
cd ColorComic
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install torch torchvision      # add the CUDA index URL for GPU — see README
pip install -r requirements.txt
cp .env.example .env               # optional; edit as needed
python app.py                      # http://127.0.0.1:5000
```

First run downloads model weights automatically (~140 MB for auto mode; ~6 GB for
reference mode on first use).

## Project layout

- `app.py` — Flask routes and the per-job colorization worker.
- `config.py` — all configuration (env vars, paths, version).
- `core/` — the pipeline: colorizers, post-processing, guided coloring, PDF I/O.
- `vendor/` — vendored third-party inference code (see their licenses).
- `templates/` + `static/` — the web UI.

See the README's **Project Structure** section for a per-file breakdown, and
`CHANGELOG.md` for the history of what changed and why.

## Ground rules

- **Match the surrounding style.** No new formatters or linters; follow the
  conventions already in the file you're editing.
- **Keep auto/reference modes fully local.** Only LLM mode and the optional
  text-only color director may reach the network, and both must degrade
  gracefully when `OPENROUTER_API_KEY` is absent.
- **Don't commit** `.env`, model weights, `uploads/`, `output/`, `logs/`, or test
  PDFs — they're gitignored for a reason.
- **Performance matters.** The post-processing and inference paths run once per
  page; avoid redundant color-space conversions and full-image Python loops.
- **Respect the licenses.** Project code is MIT; the vendored MangaNinja code is
  CC BY-NC 4.0 (non-commercial). Don't relicense vendored code.

## Testing your change

There is no heavyweight test harness. Before opening a PR:

1. `python -m py_compile app.py config.py core/*.py` — everything must import.
2. Run a short job end-to-end (a 1–2 page PDF, Draft quality, CPU) and confirm
   the pipeline completes and the PDF downloads.
3. For color/post-processing changes, sanity-check with a synthetic image or a
   real page rather than eyeballing code alone.

## Submitting

1. Branch off `main`.
2. Make focused commits with clear messages.
3. Update `CHANGELOG.md` under an `## [Unreleased]` heading, and the README if you
   changed behavior, config, or endpoints.
4. Open a PR describing the change and how you verified it.
