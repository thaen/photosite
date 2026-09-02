(() => {
  "use strict";

  const API = "https://statsapi.mlb.com/api";
  const MARINERS_ID = 136;
  const LIVE_REFRESH_MS = 10_000;
  const SCHEDULE_REFRESH_MS = 120_000;
  let state = { game: null, feed: null, timecode: null, timer: null };

  const elements = {
    status: document.querySelector("#game-title"),
    score: document.querySelector("#score"),
    detail: document.querySelector("#detail"),
    updated: document.querySelector("#updated"),
    message: document.querySelector("#message"),
    pitches: document.querySelector("#pitches"),
    refresh: document.querySelector("#refresh"),
  };

  function pacificDate() {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Los_Angeles",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
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

  function renderGame(game, feed) {
    if (!game) {
      elements.status.textContent = "No Mariners game is scheduled today.";
      elements.score.textContent = "";
      elements.detail.textContent = "The page will check again in two minutes while it is open.";
      elements.message.textContent = "";
      return;
    }

    const away = game.teams.away;
    const home = game.teams.home;
    const status = feed?.gameData?.status?.detailedState || game.status.detailedState;
    elements.status.textContent = status;
    elements.score.textContent = `${away.team.abbreviation ?? away.team.name} ${away.score ?? "–"}  ·  ${home.team.abbreviation ?? home.team.name} ${home.score ?? "–"}`;
    elements.detail.textContent = `${away.team.name} at ${home.team.name}`;
    elements.updated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  }

  function pitchRows(feed) {
    const plays = feed?.liveData?.plays?.allPlays || [];
    return plays.flatMap((play) => play.playEvents
      .filter((event) => event.isPitch)
      .map((event) => ({ play, event })))
      .reverse();
  }

  function renderPitches(feed) {
    const rows = pitchRows(feed);
    elements.pitches.replaceChildren();
    if (!rows.length) {
      elements.message.textContent = "Pitches will appear when MLB reports them.";
      return;
    }
    elements.message.textContent = `${rows.length} tracked pitches`;
    for (const { play, event } of rows) {
      const details = event.details || {};
      const pitchData = event.pitchData || {};
      const count = event.count || {};
      const pitcher = play.matchup?.pitcher?.fullName || "Pitcher";
      const batter = play.matchup?.batter?.fullName || "Batter";
      const speed = pitchData.startSpeed == null ? "speed unavailable" : `${pitchData.startSpeed.toFixed(1)} mph`;
      const type = details.type?.description || "pitch type unavailable";
      const zone = pitchData.zone == null ? "zone unavailable" : `zone ${pitchData.zone}`;
      const inning = `${play.about?.halfInning === "top" ? "Top" : "Bottom"} ${play.about?.inning ?? ""}`;
      const item = document.createElement("li");
      item.className = "pitch";
      item.innerHTML = `<div class="pitch-main"><span class="pitch-call"></span><span></span></div><div class="pitch-meta"></div>`;
      item.querySelector(".pitch-call").textContent = details.description || "Pitch";
      item.querySelector(".pitch-main span:last-child").textContent = `${speed} ${type}`;
      item.querySelector(".pitch-meta").textContent = `${inning} · ${batter} vs ${pitcher} · ${count.balls ?? 0}-${count.strikes ?? 0} · ${zone}`;
      elements.pitches.append(item);
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
      if (operation.op === "remove") {
        Array.isArray(parent) ? parent.splice(Number(key), 1) : delete parent[key];
      } else if (operation.op === "add" && Array.isArray(parent)) {
        parent.splice(key === "-" ? parent.length : Number(key), 0, operation.value);
      } else if (operation.op === "add" || operation.op === "replace") {
        parent[key] = operation.value;
      } else {
        throw new Error(`Unsupported MLB patch operation: ${operation.op}`);
      }
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
    if (Array.isArray(patch)) patchDocument(state.feed, patch);
    else state.feed = patch;
    state.timecode = newest;
  }

  async function refresh() {
    clearTimer();
    if (document.hidden) return;
    try {
      const game = await findGame();
      if (!game || state.game?.gamePk !== game.gamePk) {
        state = { game, feed: null, timecode: null, timer: null };
      } else {
        state.game = game;
      }
      if (game) await updateLiveFeed();
      renderGame(game, state.feed);
      if (state.feed) renderPitches(state.feed);
      else elements.pitches.replaceChildren();
      scheduleNext(game && isLive(game) ? LIVE_REFRESH_MS : SCHEDULE_REFRESH_MS);
    } catch (error) {
      elements.message.textContent = `The feed is unavailable: ${error.message}`;
      scheduleNext(SCHEDULE_REFRESH_MS);
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearTimer();
    else refresh();
  });
  elements.refresh.addEventListener("click", refresh);
  refresh();
})();
