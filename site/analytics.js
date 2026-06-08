(function () {
  "use strict";

  if (navigator.doNotTrack === "1") return;

  var endpoint =
    "https://europe-west1-ptia-content-engine-prod.cloudfunctions.net/analytics_event";
  var params = new URLSearchParams(window.location.search);
  var payload = JSON.stringify({
    path: window.location.pathname,
    referrer: document.referrer || "",
    utm_source: params.get("utm_source") || "",
    utm_medium: params.get("utm_medium") || "",
    utm_campaign: params.get("utm_campaign") || "",
    utm_content: params.get("utm_content") || "",
  });

  if (navigator.sendBeacon) {
    navigator.sendBeacon(endpoint, new Blob([payload], { type: "text/plain" }));
    return;
  }
  fetch(endpoint, {
    method: "POST",
    body: payload,
    headers: { "Content-Type": "text/plain" },
    keepalive: true,
  }).catch(function () {});
})();
