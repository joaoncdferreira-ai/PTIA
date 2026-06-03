const { chromium } = require("playwright");

async function test() {
  console.log("Launching browser context...");
  const context = await chromium.launchPersistentContext("C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin", {
    headless: false, // Let's run headful so we can see what's happening and check diagnostic screenshots
    viewport: { width: 1280, height: 800 },
  });
  const page = context.pages()[0] || await context.newPage();
  try {
    const query = "Unbabel";
    const searchUrl = `https://www.linkedin.com/search/results/companies/?keywords=${encodeURIComponent(query)}`;
    console.log("Navigating to:", searchUrl);
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
    
    console.log("Waiting for results to load...");
    await page.waitForTimeout(6000);
    
    // Save diagnostic screenshot
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/search-linkedin-test.png" });
    console.log("Diagnostic screenshot saved.");
    
    const html = await page.content();
    console.log("HTML length:", html.length);
    
    const resolved = await page.evaluate(() => {
      const results = [];
      const elements = Array.from(document.querySelectorAll("[data-urn], a"));
      for (const el of elements) {
        const urn = el.getAttribute("data-urn") || "";
        if (urn.includes("fs_miniCompany:")) {
          results.push({ type: "urn", value: urn });
        }
        const href = el.href || "";
        if (href.includes("linkedin.com/company/")) {
          results.push({ type: "link", value: href });
        }
      }
      return results;
    });
    
    console.log("Resolved elements:", resolved.slice(0, 10));
    
  } catch (err) {
    console.error("Error:", err.message);
  } finally {
    await context.close();
  }
}
test();
