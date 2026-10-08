(function () {
  "use strict";

  function setupShare(root) {
    if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") return;
    const scope = root || document;
    scope.querySelectorAll("[data-copy-article-link]").forEach((button) => {
      if (button.dataset.ready === "true") return;
      button.hidden = false;
      button.dataset.ready = "true";
      button.addEventListener("click", async () => {
        const status = button.parentElement.querySelector("[data-copy-status]");
        const canonical = document.querySelector('link[rel="canonical"]');
        const url = canonical?.href || window.location.origin + window.location.pathname;
        try {
          await navigator.clipboard.writeText(url);
          if (status) status.textContent = "Ligação copiada.";
        } catch (_) {
          if (status) status.textContent = "Não foi possível copiar. Usa a ligação na barra de endereço.";
        }
      });
    });
  }

  window.PTIAEngagement = { setupShare };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setupShare(document));
  } else {
    setupShare(document);
  }
})();
