const PTIA_DATA = {
  today: [
    {
      n: "01",
      title: "Governo quer usar IA no combate aos incêndios ainda este ano.",
      pt: "É o tipo de aplicação pública onde a IA deixa de ser promessa abstrata e passa para decisão operacional: previsão, recursos e risco no terreno.",
      source: "Observador",
      tag: "Portugal",
      time: "há 12h",
      readtime: "4 min",
      lead: true,
      url: "https://observador.pt/"
    },
    {
      n: "02",
      title: "Estado aposta em IA na Saúde com promessa de poupança relevante.",
      pt: "O ponto crítico não é a poupança anunciada. É perceber que processos clínicos e administrativos vão ser redesenhados, auditados e medidos.",
      source: "Jornal Económico",
      tag: "Empresas",
      time: "há 14h",
      readtime: "6 min",
      url: "https://jornaleconomico.sapo.pt/"
    },
    {
      n: "03",
      title: "Empresas portuguesas começam a tratar IA como infraestrutura, não como ferramenta.",
      pt: "A mudança importa para PME: menos experiências soltas, mais integração em vendas, suporte, reporting e operações.",
      source: "PTIA Radar",
      tag: "Empresas",
      time: "ontem",
      readtime: "5 min",
      url: "#"
    },
    {
      n: "04",
      title: "Agentes de IA entram no ciclo de produto, mas ainda precisam de avaliação séria.",
      pt: "Para builders, a pergunta já não é se o agente responde. É se falha de forma previsível, auditável e barata.",
      source: "Research Radar",
      tag: "Builders",
      time: "ontem",
      readtime: "7 min",
      url: "#"
    },
    {
      n: "05",
      title: "O AI Act começa a sair do papel e a entrar em checklists de decisão.",
      pt: "Empresas portuguesas devem mapear casos de uso antes de comprar ou lançar sistemas com risco regulatório.",
      source: "European Commission",
      tag: "Regulação",
      time: "2 dias",
      readtime: "8 min",
      url: "#"
    },
    {
      n: "06",
      title: "Modelos de vídeo tornam-se produto de consumo, mas a utilidade empresarial ainda é desigual.",
      pt: "Marketing e formação ganham velocidade. Prova, direitos de imagem e consistência continuam a separar demo de workflow.",
      source: "AI Video Radar",
      tag: "Ferramentas",
      time: "2 dias",
      readtime: "5 min",
      url: "#"
    },
    {
      n: "07",
      title: "Investigação em modelos pequenos volta a ganhar relevância para equipas com orçamento real.",
      pt: "Nem todas as empresas precisam de frontier models. Para tarefas internas, modelos pequenos bem avaliados podem chegar.",
      source: "arXiv",
      tag: "Investigação",
      time: "3 dias",
      readtime: "6 min",
      url: "#"
    },
    {
      n: "08",
      title: "Ferramentas de coding assistido passam de autocomplete para trabalho assíncrono.",
      pt: "O impacto em Portugal vai depender menos da ferramenta e mais da disciplina: specs, testes, revisão e ownership.",
      source: "Builder Radar",
      tag: "Builders",
      time: "3 dias",
      readtime: "6 min",
      url: "#"
    }
  ],
  sections: [
    { id: "mundo", name: "Mundo", blurb: "Movimentos globais de OpenAI, Google, Anthropic, Meta, Mistral e restantes laboratórios que mudam o terreno." },
    { id: "portugal", name: "Portugal", blurb: "Adoção, talento, investimento, política pública e empresas portuguesas a passar da conversa para execução." },
    { id: "builders", name: "Builders", blurb: "Ferramentas, frameworks, agentes, avaliação e infraestrutura para quem constrói produtos com IA." },
    { id: "regulacao", name: "Regulação", blurb: "AI Act, privacidade, soberania, segurança e regras que afetam decisões reais." },
    { id: "historias-reais", name: "Histórias reais", blurb: "Casos concretos de empresas, equipas, trabalho e adoção. O que acontece quando a IA sai do slide." },
    { id: "previsoes-futuras", name: "Previsões Futuras", blurb: "Sinais de médio prazo: trabalho, interfaces, modelos, pesquisa, educação e o que pode estar a formar-se." }
  ]
};

const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
let activeFilter = "Todos";

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[char]));
}

function formatLongDate(date) {
  return new Intl.DateTimeFormat("pt-PT", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric"
  }).format(date);
}

function setupDateline() {
  const dateEl = document.getElementById("date-long");
  const clockEl = document.getElementById("clock");
  const yearEl = document.getElementById("year");
  const update = () => {
    const now = new Date();
    if (dateEl) dateEl.textContent = formatLongDate(now);
    if (clockEl) {
      clockEl.textContent = new Intl.DateTimeFormat("pt-PT", {
        hour: "2-digit",
        minute: "2-digit"
      }).format(now);
    }
    if (yearEl) yearEl.textContent = String(now.getFullYear());
  };
  update();
  setInterval(update, 60000);
}

function setupTheme() {
  const button = document.getElementById("theme-toggle");
  const apply = (theme) => {
    document.documentElement.dataset.theme = theme;
    if (button) {
      button.textContent = theme === "dark" ? "Claro" : "Escuro";
      button.setAttribute("aria-pressed", String(theme === "dark"));
    }
    try { localStorage.setItem("ptia-theme", theme); } catch (_) {}
  };
  apply(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  button?.addEventListener("click", () => {
    apply(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

function renderIssueList() {
  const issueList = document.getElementById("issue-list");
  if (!issueList) return;
  issueList.innerHTML = PTIA_DATA.today.slice(0, 4).map((item) => `
    <li><span>${escapeHtml(item.title.replace(/\.$/, ""))}</span></li>
  `).join("");
}

function primaryStory() {
  return PTIA_DATA.today.find((item) => item.lead) || PTIA_DATA.today[0];
}

function renderBreakingTicker() {
  const target = document.getElementById("breaking-content");
  if (!target) return;
  const items = PTIA_DATA.today.slice(0, 8).map((item, index) => `
    <a href="${escapeHtml(item.url || "#")}" ${item.url && item.url !== "#" ? 'target="_blank" rel="noopener"' : ""}>
      <span>${escapeHtml(item.time || `#${index + 1}`)}</span>
      ${escapeHtml(item.title)}
    </a>
  `).join("");
  target.innerHTML = `<div class="ticker-line">${items}${items}</div>`;
}

function renderFrontPage() {
  const lead = primaryStory();
  const leadCard = document.getElementById("lead-card");
  const rail = document.getElementById("rail-stories");
  const signalsCount = document.getElementById("signals-count");
  const railSignals = document.getElementById("rail-signals");
  const moreCount = document.getElementById("more-count");
  const editionDate = document.getElementById("edition-date");
  const lastUpdated = document.getElementById("last-updated");
  const railClock = document.getElementById("rail-clock");

  if (signalsCount) signalsCount.textContent = String(PTIA_DATA.today.length);
  if (railSignals) railSignals.innerHTML = `${PTIA_DATA.today.length}<sup>/1840</sup>`;
  if (moreCount) moreCount.textContent = String(Math.max(PTIA_DATA.today.length - 1, 0));
  if (editionDate) editionDate.textContent = formatLongDate(new Date());
  const nowLabel = new Intl.DateTimeFormat("pt-PT", { hour: "2-digit", minute: "2-digit" }).format(new Date());
  if (lastUpdated) lastUpdated.textContent = nowLabel;
  if (railClock) railClock.textContent = nowLabel;

  if (leadCard && lead) {
    const href = lead.url && lead.url !== "#" ? lead.url : "#";
    leadCard.innerHTML = `
      <a class="cover" href="${escapeHtml(href)}" ${href !== "#" ? 'target="_blank" rel="noopener"' : ""}>
        ${storyVisual(lead, true)}
        <span class="cover-badge"><span class="live-dot"></span> Story principal</span>
        <span class="numstamp">№${escapeHtml(lead.n || "01")}<small>Lead story</small></span>
        <span class="cover-stamp">${escapeHtml(lead.tag || "IA")} · ${escapeHtml(lead.source || "PTIA")}</span>
      </a>
      <div class="lead-meta">
        <span>${escapeHtml(lead.tag || "IA")}</span>
        <strong>${escapeHtml(lead.source || "PTIA")}</strong>
        <span>${escapeHtml(lead.readtime || "4 min")}</span>
        <span>${escapeHtml(lead.time || "hoje")}</span>
        <em>Em análise</em>
      </div>
      <h1><a href="${escapeHtml(href)}" ${href !== "#" ? 'target="_blank" rel="noopener"' : ""}>${escapeHtml(lead.title)}</a></h1>
      <p class="lead-dek">${escapeHtml(lead.pt)}</p>
      <footer class="lead-foot">
        <span class="byline-avatar">J</span>
        <span>Por <em>João Ferreira</em> · Editor</span>
        <a href="${escapeHtml(href)}" ${href !== "#" ? 'target="_blank" rel="noopener"' : ""}>Ler ângulo completo -></a>
      </footer>
    `;
  }

  if (rail) {
    rail.innerHTML = PTIA_DATA.today.filter((item) => item !== lead).slice(0, 3).map((item) => `
      <a class="rail-story" href="${escapeHtml(item.url || "#")}" ${item.url && item.url !== "#" ? 'target="_blank" rel="noopener"' : ""}>
        <span class="rail-meta">№${escapeHtml(item.n)} · ${escapeHtml(item.tag)} · ${escapeHtml(item.source)} · ${escapeHtml(item.time)}</span>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.pt)}</p>
      </a>
    `).join("");
  }

}

function categories() {
  const counts = PTIA_DATA.today.reduce((acc, item) => {
    acc[item.tag] = (acc[item.tag] || 0) + 1;
    return acc;
  }, {});
  return [["Todos", PTIA_DATA.today.length], ...Object.entries(counts)];
}

function renderFilters() {
  const filterbar = document.getElementById("filterbar");
  if (!filterbar) return;
  filterbar.innerHTML = categories().map(([label, count]) => `
    <button type="button" data-filter="${escapeHtml(label)}" aria-pressed="${label === activeFilter}">
      ${escapeHtml(label)} ${count}
    </button>
  `).join("");
  filterbar.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter || "Todos";
      renderFilters();
      renderArticles();
    });
  });
}

function storyVisual(item, isLead) {
  if (item.imageUrl) {
    return `<figure class="${isLead ? "lead-visual" : "article-thumb"}">
      <img src="${escapeHtml(item.imageUrl)}" alt="" loading="${isLead ? "eager" : "lazy"}">
    </figure>`;
  }
  const circles = Array.from({ length: 19 }, (_, index) => {
    const r = 10 + index * 12;
    const opacity = Math.max(0.03, 0.22 - index * 0.009);
    return `<circle cx="50%" cy="50%" r="${r}" fill="none" stroke="#fff" stroke-opacity="${opacity}" stroke-width="1"/>`;
  }).join("");
  if (isLead) {
    return `<div class="lead-visual"><svg viewBox="0 0 360 220" aria-hidden="true">${circles}</svg></div>`;
  }
  return `<div class="article-thumb muted-visual" aria-hidden="true"></div>`;
}

function articleRow(item, isLead) {
  const href = item.url && item.url !== "#" ? item.url : "#";
  return `<article class="article-row ${isLead ? "lead" : ""}">
    <div class="article-num">№${escapeHtml(item.n)}</div>
    <div>
      <h3 class="article-title"><a href="${escapeHtml(href)}" ${href !== "#" ? 'target="_blank" rel="noopener"' : ""}>${escapeHtml(item.title)}</a></h3>
      <p class="pt-angle">${escapeHtml(item.pt)}</p>
    </div>
    ${storyVisual(item, isLead)}
    ${!isLead ? `<div class="article-meta"><span class="tag">${escapeHtml(item.tag)}</span><strong>${escapeHtml(item.source)}</strong><span>${escapeHtml(item.time)} · ${escapeHtml(item.readtime)}</span></div>` : ""}
  </article>`;
}

function renderArticles() {
  const container = document.getElementById("posts");
  if (!container) return;
  const items = activeFilter === "Todos"
    ? PTIA_DATA.today
    : PTIA_DATA.today.filter((item) => item.tag === activeFilter);
  if (!items.length) {
    container.innerHTML = `<article class="article-row"><div></div><div><h3 class="article-title">Sem sinais nesta secção.</h3><p class="pt-angle">O radar ainda não encontrou uma fonte suficientemente forte.</p></div></article>`;
    return;
  }
  const lead = items.find((item) => item.lead) || items[0];
  const rows = [articleRow(lead, true)];
  items.filter((item) => item !== lead).forEach((item, index) => {
    rows.push(articleRow(item, false));
    if (activeFilter === "Todos" && index === 1) {
      rows.push(`<aside class="pullquote">
        <div class="qmark">“</div>
        <blockquote>
          <p>Se uma notícia não muda uma decisão, uma prioridade ou uma conversa, fica fora do radar PTIA.</p>
          <cite>Editor — leitura da semana</cite>
        </blockquote>
      </aside>`);
    }
  });
  container.innerHTML = rows.join("");
}

function renderMap() {
  const grid = document.getElementById("map-grid");
  if (!grid) return;
  const counts = PTIA_DATA.today.reduce((acc, item) => {
    acc[item.tag] = (acc[item.tag] || 0) + 1;
    return acc;
  }, {});
  grid.innerHTML = PTIA_DATA.sections.map((section, index) => `
    <article class="map-cell" id="${escapeHtml(section.id)}">
      <div class="map-top"><em>${String(index + 1).padStart(2, "0")}</em><span><strong>${counts[section.name] || 0}</strong> entradas</span></div>
      <h3>${escapeHtml(section.name)}</h3>
      <p>${escapeHtml(section.blurb)}</p>
      <a href="#hoje">Abrir secção →</a>
    </article>
  `).join("");
}

function setupReveal() {
  const items = document.querySelectorAll(".reveal");
  if (reducedMotion || !("IntersectionObserver" in window)) {
    items.forEach((item) => item.classList.add("in"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("in");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });
  items.forEach((item) => observer.observe(item));
}

function setupCountUp() {
  const nodes = document.querySelectorAll("[data-count]");
  const setFinal = (node) => {
    node.textContent = Number(node.dataset.count || 0).toLocaleString("pt-PT") + (node.dataset.suffix || "");
  };
  if (reducedMotion || !("IntersectionObserver" in window)) {
    nodes.forEach(setFinal);
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const node = entry.target;
      const target = Number(node.dataset.count || 0);
      const suffix = node.dataset.suffix || "";
      const start = performance.now();
      const duration = 1100;
      const tick = (now) => {
        const progress = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        node.textContent = Math.round(target * eased).toLocaleString("pt-PT") + suffix;
        if (progress < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      observer.unobserve(node);
    });
  }, { threshold: 0.2 });
  nodes.forEach((node) => observer.observe(node));
}

function setupSignalViz() {
  const svg = document.getElementById("signal-viz");
  if (!svg) return;
  const W = 480;
  const H = 180;
  const toPath = (points) => points.map((point, index) => `${index ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`).join(" ");
  const draw = (t) => {
    const noise = [1.3, 2.7, 4.1, 5.5, 6.8, 8.2, 9.6, 11].map((seed, index) => {
      const points = [];
      for (let x = 0; x <= W; x += 12) {
        const y = H / 2
          + Math.sin(x * 0.013 + seed + t * 0.6) * 22
          + Math.sin(x * 0.029 + seed * 1.7 + t * 0.9) * 14
          + Math.cos(x * 0.05 + seed * 2.3 + t * 1.3) * 8;
        points.push([x, y]);
      }
      return `<path d="${toPath(points)}" stroke="currentColor" stroke-opacity="${0.18 + (index % 3) * 0.06}" stroke-width="0.8" fill="none"/>`;
    }).join("");
    const signal = [];
    for (let x = 0; x <= W; x += 4) {
      signal.push([x, H / 2 + Math.sin(x * 0.011 - t * 0.7) * 38]);
    }
    const markers = [];
    for (let i = 2; i < signal.length - 2; i += 1) {
      const y = signal[i][1];
      if (y < signal[i - 2][1] && y < signal[i + 2][1] && y < H / 2 - 28) {
        markers.push(signal[i]);
        i += 20;
      }
    }
    svg.innerHTML = `<defs>
      <linearGradient id="sigGrad" x1="0" x2="1">
        <stop offset="0%" stop-color="var(--signal)" stop-opacity="0"/>
        <stop offset="20%" stop-color="var(--signal)" stop-opacity="1"/>
        <stop offset="80%" stop-color="var(--signal)" stop-opacity="1"/>
        <stop offset="100%" stop-color="var(--signal)" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <line x1="0" y1="${H / 2}" x2="${W}" y2="${H / 2}" stroke="currentColor" stroke-opacity="0.06" stroke-dasharray="2 4"/>
    ${noise}
    <path d="${toPath(signal)}" stroke="url(#sigGrad)" stroke-width="2.2" fill="none" stroke-linecap="round"/>
    ${markers.slice(0, 3).map((marker) => `<g><circle cx="${marker[0]}" cy="${marker[1]}" r="3.5" fill="var(--signal)"/><circle cx="${marker[0]}" cy="${marker[1]}" r="7" fill="none" stroke="var(--signal)" stroke-opacity="0.3"/></g>`).join("")}`;
  };
  if (reducedMotion) {
    draw(0);
    return;
  }
  let raf;
  let last = performance.now();
  let t = 0;
  const loop = (now) => {
    t += (now - last) * 0.0008;
    last = now;
    draw(t);
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
  window.addEventListener("beforeunload", () => cancelAnimationFrame(raf), { once: true });
}

async function hydrateFromFeedIfAvailable() {
  try {
    let feed = null;
    for (const url of ["site-feed.json", "/api/site-feed"]) {
      const response = await fetch(url, { cache: "no-store" });
      if (response.ok) {
        feed = await response.json();
        break;
      }
    }
    if (!feed) return;
    if (!feed.posts?.length) return;
    PTIA_DATA.today = feed.posts.map((post, index) => ({
      n: String(index + 1).padStart(2, "0"),
      title: post.title || "Entrada PTIA",
      pt: (post.body || "").split("\n").find((line) => line.length > 40) || "Leitura PTIA com fonte original e contexto para Portugal.",
      source: post.source_urls?.[0] ? "Fonte original" : "PTIA",
      tag: post.section || post.channel || "Mundo",
      time: "publicado",
      readtime: "4 min",
      lead: index === 0,
      url: post.source_urls?.[0] || "#",
      imageUrl: post.image_url || ""
    }));
    renderBreakingTicker();
    renderFrontPage();
    renderFilters();
    renderArticles();
    renderMap();
    setupSignalViz();
  } catch (_) {}
}

setupDateline();
setupTheme();
renderBreakingTicker();
renderFrontPage();
renderFilters();
renderArticles();
renderMap();
setupReveal();
setupCountUp();
setupSignalViz();
hydrateFromFeedIfAvailable();
