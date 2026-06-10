# build log
  
  
Build "Crime Detector": a public web app that maps reported crime in Fort Worth, TX
by pulling from the city's open-data API, storing it, and rendering it on an
interactive filterable map.

Constraints:
- Use the official Fort Worth Socrata/SODA API (dataset k6ic-7kp7) as the primary
  data source; only fall back to HTML scraping for fields the API does not expose
- Do not de-anonymize or pin records to exact residences; display at the location
  granularity the source returns
- Stack: Flask backend, Postgres + PostGIS storage, Leaflet + OpenStreetMap frontend
- Never call the live SODA API on a page request; serve all map data from our own DB
- Display a data-source attribution and an accuracy/"as-reported" disclaimer on the site
- Build in phases; do not start a phase until the previous phase's tests pass

Detailed Description:
- Phase 1 — Ingestion: a SODA client that pages through k6ic-7kp7 with $limit/$offset,
  supports incremental pulls by date, and uses a Socrata app token. Normalize each
  record into {category, offense, timestamp, lat, lon, beat, division, raw_id}.
- Phase 2 — Storage: Postgres schema with a PostGIS geometry column; upsert on raw_id
  to dedupe; index on (timestamp) and a spatial index on geometry.
- Phase 3 — API: Flask route /api/crimes accepting bbox, start, end, and type params,
  returning GeoJSON; server-side clustering for dense bounding boxes; short-TTL cache.
- Phase 4 — Frontend: Leaflet map centered on Fort Worth with OSM tiles, marker
  clustering, optional heatmap toggle, and date-range + crime-type filter controls
  that call /api/crimes and re-render.
- Phase 5 — Deploy: Dockerize, deploy to a host with managed Postgres, run ingestion
  as a scheduled worker, add attribution + disclaimer to the page footer.

Tests:
- After EVERY phase, write and run tests before moving on; use pytest to verify
- Phase 1: mock SODA responses; assert paging, incremental date filtering, and
  normalization output shape; assert malformed/missing-coordinate records are skipped
- Phase 2: assert insert, upsert-dedupe on raw_id, and a PostGIS bbox query return
  the expected rows against a test DB
- Phase 3: spin up the Flask test client; assert /api/crimes returns valid GeoJSON,
  that bbox/date/type filters actually filter, and that an empty result is well-formed
- Phase 5: a smoke test that the deployed health endpoint responds and the map page
  loads; manually verify markers render and filters update the map
- Create the plan first and then put it into action. I am using plan mode so make
  sure you create the plan first.


  
  
  
  Things that need fixing:


  The map system that you are using is incredibly annoying and dated we need to look at taking another map
  The map zooms out ot all of america but we only want it to zoom out of fort worth
  The crime is working because when you run the api health it shows a good status with 300,000 crimes but nothing is showing up on the map
  We need to make the selection for the type of crime just always default to all (dont even include the section system)
  When the crime shows up on the map it should show up as a red dot that covers and area of 0.5 miles in all directions and when you click in the red dot it shows what the crime is and what area its in
  The date adjusting system is horrible and should instead be a scroll wheel. The end date should always default to today.
  When you first log into the site it should only be today's crime and it only shows more crime over larger dates when prompted.
  The heatmap doesnt even work but that doesnt matter because its bad


Here's the full plan for all 8 issues:

---
What's being fixed and how

1. Map tiles (dated look)
Replace OpenStreetMap tiles with CartoDB Dark Matter — free, no API key, very modern dark aesthetic that fits the existing dark color scheme. Leaflet itself stays (it's solid, the tiles were the problem).

2. Map bounds (zooms out to America)
Set minZoom: 10 and maxBounds locked to the Fort Worth metro area — the map physically cannot scroll or zoom outside the region.

3. Crimes not showing (confirmed bug)
renderServerClusters() adds markers with map.addLayer() but clearLayers() only clears the clusterGroup — so every reload stacks new circles on top of old ones but never removes them. Fix: replace L.markerClusterGroup with two plain L.layerGroup() instances (crimeLayer + clusterLayer), both properly cleared on each load.

4. Crime type filter → removed
The #crime-type dropdown and all related JS (populateTypeDropdown, the type URL param) are removed entirely. Backend already returns all crimes when the param is absent — no backend change needed.

5. Crime display → red circles
Each crime renders as L.circle with 804m radius (≈ 0.5 miles), red fill, semi-transparent. Click opens a popup showing category, offense, and beat.

6. Date scroll wheel
Replace the two <ina CSS scroll-snapwheel with 7 option week / Past 2 weeks/ Past month / Pastlected item ishighlighted red. Encoded in
loadCrimes().

7. Default to today
Scroll wheel defaul = today, end =
today. Only shows m

8. Heatmap → remove
Toggle, layer, and et Heat CDN script
removed from HTML.

---
Files changing: temmap.js,
static/js/filters.j
Files not changing:er config

