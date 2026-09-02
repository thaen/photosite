(() => {
  "use strict";

  const API = "https://statsapi.mlb.com/api";
  const MARINERS_ID = 136;
  const LIVE_REFRESH_MS = 10_000;
  const SCHEDULE_REFRESH_MS = 120_000;
  let state = { game: null, feed: null, timecode: null, timer: null, seenPitches: new Set() };
  let demo = { active: false, index: 0, timer: null };

  const DEMO_PLAYERS = [
    [1, "Logan Gilbert", "36"], [2, "Cal Raleigh", "29"], [3, "Josh Naylor", "12"],
    [4, "Cole Young", "2"], [5, "Brock Rodden", "90"], [6, "J.P. Crawford", "3"],
    [7, "Randy Arozarena", "10"], [8, "Julio Rodriguez", "44"], [9, "Dominic Canzone", "8"],
    [10, "Victor Robles", "?"], [11, "Jorge Polanco", "7"], [12, "Mitch Garver", "18"],
  ].map(([id, fullName, jerseyNumber]) => ({ id, fullName, jerseyNumber }));

  const DEMO_STATES = [
    { batter: 7, pitcher: 1, count: [0, 0], outs: 0, bases: [], pitch: ["Called Strike", "FF", 96.2, 7] },
    { batter: 7, pitcher: 1, count: [1, 1], outs: 0, bases: [], pitch: ["Ball", "SL", 85.4, 14] },
    { batter: 7, pitcher: 1, count: [1, 2], outs: 0, bases: [7], pitch: ["In play, no out", "CH", 88.1, 5] },
    { batter: 8, pitcher: 1, count: [0, 1], outs: 0, bases: [7], pitch: ["Foul", "FF", 97.4, 12] },
    { batter: 8, pitcher: 1, count: [1, 1], outs: 0, bases: [7, 8], pitch: ["In play, no out", "SI", 95.8, 8] },
    { batter: 9, pitcher: 1, count: [2, 1], outs: 0, bases: [7, 8, 9], pitch: ["Ball", "CH", 86.7, 13] },
    { batter: 9, pitcher: 1, count: [2, 2], outs: 1, bases: [8, 9], pitch: ["In play, out(s)", "FF", 96.8, 4] },
    { batter: 12, pitcher: 11, count: [0, 1], outs: 1, bases: [8, 9], pitch: ["Called Strike", "FC", 88.2, 2] },
    { batter: 12, pitcher: 11, count: [0, 2], outs: 2, bases: [], pitch: ["In play, out(s)", "SI", 94.1, 9] },
  ];

  const elements = {
    scoreboard: document.querySelector("#scoreboard"),
    field: document.querySelector("#field"),
    fieldNote: document.querySelector("#field-note"),
    message: document.querySelector("#message"),
    pitches: document.querySelector("#pitches"),
    refresh: document.querySelector("#refresh"),
    demo: document.querySelector("#demo"),
    demoReset: document.querySelector("#demo-reset"),
    demoStep: document.querySelector("#demo-step"),
    demoPlay: document.querySelector("#demo-play"),
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

  function demoPerson(id) {
    const player = DEMO_PLAYERS.find((candidate) => candidate.id === id);
    return { id: player.id, fullName: player.fullName, link: `/demo/people/${id}` };
  }

  function demoGame(index) {
    const runs = index >= 7 ? 1 : 0;
    return {
      gamePk: "demo", status: { abstractGameState: "Live", detailedState: "Demo: In Progress" },
      teams: {
        away: { team: { id: MARINERS_ID, name: "Seattle Mariners" }, score: runs },
        home: { team: { id: 117, name: "Houston Astros" }, score: 0 },
      },
    };
  }

  function demoFeed(index) {
    const current = DEMO_STATES[index];
    const playerEntries = Object.fromEntries(DEMO_PLAYERS.map((player) => [`ID${player.id}`, {
      person: demoPerson(player.id), jerseyNumber: player.jerseyNumber,
    }]));
    const defense = { pitcher: demoPerson(current.pitcher), catcher: demoPerson(2), first: demoPerson(3), second: demoPerson(4), third: demoPerson(5), shortstop: demoPerson(6), left: demoPerson(7), center: demoPerson(8), right: demoPerson(9), team: { name: "Seattle Mariners" } };
    const basePerson = (base) => current.bases[base] ? demoPerson(current.bases[base]) : undefined;
    const plays = DEMO_STATES.slice(0, index + 1).map((step, atBatIndex) => ({
      atBatIndex, about: { halfInning: "top", inning: 7 },
      matchup: { batter: demoPerson(step.batter), pitcher: demoPerson(step.pitcher) },
      playEvents: [{ index: atBatIndex, isPitch: true, count: { balls: step.count[0], strikes: step.count[1] }, details: { description: step.pitch[0], type: { code: step.pitch[1] } }, pitchData: { startSpeed: step.pitch[2], zone: step.pitch[3] } }],
    }));
    return {
      gameData: { status: { detailedState: "Demo: In Progress" }, teams: { away: { abbreviation: "SEA" }, home: { abbreviation: "HOU" } } },
      liveData: {
        boxscore: { teams: { away: { players: playerEntries }, home: { players: {} } } },
        linescore: {
          inningState: "Top", currentInningOrdinal: "7th", balls: current.count[0], strikes: current.count[1], outs: current.outs,
          defense, offense: { batter: demoPerson(current.batter), first: basePerson(0), second: basePerson(1), third: basePerson(2), team: { name: "Seattle Mariners" } },
        },
        plays: { allPlays: plays },
      },
    };
  }

  function stopDemoPlayback() {
    if (demo.timer) window.clearInterval(demo.timer);
    demo.timer = null;
  }

  function renderDemo() {
    clearTimer();
    demo.active = true;
    state = { game: demoGame(demo.index), feed: demoFeed(demo.index), timecode: null, timer: null, seenPitches: new Set() };
    renderScoreboard(state.game, state.feed);
    renderField(state.feed);
    renderPitches(state.feed);
    elements.updated.textContent = `Demo play ${demo.index + 1} of ${DEMO_STATES.length}.`;
  }

  function stepDemo() {
    if (!demo.active) demo.index = 0;
    else demo.index = Math.min(demo.index + 1, DEMO_STATES.length - 1);
    renderDemo();
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
      "DEFENSE",
      "                 " + position("CF", "center"),
      "       " + position("LF", "left") + "              " + position("RF", "right"),
      "",
      "             " + position("SS", "shortstop") + "    " + position("2B", "second"),
      "       " + position("3B", "third") + "          " + position("1B", "first"),
      "                 " + position("P", "pitcher"),
      "                 " + position("C", "catcher"),
      "",
      "BASES",
      "                   [2 " + runner("R", "second") + "]",
      "                  /         \\",
      "          [3 " + runner("R", "third") + "]             [1 " + runner("R", "first") + "]",
      "                  \\         /",
      "                   [H " + shortToken("B", offense.batter, directory) + "]",
    ].join("\n");
    elements.fieldNote.textContent = `P1 through RF9 are the defense. The lower diamond shows the batter and occupied bases.`;
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
    if (demo.active) {
      renderDemo();
      return;
    }
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

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearTimer();
      stopDemoPlayback();
    } else if (!demo.active) refresh();
  });
  elements.refresh.addEventListener("click", refresh);
  elements.demo.addEventListener("click", () => {
    stopDemoPlayback();
    demo = { active: true, index: 0, timer: null };
    renderDemo();
  });
  elements.demoReset.addEventListener("click", () => {
    stopDemoPlayback();
    demo = { active: true, index: 0, timer: null };
    renderDemo();
  });
  elements.demoStep.addEventListener("click", () => {
    stopDemoPlayback();
    stepDemo();
  });
  elements.demoPlay.addEventListener("click", () => {
    if (!demo.active || demo.index === DEMO_STATES.length - 1) demo = { active: true, index: 0, timer: null };
    stopDemoPlayback();
    renderDemo();
    demo.timer = window.setInterval(() => {
      if (demo.index === DEMO_STATES.length - 1) {
        stopDemoPlayback();
        return;
      }
      stepDemo();
    }, 900);
  });
  refresh();
})();
