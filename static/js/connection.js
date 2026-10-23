// Shows the "Reconnecting…" banner while the live connection is down.
//
// The htmx ws extension reconnects by itself, but only after unexpected
// drops: 1006 (network lost), 1012 (server restarting), 1013 (try later).
// Other closes are deliberate, e.g. the server saying the room expired,
// and come with their own notice, so the banner stays hidden for those.
(function () {
  var RETRIED = [1006, 1012, 1013];

  document.addEventListener("htmx:wsClose", function (evt) {
    var retrying = RETRIED.indexOf(evt.detail.event.code) !== -1;
    document.body.classList.toggle("reconnecting", retrying);
  });

  // Once reconnected, the server pushes the whole room, so nothing is missed.
  document.addEventListener("htmx:wsOpen", function () {
    document.body.classList.remove("reconnecting");
  });
})();
