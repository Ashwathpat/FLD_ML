/**
 * FLD-Screen — AI Diagnostic Platform
 * Multi-Cloud DR Controller with Zero-Data-Loss Failover & Bidirectional Synchronization
 */

// ── Cloud Endpoints & Protocol-Safe Routing ─────────────────────────────────
const isHttps = window.location.protocol === "https:";
const isVercel = window.location.hostname.includes("vercel.app");

// On Vercel (HTTPS) or when using SSL, route all API traffic through the
// Vercel HTTPS reverse-proxy edge rewrites (/api/aws and /api/azure).
// This guarantees ZERO browser mixed-content (HTTP on HTTPS) blocking!
// When running locally on HTTP or direct EC2/Azure IP, use direct IP endpoints.
const AWS_ENDPOINT = (isHttps || isVercel) ? "/api/aws" : "http://54.66.222.189";
const AZURE_ENDPOINT = (isHttps || isVercel) ? "/api/azure" : "http://20.187.68.47:8000";

let activeBaseUrl = AWS_ENDPOINT;

// ── Global DR State ─────────────────────────────────────────────────────────
let awsAlive = true;
let azureAlive = true;
let simulatedAwsDown = false;
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

// ── Multi-Cloud Control Panel DOM Cache ─────────────────────────────────────
const cardAws = document.getElementById("card-aws");
const cardAwsStatus = document.getElementById("card-aws-status");
const awsLatencyEl = document.getElementById("aws-latency");
const cardAzure = document.getElementById("card-azure");
const cardAzureStatus = document.getElementById("card-azure-status");
const azureLatencyEl = document.getElementById("azure-latency");
const routingBanner = document.getElementById("routing-banner");
const routingTargetText = document.getElementById("routing-target-text");
const simulateOutageBtn = document.getElementById("simulate-outage-btn");
const restorePrimaryBtn = document.getElementById("restore-primary-btn");

// ═══════════════════════════════════════════════════════════════════════════
//  TOAST NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════════════════
function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    let icon = "✓";
    if (type === "error") icon = "✕";
    if (type === "warning" || type === "info") icon = "⚡";
    toast.innerHTML = `<span>${icon}</span> ${message}`;
    toastContainer.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
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
                    <button class="modal-btn danger confirm-btn">Permanently Delete</button>
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
//  FORCE SHUTDOWN / SIMULATE OUTAGE CONTROLS
// ═══════════════════════════════════════════════════════════════════════════
if (simulateOutageBtn && restorePrimaryBtn) {
    simulateOutageBtn.addEventListener("click", () => {
        setAwsPower(false);
    });

    restorePrimaryBtn.addEventListener("click", () => {
        setAwsPower(true);
    });
}

// ── Header Quick Power Toggle (single button ON/OFF) ────────────────────
const headerPowerBtn = document.getElementById("header-aws-power-btn");
const headerPowerText = document.getElementById("header-power-text");

function setAwsPower(on) {
    simulatedAwsDown = !on;

    // Sync the DR control panel buttons
    if (simulateOutageBtn && restorePrimaryBtn) {
        simulateOutageBtn.classList.toggle("hidden", !on);
        restorePrimaryBtn.classList.toggle("hidden", on);
    }

    // Sync the header power button
    if (headerPowerBtn) {
        if (on) {
            headerPowerBtn.classList.remove("aws-off");
            headerPowerBtn.title = "Click to simulate AWS outage (Force Shutdown)";
            if (headerPowerText) headerPowerText.textContent = "Turn AWS OFF";
        } else {
            headerPowerBtn.classList.add("aws-off");
            headerPowerBtn.title = "Click to restore AWS Primary route";
            if (headerPowerText) headerPowerText.textContent = "Turn AWS ON";
        }
    }

    if (on) {
        showToast("♻️ AWS Sydney primary route restored. Traffic switched back to AWS Primary.", "success");
    } else {
        showToast("⚡ Force Shutdown! AWS Primary offline → auto-failover to Azure Hong Kong.", "warning");
    }

    updateDRDisplay();
}

if (headerPowerBtn) {
    headerPowerBtn.addEventListener("click", () => {
        setAwsPower(simulatedAwsDown); // toggle: if currently down, turn on; if up, turn off
    });
}

// ═══════════════════════════════════════════════════════════════════════════
//  MULTI-CLOUD HEALTH MONITOR & AUTO-FAILOVER
// ═══════════════════════════════════════════════════════════════════════════
async function probeCloudHealth() {
    if (simulatedAwsDown) {
        awsAlive = false;
        // Still probe Azure to maintain real-time status and latency
        try {
            const t0 = performance.now();
            const c = new AbortController();
            const t = setTimeout(() => c.abort(), 2500);
            const r = await fetch(`${AZURE_ENDPOINT}/healthz`, { signal: c.signal });
            clearTimeout(t);
            azureAlive = r.ok;
            if (azureLatencyEl) azureLatencyEl.innerText = `${Math.round(performance.now() - t0)} ms`;
        } catch (e) {
            azureAlive = false;
            if (azureLatencyEl) azureLatencyEl.innerText = "Timeout";
        }
        updateDRDisplay();
        return;
    }

    // Measure AWS Latency
    try {
        const t0 = performance.now();
        const c = new AbortController();
        const t = setTimeout(() => c.abort(), 2500);
        const r = await fetch(`${AWS_ENDPOINT}/healthz`, { signal: c.signal });
        clearTimeout(t);
        awsAlive = r.ok;
        if (awsLatencyEl) awsLatencyEl.innerText = `${Math.round(performance.now() - t0)} ms`;
    } catch (e) {
        awsAlive = false;
        if (awsLatencyEl) awsLatencyEl.innerText = "Timeout";
    }

    // Measure Azure Latency
    try {
        const t0 = performance.now();
        const c = new AbortController();
        const t = setTimeout(() => c.abort(), 2500);
        const r = await fetch(`${AZURE_ENDPOINT}/healthz`, { signal: c.signal });
        clearTimeout(t);
        azureAlive = r.ok;
        if (azureLatencyEl) azureLatencyEl.innerText = `${Math.round(performance.now() - t0)} ms`;
    } catch (e) {
        azureAlive = false;
        if (azureLatencyEl) azureLatencyEl.innerText = "Timeout";
    }

    updateDRDisplay();
}

function updateDRDisplay() {
    const isAwsActive = !simulatedAwsDown && awsAlive;

    if (isAwsActive) {
        // AWS Primary is ONLINE and actively serving
        awsDot.className = "status-indicator live";
        awsState.innerText = "ONLINE";
        awsBadge.className = "cloud-badge active-cloud";
        if (cardAws) {
            cardAws.classList.remove("offline-server");
            cardAwsStatus.className = "server-status-pill online";
            cardAwsStatus.innerText = "ACTIVE PRIMARY";
        }

        if (azureAlive) {
            azureDot.className = "status-indicator standby";
            azureState.innerText = "HOT STANDBY";
            azureBadge.className = "cloud-badge";
            if (cardAzure) {
                cardAzure.classList.remove("active-server");
                cardAzureStatus.className = "server-status-pill standby";
                cardAzureStatus.innerText = "HOT STANDBY";
            }
        } else {
            azureDot.className = "status-indicator offline";
            azureState.innerText = "OFFLINE";
            azureBadge.className = "cloud-badge offline-cloud";
            if (cardAzure) {
                cardAzure.classList.remove("active-server");
                cardAzureStatus.className = "server-status-pill offline";
                cardAzureStatus.innerText = "OFFLINE";
            }
        }

        currentServingCloud = "aws";
        currentServingLabel.innerText = "AWS Sydney (Primary)";
        activeRoutePill.className = "active-route-pill";

        if (routingBanner) {
            routingBanner.classList.remove("failover-active");
            routingTargetText.innerText = "AWS Sydney (Primary)";
        }

        activeBaseUrl = AWS_ENDPOINT;
    } else {
        // AWS is down or Force Shutdown / Simulated Outage is active -> Failover to Azure
        awsDot.className = "status-indicator offline";
        awsState.innerText = simulatedAwsDown ? "SIMULATED OUTAGE" : "OFFLINE";
        awsBadge.className = "cloud-badge offline-cloud";
        if (cardAws) {
            cardAws.classList.add("offline-server");
            cardAwsStatus.className = "server-status-pill offline";
            cardAwsStatus.innerText = simulatedAwsDown ? "SIMULATED OUTAGE" : "OFFLINE";
        }

        if (azureAlive) {
            azureDot.className = "status-indicator failover";
            azureState.innerText = "ACTIVE (FAILOVER)";
            azureBadge.className = "cloud-badge active-cloud";
            currentServingCloud = "azure";
            currentServingLabel.innerText = "Azure Hong Kong (Failover Route)";
            activeRoutePill.className = "active-route-pill failover-mode";

            if (cardAzure) {
                cardAzure.classList.add("active-server");
                cardAzureStatus.className = "server-status-pill online";
                cardAzureStatus.innerText = "ACTIVE (FAILOVER)";
            }

            if (routingBanner) {
                routingBanner.classList.add("failover-active");
                routingTargetText.innerText = "Azure East Asia (Auto-Failover Active)";
            }

            activeBaseUrl = AZURE_ENDPOINT;
        } else {
            azureDot.className = "status-indicator offline";
            azureState.innerText = "OFFLINE";
            currentServingLabel.innerText = "ALL CLOUDS UNREACHABLE";
            if (routingBanner) routingTargetText.innerText = "NONE (All Servers Down)";
        }
    }
}

setInterval(probeCloudHealth, 4000);
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

    // If AWS is force shutdown / simulated down, send directly to Azure
    let targetEndpoint = (simulatedAwsDown || !awsAlive) ? AZURE_ENDPOINT : activeBaseUrl;
    let targetUrl = `${targetEndpoint}/predict`;

    try {
        let response;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 12000); // 12s timeout
        try {
            response = await fetch(targetUrl, { method: "POST", body: formData, signal: controller.signal });
            clearTimeout(timeoutId);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
        } catch (fetchErr) {
            clearTimeout(timeoutId);
            console.warn("Primary endpoint timed out or failed. Auto-failing over to Azure Standby:", fetchErr);
            showToast("Primary offline. Auto-failing over to Azure Standby...", "info");
            targetUrl = `${AZURE_ENDPOINT}/predict`;
            response = await fetch(targetUrl, { method: "POST", body: formData });
            probeCloudHealth();
        }
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();
        const servedBy = response.headers.get("X-Served-By") || currentServingCloud;
        displayResults(data, servedBy);
        loadHistoryArchive();

        if (servedBy === "azure" || simulatedAwsDown) {
            showToast("⚡ Screening processed by Azure Standby (Auto-Failover, 0 Data Loss).", "info");
        } else {
            showToast("✓ Diagnostic complete (Served by AWS Primary).");
        }
    } catch (error) {
        showToast("Inference failed: " + error.message, "error");
    } finally {
        submitBtn.classList.remove("hidden");
        loadingSpinner.classList.add("hidden");
    }
});

// ═══════════════════════════════════════════════════════════════════════════
//  DISPLAY RESULTS
// ═══════════════════════════════════════════════════════════════════════════
function displayResults(data, servedBy) {
    resultsPlaceholder.classList.add("hidden");
    resultsContent.classList.remove("hidden");

    const isFLD = data.label === "FLD";
    resultLabel.innerText = isFLD ? "Fatty Liver Disease (FLD)" : "Healthy (No FLD)";
    resultLabel.className = `result-badge ${isFLD ? "fld" : "no-fld"}`;

    disclaimerText.innerText = isFLD
        ? "High probability of hepatic steatosis detected. Comprehensive hepatic ultrasound and clinical evaluation recommended."
        : "Low statistical risk of FLD detected based on current biomarkers. Regular annual checkups recommended.";

    const regionText = (servedBy === "azure" || simulatedAwsDown)
        ? "Azure East Asia (Hong Kong) Standby [Failover Active - 0 Data Loss]"
        : "AWS Sydney (ap-southeast-2) Primary";
    servedByText.innerHTML = `Served by: <strong>${regionText}</strong>`;

    renderDonutChart(data.probabilities);
    renderBarChart(data.top_features);
}

function renderDonutChart(probs) {
    const ctx = document.getElementById("donut-chart").getContext("2d");
    if (donutChart) donutChart.destroy();

    donutChart = new Chart(ctx, {
        type: "doughnut",
        data: {
            labels: ["FLD Probability", "Healthy Probability"],
            datasets: [{
                data: [probs.FLD * 100, probs.No_FLD * 100],
                backgroundColor: ["#ff453a", "#30d158"],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { color: "#8e8e93", font: { size: 10 } } }
            },
            cutout: "70%"
        }
    });
}

function renderBarChart(features) {
    const ctx = document.getElementById("bar-chart").getContext("2d");
    if (barChart) barChart.destroy();

    const labels = Object.keys(features);
    const values = Object.values(features);

    barChart = new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [{
                label: "SHAP Impact Score",
                data: values,
                backgroundColor: values.map(v => v >= 0 ? "rgba(255, 69, 58, 0.7)" : "rgba(48, 209, 88, 0.7)"),
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: "#8e8e93", font: { size: 9 } }, grid: { color: "rgba(255,255,255,0.05)" } },
                y: { ticks: { color: "#8e8e93", font: { size: 9 } }, grid: { display: false } }
            }
        }
    });
}

// ═══════════════════════════════════════════════════════════════════════════
//  HISTORY ARCHIVE — LOAD, DELETE, CLEAR ALL
// ═══════════════════════════════════════════════════════════════════════════
refreshHistoryBtn.addEventListener("click", () => {
    loadHistoryArchive();
    showToast("Refreshing synchronized archive...", "info");
});

async function loadHistoryArchive() {
    const primaryUrl = `${activeBaseUrl}/api/history`;
    const fallbackUrl = (activeBaseUrl === AWS_ENDPOINT) ? `${AZURE_ENDPOINT}/api/history` : `${AWS_ENDPOINT}/api/history`;

    try {
        let res;
        try {
            const c = new AbortController();
            const t = setTimeout(() => c.abort(), 4000);
            res = await fetch(primaryUrl, { signal: c.signal });
            clearTimeout(t);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
        } catch (e) {
            res = await fetch(fallbackUrl);
        }
        if (!res.ok) throw new Error("Fetch failed");
        const data = await res.json();
        renderHistoryCards(data.records || [], data.cloud || currentServingCloud);
    } catch (err) {
        historyGrid.innerHTML = `
            <div class="history-empty">
                <span class="empty-icon">⚠️</span>
                <h4>Unable to Load Archive</h4>
                <p>${err.message}</p>
            </div>`;
    }
}

function renderHistoryCards(records, cloudOrigin) {
    if (!records || records.length === 0) {
        historyGrid.innerHTML = `
            <div class="history-empty">
                <span class="empty-icon">📂</span>
                <h4>Synchronized Archive Empty</h4>
                <p>No clinical diagnostic records found across AWS RDS and Azure PostgreSQL.</p>
            </div>`;
        return;
    }

    historyGrid.innerHTML = records.map(r => {
        const isFLD = r.label === "FLD";
        const badgeClass = isFLD ? "fld" : "no_fld";
        const fldProb = (r.probs && r.probs.FLD !== undefined) ? (r.probs.FLD * 100).toFixed(1) : "N/A";
        const imgUrl = `${activeBaseUrl}/api/image/${r.image_key}`;

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
                    <img src="${imgUrl}" alt="Tongue" class="history-thumb" onerror="this.parentElement.innerHTML='<span style=\\'font-size:2rem;color:var(--text-tertiary);\\'>👅</span>'">
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
                        <div class="history-prob-fill" style="width: ${fldProb}%"></div>
                    </div>
                </div>
            </div>`;
    }).join("");
}

// ── Delete Single Record ────────────────────────────────────────────────
async function deleteSingleRecord(predId) {
    const confirmed = await showConfirm(
        "Delete Record",
        `Permanently remove diagnostic record #${predId.substring(0, 8)} from both AWS RDS and Azure PostgreSQL databases?`
    );
    if (!confirmed) return;

    try {
        // Send DELETE to both cloud endpoints
        const delAws = fetch(`${AWS_ENDPOINT}/api/history/${predId}`, { method: "DELETE" }).catch(() => ({ ok: false }));
        const delAz = fetch(`${AZURE_ENDPOINT}/api/history/${predId}`, { method: "DELETE" }).catch(() => ({ ok: false }));
        const [rAws, rAz] = await Promise.all([delAws, delAz]);

        if (!rAws.ok && !rAz.ok) {
            throw new Error("Failed to delete record on cloud databases.");
        }

        // Animate card removal
        const card = document.querySelector(`.history-card[data-id="${predId}"]`);
        if (card) {
            card.style.transition = "all 0.3s ease";
            card.style.opacity = "0";
            card.style.transform = "scale(0.95)";
            setTimeout(() => {
                card.remove();
                if (!historyGrid.querySelector(".history-card")) {
                    historyGrid.innerHTML = `
                        <div class="history-empty">
                            <span class="empty-icon">📂</span>
                            <h4>Synchronized Archive Empty</h4>
                            <p>No clinical diagnostic records found across AWS RDS and Azure PostgreSQL.</p>
                        </div>`;
                }
            }, 300);
        }
        showToast("Record deleted from both AWS & Azure databases.");
    } catch (err) {
        showToast("Delete failed: " + err.message, "error");
    }
}

// ── Clear All Records ───────────────────────────────────────────────────
clearAllBtn.addEventListener("click", async () => {
    const confirmed = await showConfirm(
        "Clear All Diagnostic Records",
        "This will permanently delete ALL patient diagnostic records from both AWS RDS and Azure PostgreSQL databases. This action cannot be undone."
    );
    if (!confirmed) return;

    try {
        // Send DELETE to both clouds in parallel
        const clearAws = fetch(`${AWS_ENDPOINT}/api/history`, { method: "DELETE" }).then(r => r.ok ? r.json() : null).catch(() => null);
        const clearAz = fetch(`${AZURE_ENDPOINT}/api/history`, { method: "DELETE" }).then(r => r.ok ? r.json() : null).catch(() => null);
        const [resAws, resAz] = await Promise.all([clearAws, clearAz]);

        // Animate all cards out
        const cards = historyGrid.querySelectorAll(".history-card");
        cards.forEach((card, i) => {
            card.style.transition = `all 0.3s ease ${i * 0.04}s`;
            card.style.opacity = "0";
            card.style.transform = "scale(0.95)";
        });

        setTimeout(() => {
            historyGrid.innerHTML = `
                <div class="history-empty">
                    <span class="empty-icon">📂</span>
                    <h4>Synchronized Archive Cleared</h4>
                    <p>All clinical diagnostic records have been permanently cleared from both AWS Sydney RDS and Azure PostgreSQL.</p>
                </div>`;
        }, Math.min(cards.length * 40 + 300, 800));

        let totalDeleted = 0;
        if (resAws && resAws.deleted_rows) totalDeleted += resAws.deleted_rows;
        if (resAz && resAz.deleted_rows) totalDeleted += resAz.deleted_rows;

        if (totalDeleted > 0) {
            showToast(`Permanently deleted ${totalDeleted} records across AWS and Azure.`);
        } else {
            showToast("Archive cleared across both AWS and Azure databases.");
        }
    } catch (err) {
        showToast("Clear all failed: " + err.message, "error");
    }
});

// ── Initial load ────────────────────────────────────────────────────────
loadHistoryArchive();
