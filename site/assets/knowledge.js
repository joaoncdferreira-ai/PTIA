(function () {
  "use strict";

  var toolButtons = document.querySelectorAll("[data-tool-category]");
  var toolPanels = document.querySelectorAll("[data-tool-panel]");
  toolButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var selected = button.getAttribute("data-tool-category");
      toolButtons.forEach(function (item) {
        item.classList.toggle("active", item === button);
        item.setAttribute("aria-selected", item === button ? "true" : "false");
      });
      toolPanels.forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-tool-panel") !== selected;
      });
    });
  });

  var indexButtons = document.querySelectorAll("[data-index-tab]");
  var indexPanels = document.querySelectorAll("[data-index-panel]");
  indexButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var selected = button.getAttribute("data-index-tab");
      indexButtons.forEach(function (item) {
        var active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", active ? "true" : "false");
      });
      indexPanels.forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-index-panel") !== selected;
      });
    });
  });

  var search = document.querySelector("[data-knowledge-search]");
  var searchItems = document.querySelectorAll("[data-search]");
  var searchSummary = document.querySelector("[data-search-summary]");
  if (search) {
    search.addEventListener("input", function () {
      var query = search.value.trim().toLocaleLowerCase("pt-PT");
      var visible = 0;
      searchItems.forEach(function (item) {
        var text = (item.getAttribute("data-search") || "").toLocaleLowerCase("pt-PT");
        var show = !query || text.indexOf(query) !== -1;
        item.hidden = !show;
        if (show) visible += 1;
      });
      if (searchSummary) {
        searchSummary.textContent = visible + (visible === 1 ? " termo" : " termos");
      }
    });
  }

  var promptInput = document.querySelector("[data-prompt-search-input]");
  var promptButtons = document.querySelectorAll("[data-prompt-category]");
  var promptItems = document.querySelectorAll("[data-prompt-item]");
  var promptSummary = document.querySelector("[data-prompt-summary]");
  var promptCategory = "all";

  function filterPrompts() {
    var query = promptInput ? promptInput.value.trim().toLocaleLowerCase("pt-PT") : "";
    var visible = 0;
    promptItems.forEach(function (item) {
      var category = item.getAttribute("data-prompt-category-value");
      var text = (item.getAttribute("data-prompt-search") || "").toLocaleLowerCase("pt-PT");
      var show = (promptCategory === "all" || category === promptCategory) &&
        (!query || text.indexOf(query) !== -1);
      item.hidden = !show;
      if (show) visible += 1;
    });
    if (promptSummary) {
      promptSummary.textContent = visible + (visible === 1 ? " prompt" : " prompts");
    }
  }

  promptButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      promptCategory = button.getAttribute("data-prompt-category") || "all";
      promptButtons.forEach(function (item) {
        item.classList.toggle("active", item === button);
      });
      filterPrompts();
    });
  });
  if (promptInput) promptInput.addEventListener("input", filterPrompts);

  function foldText(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("pt-PT");
  }

  async function copyText(value, button) {
    try {
      await navigator.clipboard.writeText(value);
      button.textContent = "Copiado";
      window.setTimeout(function () { button.textContent = "Copiar prompt"; }, 1600);
    } catch (_) {
      button.textContent = "Seleciona o texto";
    }
  }

  var suggestionForm = document.querySelector("[data-prompt-suggestion-form]");
  var useCaseInput = document.querySelector("[data-prompt-use-case]");
  var suggestionResult = document.querySelector("[data-prompt-suggestion-result]");
  var suggestionStatus = document.querySelector("[data-prompt-suggestion-status]");
  var suggestionTitle = document.querySelector("[data-prompt-suggestion-title]");
  var suggestionCode = document.querySelector("[data-prompt-suggestion-code]");
  var suggestionCopy = document.querySelector("[data-copy-suggestion]");
  var libraryScript = document.querySelector("#prompt-library-data");
  var promptLibrary = [];
  if (libraryScript) {
    try { promptLibrary = JSON.parse(libraryScript.textContent || "[]"); } catch (_) {}
  }

  if (suggestionForm && useCaseInput && suggestionResult) {
    suggestionForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var useCase = useCaseInput.value.trim();
      if (useCase.length < 8) {
        suggestionStatus.textContent = "Precisamos de um pouco mais de contexto.";
        suggestionTitle.textContent = "Descreve a tarefa numa frase completa.";
        suggestionCode.textContent = "";
        suggestionResult.hidden = false;
        suggestionCopy.hidden = true;
        return;
      }

      var stopWords = new Set([
        "para", "quero", "queria", "fazer", "uma", "umas", "uns", "com", "como",
        "que", "isto", "isso", "este", "esta", "meu", "minha", "mais", "sobre"
      ]);
      var tokens = foldText(useCase).split(/[^a-z0-9]+/).filter(function (token) {
        return token.length > 2 && !stopWords.has(token);
      });
      var best = null;
      var bestScore = 0;
      promptLibrary.forEach(function (prompt) {
        var score = tokens.reduce(function (total, token) {
          return total + (prompt.search.indexOf(token) !== -1 ? 1 : 0);
        }, 0);
        if (score > bestScore) {
          best = prompt;
          bestScore = score;
        }
      });

      var minimumScore = tokens.length <= 2 ? 1 : 2;
      if (best && bestScore >= minimumScore) {
        suggestionStatus.textContent = "Encontrámos um caso de uso testado na biblioteca PTIA.";
        suggestionTitle.textContent = best.title;
        suggestionCode.textContent = best.template;
      } else {
        suggestionStatus.textContent = "Não temos um caso de uso PTIA testado para isto. A sugestão abaixo é uma estrutura inicial, não validada.";
        suggestionTitle.textContent = "Prompt sugerido para o teu caso";
        suggestionCode.textContent =
          "Quero executar esta tarefa: " + useCase + ".\n\n" +
          "Atua como especialista no domínio relevante. Antes de responder:\n" +
          "1. Resume o objetivo e identifica informação em falta.\n" +
          "2. Declara os pressupostos necessários e não inventes factos.\n" +
          "3. Propõe uma abordagem por etapas, adequada ao contexto.\n" +
          "4. Produz um resultado concreto e utilizável, com estrutura clara.\n" +
          "5. Indica riscos, limitações e o que deve ser validado por uma pessoa.\n\n" +
          "Contexto adicional: [ADICIONAR CONTEXTO]\n" +
          "Restrições: [ADICIONAR RESTRIÇÕES]\n" +
          "Formato final pretendido: [ADICIONAR FORMATO].";
      }
      suggestionResult.hidden = false;
      suggestionCopy.hidden = false;
    });
  }

  if (suggestionCopy && suggestionCode) {
    suggestionCopy.addEventListener("click", function () {
      copyText(suggestionCode.textContent, suggestionCopy);
    });
  }

  document.querySelectorAll("[data-copy-prompt]").forEach(function (button) {
    button.addEventListener("click", async function () {
      var code = button.closest(".prompt-card").querySelector("code");
      if (!code) return;
      await copyText(code.textContent, button);
    });
  });
})();
