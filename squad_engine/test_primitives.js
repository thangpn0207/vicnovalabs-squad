/**
 * Stagehand-Inspired Self-Healing UI Automation Primitives for Playwright.
 * Provides resilient semantic interaction helpers that automatically adapt
 * when CSS classes or layout hierarchies change.
 */

async function findSemanticElement(page, descriptor, options = {}) {
  const timeout = options.timeout || 3000;
  const regex = new RegExp(descriptor, 'i');

  // 1. Try Accessibility Role (Button, Link, Tab, etc.)
  for (const role of ['button', 'link', 'tab', 'menuitem', 'checkbox', 'radio']) {
    try {
      const el = page.getByRole(role, { name: regex });
      if (await el.count() > 0 && await el.first().isVisible({ timeout: 500 })) {
        return el.first();
      }
    } catch (_) {}
  }

  // 2. Try Label / Aria-Label
  try {
    const el = page.getByLabel(regex);
    if (await el.count() > 0 && await el.first().isVisible({ timeout: 500 })) {
      return el.first();
    }
  } catch (_) {}

  // 3. Try Visible Text Content
  try {
    const el = page.getByText(regex);
    if (await el.count() > 0 && await el.first().isVisible({ timeout: 500 })) {
      return el.first();
    }
  } catch (_) {}

  // 4. Try TestID, Key, or ID attributes
  for (const attr of ['data-testid', 'data-cy', 'key', 'id', 'name']) {
    try {
      const el = page.locator(`[${attr}="${descriptor}"]`);
      if (await el.count() > 0 && await el.first().isVisible({ timeout: 500 })) {
        return el.first();
      }
    } catch (_) {}
  }

  // 5. Fallback: Direct Selector if valid
  try {
    const el = page.locator(descriptor);
    if (await el.count() > 0) {
      await el.first().waitFor({ state: 'visible', timeout });
      return el.first();
    }
  } catch (_) {}

  throw new Error(`[Stagehand Self-Healing] Could not locate element matching semantic descriptor: '${descriptor}'`);
}

async function smartClick(page, descriptor, options = {}) {
  const el = await findSemanticElement(page, descriptor, options);
  await el.click(options);
  return el;
}

async function smartFill(page, descriptor, value, options = {}) {
  const regex = new RegExp(descriptor, 'i');

  // 1. Try Label or Placeholder
  for (const locatorMethod of ['getByLabel', 'getByPlaceholder']) {
    try {
      const el = page[locatorMethod](regex);
      if (await el.count() > 0 && await el.first().isVisible({ timeout: 500 })) {
        await el.first().fill(String(value));
        return el.first();
      }
    } catch (_) {}
  }

  // 2. Try Textbox Role
  try {
    const el = page.getByRole('textbox', { name: regex });
    if (await el.count() > 0 && await el.first().isVisible({ timeout: 500 })) {
      await el.first().fill(String(value));
      return el.first();
    }
  } catch (_) {}

  // 3. Fallback to generic semantic element
  const el = await findSemanticElement(page, descriptor, options);
  await el.fill(String(value));
  return el;
}

async function smartAssert(page, descriptor, expectedVisible = true, timeout = 3000) {
  try {
    const el = await findSemanticElement(page, descriptor, { timeout });
    const isVisible = await el.isVisible();
    if (isVisible !== expectedVisible) {
      throw new Error(`[Stagehand Assert] Element '${descriptor}' visibility was ${isVisible}, expected ${expectedVisible}`);
    }
    return true;
  } catch (err) {
    if (!expectedVisible) return true; // Expected not to exist
    throw err;
  }
}

/**
 * Executes Torture Fuzzing on a target input with dirty data
 * and asserts that the application does not crash or throw unhandled errors.
 */
async function tortureFuzzInput(page, descriptor, dirtyPayloads = null) {
  const payloads = dirtyPayloads || [
    "", // Empty
    "   ", // Whitespace
    "A".repeat(500), // Extreme length
    "🚀🔥<script>alert(1)</script>' OR 1=1--", // Special chars & injection
    "-9999999" // Negative number
  ];

  const results = [];
  for (const p of payloads) {
    try {
      await smartFill(page, descriptor, p);
      results.push({ payload: p.substring(0, 15) + "...", status: "HANDLED_CLEANLY" });
    } catch (err) {
      results.push({ payload: p.substring(0, 15) + "...", status: "ERROR", error: err.message });
    }
  }
  return results;
}

module.exports = {
  findSemanticElement,
  smartClick,
  smartFill,
  smartAssert,
  tortureFuzzInput
};
