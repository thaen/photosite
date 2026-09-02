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
  await expectFieldLabel(page, 'batter', '56', 'rgb(255, 255, 255)');
  await expect(page.locator('#batter')).not.toHaveClass(/mariner/);
  await expectFieldLabel(page, 'fielder-pitcher', '65', 'rgb(255, 255, 255)');
  await expect(page.locator('#fielder-pitcher')).not.toHaveClass(/mariner/);
  await expect(page.locator('#field')).toHaveAccessibleName(/Boston Red Sox/);
});

test('the batter stays white when Seattle is batting', async ({ page }) => {
  await seekPitch(page, 1);
  await expect(page.locator('#batter')).toHaveText('56');
  await expect(page.locator('#batter')).toHaveCSS('fill', 'rgb(255, 255, 255)');
  await expect(page.locator('#batter')).not.toHaveClass(/mariner/);
});

test('the field changes both teams, player numbers, and colors at the first half-inning change', async ({ page }) => {
  await seekPitch(page, 12);
  await expect(page.locator('#scoreboard')).toContainText('Bottom 1st');
  await expectFieldLabel(page, 'batter', '19', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'fielder-pitcher', '22', 'rgb(0, 168, 168)');
  await expectFieldLabel(page, 'fielder-center', '44', 'rgb(0, 168, 168)');
  await expect(page.locator('#fielder-pitcher')).toHaveClass(/mariner/);
  await expect(page.locator('#field')).toHaveAccessibleName(/Seattle Mariners/);
});

test('the field returns to the visitor defense at the top of the second inning', async ({ page }) => {
  await seekPitch(page, 27);
  await expect(page.locator('#scoreboard')).toContainText('Top 2nd');
  await expectFieldLabel(page, 'batter', '12', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'fielder-pitcher', '65', 'rgb(255, 255, 255)');
  await expect(page.locator('#fielder-pitcher')).not.toHaveClass(/mariner/);
});

test('the field shows the cached runner at second base while retaining the current batter', async ({ page }) => {
  await seekPitch(page, 30);
  await expectFieldLabel(page, 'runner-second', '12', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'runner-first', '-', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'runner-third', '-', 'rgb(255, 255, 255)');
  await expectFieldLabel(page, 'batter', '2', 'rgb(255, 255, 255)');
});

test('all player labels remain legible without a horizontal phone-width overflow', async ({ page }) => {
  await seekPitch(page, 12);
  await expect(page.locator('#fielder-center')).toHaveCSS('stroke', 'rgb(16, 16, 16)');
  await expect(page.locator('#fielder-center')).toHaveCSS('stroke-width', '4px');
  await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).resolves.toBeTruthy();
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
  await expect(zone.locator('.zone-cell')).toHaveCount(13);
  await expect(zone.locator('.zone-strike')).toHaveCount(9);
  await expect(zone.locator('.zone-ball')).toHaveCount(4);
  await expect(zone.locator('[data-zone="10"]')).toHaveCount(0);
  await expect(zone.locator('[data-zone="15"]')).toHaveCount(0);
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

test('the live-game region puts the field, current pitch, and zone above the pitch feed on a phone', async ({ page }) => {
  await startReplay(page);
  const boxes = await page.locator('#field, #current-pitch, #pitch-zone, #pitches').evaluateAll((nodes) =>
    Object.fromEntries(nodes.map((node) => [node.id, node.getBoundingClientRect().toJSON()])));
  expect(boxes.field.y).toBeLessThan(boxes.pitches.y);
  expect(boxes['current-pitch'].y).toBeLessThan(boxes.pitches.y);
  expect(boxes['pitch-zone'].y).toBeLessThan(boxes.pitches.y);
  await expect(page.getByRole('heading', { name: 'Line score' })).toHaveCount(0);
  await expect(page.getByRole('table', { name: /line score/i })).toHaveCount(0);
});

test('the live game uses adjacent field and pitch panels on desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await startReplay(page);
  const boxes = await page.locator('#field, .live-details').evaluateAll((nodes) =>
    nodes.map((node) => node.getBoundingClientRect().toJSON()));
  expect(boxes[0].right).toBeLessThan(boxes[1].left);
  expect(boxes[0].top).toBeLessThan(900);
  expect(boxes[1].top).toBeLessThan(900);
});

test('the field contains numbers only and places batter above catcher at home', async ({ page }) => {
  await startReplay(page);
  await expect(page.locator('#fielder-pitcher')).toHaveText('65');
  await expect(page.locator('#batter')).toHaveText('56');
  const positions = await page.locator('#batter, #fielder-catcher').evaluateAll((nodes) =>
    Object.fromEntries(nodes.map((node) => [node.id, Number(node.getAttribute('y'))])));
  expect(positions.batter).toBeLessThan(positions['fielder-catcher']);
});

test('batting orders contain only cached batters and highlight the current batter', async ({ page }) => {
  await startReplay(page);
  const away = page.getByRole('table', { name: /Seattle batting order/i });
  const home = page.getByRole('table', { name: /Boston batting order/i });
  await expect(away.locator('tr:not(:first-child)')).toHaveCount(fixture.liveData.boxscore.teams.away.batters.length);
  await expect(home.locator('tr:not(:first-child)')).toHaveCount(fixture.liveData.boxscore.teams.home.batters.length);
  await expect(away.locator('tr.is-current-batter')).toContainText('Randy Arozarena');
  await page.getByRole('button', { name: 'Step', exact: true }).click();
  const nextName = pitches[1].play.matchup.batter.fullName;
  await expect(away.locator('tr.is-current-batter')).toContainText(nextName);
});
