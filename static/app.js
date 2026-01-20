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

async function postJson(url, payload) {
    const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
    });
    let data = {};
    try {
        data = await response.json();
    } catch (error) {
        console.warn("Failed to parse JSON response", error);
        data = {};
    }
    return { response, data };
}

function openExternal(url) {
    if (!url) {
        return;
    }
    window.open(url, "_blank", "noopener");
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
    elements.promptPanel.hidden = false;
}

function hidePrompt() {
    activePromptId = null;
    lastPromptType = null;
    elements.promptPanel.hidden = true;
}

async function submitPrompt(value) {
    if (activePromptId === null) {
        return;
    }
    await postJson(`/api/prompts/${activePromptId}`, { value });
    hidePrompt();
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
    const { response, data } = await postJson("/api/auth");
    if (!response.ok) {
        alert(data.error || "Failed to start auth.");
    }
});

elements.logoutBtn.addEventListener("click", async () => {
    const { response, data } = await postJson("/api/logout");
    if (!response.ok) {
        alert(data.error || "Failed to logout.");
    }
});

elements.scrapeBtn.addEventListener("click", async () => {
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
    const { response, data } = await postJson("/api/list");
    if (!response.ok) {
        alert(data.error || "Failed to list item.");
    }
});

elements.bulkProcessBtn.addEventListener("click", async () => {
    const { response, data } = await postJson("/api/bulk/process", { text: elements.bulkText.value });
    if (!response.ok) {
        alert(data.error || "Failed to start bulk processing.");
    }
});

elements.bulkPauseBtn.addEventListener("click", async () => {
    const { response, data } = await postJson("/api/bulk/pause");
    if (!response.ok) {
        alert(data.error || "Failed to toggle bulk pause.");
    } else {
        elements.bulkPauseBtn.textContent = data.paused ? "Resume" : "Pause";
    }
});

elements.bulkCancelBtn.addEventListener("click", async () => {
    const { response, data } = await postJson("/api/bulk/cancel");
    if (!response.ok) {
        alert(data.error || "Failed to cancel bulk.");
    }
});

elements.promptOk.addEventListener("click", async () => {
    const value = lastPromptType === "choice" ? elements.promptSelect.value : elements.promptInput.value;
    await submitPrompt(value);
});

elements.promptCancel.addEventListener("click", async () => {
    await submitPrompt(null);
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
setInterval(refreshState, 2000);
setInterval(refreshOpenUrls, 2000);
