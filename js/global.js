/* =========================================================
   MOVA GLOBAL JAVASCRIPT
========================================================= */


/* =========================================================
   BRAND
========================================================= */

const SITE_NAME = "MOVA";


/* =========================================================
   NAVIGATION
========================================================= */

function renderNavbar() {

    const navbar = document.getElementById("navbar");

    if (!navbar) return;

    navbar.innerHTML = `
        <nav class="main-navbar">

            <a
                href="../index.html"
                class="brand"
                aria-label="${SITE_NAME} Home"
            >
                <span class="brand-mark">✦</span>
                <span class="brand-name">${SITE_NAME}</span>
            </a>


            <div class="nav-links">

               <a href="../index.html" class="nav-link" data-page="home">Home</a>

                <a href="../pages/discover.html" class="nav-link" data-page="discover">
                    Discover
                </a>

                <a href="../pages/community.html" class="nav-link" data-page="community">
                    Community
                </a>

                <a href="../pages/plans.html" class="nav-link" data-page="plans" data-requires-auth>
                    My Plans
                </a>

            </div>


            <div class="nav-actions">

                <button
                    class="nav-icon-button"
                    aria-label="Search"
                    id="search-button"
                    title="Search"
                >
                    ⌕
                </button>

                <button
                    class="theme-toggle-button"
                    id="theme-toggle-button"
                    type="button"
                    aria-label="Switch theme"
                    title="Switch theme"
                >
                    ◐
                </button>

                <span class="nav-auth-user" data-auth-status hidden></span>
                <a href="../pages/profile.html" class="profile-button" data-page="profile" data-requires-auth data-sign-in>SIGN IN</a>
                <button type="button" class="profile-button" data-sign-out hidden>SIGN OUT</button>

            </div>


            <button
                class="mobile-menu-button"
                id="mobile-menu-button"
                aria-label="Open menu"
            >
                ☰
            </button>

        </nav>
    `;


    /* =====================================================
       MOBILE MENU
    ===================================================== */

    const menuButton =
        document.getElementById("mobile-menu-button");

    const navLinks =
        document.querySelector(".nav-links");

    if (menuButton && navLinks) {

        menuButton.addEventListener("click", () => {

            navLinks.classList.toggle("mobile-open");

            menuButton.textContent =
                navLinks.classList.contains("mobile-open")
                    ? "×"
                    : "☰";

        });

    }

    /* Search is a global action: open Discover everywhere, and focus the
       search field immediately when Discover is already open. */
    const searchButton = document.getElementById("search-button");
    if (searchButton) {
        searchButton.addEventListener("click", () => {
            const onDiscover = window.location.pathname.includes("/discover");
            if (!onDiscover) {
                window.location.href = "../pages/discover.html?focus=search";
                return;
            }
            const input = document.querySelector("#discover-search, #search-input, input[type=search]");
            if (input) {
                input.focus();
                input.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        });
    }

    const themeButton = document.getElementById("theme-toggle-button");
    if (themeButton && themeButton.dataset.bound !== "true") {
        themeButton.dataset.bound = "true";
        themeButton.addEventListener("click", toggleMovaTheme);
        updateThemeToggleButton();
    }

    syncNavbarAuthState(typeof window.movaGetFirebaseUser === "function" ? window.movaGetFirebaseUser() : null);

}

function getMovaAuthLabel(user) {
    if (!user) return "";
    try {
        const stored = JSON.parse(localStorage.getItem("movaProfile") || "null");
        const username = String(stored?.username || "").trim();
        if (username) return `@${username}`;
        const profileName = String(stored?.displayName || "").trim();
        if (profileName) return profileName;
    } catch {}
    const displayName = String(user.displayName || "").trim();
    if (displayName) return displayName;
    const email = String(user.email || "").trim();
    return email ? email.split("@")[0] : "";
}

function syncNavbarAuthState(user) {
    const label = getMovaAuthLabel(user);
    document.querySelectorAll("[data-auth-status]").forEach(el => {
        el.textContent = label;
        el.hidden = !user || !label;
        if (label) el.title = label;
        else el.removeAttribute("title");
    });
    document.querySelectorAll("[data-sign-out]").forEach(el => {
        el.hidden = !user;
    });
    document.querySelectorAll("[data-sign-in]").forEach(el => {
        el.hidden = false;
        el.textContent = user ? "PROFILE" : "SIGN IN";
    });
}

window.addEventListener("mova:auth-state", event => {
    syncNavbarAuthState(event.detail?.user || null);
});

window.addEventListener("mova:profile-updated", () => {
    if (typeof window.movaGetFirebaseUser === "function") {
        syncNavbarAuthState(window.movaGetFirebaseUser());
    }
});


/* =========================================================
   FOOTER
========================================================= */

function renderFooter() {

    const footer = document.getElementById("footer");

    if (!footer) return;

    footer.innerHTML = `

        <div class="footer-inner">

            <div class="footer-brand">

                <span class="brand-mark">✦</span>

                <span class="brand-name">
                    ${SITE_NAME}
                </span>

            </div>


            <p>
                Discover India. Plan better. Travel further.
            </p>


            <div class="footer-links">

                <a href="../pages/discover.html">
                    Discover
                </a>

                <a href="../pages/community.html">
                    Community
                </a>

                <a href="../pages/plans.html">
                    My Plans
                </a>

                <a href="../pages/profile.html">
                    Profile
                </a>

            </div>

        </div>

    `;

}


/* =========================================================
   AI ASSISTANT
========================================================= */

function initializeAssistant() {

    const assistant =
        document.getElementById("ai-assistant-button");

    if (!assistant) return;

    assistant.addEventListener("click", () => {

        alert(
            "MOVA Travel Assistant will be connected later."
        );

    });

}


/* =========================================================
   PAGE INITIALIZATION
========================================================= */

document.addEventListener("DOMContentLoaded", () => {

    applyStoredAppearance();

    renderNavbar();

    setActiveNavLink();

    renderFooter();

    initializeAssistant();

});

function setActiveNavLink() {

    const navLinks =
        document.querySelectorAll(".nav-link");

    const currentPath =
        window.location.pathname;


    let currentPage = "home";

    if (currentPath.includes("/region-details") || currentPath.includes("/place-details") || currentPath.includes("/edit-plan") || currentPath.includes("/plan-dashboard")) {
        currentPage = "";
    }
    else if (currentPath.includes("/discover")) {
        currentPage = "discover";
    }

    else if (currentPath.includes("/community")) {
        currentPage = "community";
    }

    else if (
        currentPath.includes("/plans") ||
        currentPath.includes("/create-plan")
    ) {
        currentPage = "plans";
    }

    else if (currentPath.includes("/profile")) {
        currentPage = "profile";
    }


    navLinks.forEach(link => {

        link.classList.toggle(
            "active",
            link.dataset.page === currentPage
        );

    });


    const profileButton =
        document.querySelector(".profile-button");

    if (profileButton) {

        const profileActive =
            currentPage === "profile";

        profileButton.classList.toggle(
            "active",
            profileActive
        );

        if (profileActive) {
            profileButton.setAttribute("aria-current", "page");
        } else {
            profileButton.removeAttribute("aria-current");
        }

    }

}


/* =========================================================
   QUICK THEME TOGGLE
========================================================= */

function getMovaAppearance() {
    try {
        const stored = JSON.parse(localStorage.getItem("movaProfile"));
        return stored?.settings?.appearance === "dark" ? "dark" : "light";
    } catch {
        return "light";
    }
}

function persistMovaAppearance(appearance) {
    try {
        const stored = JSON.parse(localStorage.getItem("movaProfile")) || {};
        stored.settings = { ...(stored.settings || {}), appearance };
        localStorage.setItem("movaProfile", JSON.stringify(stored));
    } catch {}
}

function updateThemeToggleButton() {
    const button = document.getElementById("theme-toggle-button");
    if (!button) return;
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    button.textContent = dark ? "☀" : "◐";
    button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    button.setAttribute("title", dark ? "Switch to light mode" : "Switch to dark mode");
}

function toggleMovaTheme() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const next = dark ? "light" : "dark";
    if (next === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.removeAttribute("data-theme");
    persistMovaAppearance(next);
    updateThemeToggleButton();
    window.dispatchEvent(new CustomEvent("mova-theme-change", { detail: { theme: next } }));
}

/* =========================================================
   APPEARANCE (from movaProfile settings)
========================================================= */

function applyStoredAppearance() {

    try {

        const stored = JSON.parse(
            localStorage.getItem("movaProfile")
        );

        const appearance =
            stored &&
            stored.settings &&
            stored.settings.appearance;

        if (appearance === "dark") {

            document.documentElement.setAttribute(
                "data-theme",
                "dark"
            );

        } else {

            document.documentElement.removeAttribute(
                "data-theme"
            );

        }

    } catch (error) {

        document.documentElement.removeAttribute(
            "data-theme"
        );

    }

    updateThemeToggleButton();

}

applyStoredAppearance();
