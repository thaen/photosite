(() => {
  "use strict";

  const packs = window.PHOTOSITE_FIXED_PACKS;
  if (!Array.isArray(packs) || packs.length !== 24 || packs.some(pack => !Array.isArray(pack.categories) || pack.categories.length !== 12)) {
    throw new Error("The fixed Scattergories packs are unavailable or malformed.");
  }

  function install(app) {
    if (!app || app.__photositeFixedPacksInstalled) return Boolean(app);
    app.__photositeFixedPacksInstalled = true;
    app.$set(app, "fixedPacks", packs);
    app.$set(app, "fixedPackIndex", 0);
    app.generateWords = function generateFixedPack() {
      this.currentWords = this.fixedPacks[this.fixedPackIndex].categories.map(category => ({ category, isCustom: false, isAdult: false }));
      this.fixedPackIndex = (this.fixedPackIndex + 1) % this.fixedPacks.length;
    };
    app.generateWords();
    app.editWordlist = function editFixedPackLibrary() {
      if (this.gameState === "IN_GAME") this.pauseGame();
      this.state.editingLists = !this.state.editingLists;
      if (this.state.editingLists) this.$nextTick(renderFixedPackLibrary);
    };
    return true;
  }

  function renderFixedPackLibrary() {
    const wrap = document.querySelector(".words-wrap");
    if (!wrap) return;
    wrap.innerHTML = "";
    packs.forEach(pack => {
      const section = document.createElement("section");
      section.className = "fixed-pack";
      const heading = document.createElement("h2");
      heading.className = "fixed-pack-heading";
      heading.textContent = pack.name;
      const list = document.createElement("ol");
      pack.categories.forEach(category => {
        const item = document.createElement("li");
        item.textContent = category;
        list.append(item);
      });
      section.append(heading, list);
      wrap.append(section);
    });
  }

  function waitForApp() {
    const app = document.querySelector("#view").__vue__;
    if (install(app)) return;
    window.setTimeout(waitForApp, 20);
  }
  waitForApp();

  function showFixedPackLibrary() {
    document.querySelector(".photosite-fixed-library")?.remove();
    const panel = document.createElement("section");
    panel.className = "photosite-fixed-library";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "photosite-fixed-library-close";
    close.textContent = "Close";
    close.addEventListener("click", () => panel.remove());
    const title = document.createElement("h1");
    title.textContent = "Categories";
    const note = document.createElement("p");
    note.textContent = "24 fixed lists. New List advances by one complete list.";
    panel.append(close, title, note);
    packs.forEach(pack => {
      const section = document.createElement("section");
      section.className = "fixed-pack";
      const heading = document.createElement("h2");
      heading.className = "fixed-pack-heading";
      heading.textContent = pack.name;
      const list = document.createElement("ol");
      pack.categories.forEach(category => {
        const item = document.createElement("li");
        item.textContent = category;
        list.append(item);
      });
      section.append(heading, list);
      panel.append(section);
    });
    document.querySelector(".frame").append(panel);
  }

  document.addEventListener("click", event => {
    const button = event.target.closest(".clickable-label");
    if (!button || button.textContent.trim() !== "Categories") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    showFixedPackLibrary();
  }, true);
  const style = document.createElement("style");
  style.textContent = ".photosite-fixed-library{position:absolute;inset:0;z-index:2000000;overflow:auto;background:var(--secondary,#fff);color:var(--primary,#000);padding:1rem}.photosite-fixed-library h1{margin:.2rem 0;font-size:2rem}.photosite-fixed-library p{margin:.2rem 0 1.2rem}.photosite-fixed-library-close{position:sticky;top:0;float:right;border:3px solid var(--primary,#000);padding:.4rem .7rem}.fixed-pack{clear:both;border-bottom:3px solid var(--primary,#000)}.fixed-pack-heading{margin:0;background:var(--primary,#000);color:var(--secondary,#fff);font-family:Mono,monospace;font-size:1rem;letter-spacing:.08em;padding:.7rem .6rem .55rem;text-transform:uppercase}.fixed-pack ol{margin:0;padding:0;list-style-position:inside}.fixed-pack li{padding:.35rem .6rem;border-bottom:1px solid rgba(var(--primary-rgb),.14)}.fixed-pack li:last-child{border-bottom:0}";
  document.head.append(style);
})();
