const { chromium } = require("playwright");

async function test() {
  const context = await chromium.launchPersistentContext("C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin", {
    headless: true,
  });
  const page = context.pages()[0] || await context.newPage();
  try {
    const query = "Fundação Champalimaud";
    const searchUrl = `https://www.linkedin.com/search/results/all/?keywords=${encodeURIComponent(query)}`;
    console.log("Navigating to:", searchUrl);
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(6000);
    
    // Save diagnostic screenshot
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/champalimaud-search-all.png" });
    
    const html = await page.content();
    console.log("HTML length:", html.length);
    
    const resolved = await page.evaluate(() => {
      const results = [];
      const links = Array.from(document.querySelectorAll("a"));
      for (const link of links) {
        const href = link.href || "";
        if (href.includes("/company/")) {
          results.push(href);
        }
      }
      return results;
    });
    console.log("Resolved links:", resolved);
  } catch (err) {
    console.error("Error:", err.message);
  } finally {
    await context.close();
  }
}
test();
