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
    
    // Save diagnostic screenshot
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/inspect-search-visible.png" });
    
    const res = await page.evaluate(() => {
      const results = [];
      
      // Look for ALL elements with data-urn
      const allDataUrn = document.querySelectorAll("[data-urn]");
      results.push(`Found ${allDataUrn.length} elements with data-urn`);
      for (const el of allDataUrn) {
        results.push(`data-urn: ${el.getAttribute("data-urn")}, tag: ${el.tagName}, class: ${el.className}`);
      }
      
      // Let's also look for elements containing post text
      const divs = document.querySelectorAll("div");
      let count = 0;
      for (const d of divs) {
        if (d.className && d.className.includes("update") || d.className.includes("search")) {
          if (count < 10) {
            results.push(`div.className: ${d.className}, innerText: ${d.innerText ? d.innerText.substring(0, 50) : ""}`);
            count++;
          }
        }
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
