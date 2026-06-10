# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What this app does

Fort Worth Crime Detector is a public web app that pulls reported crime data from the City of Fort Worth's open data portal, stores it in a PostgreSQL database, and renders it on an interactive map with filters and clustering. The live SODA API is **never** called on a page request — all map data is served from the local database, which is kept fresh by a background worker.

---

## External accounts and credentials you need to set up

Before you can run the app you need two things from outside this codebase. Neither costs money.

### 1. Socrata App Token (Fort Worth open data)

The crime data comes from the City of Fort Worth's Socrata open data portal. The app works without a token, but requests will be rate-limited to a few per hour. A free token removes that limit.

**Steps:**
1. Go to https://data.fortworthtexas.gov
2. Click **Sign In** → **Sign Up** and create a free account
3. After logging in, click your profile picture → **Developer Settings**
4. Click **Create New App Token**, give it a name (e.g. "Crime Detector"), and copy the token string
5. Paste it as `SODA_APP_TOKEN=abc123...` in your `.env` file

The dataset being queried is `k6ic-7kp7` (Fort Worth Police incident reports). You can browse it at https://data.fortworthtexas.gov/Public-Safety/Crime-Data/k6ic-7kp7

### 2. PostgreSQL database with PostGIS

The app stores crime records in Postgres and uses PostGIS for all geographic queries (bounding-box lookups, spatial indexing, geometry clustering). You need a database with the PostGIS extension enabled. Choose one of these three options:

#### Option A — Docker Desktop (easiest, nothing to install manually)
If you have [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed, `docker compose up` automatically creates a PostGIS database container. You do not need to set `DATABASE_URL` yourself — docker-compose wires the services together internally. Skip to the **Running the app** section.

#### Option B — Local PostgreSQL install
1. Download and install PostgreSQL from https://www.postgresql.org/download/windows/
2. During (or after) install, open **Stack Builder** → Spatial Extensions → install **PostGIS**
3. Open pgAdmin or the `psql` shell and run:
   ```sql
   CREATE DATABASE crimedetector;
   \c crimedetector
   CREATE EXTENSION postgis;
   ```
4. Your `DATABASE_URL` will be: `postgresql://postgres:yourpassword@localhost/crimedetector`

#### Option C — Free cloud database (no local install)
Both of these services offer free tiers with PostGIS already enabled:
- **Supabase** — https://supabase.com → New Project → copy the **URI** from Settings → Database
- **Neon** — https://neon.tech → New Project → copy the connection string

Paste whichever URI you get as `DATABASE_URL=...` in your `.env` file.

---

## First-time setup checklist

```
[ ] 1. Get a SODA App Token (data.fortworthtexas.gov — free account)
[ ] 2. Have a Postgres + PostGIS database (Docker, local install, or cloud)
[ ] 3. Copy .env.example → .env  and fill in every value:
          DATABASE_URL=postgresql://user:pass@host/crimedetector
          SODA_APP_TOKEN=your_token_here
          POSTGRES_PASSWORD=any_password    (only used by docker-compose db container)
          SECRET_KEY=any_long_random_string
          FLASK_ENV=development
[ ] 4. Create a Python virtual environment and install deps  (see below)
[ ] 5. Run: alembic upgrade head             (creates the crimes table in Postgres)
[ ] 6. Run the ingest worker once            (pulls data from Fort Worth into the DB)
[ ] 7. Run the Flask dev server              (start the web app)
```

---

## Running the app

### With Docker (full stack — recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```powershell
# First time only: create your .env file
cp .env.example .env
# Edit .env and fill in SODA_APP_TOKEN, SECRET_KEY, POSTGRES_PASSWORD

# Start everything: database + web server + ingest worker
docker compose up

# App is at http://localhost:8000
```

Docker compose runs three services automatically:
- `db` — PostGIS database (data persists in a named Docker volume)
- `web` — runs `alembic upgrade head` then starts gunicorn
- `worker` — runs the ingest scheduler (pulls new crimes from Fort Worth every hour)

### Without Docker (VS Code terminal)

```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1      # you'll see (.venv) in your prompt when active

# 2. Install all dependencies
pip install -r requirements-dev.txt

# 3. Create your .env file (one-time)
cp .env.example .env
# Open .env and fill in DATABASE_URL, SODA_APP_TOKEN, SECRET_KEY

# 4. Create the database schema (one-time, or after pulling new migrations)
alembic upgrade head

# 5. Pull crime data into the database (run once to seed, then leave the scheduler running)
python -m crime_detector.ingestion.scheduler

# 6. Start the Flask dev server (in a separate terminal tab)
$env:FLASK_ENV = "development"
python app.py
# App is at http://localhost:5000
```

### Running the ingest worker standalone

```powershell
# Runs one immediate ingest then schedules hourly pulls indefinitely
python -m crime_detector.ingestion.scheduler

# Control how often it runs (default: 1 hour)
$env:INGEST_INTERVAL_HOURS = "6"
python -m crime_detector.ingestion.scheduler
```

---

## Testing

```powershell
# All tests — storage + smoke tests skip automatically without a DB / deployed URL
python -m pytest tests/ -v

# Single test file
python -m pytest tests/test_ingestion.py -v

# Single test by name
python -m pytest tests/test_api.py::TestCrimesValidation::test_missing_bbox_returns_400 -v

# Phase 2 storage tests — requires a live Postgres + PostGIS
$env:TEST_DATABASE_URL = "postgresql://user:pass@localhost/crimedetector_test"
python -m pytest tests/test_storage.py -v

# Phase 5 smoke tests — requires a deployed instance
$env:DEPLOYED_URL = "https://your-app.example.com"
python -m pytest tests/test_smoke.py -v

# Coverage report
python -m pytest tests/ --cov=crime_detector --cov-report=term-missing
```

Test files by phase:
- `tests/test_ingestion.py` — SodaClient paging and `normalize()` (no DB needed, HTTP is mocked)
- `tests/test_storage.py` — `CrimeRepository` upsert, dedup, and spatial queries (needs real Postgres)
- `tests/test_api.py` — Flask routes and GeoJSON responses (repository is mocked, no DB needed)
- `tests/test_smoke.py` — deployed health endpoint and map page load (needs `DEPLOYED_URL`)

---

## Architecture

The app has five layers that data flows through in order:

```
Fort Worth SODA API
        ↓  (hourly, background worker)
  ingestion/          — fetches + normalizes raw records
        ↓
  storage/            — upserts into Postgres + PostGIS
        ↓
  api/                — Flask routes serve GeoJSON from DB
        ↓
  frontend            — Leaflet map renders markers / clusters
```

**The browser never talks to Fort Worth's API directly.** The ingest worker is the only thing that touches the SODA endpoint.

### How each layer works

#### `crime_detector/ingestion/client.py` — SodaClient

Responsible for paging through the SODA API. Uses raw `requests` (not the `sodapy` library) so the `$limit`, `$offset`, and `$where` query parameters are fully under our control.

- `fetch_all(since=None)` — yields raw record dicts. Adds `$where=date > '{since}'` when a timestamp is provided so only new records are fetched on subsequent runs. Stops when a page returns fewer records than the page size (signals end of data).
- Page size defaults to 1000 records. The app token is sent as an `X-App-Token` header on every request.

#### `crime_detector/ingestion/normalizer.py` — normalize()

This is the **only** place SODA field names are mapped to our internal schema. If Fort Worth ever renames a field or migrates from Socrata to ArcGIS, only this file needs updating.

`normalize(raw_dict)` returns a `NormalizedRecord` dataclass or `None`. It returns `None` (skips the record) for:
- Missing or non-numeric `latitude` / `longitude`
- Coordinates outside the Fort Worth bounding box (~32.5–33.1°N, ~97.0–97.6°W)
- Unparseable `date` field

Fields intentionally **not** stored: `block_address`, `zip_code`, `city`, `state`, `council_district` — excluded to avoid pinning records to specific addresses.

#### `crime_detector/storage/repository.py` — CrimeRepository

All database interaction lives here. The session is injected at construction time so tests can pass a mock or transaction-wrapped session.

- `upsert_batch(records)` — uses `sqlalchemy.dialects.postgresql.insert` with `ON CONFLICT (raw_id) DO UPDATE`. Never uses ORM `.add()` per-row because bulk inserts of 50k+ records would be too slow.
- `query_bbox(...)` — uses GeoAlchemy2's `ST_Within(geometry, ST_MakeEnvelope(...))` for spatial filtering, plus optional `occurred_at` range and `category ILIKE` filters.
- `query_bbox_clustered(...)` — raw SQL using `ST_SnapToGrid` to snap points to a grid (grid cell = bbox_width / 20), then aggregates by grid cell. Returns cluster centroids with counts and category breakdowns. Faster than `ST_ClusterWithin` for read-heavy workloads.

#### `crime_detector/api/routes.py` — Flask API

Three endpoints:

- `GET /api/crimes?bbox=min_lon,min_lat,max_lon,max_lat&start=YYYY-MM-DD&end=YYYY-MM-DD&type=ASSAULT`
  Returns a GeoJSON `FeatureCollection`. Switches to a clustered response when:
  - bbox area > 1 degree², OR
  - raw result count > `CLUSTER_THRESHOLD` (default 500, set in config)

  Clustered features include `{cluster: true, count, categories: {...}}`.
  Non-clustered features include `{raw_id, category, offense, occurred_at, beat, division}`.
  Both responses include `meta: {count, clustered, generated_at}`.

- `GET /api/types` — returns distinct crime categories for the filter dropdown. Cached 1 hour.

- `GET /api/health` — returns DB connectivity status, last ingest timestamp, and total crime count.

All `/api/crimes` responses are cached 5 minutes per unique query string via Flask-Caching.

#### Frontend — `static/js/map.js` and `static/js/filters.js`

Plain ES5 JavaScript, no build step required.

- `map.js` — initializes a Leaflet map centered on Fort Worth `[32.7555, -97.3308]`, attaches a debounced `moveend` handler that calls `loadCrimes()` whenever the user pans or zooms, renders either raw markers into a `MarkerClusterGroup` or server-side cluster circles, and manages the optional heatmap layer.
- `filters.js` — populates the crime-type `<select>` from `/api/types`, binds change events on the date inputs and type dropdown to trigger `loadCrimes()`, and sets sensible defaults (last 90 days).

Category colors in `map.js` are hardcoded by keyword: assaults → red, theft/burglary → orange, drugs → purple, vandalism → green, everything else → blue.

### Config and environment variables

`config.py` defines three configs selected by `FLASK_ENV`:

| Variable | What it does |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SODA_APP_TOKEN` | Socrata app token (avoids rate limiting) |
| `SODA_ENDPOINT` | SODA API URL — override this if Fort Worth migrates to ArcGIS |
| `SECRET_KEY` | Flask session signing key |
| `FLASK_ENV` | `development` / `testing` / `production` |
| `POSTGRES_PASSWORD` | Used by docker-compose for the `db` container |
| `INGEST_INTERVAL_HOURS` | How often the worker polls (default: `1`) |
| `CLUSTER_THRESHOLD` | Row count above which server clustering activates (default: `500`) |

`TestingConfig` forces `CACHE_TYPE = "NullCache"` so cached responses don't bleed between tests.

### Database schema

Single table `crimes`. Key columns:

| Column | Type | Notes |
|---|---|---|
| `raw_id` | TEXT UNIQUE | SODA `:id` field — dedup key for upserts |
| `category` | TEXT | High-level type e.g. `ASSAULT` |
| `offense` | TEXT | Specific description |
| `occurred_at` | TIMESTAMPTZ | Normalized from SODA `date` field |
| `geometry` | GEOMETRY(Point, 4326) | WGS-84 lon/lat point |
| `beat` | TEXT | Police patrol beat |
| `division` | TEXT | Mapped from SODA `sector` field |

Indexes: unique on `raw_id`, GIST spatial index on `geometry`, B-tree on `occurred_at`, composite on `(category, occurred_at)`.

Migrations are managed by Alembic. `alembic upgrade head` applies all pending migrations. The initial migration (`migrations/versions/001_initial_schema.py`) also runs `CREATE EXTENSION IF NOT EXISTS postgis`.

### docker-compose services

| Service | Image / Build | Role |
|---|---|---|
| `db` | `postgis/postgis:16-3.4` | Postgres + PostGIS; data persists in `pgdata` volume |
| `web` | local build | Runs `alembic upgrade head` then `gunicorn` on port 8000 |
| `worker` | local build | Runs `scheduler.py` — hourly incremental ingest from SODA |

`web` and `worker` both wait for `db`'s healthcheck (`pg_isready`) before starting.

---

## Adding a new API filter

1. Parse the query param in `api/routes.py::get_crimes()` (follow the pattern of `start`/`end`/`type`)
2. Pass it to both `CrimeRepository.query_bbox()` and `query_bbox_clustered()` in `storage/repository.py`
3. Add a `WHERE` clause in both methods
4. Add a test in `tests/test_api.py` asserting the param is forwarded to the repo (see `test_type_filter_forwarded_to_repo` for the pattern)
