/* global L */

var map;
var clusterGroup;
var heatLayer;
var heatmapEnabled = false;

var FORT_WORTH_CENTER = [32.7555, -97.3308];
var DEFAULT_ZOOM = 11;

function initMap() {
  map = L.map("map").setView(FORT_WORTH_CENTER, DEFAULT_ZOOM);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  }).addTo(map);

  clusterGroup = L.markerClusterGroup({ chunkedLoading: true });
  map.addLayer(clusterGroup);

  map.on("moveend", debounce(onMapMoveEnd, 400));

  loadCrimes(getFilterParams());
}

function onMapMoveEnd() {
  loadCrimes(getFilterParams());
}

function loadCrimes(params) {
  var bounds = map.getBounds();
  var bbox = [
    bounds.getWest(),
    bounds.getSouth(),
    bounds.getEast(),
    bounds.getNorth(),
  ].join(",");

  var url = "/api/crimes?bbox=" + encodeURIComponent(bbox);
  if (params.start) url += "&start=" + encodeURIComponent(params.start);
  if (params.end) url += "&end=" + encodeURIComponent(params.end);
  if (params.type) url += "&type=" + encodeURIComponent(params.type);

  fetch(url)
    .then(function (r) {
      if (!r.ok) throw new Error("API error " + r.status);
      return r.json();
    })
    .then(function (fc) {
      var countEl = document.getElementById("crime-count");
      var n = (fc.meta && fc.meta.count) || 0;
      if (countEl) countEl.textContent = n.toLocaleString() + " incidents";

      clearLayers();

      if (fc.meta && fc.meta.clustered) {
        renderServerClusters(fc.features);
      } else {
        renderPoints(fc.features);
        if (heatmapEnabled) renderHeatmap(fc.features);
      }
    })
    .catch(function (err) {
      console.error("Failed to load crimes:", err);
    });
}

function clearLayers() {
  clusterGroup.clearLayers();
  if (heatLayer) {
    map.removeLayer(heatLayer);
    heatLayer = null;
  }
}

function renderPoints(features) {
  features.forEach(function (feat) {
    if (!feat.geometry || feat.geometry.type !== "Point") return;
    var coords = feat.geometry.coordinates;
    var p = feat.properties;
    var marker = L.circleMarker([coords[1], coords[0]], {
      radius: 6,
      color: _categoryColor(p.category),
      fillColor: _categoryColor(p.category),
      fillOpacity: 0.7,
      weight: 1,
    });
    marker.bindPopup(
      "<strong>" + (p.category || "") + "</strong><br>" +
      (p.offense || "") + "<br>" +
      (p.occurred_at ? new Date(p.occurred_at).toLocaleDateString() : "") +
      (p.beat ? "<br>Beat: " + p.beat : "")
    );
    clusterGroup.addLayer(marker);
  });
}

function renderServerClusters(features) {
  features.forEach(function (feat) {
    if (!feat.geometry) return;
    var p = feat.properties;
    var coords = feat.geometry.coordinates || feat.geometry;
    var latlng;
    if (Array.isArray(coords)) {
      latlng = [coords[1], coords[0]];
    } else {
      return;
    }
    var count = p.count || 0;
    var radius = Math.min(6 + Math.sqrt(count) * 1.5, 40);
    var marker = L.circleMarker(latlng, {
      radius: radius,
      color: "#e94560",
      fillColor: "#e94560",
      fillOpacity: 0.5,
      weight: 1,
    });
    marker.bindPopup("<strong>" + count.toLocaleString() + " incidents</strong>");
    map.addLayer(marker);
  });
}

function renderHeatmap(features) {
  var points = features
    .filter(function (f) { return f.geometry && f.geometry.type === "Point"; })
    .map(function (f) {
      var c = f.geometry.coordinates;
      return [c[1], c[0], 1];
    });
  if (!points.length) return;
  heatLayer = L.heatLayer(points, { radius: 20, blur: 15, maxZoom: 17 });
  map.addLayer(heatLayer);
}

function toggleHeatmap(enabled) {
  heatmapEnabled = enabled;
  loadCrimes(getFilterParams());
}

function _categoryColor(category) {
  var c = (category || "").toUpperCase();
  if (c.includes("ASSAULT")) return "#e94560";
  if (c.includes("THEFT") || c.includes("BURGLARY") || c.includes("ROBBERY")) return "#f5a623";
  if (c.includes("DRUG")) return "#7b68ee";
  if (c.includes("VANDAL")) return "#50c878";
  return "#4a9eff";
}

function debounce(fn, ms) {
  var timer;
  return function () {
    clearTimeout(timer);
    timer = setTimeout(fn, ms);
  };
}
