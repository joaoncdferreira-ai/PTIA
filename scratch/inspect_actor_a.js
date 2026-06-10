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

    const anchorDetails = await page.evaluate(() => {
      // Find the "Gostar" button first
      const buttons = Array.from(document.querySelectorAll("button"));
      const likeBtn = buttons.find(b => b.innerText && b.innerText.includes("Gostar"));
      if (!likeBtn) return { error: "Gostar button not found" };

      // Ancestor level 5
      const lvl1 = likeBtn.parentElement;
      const lvl2 = lvl1 ? lvl1.parentElement : null;
      const lvl3 = lvl2 ? lvl2.parentElement : null;
      const lvl4 = lvl3 ? lvl3.parentElement : null;
      const lvl5 = lvl4 ? lvl4.parentElement : null;

      if (!lvl5) return { error: "Level 5 ancestor not found" };

      // Find any <a> child of lvl5
      const anchors = Array.from(lvl5.querySelectorAll("a"));
      const details = anchors.map(a => {
        return {
          href: a.getAttribute("href") || "",
          className: a.className,
          outerHTML: a.outerHTML,
          text: a.innerText,
          ariaLabel: a.getAttribute("aria-label") || "",
          role: a.getAttribute("role") || "",
          imgCount: a.querySelectorAll("img").length,
          imgAlt: a.querySelector("img") ? a.querySelector("img").getAttribute("alt") : "",
          imgSrc: a.querySelector("img") ? a.querySelector("img").getAttribute("src") : ""
        };
      });

      return {
        lvl5_class: lvl5.className,
        lvl5_innerHTML: lvl5.innerHTML.slice(0, 1000),
        anchors: details
      };
    });

    console.log("Anchor details:");
    console.log(JSON.stringify(anchorDetails, null, 2));

  } catch (err) {
    console.error("Error during inspection:", err);
  } finally {
    await context.close();
  }
}

inspect();
