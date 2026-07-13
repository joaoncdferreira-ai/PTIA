(function () {
  "use strict";

  if (navigator.doNotTrack === "1") return;

  var endpoint =
    "https://europe-west1-ptia-content-engine-prod.cloudfunctions.net/analytics_event";
  var params = new URLSearchParams(window.location.search);

  function safeProperties(properties) {
    var clean = {};
    Object.keys(properties || {}).slice(0, 12).forEach(function (key) {
      var value = properties[key];
      if (typeof value === "number" || typeof value === "boolean") {
        clean[String(key).slice(0, 48)] = value;
      } else {
        clean[String(key).slice(0, 48)] = String(value || "").slice(0, 180);
      }
    });
    return clean;
  }

  function send(eventName, properties) {
    var payload = JSON.stringify({
      event_name: String(eventName || "page_view").slice(0, 64),
      event_properties: safeProperties(properties),
      path: window.location.pathname,
      referrer: document.referrer || "",
      utm_source: params.get("utm_source") || "",
      utm_medium: params.get("utm_medium") || "",
      utm_campaign: params.get("utm_campaign") || "",
      utm_content: params.get("utm_content") || "",
    });

    if (navigator.sendBeacon) {
      navigator.sendBeacon(
        endpoint,
        new Blob([payload], { type: "text/plain" })
      );
      return;
    }
    fetch(endpoint, {
      method: "POST",
      body: payload,
      headers: { "Content-Type": "text/plain" },
      keepalive: true,
    }).catch(function () {});
  }

  window.ptiaTrack = function (eventName, properties) {
    send(eventName, properties);
  };

  send("page_view", {});
})();
