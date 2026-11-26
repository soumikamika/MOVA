/* =========================================================
   MOVA HOME — externally sourced destination imagery
   Primary image source: Wikipedia page thumbnails.
   Secondary source: Wikimedia Commons search.
========================================================= */

const HOME_IMAGE_CACHE_KEY = "mova.home.images.v2";
const HOME_IMAGE_CACHE_TTL = 1000 * 60 * 60 * 24 * 7;
const HOME_WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/";
const HOME_COMMONS_API = "https://commons.wikimedia.org/w/api.php";

let heroImageTimer = null;
let heroDestinationIndex = 0;
let destinations = [];
let currentVisibleDestinations = [];
let destinationTimer = null;
const CARDS_VISIBLE = 3;
const AUTO_ROTATE_TIME = 4500;

function homeCacheRead(key) {
    try {
        const raw = localStorage.getItem(`${HOME_IMAGE_CACHE_KEY}:${key}`);
        if (!raw) return null;
        const item = JSON.parse(raw);
        if (!item || Date.now() - item.savedAt > HOME_IMAGE_CACHE_TTL) {
            localStorage.removeItem(`${HOME_IMAGE_CACHE_KEY}:${key}`);
            return null;
        }
        return item.data || null;
    } catch { return null; }
}

function homeCacheWrite(key, data) {
    try {
        localStorage.setItem(`${HOME_IMAGE_CACHE_KEY}:${key}`, JSON.stringify({ savedAt: Date.now(), data }));
    } catch {}
}

function homeSafe(v) {
    return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

async function fetchJsonWithTimeout(url, timeout = 10000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
        const response = await fetch(url, { signal: controller.signal, headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } finally {
        clearTimeout(timer);
    }
}

async function resolveExternalDestinationImage(destination) {
    const key = String(destination.id || destination.name).toLowerCase();
    const cached = homeCacheRead(key);
    if (cached) return cached;

    const title = encodeURIComponent(String(destination.name).replaceAll(" ", "_"));
    try {
        const wiki = await fetchJsonWithTimeout(`${HOME_WIKI_API}${title}`, 9000);
        const thumb = wiki?.thumbnail?.source;
        if (thumb) {
            const result = { url: thumb, pageUrl: wiki?.content_urls?.desktop?.page || `https://en.wikipedia.org/wiki/${title}`, source: "Wikipedia" };
            homeCacheWrite(key, result);
            return result;
        }
    } catch {}

    try {
        const params = new URLSearchParams({
            action: "query", generator: "search", gsrsearch: `${destination.name} India`,
            gsrnamespace: "6", gsrlimit: "3", prop: "imageinfo", iiprop: "url", iiurlwidth: "1200",
            format: "json", origin: "*"
        });
        const data = await fetchJsonWithTimeout(`${HOME_COMMONS_API}?${params}`, 10000);
        const page = Object.values(data?.query?.pages || {})[0];
        const info = page?.imageinfo?.[0];
        const url = info?.thumburl || info?.url;
        if (url) {
            const result = { url, pageUrl: page?.canonicalurl || info?.descriptionurl || "https://commons.wikimedia.org/", source: "Wikimedia Commons" };
            homeCacheWrite(key, result);
            return result;
        }
    } catch {}

    return null;
}

async function setExternalImage(container, destination, imageClass = "hero-image") {
    if (!container || !destination) return;
    const image = await resolveExternalDestinationImage(destination);
    if (!image) {
        container.innerHTML = `<div class="home-image-unavailable"><strong>IMAGE UNAVAILABLE</strong><span>NO IMAGE RETURNED BY THE CURRENT SOURCES.</span></div>`;
        return;
    }
    container.innerHTML = `<img src="${homeSafe(image.url)}" alt="${homeSafe(destination.name)}" class="${imageClass}" loading="lazy" referrerpolicy="no-referrer"><span class="home-image-source">SOURCE: ${homeSafe(image.source)}</span>`;
}

async function setupHeroSlider() {
    const slider = document.getElementById("hero-image-slider");
    if (!slider || !destinations.length) return;
    heroDestinationIndex = Math.floor(Math.random() * destinations.length);

    const showHeroDestination = async () => {
        const destination = destinations[heroDestinationIndex];
        await setExternalImage(slider, destination, "hero-image active");
        const locationName = document.querySelector(".hero-location-name");
        if (locationName) locationName.textContent = destination.name;
    };

    await showHeroDestination();
    if (heroImageTimer) clearInterval(heroImageTimer);
    heroImageTimer = setInterval(() => {
        heroDestinationIndex = (heroDestinationIndex + 1) % destinations.length;
        showHeroDestination();
    }, 5000);
}

async function loadDestinations() {
    const destinationGrid = document.getElementById("destination-grid");
    if (!destinationGrid) return;
    destinationGrid.innerHTML = Array(3).fill(0).map(() => `<div class="destination-card"><div class="destination-image-wrap skeleton-img" style="height:340px;"></div><div class="destination-info"><div><h3 class="skeleton-text" style="width:150px;height:1.5rem;display:block;"></h3></div></div><p class="destination-description"><span class="skeleton-text"></span><span class="skeleton-text medium"></span></p></div>`).join("");
    try {
        const response = await fetch("data/destinations.json", { cache: "no-cache" });
        if (!response.ok) throw new Error("Could not load destinations.");
        destinations = await response.json();
        showRandomDestinations();
        startDestinationCarousel();
        await setupHeroSlider();
    } catch (error) {
        console.error("Destination loading error:", error);
        destinationGrid.innerHTML = `<div class="destination-error"><strong>Destination data couldn't load.</strong><span>Check your destinations.json file.</span></div>`;
    }
}

function getRandomDestinations() {
    return [...destinations].sort(() => Math.random() - 0.5).slice(0, CARDS_VISIBLE);
}

function showRandomDestinations() {
    currentVisibleDestinations = getRandomDestinations();
    renderDestinationCards(currentVisibleDestinations);
}

function renderDestinationCards(visibleDestinations) {
    const destinationGrid = document.getElementById("destination-grid");
    if (!destinationGrid) return;
    destinationGrid.innerHTML = visibleDestinations.map((destination, index) => `
        <a href="pages/discover.html?destination=${homeSafe(destination.id)}" class="destination-card">
            <div class="destination-image-wrap destination-external-image" data-destination-index="${index}">
                <div class="home-image-unavailable home-image-loading"><strong>LOADING IMAGE</strong><span>FETCHING A SOURCED IMAGE</span></div>
            </div>
            <div class="destination-overlay"></div>
            <div class="destination-info"><div><span class="destination-region">${homeSafe(destination.region)}</span><h3>${homeSafe(destination.name)}</h3></div><span class="destination-arrow">↗</span></div>
            <p class="destination-description">${homeSafe(destination.description)}</p>
        </a>
    `).join("");

    visibleDestinations.forEach((destination, index) => {
        const target = destinationGrid.querySelector(`[data-destination-index="${index}"]`);
        setExternalImage(target, destination, "destination-image");
    });
}

function rotateDestinations() {
    if (destinations.length < CARDS_VISIBLE) return;
    let newDestinations;
    do { newDestinations = getRandomDestinations(); }
    while (newDestinations.every(destination => currentVisibleDestinations.some(current => current.id === destination.id)));
    currentVisibleDestinations = newDestinations;
    renderDestinationCards(currentVisibleDestinations);
}

function startDestinationCarousel() {
    stopDestinationCarousel();
    destinationTimer = setInterval(rotateDestinations, AUTO_ROTATE_TIME);
}

function stopDestinationCarousel() {
    if (destinationTimer) { clearInterval(destinationTimer); destinationTimer = null; }
}

function setupCarouselHover() {
    const section = document.getElementById("regions-section");
    if (!section) return;
    section.addEventListener("mouseenter", stopDestinationCarousel);
    section.addEventListener("mouseleave", startDestinationCarousel);
}

document.addEventListener("DOMContentLoaded", () => {
    loadDestinations();
    setupCarouselHover();
});
