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
  await expect(page.locator('.person .player-name')).toHaveCount(4);
  await expect(page.getByRole('button', { name: 'Hard' }).nth(0)).toBeVisible();
  const claire = page.locator('.person', { has: page.getByRole('button', { name: 'Claire', exact: true }) });
  await expect(claire.getByRole('button', { name: 'Hard' })).not.toHaveClass(/selected/);
  await expect(page.getByText('Questions: The Trivia API review bank')).toBeVisible();
});

test('difficulty selection controls question eligibility and answer visibility persists', async ({ page }) => {
  await page.getByRole('button', { name: 'Start Game' }).click();
  await expect(page.locator('.category-label')).toHaveCount(6);
  await expect(page.getByRole('heading', { name: /Choose a category/i })).toHaveCount(0);
  await expect(page.getByText(/'s turn$/)).toBeVisible();
  await page.getByRole('button', { name: 'Science' }).click();
  await expect(page.getByText(/^Difficulty:/)).toBeVisible();
  await expect(page.locator('.category-heading')).toBeVisible();
  await page.getByRole('button', { name: 'Hide Answer' }).click();
  await expect(page.getByRole('button', { name: 'Show Answer' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Show Answer' })).toBeVisible();
  await page.getByRole('button', { name: 'Show Answer' }).click();
  await expect(page.getByText(/^Answer:/)).toBeVisible();
});

test('New Game returns an active game to setup', async ({ page }) => {
  await page.getByRole('button', { name: 'Start Game' }).click();
  await expect(page.getByRole('button', { name: 'New Game' })).toBeVisible();
  await page.getByRole('button', { name: 'New Game' }).click();
  await expect(page.getByRole('heading', { name: "Who's playing?" })).toBeVisible();
});

test('correct reaches the summary and hands off to the next player', async ({ page }) => {
  await page.getByRole('button', { name: 'Start Game' }).click();
  await page.getByRole('button', { name: 'History' }).click();
  await page.getByRole('button', { name: 'Correct', exact: true }).click();
  await expect(page.locator('.result-correct')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Next turn' })).toBeVisible();
});

test('the summary reflects scoring on later turns', async ({ page }) => {
  await page.getByRole('button', { name: 'Start Game' }).click();
  await page.getByRole('button', { name: 'History' }).click();
  await page.getByRole('button', { name: 'Correct', exact: true }).click();
  await expect(page.locator('.score').filter({ hasText: ': 1/6' })).toHaveCount(1);
  await expect(page.locator('.pie').evaluateAll(pies => pies.some(pie => pie.style.getPropertyValue('--c3') === '#b66b27'))).resolves.toBeTruthy();
  await page.getByRole('button', { name: 'Next turn' }).click();
  await page.getByRole('button', { name: 'Science' }).click();
  await page.getByRole('button', { name: 'Correct', exact: true }).click();
  await expect(page.locator('.score').filter({ hasText: ': 1/6' })).toHaveCount(2);
  await expect(page.locator('.pie').evaluateAll(pies => pies.some(pie => pie.style.getPropertyValue('--c4') === '#6b52a3'))).resolves.toBeTruthy();
});

test('a filled category is disabled on that player’s next turn', async ({ page }) => {
  await page.getByRole('button', { name: 'Cori', exact: true }).click();
  await page.getByRole('button', { name: 'Ethan', exact: true }).click();
  await page.getByRole('button', { name: 'Start Game' }).click();
  const first = await page.locator('.category').first().getAttribute('data-cat');
  await page.locator('.category').first().click();
  await page.getByRole('button', { name: 'Correct', exact: true }).click();
  await page.getByRole('button', { name: 'Next turn' }).click();
  await page.locator('.category').nth(1).click();
  await page.getByRole('button', { name: 'Incorrect', exact: true }).click();
  await page.getByRole('button', { name: 'Next turn' }).click();
  await expect(page.locator(`.category[data-cat="${first}"]`)).toBeDisabled();
});

test('phone viewport permits vertical scrolling but has no horizontal scrolling', async ({ page }) => {
  await expect(page.evaluate(() => getComputedStyle(document.documentElement).overflowY)).resolves.not.toBe('hidden');
  await page.getByRole('button', { name: 'Start Game' }).click();
  await page.getByRole('button', { name: 'Geography' }).click();
  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBeTruthy();
});
