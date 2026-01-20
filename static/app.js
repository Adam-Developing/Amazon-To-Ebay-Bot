const elements = {
    amazonUrl: document.getElementById("amazonUrl"),
    quantity: document.getElementById("quantity"),
    sellerNote: document.getElementById("sellerNote"),
    customSpecs: document.getElementById("customSpecs"),
    loadJsonBtn: document.getElementById("loadJsonBtn"),
    jsonFile: document.getElementById("jsonFile"),
    authBtn: document.getElementById("authBtn"),
    logoutBtn: document.getElementById("logoutBtn"),
    scrapeBtn: document.getElementById("scrapeBtn"),
    listBtn: document.getElementById("listBtn"),
    bulkText: document.getElementById("bulkText"),
    bulkProcessBtn: document.getElementById("bulkProcessBtn"),
    bulkPauseBtn: document.getElementById("bulkPauseBtn"),
    bulkCancelBtn: document.getElementById("bulkCancelBtn"),
    promptPanel: document.getElementById("promptPanel"),
    promptLabel: document.getElementById("promptLabel"),
    promptInput: document.getElementById("promptInput"),
    promptSelect: document.getElementById("promptSelect"),
    promptOk: document.getElementById("promptOk"),
    promptCancel: document.getElementById("promptCancel"),
    toggleLogBtn: document.getElementById("toggleLogBtn"),
    logView: document.getElementById("logView"),
    statusBadge: document.getElementById("statusBadge"),
    statusMessage: document.getElementById("statusMessage"),
    bulkItems: document.getElementById("bulkItems"),
    bulkMeta: document.getElementById("bulkMeta"),
    bulkPreview: document.getElementById("bulkPreview"),
    panelTabs: document.querySelectorAll(".panel-tab"),
    panelBodies: document.querySelectorAll(".panel-body"),
    loadingSpinner: document.getElementById("loadingSpinner"),
};
let lastLogId = 0;
let activePromptId = null;
let lastPromptType = null;
let bulkPreviewTimeout = null;

const BULK_STATUS_TONES = {
    Ready: "idle",
    Scraping: "working",
    Listing: "working",
    Listed: "success",
    Failed: "error",
    Cancelled: "warning",
};

// Helper to show/hide the small status spinner next to the status badge
function showSpinner() {
    if (!elements || !elements.loadingSpinner) return;
    try {
        elements.loadingSpinner.hidden = false;
        elements.loadingSpinner.setAttribute('aria-hidden', 'false');
    } catch (e) {
        // ignore
    }
}

function hideSpinner() {
    if (!elements || !elements.loadingSpinner) return;
    try {
        elements.loadingSpinner.hidden = true;
        elements.loadingSpinner.setAttribute('aria-hidden', 'true');
    } catch (e) {
        // ignore
    }
}

async function postJson(url, payload) {
    if (elements.loadingSpinner) showSpinner();
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
    });
    let data;
    try {
        data = await response.json();
    } catch (error) {
        console.warn("Failed to parse JSON response", error);
        data = {};
    }
    // Hide spinner for immediate response; long-running server work will be reflected via /api/state polling
    if (elements.loadingSpinner) hideSpinner();
    return { response, data };
}

function openExternal(url) {
    if (!url) {
        return;
    }

    // Send a message to any installed helper extension via window.postMessage.
    // The extension's content script can intercept this and ask the extension
    // background script to create the new tab at the index (currentTab.index + 1).
    // We wait briefly for an acknowledgement; if no extension handles it we
    // open a normal new tab (_blank).
    const request = { type: 'amazonToEbay_open_url_request', url };
    let handled = false;

    function onMessage(event) {
        if (!event || !event.data) return;
        const d = event.data;
        if (d && d.type === 'amazonToEbay_open_url_handled' && d.url === url) {
            handled = true;
            window.removeEventListener('message', onMessage);
        }
    }

    try {
        window.addEventListener('message', onMessage);
        window.postMessage(request, '*');
    } catch (e) {
        // ignore
    }

    // Wait briefly for extension to handle. If not handled, open a normal new tab.
    setTimeout(() => {
        if (handled) return;
        try {
            window.open(url, "_blank", "noopener");
        } catch (e) {
            // ignore
        }
    }, 250);
}

function toggleTabPanel(targetId) {
    elements.panelTabs.forEach((tab) => {
        tab.classList.toggle("active", tab.dataset.target === targetId);
    });
    elements.panelBodies.forEach((panel) => {
        panel.classList.toggle("active", panel.id === targetId);
    });
    if (elements.bulkPreview) {
        elements.bulkPreview.hidden = targetId !== "bulk-panel";
    }
}

function showPrompt(prompt) {
    activePromptId = prompt.id;
    lastPromptType = prompt.type;
    if (!elements.promptPanel) return;
    elements.promptLabel.textContent = prompt.prompt;
    if (prompt.type === "choice") {
        elements.promptSelect.innerHTML = "";
        prompt.options.forEach((option) => {
            const opt = document.createElement("option");
            opt.value = option;
            opt.textContent = option;
            elements.promptSelect.appendChild(opt);
        });
        elements.promptSelect.hidden = false;
        elements.promptInput.hidden = true;
    } else {
        elements.promptInput.value = prompt.default || "";
        elements.promptInput.hidden = false;
        elements.promptSelect.hidden = true;
    }
    // Make sure the panel is visible for layout: clear hidden attribute and set display
    try {
        elements.promptPanel.hidden = false;
    } catch (e) {
        // ignore if not supported
    }
    elements.promptPanel.style.display = 'flex';
}

function hidePrompt() {
    activePromptId = null;
    lastPromptType = null;
    if (!elements.promptPanel) return;
    try {
        elements.promptPanel.hidden = true;
    } catch (e) {
        // ignore if not supported
    }
    elements.promptPanel.style.display = 'none';
}

hidePrompt();

async function submitPrompt(value) {
    if (activePromptId === null) {
        return;
    }
    await postJson(`/api/prompts/${activePromptId}`, { value });
    hidePrompt();
}

// Helper: clean up bulk UI after cancel
function clearBulkItemsUI() {
    if (elements.bulkItems) {
        elements.bulkItems.innerHTML = "";
    }
    if (elements.bulkMeta) {
        elements.bulkMeta.textContent = "Paste bulk text to preview items.";
    }
    if (elements.bulkPreview) {
        elements.bulkPreview.hidden = true;
    }
    if (elements.bulkText) {
        elements.bulkText.value = "";
    }
    if (elements.bulkPauseBtn) {
        elements.bulkPauseBtn.hidden = true;
    }
    if (elements.bulkCancelBtn) {
        elements.bulkCancelBtn.hidden = true;
    }
    if (elements.bulkProcessBtn) {
        elements.bulkProcessBtn.disabled = false;
    }
}

async function cancelPublishingAndCleanup() {
    // If the server is waiting on a prompt, resolve it first so it doesn't hang
    try {
        if (activePromptId !== null) {
            // send null as cancellation to the active prompt
            await postJson(`/api/prompts/${activePromptId}`, { value: null });
        }
    } catch (e) {
        // ignore prompt resolution errors
    }

    // Hide any visible prompt panel on the client
    try {
        hidePrompt();
    } catch (e) {
        // ignore
    }

    // Call server cancel endpoint for bulk publishing
    const { response, data } = await postJson("/api/bulk/cancel");
    if (!response.ok) {
        return { ok: false, data };
    }
    // UI cleanup
    clearBulkItemsUI();
    // Refresh state to sync UI with server
    try {
        await refreshState();
    } catch (e) {
        // ignore
    }
    return { ok: true, data };
}

async function handlePromptEnter(event, getValue) {
    if (event.key !== "Enter") {
        return;
    }
    event.preventDefault();
    await submitPrompt(getValue());
}

async function refreshPrompt() {
    const response = await fetch("/api/prompts");
    const data = await response.json();
    if (data.prompt) {
        if (activePromptId !== data.prompt.id) {
            showPrompt(data.prompt);
        }
    } else if (activePromptId !== null) {
        hidePrompt();
    }
}

async function refreshLogs() {
    const response = await fetch(`/api/logs?since=${lastLogId}`);
    const data = await response.json();
    data.entries.forEach((entry) => {
        elements.logView.textContent += `${entry.message}\n`;
    });
    lastLogId = data.last_id;
    if (data.entries.length) {
        elements.logView.scrollTop = elements.logView.scrollHeight;
    }
}

async function refreshState() {
    const response = await fetch("/api/state");
    const data = await response.json();
    elements.listBtn.disabled = !data.product_loaded || data.processing;
    elements.scrapeBtn.disabled = data.processing;
    elements.authBtn.disabled = data.processing;
    elements.logoutBtn.disabled = data.processing;

    const status = data.status || {};
    const statusLabel = status.label || (data.processing ? "Working" : "Idle");
    const statusMessage = status.message || (data.processing ? "Working..." : "Ready to start.");
    const statusTone = status.tone || (data.processing ? "working" : "idle");
    if (elements.statusBadge) {
        elements.statusBadge.textContent = statusLabel;
        elements.statusBadge.dataset.tone = statusTone;
    }
    if (elements.statusMessage) {
        elements.statusMessage.textContent = statusMessage;
    }

    // Show spinner while server-side processing is true
    if (data.processing) {
        showSpinner();
    } else {
        hideSpinner();
    }

    const bulk = data.bulk || {};
    const running = Boolean(bulk.running);
    elements.bulkProcessBtn.disabled = running;
    elements.bulkPauseBtn.hidden = !running;
    elements.bulkCancelBtn.hidden = !running;
    elements.bulkPauseBtn.textContent = bulk.paused ? "Resume" : "Pause";
    if (elements.bulkMeta) {
        const total = bulk.total || 0;
        const processed = bulk.processed || 0;
        const stateLabel = running ? (bulk.paused ? "Paused" : "Running") : total ? "Ready" : "Idle";
        elements.bulkMeta.textContent = total
            ? `${stateLabel} • Listed ${processed}/${total}`
            : "Paste bulk text to preview items.";
    }
    if (elements.bulkItems) {
        renderBulkItems(bulk.items || []);
    }

    return data;
}

async function refreshOpenUrls() {
    const response = await fetch("/api/open-urls");
    const data = await response.json();
    const urls = data.urls || [];
    urls.forEach((url) => {
        openExternal(url);
    });
}

elements.panelTabs.forEach((tab) => {
    tab.addEventListener("click", () => toggleTabPanel(tab.dataset.target));
});

elements.loadJsonBtn.addEventListener("click", () => elements.jsonFile.click());

elements.jsonFile.addEventListener("change", async (event) => {
    const file = event.target.files[0];
    if (!file) {
        return;
    }
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch("/api/load-json", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok || !data.ok) {
        alert(data.error || "Failed to load JSON.");
        return;
    }
    elements.amazonUrl.value = data.url || "";
    elements.quantity.value = data.quantity || "";
    elements.sellerNote.value = data.seller_note || "";
});

elements.authBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const { response, data } = await postJson("/api/auth");
    if (!response.ok) {
        alert(data.error || "Failed to start auth.");
    }
});

elements.logoutBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const { response, data } = await postJson("/api/logout");
    if (!response.ok) {
        alert(data.error || "Failed to logout.");
    }
});

elements.scrapeBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const payload = {
        url: elements.amazonUrl.value,
        quantity: elements.quantity.value,
        note: elements.sellerNote.value,
        custom_specs: elements.customSpecs.value,
    };
    const { response, data } = await postJson("/api/scrape", payload);
    if (!response.ok) {
        alert(data.error || "Failed to start scrape.");
    }
});

elements.listBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const { response, data } = await postJson("/api/list");
    if (!response.ok) {
        alert(data.error || "Failed to list item.");
    }
});

elements.bulkProcessBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const { response, data } = await postJson("/api/bulk/process", { text: elements.bulkText.value });
    if (!response.ok) {
        alert(data.error || "Failed to start bulk processing.");
    }
});

elements.bulkPauseBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const { response, data } = await postJson("/api/bulk/pause");
    if (!response.ok) {
        alert(data.error || "Failed to toggle bulk pause.");
    } else {
        elements.bulkPauseBtn.textContent = data.paused ? "Resume" : "Pause";
    }
});

// Updated cancel handler: cancel publishing, clean UI
elements.bulkCancelBtn.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const result = await cancelPublishingAndCleanup();
    if (!result.ok) {
        alert(result.data.error || "Failed to cancel bulk.");
    }
});

// When user clicks Cancel on the prompt, cancel publishing and cleanup
elements.promptCancel.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const result = await cancelPublishingAndCleanup();
    if (!result.ok) {
        alert(result.data.error || "Failed to cancel bulk.");
    }
});

elements.promptOk.addEventListener("click", async () => {
    try { showSpinner(); } catch (e) {}
    const value = lastPromptType === "choice" ? elements.promptSelect.value : elements.promptInput.value;
    await submitPrompt(value);
});


elements.promptInput.addEventListener("keydown", (event) =>
    handlePromptEnter(event, () => elements.promptInput.value),
);

elements.promptSelect.addEventListener("keydown", (event) =>
    handlePromptEnter(event, () => elements.promptSelect.value),
);

elements.toggleLogBtn.addEventListener("click", () => {
    const isHidden = elements.logView.hidden;
    elements.logView.hidden = !isHidden;
    elements.toggleLogBtn.textContent = isHidden ? "Hide Log" : "Show Log";
});

function renderBulkItems(items) {
    if (!elements.bulkItems) {
        return;
    }
    elements.bulkItems.innerHTML = "";
    if (!items || items.length === 0) {
        const empty = document.createElement("div");
        empty.className = "bulk-empty";
        empty.textContent = "No bulk items parsed yet.";
        elements.bulkItems.appendChild(empty);
        return;
    }
    items.forEach((item) => {
        const card = document.createElement("div");
        card.className = "bulk-item";

        const header = document.createElement("div");
        header.className = "bulk-item-header";

        const title = document.createElement("span");
        title.className = "bulk-item-title";
        title.textContent = `Item ${item.index || "?"}`.trim();

        const status = document.createElement("span");
        status.className = "status-pill bulk-status";
        const statusLabel = item.status || "Ready";
        status.dataset.tone = BULK_STATUS_TONES[statusLabel] || "idle";
        status.textContent = statusLabel;

        header.appendChild(title);
        header.appendChild(status);

        const body = document.createElement("div");
        body.className = "bulk-item-body";

        const url = document.createElement("div");
        url.className = "bulk-item-url";
        url.textContent = item.url || "Missing URL";

        // Show parsed product title when available
        if (item.title) {
            const titleLine = document.createElement("div");
            titleLine.className = "bulk-item-product-title";
            titleLine.textContent = item.title;
            body.appendChild(titleLine);
        }

        const meta = document.createElement("div");
        meta.className = "bulk-item-meta";
        const specifics = item.custom_specifics && Object.keys(item.custom_specifics).length
            ? Object.entries(item.custom_specifics)
                  .map(([key, value]) => `${key}: ${value}`)
                  .join(" | ")
            : "No custom specifics";
        const note = item.note ? `Note: ${item.note}` : "No note";
        meta.textContent = `Qty: ${item.quantity || 1} • ${note} • ${specifics}`;

        body.appendChild(url);
        body.appendChild(meta);

        if (item.message) {
            const message = document.createElement("div");
            message.className = "bulk-item-message";
            message.textContent = item.message;
            body.appendChild(message);
        }

        card.appendChild(header);
        card.appendChild(body);
        elements.bulkItems.appendChild(card);
    });
}

function scheduleBulkPreview() {
    if (!elements.bulkText) {
        return;
    }
    if (bulkPreviewTimeout) {
        clearTimeout(bulkPreviewTimeout);
    }
    bulkPreviewTimeout = setTimeout(async () => {
        try {
            const result = await postJson("/api/bulk/preview", { text: elements.bulkText.value });
            if (result.response.ok) {
                renderBulkItems(result.data.items || []);
            } else if (elements.bulkMeta) {
                elements.bulkMeta.textContent = result.data.error || "Unable to preview bulk items.";
            }
        } catch (error) {
            if (elements.bulkMeta) {
                elements.bulkMeta.textContent = "Unable to preview bulk items.";
            }
        }
    }, 400);
}

elements.bulkText.addEventListener("input", scheduleBulkPreview);

scheduleBulkPreview();

setInterval(refreshLogs, 1500);
setInterval(refreshPrompt, 1500);
setInterval(refreshOpenUrls, 2000);

// Adaptive polling: poll faster while server-side processing/bulk is running so item statuses update more responsively
(async function startAdaptiveStatePoll() {
    async function poll() {
        try {
            const data = await refreshState();
            const shouldPollFast = data && (data.processing || (data.bulk && data.bulk.running));
            setTimeout(poll, shouldPollFast ? 800 : 2000);
        } catch (e) {
            // On error, wait a bit and retry
            setTimeout(poll, 2000);
        }
    }
    poll();
})();
