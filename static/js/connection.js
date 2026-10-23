// Keeps the room's live connection healthy.
//
// 1. Shows the "Reconnecting…" banner while the connection is down.
//    The htmx ws extension reconnects by itself, but only after unexpected
//    drops: 1006 (network lost), 1012 (server restarting), 1013 (try later).
//    Other closes are deliberate, e.g. the server saying the room expired,
//    and come with their own notice, so the banner stays hidden for those.
//
// 2. Sends a small "ping" every few minutes while the room is open. Render's
//    free plan puts the server to sleep after 15 minutes without traffic, and
//    an open but quiet connection doesn't count, so a long discussion without
//    clicks would otherwise end the session. The server ignores pings.
(function () {
  var RETRIED = [1006, 1012, 1013];
  var PING_EVERY_MS = 4 * 60 * 1000;
  var socket = null;

  document.addEventListener("htmx:wsOpen", function (evt) {
    socket = evt.detail.socketWrapper;
    // Once reconnected, the server pushes the whole room, so nothing is missed.
    document.body.classList.remove("reconnecting");
  });

  document.addEventListener("htmx:wsClose", function (evt) {
    socket = null;
    var retrying = RETRIED.indexOf(evt.detail.event.code) !== -1;
    document.body.classList.toggle("reconnecting", retrying);
  });

  setInterval(function () {
    if (socket) {
      socket.send(JSON.stringify({ action: "ping" }));
    }
  }, PING_EVERY_MS);
})();
