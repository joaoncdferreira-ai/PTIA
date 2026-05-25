const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[char]));
}

function setupDateline() {
  const dateEl = document.getElementById("date-long");
  const clockEl = document.getElementById("clock");
  const yearEl = document.getElementById("year");
  const update = () => {
    const now = new Date();
    if (dateEl) {
      dateEl.textContent = new Intl.DateTimeFormat("pt-PT", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric"
      }).format(now);
    }
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

function formatDate(value) {
  if (!value) return "data indisponivel";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "data indisponivel";
  return new Intl.DateTimeFormat("pt-PT", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function isPublishedNow(value) {
  if (!value) return true;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return true;
  return date.getTime() <= Date.now();
}

function sourceLabel(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch (_) {
    return "fonte original";
  }
}

function readingMinutes(text) {
  const words = String(text || "").trim().split(/\s+/).filter(Boolean).length;
  return `${Math.max(2, Math.ceil(words / 210))} min`;
}

function absoluteUrl(pathOrUrl) {
  if (!pathOrUrl) return window.location.origin + window.location.pathname;
  try {
    return new URL(pathOrUrl, window.location.origin).href;
  } catch (_) {
    return window.location.href;
  }
}

function articleCanonicalUrl(post) {
  if (post.article_url) return absoluteUrl(`/${String(post.article_url).replace(/^\/+/, "")}`);
  return window.location.href;
}

function articleExcerpt(body, max = 165) {
  const clean = cleanedParagraphs(body).join(" ").replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  return `${clean.slice(0, max - 1).split(" ").slice(0, -1).join(" ").replace(/[ .,:;]+$/, "")}...`;
}

function upsertMeta(selector, attributes) {
  let node = document.head.querySelector(selector);
  if (!node) {
    node = document.createElement(attributes.tag || "meta");
    document.head.appendChild(node);
  }
  Object.entries(attributes).forEach(([key, value]) => {
    if (key !== "tag") node.setAttribute(key, value);
  });
}

function updateArticleMeta(post, section, sourceUrls) {
  const title = `${post.title || "PTIA"} - PTIA.pt`;
  const description = articleExcerpt(post.body);
  const canonical = articleCanonicalUrl(post);
  const image = post.image_url ? absoluteUrl(post.image_url) : "";
  document.title = title;
  upsertMeta("meta[name='description']", { name: "description", content: description });
  upsertMeta("link[rel='canonical']", { tag: "link", rel: "canonical", href: canonical });
  upsertMeta("meta[property='og:title']", { property: "og:title", content: title });
  upsertMeta("meta[property='og:description']", { property: "og:description", content: description });
  upsertMeta("meta[property='og:url']", { property: "og:url", content: canonical });
  upsertMeta("meta[name='twitter:title']", { name: "twitter:title", content: title });
  upsertMeta("meta[name='twitter:description']", { name: "twitter:description", content: description });
  if (image) {
    upsertMeta("meta[property='og:image']", { property: "og:image", content: image });
    upsertMeta("meta[name='twitter:image']", { name: "twitter:image", content: image });
  }
  const schema = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: post.title || "PTIA",
    description,
    datePublished: post.published_at || "",
    author: { "@type": "Person", name: "João Ferreira" },
    publisher: {
      "@type": "Organization",
      name: "PTIA.pt",
      url: window.location.origin,
      logo: absoluteUrl("/assets/ptia-wordmark-navy-transparent.png")
    },
    mainEntityOfPage: canonical,
    image: image ? [image] : [],
    articleSection: section,
    isAccessibleForFree: true,
    citation: sourceUrls
  };
  let jsonLd = document.getElementById("article-jsonld");
  if (!jsonLd) {
    jsonLd = document.createElement("script");
    jsonLd.id = "article-jsonld";
    jsonLd.type = "application/ld+json";
    document.head.appendChild(jsonLd);
  }
  jsonLd.textContent = JSON.stringify(schema);
}

function cleanedParagraphs(body) {
  return String(body || "")
    .split(/\n\s*\n/g)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .filter((paragraph) => !/^fonte(?:\s+original)?\s*:/i.test(paragraph));
}

function articleVisual(post) {
  if (post.image_url) {
    return `<figure class="article-hero-image"><img src="${escapeHtml(post.image_url)}" alt="" loading="eager"></figure>`;
  }
  const rings = Array.from({ length: 22 }, (_, index) => {
    const r = 18 + index * 18;
    const opacity = Math.max(0.025, 0.2 - index * 0.007);
    return `<circle cx="50%" cy="50%" r="${r}" fill="none" stroke="#fff" stroke-opacity="${opacity}" stroke-width="1"/>`;
  }).join("");
  return `<div class="article-hero-image article-placeholder" aria-hidden="true"><svg viewBox="0 0 720 420">${rings}</svg></div>`;
}

async function loadFeed() {
  for (const url of ["site-feed.json", "/api/site-feed"]) {
    const response = await fetch(url, { cache: "no-store" });
    if (response.ok) return response.json();
  }
  throw new Error("feed indisponivel");
}

function renderNotFound() {
  const loading = document.getElementById("article-loading");
  if (!loading) return;
  loading.innerHTML = `
    <p class="eyebrow">PTIA</p>
    <h1>Noticia nao encontrada.</h1>
    <p class="article-error">Esta entrada ja nao esta no feed publico ou o link esta incompleto.</p>
    <a class="article-back" href="./">Voltar ao site</a>
  `;
}

function renderArticle(post) {
  const detail = document.getElementById("article-detail");
  const loading = document.getElementById("article-loading");
  if (!detail) return;

  const sourceUrls = Array.isArray(post.source_urls) ? post.source_urls.filter(Boolean) : [];
  const paragraphs = cleanedParagraphs(post.body);
  const firstSource = sourceUrls[0] || "";
  const section = post.section || "Mundo";
  updateArticleMeta(post, section, sourceUrls);

  detail.innerHTML = `
    <div class="wrap article-shell">
      <aside class="article-side">
        <a class="article-back" href="./">Voltar ao radar</a>
        <dl>
          <div><dt>Seccao</dt><dd>${escapeHtml(section)}</dd></div>
          <div><dt>Leitura</dt><dd>${escapeHtml(readingMinutes(post.body))}</dd></div>
          <div><dt>Publicado</dt><dd>${escapeHtml(formatDate(post.published_at))}</dd></div>
          <div><dt>Fonte</dt><dd>${escapeHtml(firstSource ? sourceLabel(firstSource) : "PTIA")}</dd></div>
        </dl>
      </aside>
      <div class="article-story">
        <header class="article-hero">
          <p class="article-kicker">${escapeHtml(section)} · Angulo PTIA</p>
          <h1>${escapeHtml(post.title || "Entrada PTIA")}</h1>
          ${articleVisual(post)}
        </header>
        <section class="article-body">
          ${paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
        </section>
        <footer class="article-source-block">
          <p>Fonte original</p>
          ${sourceUrls.length ? sourceUrls.map((url) => `
            <a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(sourceLabel(url))}<span>${escapeHtml(url)}</span></a>
          `).join("") : "<span>Sem link publico associado.</span>"}
        </footer>
      </div>
    </div>
  `;
  loading?.classList.add("hidden");
  detail.classList.remove("hidden");
}

async function initArticle() {
  setupDateline();
  setupTheme();
  try {
    const params = new URLSearchParams(window.location.search);
    const id = params.get("id") || "";
    const cleanPath = window.location.pathname.replace(/^\/+/, "").replace(/\/+$/, "");
    const feed = await loadFeed();
    const post = (feed.posts || []).find((item) => (
      item.id === id
      || String(item.article_url || "").replace(/^\/+/, "").replace(/\/+$/, "") === cleanPath
    ) && isPublishedNow(item.published_at));
    if (!post) {
      renderNotFound();
      return;
    }
    renderArticle(post);
  } catch (_) {
    renderNotFound();
  }
}

initArticle();
