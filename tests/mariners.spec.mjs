import { test, expect } from '@playwright/test';

const url = process.env.MARINERS_URL || 'http://127.0.0.1:8011/static/mariners/';

async function startReplay(page) {
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await expect(page.locator('#pitches .pitch')).toHaveCount(1);
}

async function stepToBottomFirst(page) {
  const step = page.getByRole('button', { name: 'Step', exact: true });
  for (let index = 0; index < 11; index += 1) await step.click();
  await expect(page.locator('#scoreboard')).toContainText('Bottom 1st');
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url);
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
  await expect(page.locator('#updated')).not.toHaveText('');
});

test('Seattle batter remains white when the replay starts', async ({ page }) => {
  await startReplay(page);
  await expect(page.locator('#batter')).not.toHaveClass(/mariner/);
  await expect(page.locator('#batter')).toHaveCSS('fill', 'rgb(255, 255, 255)');
  await expect(page.locator('#fielder-center')).toHaveClass(/mariner/);
});

test('visitor batter remains white while Seattle defenders are teal', async ({ page }) => {
  await startReplay(page);
  await stepToBottomFirst(page);
  await expect(page.locator('#batter')).not.toHaveClass(/mariner/);
  await expect(page.locator('#batter')).toHaveCSS('fill', 'rgb(255, 255, 255)');
  await expect(page.locator('#fielder-center')).toHaveClass(/mariner/);
  await expect(page.locator('#fielder-center')).toHaveCSS('fill', 'rgb(0, 168, 168)');
});

test('field labels use a four-pixel black halo without phone-width overflow', async ({ page }) => {
  await startReplay(page);
  await expect(page.locator('#fielder-center')).toHaveCSS('stroke', 'rgb(16, 16, 16)');
  await expect(page.locator('#fielder-center')).toHaveCSS('stroke-width', '4px');
  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBeTruthy();
});
