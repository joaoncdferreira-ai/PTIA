(function () {
  "use strict";

  var root = document.querySelector(".resources-v2");
  if (!root) return;

  function track(eventName, properties) {
    if (typeof window.ptiaTrack === "function") {
      window.ptiaTrack(eventName, properties || {});
    }
  }

  var categoryButtons = Array.from(
    root.querySelectorAll("[data-resource-category]")
  );
  var categoryPanels = Array.from(
    root.querySelectorAll("[data-resource-category-panel]")
  );

  function activateCategory(category, options) {
    var activeButton = null;
    categoryButtons.forEach(function (button) {
      var active = button.getAttribute("data-resource-category") === category;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
      if (active) activeButton = button;
    });
    categoryPanels.forEach(function (panel) {
      panel.hidden =
        panel.getAttribute("data-resource-category-panel") !== category;
    });
    if (options && options.focus && activeButton) activeButton.focus();
    if (!options || options.track !== false) {
      track("resource_category_selected", { category: category });
    }
  }

  categoryButtons.forEach(function (button, index) {
    button.addEventListener("click", function () {
      activateCategory(button.getAttribute("data-resource-category") || "");
    });
    button.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
      event.preventDefault();
      var direction = event.key === "ArrowRight" ? 1 : -1;
      var next = (index + direction + categoryButtons.length) % categoryButtons.length;
      activateCategory(
        categoryButtons[next].getAttribute("data-resource-category") || "",
        { focus: true }
      );
    });
  });

  var requestedCategory = window.location.hash.replace("#top-", "");
  if (
    requestedCategory &&
    categoryButtons.some(function (button) {
      return button.getAttribute("data-resource-category") === requestedCategory;
    })
  ) {
    activateCategory(requestedCategory, { track: false });
  } else if (categoryButtons.length) {
    activateCategory(
      categoryButtons[0].getAttribute("data-resource-category") || "",
      { track: false }
    );
  }

  root.querySelectorAll("[data-resource-explanation]").forEach(function (details) {
    details.addEventListener("toggle", function () {
      if (!details.open) return;
      track("resource_evidence_opened", {
        item: details.getAttribute("data-resource-label") || "",
        category:
          details.closest("[data-resource-category-panel]")
            ?.getAttribute("data-resource-category-panel") || "",
      });
    });
  });

  function shareUrl(content) {
    var url = new URL(window.location.origin + window.location.pathname);
    url.searchParams.set("utm_source", "share");
    url.searchParams.set("utm_medium", "organic");
    url.searchParams.set("utm_campaign", "resources-weekly");
    url.searchParams.set("utm_content", content || "weekly-edition");
    if (String(content || "").indexOf("tools-") === 0) {
      url.hash = "top-" + String(content).replace("tools-", "");
    }
    return url.toString();
  }

  async function copyShareLink(value) {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      return;
    }
    var input = document.createElement("textarea");
    input.value = value;
    input.setAttribute("readonly", "");
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.appendChild(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  root.querySelectorAll("[data-resource-share]").forEach(function (button) {
    var original = button.textContent;
    button.addEventListener("click", async function () {
      var content = button.getAttribute("data-share-content") || "weekly-edition";
      var title = button.getAttribute("data-share-title") || "Radar PTIA";
      var url = shareUrl(content);
      track("resource_share_started", { content: content });
      try {
        if (navigator.share) {
          await navigator.share({
            title: title,
            text: "Rankings com critérios e fontes visíveis.",
            url: url,
          });
          button.textContent = "Partilhado";
          track("resource_share_completed", {
            content: content,
            method: "native",
          });
        } else {
          await copyShareLink(url);
          button.textContent = "Link copiado";
          track("resource_share_completed", {
            content: content,
            method: "clipboard",
          });
        }
        window.setTimeout(function () {
          button.textContent = original;
        }, 1800);
      } catch (error) {
        if (!error || error.name !== "AbortError") {
          button.textContent = "Não foi possível";
          window.setTimeout(function () {
            button.textContent = original;
          }, 1800);
        }
      }
    });
  });

  root.querySelectorAll("[data-resource-action]").forEach(function (link) {
    link.addEventListener("click", function () {
      track("resource_action_clicked", {
        action: link.getAttribute("data-resource-action") || "unknown",
        destination: link.getAttribute("href") || "",
      });
    });
  });
})();
