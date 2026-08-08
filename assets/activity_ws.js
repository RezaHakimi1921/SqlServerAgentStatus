/**
 * Activity Monitor — Socket.IO client.
 * Joins the "activity" room and bumps store-ws-activity-tick so Dash refreshes live.
 */
(function () {
  var socket = null;
  var joined = false;

  function setTick(t) {
    try {
      if (window.dash_clientside && typeof dash_clientside.set_props === "function") {
        dash_clientside.set_props("store-ws-activity-tick", { data: t || Date.now() / 1000 });
      }
    } catch (e) {
      /* Dash not ready yet */
    }
  }

  function isActivityVisible() {
    var panel = document.getElementById("module-activity");
    if (!panel) return false;
    return panel.classList.contains("active");
  }

  function syncRoom() {
    if (!socket || !socket.connected) return;
    if (isActivityVisible()) {
      if (!joined) {
        socket.emit("join_activity");
        joined = true;
      }
    } else if (joined) {
      socket.emit("leave_activity");
      joined = false;
    }
  }

  function connect() {
    if (typeof io === "undefined") {
      console.warn("[activity_ws] socket.io client missing");
      return;
    }
    if (socket) return;
    socket = io({
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionDelay: 800,
      reconnectionDelayMax: 5000,
    });
    socket.on("connect", function () {
      joined = false;
      syncRoom();
    });
    socket.on("activity_tick", function (payload) {
      if (!isActivityVisible()) return;
      var pausedBtn = document.getElementById("btn-pause");
      // Pause button label/state is driven by Dash; store-paused checked server-side too
      setTick((payload && payload.t) || Date.now() / 1000);
    });
    socket.on("disconnect", function () {
      joined = false;
    });

    // Watch Activity panel class changes
    var panel = document.getElementById("module-activity");
    if (panel && window.MutationObserver) {
      new MutationObserver(syncRoom).observe(panel, {
        attributes: true,
        attributeFilter: ["class"],
      });
    }
    setInterval(syncRoom, 2000);
  }

  if (document.readyState === "complete") {
    setTimeout(connect, 200);
  } else {
    window.addEventListener("load", function () {
      setTimeout(connect, 200);
    });
  }
})();
