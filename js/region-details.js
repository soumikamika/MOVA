/* MOVA AREA EXPLORER — backend-proxied geographic discovery with resilient states. */
const REGION_WIKIMEDIA_URL = "https://commons.wikimedia.org/w/api.php";
const REGION_CACHE_KEY = "mova.region.cache.v4";
const REGION_CACHE_TTL = 1000 * 60 * 60 * 6;
const REGION_IMAGE_TIMEOUT = 10000;

let allRegionPlaces = [],
  nearbyPlaces = [],
  activeRegionFilter = "all",
  regionSearchQuery = "",
  regionInfo = {},
  regionRequestToken = 0,
  activeRegionController = null;

function esc(v) {
  return String(v ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function norm(v) {
  return String(v ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function parseOptionalCoord(raw) {
  if (raw === null || raw === undefined) return null;
  const trimmed = String(raw).trim();
  if (!trimmed) return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : NaN;
}

function cacheKey(name, scope) {
  return `${norm(name)}::${scope}`;
}

function cacheRead(key) {
  try {
    const raw = localStorage.getItem(`${REGION_CACHE_KEY}:${key}`);
    if (!raw) return null;
    const item = JSON.parse(raw);
    if (Date.now() - item.savedAt > REGION_CACHE_TTL) {
      return null;
    }
    return item.data || null;
  } catch {
    return null;
  }
}

function cacheReadStale(key) {
  try {
    const raw = localStorage.getItem(`${REGION_CACHE_KEY}:${key}`);
    if (!raw) return null;
    const item = JSON.parse(raw);
    return item.data || null;
  } catch {
    return null;
  }
}

function cacheWrite(key, data) {
  try {
    localStorage.setItem(
      `${REGION_CACHE_KEY}:${key}`,
      JSON.stringify({ savedAt: Date.now(), data }),
    );
  } catch {}
}

function distanceKm(a, b, c, d) {
  const R = 6371,
    rad = Math.PI / 180,
    da = (c - a) * rad,
    db = (d - b) * rad;
  const x =
    Math.sin(da / 2) ** 2 +
    Math.cos(a * rad) * Math.cos(c * rad) * Math.sin(db / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, x)));
}

async function fetchJsonWithTimeout(url, signal, timeoutMs = REGION_IMAGE_TIMEOUT) {
  const c = new AbortController();
  const onAbort = () => c.abort();
  if (signal) {
    if (signal.aborted) c.abort();
    else signal.addEventListener("abort", onAbort, { once: true });
  }
  const timer = setTimeout(() => c.abort(), timeoutMs);
  try {
    const r = await fetch(url, { signal: c.signal, headers: { Accept: "application/json" } });
    if (!r.ok) throw Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onAbort);
  }
}

async function imageForRegion(name, signal) {
  try {
    const key = `image:${norm(name)}`;
    const cached = cacheRead(key);
    if (cached) return cached;
    const p = new URLSearchParams({
      action: "query",
      generator: "search",
      gsrsearch: `${name} India`,
      gsrnamespace: "6",
      gsrlimit: "1",
      prop: "imageinfo",
      iiprop: "url",
      iiurlwidth: "1200",
      format: "json",
      origin: "*",
    });
    const d = await fetchJsonWithTimeout(`${REGION_WIKIMEDIA_URL}?${p}`, signal, REGION_IMAGE_TIMEOUT);
    const page = Object.values(d.query?.pages || {})[0];
    const info = page?.imageinfo?.[0];
    const result =
      info?.thumburl || info?.url
        ? {
            url: info.thumburl || info.url,
            pageUrl: page?.canonicalurl || info.descriptionurl,
          }
        : null;
    if (result) cacheWrite(key, result);
    return result;
  } catch {
    return null;
  }
}

async function enrichImages(places, signal, renderCallback) {
  const targets = places
    .filter((p) => !p.image && p.image !== "failed")
    .slice(0, 15);
  let cursor = 0;
  const workers = Math.min(3, targets.length);
  await Promise.all(
    Array.from({ length: workers }, async () => {
      while (cursor < targets.length) {
        if (signal?.aborted) return;
        const p = targets[cursor++];
        const img = await imageForRegion(p.name, signal);
        if (img) {
          p.image = img.url;
          p.imagePageUrl = img.pageUrl;
          p.imageSource = "Wikimedia Commons";
          if (!signal?.aborted && renderCallback) renderCallback();
        } else {
          p.image = "failed";
        }
      }
    }),
  );
}

function mapUiCategory(place) {
  const explicit = String(place.ui_category || "").toLowerCase();
  if (["heritage", "temples", "nature", "museum", "other"].includes(explicit)) {
    return explicit;
  }
  const category = String(place.category || "other").toLowerCase();
  if (category === "religious") return "temples";
  if (category === "museum") return "museum";
  if (category === "historical" || category === "cultural") return "heritage";
  if (["nature", "beach", "waterfall", "viewpoint", "park", "wildlife"].includes(category)) {
    return "nature";
  }
  return "other";
}

function mapBackendRegionPlace(place) {
  const location = place.location || {};
  const category = String(place.category || "other").toLowerCase();
  const uiCategory = mapUiCategory(place);
  const readableType =
    place.type ||
    category.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return {
    name: place.name,
    lat: Number(location.latitude),
    lon: Number(location.longitude),
    tags: { source: place.provider_source || place.source || "external_api", categories: place.tags || [] },
    type: readableType,
    category: uiCategory,
    rawCategory: category,
    description: place.description || null,
    wikipedia: place.wikipedia_url || "",
    website: place.website || "",
    openingHours: place.opening_hours || "",
    fee: place.entry_fee_inr ?? null,
    osmId: place.osm_id || place.id,
    sourceUrl: place.source_url || "",
    source: place.provider_source || (place.is_fallback ? "WIKIPEDIA" : "OPENSTREETMAP"),
    isFallback: Boolean(place.is_fallback),
    image: place.image_url || null,
    imageSource: place.image_url ? "OpenStreetMap" : null,
    imagePageUrl: place.image_url || "",
  };
}

function filteredPlaces() {
  const query = norm(regionSearchQuery);
  return allRegionPlaces.filter((p) => {
    const matchesFilter =
      activeRegionFilter === "all" ||
      p.category === activeRegionFilter ||
      (activeRegionFilter === "museum" && norm(p.type).includes("museum"));
    const haystack = norm(
      [
        p.name,
        p.type,
        p.category,
        p.rawCategory,
        p.description,
        ...(Array.isArray(p.tags?.categories) ? p.tags.categories : []),
      ]
        .filter(Boolean)
        .join(" "),
    );
    return matchesFilter && (!query || haystack.includes(query));
  });
}

function cardMarkup(p, i, nearby = false) {
  const areaLat = regionInfo.area?.lat;
  const areaLon = regionInfo.area?.lon;
  const hasAreaCenter =
    areaLat !== null &&
    areaLat !== undefined &&
    areaLat !== "" &&
    areaLon !== null &&
    areaLon !== undefined &&
    areaLon !== "" &&
    Number.isFinite(Number(areaLat)) &&
    Number.isFinite(Number(areaLon));
  const dist = hasAreaCenter
    ? distanceKm(
        Number(areaLat),
        Number(areaLon),
        p.lat,
        p.lon,
      )
    : null;
  const hasImage = p.image && p.image !== "failed";
  return `<article class="region-place-card ${nearby ? "nearby-card" : ""}"><div class="region-place-image ${hasImage ? "" : "no-image"}">${hasImage ? `<img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer">` : `<div><strong>NO SOURCED IMAGE</strong><span>NO IMAGE FOUND FROM CURRENT SOURCES</span></div>`}<span class="region-place-type">${esc(p.type)}</span></div><div class="region-place-body"><h3>${esc(p.name)}</h3><p>${esc(p.description || "Explore this mapped place to inspect available information and sources.")}</p><div class="region-place-meta"><span class="region-chip">${esc(p.category)}</span><span class="region-chip">${esc(p.source || "OPENSTREETMAP")}</span>${dist !== null ? `<span class="region-chip">${dist < 1 ? "<1" : dist.toFixed(0)} KM AWAY</span>` : ""}${p.imageSource ? `<span class="region-chip">${esc(p.imageSource.toUpperCase())}</span>` : ""}</div><div class="region-place-actions"><button class="btn btn-secondary region-detail-btn" data-index="${i}" type="button">MORE INFO</button><button class="btn quick-plan region-plan-btn" data-index="${i}" type="button">ADD TO PLAN ↗</button></div></div></article>`;
}

function bindGrid(grid, places) {
  grid
    .querySelectorAll(".region-detail-btn")
    .forEach((b) =>
      b.addEventListener("click", () =>
        openPlace(places[Number(b.dataset.index)]),
      ),
    );
  grid
    .querySelectorAll(".region-plan-btn")
    .forEach((b) =>
      b.addEventListener("click", () =>
        addPlan(places[Number(b.dataset.index)]),
      ),
    );
  grid
    .querySelectorAll(".region-retry")
    .forEach((b) => b.addEventListener("click", () => init(true)));
}

function renderSkeletonGrid(count = 6) {
  return Array(count)
    .fill(0)
    .map(
      () =>
        `<article class="region-place-card"><div class="region-place-image skeleton-img" style="height:210px;border-bottom:0"></div><div class="region-place-body"><h3 class="skeleton-text" style="height:1.5rem;width:70%"></h3><p><span class="skeleton-text"></span><span class="skeleton-text medium"></span></p><div class="region-place-meta" style="height:25px"><span class="skeleton-text" style="width:80px;height:20px;border-radius:4px"></span></div><div class="region-place-actions" style="margin-top:8px"><div class="skeleton-text" style="width:100%;height:45px"></div></div></div></article>`,
    )
    .join("");
}

function renderPlaces(notice = null) {
  const grid = document.getElementById("region-grid"),
    count = document.getElementById("region-count");
  if (!grid) return;
  const places = filteredPlaces();
  if (count)
    count.textContent = `${places.length} ${places.length === 1 ? "PLACE" : "PLACES"}`;
  const searchCount = document.getElementById("region-search-count");
  if (searchCount)
    searchCount.textContent = regionSearchQuery.trim()
      ? `${places.length} MATCHING PLACES`
      : `${allRegionPlaces.length} PLACES LOADED`;

  const noticeMarkup = notice
    ? `<div class="region-empty" role="status"><strong>${esc(notice.title)}</strong><p>${esc(notice.detail)}</p>${notice.showRetry ? `<button class="btn btn-secondary region-retry" type="button">RETRY DISCOVERY ↻</button>` : ""}</div>`
    : "";

  if (!places.length) {
    if (!allRegionPlaces.length) {
      grid.innerHTML = `<div class="region-empty"><strong>NO MATCHING PLACES FOUND FOR THIS AREA.</strong><p>${esc(notice?.detail || "The geographic source responded normally, but no matching tourist records were returned for this location.")}</p><div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px"><button class="btn btn-primary region-retry" type="button">RETRY DISCOVERY ↻</button><a class="btn btn-secondary" href="discover.html">BACK TO DISCOVER</a></div></div>`;
      bindGrid(grid, []);
      return;
    }
    grid.innerHTML = `${noticeMarkup}<div class="region-empty"><strong>${regionSearchQuery.trim() ? "NO PLACES MATCH THAT SEARCH." : "NO MAPPED PLACES FOUND FOR THIS FILTER."}</strong><p>${regionSearchQuery.trim() ? "Try another spelling or a broader term." : "Try switching to ALL or another category filter."}</p></div>`;
    bindGrid(grid, []);
    return;
  }
  grid.innerHTML = noticeMarkup + places.map((p, i) => cardMarkup(p, i)).join("");
  bindGrid(grid, places);
}

function renderNearby() {
  const section = document.getElementById("nearby-section"),
    grid = document.getElementById("nearby-grid"),
    count = document.getElementById("nearby-count");
  if (!section || !grid) return;
  if (!nearbyPlaces.length) {
    section.hidden = true;
    grid.innerHTML = "";
    return;
  }
  section.hidden = false;
  if (count) count.textContent = `${nearbyPlaces.length} SOURCED PLACES`;
  const statusEl = document.getElementById("nearby-status");
  if (statusEl) {
    statusEl.textContent =
      "Real tourist places near this area, even when they sit outside the immediate center.";
  }
  grid.innerHTML = nearbyPlaces
    .slice(0, 24)
    .map((p, i) => cardMarkup(p, i, true))
    .join("");
  bindGrid(grid, nearbyPlaces);
}

function regionCommunityPosts() {
  let posts = [];
  try {
    posts = JSON.parse(localStorage.getItem("movaCommunityPosts") || "[]");
  } catch {}
  if (!Array.isArray(posts)) return [];
  const target = norm(regionInfo.name || "");
  return posts
    .filter((post) => {
      const tags = Array.isArray(post.tags)
        ? post.tags
        : String(post.tags || "").split(",");
      const region = norm(post.regionName || post.region || "");
      const location = norm(post.locationName || "");
      const tagged = tags.some((tag) => norm(tag).replace(/^#+/, "") === target);
      return target && (region === target || tagged || location === target);
    })
    .sort((a, b) => new Date(b.createdAt || 0) - new Date(a.createdAt || 0))
    .slice(0, 6);
}

function renderRegionCommunity() {
  const grid = document.getElementById("region-community-grid");
  const share = document.getElementById("region-share-tip");
  if (!grid) return;
  const region =
    regionInfo.name || new URLSearchParams(location.search).get("name") || "India";
  if (share)
    share.href = `community.html?region=${encodeURIComponent(region)}&compose=1`;
  const posts = regionCommunityPosts();
  if (!posts.length) {
    grid.innerHTML = `<article class="region-community-empty"><strong>NO TIPS TAGGED FOR ${esc(region.toUpperCase())} YET.</strong><p>Be the first to share a useful recommendation. Your region tag helps other travellers find it here and in Community.</p><a class="btn btn-secondary" href="community.html?region=${encodeURIComponent(region)}&compose=1">SHARE THE FIRST TIP ↗</a></article>`;
    return;
  }
  grid.innerHTML = posts
    .map(
      (post) =>
        `<article class="region-community-card">${post.image ? `<img src="${esc(post.image)}" alt="" loading="lazy">` : `<div class="region-community-art">${esc((post.type || "TIP").toUpperCase())}</div>`}<div class="region-community-card-body"><span class="region-community-type">${esc(post.type || "POST")} · ${esc(post.locationName || region)}</span><h3>${esc(post.caption || "Traveller recommendation")}</h3>${post.tip ? `<p>${esc(post.tip)}</p>` : ""}<a href="community.html?region=${encodeURIComponent(region)}&post=${encodeURIComponent(post.id || "")}">VIEW IN COMMUNITY ↗</a></div></article>`,
    )
    .join("");
}

function setStatus(text, kind = "live") {
  const el = document.getElementById("region-source-status");
  if (el) el.textContent = text;
  const dot = document.querySelector(".source-dot");
  if (dot) dot.dataset.status = kind;
}

function showRetry(message, detail = "", { allowRetry = true } = {}) {
  const grid = document.getElementById("region-grid");
  if (!grid) return;
  grid.innerHTML = `<div class="region-error"><strong>${esc(message)}</strong><p>${esc(detail || "MOVA could not complete geographic discovery. Previously loaded results are kept when available.")}</p><div style="display:flex;gap:10px;flex-wrap:wrap">${allowRetry ? `<button class="btn btn-primary region-retry" type="button">RETRY DISCOVERY ↻</button>` : ""}<a class="btn btn-secondary" href="discover.html">BACK TO DISCOVER</a></div></div>`;
  grid.querySelector(".region-retry")?.addEventListener("click", () => init(true));
}

function openPlace(p) {
  const q = new URLSearchParams({
    place: p.name,
    region: regionInfo.name || "INDIA",
    lat: p.lat,
    lon: p.lon,
    osm_id: p.osmId || "",
    address: "",
    description: p.description || "",
    website: p.website || "",
    fee: p.fee ?? "",
    opening_hours: p.openingHours || "",
    wikipedia: p.wikipedia || "",
    source_url: p.sourceUrl || "",
    source: p.source || "OPENSTREETMAP",
    image: p.image && p.image !== "failed" ? p.image : "",
    image_source: p.imageSource || "",
    image_url: p.imagePageUrl || "",
  });
  window.location.href = `place-details.html?${q}`;
}

function addPlan(p) {
  let list = [];
  try {
    const saved = localStorage.getItem("movaDraftMustVisitPlaces");
    if (saved) list = JSON.parse(saved);
  } catch {}
  if (Array.isArray(list) && !list.includes(p.name)) {
    list.push(p.name);
    localStorage.setItem("movaDraftMustVisitPlaces", JSON.stringify(list));
  } else if (!Array.isArray(list)) {
    localStorage.setItem("movaDraftMustVisitPlaces", JSON.stringify([p.name]));
  }
  const params = new URLSearchParams(location.search);
  const regionName = params.get("name") || params.get("place") || "India";
  window.location.href = `create-plan.html?${new URLSearchParams({ destination: regionName })}`;
}

async function fetchRegionFromBackend({ name, scope, lat, lon, refresh, signal }) {
  if (typeof discoverMovaRegion === "function") {
    return discoverMovaRegion({ name, scope, lat, lon, refresh }, { signal, timeoutMs: 65000 });
  }
  if (typeof movaApi !== "function") {
    throw Error("MOVA backend adapter is not loaded on Region Details.");
  }
  const query = new URLSearchParams({ name, scope });
  if (Number.isFinite(lat) && Number.isFinite(lon)) {
    query.set("lat", String(lat));
    query.set("lon", String(lon));
  }
  if (refresh) query.set("refresh", "true");
  return movaApi(`/api/regions/discover?${query.toString()}`, { timeoutMs: 65000, signal });
}

function applyDiscoveredPayload(payload, { name, scope, token, controller }) {
  const area = payload.area || { name, scope };
  const places = (payload.places || [])
    .map(mapBackendRegionPlace)
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon));
  const nearby = (payload.nearby_places || [])
    .map(mapBackendRegionPlace)
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon));

  regionInfo = { name: area.name || name, scope, area };
  renderRegionCommunity();

  const detailEl = document.getElementById("region-source-detail");
  const summaryEl = document.getElementById("region-summary");
  const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];

  if (detailEl) {
    const cacheTag = payload.cache_hit ? " · cached" : "";
    const warnTag = warnings.length ? ` · ${warnings[0]}` : "";
    detailEl.textContent = `${payload.provider || "Geographic provider"}: ${area.display_name || name}${cacheTag}${warnTag}`;
  }

  if (payload.status === "empty" || !places.length) {
    allRegionPlaces = [];
    nearbyPlaces = [];
    renderPlaces({
      detail:
        payload.message ||
        `No mapped tourist places were found around ${area.name || name}.`,
    });
    renderNearby();
    setStatus("NO MATCHING PLACES", "empty");
    if (summaryEl) {
      summaryEl.textContent =
        area.summary ||
        payload.message ||
        `No mapped tourist places were returned for ${name}.`;
    }
    return;
  }

  allRegionPlaces = places;
  nearbyPlaces = nearby;

  const partialNotice =
    payload.status === "partial" && warnings.length
      ? {
          title: "PARTIAL DISCOVERY RESULTS",
          detail: warnings.join(" "),
          showRetry: true,
        }
      : null;

  renderPlaces(partialNotice);
  renderNearby();

  if (payload.status === "partial") {
    setStatus("PARTIAL DISCOVERY — FALLBACK SOURCE", "cached");
  } else {
    setStatus("SOURCED DISCOVERY", "live");
  }

  if (summaryEl) {
    summaryEl.textContent = area.summary
      ? `${area.summary} (${places.length} sourced places found)`
      : `${places.length} sourced place records found for ${area.name || name}. Provider: ${payload.provider || "live geographic data"}.`;
  }

  // Hero image & card image enrichment are non-blocking and independent.
  imageForRegion(area.name || name, controller.signal)
    .then((img) => {
      if (img && token === regionRequestToken) {
        const heroEl = document.getElementById("region-hero-image");
        if (heroEl) {
          heroEl.innerHTML = `<img src="${esc(img.url)}" alt="${esc(name)}" referrerpolicy="no-referrer">`;
        }
      }
    })
    .catch(() => {});

  enrichImages(allRegionPlaces, controller.signal, () => {
    if (token === regionRequestToken) renderPlaces(partialNotice);
  }).catch(() => {});

  if (nearbyPlaces.length) {
    enrichImages(nearbyPlaces, controller.signal, () => {
      if (token === regionRequestToken) renderNearby();
    }).catch(() => {});
  }
}

async function init(force = false) {
  if (activeRegionController) activeRegionController.abort();
  const controller = new AbortController();
  activeRegionController = controller;
  const token = ++regionRequestToken;

  const params = new URLSearchParams(location.search);
  const name = (params.get("name") || params.get("place") || "India").trim();
  const scope = params.get("scope") === "city" ? "city" : "region";
  const lat = parseOptionalCoord(params.get("lat"));
  const lon = parseOptionalCoord(params.get("lon"));

  document.getElementById("region-name").textContent = (name || "INDIA").toUpperCase();
  document.getElementById("region-plan").href =
    `create-plan.html?${new URLSearchParams({ destination: name || "India" })}`;

  const previousSnapshot =
    norm(regionInfo.name || "") === norm(name) &&
    regionInfo.scope === scope &&
    allRegionPlaces.length
      ? {
          area: regionInfo.area,
          places: [...allRegionPlaces],
          nearbyPlaces: [...nearbyPlaces],
        }
      : null;

  regionInfo = { ...regionInfo, name, scope };
  renderRegionCommunity();

  if (name.length < 2) {
    setStatus("INVALID REGION OR COORDINATES", "error");
    document.getElementById("region-count").textContent = "INVALID AREA";
    showRetry(
      "INVALID AREA NAME.",
      "Select a destination or city from Discover to load regional places.",
      { allowRetry: false },
    );
    return;
  }

  const hasLat = lat !== null;
  const hasLon = lon !== null;
  const badCoords =
    hasLat !== hasLon ||
    Number.isNaN(lat) ||
    Number.isNaN(lon) ||
    (hasLat && (lat < -90 || lat > 90 || lon < -180 || lon > 180));

  if (badCoords) {
    setStatus("INVALID REGION OR COORDINATES", "error");
    document.getElementById("region-count").textContent = "INVALID COORDINATES";
    showRetry(
      "INVALID COORDINATES SUPPLIED.",
      "The latitude or longitude in the page URL is invalid. Return to Discover and choose an area again.",
      { allowRetry: false },
    );
    return;
  }

  const grid = document.getElementById("region-grid");
  if (grid) grid.innerHTML = renderSkeletonGrid(9);
  setStatus(force ? "RETRYING DISCOVERY" : "LOADING PLACES", "loading");
  const nearbySection = document.getElementById("nearby-section");
  if (nearbySection) nearbySection.hidden = true;

  try {
    const result = await fetchRegionFromBackend({
      name,
      scope,
      lat,
      lon,
      refresh: force,
      signal: controller.signal,
    });
    if (token !== regionRequestToken) return;
    if (!result || !result.area) {
      throw Error("The backend returned an incomplete region discovery payload.");
    }

    if (result.status === "ok" && Array.isArray(result.places) && result.places.length) {
      cacheWrite(`places:${cacheKey(name, scope)}`, {
        area: result.area,
        places: result.places,
        nearby_places: result.nearby_places || [],
        provider: result.provider,
        warnings: result.warnings || [],
        status: "ok",
      });
    }

    applyDiscoveredPayload(result, { name, scope, token, controller });
  } catch (e) {
    if (e?.code === "aborted" || e?.name === "AbortError") return;
    if (token !== regionRequestToken) return;
    console.error(e);

    const status = Number(e?.status);
    if (status === 400 || status === 404 || status === 422) {
      allRegionPlaces = [];
      nearbyPlaces = [];
      renderNearby();
      setStatus("INVALID REGION OR COORDINATES", "error");
      document.getElementById("region-count").textContent = "NOT FOUND";
      showRetry(
        status === 404 ? "AREA NOT FOUND." : "INVALID AREA REQUEST.",
        e.message || "MOVA could not validate this region or its coordinates.",
        { allowRetry: false },
      );
      return;
    }

    const key = cacheKey(name, scope);
    const cachedPayload = cacheRead(`places:${key}`) || cacheReadStale(`places:${key}`);
    const fallbackPlaces = previousSnapshot?.places?.length
      ? previousSnapshot.places
      : (cachedPayload?.places || []).map(mapBackendRegionPlace);
    const fallbackNearby = previousSnapshot?.nearbyPlaces?.length
      ? previousSnapshot.nearbyPlaces
      : (cachedPayload?.nearby_places || []).map(mapBackendRegionPlace);

    if (fallbackPlaces.length) {
      allRegionPlaces = fallbackPlaces;
      nearbyPlaces = fallbackNearby;
      if (previousSnapshot?.area || cachedPayload?.area) {
        regionInfo = {
          name,
          scope,
          area: previousSnapshot?.area || cachedPayload.area,
        };
      }
      renderPlaces({
        title: "SHOWING PREVIOUSLY LOADED RESULTS",
        detail: `Live refresh failed (${e?.message || "source unavailable"}). Retry discovery when ready.`,
        showRetry: true,
      });
      renderNearby();
      setStatus("CACHED RESULTS — LIVE REFRESH UNAVAILABLE", "cached");
      document.getElementById("region-summary").textContent =
        `Showing ${fallbackPlaces.length} previously loaded places while live discovery is unavailable.`;
      return;
    }

    setStatus(
      e?.code === "network_error" ? "BACKEND OFFLINE" : "SOURCE TEMPORARILY UNAVAILABLE",
      "error",
    );
    document.getElementById("region-count").textContent = "UNAVAILABLE";
    showRetry(
      e?.code === "network_error"
        ? "MOVA BACKEND IS NOT REACHABLE."
        : "LIVE AREA DISCOVERY IS TEMPORARILY UNAVAILABLE.",
      e?.message || "MOVA couldn't reach the geographic source right now. Check your connection and retry.",
    );
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("region-search");
  search?.addEventListener("input", () => {
    regionSearchQuery = search.value || "";
    renderPlaces();
  });
  init();
  document.querySelectorAll(".region-filter").forEach((b) =>
    b.addEventListener("click", () => {
      activeRegionFilter = b.dataset.filter || "all";
      document
        .querySelectorAll(".region-filter")
        .forEach((x) => x.classList.toggle("active", x === b));
      renderPlaces();
    }),
  );
});
