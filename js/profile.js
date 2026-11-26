/* =========================================================
   MOVA PROFILE
========================================================= */

const PROFILE_KEY = "movaProfile";
const SAVED_KEY = "movaSaved";
const PLANS_KEY = "movaPlans";
const COMMUNITY_POSTS_KEY = "movaCommunityPosts";
const COMMUNITY_COMMENTS_KEY = "movaCommunityComments";

const TRAVEL_STYLES = [
    { value: "solo", label: "Solo" },
    { value: "friends", label: "Friends" },
    { value: "family", label: "Family" },
    { value: "couple", label: "Couple" },
    { value: "work", label: "Work" }
];

const INTERESTS = [
    { value: "beaches", label: "Beaches" },
    { value: "food", label: "Food" },
    { value: "culture", label: "Culture" },
    { value: "history", label: "History" },
    { value: "nature", label: "Nature" },
    { value: "adventure", label: "Adventure" },
    { value: "shopping", label: "Shopping" },
    { value: "nightlife", label: "Nightlife" }
];

const DISLIKES = [
    { value: "temples", label: "Temples" },
    { value: "clubs", label: "Clubs" },
    { value: "crowds", label: "Crowds" },
    { value: "long-travel", label: "Long travel" },
    { value: "adventure", label: "Adventure" },
    { value: "nightlife", label: "Nightlife" }
];

const TRANSPORT = [
    { value: "flight", label: "Flight" },
    { value: "train", label: "Train" },
    { value: "bus", label: "Bus" },
    { value: "self-drive", label: "Self-drive" },
    { value: "flexible", label: "Flexible" }
];

const FOOD_PREFS = [
    { value: "vegetarian", label: "Vegetarian" },
    { value: "vegan", label: "Vegan" },
    { value: "non-veg", label: "Non-veg" },
    { value: "jain", label: "Jain" },
    { value: "no-spice", label: "Mild spice" }
];

const ACCESS_PREFS = [
    { value: "wheelchair", label: "Wheelchair access" },
    { value: "reduced-walking", label: "Reduced walking" },
    { value: "step-free", label: "Step-free routes" }
];

const TAB_ORDER = [
    "overview",
    "trips",
    "saved",
    "preferences",
    "posts",
    "comments",
    "friends"
];

let profileState = null;
let savedFilter = "all";
let friendsView = "friends";
let pendingAvatarDataUrl = null;


document.addEventListener("DOMContentLoaded", () => {

    profileState = loadProfile();

    ensureSavedStore();

    setupProfileTabs();
    setupEditProfile();
    setupSettings();
    setupPreferences();
    setupAvatarUpload();
    setupSavedFilters();
    setupFriendsNav();

    renderProfile();

    const hashTab = window.location.hash.replace("#", "");

    if (TAB_ORDER.includes(hashTab)) {
        setActiveTab(hashTab);
    }

});


/* =========================================================
   STORAGE
========================================================= */

function defaultProfile() {

    return {
        displayName: "",
        username: "",
        bio: "",
        location: "",
        avatarDataUrl: null,
        travelStyle: null,
        interests: [],
        dislikes: [],
        transport: null,
        budgetPreference: null,
        pace: null,
        foodPreferences: [],
        accessibility: [],
        settings: {
            language: "en",
            currency: "INR",
            appearance: "light",
            privacy: {
                profileVisibility: "private",
                activityVisibility: "private"
            },
            notifications: {
                community: false,
                trips: false,
                planning: false
            }
        },
        friends: [],
        following: [],
        followers: []
    };

}


function defaultSaved() {

    return {
        destinations: [],
        places: [],
        guides: [],
        posts: []
    };

}


function loadProfile() {

    try {

        const stored = JSON.parse(
            localStorage.getItem(PROFILE_KEY)
        );

        return mergeProfile(stored);

    } catch (error) {

        console.error("Could not read movaProfile.", error);

        return defaultProfile();

    }

}


function mergeProfile(stored) {

    const base = defaultProfile();

    if (!stored || typeof stored !== "object") {
        return base;
    }

    return {
        ...base,
        ...stored,
        interests: Array.isArray(stored.interests)
            ? stored.interests
            : [],
        dislikes: Array.isArray(stored.dislikes)
            ? stored.dislikes
            : [],
        foodPreferences: Array.isArray(stored.foodPreferences)
            ? stored.foodPreferences
            : [],
        accessibility: Array.isArray(stored.accessibility)
            ? stored.accessibility
            : [],
        friends: Array.isArray(stored.friends)
            ? stored.friends
            : [],
        following: Array.isArray(stored.following)
            ? stored.following
            : [],
        followers: Array.isArray(stored.followers)
            ? stored.followers
            : [],
        settings: {
            ...base.settings,
            ...(stored.settings || {}),
            privacy: {
                ...base.settings.privacy,
                ...(stored.settings && stored.settings.privacy
                    ? stored.settings.privacy
                    : {})
            },
            notifications: {
                ...base.settings.notifications,
                ...(stored.settings && stored.settings.notifications
                    ? stored.settings.notifications
                    : {})
            }
        }
    };

}


function saveProfile(nextProfile) {

    profileState = nextProfile || profileState;

    localStorage.setItem(
        PROFILE_KEY,
        JSON.stringify(profileState)
    );

    if (typeof applyStoredAppearance === "function") {
        applyStoredAppearance();
    }

    window.dispatchEvent(new CustomEvent("mova:profile-updated", { detail: profileState }));

}


function loadPlans() {

    try {

        const plans = JSON.parse(
            localStorage.getItem(PLANS_KEY)
        );

        return Array.isArray(plans) ? plans : [];

    } catch (error) {

        console.error("Could not read movaPlans.", error);

        return [];

    }

}


function loadSaved() {

    try {

        const saved = JSON.parse(
            localStorage.getItem(SAVED_KEY)
        );

        if (!saved || typeof saved !== "object") {
            return defaultSaved();
        }

        return {
            destinations: Array.isArray(saved.destinations)
                ? saved.destinations
                : [],
            places: Array.isArray(saved.places)
                ? saved.places
                : [],
            guides: Array.isArray(saved.guides)
                ? saved.guides
                : [],
            posts: Array.isArray(saved.posts)
                ? saved.posts
                : []
        };

    } catch (error) {

        console.error("Could not read movaSaved.", error);

        return defaultSaved();

    }

}


function ensureSavedStore() {

    if (localStorage.getItem(SAVED_KEY)) {
        return;
    }

    localStorage.setItem(
        SAVED_KEY,
        JSON.stringify(defaultSaved())
    );

}


/* =========================================================
   RENDER
========================================================= */

function renderProfile() {

    renderHeader();
    renderOverview();
    renderTrips();
    renderSaved();
    renderPreferences();
    renderCommunityProfile();
    renderFriends();
    fillSettingsForm();

}


function renderHeader() {

    const nameEl = document.getElementById("profile-display-name");
    const userEl = document.getElementById("profile-username");
    const bioEl = document.getElementById("profile-bio");
    const locationEl = document.getElementById("profile-location");
    const avatarEl = document.getElementById("profile-avatar");
    const statsEl = document.getElementById("profile-stats");

    if (!nameEl || !userEl || !bioEl || !statsEl) {
        return;
    }

    const displayName = profileState.displayName.trim();
    const username = profileState.username.trim();

    nameEl.innerHTML = displayName
        ? `${escapeHtml(displayName)}`
        : `YOUR <span>PROFILE.</span>`;

    userEl.textContent = username
        ? `@${username}`
        : "Username not set";

    bioEl.textContent = profileState.bio.trim()
        ? profileState.bio.trim()
        : "Add a short bio from Edit profile.";

    if (profileState.location.trim()) {

        locationEl.hidden = false;
        locationEl.textContent = profileState.location.trim();

    } else {

        locationEl.hidden = true;
        locationEl.textContent = "";

    }

    renderAvatar(avatarEl);

    const plans = loadPlans();
    const saved = loadSaved();
    const savedCount =
        saved.destinations.length +
        saved.places.length +
        saved.guides.length +
        saved.posts.length;

    statsEl.innerHTML = `

        <div>
            <dt>Trips</dt>
            <dd>${plans.length}</dd>
        </div>

        <div>
            <dt>Saved</dt>
            <dd>${savedCount}</dd>
        </div>

        <div>
            <dt>Friends</dt>
            <dd>${profileState.friends.length}</dd>
        </div>

    `;

}


function renderAvatar(avatarEl, dataUrl = profileState.avatarDataUrl) {

    if (!avatarEl) {
        return;
    }

    if (dataUrl) {

        avatarEl.innerHTML = `
            <img
                src="${dataUrl}"
                alt=""
            >
        `;

        return;

    }

    avatarEl.textContent = getInitials();

}


function getInitials() {

    const source =
        profileState.displayName.trim() ||
        profileState.username.trim();

    if (!source) {
        return "✦";
    }

    const parts = source.split(/\s+/).filter(Boolean);

    if (parts.length === 1) {
        return parts[0].slice(0, 2).toUpperCase();
    }

    return (
        parts[0][0] + parts[1][0]
    ).toUpperCase();

}


function renderOverview() {

    const bio = document.getElementById("overview-bio");
    const prefs = document.getElementById("overview-preferences");
    const trips = document.getElementById("overview-trips");
    const savedBox = document.getElementById("overview-saved");
    const activity = document.getElementById("overview-activity");

    if (!bio || !prefs || !trips || !savedBox || !activity) {
        return;
    }

    bio.textContent = profileState.bio.trim()
        ? profileState.bio.trim()
        : "No bio yet.";

    prefs.innerHTML = preferenceSummaryMarkup();

    const plans = loadPlans().slice().reverse().slice(0, 3);

    if (!plans.length) {

        trips.innerHTML = emptyMarkup(
            "No trips yet.",
            "Create your first trip from My Plans."
        );

    } else {

        trips.innerHTML = plans.map(plan => tripCardMarkup(plan)).join("");
        bindTripButtons(trips);

    }

    const saved = loadSaved();
    const savedCount =
        saved.destinations.length +
        saved.places.length +
        saved.guides.length +
        saved.posts.length;

    if (!savedCount) {

        savedBox.innerHTML = emptyMarkup(
            "Your saved places will appear here.",
            "Add places from Discover to start building your travel collection."
        );

    } else {

        savedBox.innerHTML = `<p>${savedCount} saved item${savedCount === 1 ? "" : "s"} on this device.</p>`;

    }

    const posts = loadCommunityPosts();
    const comments = loadCommunityComments();
    activity.innerHTML = (posts.length || comments.length)
        ? `<div class="activity-summary"><strong>${posts.length} post${posts.length===1?"":"s"}</strong><span>${comments.length} comment${comments.length===1?"":"s"}</span></div><a class="text-link" href="#posts" data-profile-jump="posts">OPEN MY POSTS →</a>`
        : emptyMarkup("No community activity yet.", "Share a post or comment on a traveller story to see it here.");
    activity.querySelector("[data-profile-jump]")?.addEventListener("click", event => { event.preventDefault(); setActiveTab("posts"); });

}


function loadCommunityPosts() {
    try { const posts = JSON.parse(localStorage.getItem(COMMUNITY_POSTS_KEY)); return Array.isArray(posts) ? posts.filter(post => post.owner === "local") : []; }
    catch { return []; }
}

function loadCommunityComments() {
    try { const comments = JSON.parse(localStorage.getItem(COMMUNITY_COMMENTS_KEY)); return Array.isArray(comments) ? comments.filter(comment => comment.owner === "local") : []; }
    catch { return []; }
}

function communityPostTitle(post) {
    return escapeHtml(String(post.caption || "").split("\n")[0].slice(0, 110) || post.locationName || "Community post");
}

function renderCommunityProfile() {
    const postsBox = document.getElementById("my-posts-list");
    const commentsBox = document.getElementById("my-comments-list");
    const posts = loadCommunityPosts();
    const comments = loadCommunityComments();
    const postById = Object.fromEntries(loadCommunityPosts().map(post => [post.id, post]));
    if (postsBox) postsBox.innerHTML = posts.length ? posts.map(post => `<article class="community-profile-item"><div><span class="profile-card-label">${escapeHtml(String(post.type||"post").toUpperCase())} · ${escapeHtml(post.locationName||"INDIA")}</span><h3>${communityPostTitle(post)}</h3><p>${escapeHtml(post.caption||"")}</p><small>${escapeHtml(formatPlanDate((post.createdAt||"").slice(0,10)))}</small></div><a class="btn btn-secondary" href="community.html?post=${encodeURIComponent(post.id)}">VIEW POST</a></article>`).join("") : emptyMarkup("No posts yet.", "Your community posts will appear here.");
    if (commentsBox) commentsBox.innerHTML = comments.length ? comments.slice().reverse().map(comment => `<article class="community-profile-item"><div><span class="profile-card-label">COMMENT · ${escapeHtml(postById[comment.postId]?.locationName||"COMMUNITY")}</span><p>${escapeHtml(comment.text||"")}</p><small>${escapeHtml(formatPlanDate((comment.createdAt||"").slice(0,10)))}</small></div><a class="btn btn-secondary" href="community.html?post=${encodeURIComponent(comment.postId)}">VIEW COMMENT</a></article>`).join("") : emptyMarkup("No comments yet.", "Comments you leave on community posts will appear here.");
}

function preferenceSummaryMarkup() {

    const style = labelFor(TRAVEL_STYLES, profileState.travelStyle);
    const transport = labelFor(TRANSPORT, profileState.transport);
    const interests = profileState.interests
        .map(value => labelFor(INTERESTS, value))
        .filter(Boolean);

    return `

        <div>
            <dt>Style</dt>
            <dd>${escapeHtml(style || "Not set")}</dd>
        </div>

        <div>
            <dt>Transport</dt>
            <dd>${escapeHtml(transport || "Not set")}</dd>
        </div>

        <div>
            <dt>Interests</dt>
            <dd>${escapeHtml(interests.length ? interests.join(", ") : "Not set")}</dd>
        </div>

        <div>
            <dt>Budget</dt>
            <dd>${escapeHtml(profileState.budgetPreference || "Not set")}</dd>
        </div>

        <div>
            <dt>Pace</dt>
            <dd>${escapeHtml(profileState.pace || "Not set")}</dd>
        </div>

    `;

}


function renderTrips() {

    const list = document.getElementById("trips-list");

    if (!list) {
        return;
    }

    const plans = loadPlans().slice().reverse();

    if (!plans.length) {

        list.innerHTML = emptyMarkup(
            "No trips yet",
            "Create your first trip from My Plans."
        );

        return;

    }

    list.innerHTML = plans.map(plan => tripCardMarkup(plan)).join("");
    bindTripButtons(list);

}


function tripCardMarkup(plan) {

    const destination =
        plan.destination && plan.destination.name
            ? plan.destination.name
            : "Unknown destination";

    const region =
        plan.destination && plan.destination.region
            ? plan.destination.region
            : "";

    const start = formatPlanDate(plan.startDate);
    const end = formatPlanDate(plan.endDate);
    const transport = plan.transport || "Not set";
    const tripType = plan.tripType || "Not set";
    const travellers = plan.travellers || 0;
    const budget = formatMoney(plan.budget);
    const status = plan.status || "Planned";
    const planId = plan.id || "";

    return `

        <article class="trip-card">

            <div>

                <span class="trip-status">${escapeHtml(String(status))}</span>

                <p class="profile-username">${escapeHtml(region)}</p>

                <h3>${escapeHtml(destination)}</h3>

                <div class="trip-meta">
                    <span>${escapeHtml(start)} → ${escapeHtml(end)}</span>
                    <span>${escapeHtml(String(travellers))} travellers</span>
                    <span>${escapeHtml(String(tripType))}</span>
                    <span>${escapeHtml(transport)}</span>
                    <span>${escapeHtml(budget)}</span>
                </div>

            </div>

            <a
                class="btn btn-secondary"
                href="plans.html"
                data-plan-id="${escapeHtml(planId)}"
            >
                OPEN IN MY PLANS
            </a>

        </article>

    `;

}


function bindTripButtons(root) {

    root.querySelectorAll("[data-plan-id]").forEach(link => {

        link.addEventListener("click", () => {

            const planId = link.getAttribute("data-plan-id");

            if (planId) {
                sessionStorage.setItem("movaOpenPlanId", planId);
            }

        });

    });

}


function renderSaved() {

    const list = document.getElementById("saved-list");

    if (!list) {
        return;
    }

    const saved = loadSaved();
    const groups = [
        { key: "destinations", label: "Destination" },
        { key: "places", label: "Place" },
        { key: "guides", label: "Guide" },
        { key: "posts", label: "Post" }
    ];

    const items = [];

    groups.forEach(group => {

        if (savedFilter !== "all" && savedFilter !== group.key) {
            return;
        }

        saved[group.key].forEach(entry => {

            items.push({
                type: group.label,
                title: entry.title || entry.name || entry.id || "Saved item",
                subtitle: entry.subtitle || entry.location || ""
            });

        });

    });

    if (!items.length) {

        list.innerHTML = emptyMarkup(
            "Your saved places will appear here.",
            "Add places from Discover to start building your travel collection."
        );

        return;

    }

    list.innerHTML = items.map(item => `

        <article class="saved-item">

            <div>
                <small>${escapeHtml(item.type)}</small>
                <h3>${escapeHtml(item.title)}</h3>
                ${item.subtitle ? `<p>${escapeHtml(item.subtitle)}</p>` : ""}
            </div>

        </article>

    `).join("");

}


function renderPreferences() {

    fillChipGroup(
        "travel-style-options",
        TRAVEL_STYLES,
        "travelStyle",
        false
    );

    fillChipGroup(
        "interest-options",
        INTERESTS,
        "interests",
        true
    );

    fillChipGroup(
        "dislike-options",
        DISLIKES,
        "dislikes",
        true
    );

    fillChipGroup(
        "transport-options",
        TRANSPORT,
        "transport",
        false
    );

    fillChipGroup(
        "food-options",
        FOOD_PREFS,
        "foodPreferences",
        true
    );

    fillChipGroup(
        "accessibility-options",
        ACCESS_PREFS,
        "accessibility",
        true
    );

    const budget = document.getElementById("budget-preference");
    const pace = document.getElementById("pace-preference");

    if (budget) {
        budget.value = profileState.budgetPreference || "";
    }

    if (pace) {
        pace.value = profileState.pace || "";
    }

}


function fillChipGroup(containerId, options, field, multiple) {

    const container = document.getElementById(containerId);

    if (!container) {
        return;
    }

    const selected = profileState[field];

    container.innerHTML = options.map(option => {

        const on = multiple
            ? Array.isArray(selected) && selected.includes(option.value)
            : selected === option.value;

        return `
            <button
                type="button"
                class="chip-button${on ? " is-on" : ""}"
                aria-pressed="${on ? "true" : "false"}"
                data-field="${field}"
                data-multiple="${multiple ? "true" : "false"}"
                data-value="${option.value}"
            >
                ${escapeHtml(option.label)}
            </button>
        `;

    }).join("");

    if (container.dataset.bound === "true") {
        return;
    }

    container.dataset.bound = "true";

    container.addEventListener("click", event => {

        const button = event.target.closest("[data-field]");

        if (!button) {
            return;
        }

        const fieldName = button.dataset.field;
        const value = button.dataset.value;
        const isMultiple = button.dataset.multiple === "true";

        if (isMultiple) {

            const current = Array.isArray(profileState[fieldName])
                ? profileState[fieldName].slice()
                : [];

            const index = current.indexOf(value);

            if (index >= 0) {
                current.splice(index, 1);
            } else {
                current.push(value);
            }

            profileState[fieldName] = current;

        } else {

            profileState[fieldName] =
                profileState[fieldName] === value
                    ? null
                    : value;

        }

        renderPreferences();

    });

}


function renderFriends() {

    const list = document.getElementById("friends-list");

    if (!list) {
        return;
    }

    const people = Array.isArray(profileState[friendsView])
        ? profileState[friendsView]
        : [];

    if (!people.length) {

        list.innerHTML = emptyMarkup(
            "No connections yet.",
            "Friends, following and followers will appear here when accounts exist."
        );

        return;

    }

    list.innerHTML = people.map(person => `

        <article class="saved-item">
            <div>
                <h3>${escapeHtml(person.displayName || person.username || "Traveller")}</h3>
            </div>
        </article>

    `).join("");

}


/* =========================================================
   TABS
========================================================= */

function setupProfileTabs() {

    const tablist = document.querySelector(".profile-tablist");

    if (!tablist || tablist.dataset.bound === "true") {
        return;
    }

    tablist.dataset.bound = "true";

    tablist.addEventListener("click", event => {

        const tab = event.target.closest("[data-tab]");

        if (!tab) {
            return;
        }

        setActiveTab(tab.dataset.tab);

    });

    tablist.addEventListener("keydown", event => {

        const tabs = Array.from(
            tablist.querySelectorAll("[data-tab]")
        );

        const current = tabs.indexOf(document.activeElement);

        if (current < 0) {
            return;
        }

        let next = current;

        if (event.key === "ArrowRight") {
            next = (current + 1) % tabs.length;
        } else if (event.key === "ArrowLeft") {
            next = (current - 1 + tabs.length) % tabs.length;
        } else if (event.key === "Home") {
            next = 0;
        } else if (event.key === "End") {
            next = tabs.length - 1;
        } else {
            return;
        }

        event.preventDefault();
        tabs[next].focus();
        setActiveTab(tabs[next].dataset.tab);

    });

}


function setActiveTab(tabName) {

    if (!TAB_ORDER.includes(tabName)) {
        return;
    }

    const settingsPanel = document.getElementById("settings-panel");
    const mainUi = document.getElementById("profile-main-ui");

    if (settingsPanel) {
        settingsPanel.hidden = true;
    }

    if (mainUi) {
        mainUi.hidden = false;
    }

    document.querySelectorAll(".profile-tablist [data-tab]").forEach(tab => {

        const selected = tab.dataset.tab === tabName;

        tab.setAttribute("aria-selected", selected ? "true" : "false");
        tab.tabIndex = selected ? 0 : -1;

    });

    document.querySelectorAll(".profile-panel").forEach(panel => {

        const selected = panel.dataset.panel === tabName;

        panel.hidden = !selected;

    });

    if (history.replaceState) {
        history.replaceState(null, "", `#${tabName}`);
    }

}


function setupSavedFilters() {

    const wrap = document.querySelector(".saved-filters");

    if (!wrap || wrap.dataset.bound === "true") {
        return;
    }

    wrap.dataset.bound = "true";

    wrap.addEventListener("click", event => {

        const button = event.target.closest("[data-saved-filter]");

        if (!button) {
            return;
        }

        savedFilter = button.dataset.savedFilter;

        wrap.querySelectorAll("[data-saved-filter]").forEach(chip => {

            chip.classList.toggle(
                "is-on",
                chip === button
            );

        });

        renderSaved();

    });

}


function setupFriendsNav() {

    const wrap = document.querySelector(".friends-subnav");

    if (!wrap || wrap.dataset.bound === "true") {
        return;
    }

    wrap.dataset.bound = "true";

    wrap.addEventListener("click", event => {

        const button = event.target.closest("[data-friends-view]");

        if (!button) {
            return;
        }

        friendsView = button.dataset.friendsView;

        wrap.querySelectorAll("[data-friends-view]").forEach(tab => {

            tab.setAttribute(
                "aria-selected",
                tab === button ? "true" : "false"
            );

        });

        renderFriends();

    });

}


/* =========================================================
   EDIT PROFILE
========================================================= */

function setupEditProfile() {

    const dialog = document.getElementById("edit-profile-dialog");
    const form = document.getElementById("edit-profile-form");
    const openButtons = [
        document.getElementById("edit-profile-button"),
        document.getElementById("settings-edit-profile")
    ];
    const cancel = document.getElementById("cancel-edit-profile");

    if (!dialog || !form) {
        return;
    }

    openButtons.forEach(button => {

        if (!button || button.dataset.bound === "true") {
            return;
        }

        button.dataset.bound = "true";

        button.addEventListener("click", () => {
            openEditProfile();
        });

    });

    if (cancel && cancel.dataset.bound !== "true") {

        cancel.dataset.bound = "true";

        cancel.addEventListener("click", () => {
            dialog.close();
        });

    }

    if (form.dataset.bound === "true") {
        return;
    }

    form.dataset.bound = "true";

    form.addEventListener("submit", event => {

        event.preventDefault();

        const displayName = document.getElementById("edit-display-name").value.trim();
        const username = document.getElementById("edit-username").value.trim();
        const bio = document.getElementById("edit-bio").value.trim();
        const location = document.getElementById("edit-location").value.trim();

        if (username && !/^[A-Za-z0-9_]{3,24}$/.test(username)) {
            return;
        }

        profileState.displayName = displayName;
        profileState.username = username;
        profileState.bio = bio;
        profileState.location = location;
        profileState.avatarDataUrl = pendingAvatarDataUrl;

        try {
            saveProfile();
        } catch (error) {
            const status = document.getElementById("edit-avatar-status");
            if (status) status.textContent = "Could not save profile photo. Try a smaller image.";
            return;
        }
        renderProfile();
        dialog.close();

    });

    const editAvatarInput = document.getElementById("edit-avatar-input");
    const removeAvatarBtn = document.getElementById("remove-avatar-button");
    const editAvatarStatus = document.getElementById("edit-avatar-status");

    if (editAvatarInput && editAvatarInput.dataset.bound !== "true") {
        editAvatarInput.dataset.bound = "true";
        editAvatarInput.addEventListener("change", () => {
            const file = editAvatarInput.files && editAvatarInput.files[0];
            editAvatarInput.value = "";
            if (!file) return;
            if (editAvatarStatus) editAvatarStatus.textContent = "";
            processAvatarFile(
                file,
                dataUrl => {
                    pendingAvatarDataUrl = dataUrl;
                    renderEditAvatarPreview();
                    if (editAvatarStatus) editAvatarStatus.textContent = "Preview ready. Click SAVE to apply.";
                },
                message => {
                    if (editAvatarStatus) editAvatarStatus.textContent = message;
                }
            );
        });
    }

    if (removeAvatarBtn && removeAvatarBtn.dataset.bound !== "true") {
        removeAvatarBtn.dataset.bound = "true";
        removeAvatarBtn.addEventListener("click", () => {
            pendingAvatarDataUrl = null;
            renderEditAvatarPreview();
            if (editAvatarStatus) editAvatarStatus.textContent = "Photo removed. Click SAVE to apply.";
        });
    }

}

function renderEditAvatarPreview() {
    const preview = document.getElementById("edit-avatar-preview");
    const removeBtn = document.getElementById("remove-avatar-button");
    if (preview) renderAvatar(preview, pendingAvatarDataUrl);
    if (removeBtn) removeBtn.disabled = !pendingAvatarDataUrl;
}


function openEditProfile() {

    const dialog = document.getElementById("edit-profile-dialog");
    const editAvatarStatus = document.getElementById("edit-avatar-status");

    pendingAvatarDataUrl = profileState.avatarDataUrl || null;
    if (editAvatarStatus) editAvatarStatus.textContent = "";
    renderEditAvatarPreview();

    document.getElementById("edit-display-name").value =
        profileState.displayName;

    document.getElementById("edit-username").value =
        profileState.username;

    document.getElementById("edit-bio").value =
        profileState.bio;

    document.getElementById("edit-location").value =
        profileState.location;

    if (typeof dialog.showModal === "function") {
        dialog.showModal();
    } else {
        dialog.setAttribute("open", "");
    }

    document.getElementById("edit-display-name").focus();

}


/* =========================================================
   PREFERENCES / SETTINGS / AVATAR
========================================================= */

function setupPreferences() {

    const form = document.getElementById("preferences-form");

    if (!form || form.dataset.bound === "true") {
        return;
    }

    form.dataset.bound = "true";

    form.addEventListener("submit", event => {

        event.preventDefault();
        savePreferences();

    });

}


function savePreferences() {

    const budget = document.getElementById("budget-preference");
    const pace = document.getElementById("pace-preference");

    profileState.budgetPreference = budget && budget.value
        ? budget.value
        : null;

    profileState.pace = pace && pace.value
        ? pace.value
        : null;

    saveProfile();
    renderOverview();
    renderHeader();

    const status = document.getElementById("preferences-status");

    if (status) {
        status.textContent = "Preferences saved on this device.";
    }

}


function setupSettings() {

    const openButton = document.getElementById("open-settings-button");
    const closeButton = document.getElementById("close-settings-button");
    const form = document.getElementById("settings-form");

    if (openButton && openButton.dataset.bound !== "true") {

        openButton.dataset.bound = "true";

        openButton.addEventListener("click", () => {
            showSettings(true);
        });

    }

    if (closeButton && closeButton.dataset.bound !== "true") {

        closeButton.dataset.bound = "true";

        closeButton.addEventListener("click", () => {
            showSettings(false);
        });

    }

    if (!form || form.dataset.bound === "true") {
        return;
    }

    form.dataset.bound = "true";

    form.addEventListener("submit", event => {

        event.preventDefault();

        const appearance = form.querySelector(
            "input[name='appearance']:checked"
        );

        profileState.settings.language =
            document.getElementById("setting-language").value;

        profileState.settings.currency =
            document.getElementById("setting-currency").value;

        profileState.settings.appearance =
            appearance ? appearance.value : "light";

        profileState.settings.privacy.profileVisibility =
            document.getElementById("profile-visibility").value;

        profileState.settings.privacy.activityVisibility =
            document.getElementById("activity-visibility").value;

        profileState.settings.notifications.community =
            document.getElementById("notify-community").checked;

        profileState.settings.notifications.trips =
            document.getElementById("notify-trips").checked;

        profileState.settings.notifications.planning =
            document.getElementById("notify-planning").checked;

        saveProfile();
        renderHeader();
        if (typeof updateThemeToggleButton === "function") updateThemeToggleButton();

        const status = document.getElementById("settings-status");

        if (status) {
            status.textContent = "Settings saved on this device.";
        }

    });

    const saveButton = document.getElementById("save-settings-button");
    if (saveButton && saveButton.dataset.bound !== "true") {
        saveButton.dataset.bound = "true";
        saveButton.addEventListener("click", event => {
            event.preventDefault();
            if (typeof form.requestSubmit === "function") form.requestSubmit();
            else form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
        });
    }

}


function showSettings(open) {

    const settingsPanel = document.getElementById("settings-panel");
    const mainUi = document.getElementById("profile-main-ui");

    if (!settingsPanel || !mainUi) {
        return;
    }

    settingsPanel.hidden = !open;
    mainUi.hidden = open;

    if (open) {
        fillSettingsForm();
        settingsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    }

}


function fillSettingsAccount(user = typeof window.movaGetFirebaseUser === "function" ? window.movaGetFirebaseUser() : null) {
    const emailEl = document.getElementById("settings-auth-email");
    const providerEl = document.getElementById("settings-auth-provider");
    const noteEl = document.getElementById("settings-auth-note");
    if (!emailEl || !providerEl) return;

    if (!user) {
        emailEl.textContent = "Not signed in";
        providerEl.textContent = "None";
        if (noteEl) noteEl.textContent = "Sign in to connect your MOVA account.";
        return;
    }

    emailEl.textContent = user.email || "Signed in";
    const providers = Array.isArray(user.providerData)
        ? user.providerData
              .map(p => {
                  if (p?.providerId === "google.com") return "Google";
                  if (p?.providerId === "password") return "Email & Password";
                  return p?.providerId || "";
              })
              .filter(Boolean)
        : [];
    providerEl.textContent = providers.length ? providers.join(", ") : "Firebase Authentication";
    if (noteEl) noteEl.textContent = "Connected to Firebase Authentication.";
}

window.addEventListener("mova:auth-state", event => {
    fillSettingsAccount(event.detail?.user || null);
});

function fillSettingsForm() {

    fillSettingsAccount();

    const language = document.getElementById("setting-language");
    const currency = document.getElementById("setting-currency");
    const visibility = document.getElementById("profile-visibility");
    const activity = document.getElementById("activity-visibility");

    if (!language) {
        return;
    }

    language.value = profileState.settings.language || "en";
    currency.value = profileState.settings.currency || "INR";
    visibility.value =
        profileState.settings.privacy.profileVisibility;
    activity.value =
        profileState.settings.privacy.activityVisibility;

    document.getElementById("notify-community").checked =
        !!profileState.settings.notifications.community;

    document.getElementById("notify-trips").checked =
        !!profileState.settings.notifications.trips;

    document.getElementById("notify-planning").checked =
        !!profileState.settings.notifications.planning;

    const appearance = profileState.settings.appearance || "light";

    document.querySelectorAll("input[name='appearance']").forEach(input => {
        input.checked = input.value === appearance;
    });

}


const ALLOWED_AVATAR_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function processAvatarFile(file, onSuccess, onError) {
    if (!ALLOWED_AVATAR_TYPES.has(file.type)) {
        onError("Please choose a JPG, PNG or WebP image.");
        return;
    }

    if (file.size > 1.5 * 1024 * 1024) {
        onError("Photo is too large. Choose an image under 1.5 MB.");
        return;
    }

    const image = new Image();
    const objectUrl = URL.createObjectURL(file);

    image.onload = () => {
        const size = 256;
        const canvas = document.createElement("canvas");
        canvas.width = size;
        canvas.height = size;

        const context = canvas.getContext("2d");
        const scale = Math.max(size / image.width, size / image.height);
        const width = image.width * scale;
        const height = image.height * scale;
        const x = (size - width) / 2;
        const y = (size - height) / 2;

        context.fillStyle = "#E7B83E";
        context.fillRect(0, 0, size, size);
        context.drawImage(image, x, y, width, height);

        URL.revokeObjectURL(objectUrl);

        try {
            onSuccess(canvas.toDataURL("image/jpeg", 0.72));
        } catch {
            onError("This image could not be processed. Try a smaller image.");
        }
    };

    image.onerror = () => {
        URL.revokeObjectURL(objectUrl);
        onError("Could not read this image file.");
    };

    image.src = objectUrl;
}

function setupAvatarUpload() {

    const input = document.getElementById("avatar-upload");

    if (!input || input.dataset.bound === "true") {
        return;
    }

    input.dataset.bound = "true";

    input.addEventListener("change", () => {

        const file = input.files && input.files[0];

        input.value = "";

        if (!file) {
            return;
        }

        const status = document.getElementById("avatar-status");
        const showAvatarStatus = message => { if (status) status.textContent = message; };
        showAvatarStatus("");

        processAvatarFile(
            file,
            dataUrl => {
                try {
                    profileState.avatarDataUrl = dataUrl;
                    saveProfile();
                    renderHeader();
                    showAvatarStatus("Profile photo saved on this device.");
                } catch {
                    showAvatarStatus("This image could not be saved. Try a smaller image.");
                }
            },
            showAvatarStatus
        );

    });

}


/* =========================================================
   HELPERS
========================================================= */

function emptyMarkup(title, copy) {

    return `
        <div class="empty-state">
            <strong>${escapeHtml(title)}</strong>
            <p>${escapeHtml(copy)}</p>
        </div>
    `;

}


function labelFor(options, value) {

    const match = options.find(option => option.value === value);

    return match ? match.label : "";

}


function formatPlanDate(dateString) {

    if (!dateString) {
        return "Date not set";
    }

    const date = new Date(`${dateString}T00:00:00`);

    if (Number.isNaN(date.getTime())) {
        return dateString;
    }

    return date.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
    });

}


function formatMoney(amount) {

    const value = Number(amount);

    if (!Number.isFinite(value)) {
        return "Budget not set";
    }

    const currency = profileState.settings.currency || "INR";

    try {

        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency,
            maximumFractionDigits: 0
        }).format(value);

    } catch (error) {

        return `₹${value.toLocaleString("en-IN")}`;

    }

}


function escapeHtml(value) {

    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");

}
