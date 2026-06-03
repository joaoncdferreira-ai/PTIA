const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";

async function scrapeProfile(profileUrl) {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false, // Headless false is required because LinkedIn redirects headless mode to login page
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  try {
    console.error(`-> Aceder a página de publicações de: ${profileUrl}`);
    // Navigate straight to the posts page (recent activity / company posts)
    let postsUrl = profileUrl.replace(/\/$/, "");
    if (profileUrl.includes("/company/")) {
      postsUrl += "/posts/?feedView=all";
    } else {
      postsUrl += "/recent-activity/all/";
    }
    await page.goto(postsUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    
    // Wait for the feed items to load
    await page.waitForTimeout(5000);
    
    // Dismiss cookie banner if present
    const cookieBtn = page.getByRole('button', { name: /Aceitar|Accept/i }).first();
    if (await cookieBtn.count() > 0 && await cookieBtn.isVisible()) {
      console.error("-> Cookie banner detetado. A aceitar cookies...");
      await cookieBtn.click();
      await page.waitForTimeout(1500);
    }
    
    // Save a diagnostic screenshot
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/scrape-profile-check.png" });
    console.error("-> Diagnostic screenshot saved to .tmp/scrape-profile-check.png");
    
    // Auto-scroll slightly to trigger lazy-loaded posts
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(2000);
    
    const posts = await page.evaluate(() => {
      const items = [];
      const cards = Array.from(document.querySelectorAll("div.feed-shared-update-v2, div.feed-shared-update, [data-urn], [role='listitem'], .reusable-search__result-container"));
      
      for (const card of cards) {
        if (items.length >= 3) break;
        
        let urn = card.getAttribute("data-urn") || "";
        if (!urn) {
          const html = card.outerHTML;
          const ugcMatch = html.match(/userGeneratedContentId[=\)]['"]?(\d+)['"]?/i) || html.match(/urn:li:\w+:(\d+)/i) || html.match(/urn%3Ali%3A\w+%3A(\d+)/i);
          if (ugcMatch) {
            urn = `urn:li:activity:${ugcMatch[1]}`;
          }
        }
        if (!urn) continue;
        
        // Find text body
        const textEl = card.querySelector(".feed-shared-update-v2__commentary, .break-words, .feed-shared-text, [data-view-name='feed-commentary'], [class*='update-v2__commentary']");
        const bodyText = textEl ? textEl.innerText.trim() : "";
        
        // Find relative time
        let relativeTime = "";
        const timeEl = card.querySelector(".feed-shared-actor__sub-description, .feed-shared-actor__meta, span.feed-shared-actor__sub-description, [class*='actor__sub-description']");
        if (timeEl) {
          relativeTime = timeEl.innerText.trim();
        } else {
          const allSpans = card.querySelectorAll("span, p, div");
          for (const s of allSpans) {
            const txt = s.innerText ? s.innerText.trim() : "";
            if (txt && txt.length < 50 && (txt.includes("•") || txt.includes("·"))) {
              if (/\b\d+\s*(min|h|d|dia|hora|semana|mês|ano|month|week|day|year|s|mo|yr|w|ago)\b/i.test(txt)) {
                relativeTime = txt;
                break;
              }
            }
          }
        }
        
        // Find reactions/likes count
        const reactionsEl = card.querySelector(".social-details-social-counts__reactions, .social-details-social-counts__reactions-count, button[aria-label*='reac'], button[aria-label*='like'], [class*='social-counts__reactions'], [data-view-name*='social-counts']");
        let likes = 0;
        if (reactionsEl) {
          const cleanTxt = reactionsEl.innerText.replace(/[^0-9]/g, "");
          if (cleanTxt) likes = parseInt(cleanTxt, 10);
        }
        
        // Find comments count
        const commentsEl = card.querySelector(".social-details-social-counts__comments, button[aria-label*='coment'], button[aria-label*='comment'], [class*='social-counts__comments']");
        let comments = 0;
        if (commentsEl) {
          const cleanTxt = commentsEl.innerText.replace(/[^0-9]/g, "");
          if (cleanTxt) comments = parseInt(cleanTxt, 10);
        }
        
        // Generate direct link
        let postUrl = "";
        if (urn.includes("activity:")) {
          const activityId = urn.split("activity:")[1];
          postUrl = `https://www.linkedin.com/feed/update/urn:li:activity:${activityId}`;
        } else {
          postUrl = `https://www.linkedin.com/feed/update/${urn}`;
        }
        
        if (bodyText && !items.some(item => item.urn === urn)) {
          items.push({
            urn,
            url: postUrl,
            body: bodyText,
            relative_time: relativeTime,
            likes,
            comments
          });
        }
      }
      return items;
    });
    
    console.log(JSON.stringify({ ok: true, posts }));
  } catch (err) {
    console.error("ERROR in scrapeProfile:", err.message);
    console.log(JSON.stringify({ ok: false, error: err.message }));
  } finally {
    await context.close();
  }
}

async function scrapeSearch(keywords) {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  try {
    const encoded = encodeURIComponent(keywords);
    const searchUrl = `https://www.linkedin.com/search/results/content/?keywords=${encoded}&sortBy=%22date_posted%22`;
    console.error(`-> Aceder a página de pesquisa de: ${searchUrl}`);
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    
    // Wait for the feed items to load
    await page.waitForTimeout(5000);
    
    // Save diagnostic screenshot
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/scrape-search-check.png" });
    console.error("-> Diagnostic screenshot saved to .tmp/scrape-search-check.png");
    
    // Dismiss cookie banner if present
    const cookieBtn = page.getByRole('button', { name: /Aceitar|Accept/i }).first();
    if (await cookieBtn.count() > 0 && await cookieBtn.isVisible()) {
      console.error("-> Cookie banner detetado. A aceitar cookies...");
      await cookieBtn.click();
      await page.waitForTimeout(1500);
    }
    
    // Auto-scroll slightly to trigger lazy-loaded posts
    await page.evaluate(() => window.scrollBy(0, 800));
    await page.waitForTimeout(2000);
    
    const posts = await page.evaluate(() => {
      const items = [];
      const cards = Array.from(document.querySelectorAll("div.feed-shared-update-v2, div.feed-shared-update, [data-urn], [role='listitem'], .reusable-search__result-container"));
      
      for (const card of cards) {
        if (items.length >= 10) break; // Fetch up to 10 candidates for search results
        
        let urn = card.getAttribute("data-urn") || "";
        if (!urn) {
          const html = card.outerHTML;
          const ugcMatch = html.match(/userGeneratedContentId[=\)]['"]?(\d+)['"]?/i) || html.match(/urn:li:\w+:(\d+)/i) || html.match(/urn%3Ali%3A\w+%3A(\d+)/i);
          if (ugcMatch) {
            urn = `urn:li:activity:${ugcMatch[1]}`;
          }
        }
        if (!urn) continue;
        
        // Find text body
        const textEl = card.querySelector(".feed-shared-update-v2__commentary, .break-words, .feed-shared-text, [data-view-name='feed-commentary'], [class*='update-v2__commentary']");
        const bodyText = textEl ? textEl.innerText.trim() : "";
        
        // Find relative time
        let relativeTime = "";
        const timeEl = card.querySelector(".feed-shared-actor__sub-description, .feed-shared-actor__meta, span.feed-shared-actor__sub-description, [class*='actor__sub-description']");
        if (timeEl) {
          relativeTime = timeEl.innerText.trim();
        } else {
          const allSpans = card.querySelectorAll("span, p, div");
          for (const s of allSpans) {
            const txt = s.innerText ? s.innerText.trim() : "";
            if (txt && txt.length < 50 && (txt.includes("•") || txt.includes("·"))) {
              if (/\b\d+\s*(min|h|d|dia|hora|semana|mês|ano|month|week|day|year|s|mo|yr|w|ago)\b/i.test(txt)) {
                relativeTime = txt;
                break;
              }
            }
          }
        }
        
        // Find reactions/likes count
        const reactionsEl = card.querySelector(".social-details-social-counts__reactions, .social-details-social-counts__reactions-count, button[aria-label*='reac'], button[aria-label*='like'], [class*='social-counts__reactions'], [data-view-name*='social-counts']");
        let likes = 0;
        if (reactionsEl) {
          const cleanTxt = reactionsEl.innerText.replace(/[^0-9]/g, "");
          if (cleanTxt) likes = parseInt(cleanTxt, 10);
        }
        
        // Find comments count
        const commentsEl = card.querySelector(".social-details-social-counts__comments, button[aria-label*='coment'], button[aria-label*='comment'], [class*='social-counts__comments']");
        let comments = 0;
        if (commentsEl) {
          const cleanTxt = commentsEl.innerText.replace(/[^0-9]/g, "");
          if (cleanTxt) comments = parseInt(cleanTxt, 10);
        }
        
        // Generate direct link
        let postUrl = "";
        if (urn.includes("activity:")) {
          const activityId = urn.split("activity:")[1];
          postUrl = `https://www.linkedin.com/feed/update/urn:li:activity:${activityId}`;
        } else {
          postUrl = `https://www.linkedin.com/feed/update/${urn}`;
        }
        
        if (bodyText && !items.some(item => item.urn === urn)) {
          items.push({
            urn,
            url: postUrl,
            body: bodyText,
            relative_time: relativeTime,
            likes,
            comments
          });
        }
      }
      return items;
    });
    
    console.log(JSON.stringify({ ok: true, posts }));
  } catch (err) {
    console.error("ERROR in scrapeSearch:", err.message);
    console.log(JSON.stringify({ ok: false, error: err.message }));
  } finally {
    await context.close();
  }
}

async function postComment(postUrl, commentText, isDraft = false) {
  // Headless false is safer for posting to ensure mouse interactions work and bypass bot detection!
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  try {
    console.error(`-> Aceder ao post do LinkedIn: ${postUrl}`);
    await page.goto(postUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    
    await page.waitForTimeout(4000);
    
    // Dismiss cookie banner if present
    const cookieBtn = page.getByRole('button', { name: /Aceitar|Accept/i }).first();
    if (await cookieBtn.count() > 0 && await cookieBtn.isVisible()) {
      console.error("-> Cookie banner detetado. A aceitar cookies...");
      await cookieBtn.click();
      await page.waitForTimeout(1500);
    }
    
    // Scroll down slightly to trigger lazy-loaded comment section
    console.error("-> Fazer scroll para acionar secção de comentários...");
    await page.evaluate(() => window.scrollBy(0, 500));
    await page.waitForTimeout(2000);
    
    // Find comment box or click trigger
    console.error("-> Procurar caixa de comentários...");
    const commentBoxSelector = ".ql-editor, [role='textbox'], .comments-comment-box__editor";
    
    // Check if the comment box is already visible
    const commentBox = page.locator(commentBoxSelector).first();
    if (await commentBox.count() === 0 || !(await commentBox.isVisible())) {
      console.error("-> Caixa de comentários não está visível. Procurar botão de acionar comentário (Comentar/Comment)...");
      const commentTriggerSelector = "button.comment-button, button.comments-comment-box-trigger, button[aria-label*='comentar'], button[aria-label*='comment'], button[aria-label*='Comment']";
      const triggerBtn = page.locator(commentTriggerSelector).first();
      
      if (await triggerBtn.count() > 0 && await triggerBtn.isVisible()) {
        console.error("-> Botão de acionar comentário encontrado! A clicar...");
        await triggerBtn.scrollIntoViewIfNeeded();
        await triggerBtn.click();
        await page.waitForTimeout(2000);
      } else {
        // Fallback using getByRole
        const roleBtn = page.getByRole('button', { name: /comentar|comment/i }).first();
        if (await roleBtn.count() > 0 && await roleBtn.isVisible()) {
          console.error("-> Botão de acionar comentário encontrado por Role! A clicar...");
          await roleBtn.scrollIntoViewIfNeeded();
          await roleBtn.click();
          await page.waitForTimeout(2000);
        } else {
          console.error("-> AVISO: Botão de acionar comentário não encontrado. A tentar aguardar pela caixa diretamente...");
        }
      }
    }
    
    await page.waitForSelector(commentBoxSelector, { timeout: 15000 });
    
    const editor = page.locator(commentBoxSelector).first();
    await editor.click();
    await page.waitForTimeout(1000);
    
    // Switch active identity (actor) to PTIA if necessary
    console.error("-> Verificar identidade de publicação (PTIA vs Pessoal)...");
    let actorBtn = null;
    const likeBtn = page.locator("button").filter({ hasText: "Gostar" }).first();
    if (await likeBtn.count() > 0 && await likeBtn.isVisible()) {
      const container = likeBtn.locator("xpath=ancestor::div[contains(@class, 'eba433ab')]").first();
      const avatar = container.locator("img").first();
      if (await avatar.count() > 0 && await avatar.isVisible()) {
        console.error("-> Encontrado avatar do utilizador na barra de ações. A usar como seletor de identidade.");
        actorBtn = avatar;
      }
    }
    
    if (!actorBtn) {
      const actorBtnSelector = "button.comments-select-actor-button, button.comments-comment-box__select-active-actor-button, .comments-comment-box__actor-container button, button[aria-label*='comentar como'], button[aria-label*='commenting as'], button[aria-label*='Posting as'], button[aria-label*='Publicando como']";
      const legacyBtn = page.locator(actorBtnSelector).first();
      if (await legacyBtn.count() > 0 && await legacyBtn.isVisible()) {
        console.error("-> Encontrado seletor de identidade legado.");
        actorBtn = legacyBtn;
      }
    }
    
    if (actorBtn) {
      console.error("-> A clicar no seletor de identidade...");
      await actorBtn.click();
      await page.waitForTimeout(2000);
      
      // Find PTIA option in the dropdown/modal
      const ptiaOptionSelector = "[role='menuitem'], [role='radio'], [role='option'], button, li, label, .actor-toggle";
      const ptiaOption = page.locator(ptiaOptionSelector).filter({ hasText: "PTIA" }).first();
      
      if (await ptiaOption.count() > 0) {
        console.error("-> Opção PTIA encontrada! A clicar...");
        await ptiaOption.click();
        await page.waitForTimeout(1000);
        
        // Look for any Done / Save / Guardar / Salvar / Concluir button to confirm the choice
        const saveBtn = page.getByRole('button', { name: /Save|Done|Guardar|Salvar|Concluir/i });
        if (await saveBtn.count() > 0 && await saveBtn.isVisible()) {
          console.error("-> A clicar no botão de confirmar escolha (Salvar)...");
          await saveBtn.click();
          await page.waitForTimeout(1500);
        }
        console.error("-> Identidade PTIA selecionada com sucesso!");
      } else {
        console.error("-> AVISO: Opção 'PTIA' não encontrada na lista de identidades. Irá comentar com o perfil predefinido.");
        // If we clicked actorBtn to open dropdown, and didn't select, let's close it by clicking actorBtn or somewhere else
        // but typically clicking editor will close it anyway.
      }
    } else {
      console.error("-> Não foi encontrado o seletor de identidade. A comentar com o perfil predefinido.");
    }

    
    // Simulate realistic typing
    console.error("-> A digitar comentário de forma humana...");
    for (const char of commentText) {
      await editor.type(char, { delay: Math.floor(Math.random() * 40) + 20 }); // delay between 20ms and 60ms
    }
    
    await page.waitForTimeout(1500);
    
    if (isDraft) {
      console.error("-> [Draft Mode] Apenas a tirar screenshot sem publicar...");
      await page.waitForTimeout(2000);
      
      const tmpDir = path.join(__dirname, "../.tmp");
      if (!fs.existsSync(tmpDir)) {
        fs.mkdirSync(tmpDir, { recursive: true });
      }
      const screenshotPath = path.join(tmpDir, `comment-draft-${Date.now()}.png`);
      await page.screenshot({ path: screenshotPath });
      console.error(`-> Screenshot de rascunho gravado em: ${screenshotPath}`);
      
      console.log(JSON.stringify({ ok: true, screenshot: screenshotPath }));
      return;
    }
    
    // Find public button (Publicar)
    console.error("-> Procurar botão de Publicar...");
    const submitBtnSelector = "button.comments-comment-box__submit-button, button.comments-comment-box__submit-btn-container, button[type='submit']";
    await page.waitForSelector(submitBtnSelector, { timeout: 5000 });
    
    const submitBtn = page.locator(submitBtnSelector).first();
    await submitBtn.click();
    
    console.error("-> Comentário submetido!");
    await page.waitForTimeout(3000);
    
    // Take confirmation screenshot
    const tmpDir = path.join(__dirname, "../.tmp");
    if (!fs.existsSync(tmpDir)) {
      fs.mkdirSync(tmpDir, { recursive: true });
    }
    const screenshotPath = path.join(tmpDir, `comment-sent-${Date.now()}.png`);
    await page.screenshot({ path: screenshotPath });
    console.error(`-> Screenshot de verificação gravado em: ${screenshotPath}`);
    
    console.log(JSON.stringify({ ok: true, screenshot: screenshotPath }));
  } catch (err) {
    console.error("ERROR in postComment:", err.message);
    try {
      const tmpDir = path.join(__dirname, "../.tmp");
      if (!fs.existsSync(tmpDir)) {
        fs.mkdirSync(tmpDir, { recursive: true });
      }
      const errorScreenshotPath = path.join(tmpDir, `comment-error-${Date.now()}.png`);
      await page.screenshot({ path: errorScreenshotPath });
      console.error(`-> Error screenshot saved to: ${errorScreenshotPath}`);
    } catch (e) {
      console.error("Could not take error screenshot:", e.message);
    }
    console.log(JSON.stringify({ ok: false, error: err.message }));
  } finally {
    await context.close();
  }
}

// CLI Routing
const args = process.argv.slice(2);
const command = args[0];

if (command === "scrape-profile") {
  const profileUrl = args[1];
  if (!profileUrl) {
    console.log(JSON.stringify({ ok: false, error: "Falta URL do perfil" }));
    process.exit(1);
  }
  scrapeProfile(profileUrl);
} else if (command === "scrape-search") {
  const keywords = args[1];
  if (!keywords) {
    console.log(JSON.stringify({ ok: false, error: "Falta keywords de pesquisa" }));
    process.exit(1);
  }
  scrapeSearch(keywords);
} else if (command === "post-comment") {
  const postUrl = args[1];
  const commentText = args[2];
  const isDraft = args[3] === "draft";
  if (!postUrl || !commentText) {
    console.log(JSON.stringify({ ok: false, error: "Falta URL do post ou texto do comentário" }));
    process.exit(1);
  }
  postComment(postUrl, commentText, isDraft);
} else {
  console.log(JSON.stringify({ ok: false, error: "Comando desconhecido" }));
  process.exit(1);
}
