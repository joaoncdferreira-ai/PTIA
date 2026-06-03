const { chromium } = require("playwright");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";

async function run() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
  });
  const page = context.pages()[0] || await context.newPage();
  
  try {
    await page.goto("https://www.linkedin.com/search/results/content/?keywords=AI%20Portugal&sortBy=%22date_posted%22");
    await page.waitForTimeout(5000);
    
    const res = await page.evaluate(() => {
      const results = [];
      // Find all update cards or potential cards
      const elements = document.querySelectorAll(".reusable-search__result-container, .feed-shared-update-v2, .feed-shared-update, [data-urn]");
      for (const el of elements) {
        results.push({
          tagName: el.tagName,
          className: el.className,
          urn: el.getAttribute("data-urn") || "",
          textPreview: el.innerText ? el.innerText.substring(0, 100).replace(/\n/g, " ") : ""
        });
      }
      return results;
    });
    
    console.log(JSON.stringify(res, null, 2));
  } catch (err) {
    console.error(err);
  } finally {
    await context.close();
  }
}

run();
