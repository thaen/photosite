import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

const url = process.env.MARINERS_URL || 'http://127.0.0.1:8011/static/mariners/';
const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const fixture = JSON.parse(fs.readFileSync(
  path.join(projectRoot, 'content/static/mariners/demo-game-824716.json'),
  'utf8',
));
const players = Object.fromEntries(Object.values(fixture.liveData.boxscore.teams)
  .flatMap((team) => Object.values(team.players))
  .map((player) => [player.person.id, player]));
const pitches = fixture.liveData.plays.allPlays.flatMap((play) => play.playEvents
  .filter((event) => event.isPitch)
  .map((event) => ({ play, event })));

function jersey(person) {
  return players[person.id].jerseyNumber;
}

function pitchText({ play, event }) {
  const inning = `${play.about.halfInning === 'top' ? 'T' : 'B'}${play.about.inning}`;
  const speed = event.pitchData.startSpeed.toFixed(1);
  const type = event.details.type.description;
  const batter = `${play.matchup.batter.fullName.split(' ').at(-1)} #${jersey(play.matchup.batter)}`;
  const pitcher = `${play.matchup.pitcher.fullName.split(' ').at(-1)} #${jersey(play.matchup.pitcher)}`;
  return `${inning} ${event.count.balls}-${event.count.strikes} ${speed} mph ${type}, zone ${event.pitchData.zone}: ${event.details.description} | ${batter} vs ${pitcher}`;
}

async function startReplay(page) {
  await page.getByRole('button', { name: 'Start', exact: true }).click();
  await expect(page.locator('#pitches .pitch')).toHaveCount(1);
}

async function seekPitch(page, number) {
  await startReplay(page);
  const step = page.getByRole('button', { name: 'Step', exact: true });
  for (let index = 1; index < number; index += 1) await step.click();
  await expect(page.locator('#updated')).toContainText(`Cached MLB pitch ${number} of ${pitches.length}`);
}

async function expectFieldLabel(page, id, text, color) {
  const label = page.locator(`#${id}`);
  await expect(label).toHaveText(text, { timeout: 1_000 });
  await expect(label).toHaveCSS('fill', color);
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url);
  await expect(page.getByRole('button', { name: 'Start', exact: true })).toBeVisible();
  await expect(page.locator('#updated')).not.toHaveText('');
});

test('the replay starts on the first cached MLB pitch with its count, score, and pitch description', async ({ page }) => {
  await startReplay(page);
  await expect(page.locator('#scoreboard')).toContainText('SEA    0');
  await expect(page.locator('#scoreboard')).toContainText('BOS    0');
  await expect(page.locator('#scoreboard')).toContainText('Top 1st | 0 out | 1-0');
  await expect(page.locator('#pitches .pitch').first()).toHaveText(pitchText(pitches[0]));
  await expect(page.locator('#message')).toContainText('1 pitches');
});

test('the pitch feed is newest first and retains every pitch after stepping', async ({ page }) => {
  await seekPitch(page, 3);
  await expect(page.locator('#pitches .pitch')).toHaveCount(3);
  await expect(page.locator('#pitches .pitch').nth(0)).toHaveText(pitchText(pitches[2]));
  await expect(page.locator('#pitches .pitch').nth(1)).toHaveText(pitchText(pitches[1]));
  await expect(page.locator('#pitches .pitch').nth(2)).toHaveText(pitchText(pitches[0]));
});

test('the step and reset controls move through the cached feed by one pitch and return to pitch one', async ({ page }) => {
  await startReplay(page);
  await page.getByRole('button', { name: 'Step', exact: true }).click();
  await expect(page.locator('#updated')).toContainText('Cached MLB pitch 2 of 334');
  await expect(page.locator('#pitches .pitch')).toHaveCount(2);
  await page.getByRole('button', { name: 'Reset', exact: true }).click();
  await expect(page.locator('#updated')).toContainText('Cached MLB pitch 1 of 334');
  await expect(page.locator('#pitches .pitch')).toHaveCount(1);
});

test('the play control advances the replay without a manual step', async ({ page }) => {
  await startReplay(page);
  await page.getByRole('button', { name: 'Play', exact: true }).click();
  await expect(page.locator('#updated')).not.toContainText('Cached MLB pitch 1 of 334', { timeout: 2_000 });
  await expect(page.locator('#pitches .pitch')).toHaveCount(2);
});

test('the field shows Boston as white defenders during Seattle at-bats', async ({ page }) => {
  await seekPitch(page, 1);
  await expectFieldLabel(page, 'batter', 'B 56', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'fielder-pitcher', 'P 65', 'rgb(255, 255, 255)');
  await expect(page.locator('#fielder-pitcher')).not.toHaveClass(/mariner/);
  await expect(page.locator('#field')).toHaveAccessibleName(/Boston Red Sox/);
});

test('the field changes both teams, player numbers, and colors at the first half-inning change', async ({ page }) => {
  await seekPitch(page, 12);
  await expect(page.locator('#scoreboard')).toContainText('Bottom 1st');
  await expectFieldLabel(page, 'batter', 'B 19', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'fielder-pitcher', 'P 22', 'rgb(0, 168, 168)');
  await expectFieldLabel(page, 'fielder-center', 'CF 44', 'rgb(0, 168, 168)');
  await expect(page.locator('#fielder-pitcher')).toHaveClass(/mariner/);
  await expect(page.locator('#field')).toHaveAccessibleName(/Seattle Mariners/);
});

test('the field returns to the visitor defense at the top of the second inning', async ({ page }) => {
  await seekPitch(page, 27);
  await expect(page.locator('#scoreboard')).toContainText('Top 2nd');
  await expectFieldLabel(page, 'batter', 'B 12', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'fielder-pitcher', 'P 65', 'rgb(255, 255, 255)');
  await expect(page.locator('#fielder-pitcher')).not.toHaveClass(/mariner/);
});

test('the field shows the cached runner at second base while retaining the current batter', async ({ page }) => {
  await seekPitch(page, 30);
  await expectFieldLabel(page, 'runner-second', 'R 12', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'runner-first', 'R -', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'runner-third', 'R -', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'batter', 'B 2', 'rgb(255, 255, 255)');
});

test('all player labels remain legible without a horizontal phone-width overflow', async ({ page }) => {
  await seekPitch(page, 12);
  await expect(page.locator('#fielder-center')).toHaveCSS('stroke', 'rgb(16, 16, 16)');
  await expect(page.locator('#fielder-center')).toHaveCSS('stroke-width', '4px');
  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBeTruthy();
});

test('the page has a semantic line-score table for Seattle and Boston', async ({ page }) => {
  await seekPitch(page, 12);
  const lineScore = page.getByRole('table', { name: /line score/i });
  await expect(lineScore).toBeVisible({ timeout: 1_000 });
  await expect(lineScore).toContainText('Seattle');
  await expect(lineScore).toContainText('Boston');
  await expect(lineScore).toContainText('R');
  await expect(lineScore).toContainText('H');
  await expect(lineScore).toContainText('E');
});

test('the page has a semantic box-score table with team totals and player results', async ({ page }) => {
  await seekPitch(page, 12);
  const boxScore = page.getByRole('table', { name: /box score/i });
  await expect(boxScore).toBeVisible({ timeout: 1_000 });
  await expect(boxScore).toContainText('Seattle Mariners');
  await expect(boxScore).toContainText('Boston Red Sox');
  await expect(boxScore).toContainText('Arozarena');
  await expect(boxScore).toContainText('Anthony');
});

test('the page has a Seattle batting-order table with name, jersey number, and position', async ({ page }) => {
  await startReplay(page);
  const lineup = page.getByRole('table', { name: /Seattle batting order/i });
  await expect(lineup).toBeVisible({ timeout: 1_000 });
  await expect(lineup).toContainText('1');
  await expect(lineup).toContainText('Randy Arozarena');
  await expect(lineup).toContainText('56');
  await expect(lineup).toContainText('LF');
  await expect(lineup).toContainText('Julio Rodríguez');
  await expect(lineup).toContainText('44');
  await expect(lineup).toContainText('CF');
});

test('the page has a Boston batting-order table with name, jersey number, and position', async ({ page }) => {
  await startReplay(page);
  const lineup = page.getByRole('table', { name: /Boston batting order/i });
  await expect(lineup).toBeVisible({ timeout: 1_000 });
  await expect(lineup).toContainText('Roman Anthony');
  await expect(lineup).toContainText('19');
  await expect(lineup).toContainText('RF');
  await expect(lineup).toContainText('Trevor Story');
  await expect(lineup).toContainText('10');
  await expect(lineup).toContainText('SS');
});

test('the page has a pitch-zone diagram that marks the current cached pitch zone', async ({ page }) => {
  await seekPitch(page, 3);
  const zone = page.getByRole('img', { name: /pitch zone/i });
  await expect(zone).toBeVisible({ timeout: 1_000 });
  await expect(zone.locator('[data-zone="9"]')).toHaveAttribute('data-current', 'true');
  await expect(zone).toContainText('9');
});

test('the page has an accessible player directory that connects jersey numbers to current positions', async ({ page }) => {
  await seekPitch(page, 12);
  const directory = page.getByRole('table', { name: /players and positions/i });
  await expect(directory).toBeVisible({ timeout: 1_000 });
  await expect(directory).toContainText('Bryan Woo');
  await expect(directory).toContainText('22');
  await expect(directory).toContainText('P');
  await expect(directory).toContainText('Roman Anthony');
  await expect(directory).toContainText('19');
  await expect(directory).toContainText('RF');
});
