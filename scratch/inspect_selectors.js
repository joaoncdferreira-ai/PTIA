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

    // Let's dump all buttons in the social actions area
    const buttonsInfo = await page.evaluate(() => {
      const results = [];
      const buttons = Array.from(document.querySelectorAll("button"));
      for (const btn of buttons) {
        const text = btn.innerText ? btn.innerText.trim() : "";
        const ariaLabel = btn.getAttribute("aria-label") || "";
        const className = btn.className;
        const id = btn.id;
        
        // If button has caret, or user profile image, or text like Gostar, or classes containing actor/identity/profile
        if (
          text.includes("Gostar") || 
          text.includes("Comentar") || 
          ariaLabel.toLowerCase().includes("comentar") ||
          ariaLabel.toLowerCase().includes("gostar") ||
          ariaLabel.toLowerCase().includes("actor") ||
          ariaLabel.toLowerCase().includes("identidade") ||
          ariaLabel.toLowerCase().includes("como") ||
          className.includes("actor") ||
          className.includes("identity") ||
          btn.querySelector("img") ||
          btn.innerHTML.includes("svg")
        ) {
          // Let's get parent info
          const parent = btn.parentElement;
          results.push({
            tag: "button",
            id,
            className,
            text: text.slice(0, 50),
            ariaLabel,
            parentClass: parent ? parent.className : "",
            htmlSummary: btn.outerHTML.slice(0, 300)
          });
        }
      }
      return results;
    });

    console.log("Found buttons:", JSON.stringify(buttonsInfo, null, 2));

    // Try to find the button with caret next to "Gostar"
    console.log("Searching for the actor/identity selector button next to Like/Comment buttons...");
    
    // Let's take a screenshot after trying to hover/click the actor button
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/inspect-actor-button.png" });
    console.log("Diagnostic screenshot saved.");

  } catch (err) {
    console.error("Error during inspection:", err);
  } finally {
    await context.close();
  }
}

inspect();
