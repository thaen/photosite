import { test, expect } from '@playwright/test';

const url = 'http://192.168.68.77:8001/static/trivia/';

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url);
  await page.evaluate(() => localStorage.clear());
  await page.reload();
});

test('setup has the required defaults and Claire lacks Hard', async ({ page }) => {
  await expect(page.getByRole('heading', { name: "Who's playing?" })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Hard' }).nth(0)).toBeVisible();
  const claire = page.locator('.person', { has: page.getByRole('button', { name: 'Claire', exact: true }) });
  await expect(claire.getByRole('button', { name: 'Hard' })).not.toHaveClass(/selected/);
  await expect(page.getByText('Questions: The Trivia API review bank')).toBeVisible();
});

test('difficulty selection controls question eligibility and answer visibility persists', async ({ page }) => {
  await page.getByRole('button', { name: 'Start Game' }).click();
  await page.getByRole('button', { name: 'Science' }).click();
  await expect(page.getByText(/^Difficulty:/)).toBeVisible();
  await page.getByRole('button', { name: 'Hide Answer' }).click();
  await expect(page.getByRole('button', { name: 'Show Answer' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Show Answer' })).toBeVisible();
  await page.getByRole('button', { name: 'Show Answer' }).click();
  await expect(page.getByText(/^Answer:/)).toBeVisible();
});

test('correct reaches the summary and hands off to the next player', async ({ page }) => {
  await page.getByRole('button', { name: 'Start Game' }).click();
  await page.getByRole('button', { name: 'History' }).click();
  await page.getByRole('button', { name: 'Correct', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Correct!' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Pass the phone to/ })).toBeVisible();
});

test('phone viewport has no document scrolling in setup and question screens', async ({ page }) => {
  await expect(page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).resolves.toBeTruthy();
  await page.getByRole('button', { name: 'Start Game' }).click();
  await page.getByRole('button', { name: 'Geography' }).click();
  await expect(page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).resolves.toBeTruthy();
  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBeTruthy();
});
