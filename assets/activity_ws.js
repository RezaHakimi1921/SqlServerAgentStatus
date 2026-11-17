/**
 * Activity Monitor — Socket.IO client (lazy, fail-soft).
 * Connects only while Activity tab is visible; stops retry spam on failure.
 */
(function () {
  var socket = null;
  var joined = false;
  var disabled = false;
  var failCount = 0;
  var MAX_FAIL = 2;

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

  function teardown() {
    if (socket) {
      try {
        socket.removeAllListeners();
        socket.close();
      } catch (e) {
        /* ignore */
      }
    }
    socket = null;
    joined = false;
  }

  function disableWs(reason) {
    if (disabled) return;
    disabled = true;
    teardown();
    if (failCount >= MAX_FAIL) {
      console.info("[activity_ws] realtime disabled:", reason || "server unavailable");
    }
  }

  function connect() {
    if (disabled || window.__SM_REALTIME_WS__ === false) return;
    if (!isActivityVisible()) return;
    if (typeof io === "undefined") return;
    if (socket) return;

    socket = io({
      transports: ["polling", "websocket"],
      reconnection: true,
      reconnectionAttempts: MAX_FAIL,
      reconnectionDelay: 1200,
      reconnectionDelayMax: 4000,
      timeout: 8000,
    });

    socket.on("connect", function () {
      failCount = 0;
      joined = false;
      syncRoom();
    });

    socket.on("connect_error", function () {
      failCount += 1;
      if (failCount >= MAX_FAIL) {
        disableWs("connect_error");
      }
    });

    socket.on("activity_tick", function (payload) {
      if (!isActivityVisible()) return;
      setTick((payload && payload.t) || Date.now() / 1000);
    });

    socket.on("disconnect", function () {
      joined = false;
    });
  }

  function watchActivityPanel() {
    var panel = document.getElementById("module-activity");
    if (panel && window.MutationObserver) {
      new MutationObserver(function () {
        if (isActivityVisible()) connect();
        else {
          syncRoom();
          if (socket && !socket.connected) teardown();
        }
      }).observe(panel, { attributes: true, attributeFilter: ["class"] });
    }
    setInterval(function () {
      if (disabled) return;
      if (isActivityVisible()) connect();
      else syncRoom();
    }, 2500);
  }

  if (document.readyState === "complete") {
    setTimeout(watchActivityPanel, 300);
  } else {
    window.addEventListener("load", function () {
      setTimeout(watchActivityPanel, 300);
    });
  }
})();
