/* global L, getFilterParams */

var map;
var crimeLayer;

var FORT_WORTH_CENTER = [32.7555, -97.3308];
var FW_BOUNDS = [[32.4, -97.8], [33.2, -96.8]];

function initMap() {
  map = L.map("map", {
    minZoom: 10,
    maxBounds: FW_BOUNDS,
    maxBoundsViscosity: 1.0,
  }).setView(FORT_WORTH_CENTER, 12);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ' +
      '&copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);

  crimeLayer = L.layerGroup().addTo(map);

  map.on("moveend", debounce(function () {
    loadCrimes(getFilterParams());
  }, 400));

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
  url += "&end=" + encodeURIComponent(params.end);

  fetch(url)
    .then(function (r) {
      if (!r.ok) throw new Error("API error " + r.status);
      return r.json();
    })
    .then(function (fc) {
      var countEl = document.getElementById("crime-count");
      var n = (fc.meta && fc.meta.count) || 0;
      if (countEl) countEl.textContent = n.toLocaleString() + " incidents";

      crimeLayer.clearLayers();
      renderPoints(fc.features || []);
    })
    .catch(function (err) {
      console.error("Failed to load crimes:", err);
    });
}

function renderPoints(features) {
  features.forEach(function (feat) {
    if (!feat.geometry || feat.geometry.type !== "Point") return;
    var coords = feat.geometry.coordinates;
    var p = feat.properties;

    var marker = L.circleMarker([coords[1], coords[0]], {
      radius: 5,
      color: "#e94560",
      fillColor: "#e94560",
      fillOpacity: 0.85,
      weight: 1,
    });

    marker.bindPopup(_buildPopup(p), { maxWidth: 260 });
    crimeLayer.addLayer(marker);
  });
}

function _buildPopup(p) {
  var time = "Unknown time";
  if (p.occurred_at) {
    var d = new Date(p.occurred_at);
    time = d.toLocaleDateString("en-US", { weekday: "short", year: "numeric", month: "short", day: "numeric" }) +
           "<br>" +
           d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
  }

  var location = [];
  if (p.beat)     location.push("Beat " + p.beat);
  if (p.division) location.push(p.division);
  var locationStr = location.length ? location.join(" &middot; ") : "Location unavailable";

  return (
    '<div class="popup">' +
      '<div class="popup-category">' + (p.category || "Unknown") + "</div>" +
      '<div class="popup-offense">' + (p.offense || "") + "</div>" +
      '<div class="popup-meta">' +
        '<span class="popup-icon">&#128337;</span> ' + time +
      "</div>" +
      '<div class="popup-meta">' +
        '<span class="popup-icon">&#128205;</span> ' + locationStr +
      "</div>" +
    "</div>"
  );
}

function debounce(fn, ms) {
  var timer;
  return function () {
    clearTimeout(timer);
    timer = setTimeout(fn, ms);
  };
}

function _toDateString(d) {
  return d.toISOString().slice(0, 10);
}
