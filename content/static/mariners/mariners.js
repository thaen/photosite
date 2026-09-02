(() => {
  "use strict";

  const API = "https://statsapi.mlb.com/api";
  const MARINERS_ID = 136;
  const LIVE_REFRESH_MS = 10_000;
  const SCHEDULE_REFRESH_MS = 120_000;
  let state = { game: null, feed: null, timecode: null, timer: null, seenPitches: new Set() };

  const elements = {
    scoreboard: document.querySelector("#scoreboard"),
    field: document.querySelector("#field"),
    fieldNote: document.querySelector("#field-note"),
    message: document.querySelector("#message"),
    pitches: document.querySelector("#pitches"),
    refresh: document.querySelector("#refresh"),
    updated: document.querySelector("#updated"),
  };

  function pacificDate() {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Los_Angeles", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date());
  }

  async function getJson(path) {
    const response = await fetch(`${API}${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`MLB returned ${response.status}`);
    return response.json();
  }

  function clearTimer() {
    if (state.timer) window.clearTimeout(state.timer);
    state.timer = null;
  }

  function scheduleNext(delay) {
    clearTimer();
    if (!document.hidden) state.timer = window.setTimeout(refresh, delay);
  }

  function isLive(game) {
    return game.status.abstractGameState === "Live";
  }

  async function findGame() {
    const data = await getJson(`/v1/schedule?sportId=1&teamId=${MARINERS_ID}&date=${pacificDate()}`);
    return data.dates?.[0]?.games?.find((game) =>
      game.teams.away.team.id === MARINERS_ID || game.teams.home.team.id === MARINERS_ID);
  }

  function line(text, width = 42) {
    return `| ${text.padEnd(width - 2).slice(0, width - 2)} |`;
  }

  function renderScoreboard(game, feed) {
    if (!game) {
      elements.scoreboard.textContent = "+------------------------------------------+\n"
        + line("No Mariners game is scheduled today.") + "\n"
        + "+------------------------------------------+";
      return;
    }
    const away = game.teams.away;
    const home = game.teams.home;
    const status = feed?.gameData?.status?.detailedState || game.status.detailedState;
    const feedTeams = feed?.gameData?.teams || {};
    const awayName = feedTeams.away?.abbreviation || away.team.name;
    const homeName = feedTeams.home?.abbreviation || home.team.name;
    const linescore = feed?.liveData?.linescore;
    const situation = linescore && isLive(game) ? `${linescore.inningState || ""} ${linescore.currentInningOrdinal || ""} | ${linescore.outs ?? 0} out | ${linescore.balls ?? 0}-${linescore.strikes ?? 0}` : "";
    elements.scoreboard.textContent = "+------------------------------------------+\n"
      + line(`${awayName.padEnd(5)} ${String(away.score ?? "-").padStart(2)}   ${status}`) + "\n"
      + line(`${homeName.padEnd(5)} ${String(home.score ?? "-").padStart(2)}   ${situation}`) + "\n"
      + line(`${away.team.name} at ${home.team.name}`) + "\n"
      + "+------------------------------------------+";
  }

  function playerDirectory(feed) {
    const teams = feed?.liveData?.boxscore?.teams || {};
    return Object.values(teams).flatMap((team) => Object.values(team.players || []))
      .reduce((directory, player) => directory.set(player.person.id, player), new Map());
  }

  function token(label, person, directory) {
    const number = person ? directory.get(person.id)?.jerseyNumber || "?" : "-";
    return `${label}${number}`.padEnd(8);
  }

  function shortToken(label, person, directory) {
    return `${label}${person ? directory.get(person.id)?.jerseyNumber || "?" : "-"}`;
  }

  function renderField(feed) {
    const linescore = feed?.liveData?.linescore;
    if (!linescore?.defense || !linescore?.offense) {
      elements.field.textContent = "The defensive alignment will appear when MLB reports it.";
      elements.fieldNote.textContent = "";
      return;
    }
    const defense = linescore.defense;
    const offense = linescore.offense;
    const directory = playerDirectory(feed);
    const position = (label, name) => shortToken(label, defense[name], directory);
    const runner = (label, name) => shortToken(label, offense[name], directory);
    elements.field.textContent = [
      "             " + position("CF", "center"),
      "      " + position("LF", "left") + "              " + position("RF", "right"),
      "",
      "           " + position("SS", "shortstop") + "    " + position("2B", "second"),
      "      " + position("3B", "third") + "    .-" + runner("R2", "second") + "-.    " + position("1B", "first"),
      "                   /       \\",
      "          " + runner("R3", "third") + "  / " + position("P", "pitcher") + "  \\  " + runner("R1", "first"),
      "                 /  " + position("C", "catcher") + "   \\",
      "                 '---" + shortToken("B", offense.batter, directory) + "---'",
    ].join("\n");
    elements.fieldNote.textContent = `B = batter. R1, R2, and R3 = runners. Defense: ${defense.team?.name || "unknown"}.`;
  }

  function pitchRows(feed) {
    const plays = feed?.liveData?.plays?.allPlays || [];
    return plays.flatMap((play) => play.playEvents
      .filter((event) => event.isPitch)
      .map((event) => ({ play, event, key: `${play.atBatIndex}:${event.index}` })))
      .reverse();
  }

  function renderPitches(feed) {
    const rows = pitchRows(feed);
    const firstRender = state.seenPitches.size === 0;
    const directory = playerDirectory(feed);
    elements.pitches.replaceChildren();
    if (!rows.length) {
      elements.message.textContent = "Pitches will appear when MLB reports them.";
      return;
    }
    elements.message.textContent = `${rows.length} tracked pitches. New pitches appear at the top.`;
    for (const { play, event, key } of rows) {
      const details = event.details || {};
      const data = event.pitchData || {};
      const count = event.count || {};
      const inning = `${play.about?.halfInning === "top" ? "T" : "B"}${play.about?.inning ?? "?"}`;
      const speed = data.startSpeed == null ? "--.-" : data.startSpeed.toFixed(1);
      const type = details.type?.code || "--";
      const zone = data.zone == null ? "-" : data.zone;
      const batter = shortToken("B", play.matchup?.batter, directory);
      const pitcher = shortToken("P", play.matchup?.pitcher, directory);
      const item = document.createElement("li");
      item.className = `pitch${!firstRender && !state.seenPitches.has(key) ? " new" : ""}`;
      item.textContent = `${inning} ${String(count.balls ?? 0)}-${String(count.strikes ?? 0)} ${speed.padStart(5)} ${type.padEnd(2)} z${zone.toString().padStart(2)} ${details.description || "Pitch"} ${batter}/${pitcher}`;
      elements.pitches.append(item);
      state.seenPitches.add(key);
    }
  }

  function decodePointer(pointer) {
    return pointer.split("/").slice(1).map((part) => part.replaceAll("~1", "/").replaceAll("~0", "~"));
  }

  function patchDocument(documentValue, operations) {
    for (const operation of operations) {
      const parts = decodePointer(operation.path);
      const key = parts.pop();
      const parent = parts.reduce((value, part) => value[part], documentValue);
      if (operation.op === "remove") Array.isArray(parent) ? parent.splice(Number(key), 1) : delete parent[key];
      else if (operation.op === "add" && Array.isArray(parent)) parent.splice(key === "-" ? parent.length : Number(key), 0, operation.value);
      else if (operation.op === "add" || operation.op === "replace") parent[key] = operation.value;
      else throw new Error(`Unsupported MLB patch operation: ${operation.op}`);
    }
  }

  async function updateLiveFeed() {
    const gamePk = state.game.gamePk;
    const timestamps = await getJson(`/v1.1/game/${gamePk}/feed/live/timestamps`);
    const newest = timestamps.at(-1);
    if (!state.timecode || !newest || newest === state.timecode) {
      if (!state.feed) state.feed = await getJson(`/v1.1/game/${gamePk}/feed/live`);
      state.timecode = newest || state.timecode;
      return;
    }
    const patch = await getJson(`/v1.1/game/${gamePk}/feed/live/diffPatch?startTimecode=${state.timecode}&endTimecode=${newest}`);
    try {
      if (Array.isArray(patch)) patchDocument(state.feed, patch);
      else state.feed = patch;
    } catch {
      state.feed = await getJson(`/v1.1/game/${gamePk}/feed/live`);
    }
    state.timecode = newest;
  }

  async function refresh() {
    clearTimer();
    if (document.hidden) return;
    try {
      const game = await findGame();
      if (!game || state.game?.gamePk !== game.gamePk) state = { game, feed: null, timecode: null, timer: null, seenPitches: new Set() };
      else state.game = game;
      if (game) await updateLiveFeed();
      renderScoreboard(game, state.feed);
      renderField(state.feed);
      if (state.feed) renderPitches(state.feed);
      else elements.pitches.replaceChildren();
      elements.updated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}.`;
      scheduleNext(game && isLive(game) ? LIVE_REFRESH_MS : SCHEDULE_REFRESH_MS);
    } catch (error) {
      elements.message.textContent = `The feed is unavailable: ${error.message}`;
      scheduleNext(SCHEDULE_REFRESH_MS);
    }
  }

  document.addEventListener("visibilitychange", () => document.hidden ? clearTimer() : refresh());
  elements.refresh.addEventListener("click", refresh);
  refresh();
})();
