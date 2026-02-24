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
APP_ENV=local streamlit run src/app.py
```

### CLI

```bash
python -m src.cli --env prod --input "data/samples/example.xlsx"
```
