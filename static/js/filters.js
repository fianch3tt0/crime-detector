function bindFilterControls() {
  var startEl = document.getElementById("start-date");
  var endEl = document.getElementById("end-date");
  var typeEl = document.getElementById("crime-type");
  var heatEl = document.getElementById("heatmap-toggle");

  // Set sensible defaults: last 90 days
  var now = new Date();
  var past = new Date(now);
  past.setDate(past.getDate() - 90);
  if (endEl) endEl.value = _toDateString(now);
  if (startEl) startEl.value = _toDateString(past);

  function onChange() {
    loadCrimes(getFilterParams());
  }

  if (startEl) startEl.addEventListener("change", onChange);
  if (endEl) endEl.addEventListener("change", onChange);
  if (typeEl) typeEl.addEventListener("change", onChange);
  if (heatEl) {
    heatEl.addEventListener("change", function () {
      toggleHeatmap(heatEl.checked);
    });
  }
}

function getFilterParams() {
  var startEl = document.getElementById("start-date");
  var endEl = document.getElementById("end-date");
  var typeEl = document.getElementById("crime-type");

  return {
    start: startEl ? startEl.value : "",
    end: endEl ? endEl.value : "",
    type: typeEl ? typeEl.value : "",
  };
}

function populateTypeDropdown() {
  fetch("/api/types")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var sel = document.getElementById("crime-type");
      if (!sel || !data.types) return;
      data.types.forEach(function (t) {
        var opt = document.createElement("option");
        opt.value = t;
        opt.textContent = _titleCase(t);
        sel.appendChild(opt);
      });
    })
    .catch(function (err) {
      console.warn("Could not load crime types:", err);
    });
}

function _toDateString(d) {
  return d.toISOString().slice(0, 10);
}

function _titleCase(s) {
  return s.toLowerCase().replace(/\b\w/g, function (c) { return c.toUpperCase(); });
}
