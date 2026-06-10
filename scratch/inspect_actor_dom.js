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

    const domStructure = await page.evaluate(() => {
      // Find the "Gostar" button first
      const buttons = Array.from(document.querySelectorAll("button"));
      const likeBtn = buttons.find(b => b.innerText && b.innerText.includes("Gostar"));
      if (!likeBtn) return { error: "Gostar button not found" };

      // Helper to serialize an element's basic details
      function serialize(el) {
        return {
          tag: el.tagName.toLowerCase(),
          className: el.className,
          id: el.id,
          text: el.innerText ? el.innerText.trim().slice(0, 30) : "",
          ariaLabel: el.getAttribute("aria-label") || "",
          role: el.getAttribute("role") || "",
          htmlSummary: el.outerHTML.slice(0, 150)
        };
      }

      // Trace parents up
      const parents = [];
      let curr = likeBtn;
      for (let i = 0; i < 6; i++) {
        if (!curr) break;
        const childrenInfo = Array.from(curr.children).map(c => serialize(c));
        parents.push({
          level: i,
          element: serialize(curr),
          children: childrenInfo
        });
        curr = curr.parentElement;
      }

      return { parents };
    });

    console.log("DOM Structure around Gostar button:");
    console.log(JSON.stringify(domStructure, null, 2));

  } catch (err) {
    console.error("Error during inspection:", err);
  } finally {
    await context.close();
  }
}

inspect();
