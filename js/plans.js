/* =========================================================
   MOVA — PLAN CREATION + MY PLANS
   Connected to the MOVA Travel Intelligence Engine.
========================================================= */

let destinations = [];
let selectedDestination = null;
let selectedDestinations = [];
let mustVisitPlaces = [];
let invitedPeople = [];
let originLocation = null;
let travellerCount = 1;
let plannerCapabilities = null;

const MOVA_PLANS_KEY = "movaPlans";
const MOVA_PLAN_RESULT_KEY = "movaPlanResults";

/* =========================================================
   INITIALIZE
========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    setupCreatePlanButtons();
    initializePlanner();
    loadSavedPlans();
    setupPlanActions();
});

/* =========================================================
   CREATE PLAN BUTTONS
========================================================= */

function setupCreatePlanButtons() {
    [
        document.getElementById("create-plan-button"),
        document.getElementById("empty-create-plan-button")
    ].forEach(button => {
        if (!button) return;
        button.addEventListener("click", () => {
            window.location.href = "create-plan.html";
        });
    });
}

/* =========================================================
   CREATE PLAN INITIALIZATION
========================================================= */

async function initializePlanner() {
    const form = document.getElementById("create-plan-form");
    if (!form) return;

    await loadDestinations();
    await loadPlannerCapabilities();
    setupDestinationSearch();
    setupMultiDestinationControls();
    setupMustVisitControls();
    setupInviteControls();
    setupLocationCapture();
    setupTravellerCounter();
    setupDateValidation();
    setupTravelCostFields();
    setupMustVisitDialog();
    setupPlannerProgress();
    setupFormSubmission();
    setupEngineStatus();

    const retryButton = document.getElementById("planner-engine-retry");
    if (retryButton) {
        retryButton.addEventListener("click", async () => {
            retryButton.disabled = true;
            retryButton.textContent = "CHECKING...";
            try {
                await movaHealthCheck();
                setEngineStatus(
                    "READY",
                    "The MOVA planning engine is reachable. Your plan will be generated from the information you provide."
                );
            } catch (error) {
                setEngineStatus(
                    "BACKEND OFFLINE",
                    friendlyApiError(error),
                    "error"
                );
            } finally {
                retryButton.disabled = false;
                retryButton.textContent = "RETRY CONNECTION";
            }
        });
    }

    // A failed health check is informational only; the actual request
    // remains the source of truth.
    try {
        await movaHealthCheck();
        setEngineStatus(
            "READY",
            "The MOVA planning engine is reachable. Your plan will be generated from the information you provide."
        );
    } catch {
        setEngineStatus(
            "BACKEND OFFLINE",
            `The planning engine is not reachable at ${getMovaApiBase()}. Start FastAPI locally, or configure the deployed API URL.`,
            "error"
        );
    }
}

function setupEngineStatus() {
    const status = document.getElementById("planner-engine-status");
    if (status) status.dataset.state = "ready";
}

function setEngineStatus(title, message, state = "ready") {
    const status = document.getElementById("planner-engine-status");
    const messageNode = document.getElementById("planner-engine-message");
    if (!status) return;

    status.dataset.state = state;

    const strong = status.querySelector("strong");
    if (strong) strong.textContent = title;
    if (messageNode) messageNode.textContent = message;
}

/* =========================================================
   PLANNER CAPABILITIES
========================================================= */

async function loadPlannerCapabilities() {
    try {
        plannerCapabilities = await movaCapabilities();
        updatePlannerCapabilityNotice();
    } catch (error) {
        plannerCapabilities = null;
        // The real generate request remains authoritative; this endpoint is
        // only used to explain which bundled datasets are currently available.
        console.warn("MOVA capabilities unavailable:", error);
    }
}

function supportedDestinationNames() {
    return new Set(
        (plannerCapabilities?.planner?.supported_destinations || [])
            .map(item => String(item.name || "").toLowerCase())
    );
}

function updatePlannerCapabilityNotice() {
    const status = document.getElementById("planner-engine-status");
    const message = document.getElementById("planner-engine-message");
    if (!status || !message || !plannerCapabilities?.planner) return;

    const planner = plannerCapabilities.planner;
    if (!planner.available) {
        status.dataset.state = "error";
        const strong = status.querySelector("strong");
        if (strong) strong.textContent = "PLANNER DATA UNAVAILABLE";
        message.textContent = "The planning engine is running, but no destination and place dataset is configured.";
        return;
    }

    if (planner.development_only && plannerCapabilities?.providers?.osm?.enabled) {
        message.textContent =
            `${planner.destination_count} destination is bundled locally; other destinations can use live OpenStreetMap discovery when available. ` +
            `Bundled development records are clearly marked in the generated plan.`;
    } else if (planner.development_only) {
        message.textContent =
            `${planner.destination_count} planner destination is currently bundled for development. Generated itineraries using this dataset are marked as development data.`;
    }
}

/* =========================================================
   DESTINATION DATA
========================================================= */

async function loadDestinations() {
    try {
        const response = await fetch("../data/destinations.json");
        if (!response.ok) throw new Error("Could not load destination data.");
        destinations = await response.json();
    } catch (error) {
        console.error("Destination loading error:", error);
        destinations = [];
    }
}

/* =========================================================
   DESTINATION SEARCH
========================================================= */

function setupDestinationSearch() {
    const input = document.getElementById("destination-search");
    const results = document.getElementById("destination-results");
    if (!input || !results) return;

    input.addEventListener("input", () => {
        const query = input.value.trim().toLowerCase();
        selectedDestination = null;

        if (!query) {
            results.innerHTML = "";
            return;
        }

        const matches = destinations
            .filter(destination => {
                const name = String(destination.name || "").toLowerCase();
                const region = String(destination.region || "").toLowerCase();
                const id = String(destination.id || "").toLowerCase();
                return name.includes(query) || region.includes(query) || id.includes(query);
            })
            .slice(0, 8);

        if (!matches.length) {
            results.innerHTML = `
                <div class="destination-no-results">
                    No matching destinations found.
                </div>
            `;
            return;
        }

        results.innerHTML = matches.map(destination => `
            <button
                type="button"
                class="destination-result"
                data-destination-id="${escapeHtml(destination.id)}"
            >
                <span class="destination-result-name">
                    ${escapeHtml(destination.name)}
                </span>
                <span class="destination-result-region">
                    ${escapeHtml(destination.region || "")}
                </span>
            </button>
        `).join("");

        setupDestinationResults();
    });
}

function setupDestinationResults() {
    document.querySelectorAll(".destination-result").forEach(button => {
        button.addEventListener("click", () => {
            const destinationId = button.dataset.destinationId;
            const destination = destinations.find(item => item.id === destinationId);
            if (!destination) return;

            selectedDestination = destination;

            const input = document.getElementById("destination-search");
            if (input) input.value = destination.name;

            const results = document.getElementById("destination-results");
            if (results) {
                const supported = supportedDestinationNames().has(String(destination.name || "").toLowerCase());
        const liveEnabled = Boolean(plannerCapabilities?.providers?.osm?.enabled);
                results.innerHTML = `
                    <div class="destination-selected ${supported ? "" : "destination-selected-warning"}">
                        <div>
                            <strong>${escapeHtml(destination.name)}</strong>
                            <span>${escapeHtml(destination.region || "")}</span>
                        </div>
                        <span class="destination-engine-badge">
                            ${supported ? "PLANNER READY" : (liveEnabled ? "LIVE DISCOVERY" : "DISCOVERY ONLY")}
                        </span>
                    </div>
                `;
            }
        });
    });
}

/* =========================================================
   MULTI-DESTINATION / MUST-VISIT / INVITES / LOCATION
========================================================= */

function renderSelectedDestinations() {
    const box = document.getElementById("selected-destinations");
    if (!box) return;
    box.innerHTML = selectedDestinations.map((item, index) => `
        <div class="selected-destination-chip">
            <span><b>${index + 1}</b> ${escapeHtml(item.name)} <small>${escapeHtml(item.region || "")}</small></span>
            <button type="button" data-remove-destination="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(item.name)}">×</button>
        </div>`).join("");
    const hidden = document.getElementById("destination-list");
    if (hidden) hidden.value = JSON.stringify(selectedDestinations.map(item => item.name));
    box.querySelectorAll("[data-remove-destination]").forEach(button => button.addEventListener("click", () => {
        selectedDestinations = selectedDestinations.filter(item => item.id !== button.dataset.removeDestination);
        if (selectedDestination?.id === button.dataset.removeDestination) selectedDestination = selectedDestinations[0] || null;
        renderSelectedDestinations();
    }));
}

function setupMultiDestinationControls() {
    const add = document.getElementById("add-destination-button");
    const input = document.getElementById("destination-search");
    if (!add || !input) return;
    add.addEventListener("click", () => {
        if (!selectedDestination) { input.focus(); showPlanToast("Search and select a destination first."); return; }
        if (selectedDestinations.some(item => item.id === selectedDestination.id)) { showPlanToast("That destination is already in the route."); return; }
        selectedDestinations.push(selectedDestination); renderSelectedDestinations(); showPlanToast(`${selectedDestination.name} added to the journey.`);
        input.value = ""; document.getElementById("destination-results").innerHTML = ""; selectedDestination = null;
    });
    renderSelectedDestinations();
}

function setupMustVisitControls() {
    const add = document.getElementById("add-must-visit");
    if (!add) return;
    
    try {
        const saved = localStorage.getItem("movaDraftMustVisitPlaces");
        if (saved) {
            const parsed = JSON.parse(saved);
            if (Array.isArray(parsed)) mustVisitPlaces = parsed;
        }
    } catch {}

    const render = () => {
        const box = document.getElementById("must-visit-list");
        if (!box) return;
        box.innerHTML = mustVisitPlaces.map((name, i) => `<div class="must-visit-chip"><span>${i + 1}. ${escapeHtml(name)}</span><button type="button" data-remove-must="${i}">×</button></div>`).join("");
        box.querySelectorAll("[data-remove-must]").forEach(b => b.addEventListener("click", () => { 
            mustVisitPlaces.splice(Number(b.dataset.removeMust), 1); 
            localStorage.setItem("movaDraftMustVisitPlaces", JSON.stringify(mustVisitPlaces));
            render(); 
        }));
    };
    add.addEventListener("click", () => {
        if (mustVisitPlaces.length >= 8) { showPlanToast("You can pin up to 8 must-visit places."); return; }
        const dialog = document.getElementById("must-visit-dialog");
        const input = document.getElementById("must-visit-input");
        if (dialog && typeof dialog.showModal === "function") {
            input.value = "";
            dialog.showModal();
            setTimeout(() => input.focus(), 0);
        } else {
            const value = window.prompt("Place you want to visit (for example: Baga Beach)");
            if (value?.trim()) addMustVisit(value.trim());
        }
    });

    function addMustVisit(value) {
        if (mustVisitPlaces.length >= 8) return;
        mustVisitPlaces.push(value.trim());
        localStorage.setItem("movaDraftMustVisitPlaces", JSON.stringify(mustVisitPlaces));
        render();
        window.updatePlannerProgress?.();
    }

    window.__movaAddMustVisit = addMustVisit;
    render();
}

function setupMustVisitDialog() {
    const dialog = document.getElementById("must-visit-dialog");
    const form = document.getElementById("must-visit-dialog-form");
    const input = document.getElementById("must-visit-input");
    const cancel = document.getElementById("cancel-must-visit");
    if (!dialog || !form || !input) return;
    cancel?.addEventListener("click", () => dialog.close());
    form.addEventListener("submit", event => {
        event.preventDefault();
        const value = input.value.trim();
        if (!value) { input.focus(); return; }
        window.__movaAddMustVisit?.(value);
        dialog.close();
    });
    dialog.addEventListener("click", event => {
        if (event.target === dialog) dialog.close();
    });
}

function setupPlannerProgress() {
    const form = document.getElementById("create-plan-form");
    if (!form) return;
    const update = () => {
        const required = [...form.querySelectorAll("[required]")];
        const complete = required.filter(el => {
            if (el.type === "radio") return form.querySelector(`input[name="${el.name}"]:checked`);
            if (el.type === "checkbox") return el.checked;
            return String(el.value || "").trim() !== "";
        }).length;
        const uniqueRequiredNames = new Set(required.map(el => el.name || el.id)).size || 1;
        const doneNames = new Set(required.filter(el => {
            if (el.type === "radio") return form.querySelector(`input[name="${el.name}"]:checked`);
            if (el.type === "checkbox") return el.checked;
            return String(el.value || "").trim() !== "";
        }).map(el => el.name || el.id));
        const pct = Math.min(100, Math.round(doneNames.size / uniqueRequiredNames * 100));
        const fill = document.getElementById("planner-progress-fill");
        const text = document.getElementById("planner-progress-text");
        if (fill) fill.style.width = `${pct}%`;
        if (text) text.textContent = `${pct}% COMPLETE`;
    };
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    window.updatePlannerProgress = update;
    update();
}

function setupInviteControls() {
    const add = document.getElementById("add-invite");
    const input = document.getElementById("invite-person");
    const render = () => {
        const box = document.getElementById("invite-list"); if (!box) return;
        box.innerHTML = invitedPeople.map((person, i) => `<div class="invite-chip"><span>${escapeHtml(person)}</span><button type="button" data-remove-invite="${i}">×</button></div>`).join("");
        box.querySelectorAll("[data-remove-invite]").forEach(b => b.addEventListener("click", () => { invitedPeople.splice(Number(b.dataset.removeInvite), 1); render(); }));
    };
    if (add && input) add.addEventListener("click", () => { const v=input.value.trim(); if (!v) return; if (!invitedPeople.includes(v)) invitedPeople.push(v); input.value=""; render(); });
    render();
}

function setupLocationCapture() {
    const button = document.getElementById("use-my-location");
    const status = document.getElementById("origin-status");
    const message = document.getElementById("origin-message");
    if (!button || !navigator.geolocation) { if (status) status.textContent="LOCATION NOT AVAILABLE"; return; }
    button.addEventListener("click", () => {
        button.disabled = true; button.textContent = "LOCATING...";
        navigator.geolocation.getCurrentPosition(pos => {
            originLocation = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
            if (status) status.textContent = "STARTING LOCATION CAPTURED";
            if (message) message.textContent = `Coordinates captured for distance and travel-mode calculations. (${pos.coords.latitude.toFixed(4)}, ${pos.coords.longitude.toFixed(4)})`;
            button.textContent = "LOCATION ADDED";
            button.disabled = false;
        }, () => {
            if (status) status.textContent = "LOCATION NOT SHARED";
            if (message) message.textContent = "You can still enter your starting city manually. MOVA will use it for the route context.";
            button.textContent = "TRY AGAIN"; button.disabled = false;
        }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
    });
}

/* =========================================================
   TRAVELLERS
========================================================= */

function setupTravellerCounter() {
    const minus = document.getElementById("travellers-minus");
    const plus = document.getElementById("travellers-plus");
    const output = document.getElementById("travellers-count");

    if (!minus || !plus || !output) return;

    minus.addEventListener("click", () => {
        if (travellerCount <= 1) return;
        travellerCount--;
        output.textContent = travellerCount;
    });

    plus.addEventListener("click", () => {
        if (travellerCount >= 20) return;
        travellerCount++;
        output.textContent = travellerCount;
    });
}

/* =========================================================
   DATES
========================================================= */

function setupDateValidation() {
    const startDate = document.getElementById("start-date");
    const endDate = document.getElementById("end-date");
    if (!startDate || !endDate) return;

    const now = new Date();
    const today =
        `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
    startDate.min = today;
    endDate.min = today;

    startDate.addEventListener("change", () => {
        endDate.min = startDate.value || today;

        if (endDate.value && endDate.value < startDate.value) {
            endDate.value = "";
        }
    });
}

/* =========================================================
   FORM SUBMISSION
========================================================= */

function setupTravelCostFields() {
    const checkboxes = document.querySelectorAll('input[name="preferred_transport"]');
    const fuelBox = document.getElementById("self-drive-fields");
    const mileage = document.getElementById("mileage");
    const fuelPrice = document.getElementById("fuel-price");
    const update = () => {
        const road = Array.from(document.querySelectorAll('input[name="preferred_transport"]:checked')).some(cb => cb.value === "car");
        if (fuelBox) fuelBox.hidden = !road;
        if (mileage) mileage.required = road;
        if (fuelPrice) fuelPrice.required = road;
    };
    checkboxes.forEach(r => r.addEventListener("change", update));
    update();
}

function setupFormSubmission() {
    const form = document.getElementById("create-plan-form");
    if (!form) return;
    form.addEventListener("submit", handlePlanSubmission);
}

function collectPlanData() {
    const form = document.getElementById("create-plan-form");
    const formData = new FormData(form);
    const destinationsForPlan = selectedDestinations.length
        ? selectedDestinations.map(item => ({ id: item.id, name: item.name, region: item.region || "" }))
        : selectedDestination ? [{ id: selectedDestination.id, name: selectedDestination.name, region: selectedDestination.region || "" }] : [];

    return {
        destination: destinationsForPlan[0]?.name || formData.get("destination"),
        destinations: destinationsForPlan.map(item => item.name),
        destination_ids: destinationsForPlan.map(item => item.id),
        must_visit_places: [...mustVisitPlaces],
        start_date: formData.get("startDate"),
        end_date: formData.get("endDate"),
        travellers: travellerCount,
        trip_type: String(formData.get("tripType") || "").toLowerCase(),
        budget: Number(formData.get("budget")),
        food_budget_per_person_per_day: Number(formData.get("foodBudget")),
        vehicle_fuel_type: String(formData.get("fuelType") || "").toLowerCase() || null,
        vehicle_mileage_kmpl: formData.get("mileage") ? Number(formData.get("mileage")) : null,
        fuel_price_inr_per_litre: formData.get("fuelPrice") ? Number(formData.get("fuelPrice")) : null,
        interests: formData.getAll("interests"),
        dislikes: formData.getAll("dislikes"),
        preferred_travel_methods: Array.from(formData.getAll("preferred_transport")),
        avoid_travel_methods: Array.from(formData.getAll("avoid_transport")),
        activity_level: "moderate",
        origin: document.getElementById("origin-name")?.value.trim() || null,
        origin_latitude: originLocation?.latitude ?? null,
        origin_longitude: originLocation?.longitude ?? null,
        invited_people: [...invitedPeople]
    };
}

async function handlePlanSubmission(event) {
    event.preventDefault();

    if (!selectedDestination) {
        setEngineStatus(
            "DESTINATION REQUIRED",
            "Choose a destination from the MOVA suggestions before building the itinerary.",
            "error"
        );
        document.getElementById("destination-search")?.focus();
        return;
    }

    const trip = collectPlanData();

    if (!trip.start_date || !trip.end_date || trip.end_date < trip.start_date) {
        setEngineStatus(
            "CHECK YOUR DATES",
            "Choose a valid start and end date before sending the plan to the engine.",
            "error"
        );
        return;
    }

    if (!Number.isFinite(trip.budget) || trip.budget <= 0) {
        setEngineStatus(
            "CHECK YOUR BUDGET",
            "Enter a total trip budget greater than ₹0.",
            "error"
        );
        return;
    }

    if (!Number.isFinite(trip.food_budget_per_person_per_day) || trip.food_budget_per_person_per_day < 0) {
        setEngineStatus("CHECK YOUR FOOD BUDGET", "Enter a daily food amount per person so MOVA can count food in the trip budget.", "error");
        return;
    }

    if ((trip.preferred_travel_methods || []).includes("car")) {
        if (!trip.vehicle_mileage_kmpl || !Number.isFinite(trip.vehicle_mileage_kmpl) || trip.vehicle_mileage_kmpl <= 0 || trip.fuel_price_inr_per_litre === null || !Number.isFinite(trip.fuel_price_inr_per_litre) || trip.fuel_price_inr_per_litre < 0) {
            setEngineStatus("ADD FUEL DETAILS", "For self-drive, enter mileage and current fuel price so MOVA can calculate the fuel cost.", "error");
            return;
        }
    }

    const submitButton = document.querySelector(".planner-submit-button");
    const originalText = submitButton?.innerHTML;

    if (submitButton) {
        submitButton.disabled = true;
        submitButton.innerHTML = `
            BUILDING PLAN
            <span class="button-arrow">↻</span>
        `;
    }

    setEngineStatus(
        "BUILDING YOUR PLAN",
        "MOVA is resolving the destination, ranking candidates, checking constraints and optimizing the itinerary.",
        "loading"
    );

    try {
        const result = await generateMovaPlan({ trip });
        saveGeneratedPlan(result);
        window.location.href = `edit-plan.html?plan=${encodeURIComponent(result.plan_id)}`;
    } catch (error) {
        console.error("MOVA plan generation failed:", error);

        setEngineStatus(
            error.code === "not_found" ? "DESTINATION NOT AVAILABLE" : "PLAN COULD NOT BE BUILT",
            friendlyApiError(error),
            "error"
        );

        if (error.code === "not_found") {
            setEngineStatus(
                "ENGINE DATA LIMIT",
                `${friendlyApiError(error)} The current development engine may only contain a subset of destinations.`,
                "error"
            );
        }
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerHTML = originalText || `
                BUILD MY REAL PLAN
                <span class="button-arrow">→</span>
            `;
        }
    }
}

/* =========================================================
   LOCAL PLAN PERSISTENCE
========================================================= */

function readJsonStorage(key, fallback = []) {
    try {
        const parsed = JSON.parse(localStorage.getItem(key));
        return parsed ?? fallback;
    } catch {
        return fallback;
    }
}

function writeJsonStorage(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

function saveGeneratedPlan(result) {
    const plans = readJsonStorage(MOVA_PLANS_KEY, []);
    const results = readJsonStorage(MOVA_PLAN_RESULT_KEY, {});

    const trip = result.trip || {};
    const summary = {
        id: result.plan_id,
        destination: {
            id: result.destination_id,
            name: result.destination_name,
            region: selectedDestination?.region || ""
        },
        destinations: trip.destinations || [{ id: result.destination_id, name: result.destination_name, region: selectedDestination?.region || "" }],
        destinationIds: trip.destination_ids || [result.destination_id],
        mustVisitPlaces: trip.must_visit_places || [],
        origin: trip.origin || "",
        originLatitude: trip.origin_latitude ?? null,
        originLongitude: trip.origin_longitude ?? null,
        invitedPeople: trip.invited_people || [],
        confirmed: false,
        startDate: trip.start_date,
        endDate: trip.end_date,
        travellers: trip.travellers,
        tripType: trip.trip_type,
        budget: trip.budget,
        foodBudgetPerPersonPerDay: trip.food_budget_per_person_per_day,
        fuelType: trip.vehicle_fuel_type,
        mileageKmpl: trip.vehicle_mileage_kmpl,
        fuelPriceInrPerLitre: trip.fuel_price_inr_per_litre,
        interests: trip.interests || [],
        dislikes: trip.dislikes || [],
        preferred_travel_methods: trip.preferred_travel_methods || [],
        avoid_travel_methods: trip.avoid_travel_methods || [],
        createdAt: new Date().toISOString(),
        generated: true,
        feasible: result.feasible,
        developmentOnly: Boolean(result.data_quality?.development_only),
        objectiveScore: result.objective_score
    };

    const existingIndex = plans.findIndex(plan => plan.id === summary.id);
    if (existingIndex >= 0) plans[existingIndex] = summary;
    else plans.push(summary);

    results[result.plan_id] = result;

    writeJsonStorage(MOVA_PLANS_KEY, plans);
    writeJsonStorage(MOVA_PLAN_RESULT_KEY, results);
}

/* =========================================================
   MY PLANS DASHBOARD
========================================================= */

function loadSavedPlans() {
    const plansList = document.getElementById("plans-list");
    if (!plansList) return;

    const emptyPlans = document.getElementById("empty-plans");
    const plansCount = document.getElementById("plans-count");
    const savedPlans = readJsonStorage(MOVA_PLANS_KEY, []);

    if (!savedPlans.length) {
        plansList.innerHTML = "";
        if (emptyPlans) emptyPlans.style.display = "flex";
        if (plansCount) plansCount.textContent = "0 TRIPS";
        return;
    }

    if (emptyPlans) emptyPlans.style.display = "none";

    if (plansCount) {
        plansCount.textContent =
            `${savedPlans.length} ${savedPlans.length === 1 ? "TRIP" : "TRIPS"}`;
    }

    const focusId = new URLSearchParams(window.location.search).get("plan");

    plansList.innerHTML = savedPlans
        .slice()
        .reverse()
        .map(plan => createPlanCard(plan, plan.id === focusId))
        .join("");
}

/* =========================================================
   PLAN CARD
========================================================= */

function createPlanCard(plan, open = false) {
    const result = readJsonStorage(MOVA_PLAN_RESULT_KEY, {})[plan.id];
    const destination = plan.destination?.name || result?.destination_name || "Unknown destination";
    const region = plan.destination?.region || "";
    const interests = plan.interests?.length
        ? plan.interests.slice(0, 3).map(item => `<span>${escapeHtml(item)}</span>`).join("")
        : `<span>NO INTERESTS SELECTED</span>`;

    const status = result
        ? (result.feasible ? "FEASIBLE" : "NEEDS CHANGES")
        : "SAVED";

    return `
        <article class="plan-card ${open ? "is-open" : ""}" data-plan-id="${escapeHtml(plan.id)}">
            <div class="plan-card-main">
                <div class="plan-card-top">
                    <span class="plan-card-region">${escapeHtml(region)}</span>
                    <span class="plan-card-status ${result?.feasible ? "status-good" : ""}">${status}</span>
                </div>

                <h3>${escapeHtml(destination)}</h3>

                <div class="plan-card-dates">
                    <span>${formatPlanDate(plan.startDate)}</span>
                    <span class="plan-date-arrow">→</span>
                    <span>${formatPlanDate(plan.endDate)}</span>
                </div>
            </div>

            <div class="plan-card-details">
                <div class="plan-detail">
                    <span class="plan-detail-label">TRAVELLERS</span>
                    <strong>${escapeHtml(plan.travellers)}</strong>
                </div>
                <div class="plan-detail">
                    <span class="plan-detail-label">BUDGET</span>
                    <strong>₹${formatNumber(plan.budget)}</strong>
                </div>
                <div class="plan-detail">
                    <span class="plan-detail-label">TYPE</span>
                    <strong>${escapeHtml(plan.tripType || "")}</strong>
                </div>
                <div class="plan-card-interests">${interests}</div>
            </div>

            <div class="plan-card-actions">
                <button type="button" class="plan-action-button" data-action="open" data-plan-id="${escapeHtml(plan.id)}">
                    ${open ? "CLOSE PLAN ↑" : "OPEN PLAN →"}
                </button>
                <button type="button" class="plan-action-button" data-action="reoptimize" data-plan-id="${escapeHtml(plan.id)}">
                    RE-OPTIMIZE ↻
                </button>
                <button type="button" class="plan-action-button" data-action="dashboard" data-plan-id="${escapeHtml(plan.id)}">
                    DASHBOARD ↗
                </button>
                <button type="button" class="plan-action-button" data-action="edit" data-plan-id="${escapeHtml(plan.id)}">
                    EDIT PLAN ✎
                </button>
                <button type="button" class="plan-action-delete" data-action="delete" data-plan-id="${escapeHtml(plan.id)}" aria-label="Delete plan">
                    ×
                </button>
            </div>

            ${result ? renderPlanResult(result, open) : ""}
        </article>
    `;
}

function renderPlanResult(result, open) {
    if (!open) return "";

    const quality = result.data_quality || {};
    const engine = result.engine || {};

    const qualityClass = quality.development_only ? "plan-warning" : "plan-info";

    return `
        <div class="plan-result-panel">
            <div class="plan-result-meta ${qualityClass}">
                <strong>${quality.development_only ? "DEVELOPMENT DATA" : "DATA STATUS"}</strong>
                <span>${escapeHtml((quality.notes || []).join(" ") || "The engine returned provenance information with this plan.")}</span>
            </div>

            ${result.conflicts?.length ? renderConflictBox("CONFLICTS", result.conflicts, "conflict") : ""}
            ${result.warnings?.length ? renderConflictBox("WARNINGS", result.warnings, "warning") : ""}

            <div class="plan-result-grid">
                <div>
                    <span>ENGINE</span>
                    <strong>${escapeHtml(engine.optimizer_method || result.optimizer_method || "MOVA")}</strong>
                </div>
                <div>
                    <span>FEASIBILITY</span>
                    <strong>${result.feasible ? "FEASIBLE" : "REVIEW NEEDED"}</strong>
                </div>
                <div>
                    <span>RECOMMENDATIONS</span>
                    <strong>${result.recommendations?.length || 0}</strong>
                </div>
                <div>
                    <span>CHANGES</span>
                    <strong>${result.changes?.length || 0}</strong>
                </div>
            </div>

            <div class="itinerary-heading">
                <div>
                    <span class="plans-label">GENERATED ITINERARY</span>
                    <h3>YOUR DAYS</h3>
                </div>
                <button type="button" class="plan-small-action" data-action="validate" data-plan-id="${escapeHtml(result.plan_id)}">
                    CHECK PLAN
                </button>
            </div>

            <div class="itinerary-days">
                ${(result.itinerary?.days || []).map(renderDayPlan).join("") ||
                    `<div class="plan-empty-result">The engine returned no scheduled activities for this plan.</div>`}
            </div>

            ${result.recommendations?.length ? `
                <details class="recommendations-details">
                    <summary>RECOMMENDATIONS USED (${result.recommendations.length})</summary>
                    <div class="recommendation-list">
                        ${result.recommendations.slice(0, 12).map(rec => {
                            const scheduled = (result.itinerary?.days || []).some(day =>
                                (day.items || []).some(item => item.place_id === rec.place_id)
                            );
                            return `
                            <div class="recommendation-row">
                                <div class="recommendation-main">
                                    <strong>${escapeHtml(rec.place_id || "PLACE")}</strong>
                                    <small>${escapeHtml((rec.reasons || []).join(" • ") || "Ranked by MOVA.")}</small>
                                </div>
                                <span>${escapeHtml(rec.score)}</span>
                                ${!scheduled ? `
                                    <button type="button" class="plan-small-action recommendation-add"
                                        data-action="add-place"
                                        data-plan-id="${escapeHtml(result.plan_id)}"
                                        data-place-id="${escapeHtml(rec.place_id)}">ADD</button>
                                ` : `<span class="recommendation-scheduled">SCHEDULED</span>`}
                            </div>`;
                        }).join("")}
                    </div>
                </details>
            ` : ""}
        </div>
    `;
}

function renderDayPlan(day) {
    return `
        <section class="itinerary-day">
            <header>
                <div>
                    <span>DAY ${escapeHtml(day.day)}</span>
                    <strong>${formatPlanDate(day.date)}</strong>
                </div>
                <span>${day.total_activity_minutes || 0} MIN ACTIVITY</span>
            </header>

            <div class="itinerary-items">
                ${(day.items || []).map(item => renderItineraryItem(item, day.day)).join("") ||
                    `<div class="plan-empty-result">No itinerary items scheduled.</div>`}
            </div>
        </section>
    `;
}

function renderItineraryItem(item, day) {
    const label =
        item.type === "activity" ? "ACTIVITY" :
        item.type === "meal" ? "MEAL" :
        item.type === "travel" ? "TRAVEL" : "REST";

    const id = item.place_id || item.restaurant_id || item.to_id || item.from_id || "";
    const displayName = item.facts?.place_name || id || "Scheduled item";
    const canRemove = Boolean(item.place_id);

    return `
        <div class="itinerary-item">
            <div class="itinerary-time">
                <strong>${escapeHtml(item.start)}</strong>
                <span>${escapeHtml(item.end)}</span>
            </div>
            <div class="itinerary-item-main">
                <span class="itinerary-type">${label}</span>
                <strong>${escapeHtml(displayName)}</strong>
                ${item.place_id ? `<small class="itinerary-place-id">${escapeHtml(item.place_id)}</small>` : ""}
                ${item.cost_inr != null ? `<small>₹${formatNumber(item.cost_inr)}</small>` : ""}
            </div>
            ${canRemove ? `
                <div class="itinerary-item-actions">
                    <button
                        type="button"
                        class="plan-small-action"
                        data-action="move-place"
                        data-plan-id="${escapeHtml(currentPlanIdFromDom())}"
                        data-place-id="${escapeHtml(item.place_id)}"
                        data-day="${escapeHtml(day)}"
                    >MOVE</button>
                    <button
                        type="button"
                        class="plan-item-remove"
                        data-action="remove-place"
                        data-plan-id="${escapeHtml(currentPlanIdFromDom())}"
                        data-place-id="${escapeHtml(item.place_id)}"
                        data-day="${escapeHtml(day)}"
                    >REMOVE</button>
                </div>
            ` : ""}
        </div>
    `;
}

function currentPlanIdFromDom() {
    const card = document.querySelector(".plan-card.is-open");
    return card?.dataset.planId || "";
}

function renderConflictBox(title, conflicts, className) {
    return `
        <div class="plan-alert ${className}">
            <strong>${escapeHtml(title)}</strong>
            <ul>
                ${conflicts.map(item => `<li>${escapeHtml(item.message || "Review this item.")}</li>`).join("")}
            </ul>
        </div>
    `;
}

/* =========================================================
   PLAN ACTIONS
========================================================= */

function setupPlanActions() {
    const plansList = document.getElementById("plans-list");
    if (!plansList) return;

    plansList.addEventListener("click", async event => {
        const button = event.target.closest("[data-action]");
        if (!button) return;

        const action = button.dataset.action;
        const planId = button.dataset.planId;

        if (action === "delete") {
            deletePlan(planId);
            return;
        }

        if (action === "open") {
            togglePlanOpen(planId);
            return;
        }

        if (action === "reoptimize") {
            await reoptimizePlan(planId);
            return;
        }

        if (action === "dashboard") {
            window.location.href = `plan-dashboard.html?plan=${encodeURIComponent(planId)}`;
            return;
        }

        if (action === "edit") {
            window.location.href = `edit-plan.html?plan=${encodeURIComponent(planId)}`;
            return;
        }

        if (action === "remove-place") {
            await removePlaceFromPlan(planId, button.dataset.placeId);
            return;
        }

        if (action === "add-place") {
            await addPlaceToPlan(planId, button.dataset.placeId);
            return;
        }

        if (action === "move-place") {
            await movePlaceInPlan(planId, button.dataset.placeId);
            return;
        }

        if (action === "validate") {
            await validatePlan(planId);
        }
    });
}

function togglePlanOpen(planId) {
    const plans = readJsonStorage(MOVA_PLANS_KEY, []);
    const plan = plans.find(item => item.id === planId);
    if (!plan) return;

    const results = readJsonStorage(MOVA_PLAN_RESULT_KEY, {});
    const result = results[planId];

    const card = document.querySelector(`.plan-card[data-plan-id="${CSS.escape(planId)}"]`);
    if (!card) return;

    const wasOpen = card.classList.contains("is-open");

    document.querySelectorAll(".plan-card").forEach(other => {
        other.classList.remove("is-open");
    });

    const open = !wasOpen;

    card.outerHTML = createPlanCard(plan, open && Boolean(result));
}

async function reoptimizePlan(planId) {
    const result = readJsonStorage(MOVA_PLAN_RESULT_KEY, {})[planId];
    if (!result) {
        showPlanToast("This plan does not contain an engine result yet.");
        return;
    }

    const button = document.querySelector(
        `.plan-card[data-plan-id="${CSS.escape(planId)}"] [data-action="reoptimize"]`
    );
    setPlanButtonBusy(button, "RE-OPTIMIZING...");

    try {
        const updated = await optimizeMovaPlan({
            trip: result.trip,
            base_itinerary: cleanItineraryForRequest(result.itinerary)
        });

        replaceStoredResult(updated);
        renderPlansKeepingFocus(updated.plan_id, true);
        showPlanToast("MOVA re-optimized the itinerary.");
    } catch (error) {
        showPlanToast(friendlyApiError(error));
        setPlanButtonBusy(button, "RE-OPTIMIZE ↻", false);
    }
}

async function removePlaceFromPlan(planId, placeId) {
    const result = readJsonStorage(MOVA_PLAN_RESULT_KEY, {})[planId];
    if (!result || !placeId) return;

    const button = document.querySelector(
        `.plan-card[data-plan-id="${CSS.escape(planId)}"] [data-place-id="${CSS.escape(placeId)}"]`
    );
    setPlanButtonBusy(button, "REMOVING...");

    try {
        const response = await modifyMovaPlan({
            trip: result.trip,
            itinerary: cleanItineraryForRequest(result.itinerary),
            modifications: [{
                action: "remove_place",
                place_id: placeId,
                reason: "Traveller removed the place from the itinerary."
            }]
        });

        if (response?.plan) {
            replaceStoredResult(response.plan);
            renderPlansKeepingFocus(response.plan.plan_id, true);
            const rejected = response.rejected?.length;
            showPlanToast(rejected ? (response.messages?.[0] || "The place could not be removed from the current plan.") : "Place removed and the itinerary was re-checked.");
        }
    } catch (error) {
        showPlanToast(friendlyApiError(error));
        setPlanButtonBusy(button, "REMOVE", false);
    }
}

async function addPlaceToPlan(planId, placeId) {
    const result = readJsonStorage(MOVA_PLAN_RESULT_KEY, {})[planId];
    if (!result || !placeId) return;

    const button = document.querySelector(
        `.plan-card[data-plan-id="${CSS.escape(planId)}"] [data-place-id="${CSS.escape(placeId)}"][data-action="add-place"]`
    );
    setPlanButtonBusy(button, "ADDING...");

    try {
        const response = await modifyMovaPlan({
            trip: result.trip,
            itinerary: cleanItineraryForRequest(result.itinerary),
            modifications: [{
                action: "add_place",
                place_id: placeId,
                reason: "Traveller added a recommended place to the itinerary."
            }]
        });

        if (response?.plan) {
            replaceStoredResult(response.plan);
            renderPlansKeepingFocus(response.plan.plan_id, true);
            showPlanToast("Place added and the itinerary was re-optimized.");
        }
    } catch (error) {
        showPlanToast(friendlyApiError(error));
        setPlanButtonBusy(button, "ADD", false);
    }
}

async function movePlaceInPlan(planId, placeId) {
    const result = readJsonStorage(MOVA_PLAN_RESULT_KEY, {})[planId];
    if (!result || !placeId) return;

    const requestedDay = Number(window.prompt("Move this place to which day?"));
    if (!Number.isInteger(requestedDay) || requestedDay < 1 || requestedDay > (result.itinerary?.days?.length || 0)) {
        showPlanToast("Move cancelled: enter a valid trip day.");
        return;
    }

    const requestedStart = window.prompt("Start time (HH:MM)", "10:00");
    if (!requestedStart || !/^([01]\d|2[0-3]):[0-5]\d$/.test(requestedStart)) {
        showPlanToast("Move cancelled: use a valid 24-hour time such as 10:00.");
        return;
    }

    try {
        const response = await modifyMovaPlan({
            trip: result.trip,
            itinerary: cleanItineraryForRequest(result.itinerary),
            modifications: [{
                action: "move_place",
                place_id: placeId,
                day: requestedDay,
                start: requestedStart,
                reason: "Traveller moved the place to a different day/time."
            }]
        });

        if (response?.plan) {
            replaceStoredResult(response.plan);
            renderPlansKeepingFocus(response.plan.plan_id, true);
            showPlanToast("Place moved and the itinerary was re-optimized.");
        }
    } catch (error) {
        showPlanToast(friendlyApiError(error));
    }
}

async function validatePlan(planId) {
    const result = readJsonStorage(MOVA_PLAN_RESULT_KEY, {})[planId];
    if (!result) return;

    try {
        const response = await validateMovaPlan({
            trip: result.trip,
            itinerary: cleanItineraryForRequest(result.itinerary),
            modifications: [{
                action: "reoptimize"
            }]
        });

        const messages = [
            ...(response?.conflicts || []).map(item => item.message),
            ...(response?.warnings || []).map(item => item.message)
        ];

        showPlanToast(
            response?.feasible
                ? "Plan checked: no hard conflicts were returned."
                : messages[0] || "Plan needs changes before it is fully feasible."
        );
    } catch (error) {
        showPlanToast(friendlyApiError(error));
    }
}

function replaceStoredResult(result) {
    const results = readJsonStorage(MOVA_PLAN_RESULT_KEY, {});
    results[result.plan_id] = result;
    writeJsonStorage(MOVA_PLAN_RESULT_KEY, results);

    const plans = readJsonStorage(MOVA_PLANS_KEY, []);
    const index = plans.findIndex(item => item.id === result.plan_id);

    if (index >= 0) {
        plans[index].feasible = result.feasible;
        plans[index].developmentOnly = Boolean(result.data_quality?.development_only);
    }

    writeJsonStorage(MOVA_PLANS_KEY, plans);
}

function renderPlansKeepingFocus(planId, open = false) {
    const list = document.getElementById("plans-list");
    if (!list) return;

    const plans = readJsonStorage(MOVA_PLANS_KEY, []);
    list.innerHTML = plans.slice().reverse().map(plan =>
        createPlanCard(plan, open && plan.id === planId)
    ).join("");

    const card = document.querySelector(`.plan-card[data-plan-id="${CSS.escape(planId)}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "center" });
}

/* =========================================================
   DELETE / FORMATTERS
========================================================= */

function deletePlan(planId) {
    const plans = readJsonStorage(MOVA_PLANS_KEY, []).filter(plan => plan.id !== planId);
    const results = readJsonStorage(MOVA_PLAN_RESULT_KEY, {});
    delete results[planId];

    writeJsonStorage(MOVA_PLANS_KEY, plans);
    writeJsonStorage(MOVA_PLAN_RESULT_KEY, results);
    loadSavedPlans();
}

function formatPlanDate(dateString) {
    if (!dateString) return "DATE NOT SET";

    const date = new Date(
        String(dateString).includes("T")
            ? dateString
            : `${dateString}T00:00:00`
    );

    if (Number.isNaN(date.getTime())) return String(dateString);

    return date.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric"
    });
}

function formatNumber(number) {
    return Number(number || 0).toLocaleString("en-IN");
}

/* =========================================================
   API REQUEST NORMALIZATION
   Pydantic computed fields are response-only and must not be
   echoed into strict request schemas.
========================================================= */

function cleanItineraryForRequest(itinerary) {
    if (!itinerary) return null;

    return {
        plan_id: itinerary.plan_id,
        days: (itinerary.days || []).map(day => ({
            day: day.day,
            date: day.date,
            items: (day.items || []).map(item => {
                const cleaned = {
                    type: item.type,
                    start: item.start,
                    end: item.end,
                    duration_minutes: item.duration_minutes,
                    place_id: item.place_id ?? null,
                    restaurant_id: item.restaurant_id ?? null,
                    meal_type: item.meal_type ?? null,
                    from_id: item.from_id ?? null,
                    to_id: item.to_id ?? null,
                    transport_mode: item.transport_mode ?? null,
                    cost_inr: item.cost_inr ?? null,
                    facts: item.facts || {}
                };
                return cleaned;
            })
        }))
    };
}

/* =========================================================
   FEEDBACK
========================================================= */

function setPlanButtonBusy(button, label, reset = true) {
    if (!button) return;

    if (!button.dataset.originalLabel) {
        button.dataset.originalLabel = button.innerHTML;
    }

    button.disabled = reset;
    button.innerHTML = label;
}

function showPlanToast(message) {
    let toast = document.getElementById("mova-plan-toast");

    if (!toast) {
        toast = document.createElement("div");
        toast.id = "mova-plan-toast";
        toast.className = "mova-plan-toast";
        document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.classList.add("visible");

    clearTimeout(window.__movaToastTimer);
    window.__movaToastTimer = setTimeout(() => {
        toast.classList.remove("visible");
    }, 4500);
}

function friendlyApiError(error) {
    if (!error) return "Something went wrong while contacting the planning engine.";

    if (error.code === "network_error") {
        return "The MOVA planning engine is offline. Run the FastAPI server on port 8000 and try again.";
    }

    if (error.code === "timeout") {
        return "The planning engine did not respond in time. Check the backend terminal and try again.";
    }

    if (error.code === "data_unavailable") {
        const providerDetails = error.details?.provider_details || {};
        const overpassAttempts = providerDetails.overpass?.attempts || providerDetails.attempts || [];
        const overpassStatuses = [...new Set(overpassAttempts.map(item => item.status).filter(Boolean))];
        const wikiStatus = providerDetails.wikipedia?.status;
        const diagnostics = [];
        if (overpassStatuses.length) diagnostics.push(`Overpass HTTP ${overpassStatuses.join("/")}`);
        if (wikiStatus) diagnostics.push(`Wikipedia HTTP ${wikiStatus}`);
        const statusText = diagnostics.length ? ` (${diagnostics.join("; ")})` : "";
        return `${error.message || "Live destination places are temporarily unavailable."}${statusText} Check the backend terminal for the full provider error, then retry.`;
    }

    return error.message || "The planning engine rejected this request.";
}

/* =========================================================
   SAFETY / DISPLAY HELPERS
========================================================= */

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}
