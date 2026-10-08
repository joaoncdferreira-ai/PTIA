(function () {
  "use strict";

  if (navigator.doNotTrack === "1" || window.doNotTrack === "1") return;

  var endpoint =
    "https://europe-west1-ptia-content-engine-prod.cloudfunctions.net/analytics_event";
  var params = new URLSearchParams(window.location.search);
  var path = window.location.pathname || "/";
  if (/@|%40/i.test(path) || path.length > 256) path = "/other";
  var referrerOrigin = "";
  try {
    var referrerUrl = new URL(document.referrer);
    if (referrerUrl.protocol === "https:" || referrerUrl.protocol === "http:") {
      referrerOrigin = referrerUrl.origin;
    }
  } catch (_) {}
  function campaignValue(key) {
    var value = params.get(key) || "";
    return /^[a-z0-9][a-z0-9_-]{0,63}$/i.test(value) ? value : "";
  }
  var payload = JSON.stringify({
    path: path,
    referrer: referrerOrigin,
    utm_source: campaignValue("utm_source"),
    utm_medium: campaignValue("utm_medium"),
    utm_campaign: campaignValue("utm_campaign"),
    utm_content: campaignValue("utm_content"),
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
