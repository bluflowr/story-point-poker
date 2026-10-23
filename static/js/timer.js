// Counts the round timer down in the browser.
//
// The server only stores when the timer ends. Every update it pushes says how
// many seconds are left (data-seconds-left), and this script ticks that down
// locally, so the server doesn't have to send something every second. Counting
// from "seconds left" rather than the end time means a wrong computer clock
// doesn't matter.
(function () {
  var endsAt = null; // this browser's clock time when the timer runs out

  function timerElement() {
    return document.querySelector(".timer[data-seconds-left]");
  }

  function format(seconds) {
    var rest = seconds % 60;
    return Math.floor(seconds / 60) + ":" + (rest < 10 ? "0" : "") + rest;
  }

  // Called whenever the server sends fresh HTML.
  function sync() {
    var el = timerElement();
    endsAt = el ? Date.now() + Number(el.dataset.secondsLeft) * 1000 : null;
    tick();
  }

  function tick() {
    var el = timerElement();
    if (!el || endsAt === null) {
      return;
    }
    var left = Math.max(0, Math.ceil((endsAt - Date.now()) / 1000));
    el.textContent = left > 0 ? format(left) : "Time's up";
    el.classList.toggle("times-up", left === 0);
  }

  document.addEventListener("DOMContentLoaded", sync);
  document.addEventListener("htmx:wsAfterMessage", sync);
  setInterval(tick, 250);
})();
