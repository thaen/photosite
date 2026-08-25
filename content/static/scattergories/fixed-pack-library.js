(() => {
  "use strict";

  const packs = window.PHOTOSITE_FIXED_PACKS;
  if (!Array.isArray(packs)) throw new Error("Fixed Scattergories packs did not load.");

  function openLibrary() {
    document.querySelector(".photosite-fixed-library")?.remove();
    const panel = document.createElement("section");
    panel.className = "photosite-fixed-library";
    panel.innerHTML = '<button type="button" class="photosite-fixed-library-close">Close</button><h1>Categories</h1><p>24 fixed lists. New List advances by one complete list.</p>';
    panel.querySelector("button").addEventListener("click", () => panel.remove());
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
    openLibrary();
  }, true);

  const style = document.createElement("style");
  style.textContent = ".photosite-fixed-library{position:absolute;inset:0;z-index:2000000;overflow:auto;background:var(--secondary,#fff);color:var(--primary,#000);padding:1rem}.photosite-fixed-library h1{margin:.2rem 0;font-size:2rem}.photosite-fixed-library p{margin:.2rem 0 1.2rem}.photosite-fixed-library-close{position:sticky;top:0;float:right;border:3px solid var(--primary,#000);padding:.4rem .7rem}.fixed-pack{clear:both;border-bottom:3px solid var(--primary,#000)}.fixed-pack-heading{margin:0;background:var(--primary,#000);color:var(--secondary,#fff);font-family:Mono,monospace;font-size:1rem;letter-spacing:.08em;padding:.7rem .6rem .55rem;text-transform:uppercase}.fixed-pack ol{margin:0;padding:0;list-style-position:inside}.fixed-pack li{padding:.35rem .6rem;border-bottom:1px solid rgba(var(--primary-rgb),.14)}.fixed-pack li:last-child{border-bottom:0}@media (max-width:799px){.photosite-fixed-library{font-size:1.35rem}.photosite-fixed-library h1{font-size:2.7rem}.photosite-fixed-library-close{font-size:1.35rem}.fixed-pack-heading{font-size:1.35rem}}";
  document.head.append(style);
})();
