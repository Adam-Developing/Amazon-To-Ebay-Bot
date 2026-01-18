const defaultUrl = document.body.dataset.defaultUrl || "https://www.google.com";

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
    navBack: document.getElementById("navBack"),
    navForward: document.getElementById("navForward"),
    navRefresh: document.getElementById("navRefresh"),
    addressBar: document.getElementById("addressBar"),
    goBtn: document.getElementById("goBtn"),
    openEdgeBtn: document.getElementById("openEdgeBtn"),
    edgeMode: document.getElementById("edgeMode"),
    tabBar: document.getElementById("tabBar"),
    tabContents: document.getElementById("tabContents"),
    addTabBtn: document.getElementById("addTabBtn"),
    panelTabs: document.querySelectorAll(".panel-tab"),
    panelBodies: document.querySelectorAll(".panel-body"),
};

let tabs = [];
let activeTabId = null;
let tabCounter = 0;
let lastLogId = 0;
let activePromptId = null;
let lastPromptType = null;

function postJson(url, payload) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload || {}),
    }).then((response) => response.json().then((data) => ({ response, data })));
}

function normalizeUrl(text) {
    const trimmed = text.trim();
    if (!trimmed) {
        return "";
    }
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(trimmed)) {
        return trimmed;
    }
    if (/^[^\s/:]+\.[^\s/:]+.*$/.test(trimmed)) {
        return `https://${trimmed}`;
    }
    return `https://www.google.com/search?q=${encodeURIComponent(trimmed)}`;
}

function deriveTitle(url) {
    try {
        const parsed = new URL(url);
        return parsed.hostname || url;
    } catch (error) {
        return url || "Tab";
    }
}

function createTab(url, activate = true) {
    const id = ++tabCounter;
    const tabButton = document.createElement("button");
    tabButton.className = "tab";
    tabButton.dataset.tabId = String(id);

    const titleSpan = document.createElement("span");
    titleSpan.textContent = deriveTitle(url);

    const closeSpan = document.createElement("span");
    closeSpan.className = "close";
    closeSpan.textContent = "×";

    tabButton.appendChild(titleSpan);
    tabButton.appendChild(closeSpan);
    elements.tabBar.insertBefore(tabButton, elements.addTabBtn);

    const iframe = document.createElement("iframe");
    iframe.className = "browser-frame";
    iframe.dataset.tabId = String(id);
    iframe.src = url;
    elements.tabContents.appendChild(iframe);

    const tab = { id, button: tabButton, titleSpan, iframe, url };
    tabs.push(tab);

    tabButton.addEventListener("click", (event) => {
        if (event.target === closeSpan) {
            closeTab(id);
            return;
        }
        setActiveTab(id);
    });

    closeSpan.addEventListener("click", (event) => {
        event.stopPropagation();
        closeTab(id);
    });

    iframe.addEventListener("load", () => {
        tab.url = iframe.src;
        tab.titleSpan.textContent = deriveTitle(tab.url).slice(0, 24);
        if (activeTabId === id) {
            elements.addressBar.value = tab.url;
        }
    });

    if (activate) {
        setActiveTab(id);
    }
}

function setActiveTab(id) {
    activeTabId = id;
    tabs.forEach((tab) => {
        const isActive = tab.id === id;
        tab.button.classList.toggle("active", isActive);
        tab.iframe.style.display = isActive ? "block" : "none";
        if (isActive) {
            elements.addressBar.value = tab.url || "";
        }
    });
}

function closeTab(id) {
    if (tabs.length <= 1) {
        return;
    }
    const index = tabs.findIndex((tab) => tab.id === id);
    if (index === -1) {
        return;
    }
    const tab = tabs[index];
    tab.button.remove();
    tab.iframe.remove();
    tabs.splice(index, 1);
    if (activeTabId === id) {
        const fallback = tabs[Math.min(index, tabs.length - 1)];
        if (fallback) {
            setActiveTab(fallback.id);
        }
    }
}

function getActiveTab() {
    return tabs.find((tab) => tab.id === activeTabId) || null;
}

function navigateCurrent(url) {
    const target = getActiveTab();
    if (!target) {
        return;
    }
    target.url = url;
    target.iframe.src = url;
    target.titleSpan.textContent = deriveTitle(url).slice(0, 24);
    elements.addressBar.value = url;
}

function openExternal(url) {
    if (!url) {
        return;
    }
    window.open(url, "_blank", "noopener");
}

function handleNavigation() {
    const url = normalizeUrl(elements.addressBar.value);
    if (!url) {
        return;
    }
    if (elements.edgeMode.checked) {
        elements.addressBar.value = url;
        openExternal(url);
        return;
    }
    navigateCurrent(url);
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
        if (elements.edgeMode.checked) {
            openExternal(url);
        } else {
            createTab(url, true);
        }
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

elements.navBack.addEventListener("click", () => {
    const active = getActiveTab();
    if (active && active.iframe.contentWindow) {
        active.iframe.contentWindow.history.back();
    }
});

elements.navForward.addEventListener("click", () => {
    const active = getActiveTab();
    if (active && active.iframe.contentWindow) {
        active.iframe.contentWindow.history.forward();
    }
});

elements.navRefresh.addEventListener("click", () => {
    const active = getActiveTab();
    if (active && active.iframe.contentWindow) {
        active.iframe.contentWindow.location.reload();
    }
});

elements.addressBar.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        handleNavigation();
    }
});

elements.goBtn.addEventListener("click", handleNavigation);

elements.openEdgeBtn.addEventListener("click", () => {
    const url = normalizeUrl(elements.addressBar.value || (getActiveTab() || {}).url || "");
    openExternal(url);
});

elements.edgeMode.addEventListener("change", () => {
    const state = elements.edgeMode.checked ? "ON" : "OFF";
    postJson("/api/log", { message: `Edge mode: ${state}` });
});

elements.addTabBtn.addEventListener("click", () => createTab(defaultUrl, true));

document.addEventListener("keydown", (event) => {
    if (event.ctrlKey && event.key.toLowerCase() === "t") {
        event.preventDefault();
        createTab(defaultUrl, true);
    }
    if (event.ctrlKey && event.key.toLowerCase() === "w") {
        event.preventDefault();
        const active = getActiveTab();
        if (active) {
            closeTab(active.id);
        }
    }
    if (event.ctrlKey && event.shiftKey && event.key === "Tab") {
        event.preventDefault();
        if (tabs.length > 1) {
            const currentIndex = tabs.findIndex((tab) => tab.id === activeTabId);
            const nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
            setActiveTab(tabs[nextIndex].id);
        }
    }
    if (event.ctrlKey && event.key === "Tab" && !event.shiftKey) {
        event.preventDefault();
        if (tabs.length > 1) {
            const currentIndex = tabs.findIndex((tab) => tab.id === activeTabId);
            const nextIndex = (currentIndex + 1) % tabs.length;
            setActiveTab(tabs[nextIndex].id);
        }
    }
    if (event.key === "F5" || (event.ctrlKey && event.key.toLowerCase() === "r")) {
        event.preventDefault();
        elements.navRefresh.click();
    }
    if (event.altKey && event.key === "ArrowLeft") {
        event.preventDefault();
        elements.navBack.click();
    }
    if (event.altKey && event.key === "ArrowRight") {
        event.preventDefault();
        elements.navForward.click();
    }
});

createTab(defaultUrl, true);

setInterval(refreshLogs, 1500);
setInterval(refreshPrompt, 1500);
setInterval(refreshState, 2000);
setInterval(refreshOpenUrls, 2000);
