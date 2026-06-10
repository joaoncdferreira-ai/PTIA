const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
const postUrl = "https://www.linkedin.com/feed/update/urn:li:activity:7468064784647602176";

async function run() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  try {
    console.log(`Navigating to ${postUrl}...`);
    await page.goto(postUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(5000);
    
    // Auto-scroll slightly
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(2000);

    let actorBtn = null;
    const actorSelectors = [
      "[aria-label*='Mudar de conta']",
      "[aria-label*='mudar de conta']",
      "[aria-label*='Mudar a conta']",
      "[aria-label*='mudar a conta']",
      "[aria-label*='Change account']",
      "[aria-label*='change account']",
      "[aria-label*='Switch account']",
      "[aria-label*='switch account']",
      "[aria-label*='Change member']",
      "[aria-label*='Switch member']",
      "[aria-label*='comentar como']",
      "[aria-label*='Publicando como']",
      "[aria-label*='Posting as']",
      "[aria-label*='commenting as']",
      "button.comments-select-actor-button",
      "button.comments-comment-box__select-active-actor-button"
    ];

    for (const sel of actorSelectors) {
      const el = page.locator(sel).first();
      if (await el.count() > 0 && await el.isVisible()) {
        console.log(`FOUND actorBtn using selector: ${sel}`);
        actorBtn = el;
        break;
      }
    }

    if (actorBtn) {
      console.log("Clicking actorBtn...");
      await actorBtn.click();
      await page.waitForTimeout(3000);
      
      const screenshotPath = "C:/Users/joaon/ptia-content-engine/.tmp/actor-clicked-test.png";
      await page.screenshot({ path: screenshotPath });
      console.log(`Screenshot saved to ${screenshotPath}`);

      // Inspect elements in the opened modal/dropdown
      const menuText = await page.evaluate(() => {
        const textElements = Array.from(document.querySelectorAll("[role='menuitem'], [role='radio'], [role='option'], button, li, label, .actor-toggle"));
        return textElements.map(el => ({
          text: el.innerText ? el.innerText.trim() : "",
          tag: el.tagName.toLowerCase(),
          role: el.getAttribute("role") || "",
          className: el.className
        })).filter(item => item.text.length > 0);
      });
      console.log("Found dropdown/modal items:", JSON.stringify(menuText.slice(0, 15), null, 2));

    } else {
      console.log("ERROR: actorBtn NOT found with any selector!");
    }

  } catch (err) {
    console.error("Error during script execution:", err);
  } finally {
    await context.close();
  }
}

run();
