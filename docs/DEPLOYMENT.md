# Deployment Guide

## Runtime Profiles

The project supports three runtime profiles:

- `local`
- `dev`
- `prod`

Profiles are defined in `config/profiles/*.json` and selected by:

1. CLI flag: `--env`
2. Environment variable: `APP_ENV`
3. Fallback default: `local`

## Docker

### Build and run

```bash
docker compose up --build
```

### Run with a specific profile

```bash
APP_ENV=dev docker compose up --build
```

### Persisted data

`docker-compose.yml` mounts:

- `./outputs` to `/app/outputs`
- `./data` to `/app/data`

so generated reports/history remain on the host.

## Direct (non-Docker) runs

### Streamlit

```bash
APP_ENV=local streamlit run streamlit_app.py
```

### CLI

```bash
python -m src.cli --env prod --input "data/samples/example.xlsx"
```

## Streamlit Cloud

Use these app settings on Streamlit Cloud:

- Main file path: `streamlit_app.py`
- Python dependencies: `requirements.txt`
- Python runtime pin: `runtime.txt` (`python-3.11`)
- Optional environment variable: `APP_ENV=prod`

Notes:
- `prod` profile defaults `Run NLP Analysis` to OFF for lighter cloud runs.
- Enable NLP only when you need clustering/negative recommendations.
- 48-hour date checking is advisory only; recent files show a warning but runs continue.

## Phase C Smoke Checklist

1. Upload sample bulk file in Streamlit and run optimization.
2. Download unified export and confirm it opens without worksheet-name errors.
3. Re-open the export and verify required Amazon upload columns/sheets exist.
