const PTIA_DATA = {
  today: [],
  sections: [
    { id: "mundo", name: "Mundo", blurb: "Movimentos globais de OpenAI, Google, Anthropic, Meta, Mistral e restantes laboratórios que mudam o terreno." },
    { id: "portugal", name: "Portugal", blurb: "Adoção, talento, investimento, política pública e empresas portuguesas a passar da conversa para execução." },
    { id: "builders", name: "Builders", blurb: "Ferramentas, frameworks, agentes, avaliação e infraestrutura para quem constrói produtos com IA." },
    { id: "regulacao", name: "Regulação", blurb: "AI Act, privacidade, soberania, segurança e regras que afetam decisões reais." },
    { id: "historias-reais", name: "Histórias reais", blurb: "Casos concretos de empresas, equipas, trabalho e adoção. O que acontece quando a IA sai do slide." },
    { id: "previsoes-futuras", name: "Previsões Futuras", blurb: "Sinais de médio prazo: trabalho, interfaces, modelos, pesquisa, educação e o que pode estar a formar-se." }
  ]
};

PTIA_DATA.guides = [
  {
    title: "IA para PME: por onde começar sem desperdiçar dinheiro",
    intent: "Empresas",
    blurb: "Um guia prático para escolher casos de uso pequenos, medir impacto e evitar pilotos que nunca chegam a operação.",
    search: "ia para pme portugal",
    url: "guias/ia-para-pme-portugal/"
  },
  {
    title: "O que é um agente de IA e quando é que faz sentido usar",
    intent: "Builders",
    blurb: "A diferença entre chatbot, automação e agente. Onde há valor real, onde há risco e que perguntas fazer antes de construir.",
    search: "agentes de ia o que são",
    url: "guias/agentes-de-ia-empresas/"
  },
  {
    title: "AI Act para empresas portuguesas: o mínimo que importa saber",
    intent: "Regulação",
    blurb: "Como mapear casos de uso, risco, fornecedores e responsabilidades antes de comprar ou lançar sistemas de IA.",
    search: "ai act portugal empresas",
    url: "guias/ai-act-empresas-portuguesas/"
  },
  {
    title: "Como usar ChatGPT no trabalho sem expor dados sensíveis",
    intent: "Trabalho",
    blurb: "Boas práticas para equipas, gestores e profissionais que querem produtividade sem criar risco desnecessário.",
    search: "usar chatgpt no trabalho dados sensiveis",
    url: "guias/chatgpt-no-trabalho-dados-sensiveis/"
  },
  {
    title: "Ferramentas de IA para empresas: como escolher sem seguir hype",
    intent: "Decisão",
    blurb: "Critérios de escolha: integração, dados, custo total, segurança, ownership e impacto mensurável.",
    search: "ferramentas de ia para empresas",
    url: "guias/ferramentas-de-ia-para-empresas/"
  }
];

const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
let activeFilter = "Todos";
let lastFeedSignature = "";
let currentFeedUpdatedAt = "";
let currentFeedFromCache = false;
const FEED_CACHE_KEY = "ptia-site-feed-v1";
// A stale editorial feed should never look current for several days. Keep the
// offline fallback short and let the page show its sync state when it expires.
const MAX_CACHED_FEED_AGE_MS = 6 * 60 * 60 * 1000;

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[char]));
}

function articleUrl(post) {
  if (post?.articleUrl) return `/${String(post.articleUrl).replace(/^\/+/, "")}`;
  if (post?.article_url) return `/${String(post.article_url).replace(/^\/+/, "")}`;
  return post?.id ? `article.html?id=${encodeURIComponent(post.id)}` : (post?.url || "#");
}

function linkAttrs(href) {
  return /^https?:\/\//i.test(href || "") ? 'target="_blank" rel="noopener"' : "";
}

function cleanPublicText(value) {
  const raw = String(value || "");
  const withoutMarkdownLinks = raw.replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g, "$1");
  const tmp = document.createElement("textarea");
  tmp.innerHTML = withoutMarkdownLinks;
  const decoded = tmp.value;
  const wrapper = document.createElement("div");
  wrapper.innerHTML = decoded;
  return (wrapper.textContent || wrapper.innerText || decoded)
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function isUrlOnly(value) {
  return /^(?:https?:\/\/|www\.)\S+\.?$/i.test(String(value || "").trim());
}

function firstContentParagraph(value) {
  const lines = cleanPublicText(value).split(/\n+/).map((line) => line.trim());
  const first = lines.find((line) => line.length > 40 && !/^fonte(?:\s+original)?\s*:/i.test(line) && !isUrlOnly(line));
  if (!first) return "Lê a análise, o contexto e as fontes no artigo.";
  const limit = 220;
  if (first.length <= limit) return first;
  const trimmed = first.slice(0, limit).replace(/\s+\S*$/, "").replace(/[\s.,;:]+$/, "");
  return `${trimmed}…`;
}

function readMinutes(value) {
  const words = cleanPublicText(value).split(/\s+/).filter(Boolean).length;
  return `${Math.max(2, Math.ceil(words / 210))} min`;
}

function relativeTime(value) {
  if (!value) return "hoje";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "hoje";
  const diffMs = Date.now() - date.getTime();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (diffMs < minute) return "agora";
  if (diffMs < hour) return `h\u00e1 ${Math.max(1, Math.floor(diffMs / minute))} min`;
  if (diffMs < day) return `h\u00e1 ${Math.max(1, Math.floor(diffMs / hour))} h`;
  if (diffMs < 2 * day) return "ontem";
  return `h\u00e1 ${Math.floor(diffMs / day)} dias`;
}

function issueLabel(date) {
  const start = new Date(date.getFullYear(), 0, 1);
  const day = Math.floor((date - start) / 86400000) + 1;
  return String(Math.ceil(day / 7)).padStart(3, "0");
}

function parseFeedDate(value) {
  if (!value || typeof value !== "string") return null;
  const raw = value.trim();
  const isoDate = new Date(raw);
  if (!Number.isNaN(isoDate.getTime())) return isoDate;
  const localMatch = raw.match(/^(\d{2})\/(\d{2})\/(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?$/);
  if (!localMatch) return null;
  const [, day, month, year, hour = "00", minute = "00", second = "00"] = localMatch;
  const localDate = new Date(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute),
    Number(second)
  );
  return Number.isNaN(localDate.getTime()) ? null : localDate;
}

function isPublishedNow(value) {
  if (!value) return true;
  const date = parseFeedDate(value);
  if (!date) return false;
  return date.getTime() <= Date.now();
}

function visibleFeedPosts(feed) {
  const posts = feed?.posts || [];
  let visible = posts.filter((post) => isPublishedNow(post.published_at));
  const newAppleVisible = visible.some((post) => post.id === "post_a42ec13e57b539f599");
  if (newAppleVisible) {
    visible = visible.filter((post) => post.id !== "post_ca28e48d21d880a356");
  }
  return visible.sort((a, b) => {
    const aDate = parseFeedDate(a.published_at)?.getTime() ?? Number.NEGATIVE_INFINITY;
    const bDate = parseFeedDate(b.published_at)?.getTime() ?? Number.NEGATIVE_INFINITY;
    return bDate - aDate;
  });
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
  const issueEl = document.querySelector(".dateline .issue");
  const update = () => {
    const now = new Date();
    if (dateEl) dateEl.textContent = formatLongDate(now);
    if (issueEl) issueEl.textContent = issueLabel(now);
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
  const frontStories = frontPageStories();
  const items = PTIA_DATA.today.filter((item) => !frontStories.includes(item)).slice(0, 8).map((item, index) => `
    <a href="${escapeHtml(articleUrl(item))}" ${linkAttrs(articleUrl(item))}>
      <span>${escapeHtml(item.time || `#${index + 1}`)}</span>
      ${escapeHtml(item.title)}
    </a>
  `).join("");
  target.innerHTML = `<div class="ticker-line">${items}${items}</div>`;
}

const FRONT_RAIL_COUNT = 3;
const MORE_LIST_LIMIT = 10;

function primaryTag(item) {
  const tags = Array.isArray(item?.tag) ? item.tag : [item?.tag];
  return tags.find(Boolean) || "IA";
}

function frontPageStories() {
  const lead = primaryStory();
  if (!lead) return [];
  return [lead, ...PTIA_DATA.today.filter((item) => item !== lead).slice(0, FRONT_RAIL_COUNT)];
}

function renderFrontPage() {
  const [lead, ...railItems] = frontPageStories();
  const leadCard = document.getElementById("lead-card");
  const rail = document.getElementById("rail-stories");
  const moreCount = document.getElementById("more-count");
  const editionDay = document.getElementById("edition-day");
  const lastUpdated = document.getElementById("last-updated");

  if (moreCount) moreCount.textContent = String(Math.min(MORE_LIST_LIMIT, Math.max(PTIA_DATA.today.length - railItems.length - 1, 0)));
  if (editionDay) editionDay.textContent = `Edição de ${new Intl.DateTimeFormat("pt-PT", { weekday: "long" }).format(new Date())}`;
  const feedDate = new Date(currentFeedUpdatedAt || Date.now());
  const displayDate = Number.isNaN(feedDate.getTime()) ? new Date() : feedDate;
  const updatedLabel = new Intl.DateTimeFormat("pt-PT", { hour: "2-digit", minute: "2-digit" }).format(displayDate);
  if (lastUpdated) lastUpdated.textContent = `atualizada às ${updatedLabel}${currentFeedFromCache ? " · edição guardada" : ""}`;

  if (leadCard && lead) {
    const href = escapeHtml(articleUrl(lead));
    const attrs = linkAttrs(articleUrl(lead));
    leadCard.innerHTML = `
      <div class="lead-copy">
        <p class="lead-kicker">${escapeHtml(primaryTag(lead))}</p>
        <h2 class="lead-title"><a href="${href}" ${attrs}>${escapeHtml(lead.title)}</a></h2>
        <p class="lead-dek">${escapeHtml(lead.pt)}</p>
        <p class="lead-byline">Por <span>João Ferreira</span> · ${escapeHtml(lead.time || "hoje")} · ${escapeHtml(lead.readtime || "4 min")} de leitura</p>
      </div>
      <a class="lead-media" href="${href}" ${attrs} tabindex="-1" aria-hidden="true">${storyVisual(lead, true, true)}</a>
    `;
    fadeInImages(leadCard);
  }

  if (rail) {
    rail.innerHTML = railItems.map((item) => `
      <a class="rail-story" href="${escapeHtml(articleUrl(item))}" ${linkAttrs(articleUrl(item))}>
        <span class="rail-meta"><span>${escapeHtml(primaryTag(item))}</span> ${escapeHtml(item.time || "")}</span>
        <h3>${escapeHtml(item.title)}</h3>
      </a>
    `).join("");
  }
}

function categories() {
  const counts = {};
  PTIA_DATA.today.forEach((item) => {
    const tags = Array.isArray(item.tag) ? item.tag : (item.tag ? [item.tag] : []);
    tags.forEach((t) => {
      counts[t] = (counts[t] || 0) + 1;
    });
  });
  const order = ["Todos", "Mundo", "Portugal", "Builders", "Regulação", "Histórias reais", "Previsões Futuras"];
  const sortedEntries = Object.entries(counts).sort((a, b) => {
    const idxA = order.indexOf(a[0]);
    const idxB = order.indexOf(b[0]);
    if (idxA !== -1 && idxB !== -1) return idxA - idxB;
    if (idxA !== -1) return -1;
    if (idxB !== -1) return 1;
    return a[0].localeCompare(b[0]);
  });
  return [["Todos", Math.min(10, PTIA_DATA.today.length)], ...sortedEntries];
}

function renderFilters() {
  const filterbar = document.getElementById("filterbar");
  if (!filterbar) return;
  const previousIndicator = filterbar.querySelector(".filter-indicator");
  const previousLeft = previousIndicator?.style.left;
  const previousWidth = previousIndicator?.style.width;
  const previousScroll = filterbar.scrollLeft;
  filterbar.innerHTML = `<span class="filter-indicator" aria-hidden="true"></span>` + categories().map(([label, count]) => `
    <button type="button" data-filter="${escapeHtml(label)}" aria-pressed="${label === activeFilter}">
      <span>${escapeHtml(label)}</span><span class="filter-count">${count}</span>
    </button>
  `).join("");
  filterbar.scrollLeft = previousScroll;
  const indicator = filterbar.querySelector(".filter-indicator");
  if (previousLeft && previousWidth) {
    indicator.style.left = previousLeft;
    indicator.style.width = previousWidth;
  }
  const positionIndicator = () => {
    const selected = filterbar.querySelector('[aria-pressed="true"]');
    if (!selected) return;
    indicator.style.left = `${selected.offsetLeft}px`;
    indicator.style.width = `${selected.offsetWidth}px`;
  };
  // Two frames preserve the previous indicator position across the filter render.
  requestAnimationFrame(() => requestAnimationFrame(positionIndicator));
  filterbar._resizeObserver?.disconnect();
  if ("ResizeObserver" in window) {
    filterbar._resizeObserver = new ResizeObserver(positionIndicator);
    filterbar._resizeObserver.observe(filterbar);
    filterbar.querySelectorAll("button").forEach((button) => filterbar._resizeObserver.observe(button));
  }
  filterbar.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter || "Todos";
      filterbar.querySelectorAll("button").forEach((item) => {
        item.setAttribute("aria-pressed", String(item.dataset.filter === activeFilter));
      });
      positionIndicator();
      renderArticles();
    });
  });
}

// Only the front-page lead image is fetched eagerly with high priority (it is the LCP element).
function storyVisual(item, isLead, isPriority = false) {
  if (item.imageUrl) {
    const size = String(item.imageUrl).match(/(\d{3,4})x(\d{3,4})\.(?:jpe?g|png|webp|avif)$/i);
    const dims = size ? ` width="${size[1]}" height="${size[2]}"` : "";
    const priority = isPriority ? 'loading="eager" fetchpriority="high"' : 'loading="lazy"';
    return `<figure class="${isLead ? "lead-visual" : "article-thumb"}">
      <img src="${escapeHtml(item.imageUrl)}" alt=""${dims} ${priority} decoding="async">
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
  const href = articleUrl(item);
  const tagsStr = Array.isArray(item.tag) ? item.tag.join(", ") : (item.tag || "");
  return `<article class="article-row ${isLead ? "lead" : ""}">
    <div class="article-num">№${escapeHtml(item.n)}</div>
    <div>
      <h3 class="article-title"><a href="${escapeHtml(href)}" ${linkAttrs(href)}>${escapeHtml(item.title)}</a></h3>
      <p class="pt-angle">${escapeHtml(item.pt)}</p>
    </div>
    ${storyVisual(item, isLead)}
    ${!isLead ? `<div class="article-meta"><span class="tag">${escapeHtml(tagsStr)}</span><strong>${escapeHtml(item.source)}</strong><span>${escapeHtml(item.time)} · ${escapeHtml(item.readtime)}</span></div>` : ""}
  </article>`;
}

function renderArticles() {
  const container = document.getElementById("posts");
  if (!container) return;
  const frontStories = frontPageStories();
  const items = activeFilter === "Todos"
    ? PTIA_DATA.today.filter((item) => !frontStories.includes(item)).slice(0, MORE_LIST_LIMIT)
    : PTIA_DATA.today.filter((item) => {
        const tags = Array.isArray(item.tag) ? item.tag : (item.tag ? [item.tag] : []);
        return tags.includes(activeFilter);
      });
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
  fadeInImages(container);
  if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches && container.animate) {
    container.animate([{ opacity: 0.45, transform: "translateY(8px)" }, { opacity: 1, transform: "translateY(0)" }], {
      duration: 260, easing: "cubic-bezier(.22,1,.36,1)"
    });
  }
}

function renderMap() {
  const grid = document.getElementById("map-grid");
  if (!grid) return;
  const counts = {};
  PTIA_DATA.today.forEach((item) => {
    const tags = Array.isArray(item.tag) ? item.tag : (item.tag ? [item.tag] : []);
    tags.forEach((t) => {
      counts[t] = (counts[t] || 0) + 1;
    });
  });
  grid.innerHTML = PTIA_DATA.sections.map((section, index) => `
    <article class="map-cell" id="${escapeHtml(section.id)}">
      <div class="map-top"><em>${String(index + 1).padStart(2, "0")}</em><span><strong>${counts[section.name] || 0}</strong> entradas</span></div>
      <h3>${escapeHtml(section.name)}</h3>
      <p>${escapeHtml(section.blurb)}</p>
      <a href="#${escapeHtml(section.id)}">Abrir secção →</a>
    </article>
  `).join("");
}

function formatCompactNumber(value) {
  return new Intl.NumberFormat("pt-PT", {
    notation: "compact",
    maximumFractionDigits: 1
  }).format(Number(value || 0));
}

function formatRepoDate(value) {
  if (!value) return "data indisponível";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "data indisponível";
  return new Intl.DateTimeFormat("pt-PT", {
    day: "numeric",
    month: "short",
    year: "numeric"
  }).format(date);
}

async function renderGitHubRepos() {
  const list = document.getElementById("github-repos-list");
  const updated = document.getElementById("github-repos-updated");
  if (!list) return;
  try {
    const response = await fetch("assets/github-ai-repos.json", { cache: "no-store" });
    if (!response.ok) throw new Error("GitHub radar indisponível");
    const payload = await response.json();
    const repos = Array.isArray(payload.repos) ? payload.repos : [];
    if (!repos.length) throw new Error("Sem repos para mostrar");
    if (updated) {
      updated.textContent = `Atualizado ${formatRepoDate(payload.updated_at)} · GitHub Search API`;
    }
    list.innerHTML = repos.map((repo) => `
      <a class="repo-card" href="${escapeHtml(repo.url)}" target="_blank" rel="noopener">
        <span class="repo-rank">${String(repo.rank).padStart(2, "0")}</span>
        <div>
          <h3>${escapeHtml(repo.name)}</h3>
          <p>${escapeHtml(repo.description || "Sem descrição disponível.")}</p>
          <div class="repo-meta">
            <span>${escapeHtml(repo.language || "multi")}</span>
            <span>${formatCompactNumber(repo.stars)} stars</span>
            <span>${formatCompactNumber(repo.forks)} forks</span>
            <span>update ${formatRepoDate(repo.updated_at)}</span>
          </div>
        </div>
      </a>
    `).join("");
  } catch (error) {
    if (updated) updated.textContent = "GitHub radar ainda sem dados.";
    list.innerHTML = `<article class="repo-card unavailable">
      <span class="repo-rank">--</span>
      <div>
        <h3>Top 10 ainda indisponível</h3>
        <p>A automação vai preencher esta rubrica assim que conseguir ler a API do GitHub.</p>
      </div>
    </article>`;
  }
}

function renderGuides() {
  const grid = document.getElementById("guides-grid");
  if (!grid) return;
  grid.innerHTML = PTIA_DATA.guides.map((guide, index) => `
    <a class="guide-card" href="${escapeHtml(guide.url || "#")}">
      <div class="guide-top"><span>${String(index + 1).padStart(2, "0")}</span><em>${escapeHtml(guide.intent)}</em></div>
      <h3>${escapeHtml(guide.title)}</h3>
      <p>${escapeHtml(guide.blurb)}</p>
      <footer>Pesquisa alvo: ${escapeHtml(guide.search)}</footer>
    </a>
  `).join("");
}

function setupReveal() {
  const items = document.querySelectorAll(".reveal, .section-head, .qeq-intro-text, .guides-grid");
  if (reducedMotion || !("IntersectionObserver" in window)) {
    items.forEach((item) => item.classList.add("in"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("in");
        if (!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches && entry.target.animate) {
          entry.target.animate([{ opacity: 0, transform: "translateY(18px)" }, { opacity: 1, transform: "translateY(0)" }], {
            duration: 600, easing: "cubic-bezier(.22,1,.36,1)"
          });
        }
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });
  items.forEach((item) => observer.observe(item));
}

function renderEditorialViews() {
  renderBreakingTicker();
  renderFrontPage();
  renderFilters();
  renderArticles();
  renderMap();
  renderIssueList();
}

function renderFeedStatus(message) {
  const safeMessage = escapeHtml(message);
  const breaking = document.getElementById("breaking-content");
  const leadCard = document.getElementById("lead-card");
  const rail = document.getElementById("rail-stories");
  const filters = document.getElementById("filterbar");
  const posts = document.getElementById("posts");
  const map = document.getElementById("map-grid");
  const moreCount = document.getElementById("more-count");
  const lastUpdated = document.getElementById("last-updated");

  if (breaking) breaking.innerHTML = `<div class="ticker-line"><span role="status">${safeMessage}</span></div>`;
  if (leadCard) leadCard.innerHTML = `<div class="lead-copy"><p class="lead-kicker">Edição diária</p><h2 class="lead-title" role="status">${safeMessage}</h2></div>`;
  if (rail) rail.innerHTML = "";
  if (filters) filters.innerHTML = "";
  if (posts) posts.innerHTML = `<article class="article-row"><div></div><div><h3 class="article-title">${safeMessage}</h3><p class="pt-angle">A página volta a tentar automaticamente.</p></div></article>`;
  if (map) map.innerHTML = "";
  if (moreCount) moreCount.textContent = "0";
  if (lastUpdated) lastUpdated.textContent = "a sincronizar";
}

function loadCachedFeed() {
  try {
    const feed = JSON.parse(localStorage.getItem(FEED_CACHE_KEY) || "null");
    const updatedAt = new Date(feed?.updated_at || "");
    if (!feed || Number.isNaN(updatedAt.getTime())) return null;
    if (Date.now() - updatedAt.getTime() > MAX_CACHED_FEED_AGE_MS) return null;
    return feed;
  } catch (_) {
    return null;
  }
}

function cacheFeed(feed) {
  try {
    localStorage.setItem(FEED_CACHE_KEY, JSON.stringify(feed));
  } catch (_) {}
}

async function fetchLatestFeed() {
  for (const path of ["/site-feed.json", "/api/site-feed"]) {
    try {
      const url = new URL(path, window.location.href);
      url.searchParams.set("v", String(Date.now()));
      const response = await fetch(url, {
        cache: "no-store",
        headers: { "Cache-Control": "no-cache" }
      });
      if (!response.ok) continue;
      const feed = await response.json();
      if (Array.isArray(feed?.posts)) return feed;
    } catch (error) {
      console.warn(`Falha ao carregar ${path}`, error);
    }
  }
  return null;
}

async function hydrateFromFeedIfAvailable() {
  try {
    let feed = await fetchLatestFeed();
    let fromCache = false;
    if (feed) {
      cacheFeed(feed);
    } else {
      feed = loadCachedFeed();
      fromCache = Boolean(feed);
    }
    if (!feed) return false;

    const visiblePosts = visibleFeedPosts(feed);
    if (!visiblePosts.length) return false;

    const signature = JSON.stringify({
      updatedAt: feed.updated_at || "",
      fromCache,
      visibleIds: visiblePosts.map((post) => post.id || post.published_at || post.title || "")
    });
    if (signature === lastFeedSignature) return true;

    const updateTimes = [feed.updated_at, visiblePosts[0]?.published_at]
      .map((value) => new Date(value || "").getTime())
      .filter((value) => !Number.isNaN(value));
    currentFeedUpdatedAt = updateTimes.length ? new Date(Math.max(...updateTimes)).toISOString() : "";
    currentFeedFromCache = fromCache;
    PTIA_DATA.today = visiblePosts.map((post, index) => {
      const cleanBody = cleanPublicText(post.body || "");
      return {
        id: post.id || "",
        n: String(index + 1).padStart(2, "0"),
        title: cleanPublicText(post.title || "Entrada PTIA"),
        pt: firstContentParagraph(cleanBody),
        source: post.source_urls?.[0] ? "Fonte original" : "PTIA",
        tag: post.section || post.channel || "Mundo",
        time: relativeTime(post.published_at),
        readtime: readMinutes(cleanBody),
        lead: index === 0,
        url: post.source_urls?.[0] || "#",
        body: cleanBody,
        sourceUrls: post.source_urls || [],
        publishedAt: post.published_at || "",
        articleUrl: post.article_url || "",
        imageUrl: post.image_url || ""
      };
    });
    lastFeedSignature = signature;
    renderEditorialViews();
    return true;
  } catch (error) {
    console.warn("Falha ao atualizar a edição PTIA", error);
    return false;
  }
}

// Images arrive with a short fade instead of popping in over the placeholder.
function fadeInImages(root) {
  root?.querySelectorAll("img").forEach((img) => {
    if (img.complete) return;
    img.classList.add("is-loading");
    const done = () => img.classList.remove("is-loading");
    img.addEventListener("load", done, { once: true });
    img.addEventListener("error", done, { once: true });
  });
}

// Once the masthead scrolls away, a compact bar keeps sections and Subscrever at hand.
function setupStickyBar() {
  const bar = document.getElementById("sticky-bar");
  const header = document.querySelector(".site-header");
  if (!bar || !header || !("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver(([entry]) => {
    bar.classList.toggle("is-visible", !entry.isIntersecting && entry.boundingClientRect.top < 0);
  }, { rootMargin: "-40px 0px 0px 0px" });
  observer.observe(header);
}

// The header CTA lands the reader in the front-page form, ready to type.
function focusSignupForm() {
  const section = document.getElementById("subscrever");
  const input = document.getElementById("front-signup-email");
  if (!section || !input) return false;
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  section.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
  input.focus({ preventScroll: true });
  return true;
}

// The site generator writes a static front page into index.html for crawlers that skip
// JavaScript; it stays on screen until the live feed replaces it.
function hasFrontSnapshot() {
  return Boolean(document.querySelector("#lead-card .lead-title"));
}

async function initializeSite() {
  setupDateline();
  setupTheme();
  setupStickyBar();
  const snapshot = hasFrontSnapshot();
  if (!snapshot) renderFeedStatus("A atualizar a edição…");
  renderGitHubRepos();
  renderGuides();

  const hydrated = await hydrateFromFeedIfAvailable();
  if (!hydrated && !snapshot) renderFeedStatus("Não foi possível atualizar a edição.");
  setupReveal();
  // Inner pages link to /#subscrever; land on the form once the lead has rendered.
  if (window.location.hash === "#subscrever") focusSignupForm();
  // ptia.pt/newsletter (Instagram bio) lands on #newsletter; sections rendered above it move the
  // browser's initial anchor jump, so anchor again once the page is complete.
  if (window.location.hash === "#newsletter") {
    document.getElementById("newsletter")?.scrollIntoView({ behavior: "instant", block: "start" });
  }
}

initializeSite();
setInterval(async () => {
  const hydrated = await hydrateFromFeedIfAvailable();
  if (!hydrated && !PTIA_DATA.today.length && !hasFrontSnapshot()) {
    renderFeedStatus("Não foi possível atualizar a edição.");
  }
}, 60000);

// Navegação Dinâmica de Categorias (SPA Routing)
window.selectCategory = function(name) {
  activeFilter = name;
  renderFilters();
  renderArticles();
  document.getElementById("filterbar")?.scrollIntoView({ behavior: "smooth", block: "center" });
};

function handleHashChange() {
  const hash = window.location.hash.substring(1).toLowerCase();
  const sectionMap = {
    "mundo": "Mundo",
    "portugal": "Portugal",
    "builders": "Builders",
    "regulacao": "Regulação",
    "historias-reais": "Histórias reais",
    "previsoes-futuras": "Previsões Futuras"
  };
  const categoryName = sectionMap[hash];
  if (categoryName) {
    activeFilter = categoryName;
    renderFilters();
    renderArticles();
    // Pequeno delay no carregamento inicial para o DOM estabilizar
    setTimeout(() => {
      document.getElementById("filterbar")?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 100);
  } else if (hash === "hoje" || !hash) {
    activeFilter = "Todos";
    renderFilters();
    renderArticles();
    if (hash === "hoje") {
      setTimeout(() => {
        document.getElementById("hoje")?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    }
  }
}

window.addEventListener("hashchange", handleHashChange);
// Executar no arranque
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", handleHashChange);
} else {
  handleHashChange();
}

// Intercept clicks on links globally to handle SPA routing smoothly and avoid jumps
document.addEventListener("click", function(e) {
  const link = e.target.closest("a");
  if (!link) return;
  
  const href = link.getAttribute("href");
  if (!href || !href.startsWith("#")) return;
  
  const hash = href.substring(1).toLowerCase();
  
  const sectionMap = {
    "mundo": "Mundo",
    "portugal": "Portugal",
    "builders": "Builders",
    "regulacao": "Regulação",
    "historias-reais": "Histórias reais",
    "previsoes-futuras": "Previsões Futuras"
  };
  
  const categoryName = sectionMap[hash];
  if (categoryName) {
    e.preventDefault();
    window.selectCategory(categoryName);
    history.pushState(null, null, `#${hash}`);
    return;
  }
  
  if (hash === "subscrever" && focusSignupForm()) {
    e.preventDefault();
    history.pushState(null, null, "#subscrever");
    return;
  }

  if (hash === "hoje") {
    e.preventDefault();
    activeFilter = "Todos";
    renderFilters();
    renderArticles();
    document.getElementById("hoje")?.scrollIntoView({ behavior: "smooth" });
    history.pushState(null, null, "#hoje");
    return;
  }
  
  // For other internal anchors, perform smooth scroll and update URL hash without jump
  const targetId = hash === "top" ? "top" : href.substring(1);
  const targetEl = document.getElementById(targetId) || document.getElementsByName(targetId)[0];
  if (targetEl) {
    e.preventDefault();
    targetEl.scrollIntoView({ behavior: "smooth" });
    history.pushState(null, null, href);
  }
});

function setupMobileMenu() {
  const toggle = document.querySelector(".mobile-menu-toggle");
  const backdrop = document.querySelector(".mobile-menu-backdrop");
  const menu = document.getElementById("mobile-menu");
  const closeButton = document.querySelector(".mobile-menu-close");
  if (!toggle || !backdrop || !menu || !closeButton) return;

  const closeMenu = () => {
    backdrop.classList.remove("is-open");
    backdrop.setAttribute("aria-hidden", "true");
    menu.setAttribute("aria-hidden", "true");
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("mobile-menu-open");
  };
  const openMenu = () => {
    backdrop.classList.add("is-open");
    backdrop.setAttribute("aria-hidden", "false");
    menu.setAttribute("aria-hidden", "false");
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("mobile-menu-open");
    closeButton.focus();
  };

  toggle.addEventListener("click", openMenu);
  closeButton.addEventListener("click", closeMenu);
  menu.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && backdrop.classList.contains("is-open")) {
      closeMenu();
      toggle.focus();
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", setupMobileMenu);
} else {
  setupMobileMenu();
}
