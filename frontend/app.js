/* ── Configuration ──────────────────────────────────── */
const API_BASE = "http://localhost:8000/api/v1";

/* ── DOM Elements ──────────────────────────────────── */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const apiKeyInput = $("#api-key-input");
const apiKeyToggle = $("#api-key-toggle");
const apiStatus = $("#api-status");
const themeToggle = $("#theme-toggle");
const themeIcon = themeToggle.querySelector(".theme-icon");

// Upload
const dropZone = $("#drop-zone");
const fileInput = $("#file-input");
const uploadBtn = $("#upload-btn");
const tagsInput = $("#tags-input");
const locationInput = $("#location-input");
const uploadProgress = $("#upload-progress");
const progressFill = $("#progress-fill");
const progressText = $("#progress-text");
const uploadResults = $("#upload-results");

// Search
const searchInput = $("#search-input");
const searchBtn = $("#search-btn");
const filterType = $("#filter-type");
const topK = $("#top-k");
const searchResults = $("#search-results");

// Ask
const askInput = $("#ask-input");
const askBtn = $("#ask-btn");
const askResults = $("#ask-results");

// Toast
const toast = $("#toast");

let selectedFiles = [];

/* ── Theme Toggle ──────────────────────────────────── */

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
    localStorage.setItem("pai-theme", theme);
}

themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "light" : "dark");
});

// Load saved theme
const savedTheme = localStorage.getItem("pai-theme") || "light";
setTheme(savedTheme);

/* ── API Key ───────────────────────────────────────── */

function getApiKey() {
    return apiKeyInput.value.trim();
}

apiKeyToggle.addEventListener("click", () => {
    const type = apiKeyInput.type === "password" ? "text" : "password";
    apiKeyInput.type = type;
    apiKeyToggle.textContent = type === "password" ? "👁" : "🔒";
});

apiKeyInput.addEventListener("input", () => {
    if (getApiKey()) {
        apiStatus.textContent = "Ready";
        apiStatus.className = "api-status connected";
    } else {
        apiStatus.textContent = "";
        apiStatus.className = "api-status";
    }
});

// Load saved API key
const savedKey = localStorage.getItem("pai-api-key");
if (savedKey) {
    apiKeyInput.value = savedKey;
    apiStatus.textContent = "Ready";
    apiStatus.className = "api-status connected";
}

apiKeyInput.addEventListener("change", () => {
    localStorage.setItem("pai-api-key", getApiKey());
});

/* ── Tabs ──────────────────────────────────────────── */

$$(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
        $$(".tab").forEach((t) => t.classList.remove("active"));
        $$(".panel").forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        $(`#panel-${tab.dataset.tab}`).classList.add("active");
    });
});

/* ── Toast Notifications ───────────────────────────── */

function showToast(message, type = "success") {
    toast.textContent = message;
    toast.className = `toast ${type}`;
    toast.hidden = false;
    setTimeout(() => {
        toast.hidden = true;
    }, 3000);
}

/* ── API Helpers ───────────────────────────────────── */

async function apiRequest(endpoint, options = {}) {
    const key = getApiKey();
    if (!key) {
        showToast("Please enter your API key first", "error");
        throw new Error("No API key");
    }

    const headers = { "X-API-Key": key, ...options.headers };
    const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
}

/* ── File Upload ───────────────────────────────────── */

// Drag & drop
dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    handleFiles(e.dataTransfer.files);
});
fileInput.addEventListener("change", () => handleFiles(fileInput.files));

function handleFiles(files) {
    selectedFiles = [...files];
    if (selectedFiles.length > 0) {
        uploadBtn.disabled = false;
        dropZone.querySelector(".upload-text").textContent =
            `${selectedFiles.length} file(s) selected`;
        dropZone.querySelector(".upload-sub").textContent =
            selectedFiles.map((f) => f.name).join(", ");
    }
}

uploadBtn.addEventListener("click", async () => {
    if (!selectedFiles.length) return;

    uploadBtn.disabled = true;
    uploadProgress.hidden = false;
    uploadResults.innerHTML = "";

    let done = 0;
    for (const file of selectedFiles) {
        progressText.textContent = `Uploading ${file.name}... (${done + 1}/${selectedFiles.length})`;
        progressFill.style.width = `${((done) / selectedFiles.length) * 100}%`;

        const formData = new FormData();
        formData.append("file", file);
        if (tagsInput.value.trim()) formData.append("tags", tagsInput.value.trim());
        if (locationInput.value.trim()) formData.append("location", locationInput.value.trim());

        try {
            const result = await apiRequest("/upload", {
                method: "POST",
                body: formData,
            });
            uploadResults.innerHTML += createUploadCard(result, true);
        } catch (err) {
            uploadResults.innerHTML += createUploadCard({ filename: file.name, error: err.message }, false);
        }
        done++;
        progressFill.style.width = `${(done / selectedFiles.length) * 100}%`;
    }

    progressText.textContent = "Upload complete!";
    showToast(`${done} file(s) uploaded successfully`);

    // Reset after a delay
    setTimeout(() => {
        selectedFiles = [];
        fileInput.value = "";
        uploadBtn.disabled = true;
        uploadProgress.hidden = true;
        progressFill.style.width = "0%";
        dropZone.querySelector(".upload-text").textContent = "Drag & drop files here";
        dropZone.querySelector(".upload-sub").textContent = "or click to browse";
    }, 2000);
});

function createUploadCard(data, success) {
    if (success) {
        return `
            <div class="result-card upload-success">
                <div class="result-header">
                    <span class="result-filename">${fileIcon(data.file_type)} ${data.filename}</span>
                    <span class="result-badge badge-${data.file_type}">${data.file_type}</span>
                </div>
                <div class="result-meta">
                    <span>✅ ${data.message || "Uploaded and queued for ingestion"}</span>
                </div>
            </div>
        `;
    }
    return `
        <div class="result-card upload-error">
            <div class="result-header">
                <span class="result-filename">❌ ${data.filename}</span>
            </div>
            <div class="result-text">${data.error}</div>
        </div>
    `;
}

/* ── Search ────────────────────────────────────────── */

searchBtn.addEventListener("click", doSearch);
searchInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") doSearch();
});

async function doSearch() {
    const query = searchInput.value.trim();
    if (!query) return;

    searchResults.innerHTML = `<div class="loading"><div class="spinner"></div> Searching...</div>`;

    const body = {
        query,
        top_k: parseInt(topK.value),
    };
    const ft = filterType.value;
    if (ft) body.filters = { file_type: ft };

    try {
        const data = await apiRequest("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (data.results.length === 0) {
            searchResults.innerHTML = `
                <div class="empty-state">
                    <div class="icon">🔍</div>
                    <p>No results found for "${query}"</p>
                </div>
            `;
            return;
        }

        searchResults.innerHTML = data.results.map(createSearchCard).join("");
        if (data.cached) showToast("Results served from cache ⚡");
    } catch (err) {
        searchResults.innerHTML = `<div class="result-card upload-error"><div class="result-text">${err.message}</div></div>`;
    }
}

function createSearchCard(r) {
    const text = r.chunk_text || r.caption || "—";
    const score = (r.score * 100).toFixed(1);
    return `
        <div class="result-card">
            <div class="result-header">
                <span class="result-filename">${fileIcon(r.file_type)} ${r.filename}</span>
                <span class="result-score">${score}% match</span>
            </div>
            <div class="result-text">${escapeHtml(text)}</div>
            <div class="result-meta">
                <span class="result-badge badge-${r.file_type}">${r.file_type}</span>
                ${r.location ? `<span>📍 ${r.location}</span>` : ""}
                ${r.tags ? `<span>🏷️ ${r.tags.join(", ")}</span>` : ""}
            </div>
        </div>
    `;
}

/* ── Ask ───────────────────────────────────────────── */

askBtn.addEventListener("click", doAsk);
askInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        doAsk();
    }
});

async function doAsk() {
    const question = askInput.value.trim();
    if (!question) return;

    askResults.innerHTML = `<div class="loading"><div class="spinner"></div> Thinking...</div>`;

    try {
        const data = await apiRequest("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });

        let html = `
            <div class="answer-card">
                <div class="answer-label">🤖 AI Answer</div>
                <div class="answer-text">${escapeHtml(data.answer)}</div>
                <div class="answer-meta">
                    ${data.reasoning_used ? "🧠 Claude reasoning used" : "⚡ Direct retrieval (no LLM cost)"}
                    · ${data.sources.length} source(s)
                </div>
            </div>
        `;

        if (data.sources.length > 0) {
            html += `<div style="font-size:13px;font-weight:600;color:var(--text-secondary);margin-top:8px;">📎 Sources</div>`;
            html += data.sources.map(createSearchCard).join("");
        }

        askResults.innerHTML = html;
    } catch (err) {
        askResults.innerHTML = `<div class="result-card upload-error"><div class="result-text">${err.message}</div></div>`;
    }
}

/* ── Helpers ───────────────────────────────────────── */

function fileIcon(type) {
    const icons = {
        pdf: "📕",
        docx: "📘",
        text: "📄",
        image: "🖼️",
    };
    return icons[type] || "📁";
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}
