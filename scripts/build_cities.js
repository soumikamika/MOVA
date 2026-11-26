/*
 * Build a city discovery seed from a structured external source.
 *
 * This script intentionally does NOT generate descriptions, ratings, prices,
 * images or travel advice. It only stores facts returned by the provider and
 * provenance so Discover can use cities as search seeds without pretending
 * MOVA has verified them.
 *
 * Usage: node scripts/build_cities.js
 * Requires Node 18+ (global fetch).
 */

const fs = require("fs");
const path = require("path");

const ENDPOINT = "https://countriesnow.space/api/v0.1/countries/cities";
const OUTPUT = path.join(__dirname, "..", "data", "cities.json");

async function build() {
    console.log("Fetching India city names from CountriesNow...");

    const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ country: "India" })
    });

    if (!response.ok) throw new Error(`Provider returned HTTP ${response.status}`);

    const payload = await response.json();
    const cities = Array.isArray(payload.data) ? payload.data : [];

    const records = cities
        .filter(city => typeof city === "string" && city.trim())
        .map(city => ({
            id: `city-${city.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`,
            name: city.trim(),
            country: "India",
            source: "external_api",
            source_provider: "countriesnow",
            source_url: "https://countriesnow.space/",
            last_updated: new Date().toISOString(),
            description: null,
            image: null
        }));

    const deduped = [...new Map(records.map(record => [record.name.toLowerCase(), record])).values()]
        .sort((a, b) => a.name.localeCompare(b.name));

    fs.writeFileSync(OUTPUT, JSON.stringify(deduped, null, 2), "utf8");
    console.log(`Wrote ${deduped.length} city discovery records to ${OUTPUT}`);
}

build().catch(error => {
    console.error("City discovery build failed:", error.message);
    process.exitCode = 1;
});
