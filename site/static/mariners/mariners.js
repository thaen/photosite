(() => {
  "use strict";

  const API = "https://statsapi.mlb.com/api";
  const MARINERS_ID = 136;
  const LIVE_REFRESH_MS = 10_000;
  const SCHEDULE_REFRESH_MS = 120_000;
  const OPENING_ALIGNMENTS = {
    136: { P: 693433, C: 663728, "1B": 647304, "2B": 702284, "3B": 801126, SS: 641487, LF: 668227, CF: 677594, RF: 686527 },
    111: { P: 699151, C: 657136, "1B": 681508, "2B": 686765, "3B": 702332, SS: 596115, LF: 680776, CF: 678882, RF: 701350 },
  };
  let state = { game: null, feed: null, timecode: null, timer: null, seenPitches: new Set() };
  let demo = { active: false, index: 0, timer: null, source: null, pitches: [] };
  let pitchFeedExpanded = false;

  const elements = {
    scoreboard: document.querySelector("#scoreboard"),
    field: document.querySelector("#field"),
    fieldNote: document.querySelector("#field-note"),
    message: document.querySelector("#message"),
    pitches: document.querySelector("#pitches"),
    pitchToggle: document.querySelector("#pitch-toggle"),
    refresh: document.querySelector("#refresh"),
    demo: document.querySelector("#demo"),
    demoReset: document.querySelector("#demo-reset"),
    demoStep: document.querySelector("#demo-step"),
    demoPlay: document.querySelector("#demo-play"),
    updated: document.querySelector("#updated"),
    currentPitch: document.querySelector("#current-pitch"),
    recentInnings: document.querySelector("#recent-innings"),
    pitchZone: document.querySelector("#pitch-zone"),
    zoneCells: document.querySelector("#zone-cells"),
    boxScore: document.querySelector("#box-score"),
    awayLineup: document.querySelector("#away-lineup"),
    homeLineup: document.querySelector("#home-lineup"),
    playerDirectory: document.querySelector("#player-directory"),
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
      .concat([{
        ...play,
        about: { ...play.about, isComplete: isLastPitch },
        playEvents: play.playEvents.filter((candidate) => candidate.index <= event.index),
      }]);
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
    pitchFeedExpanded = false;
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
    renderScoresheet(state.game, state.feed);
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

  function currentPlay(feed) {
    return feed?.liveData?.plays?.allPlays?.at(-1) || null;
  }

  function currentPitch(feed) {
    return currentPlay(feed)?.playEvents?.filter((event) => event.isPitch).at(-1) || null;
  }

  function teamForHalf(feed, halfInning) {
    const side = halfInning === "top" ? "home" : "away";
    return feed?.liveData?.boxscore?.teams?.[side] || null;
  }

  function playerAtPosition(team, position) {
    return Object.values(team?.players || []).find((player) => player.position?.abbreviation === position)?.person || null;
  }

  function defenseForPlay(feed) {
    const play = currentPlay(feed);
    const team = teamForHalf(feed, play?.about?.halfInning);
    const directory = playerDirectory(feed);
    const opening = OPENING_ALIGNMENTS[team?.team?.id];
    const alignment = Object.fromEntries(Object.entries(opening || {}).map(([position, id]) => [position, directory.get(id)?.person || null]));
    for (const priorPlay of visiblePlays(feed)) {
      const priorTeam = teamForHalf(feed, priorPlay.about?.halfInning);
      if (priorTeam?.team?.id !== team?.team?.id) continue;
      for (const event of priorPlay.playEvents || []) {
        if (!event.isSubstitution || !["defensive_substitution", "pitching_substitution"].includes(event.details?.eventType)) continue;
        const position = event.position?.abbreviation;
        if (position) alignment[position] = directory.get(event.player?.id)?.person || event.player;
      }
    }
    return {
      team: team?.team,
      center: alignment.CF || playerAtPosition(team, "CF"),
      left: alignment.LF || playerAtPosition(team, "LF"),
      right: alignment.RF || playerAtPosition(team, "RF"),
      shortstop: alignment.SS || playerAtPosition(team, "SS"),
      second: alignment["2B"] || playerAtPosition(team, "2B"),
      third: alignment["3B"] || playerAtPosition(team, "3B"),
      first: alignment["1B"] || playerAtPosition(team, "1B"),
      pitcher: play?.matchup?.pitcher || alignment.P || playerAtPosition(team, "P"),
      catcher: alignment.C || playerAtPosition(team, "C"),
    };
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
    const defense = defenseForPlay(feed);
    const offense = linescore.offense;
    const directory = playerDirectory(feed);
    const mariners = new Set(Object.values(feed.liveData?.boxscore?.teams || {})
      .filter((team) => String(team.team?.id) === String(MARINERS_ID))
      .flatMap((team) => Object.values(team.players || []).map((player) => player.person.id)));
    const number = (person) => person ? directory.get(person.id)?.jerseyNumber || "?" : "-";
    const setText = (id, text, person, useTeamColor = true) => {
      const label = document.querySelector(`#${id}`);
      label.textContent = text;
      label.classList.toggle("mariner", useTeamColor && mariners.has(person?.id));
    };
    setText("fielder-center", number(defense.center), defense.center, true);
    setText("fielder-left", number(defense.left), defense.left, true);
    setText("fielder-right", number(defense.right), defense.right, true);
    setText("fielder-shortstop", number(defense.shortstop), defense.shortstop, true);
    setText("fielder-second", number(defense.second), defense.second, true);
    setText("fielder-third", number(defense.third), defense.third, true);
    setText("fielder-first", number(defense.first), defense.first, true);
    setText("fielder-pitcher", number(defense.pitcher), defense.pitcher, true);
    setText("fielder-catcher", number(defense.catcher), defense.catcher, true);
    setText("runner-second", number(offense.second), offense.second, true);
    setText("runner-third", number(offense.third), offense.third, true);
    setText("runner-first", number(offense.first), offense.first, true);
    setText("batter", number(offense.batter), offense.batter, true);
    elements.field.setAttribute("aria-label", `Defensive alignment for ${defense.team?.name || "the fielding team"}; batter and runners are shown at the bases.`);
    elements.fieldNote.textContent = demo.active
      ? "Seattle players are teal and Boston players are white. The defensive team and pitcher follow this cached pitch."
      : "Seattle players are teal and Boston players are white.";
  }

  function tableRow(cells, header = false) {
    const row = document.createElement("tr");
    for (const value of cells) {
      const cell = document.createElement(header ? "th" : "td");
      cell.textContent = value;
      row.append(cell);
    }
    return row;
  }

  function fillTable(table, headers, rows) {
    table.replaceChildren(tableRow(headers, true), ...rows.map((row) => tableRow(row)));
  }

  function visiblePlays(feed) {
    return feed?.liveData?.plays?.allPlays || [];
  }

  function teamTotals(feed, side, game) {
    const hitTypes = new Set(["single", "double", "triple", "home_run"]);
    const plays = visiblePlays(feed);
    const score = game?.teams?.[side]?.score ?? 0;
    const isAway = side === "away";
    const hits = plays.filter((play) => hitTypes.has(play.result?.eventType)
      && (isAway ? play.matchup?.batter?.id !== undefined && play.about?.isTopInning : !play.about?.isTopInning)).length;
    const errors = plays.filter((play) => play.result?.eventType === "error"
      && (isAway ? !play.about?.isTopInning : play.about?.isTopInning)).length;
    return { score, hits, errors };
  }

  function renderPitchZone(feed) {
    const current = currentPitch(feed)?.pitchData?.zone;
    elements.zoneCells.replaceChildren();
    const zones = [
      [1, 42, 38], [2, 66, 38], [3, 90, 38],
      [4, 42, 62], [5, 66, 62], [6, 90, 62],
      [7, 42, 86], [8, 66, 86], [9, 90, 86],
      [11, 10, 10], [12, 114, 10], [13, 10, 114], [14, 114, 114],
    ];
    for (const [zone, x, y] of zones) {
      const cell = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      cell.setAttribute("class", `zone-cell ${zone <= 9 ? "zone-strike" : "zone-ball"}`);
      cell.setAttribute("data-zone", zone);
      cell.setAttribute("data-current", String(zone === current));
      cell.setAttribute("x", x);
      cell.setAttribute("y", y);
      cell.setAttribute("width", 24);
      cell.setAttribute("height", 24);
      elements.zoneCells.append(cell);
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", x + 12);
      label.setAttribute("y", y + 17);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("fill", "#fff");
      label.setAttribute("font-size", "12");
      label.textContent = zone;
      elements.zoneCells.append(label);
    }
    elements.pitchZone.setAttribute("aria-label", `Pitch zone${current ? `; zone ${current} is current` : ""}`);
  }

  function renderLineup(table, team, currentBatter) {
    const players = team?.batters?.map((id) => team.players[`ID${id}`]).filter(Boolean) || [];
    const header = tableRow(["#", "Player", "No.", "Pos."], true);
    const rows = players.map((player, index) => {
      const row = tableRow([index + 1, player.person.fullName, player.jerseyNumber || "-", player.position?.abbreviation || "-"]);
      row.classList.toggle("is-current-batter", player.person.id === currentBatter?.id);
      return row;
    });
    table.replaceChildren(header, ...rows);
  }

  function renderBoxScore(feed) {
    const teams = feed?.liveData?.boxscore?.teams;
    if (!teams) {
      elements.boxScore.textContent = "";
      return;
    }
    const rows = ["away", "home"].flatMap((side) => Object.values(teams[side].players)
      .filter((player) => player.stats?.batting?.plateAppearances)
      .slice(0, 9)
      .map((player) => [teams[side].team.id === MARINERS_ID ? "SEA" : "BOS", player.person.fullName, player.stats.batting.atBats || 0, player.stats.batting.hits || 0, player.stats.batting.runs || 0, player.stats.batting.rbi || 0]));
    const headers = ["TEAM", "PLAYER", "AB", "H", "R", "RBI"];
    const widths = headers.map((header, index) => Math.max(header.length, ...rows.map((row) => String(row[index]).length)));
    elements.boxScore.textContent = [headers, ...rows]
      .map((row) => row.map((value, index) => String(value).padEnd(widths[index])).join("  ").trimEnd())
      .join("\n");
  }

  function renderPlayerDirectory(feed) {
    const teams = feed?.liveData?.boxscore?.teams;
    if (!teams) {
      elements.playerDirectory.replaceChildren();
      return;
    }
    const rows = ["away", "home"].flatMap((side) => Object.values(teams[side].players)
      .filter((player) => player.position?.abbreviation && player.position.abbreviation !== "Bench")
      .map((player) => [teams[side].team.name, player.person.fullName, player.jerseyNumber || "-", player.position.abbreviation]));
    fillTable(elements.playerDirectory, ["Team", "Player", "No.", "Pos."], rows);
  }

  function renderScoresheet(game, feed) {
    renderPitchZone(feed);
    const teams = feed?.liveData?.boxscore?.teams;
    const batter = currentPlay(feed)?.matchup?.batter;
    const pitch = currentPitch(feed);
    elements.currentPitch.textContent = pitch
      ? `Zone ${pitch.pitchData?.zone ?? "-"}: ${pitch.details?.description || "Pitch"}`
      : "No pitch has been recorded.";
    renderRecentInnings(feed);
    renderBoxScore(feed);
    renderLineup(elements.awayLineup, teams?.away, batter);
    renderLineup(elements.homeLineup, teams?.home, batter);
    renderPlayerDirectory(feed);
  }

  function pitchRows(feed) {
    const plays = feed?.liveData?.plays?.allPlays || [];
    return plays.flatMap((play) => play.playEvents
      .filter((event) => event.isPitch)
      .map((event) => ({ play, event, key: `${play.atBatIndex}:${event.index}` })))
      .reverse();
  }

  function completedPlays(feed) {
    return visiblePlays(feed).filter((play) => play.about?.isComplete);
  }

  function renderRecentInnings(feed) {
    const teams = feed?.liveData?.boxscore?.teams || {};
    const playsByIndex = new Map(completedPlays(feed).map((play) => [play.about?.atBatIndex, play]));
    const innings = feed?.liveData?.plays?.playsByInning || [];
    const latest = innings.flatMap((inning, index) => ["top", "bottom"].map((half) => {
      const plays = (inning[half] || []).map((atBatIndex) => playsByIndex.get(atBatIndex)).filter(Boolean);
      if (!plays.length) return null;
      return { key: `${half === "top" ? "T" : "B"}${index + 1}`, side: half === "top" ? "away" : "home", plays };
    })).filter(Boolean).slice(-2).reverse();
    elements.recentInnings.replaceChildren(...latest.map((group) => {
      const item = document.createElement("li");
      const team = teams[group.side]?.team?.name || group.side;
      item.textContent = `${group.key} ${team} — ${group.plays.map((play) => play.result?.description || play.result?.event || "Plate appearance").join("; ")}`;
      return item;
    }));
  }

  function renderPitches(feed) {
    const rows = pitchRows(feed);
    const firstRender = state.seenPitches.size === 0;
    const directory = playerDirectory(feed);
    elements.pitches.replaceChildren();
    if (!rows.length) {
      elements.message.textContent = "Pitches will appear when MLB reports them.";
      elements.pitchToggle.hidden = true;
      return;
    }
    const visibleRows = pitchFeedExpanded ? rows : rows.slice(0, 10);
    elements.message.textContent = `${rows.length} pitches. ${pitchFeedExpanded ? "Showing all pitches." : `Showing the 10 most recent.`} Format: inning, count, mph, type, zone, result, batter versus pitcher.`;
    elements.pitchToggle.hidden = rows.length <= 10;
    elements.pitchToggle.textContent = pitchFeedExpanded ? "Show recent 10 pitches" : `Show all ${rows.length} pitches`;
    elements.pitchToggle.setAttribute("aria-expanded", String(pitchFeedExpanded));
    let priorBatterId = null;
    let stripe = false;
    for (const { play, event, key } of visibleRows) {
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
      const batterId = String(play.matchup?.batter?.id || "");
      if (batterId !== priorBatterId) stripe = !stripe;
      priorBatterId = batterId;
      item.className = `pitch${stripe ? " batter-stripe" : ""}${!firstRender && !state.seenPitches.has(key) ? " new" : ""}`;
      item.dataset.batterId = batterId;
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
      renderScoresheet(game, state.feed);
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
  elements.pitchToggle.addEventListener("click", () => {
    pitchFeedExpanded = !pitchFeedExpanded;
    renderPitches(state.feed);
  });
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
