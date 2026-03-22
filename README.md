# S2_M6_WeatherAnalysis
# Automated Weather Pipeline with GitHub Pages

This project is a small automated data pipeline for a university assignment.

# See website: https://faraiba.github.io/S2_M6_WeatherAnalysis/

## What it does

Every day, the pipeline:

1. fetches tomorrow's weather forecast from Open-Meteo,
2. stores the forecast in a SQLite database,
3. generates a bilingual poem with Groq,
4. publishes the result to a GitHub Pages website.

## Locations

- DHAKA
- COPENHAGEN
- AALBORG

## Weather variables used

- maximum temperature
- precipitation sum
- maximum wind speed
- mean relative humidity

## Files

- `fetch.py` — main pipeline script
- `weather.db` — SQLite database
- `docs/index.html` — GitHub Pages site
- `.github/workflows/weather.yml` — automation workflow

## Setup

1. Create a public GitHub repository.
2. Add your locations in `fetch.py`.
3. Add a repository secret:
   - `GROQ_API_KEY`
4. Enable GitHub Pages:
   - Source: `Deploy from a branch`
   - Branch: `main`
   - Folder: `/docs`

## Run locally

```bash
pip install -r requirements.txt
export GROQ_API_KEY="your_api_key_here"
python fetch.py
