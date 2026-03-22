iimport os
import json
import html
import sqlite3
from datetime import datetime
from pathlib import Path

import requests
from groq import Groq


DB_PATH = "weather.db"
DOCS_DIR = Path("docs")
HTML_PATH = DOCS_DIR / "index.html"

# --------------------------------------------------
# CHANGE THESE THREE LOCATIONS
# --------------------------------------------------
LOCATIONS = [
    {"label": "Place of birth", "query": "Dhaka"},
    {"label": "Last residence before Aalborg", "query": "Copenhagen"},
    {"label": "Current city", "query": "Aalborg"},
]

# Daily weather variables from Open-Meteo
DAILY_VARS = [
    "temperature_2m_max",
    "precipitation_sum",
    "wind_speed_10m_max",
    "relative_humidity_2m_mean",
]


def geocode_place(place_name: str) -> dict:
    """
    Use Open-Meteo geocoding API to convert a place name into coordinates.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": place_name,
        "count": 1,
        "language": "en",
        "format": "json",
    }
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    results = data.get("results")
    if not results:
        raise ValueError(f"Could not geocode place: {place_name}")

    top = results[0]
    return {
        "name": top["name"],
        "country": top.get("country", ""),
        "latitude": top["latitude"],
        "longitude": top["longitude"],
    }


def fetch_tomorrow_weather(location: dict) -> dict:
    """
    Fetch tomorrow's forecast for one location from Open-Meteo.
    """
    geo = geocode_place(location["query"])

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
        "forecast_days": 2,
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    daily = data["daily"]
    times = daily["time"]

    if len(times) < 2:
        raise ValueError(f"Not enough forecast days returned for {location['query']}")

    # index 0 = today, index 1 = tomorrow
    i = 1

    return {
        "label": location["label"],
        "query": location["query"],
        "resolved_name": geo["name"],
        "country": geo["country"],
        "latitude": geo["latitude"],
        "longitude": geo["longitude"],
        "forecast_date": times[i],
        "temperature_2m_max": daily["temperature_2m_max"][i],
        "precipitation_sum": daily["precipitation_sum"][i],
        "wind_speed_10m_max": daily["wind_speed_10m_max"][i],
        "relative_humidity_2m_mean": daily["relative_humidity_2m_mean"][i],
    }


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            query TEXT NOT NULL,
            resolved_name TEXT NOT NULL,
            country TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            forecast_date TEXT NOT NULL,
            temperature_2m_max REAL,
            precipitation_sum REAL,
            wind_speed_10m_max REAL,
            relative_humidity_2m_mean REAL,
            fetched_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def save_forecasts(conn: sqlite3.Connection, forecasts: list[dict]) -> None:
    fetched_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    conn.executemany(
        """
        INSERT INTO forecasts (
            label, query, resolved_name, country, latitude, longitude,
            forecast_date, temperature_2m_max, precipitation_sum,
            wind_speed_10m_max, relative_humidity_2m_mean, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                f["label"],
                f["query"],
                f["resolved_name"],
                f["country"],
                f["latitude"],
                f["longitude"],
                f["forecast_date"],
                f["temperature_2m_max"],
                f["precipitation_sum"],
                f["wind_speed_10m_max"],
                f["relative_humidity_2m_mean"],
                fetched_at,
            )
            for f in forecasts
        ],
    )
    conn.commit()


def choose_best_place(forecasts: list[dict]) -> str:
    """
    A simple comfort score:
    - lower rain is better
    - lower wind is better
    - temperature around 22C is preferred
    - humidity around 50% is preferred
    """
    def score(f: dict) -> float:
        temp_penalty = abs(f["temperature_2m_max"] - 22) * 1.5
        rain_penalty = f["precipitation_sum"] * 2.0
        wind_penalty = f["wind_speed_10m_max"] * 0.4
        humidity_penalty = abs(f["relative_humidity_2m_mean"] - 50) * 0.1
        return temp_penalty + rain_penalty + wind_penalty + humidity_penalty

    best = min(forecasts, key=score)
    return f'{best["resolved_name"]}, {best["country"]}'


def generate_poem(forecasts: list[dict]) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set.")

    best_place = choose_best_place(forecasts)

    weather_lines = []
    for f in forecasts:
        weather_lines.append(
            (
                f'- {f["label"]}: {f["resolved_name"]}, {f["country"]} '
                f'on {f["forecast_date"]}: '
                f'max temp {f["temperature_2m_max"]}°C, '
                f'precipitation {f["precipitation_sum"]} mm, '
                f'max wind {f["wind_speed_10m_max"]} km/h, '
                f'mean humidity {f["relative_humidity_2m_mean"]}%.'
            )
        )

    prompt = f"""
You are a poetic weather narrator.

Write one short poem comparing tomorrow's weather in three places.
The poem must:
1. compare the weather in all three locations,
2. describe the differences clearly,
3. suggest where it would be nicest to be tomorrow,
4. be bilingual: first English, then Bangla,
5. be concise but creative,
6. explicitly mention the best place as: {best_place}

Weather data:
{chr(10).join(weather_lines)}
""".strip()

    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You write clean, vivid bilingual poems."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_completion_tokens=500,
    )
    return completion.choices[0].message.content.strip()


def build_html(forecasts: list[dict], poem: str) -> str:
    rows = []
    for f in forecasts:
        rows.append(
            f"""
            <tr>
              <td>{html.escape(f["label"])}</td>
              <td>{html.escape(f["resolved_name"] + ", " + f["country"])}</td>
              <td>{html.escape(f["forecast_date"])}</td>
              <td>{f["temperature_2m_max"]} °C</td>
              <td>{f["precipitation_sum"]} mm</td>
              <td>{f["wind_speed_10m_max"]} km/h</td>
              <td>{f["relative_humidity_2m_mean"]} %</td>
            </tr>
            """
        )

    poem_html = "<br>".join(html.escape(poem).splitlines())

    generated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Automated Weather Poem</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      max-width: 900px;
      margin: 40px auto;
      padding: 0 16px;
      line-height: 1.6;
      background: #f8fbff;
      color: #1f2937;
    }}
    h1, h2 {{
      color: #0f172a;
    }}
    .card {{
      background: white;
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
      margin-bottom: 24px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
    }}
    th, td {{
      border: 1px solid #dbeafe;
      padding: 10px;
      text-align: left;
    }}
    th {{
      background: #e0f2fe;
    }}
    .small {{
      color: #475569;
      font-size: 0.95rem;
    }}
    pre {{
      white-space: pre-wrap;
      word-wrap: break-word;
      font-family: inherit;
      font-size: 1.05rem;
    }}
  </style>
</head>
<body>
  <h1>Automated Weather Pipeline</h1>

  <div class="card">
    <h2>Bilingual Weather Poem</h2>
    <pre>{poem_html}</pre>
  </div>

  <div class="card">
    <h2>Tomorrow's Forecast</h2>
    <table>
      <thead>
        <tr>
          <th>Type</th>
          <th>Location</th>
          <th>Date</th>
          <th>Max Temp</th>
          <th>Precipitation</th>
          <th>Max Wind</th>
          <th>Humidity</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>

  <p class="small">Last generated: {generated_at}</p>
</body>
</html>
"""


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    forecasts = [fetch_tomorrow_weather(loc) for loc in LOCATIONS]

    with sqlite3.connect(DB_PATH) as conn:
        init_db(conn)
        save_forecasts(conn, forecasts)

    poem = generate_poem(forecasts)

    html_content = build_html(forecasts, poem)
    HTML_PATH.write_text(html_content, encoding="utf-8")

    # Optional JSON output for debugging or reuse
    Path("latest.json").write_text(
        json.dumps({"forecasts": forecasts, "poem": poem}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Done: weather fetched, DB updated, poem generated, docs/index.html written.")


if __name__ == "__main__":
    main()
