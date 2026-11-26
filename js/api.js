/* =========================================================
   MOVA API ADAPTER
   Single frontend gateway for the Travel Intelligence Engine.
========================================================= */

const MOVA_API_BASE = (() => {
    const queryApi =
        new URLSearchParams(window.location.search).get("api");

    const configured =
        queryApi ||
        window.MOVA_CONFIG?.apiBaseUrl ||
        document.querySelector('meta[name="mova-api-base"]')?.content ||
        localStorage.getItem("movaApiBaseUrl");

    // Local development default. Production hosting can override this
    // through window.MOVA_CONFIG, a meta tag, or localStorage.
    return String(configured || "http://127.0.0.1:8000").replace(/\/$/, "");
})();

async function movaApi(path, options = {}) {
    const controller = new AbortController();
    const timeoutMs = options.timeoutMs || 45000;
    let timedOut = false;
    const externalSignal = options.signal || null;
    const onExternalAbort = () => controller.abort();

    if (externalSignal) {
        if (externalSignal.aborted) {
            const abortError = new Error("Request cancelled.");
            abortError.name = "AbortError";
            abortError.code = "aborted";
            throw abortError;
        }
        externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }

    const timer = setTimeout(() => {
        timedOut = true;
        controller.abort();
    }, timeoutMs);

    try {
        const method = options.method || "GET";
        const headers = { ...(options.headers || {}) };
        if (typeof window.movaGetIdToken === "function") {
            const idToken = await window.movaGetIdToken();
            if (idToken) headers.Authorization = `Bearer ${idToken}`;
        }
        if (options.body !== undefined) headers["Content-Type"] = "application/json";

        const response = await fetch(`${MOVA_API_BASE}${path}`, {
            method,
            headers,
            body: options.body === undefined
                ? undefined
                : JSON.stringify(options.body),
            signal: controller.signal
        });

        const text = await response.text();
        let payload = null;

        try {
            payload = text ? JSON.parse(text) : null;
        } catch {
            payload = { message: text || "The server returned an invalid response." };
        }

        if (!response.ok) {
            const detail = payload?.detail;
            const message =
                typeof detail === "string"
                    ? detail
                    : detail?.message ||
                      payload?.message ||
                      `MOVA API request failed (${response.status}).`;

            const error = new Error(message);
            error.status = response.status;
            error.code = detail?.code || payload?.code || "api_error";
            error.details = detail?.details || payload?.details || null;
            throw error;
        }

        return payload;
    } catch (error) {
        if (error.name === "AbortError") {
            if (!timedOut) {
                const abortError = new Error("Request cancelled.");
                abortError.name = "AbortError";
                abortError.code = "aborted";
                throw abortError;
            }
            const timeoutError = new Error(
                "The planning engine took too long to respond. Check that the backend is running and try again."
            );
            timeoutError.code = "timeout";
            throw timeoutError;
        }

        if (error instanceof TypeError && /fetch/i.test(error.message)) {
            const networkError = new Error(
                `MOVA planning engine is not reachable at ${MOVA_API_BASE}. Start the FastAPI server and try again.`
            );
            networkError.code = "network_error";
            throw networkError;
        }

        throw error;
    } finally {
        clearTimeout(timer);
        if (externalSignal) {
            externalSignal.removeEventListener("abort", onExternalAbort);
        }
    }
}

async function movaHealthCheck() {
    return movaApi("/api/health", { timeoutMs: 7000 });
}

function getMovaApiBase() {
    return MOVA_API_BASE;
}

async function generateMovaPlan(request) {
    return movaApi("/api/plans/generate", {
        method: "POST",
        body: request,
        timeoutMs: 60000
    });
}

async function optimizeMovaPlan(request) {
    return movaApi("/api/plans/optimize", {
        method: "POST",
        body: request,
        timeoutMs: 60000
    });
}

async function modifyMovaPlan(request) {
    return movaApi("/api/plans/modify", {
        method: "POST",
        body: request,
        timeoutMs: 60000
    });
}

async function validateMovaPlan(request) {
    return movaApi("/api/plans/validate", {
        method: "POST",
        body: request,
        timeoutMs: 30000
    });
}

async function movaCapabilities() {
    return movaApi("/api/capabilities", { timeoutMs: 10000 });
}

async function discoverMovaRegion(params, options = {}) {
    const query = new URLSearchParams({
        name: params.name,
        scope: params.scope || "region",
    });
    if (Number.isFinite(params.lat) && Number.isFinite(params.lon)) {
        query.set("lat", String(params.lat));
        query.set("lon", String(params.lon));
    }
    if (params.refresh) {
        query.set("refresh", "true");
    }
    return movaApi(`/api/regions/discover?${query.toString()}`, {
        timeoutMs: options.timeoutMs || 60000,
        signal: options.signal,
    });
}
