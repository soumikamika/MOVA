/* =========================================================
   MOVA COMMUNITY
   Local-first community UI. Posts are user-generated and stored
   locally until the backend/media service is connected.
========================================================= */

const COMMUNITY_STORAGE_KEY = "movaCommunityPosts";
const COMMUNITY_SAVED_KEY = "movaCommunitySaved";
const COMMUNITY_PLAN_SUGGESTIONS_KEY = "movaPlanSuggestions";
const COMMUNITY_COMMENTS_KEY = "movaCommunityComments";

let communityPosts = [];
let communityFilter = "all";
let communityQuery = "";
let communityRegion = "";

const escapeHTML = (value) => String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

function loadPosts() {
    try {
        const stored = JSON.parse(localStorage.getItem(COMMUNITY_STORAGE_KEY));
        communityPosts = Array.isArray(stored) ? stored : [];
    } catch {
        communityPosts = [];
    }
}

function savePosts() {
    try {
        localStorage.setItem(COMMUNITY_STORAGE_KEY, JSON.stringify(communityPosts));
    } catch {
        setFormStatus("Your browser could not save this post. Try a smaller image.");
    }
}

function loadComments() {
    try {
        const stored = JSON.parse(localStorage.getItem(COMMUNITY_COMMENTS_KEY));
        return Array.isArray(stored) ? stored : [];
    } catch {
        return [];
    }
}

function saveComments(comments) {
    try {
        localStorage.setItem(COMMUNITY_COMMENTS_KEY, JSON.stringify(comments));
    } catch {
        // Keep the community page usable if browser storage is unavailable.
    }
}

function getPostComments(postId) {
    return loadComments().filter(comment => comment.postId === postId);
}

function getSavedPosts() {
    try {
        const saved = JSON.parse(localStorage.getItem(COMMUNITY_SAVED_KEY));
        return new Set(Array.isArray(saved) ? saved : []);
    } catch {
        return new Set();
    }
}

function setSavedPosts(saved) {
    localStorage.setItem(COMMUNITY_SAVED_KEY, JSON.stringify([...saved]));
}

function formatDate(dateString) {
    try {
        return new Intl.DateTimeFormat("en-IN", {
            day: "numeric",
            month: "short",
            year: "numeric"
        }).format(new Date(dateString));
    } catch {
        return "Recently";
    }
}

function typeLabel(type) {
    return {
        story: "STORY",
        guide: "GUIDE",
        tip: "TIP",
        photo: "PHOTO"
    }[type] || "POST";
}

function normalizeTags(tags) {
    if (Array.isArray(tags)) return tags.filter(Boolean).slice(0, 8);
    return String(tags || "")
        .split(",")
        .map(tag => tag.trim().replace(/^#/, ""))
        .filter(Boolean)
        .slice(0, 8);
}

function renderFeed() {
    const feed = document.getElementById("community-feed");
    if (!feed) return;

    const query = communityQuery.trim().toLowerCase();
    const filtered = communityPosts.filter(post => {
        const matchesType = communityFilter === "all" || post.type === communityFilter;
        const requestedRegion = communityRegion.trim().toLowerCase();
        const postTags = normalizeTags(post.tags).map(tag => tag.toLowerCase());
        const matchesRegion = !requestedRegion ||
            String(post.regionName || post.region || "").trim().toLowerCase() === requestedRegion ||
            String(post.locationName || "").trim().toLowerCase() === requestedRegion ||
            postTags.some(tag => tag.replace(/^#+/, "") === requestedRegion);
        const haystack = [
            post.caption,
            post.locationName,
            post.tip,
            post.bestTime,
            post.regionName,
            ...(Array.isArray(post.tags) ? post.tags : normalizeTags(post.tags))
        ].join(" ").toLowerCase();
        return matchesType && matchesRegion && (!query || haystack.includes(query));
    });

    if (!filtered.length) {
        const hasAnyPosts = communityPosts.length > 0;
        feed.innerHTML = `
            <div class="community-empty">
                <h3>${hasAnyPosts ? "NOTHING MATCHED." : "THE COMMUNITY STARTS HERE."}</h3>
                <p>
                    ${hasAnyPosts
                        ? "Try another search or filter."
                        : "There are no community posts in this browser yet. Be the first traveller to share a real experience."}
                </p>
                <button class="btn btn-primary" type="button" id="empty-post-button">SHARE A POST</button>
            </div>
        `;
        document.getElementById("empty-post-button")?.addEventListener("click", openPostDialog);
        return;
    }

    feed.innerHTML = filtered.map(renderPost).join("");
    bindPostActions();
}

function renderPost(post) {
    const saved = getSavedPosts().has(post.id);
    const tags = normalizeTags(post.tags);
    const cost = post.cost !== "" && post.cost !== null && post.cost !== undefined
        ? `₹${Number(post.cost).toLocaleString("en-IN")} / PERSON`
        : "";
    const rating = post.rating ? `${post.rating}/5 EXPERIENCE` : "";

    return `
        <article class="community-post" data-post-id="${escapeHTML(post.id)}">
            <div class="community-post-main">
                <div class="community-post-visual">
                    <span class="community-post-type">${escapeHTML(typeLabel(post.type))}</span>
                    ${post.image
                        ? `<img src="${post.image}" alt="Community post from ${escapeHTML(post.locationName)}" loading="lazy">`
                        : `<div class="community-post-placeholder">
                            <strong>${escapeHTML(post.locationName || "INDIA")}</strong>
                            <span>TRAVEL NOTE · ${escapeHTML(typeLabel(post.type))}</span>
                           </div>`}
                </div>
                <div class="community-post-body">
                    <div class="post-meta">
                        <span class="post-location">📍 ${escapeHTML(post.locationName)}</span>
                        <span>${escapeHTML(formatDate(post.createdAt))}</span>
                    </div>
                    <h3>${escapeHTML(post.caption).split("\n")[0].slice(0, 110)}</h3>
                    <p class="post-caption">${escapeHTML(post.caption)}</p>

                    ${tags.length ? `<div class="post-tags">${tags.map(tag => `<span class="post-tag">#${escapeHTML(tag)}</span>`).join("")}</div>` : ""}

                    ${(cost || rating || post.bestTime) ? `
                        <div class="post-details">
                            ${cost ? `<span class="post-detail-chip">${cost}</span>` : ""}
                            ${rating ? `<span class="post-detail-chip">★ ${rating}</span>` : ""}
                            ${post.bestTime ? `<span class="post-detail-chip">BEST: ${escapeHTML(post.bestTime)}</span>` : ""}
                        </div>
                    ` : ""}

                    ${post.tip ? `<div class="post-tip"><strong>TRAVELLER TIP:</strong> ${escapeHTML(post.tip)}</div>` : ""}

                    <div class="post-actions">
                        <button class="post-action save-action ${saved ? "active" : ""}" type="button" data-action="save">${saved ? "★ SAVED" : "☆ SAVE"}</button>
                        <button class="post-action detail-action" type="button" data-action="details">VIEW</button>
                        <button class="post-action plan-action" type="button" data-action="plan">ADD TO MY PLAN</button>
                        ${post.owner === "local" ? `<button class="post-action delete-action" type="button" data-action="delete">DELETE</button>` : ""}
                    </div>
                </div>
            </div>
        </article>
    `;
}

function bindPostActions() {
    document.querySelectorAll(".community-post").forEach(card => {
        const id = card.dataset.postId;
        card.querySelectorAll("[data-action]").forEach(button => {
            button.addEventListener("click", () => handlePostAction(id, button.dataset.action));
        });
    });
}

function findPost(id) {
    return communityPosts.find(post => post.id === id);
}

function handlePostAction(id, action) {
    const post = findPost(id);
    if (!post) return;

    if (action === "save") {
        const saved = getSavedPosts();
        if (saved.has(id)) saved.delete(id); else saved.add(id);
        setSavedPosts(saved);
        renderFeed();
        return;
    }

    if (action === "delete") {
        if (!window.confirm("Delete this post from this browser?")) return;
        communityPosts = communityPosts.filter(item => item.id !== id);
        saveComments(loadComments().filter(comment => comment.postId !== id));
        const saved = getSavedPosts();
        saved.delete(id);
        setSavedPosts(saved);
        savePosts();
        renderFeed();
        return;
    }

    if (action === "plan") {
        try {
            const current = JSON.parse(localStorage.getItem(COMMUNITY_PLAN_SUGGESTIONS_KEY)) || [];
            const exists = current.some(item => item.postId === post.id);
            if (!exists) {
                current.push({
                    postId: post.id,
                    locationId: post.locationId,
                    locationName: post.locationName,
                    source: "community",
                    addedAt: new Date().toISOString()
                });
                localStorage.setItem(COMMUNITY_PLAN_SUGGESTIONS_KEY, JSON.stringify(current));
            }
            alert(`${post.locationName} was saved as a planning suggestion.`);
        } catch {
            alert("Could not save this planning suggestion in your browser.");
        }
        return;
    }

    if (action === "details") openPostDetail(post);
}

function openPostDetail(post) {
    const dialog = document.getElementById("post-detail-dialog");
    const content = document.getElementById("post-detail-content");
    if (!dialog || !content) return;

    const comments = getPostComments(post.id);
    content.innerHTML = `
        <div class="detail-dialog-content">
            <div class="section-number">${escapeHTML(typeLabel(post.type))} · ${escapeHTML(formatDate(post.createdAt))}</div>
            <h2 id="post-detail-title">${escapeHTML(post.locationName)}</h2>
            ${post.image ? `<img class="detail-image" src="${post.image}" alt="Community post from ${escapeHTML(post.locationName)}">` : ""}
            <p>${escapeHTML(post.caption)}</p>
            ${post.tip ? `<div class="post-tip"><strong>TRAVELLER TIP:</strong> ${escapeHTML(post.tip)}</div>` : ""}
            <div class="post-details">
                ${post.cost ? `<span class="post-detail-chip">₹${Number(post.cost).toLocaleString("en-IN")} / PERSON</span>` : ""}
                ${post.rating ? `<span class="post-detail-chip">★ ${escapeHTML(post.rating)}/5</span>` : ""}
                ${post.bestTime ? `<span class="post-detail-chip">BEST: ${escapeHTML(post.bestTime)}</span>` : ""}
            </div>
            <section class="post-comments" aria-labelledby="post-comments-title">
                <div class="post-comments-heading"><div><span class="section-number">COMMUNITY</span><h3 id="post-comments-title">COMMENTS</h3></div><span class="comment-count">${comments.length}</span></div>
                <div id="post-comments-list" class="post-comments-list">
                    ${comments.length ? comments.map(renderComment).join("") : `<p class="comments-empty">No comments yet. Be the first to add something useful.</p>`}
                </div>
                <form id="post-comment-form" class="post-comment-form">
                    <textarea id="post-comment-input" rows="3" maxlength="400" placeholder="Add a useful comment..." required></textarea>
                    <button class="btn btn-primary" type="submit">ADD COMMENT →</button>
                </form>
            </section>
            <div class="detail-close-row"><button class="btn btn-secondary" id="close-detail-dialog" type="button">CLOSE</button></div>
        </div>
    `;
    document.getElementById("post-comment-form")?.addEventListener("submit", event => {
        event.preventDefault();
        const input = document.getElementById("post-comment-input");
        const text = input?.value.trim();
        if (!text) return;
        const all = loadComments();
        all.push({ id:`comment-${Date.now()}-${Math.random().toString(36).slice(2,7)}`, postId:post.id, text, owner:"local", createdAt:new Date().toISOString() });
        saveComments(all);
        dialog.close();
        openPostDetail(post);
    });
    dialog.showModal();
    document.getElementById("close-detail-dialog")?.addEventListener("click", () => dialog.close());
}

function renderComment(comment) {
    return `<article class="post-comment"><div><strong>YOU</strong><span>${escapeHTML(formatDate(comment.createdAt))}</span></div><p>${escapeHTML(comment.text)}</p></article>`;
}

function openPostDialog() {
    const dialog = document.getElementById("post-dialog");
    if (!dialog) return;
    resetPostForm();
    const regionInput = document.getElementById("post-region-name");
    if (regionInput && communityRegion) regionInput.value = communityRegion;
    dialog.showModal();
}

function closePostDialog() {
    document.getElementById("post-dialog")?.close();
}

function setFormStatus(message) {
    const status = document.getElementById("post-form-status");
    if (status) status.textContent = message;
}

function resetPostForm() {
    const form = document.getElementById("community-post-form");
    const preview = document.getElementById("post-image-preview");
    if (form) form.reset();
    if (preview) {
        preview.hidden = true;
        preview.innerHTML = "";
    }
    setFormStatus("");
}

async function loadLocations() {
    const select = document.getElementById("post-location");
    if (!select) return;

    try {
        const response = await fetch("../data/destinations.json", { cache: "no-store" });
        if (!response.ok) throw new Error("Could not load destinations");
        const destinations = await response.json();
        destinations.forEach(destination => {
            const option = document.createElement("option");
            option.value = destination.id;
            option.textContent = destination.name;
            option.dataset.name = destination.name;
            select.appendChild(option);
        });
    } catch {
        setFormStatus("Destination data could not be loaded. Please use the page from the project server rather than file://.");
    }
}

function bindImagePreview() {
    const input = document.getElementById("post-image");
    const preview = document.getElementById("post-image-preview");
    if (!input || !preview) return;

    input.addEventListener("change", () => {
        const file = input.files?.[0];
        if (!file) {
            preview.hidden = true;
            preview.innerHTML = "";
            return;
        }

        if (!file.type.startsWith("image/")) {
            input.value = "";
            setFormStatus("Please choose an image file.");
            return;
        }

        if (file.size > 2 * 1024 * 1024) {
            input.value = "";
            setFormStatus("For this local version, keep images under 2 MB.");
            return;
        }

        const reader = new FileReader();
        reader.onload = () => {
            preview.innerHTML = `<img src="${reader.result}" alt="Selected community photo preview">`;
            preview.hidden = false;
        };
        reader.readAsDataURL(file);
    });
}

function handlePostSubmit(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const locationSelect = document.getElementById("post-location");
    const locationOption = locationSelect?.selectedOptions?.[0];

    const caption = String(formData.get("caption") || "").trim();
    const locationId = String(formData.get("location") || "");
    const locationName = locationOption?.dataset.name || locationOption?.textContent || "";

    if (!caption || !locationId) {
        setFormStatus("Add a caption and choose a place before publishing.");
        return;
    }

    const imageInput = document.getElementById("post-image");
    const file = imageInput?.files?.[0];

    const finish = (image = "") => {
        const post = {
            id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            owner: "local",
            type: String(formData.get("type") || "story"),
            locationId,
            locationName,
            regionName: String(formData.get("regionName") || communityRegion || "").trim(),
            caption,
            cost: String(formData.get("cost") || "").trim(),
            rating: String(formData.get("rating") || "").trim(),
            bestTime: String(formData.get("bestTime") || "").trim(),
            tags: normalizeTags(formData.get("tags")),
            tip: String(formData.get("tip") || "").trim(),
            image,
            createdAt: new Date().toISOString()
        };

        communityPosts.unshift(post);
        savePosts();
        communityFilter = "all";
        communityQuery = "";
        document.getElementById("community-search").value = "";
        document.querySelectorAll(".community-filter").forEach(button => button.classList.toggle("active", button.dataset.filter === "all"));
        renderFeed();
        closePostDialog();
        document.getElementById("community-feed")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    if (file) {
        const reader = new FileReader();
        reader.onload = () => finish(String(reader.result || ""));
        reader.onerror = () => setFormStatus("The image could not be read. Try again or publish without it.");
        reader.readAsDataURL(file);
    } else {
        finish();
    }
}

function bindCommunityUI() {
    document.getElementById("open-post-modal")?.addEventListener("click", openPostDialog);
    document.getElementById("sidebar-post-button")?.addEventListener("click", openPostDialog);
    document.getElementById("close-post-modal")?.addEventListener("click", closePostDialog);
    document.getElementById("cancel-post")?.addEventListener("click", closePostDialog);
    document.getElementById("community-post-form")?.addEventListener("submit", handlePostSubmit);
    document.getElementById("post-detail-dialog")?.addEventListener("click", event => {
        if (event.target === event.currentTarget) event.currentTarget.close();
    });
    document.getElementById("post-dialog")?.addEventListener("click", event => {
        if (event.target === event.currentTarget) event.currentTarget.close();
    });

    document.querySelectorAll(".community-filter").forEach(button => {
        button.addEventListener("click", () => {
            communityFilter = button.dataset.filter || "all";
            document.querySelectorAll(".community-filter").forEach(item => item.classList.toggle("active", item === button));
            renderFeed();
        });
    });

    document.getElementById("community-search")?.addEventListener("input", event => {
        communityQuery = event.target.value || "";
        renderFeed();
    });

    bindImagePreview();
}

document.addEventListener("DOMContentLoaded", async () => {
    const params = new URLSearchParams(location.search);
    communityRegion = params.get("region") || "";
    loadPosts();
    bindCommunityUI();
    await loadLocations();
    renderFeed();
    if (params.get("compose") === "1") openPostDialog();
    const requestedPost = params.get("post");
    if (requestedPost) {
        const post = findPost(requestedPost);
        if (post) openPostDetail(post);
    }
});
