const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
const postUrl = "https://www.linkedin.com/feed/update/urn:li:activity:7468064784647602176";

async function inspect() {
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

    const htmlContent = await page.evaluate(() => {
      const container = document.querySelector("div[class*='ca13589c']");
      if (!container) return "Container ca13589c not found";
      
      return {
        outerHTML: container.outerHTML
      };
    });

    console.log("Container HTML:");
    console.log(JSON.stringify(htmlContent, null, 2));

  } catch (err) {
    console.error("Error during inspection:", err);
  } finally {
    await context.close();
  }
}

inspect();
