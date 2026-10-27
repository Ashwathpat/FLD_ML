/**
 * FLD-Screen — AI Diagnostic Platform
 * Multi-Cloud DR Controller with Delete & Clear All
 */

// ── Cloud Endpoints ─────────────────────────────────────────────────────────
const AWS_ENDPOINT = "http://54.66.222.189";
const AZURE_ENDPOINT = "http://20.187.68.47:8000";

let activeBaseUrl = window.location.origin;
if (activeBaseUrl.includes("localhost") || activeBaseUrl.includes("127.0.0.1")) {
    activeBaseUrl = "";
} else if (window.location.hostname === "54.66.222.189") {
    activeBaseUrl = AWS_ENDPOINT;
} else if (window.location.hostname === "20.187.68.47") {
    activeBaseUrl = AZURE_ENDPOINT;
}

// ── Global DR State ─────────────────────────────────────────────────────────
let awsAlive = true;
let azureAlive = true;
let currentServingCloud = "aws";

// ── DOM Cache ───────────────────────────────────────────────────────────────
const awsBadge = document.getElementById("aws-status-badge");
const awsDot = document.getElementById("aws-dot");
const awsState = document.getElementById("aws-state");
const azureBadge = document.getElementById("azure-status-badge");
const azureDot = document.getElementById("azure-dot");
const azureState = document.getElementById("azure-state");
const currentServingLabel = document.getElementById("current-serving-cloud");
const activeRoutePill = document.getElementById("active-route-pill");
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("image-upload");
const fileNameDisplay = document.getElementById("file-name");
const predictForm = document.getElementById("predict-form");
const submitBtn = document.getElementById("submit-btn");
const loadingSpinner = document.getElementById("loading-spinner");
const resultsPlaceholder = document.querySelector(".results-placeholder");
const resultsContent = document.getElementById("results-content");
const resultLabel = document.getElementById("result-label");
const disclaimerText = document.getElementById("disclaimer-text");
const servedByText = document.getElementById("served-by-text");
const historyGrid = document.getElementById("history-grid");
const refreshHistoryBtn = document.getElementById("refresh-history-btn");
const clearAllBtn = document.getElementById("clear-all-btn");
const toastContainer = document.getElementById("toast-container");

let selectedFile = null;
let donutChart = null;
let barChart = null;

// ═══════════════════════════════════════════════════════════════════════════
//  TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════════════════
function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${type === "success" ? "✓" : "✕"}</span> ${message}`;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// ═══════════════════════════════════════════════════════════════════════════
//  CONFIRM MODAL
// ═══════════════════════════════════════════════════════════════════════════
function showConfirm(title, message) {
    return new Promise((resolve) => {
        const overlay = document.createElement("div");
        overlay.className = "modal-overlay";
        overlay.innerHTML = `
            <div class="modal-box">
                <h3>${title}</h3>
                <p>${message}</p>
                <div class="modal-actions">
                    <button class="modal-btn cancel-btn">Cancel</button>
                    <button class="modal-btn danger confirm-btn">Delete</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        overlay.querySelector(".cancel-btn").addEventListener("click", () => {
            overlay.remove();
            resolve(false);
        });
        overlay.querySelector(".confirm-btn").addEventListener("click", () => {
            overlay.remove();
            resolve(true);
        });
        overlay.addEventListener("click", (e) => {
            if (e.target === overlay) { overlay.remove(); resolve(false); }
        });
    });
}

// ═══════════════════════════════════════════════════════════════════════════
//  MULTI-CLOUD HEALTH MONITOR & AUTO-FAILOVER
// ═══════════════════════════════════════════════════════════════════════════
async function probeCloudHealth() {
    try {
        const res = await fetch("/api/dr-status");
        if (res.ok) {
            const data = await res.json();
            awsAlive = Boolean(data.aws_alive);
            azureAlive = Boolean(data.azure_alive);
            updateDRDisplay();
            if (data.active_region) currentServingLabel.innerText = data.active_region;
            return;
        }
    } catch (e) { /* fallback below */ }

    // Direct probe fallback
    try {
        const c = new AbortController();
        const t = setTimeout(() => c.abort(), 2000);
        const r = await fetch(`${AWS_ENDPOINT}/healthz`, { signal: c.signal, mode: "cors" });
        clearTimeout(t);
        awsAlive = r.ok;
    } catch (e) { awsAlive = false; }

    try {
        const c = new AbortController();
        const t = setTimeout(() => c.abort(), 2000);
        const r = await fetch(`${AZURE_ENDPOINT}/healthz`, { signal: c.signal, mode: "cors" });
        clearTimeout(t);
        azureAlive = r.ok;
    } catch (e) { azureAlive = false; }

    updateDRDisplay();
}

function updateDRDisplay() {
    if (awsAlive) {
        awsDot.className = "status-indicator live";
        awsState.innerText = "ONLINE";
        awsBadge.className = "cloud-badge active-cloud";

        if (azureAlive) {
            azureDot.className = "status-indicator standby";
            azureState.innerText = "HOT STANDBY";
            azureBadge.className = "cloud-badge";
        } else {
            azureDot.className = "status-indicator offline";
            azureState.innerText = "OFFLINE";
            azureBadge.className = "cloud-badge offline-cloud";
        }

        currentServingCloud = "aws";
        currentServingLabel.innerText = "AWS Sydney (Primary)";
        activeRoutePill.className = "active-route-pill";

        if (window.location.hostname !== "20.187.68.47" && !window.location.origin.includes("localhost:8080")) {
            activeBaseUrl = AWS_ENDPOINT;
        }
    } else {
        awsDot.className = "status-indicator offline";
        awsState.innerText = "OFFLINE";
        awsBadge.className = "cloud-badge offline-cloud";

        if (azureAlive) {
            azureDot.className = "status-indicator failover";
            azureState.innerText = "ACTIVE (FAILOVER)";
            azureBadge.className = "cloud-badge active-cloud";
            currentServingCloud = "azure";
            currentServingLabel.innerText = "Azure Hong Kong (Failover)";
            activeRoutePill.className = "active-route-pill failover-mode";

            if (!window.location.origin.includes("localhost:8080")) {
                activeBaseUrl = AZURE_ENDPOINT;
            }
        } else {
            azureDot.className = "status-indicator offline";
            azureState.innerText = "OFFLINE";
            currentServingLabel.innerText = "ALL CLOUDS UNREACHABLE";
        }
    }
}

setInterval(probeCloudHealth, 3000);
probeCloudHealth();

// ═══════════════════════════════════════════════════════════════════════════
//  FILE UPLOAD
// ═══════════════════════════════════════════════════════════════════════════
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) handleFileSelection(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) handleFileSelection(e.target.files[0]);
});

function handleFileSelection(file) {
    if (!file.type.startsWith("image/")) { showToast("Please upload a valid image (JPG/PNG).", "error"); return; }
    selectedFile = file;
    fileNameDisplay.innerHTML = `<span style="color: var(--green); font-weight: 600;">✓ ${file.name}</span>`;
}

// ═══════════════════════════════════════════════════════════════════════════
//  INFERENCE SUBMISSION
// ═══════════════════════════════════════════════════════════════════════════
predictForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) { showToast("Select a tongue image first.", "error"); return; }

    submitBtn.classList.add("hidden");
    loadingSpinner.classList.remove("hidden");

    const formData = new FormData(predictForm);
    formData.set("file", selectedFile);

    let targetUrl = activeBaseUrl ? `${activeBaseUrl}/predict` : "/predict";

    try {
        let response;
        try {
            response = await fetch(targetUrl, { method: "POST", body: formData });
        } catch (fetchErr) {
            targetUrl = `${AZURE_ENDPOINT}/predict`;
            response = await fetch(targetUrl, { method: "POST", body: formData });
            probeCloudHealth();
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const servedBy = response.headers.get("X-Served-By") || currentServingCloud;
        displayResults(data, servedBy);
        loadHistoryArchive();
        showToast("Diagnostic complete.");
    } catch (error) {
        showToast("Inference failed: " + error.message, "error");
    } finally {
        submitBtn.classList.remove("hidden");
        loadingSpinner.classList.add("hidden");
    }
});

function displayResults(data, servedBy) {
    resultsPlaceholder.classList.add("hidden");
    resultsContent.classList.remove("hidden");

    const isFLD = data.label === "FLD";
    resultLabel.innerText = isFLD ? "Fatty Liver Detected" : "Healthy — No FLD";
    resultLabel.className = `result-badge ${isFLD ? "fld" : "healthy"}`;

    disclaimerText.innerText = data.disclaimer || "Screening-support tool, not a medical diagnosis.";
    servedByText.innerText = `Processed by ${servedBy.toUpperCase()} Cloud`;

    renderDonutChart(data.probabilities);
    renderBarChart(data.top_features);
}

function renderDonutChart(probs) {
    const ctx = document.getElementById("donut-chart").getContext("2d");
    if (donutChart) donutChart.destroy();
    donutChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: Object.keys(probs),
            datasets: [{
                data: Object.values(probs),
                backgroundColor: ["#ff453a", "#30d158"],
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "70%",
            plugins: { legend: { position: "bottom", labels: { color: "#86868b", font: { size: 11 } } } }
        }
    });
}

function renderBarChart(features) {
    const ctx = document.getElementById("bar-chart").getContext("2d");
    if (!features || !features.length) return;
    if (barChart) barChart.destroy();
    barChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: features.map(f => f.feature),
            datasets: [{
                label: "SHAP Impact",
                data: features.map(f => f.importance_score),
                backgroundColor: "rgba(10, 132, 255, 0.6)",
                borderRadius: 3,
                borderSkipped: false,
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { ticks: { color: "#86868b", font: { size: 10 } }, grid: { color: "rgba(255,255,255,0.03)" } },
                y: { ticks: { color: "#86868b", font: { size: 10 } }, grid: { display: false } }
            },
            plugins: { legend: { display: false } }
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════
//  HISTORY ARCHIVE — LOAD, DELETE, CLEAR ALL
// ═══════════════════════════════════════════════════════════════════════════
refreshHistoryBtn.addEventListener("click", loadHistoryArchive);

async function loadHistoryArchive() {
    const historyUrl = activeBaseUrl ? `${activeBaseUrl}/api/history` : "/api/history";
    try {
        let res;
        try { res = await fetch(historyUrl); }
        catch (e) { res = await fetch(`${AZURE_ENDPOINT}/api/history`); }
        if (!res.ok) throw new Error("Fetch failed");
        const data = await res.json();
        renderHistoryCards(data.records || []);
    } catch (err) {
        historyGrid.innerHTML = `<div class="history-loading">Unable to fetch archive — ${err.message}</div>`;
    }
}

function renderHistoryCards(records) {
    if (!records || records.length === 0) {
        historyGrid.innerHTML = `<div class="history-loading">No diagnostic records found.</div>`;
        return;
    }

    historyGrid.innerHTML = records.map(r => {
        const isFLD = r.label === "FLD";
        const badgeClass = isFLD ? "fld" : "no_fld";
        const fldProb = (r.probs && r.probs.FLD !== undefined) ? (r.probs.FLD * 100).toFixed(1) : "N/A";
        const imgUrl = activeBaseUrl ? `${activeBaseUrl}/api/image/${r.image_key}` : `/api/image/${r.image_key}`;

        let dateStr = "Recent";
        if (r.created_at) {
            try {
                const d = new Date(r.created_at);
                dateStr = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) + " · " + d.toLocaleDateString();
            } catch (e) {}
        }

        return `
            <div class="history-card" data-id="${r.id}">
                <button class="delete-card-btn" onclick="deleteSingleRecord('${r.id}')" title="Delete record">✕</button>
                <div class="history-thumb-wrap">
                    <img src="${imgUrl}" alt="Tongue" class="history-thumb" onerror="this.style.display='none'">
                </div>
                <div class="history-card-body">
                    <div class="history-meta-row">
                        <span class="history-id">${r.id.substring(0, 8)}</span>
                        <span>${dateStr}</span>
                    </div>
                    <div class="history-result-row">
                        <span class="history-badge ${badgeClass}">${isFLD ? "FLD Detected" : "Healthy"}</span>
                        <small style="color: var(--text-tertiary); font-weight: 600; font-size: 0.68rem;">${fldProb}%</small>
                    </div>
                    <div class="history-prob-bar">
                        <div class="history-prob-fill" style="width: ${fldProb === "N/A" ? 50 : fldProb}%"></div>
                    </div>
                </div>
            </div>`;
    }).join("");
}

// ── Delete Single Record ────────────────────────────────────────────────
async function deleteSingleRecord(predId) {
    const confirmed = await showConfirm(
        "Delete Record",
        "This will permanently remove this diagnostic from both AWS and Azure databases."
    );
    if (!confirmed) return;

    const url = activeBaseUrl ? `${activeBaseUrl}/api/history/${predId}` : `/api/history/${predId}`;
    try {
        let res;
        try { res = await fetch(url, { method: "DELETE" }); }
        catch (e) { res = await fetch(`${AZURE_ENDPOINT}/api/history/${predId}`, { method: "DELETE" }); }

        if (!res.ok) throw new Error("Delete failed");

        // Animate card removal
        const card = document.querySelector(`.history-card[data-id="${predId}"]`);
        if (card) {
            card.style.transition = "all 0.3s ease";
            card.style.opacity = "0";
            card.style.transform = "scale(0.95)";
            setTimeout(() => {
                card.remove();
                if (!historyGrid.querySelector(".history-card")) {
                    historyGrid.innerHTML = `<div class="history-loading">No diagnostic records found.</div>`;
                }
            }, 300);
        }
        showToast("Record deleted from both databases.");
    } catch (err) {
        showToast("Delete failed: " + err.message, "error");
    }
}

// ── Clear All Records ───────────────────────────────────────────────────
clearAllBtn.addEventListener("click", async () => {
    const confirmed = await showConfirm(
        "Clear All Records",
        "This will permanently delete ALL diagnostic records from both AWS RDS and Azure PostgreSQL. This action cannot be undone."
    );
    if (!confirmed) return;

    const url = activeBaseUrl ? `${activeBaseUrl}/api/history` : "/api/history";
    try {
        let res;
        try { res = await fetch(url, { method: "DELETE" }); }
        catch (e) { res = await fetch(`${AZURE_ENDPOINT}/api/history`, { method: "DELETE" }); }

        if (!res.ok) throw new Error("Clear all failed");

        // Animate all cards out
        const cards = historyGrid.querySelectorAll(".history-card");
        cards.forEach((card, i) => {
            card.style.transition = `all 0.3s ease ${i * 0.05}s`;
            card.style.opacity = "0";
            card.style.transform = "scale(0.95)";
        });
        setTimeout(() => {
            historyGrid.innerHTML = `<div class="history-loading">No diagnostic records found.</div>`;
        }, cards.length * 50 + 350);

        showToast("All records cleared from both databases.");
    } catch (err) {
        showToast("Clear all failed: " + err.message, "error");
    }
});

// ── Initial load ────────────────────────────────────────────────────────
loadHistoryArchive();
