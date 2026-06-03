const { chromium } = require("playwright");
const fs = require("fs");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";

async function test() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  try {
    const searchUrl = "https://www.linkedin.com/search/results/content/?keywords=AI%20Portugal&sortBy=%22date_posted%22";
    console.log("Navigating to:", searchUrl);
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    
    await page.waitForTimeout(5000);
    
    // Auto-scroll
    await page.evaluate(() => window.scrollBy(0, 800));
    await page.waitForTimeout(2000);
    
    const posts = await page.evaluate(() => {
      const items = [];
      const cards = Array.from(document.querySelectorAll("div.feed-shared-update-v2, div.feed-shared-update, [data-urn], [role='listitem'], .reusable-search__result-container"));
      
      for (const card of cards) {
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
        if (!bodyText) continue;
        
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
        
        let postUrl = `https://www.linkedin.com/feed/update/${urn}`;
        
        if (!items.some(item => item.urn === urn)) {
          items.push({
            urn,
            url: postUrl,
            body: bodyText.substring(0, 100).replace(/\n/g, " "),
            relative_time: relativeTime,
            likes,
            comments
          });
        }
      }
      return items;
    });
    
    console.log("Extracted cards:", JSON.stringify(posts, null, 2));
  } catch (err) {
    console.error("Error:", err.message);
  } finally {
    await context.close();
  }
}

test();
