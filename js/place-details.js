/* =========================================================
   MOVA PLACE DETAILS
   Fast, source-first loading with progressive rendering.
   Independent sources load in parallel so the page does not wait for the
   slowest provider before showing useful information.
========================================================= */

document.addEventListener("DOMContentLoaded", () => {
  const p = new URLSearchParams(location.search);
  const name = p.get("place") || "Unknown Place";
  const region = p.get("region") || "INDIA";

  document.title = `${name} — MOVA`;
  document.getElementById("place-title").textContent = name;
  const regionLabel = document.getElementById("place-region");
  regionLabel.textContent = region;
  // These labels are real immediately from the URL; they are not async content.
  regionLabel.classList.remove("skeleton-text", "skeleton-region");
  const meta = document.getElementById("place-meta");
  meta?.querySelectorAll(".skeleton-pill, .meta-skeleton").forEach((node) => node.remove());

  setupTabs();
  setupPlanButton(name, p.get("destination_id"));
  loadCommunity(name, p.get("destination_id"));
  renderHeroImage(p.get("image"), p.get("image_source"), p.get("image_url"), name);
  // Place Details must never be held hostage by a remote provider or a JS error.
  try {
    loadPlaceData(name, p);
  } catch (error) {
    console.error("MOVA Place Details startup failed:", error);
    forcePlaceDetailsFallback(name, p);
  }
});

function escapeHtml(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setMetaChip(text) {
  const meta = document.getElementById("place-meta");
  if (!meta || !text) return;
  if ([...meta.children].some((c) => c.textContent === text)) return;
  meta.insertAdjacentHTML("beforeend", `<span class="place-meta-chip">${escapeHtml(text)}</span>`);
}

function clearSkeleton(node) {
  if (!node) return;
  node.classList.remove("loading-panel");
}

function addSource(label, url) {
  const c = document.getElementById("place-sources");
  if (!c || !url) return;
  if ([...c.querySelectorAll("a")].some((a) => a.href === url)) return;
  // Remove the placeholder bars shipped in the initial HTML, even on older markup
  // that does not label them with .source-loading.
  c.querySelectorAll(".source-loading, .skeleton-line, .skeleton-text, .skeleton-pill").forEach((node) => node.remove());
  c.insertAdjacentHTML(
    "beforeend",
    `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)} ↗</a>`
  );
}

function renderHeroImage(url, source, pageUrl, name) {
  const box = document.getElementById("place-hero-image");
  const media = document.getElementById("place-hero-media");
  if (!box || !media || !url) return;

  const img = new Image();
  img.alt = name;
  img.referrerPolicy = "no-referrer";
  img.onload = () => {
    box.hidden = false;
    box.innerHTML = `<img src="${escapeHtml(url)}" alt="${escapeHtml(name)}" referrerpolicy="no-referrer">${source ? `<span>${escapeHtml(source)}</span>` : ""}`;
    media.querySelector(".hero-image-skeleton")?.remove();
    if (pageUrl) addSource(source || "Image source", pageUrl);
  };
  img.onerror = () => {
    // Keep the skeleton briefly, then turn it into an honest no-image state.
    media.querySelector(".hero-image-skeleton")?.remove();
    media.insertAdjacentHTML("beforeend", `<div class="image-unavailable"><strong>NO SOURCED IMAGE</strong><span>MOVA could not verify an image for this place.</span></div>`);
  };
  img.src = url;
}

function setupTabs() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.tab;
      document.querySelectorAll(".tab-button").forEach((item) => {
        const active = item === button;
        item.classList.toggle("active", active);
        item.setAttribute("aria-selected", String(active));
      });
      document.querySelectorAll(".tab-content").forEach((content) => {
        const active = content.id === `tab-${target}`;
        content.hidden = !active;
        content.classList.toggle("active", active);
      });
    });
  });
}

function setupPlanButton(name, id) {
  const button = document.getElementById("btn-add-plan");
  if (!button) return;
  button.disabled = false;
  button.addEventListener("click", () => {
    let list = [];
    try {
      const saved = localStorage.getItem("movaDraftMustVisitPlaces");
      if (saved) list = JSON.parse(saved);
    } catch {}
    if (Array.isArray(list) && !list.includes(name)) {
      list.push(name);
      localStorage.setItem("movaDraftMustVisitPlaces", JSON.stringify(list));
    } else if (!Array.isArray(list)) {
      localStorage.setItem("movaDraftMustVisitPlaces", JSON.stringify([name]));
    }
    const p = new URLSearchParams(location.search);
    const destination = p.get("region") || id || name;
    location.href = `create-plan.html?${new URLSearchParams({ destination })}`;
  });
}

function renderMap(lat, lon, title, sourceUrl = null) {
  const box = document.getElementById("place-map");
  if (!box) return;

  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    box.innerHTML = `<div class="map-unavailable"><strong>MAP LOCATION NOT FOUND</strong><span>Current sources did not provide coordinates.</span></div>`;
    document.getElementById("map-source").textContent = "NO COORDINATES";
    return;
  }

  const d = 0.012;
  const bbox = [lon - d, lat - d, lon + d, lat + d].join(",");
  const src = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(bbox)}&layer=mapnik&marker=${encodeURIComponent(`${lat},${lon}`)}`;
  box.innerHTML = `<iframe title="OpenStreetMap map for ${escapeHtml(title)}" src="${src}" loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe><a class="map-open-link" href="https://www.openstreetmap.org/?mlat=${encodeURIComponent(lat)}&mlon=${encodeURIComponent(lon)}#map=16/${encodeURIComponent(lat)}/${encodeURIComponent(lon)}" target="_blank" rel="noopener noreferrer">OPEN FULL MAP ↗</a>`;
  document.getElementById("map-source").textContent = "OPENSTREETMAP";
  if (sourceUrl) addSource("OpenStreetMap record", sourceUrl);
}

function renderPracticalFromParams(p) {
  const container = document.getElementById("place-practical-content");
  if (!container) return;

  const fields = [
    ["LOCATION", p.get("address") || "Looking up a sourced location…"],
    ["OPENING HOURS", p.get("opening_hours") || "Unknown from current sources."],
    ["ENTRY FEE", p.get("fee") || "Unknown from current sources."],
  ];

  container.classList.remove("loading-panel");
  container.innerHTML = fields.map(([label, value]) =>
    `<div class="practical-card"><h4>${escapeHtml(label)}</h4><p>${escapeHtml(value)}</p></div>`
  ).join("");

  const website = p.get("website");
  if (website) {
    let safeWebsite = "";
    try {
      const parsed = new URL(website);
      if (["http:", "https:"].includes(parsed.protocol)) safeWebsite = parsed.href;
    } catch {}
    if (safeWebsite) {
      container.insertAdjacentHTML("beforeend", `<div class="practical-card"><h4>WEBSITE</h4><p><a href="${escapeHtml(safeWebsite)}" target="_blank" rel="noopener noreferrer">Open listed website ↗</a></p></div>`);
    }
  }
  container.insertAdjacentHTML("beforeend", `<div class="practical-card"><h4>DATA STATUS</h4><p>Details are shown only when a source provides them.</p></div>`);
}

function fetchWithTimeout(url, options = {}, ms = 8000) {
  const c = new AbortController();
  const timer = setTimeout(() => c.abort(new Error("Timeout")), ms);
  return fetch(url, { ...options, signal: c.signal }).finally(() => clearTimeout(timer));
}

async function searchCoordinates(name) {
  const key = `cache:coords:${name}`;
  try { const c = sessionStorage.getItem(key); if (c) return JSON.parse(c); } catch {}
  const params = new URLSearchParams({ q: `${name}, India`, format: "jsonv2", limit: "1", countrycodes: "in", addressdetails: "1" });
  try {
    const response = await fetchWithTimeout(`https://nominatim.openstreetmap.org/search?${params}`, { headers: { "User-Agent": "MOVA travel discovery" }, cache: "no-store" }, 10000);
    if (!response.ok) return null;
    const results = await response.json();
    const item = results[0];
    const data = item ? {
      lat: Number(item.lat),
      lon: Number(item.lon),
      address: item.display_name,
      sourceUrl: item.osm_id ? `https://www.openstreetmap.org/${item.osm_type}/${item.osm_id}` : null
    } : null;
    if (data) sessionStorage.setItem(key, JSON.stringify(data));
    return data;
  } catch { return null; }
}

function parseWikipediaReference(name, wikipediaReference) {
  let language = "en";
  let title = String(name || "Unknown_Place").trim().replace(/\s+/g, "_");
  if (!wikipediaReference) return { language, title };

  try {
    const reference = String(wikipediaReference).trim();
    if (/^https?:\/\//i.test(reference)) {
      const url = new URL(reference);
      const match = url.hostname.match(/^([a-z-]+)\.wikipedia\.org$/i);
      if (match) language = match[1].toLowerCase();
      const pathMatch = url.pathname.match(/\/wiki\/(.+)$/i);
      if (pathMatch) title = decodeURIComponent(pathMatch[1]).split("#")[0];
    } else {
      title = decodeURIComponent(reference).replace(/^\/wiki\//, "").split("#")[0];
    }
  } catch {
    title = String(wikipediaReference).replace(/^.*\/wiki\//, "").split("#")[0] || title;
  }

  title = title.replaceAll(" ", "_").trim();
  return { language, title: title || String(name || "Unknown_Place").replace(/\s+/g, "_") };
}

async function fetchWikipedia(name, wikipediaReference) {
  const { language, title } = parseWikipediaReference(name, wikipediaReference);
  const key = `cache:wiki:v2:${language}:${title}`;
  try {
    const cached = sessionStorage.getItem(key);
    if (cached) {
      const parsed = JSON.parse(cached);
      if (parsed?.extract) return parsed;
    }
  } catch {}

  const base = `https://${language}.wikipedia.org`;

  // First try the compact REST summary endpoint.
  try {
    const restUrl = `${base}/api/rest_v1/page/summary/${encodeURIComponent(title)}`;
    const response = await fetchWithTimeout(restUrl, { headers: { Accept: "application/json" } }, 8500);
    if (response.ok) {
      const data = await response.json();
      if (data?.extract && data.type !== "disambiguation") {
        try { sessionStorage.setItem(key, JSON.stringify(data)); } catch {}
        return data;
      }
    }
  } catch {}

  // Fallback to MediaWiki's public API. It often succeeds when the REST
  // summary endpoint has no summary for a page or is temporarily unavailable.
  try {
    const params = new URLSearchParams({
      action: "query",
      prop: "extracts|info|coordinates",
      titles: title.replaceAll("_", " "),
      exintro: "1",
      explaintext: "1",
      exchars: "6000",
      inprop: "url",
      colimit: "1",
      format: "json",
      formatversion: "2",
      origin: "*"
    });
    const response = await fetchWithTimeout(`${base}/w/api.php?${params}`, { headers: { Accept: "application/json" } }, 8500);
    if (!response.ok) return null;
    const payload = await response.json();
    const page = payload?.query?.pages?.[0];
    if (!page || page.missing !== undefined || !String(page.extract || "").trim()) return null;
    const data = {
      title: page.title || title.replaceAll("_", " "),
      extract: String(page.extract).trim(),
      content_urls: { desktop: { page: page.fullurl || `https://${language}.wikipedia.org/wiki/${encodeURIComponent(title)}` } },
      coordinates: page.coordinates || undefined
    };
    try { sessionStorage.setItem(key, JSON.stringify(data)); } catch {}
    return data;
  } catch {
    return null;
  }
}

async function fetchWikivoyage(name) {
  const title = encodeURIComponent(name.replaceAll(" ", "_"));
  const key = `cache:voyage:${title}`;
  try { const c = sessionStorage.getItem(key); if (c) return JSON.parse(c); } catch {}
  try {
    const response = await fetchWithTimeout(`https://en.wikivoyage.org/w/api.php?action=query&prop=extracts&explaintext=1&titles=${title}&format=json&origin=*`);
    if (!response.ok) return null;
    const data = await response.json();
    const pages = data.query?.pages || {};
    const id = Object.keys(pages)[0];
    const res = id && id !== "-1" ? pages[id].extract || null : null;
    if (res) sessionStorage.setItem(key, JSON.stringify(res));
    return res;
  } catch { return null; }
}

function splitUsefulSections(text) {
  return text
    ? text.split(/\n(?=[A-Z][A-Za-z &'/-]{2,60}\n)/).map((x) => x.trim()).filter(Boolean).slice(0, 12)
    : [];
}

function renderTextBlocks(container, text, fallback) {
  if (!container) return;
  const blocks = splitUsefulSections(text);
  container.classList.remove("loading-panel");
  if (!blocks.length) {
    container.innerHTML = `<p>${escapeHtml(fallback)}</p>`;
    return;
  }
  container.innerHTML = blocks.map((block) => {
    const lines = block.split("\n").filter(Boolean);
    const heading = lines.shift();
    return `<div class="practical-card"><h4>${escapeHtml(heading)}</h4><p>${escapeHtml(lines.join(" ").slice(0, 900))}</p></div>`;
  }).join("");
}

function withDeadline(promise, ms, label = "request") {
  let timer;
  const deadline = new Promise((resolve) => {
    timer = setTimeout(() => {
      console.warn(`MOVA Place Details: ${label} exceeded ${ms}ms`);
      resolve(null);
    }, ms);
  });
  return Promise.race([Promise.resolve(promise).catch((error) => {
    console.warn(`MOVA Place Details: ${label} failed`, error);
    return null;
  }), deadline]).finally(() => clearTimeout(timer));
}

function forcePlaceDetailsFallback(name, p = new URLSearchParams(location.search)) {
  const overview = document.getElementById("place-overview-content");
  const practical = document.getElementById("place-practical-content");
  const explore = document.getElementById("place-explore-content");
  const highlights = document.getElementById("sidebar-highlights");
  const description = String(p.get("description") || "").trim();
  const sources = document.getElementById("place-sources");
  if (sources && !sources.querySelector("a.source-link")) {
    sources.innerHTML = '<p class="source-empty">No source links were returned for this place.</p>';
  }
  if (overview) {
    overview.classList.remove("loading-panel");
    overview.innerHTML = description
      ? `<p>${escapeHtml(description)}</p><p class="source-note">Description supplied with the mapped place record.</p>`
      : `<div class="place-data-unavailable"><h3>${escapeHtml(name)}</h3><p>We couldn't load the article text automatically. The place page is available, and you can open the source search below.</p><a href="https://en.wikipedia.org/w/index.php?search=${encodeURIComponent(name)}" target="_blank" rel="noopener noreferrer">Search Wikipedia for ${escapeHtml(name)} ↗</a></div>`;
  }
  if (practical && practical.classList.contains("loading-panel")) renderPracticalFromParams(p);
  if (explore) {
    explore.classList.remove("loading-panel");
    if (!explore.textContent.trim() || explore.querySelector(".skeleton-line")) explore.innerHTML = `<p>Explore information could not be loaded automatically. Try the linked article search or check back later.</p>`;
  }
  if (highlights) {
    highlights.classList.remove("loading-panel");
    if (highlights.querySelector(".skeleton-line")) highlights.innerHTML = `<div class="highlight-item"><strong>DATA STATUS</strong><span>External information source timed out.</span></div>`;
  }
}

async function loadPlaceData(name, p) {
  const overview = document.getElementById("place-overview-content");
  const practical = document.getElementById("place-practical-content");
  const explore = document.getElementById("place-explore-content");
  const highlights = document.getElementById("sidebar-highlights");

  if (p.get("source") === "mova") setMetaChip("MOVA CANONICAL RECORD");
  if (p.get("source_url")) addSource("OpenStreetMap record", p.get("source_url"));
  if (p.get("wikipedia")) addSource("Wikipedia", p.get("wikipedia"));
  if (p.get("website")) addSource("Official / listed website", p.get("website"));
  // Render whatever practical facts are already available, but never let them
  // short-circuit the overview/explore/map providers. That early return was
  // leaving Place Details stuck on its loading skeleton for most entry paths.
  renderPracticalFromParams(p);
  // Remove the endless skeleton immediately. Use supplied place text while the
  // article request runs, then replace it with the sourced article if available.
  const initialDescription = String(p.get("description") || "").trim();
  if (overview) {
    overview.classList.remove("loading-panel");
    overview.innerHTML = initialDescription
      ? `<p>${escapeHtml(initialDescription)}</p><p class="source-note">Description supplied with the mapped place record. Looking for a fuller article…</p>`
      : `<p>Loading available background information for ${escapeHtml(name)}…</p>`;
  }

  // Run independent providers in parallel instead of waterfall loading.
  const rawLat = p.get("lat");
  const rawLon = p.get("lon");
  const hasCoordinates = rawLat !== null && rawLat.trim() !== "" && rawLon !== null && rawLon.trim() !== ""
    && Number.isFinite(Number(rawLat)) && Number.isFinite(Number(rawLon));
  const coordsPromise = withDeadline(hasCoordinates
    ? Promise.resolve({ lat: Number(rawLat), lon: Number(rawLon), address: p.get("address") || null, sourceUrl: p.get("source_url") || null })
    : searchCoordinates(name), 12000, "coordinates");
  const wikiPromise = withDeadline(fetchWikipedia(name, p.get("wikipedia")), 12000, "Wikipedia");
  const voyagePromise = withDeadline(fetchWikivoyage(name), 14000, "Wikivoyage");
  // Final watchdog: even a broken provider promise or unexpected rendering error
  // must not leave skeletons visible indefinitely.
  const pageWatchdog = setTimeout(() => forcePlaceDetailsFallback(name, p), 16000);

  coordsPromise.then((coords) => {
    if (coords) {
      setMetaChip(`${coords.lat.toFixed(4)}, ${coords.lon.toFixed(4)}`);
      renderMap(coords.lat, coords.lon, name, coords.sourceUrl || p.get("source_url"));
      if (coords.address && !p.get("address")) p.set("address", coords.address);
    } else {
      renderMap(null, null, name);
    }
  });

  wikiPromise.then(async (wiki) => {
    clearSkeleton(overview);
    if (wiki?.extract) {
      overview.innerHTML = `<p>${escapeHtml(wiki.extract)}</p>`;
      setMetaChip("WIKIPEDIA SUMMARY");
      if (wiki.content_urls?.desktop?.page) addSource("Wikipedia article", wiki.content_urls.desktop.page);
      if (wiki.coordinates?.[0]) {
        const lat = Number(wiki.coordinates[0].lat);
        const lon = Number(wiki.coordinates[0].lon);
        const map = document.getElementById("place-map");
        if (map?.querySelector(".map-skeleton")) renderMap(lat, lon, name, wiki.content_urls?.desktop?.page || null);
      }
      return;
    }

    // OSM descriptions are already attached to some discovered place records;
    // show that text immediately as a basic source-backed fallback.
    const osmDescription = String(p.get("description") || "").trim();
    if (osmDescription) {
      overview.innerHTML = `<p>${escapeHtml(osmDescription)}</p><p class="source-note">Description supplied by OpenStreetMap data.</p>`;
      setMetaChip("OPENSTREETMAP DESCRIPTION");
      if (p.get("source_url")) addSource("OpenStreetMap record", p.get("source_url"));
      return;
    }

    // Wikivoyage is fetched in parallel for the Explore tab. Reuse its text
    // here if Wikipedia did not have an article or summary.
    const voyageText = await voyagePromise;
    if (voyageText && String(voyageText).trim()) {
      overview.innerHTML = `<p>${escapeHtml(String(voyageText).trim().slice(0, 6000))}</p><p class="source-note">Background text from Wikivoyage.</p>`;
      setMetaChip("WIKIVOYAGE BACKUP");
      addSource("Wikivoyage", `https://en.wikivoyage.org/wiki/${encodeURIComponent(name.replaceAll(" ", "_"))}`);
      return;
    }

    const searchUrl = `https://${parseWikipediaReference(name, null).language}.wikipedia.org/w/index.php?search=${encodeURIComponent(name)}`;
    overview.innerHTML = `<div class="place-data-unavailable"><h3>PLACE INFORMATION IS TEMPORARILY UNAVAILABLE</h3><p>We could not retrieve a sourced description from Wikipedia, OpenStreetMap, or Wikivoyage. Try again later, or search Wikipedia directly.</p><a href="${escapeHtml(searchUrl)}" target="_blank" rel="noopener noreferrer">Search Wikipedia for ${escapeHtml(name)} ↗</a></div>`;
    addSource("Search Wikipedia", searchUrl);
  }).catch(() => {
    clearSkeleton(overview);
    overview.innerHTML = `<p>Place information could not be loaded right now. Please refresh this page to retry.</p>`;
  });

  voyagePromise.then((wikivoyage) => {
    if (wikivoyage) {
      setMetaChip("WIKIVOYAGE");
      addSource("Wikivoyage", `https://en.wikivoyage.org/wiki/${encodeURIComponent(name.replaceAll(" ", "_"))}`);
      renderTextBlocks(explore, wikivoyage, "No structured exploration guidance was found.");
      const blocks = splitUsefulSections(wikivoyage).slice(0, 4);
      highlights.classList.remove("loading-panel");
      highlights.innerHTML = blocks.map((block, i) => `<div class="highlight-item"><strong>SOURCE NOTE ${i + 1}</strong><span>${escapeHtml(block.replace(/\s+/g, " ").slice(0, 150))}</span></div>`).join("") || `<div class="highlight-item"><strong>DATA STATUS</strong><span>Limited sourced information available.</span></div>`;
    } else {
      explore.innerHTML = `<p>No Wikivoyage guide was found. Explore information will expand as more structured sources are connected.</p>`;
      clearSkeleton(explore);
      highlights.classList.remove("loading-panel");
      highlights.innerHTML = `<div class="highlight-item"><strong>DATA STATUS</strong><span>Limited sourced information available.</span></div>`;
    }
  });

  // Update the location card when geocoding resolves; keep the other practical
  // fields rendered from URL/OSM data instead of overwriting them later.
  coordsPromise.then((coords) => {
    if (coords && Number.isFinite(coords.lat) && Number.isFinite(coords.lon)) {
      const locationCard = [...practical.querySelectorAll(".practical-card")].find((card) => card.querySelector("h4")?.textContent === "LOCATION");
      const locationText = coords.address || `${coords.lat.toFixed(5)}, ${coords.lon.toFixed(5)}`;
      if (locationCard) locationCard.querySelector("p").textContent = locationText;
    }
  });
  Promise.allSettled([wikiPromise, voyagePromise, coordsPromise]).then(() => {
    clearTimeout(pageWatchdog);
    const sources = document.getElementById("place-sources");
    if (sources && !sources.querySelector("a.source-link")) {
      sources.innerHTML = '<p class="source-empty">No source links were returned for this place.</p>';
    }
  });
}

function loadCommunity(name, id) {
  const container = document.getElementById("place-community-content");
  if (!container) return;
  let posts = [];
  try { posts = JSON.parse(localStorage.getItem("movaCommunityPosts") || "[]"); } catch { posts = []; }
  if (!Array.isArray(posts)) posts = [];

  const normalized = name.trim().toLowerCase();
  const matching = posts.filter((post) => {
    const location = String(post.location || post.place || "").toLowerCase();
    return location === normalized || location.includes(normalized) || (id && String(post.destinationId || "") === id);
  });

  if (!matching.length) {
    container.innerHTML = `<div class="community-empty"><h4>NO COMMUNITY POSTS YET.</h4><p>This place has no linked MOVA traveller posts yet. We won't fabricate reviews or photos.</p><a class="btn btn-primary" href="community.html">SHARE AN EXPERIENCE ↗</a></div>`;
    return;
  }

  container.innerHTML = matching.slice(0, 12).map((post) => `<article class="community-card"><div class="community-user">${escapeHtml(post.author || post.username || "MOVA TRAVELLER")}</div><p>${escapeHtml(post.caption || post.text || "No caption provided.")}</p>${post.experienceRating ? `<div class="place-meta-chip">EXPERIENCE ${escapeHtml(post.experienceRating)}/5</div>` : ""}${post.tip ? `<p><strong>TIP:</strong> ${escapeHtml(post.tip)}</p>` : ""}</article>`).join("");
}
