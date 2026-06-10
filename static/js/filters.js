var selectedDays = 0;

function initScrollWheel() {
  var wheel = document.getElementById("date-scroll");
  if (!wheel) return;

  var items = Array.prototype.slice.call(wheel.querySelectorAll(".scroll-item"));
  var itemHeight = 30;

  // Scroll to top (Today selected) on init
  wheel.scrollTop = 0;
  _highlightSelected(items, 0);

  wheel.addEventListener("scroll", debounce(function () {
    var idx = Math.round(wheel.scrollTop / itemHeight);
    idx = Math.max(0, Math.min(idx, items.length - 1));
    var days = parseInt(items[idx].dataset.days, 10);
    if (days !== selectedDays) {
      selectedDays = days;
      _highlightSelected(items, idx);
      _updateDateDisplay(items[idx].textContent);
      loadCrimes(getFilterParams());
    }
  }, 150));
}

function _highlightSelected(items, idx) {
  items.forEach(function (el, i) {
    el.classList.toggle("selected", i === idx);
  });
}

function _updateDateDisplay(label) {
  var el = document.getElementById("date-display");
  if (el) el.textContent = label;
}

function getFilterParams() {
  var today = new Date();
  var start = new Date(today);
  start.setDate(start.getDate() - selectedDays);
  return {
    start: _toDateString(start),
    end: _toDateString(today),
  };
}

function _toDateString(d) {
  return d.toISOString().slice(0, 10);
}
