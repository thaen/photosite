(() => {
  "use strict";

  const API = "https://statsapi.mlb.com/api";
  const MARINERS_ID = 136;
  const LIVE_REFRESH_MS = 10_000;
  const SCHEDULE_REFRESH_MS = 120_000;
  let state = { game: null, feed: null, timecode: null, timer: null, seenPitches: new Set() };
  let demo = { active: false, index: 0, timer: null, source: null, pitches: [] };

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

  function demoPitchEvents(feed) {
    return feed.liveData.plays.allPlays.flatMap((play) => play.playEvents
      .filter((event) => event.isPitch)
      .map((event) => ({ play, event })));
  }

  function baseStateBefore(plays, targetAtBatIndex) {
    const bases = new Map();
    for (const play of plays) {
      if (play.about.atBatIndex >= targetAtBatIndex) break;
      for (const runner of play.runners || []) {
        const movement = runner.movement || {};
        if (movement.start) bases.delete(movement.start);
        if (["1B", "2B", "3B"].includes(movement.end)) bases.set(movement.end, runner.details.runner);
      }
    }
    return bases;
  }

  function demoFrame(index) {
    const source = demo.source;
    const { play, event } = demo.pitches[index];
    const plays = source.liveData.plays.allPlays;
    const bases = baseStateBefore(plays, play.about.atBatIndex);
    const isLastPitch = play.playEvents.filter((candidate) => candidate.isPitch).at(-1)?.index === event.index;
    const previous = plays.findLast((candidate) => candidate.about.atBatIndex < play.about.atBatIndex);
    const result = isLastPitch ? play.result : previous?.result;
    const gameData = source.gameData;
    const linescore = source.liveData.linescore;
    const game = {
      gamePk: gameData.game.pk,
      status: { abstractGameState: "Live", detailedState: "Replay: Seattle at Boston" },
      teams: {
        away: { team: { id: gameData.teams.away.id, name: gameData.teams.away.name }, score: result?.awayScore ?? 0 },
        home: { team: { id: gameData.teams.home.id, name: gameData.teams.home.name }, score: result?.homeScore ?? 0 },
      },
    };
    const replayLinescore = {
      ...linescore,
      inningState: play.about.halfInning === "top" ? "Top" : "Bottom",
      currentInningOrdinal: `${play.about.inning}${play.about.inning === 1 ? "st" : play.about.inning === 2 ? "nd" : play.about.inning === 3 ? "rd" : "th"}`,
      balls: event.count.balls, strikes: event.count.strikes, outs: event.count.outs,
      offense: {
        ...linescore.offense,
        batter: play.matchup.batter,
        pitcher: play.matchup.pitcher,
        first: bases.get("1B"), second: bases.get("2B"), third: bases.get("3B"),
      },
    };
    const visiblePlays = plays.filter((candidate) => candidate.about.atBatIndex < play.about.atBatIndex)
      .concat([{ ...play, playEvents: play.playEvents.filter((candidate) => candidate.isPitch && candidate.index <= event.index) }]);
    return { game, feed: { ...source, gameData: { ...gameData, status: { detailedState: "Replay: Seattle at Boston" } }, liveData: { ...source.liveData, linescore: replayLinescore, plays: { ...source.liveData.plays, allPlays: visiblePlays } } } };
  }

  function stopDemoPlayback() {
    if (demo.timer) window.clearInterval(demo.timer);
    demo.timer = null;
  }

  async function startDemo() {
    stopDemoPlayback();
    if (!demo.source) {
      elements.message.textContent = "Loading cached Seattle at Boston game...";
      const response = await fetch("demo-game-824716.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`Cached game returned ${response.status}`);
      demo.source = await response.json();
      demo.pitches = demoPitchEvents(demo.source);
    }
    demo.active = true;
    demo.index = 0;
    renderDemo();
  }

  function renderDemo() {
    clearTimer();
    demo.active = true;
    const frame = demoFrame(demo.index);
    state = { game: frame.game, feed: frame.feed, timecode: null, timer: null, seenPitches: new Set() };
    renderScoreboard(state.game, state.feed);
    renderField(state.feed);
    renderPitches(state.feed);
    elements.updated.textContent = `Cached MLB pitch ${demo.index + 1} of ${demo.pitches.length}.`;
  }

  function stepDemo() {
    if (!demo.active) demo.index = 0;
    else demo.index = Math.min(demo.index + 1, demo.pitches.length - 1);
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
      for (const id of ["fielder-center", "fielder-left", "fielder-right", "fielder-shortstop", "fielder-second", "fielder-third", "fielder-first", "fielder-pitcher", "fielder-catcher", "runner-second", "runner-third", "runner-first", "batter"]) document.querySelector(`#${id}`).textContent = "";
      elements.field.setAttribute("aria-label", "The defensive alignment will appear when MLB reports it.");
      elements.fieldNote.textContent = "";
      return;
    }
    const defense = linescore.defense;
    const offense = linescore.offense;
    const directory = playerDirectory(feed);
    const mariners = new Set(Object.values(feed.liveData?.boxscore?.teams || {})
      .filter((team) => String(team.team?.id) === String(MARINERS_ID))
      .flatMap((team) => Object.values(team.players || []).map((player) => player.person.id)));
    const number = (person) => person ? directory.get(person.id)?.jerseyNumber || "?" : "-";
    const setText = (id, text, person, useTeamColor = false) => {
      const label = document.querySelector(`#${id}`);
      label.textContent = text;
      label.classList.toggle("mariner", useTeamColor && mariners.has(person?.id));
    };
    setText("fielder-center", `CF ${number(defense.center)}`, defense.center, true);
    setText("fielder-left", `LF ${number(defense.left)}`, defense.left, true);
    setText("fielder-right", `RF ${number(defense.right)}`, defense.right, true);
    setText("fielder-shortstop", `SS ${number(defense.shortstop)}`, defense.shortstop, true);
    setText("fielder-second", `2B ${number(defense.second)}`, defense.second, true);
    setText("fielder-third", `3B ${number(defense.third)}`, defense.third, true);
    setText("fielder-first", `1B ${number(defense.first)}`, defense.first, true);
    setText("fielder-pitcher", `P ${number(defense.pitcher)}`, defense.pitcher, true);
    setText("fielder-catcher", `C ${number(defense.catcher)}`, defense.catcher, true);
    setText("runner-second", `R ${number(offense.second)}`, offense.second);
    setText("runner-third", `R ${number(offense.third)}`, offense.third);
    setText("runner-first", `R ${number(offense.first)}`, offense.first);
    setText("batter", `B ${number(offense.batter)}`, offense.batter);
    elements.field.setAttribute("aria-label", `Defensive alignment for ${defense.team?.name || "the fielding team"}; batter and runners are shown at the bases.`);
    elements.fieldNote.textContent = demo.active
      ? "Seattle defenders are teal. The batter and runners are white. The defense is the final alignment in this cached game."
      : "Seattle defenders are teal. The batter and runners are white.";
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
    elements.message.textContent = `${rows.length} pitches. Format: inning, count, mph, type, zone, result, batter versus pitcher.`;
    for (const { play, event, key } of rows) {
      const details = event.details || {};
      const data = event.pitchData || {};
      const count = event.count || {};
      const inning = `${play.about?.halfInning === "top" ? "T" : "B"}${play.about?.inning ?? "?"}`;
      const speed = data.startSpeed == null ? "--.-" : data.startSpeed.toFixed(1);
      const type = details.type?.description || "Unknown pitch";
      const zone = data.zone == null ? "-" : data.zone;
      const displayPlayer = (person) => {
        const player = directory.get(person?.id);
        const lastName = person?.fullName?.split(" ").at(-1) || "Unknown";
        return `${lastName} #${player?.jerseyNumber || "?"}`;
      };
      const batter = displayPlayer(play.matchup?.batter);
      const pitcher = displayPlayer(play.matchup?.pitcher);
      const item = document.createElement("li");
      item.className = `pitch${!firstRender && !state.seenPitches.has(key) ? " new" : ""}`;
      item.textContent = `${inning} ${String(count.balls ?? 0)}-${String(count.strikes ?? 0)} ${speed} mph ${type}, zone ${zone}: ${details.description || "Pitch"} | ${batter} vs ${pitcher}`;
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
  elements.demo.addEventListener("click", async () => {
    try {
      await startDemo();
    } catch (error) {
      elements.message.textContent = `The cached game is unavailable: ${error.message}`;
    }
  });
  elements.demoReset.addEventListener("click", async () => {
    try {
      await startDemo();
    } catch (error) {
      elements.message.textContent = `The cached game is unavailable: ${error.message}`;
    }
  });
  elements.demoStep.addEventListener("click", async () => {
    try {
      if (!demo.active) await startDemo();
      else {
        stopDemoPlayback();
        stepDemo();
      }
    } catch (error) {
      elements.message.textContent = `The cached game is unavailable: ${error.message}`;
    }
  });
  elements.demoPlay.addEventListener("click", async () => {
    try {
      if (!demo.active || demo.index === demo.pitches.length - 1) await startDemo();
      stopDemoPlayback();
      demo.timer = window.setInterval(() => {
        if (demo.index === demo.pitches.length - 1) {
          stopDemoPlayback();
          return;
        }
        stepDemo();
      }, 250);
    } catch (error) {
      elements.message.textContent = `The cached game is unavailable: ${error.message}`;
    }
  });
  refresh();
})();
