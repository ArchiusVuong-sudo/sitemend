import { expect, type Page, test } from "@playwright/test";

const shots = process.env.SHOTS_DIR;

async function shot(page: Page, name: string) {
  if (!shots) return;
  await page.mouse.move(1430, 890);
  await page.waitForTimeout(400); // let hover and colour transitions settle
  await page.screenshot({ path: `${shots}/${name}.png` });
}

function nav(page: Page, name: string) {
  return page.getByRole("navigation").getByRole("link", { name, exact: true });
}

async function toast(page: Page, text: string | RegExp) {
  await expect(page.locator("[aria-live=polite]").getByText(text).first()).toBeVisible({ timeout: 60_000 });
}

test("scan, fix, approve, deploy, verify, revert and roll back", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("console", (msg) => msg.type() === "error" && errors.push(msg.text()));
  page.on("pageerror", (err) => errors.push(err.message));

  expect((await request.post("/api/site/reset")).ok()).toBeTruthy();

  // Overview: empty state, then a scan.
  await page.goto("/");
  await expect(page.getByText("Synthetic site and search data")).toBeVisible();
  await expect(page.getByText("No scan yet")).toBeVisible();
  await shot(page, "01-overview-empty");
  await page.getByRole("button", { name: "Run scan" }).first().click();
  await toast(page, /Scan finished: 27 issues on 12 pages/);
  await expect(page.locator("tbody tr")).toHaveCount(27);
  await page.locator("tbody tr").first().click();
  await expect(page.getByText("HTML evidence")).toBeVisible();
  await page.locator("tbody tr").first().locator("td").first().hover();
  await expect(page.getByRole("tooltip")).toContainText("impressions");
  await shot(page, "02-overview-scanned");

  // Settings: alt text on autopilot.
  await nav(page, "Settings").click();
  await page.getByRole("radiogroup", { name: "Alt text" }).getByRole("radio", { name: "Autopilot" }).click();
  await toast(page, "Alt text: Autopilot");
  await shot(page, "03-settings");

  // Fixes: generate, autopilot ships v1.
  await nav(page, "Fixes").click();
  await page.getByRole("button", { name: "Generate fixes" }).first().click();
  await toast(page, "Release v1 went out on autopilot");
  await expect(page.getByText("Writing", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/^Product: .+, \d+(\.\d+)? USD/).first()).toBeVisible();
  await shot(page, "04-fixes");

  // A meta description with a rejected first attempt.
  await page.getByRole("button", { name: /Meta description.*repotting-a-fern/ }).click();
  await expect(page.getByRole("dialog", { name: "Meta description" })).toBeVisible();
  await expect(page.getByText("Rejected").first()).toBeVisible();
  await expect(page.getByText(/claims not on the page: best/).first()).toBeVisible();
  await shot(page, "05-fix-drawer");
  await page.keyboard.press("Escape");

  // Edit a title: a failing edit, then a passing one, then approve.
  await page.getByRole("button", { name: /Title.*speckled-stoneware-mug/ }).click();
  const input = page.locator("#fix-text");
  await input.fill("Best Speckled Stoneware Mug | Mossgrove Clayworks");
  await expect(page.getByText(/Remove claims not on the page: best/)).toBeVisible();
  await input.fill("Speckled Stoneware Mug, Thrown by Hand | Mossgrove Clayworks");
  await page.getByRole("button", { name: "Save edit" }).click();
  await toast(page, "Saved. Every check passes");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await toast(page, "Approved");
  await page.keyboard.press("Escape");
  for (const section of ["Titles", "Meta descriptions"]) {
    const card = page.locator("div.rounded-xl", { has: page.getByRole("heading", { name: section, exact: true }) });
    await card.getByRole("button", { name: /Approve all \d+ passing/ }).click();
    await toast(page, /approved/);
  }

  // Deploy v2, compare origin and edge.
  await page.getByRole("button", { name: /^Deploy/ }).click();
  await toast(page, "Release v2 is live at the edge");
  await nav(page, "Releases").click();
  await expect(page.getByText("X-Sitemend-Release:")).toBeVisible();
  await expect(page.locator("text=v2").first()).toBeVisible();
  await shot(page, "06-releases-compare");

  // Verify on the edge.
  await nav(page, "Fixes").click();
  await page.getByRole("button", { name: "Verify" }).click();
  await toast(page, /Edge re-scan: \d+ fixes verified live/);
  await nav(page, "Overview").click();
  await expect(page.getByText("Live edge").first()).toBeVisible();
  // Every issue row names its fix; only the low-confidence link removal still waits.
  await expect(page.locator("tbody tr").getByText("No fix yet")).toHaveCount(0);
  await expect(page.locator("tbody tr").getByText("Verified live", { exact: true })).toHaveCount(26);
  await shot(page, "07-overview-verified");

  // Revert one title (v3), then roll back to v1 (v4).
  await nav(page, "Releases").click();
  await page.getByRole("button", { name: /^v2/ }).click();
  const aboutTitle = page.locator("li", { hasText: "/about" }).filter({ hasText: "About Our Pottery Studio" });
  await aboutTitle.getByRole("button", { name: "Revert" }).click();
  await toast(page, "Release v3: one fix reverted");
  await page.getByRole("button", { name: "Roll back to v1" }).click();
  await toast(page, "Release v4: rolled back to v1");
  await shot(page, "08-releases-rollback");

  // Runs: waterfall and baselines.
  await nav(page, "Runs").click();
  await expect(page.getByText("Baselines per step, all runs")).toBeVisible();
  await page.getByRole("button", { name: /Generate fixes #/ }).click();
  await page.getByRole("button", { name: /^model session\/products/ }).first().click();
  await expect(page.getByText("input_tokens")).toBeVisible();
  await shot(page, "09-runs");

  expect(errors).toEqual([]);
});

test("an unknown address shows the dashboard's own not-found page", async ({ page }) => {
  await page.goto("/no-such-page");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await page.getByRole("link", { name: "Back to Overview" }).click();
  await expect(page).toHaveURL(/\/$/);
});
