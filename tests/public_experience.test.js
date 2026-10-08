const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const siteDir = path.join(__dirname, "..", "site");

function loadPureFunctions(fileName, stopAt) {
  const source = fs.readFileSync(path.join(siteDir, fileName), "utf8");
  const code = source.slice(0, source.indexOf(stopAt));
  const document = {
    createElement() {
      return {
        value: "",
        textContent: "",
        set innerHTML(value) {
          this.value = value;
          this.textContent = value;
        }
      };
    }
  };
  const context = vm.createContext({
    document,
    window: { matchMedia: () => ({ matches: false }), location: { origin: "https://ptia.pt", href: "https://ptia.pt/article.html" } },
    URL,
    Date,
    Intl,
    console
  });
  vm.runInContext(code, context, { filename: fileName });
  return context;
}

test("homepage excerpt ends before a long article body", () => {
  const context = loadPureFunctions("app.js", "initializeSite();");
  const body = `${"Uma frase sobre uma decisão real em Portugal. ".repeat(12)}\n\nDetalhe aprofundado.`;
  const result = vm.runInContext(`firstContentParagraph(${JSON.stringify(body)})`, context);
  assert.ok(result.length <= 221);
  assert.ok(result.endsWith("…"));
  assert.ok(!result.includes("Detalhe aprofundado"));
});

test("article related reading excludes future posts and unsafe paths", () => {
  const context = loadPureFunctions("article.js", "initArticle();");
  const current = { id: "a", title: "Atual", article_url: "artigos/atual", published_at: "2020-01-01T10:00:00Z", section: ["Portugal"] };
  const older = { id: "b", title: "Anterior", article_url: "artigos/anterior", published_at: "2020-01-01T09:00:00Z", section: ["Portugal"] };
  const future = { id: "c", title: "Futura", article_url: "artigos/futura", published_at: "2999-01-01T09:00:00Z", section: ["Portugal"] };
  const unsafe = { id: "d", title: "Insegura", article_url: "javascript:alert(1)", published_at: "2020-01-01T08:00:00Z", section: ["Portugal"] };
  context.posts = [current, older, future, unsafe];
  const result = vm.runInContext("relatedArticles(posts[0], posts)", context);
  assert.deepEqual(Array.from(result, (item) => item.id), ["b"]);
  assert.equal(vm.runInContext('safeHttpUrl("javascript:alert(1)")', context), "");
  assert.equal(vm.runInContext('safeHttpUrl("https://example.org/story")', context), "https://example.org/story");
});

test("newsletter uses native provider response with and without JavaScript", () => {
  for (const fileName of ["index.html", "article.html"]) {
    const html = fs.readFileSync(path.join(siteDir, fileName), "utf8");
    const form = html.match(/<form\s+id="ptia-newsletter-form"[\s\S]*?<\/form>/)?.[0];
    assert.ok(form, `${fileName} has a form`);
    assert.match(form, /action="https:\/\/[^" ]+\.sibforms\.com\/serve\//);
    assert.match(form, /method="post"/);
    assert.doesNotMatch(form, /target=|<iframe/);
    for (const name of ["EMAIL", "FIRSTNAME", "email_address_check", "locale"]) {
      assert.match(form, new RegExp(`name="${name}"`));
    }
    assert.match(form, /required/);
  }
  for (const fileName of ["app.js", "article.js"]) {
    const script = fs.readFileSync(path.join(siteDir, fileName), "utf8");
    assert.doesNotMatch(script, /form\.reset\(|newsletter-status|ptia-newsletter-frame/);
  }
});

test("analytics pageview omits full referrer, raw query, and email", async () => {
  const script = fs.readFileSync(path.join(siteDir, "analytics.js"), "utf8");
  let beacon;
  const navigator = { doNotTrack: "0", sendBeacon: (_endpoint, body) => { beacon = body; return true; } };
  const window = { doNotTrack: "0", location: {
    pathname: "/artigos/exemplo",
    search: "?utm_source=linkedin&utm_content=ana%40example.com&utm_campaign=weekly"
  } };
  const document = { referrer: "https://www.linkedin.com/feed/?email=ana%40example.com" };
  vm.runInNewContext(script, { navigator, window, document, URL, URLSearchParams, Blob });

  const payload = JSON.parse(await beacon.text());
  assert.equal(payload.path, "/artigos/exemplo");
  assert.equal(payload.referrer, "https://www.linkedin.com");
  assert.equal(payload.utm_source, "linkedin");
  assert.equal(payload.utm_campaign, "weekly");
  assert.equal(payload.utm_content, "");
  assert.ok(!JSON.stringify(payload).includes("ana@example.com"));
  assert.ok(!JSON.stringify(payload).includes("/feed/"));
  navigator.doNotTrack = "1";
  beacon = undefined;
  vm.runInNewContext(script, { navigator, window, document, URL, URLSearchParams, Blob });
  assert.equal(beacon, undefined);
});
