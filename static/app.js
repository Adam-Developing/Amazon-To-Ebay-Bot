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
    panelTabs: document.querySelectorAll(".panel-tab"),
    panelBodies: document.querySelectorAll(".panel-body"),
};
let lastLogId = 0;
let activePromptId = null;
let lastPromptType = null;

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

    const bulk = data.bulk || {};
    const running = Boolean(bulk.running);
    elements.bulkProcessBtn.disabled = running;
    elements.bulkPauseBtn.hidden = !running;
    elements.bulkCancelBtn.hidden = !running;
    elements.bulkPauseBtn.textContent = bulk.paused ? "Resume" : "Pause";
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
    if (activePromptId === null) {
        return;
    }
    const value = lastPromptType === "choice" ? elements.promptSelect.value : elements.promptInput.value;
    await postJson(`/api/prompts/${activePromptId}`, { value });
    hidePrompt();
});

elements.promptCancel.addEventListener("click", async () => {
    if (activePromptId === null) {
        return;
    }
    await postJson(`/api/prompts/${activePromptId}`, { value: null });
    hidePrompt();
});

elements.toggleLogBtn.addEventListener("click", () => {
    const isHidden = elements.logView.hidden;
    elements.logView.hidden = !isHidden;
    elements.toggleLogBtn.textContent = isHidden ? "Hide Log" : "Show Log";
});

setInterval(refreshLogs, 1500);
setInterval(refreshPrompt, 1500);
setInterval(refreshState, 2000);
setInterval(refreshOpenUrls, 2000);
