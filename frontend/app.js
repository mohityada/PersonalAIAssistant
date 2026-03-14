/* ── Configuration ──────────────────────────────────── */
const API_BASE = (window.API_BASE && window.API_BASE.trim()) || "http://localhost:8000/api/v1";

/* ── DOM Elements ──────────────────────────────────── */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const authButtons = $("#auth-buttons");
const authLoginBtn = $("#auth-login-btn");
const authUser = $("#auth-user");
const authEmailDisplay = $("#auth-email-display");
const authLogoutBtn = $("#auth-logout-btn");

const authModal = $("#auth-modal");
const closeModalBtn = $("#close-modal-btn");
const tabLogin = $("#tab-login");
const tabRegister = $("#tab-register");
const authForm = $("#auth-form");
const nameGroup = $("#name-group");
const authName = $("#auth-name");
const authEmail = $("#auth-email");
const authPassword = $("#auth-password");
const confirmPasswordGroup = $("#confirm-password-group");
const authConfirmPassword = $("#auth-confirm-password");
const authSubmitBtn = $("#auth-submit-btn");
const authError = $("#auth-error");

const mainContent = $("#main-content");
const faqList = $("#faq-list");
const recentAsksList = $("#recent-asks-list");
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

// Upload mode toggle
const modeFileBtn = $("#mode-file");
const modeTextBtn = $("#mode-text");
const fileUploadSection = $("#file-upload-section");
const textUploadSection = $("#text-upload-section");
const textFilenameInput = $("#text-filename-input");
const textContentInput = $("#text-content-input");
const textUploadBtn = $("#text-upload-btn");

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

// Files
const filesRefreshBtn = $("#files-refresh-btn");
const filesList = $("#files-list");

// Toast
const toast = $("#toast");

let selectedFiles = [];
const _ingestionPolls = new Map(); // fileId -> intervalId

/* ── Theme Toggle ──────────────────────────────────── */

const sunSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`;
const moonSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;

function setTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeIcon.innerHTML = theme === "dark" ? sunSvg : moonSvg;
    localStorage.setItem("pai-theme", theme);
}

themeToggle.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "light" : "dark");
});

// Load saved theme
const savedTheme = localStorage.getItem("pai-theme") || "light";
setTheme(savedTheme);

/* ── Auth Flow ─────────────────────────────────────── */

let isLoginMode = true;
let currentToken = localStorage.getItem("pai-token") || null;
let currentUser = localStorage.getItem("pai-user") || null;

function applyAuthLock() {
    if (currentToken) {
        mainContent.style.opacity = "1";
        mainContent.style.pointerEvents = "auto";
    } else {
        mainContent.style.opacity = "0.5";
        mainContent.style.pointerEvents = "none";
    }
}

function updateAuthState() {
    if (currentToken) {
        authButtons.hidden = true;
        authUser.hidden = false;
        authEmailDisplay.textContent = currentUser || "User";
        loadRecentAsks();
        loadFaqSuggestions();
    } else {
        authButtons.hidden = false;
        authUser.hidden = true;
        authEmailDisplay.textContent = "";
    }
    updateHomePanel();
    // Re-apply auth lock if we're on a non-home tab
    const activeTab = document.querySelector(".tab[data-tab].active");
    if (activeTab && activeTab.dataset.tab !== "home") {
        applyAuthLock();
    }
}

function openAuthModal() {
    authModal.hidden = false;
    authEmail.focus();
}

function closeAuthModal() {
    authModal.hidden = true;
    authError.hidden = true;
    authForm.reset();
}

authLoginBtn.addEventListener("click", openAuthModal);
closeModalBtn.addEventListener("click", closeAuthModal);
authLogoutBtn.addEventListener("click", () => {
    currentToken = null;
    currentUser = null;
    localStorage.removeItem("pai-token");
    localStorage.removeItem("pai-user");
    updateAuthState();
});

tabLogin.addEventListener("click", () => {
    isLoginMode = true;
    tabLogin.classList.add("active");
    tabRegister.classList.remove("active");
    nameGroup.hidden = true;
    confirmPasswordGroup.hidden = true;
    authName.required = false;
    authConfirmPassword.required = false;
    authSubmitBtn.textContent = "Login";
    authError.hidden = true;
});

tabRegister.addEventListener("click", () => {
    isLoginMode = false;
    tabRegister.classList.add("active");
    tabLogin.classList.remove("active");
    nameGroup.hidden = false;
    confirmPasswordGroup.hidden = false;
    authName.required = true;
    authConfirmPassword.required = true;
    authSubmitBtn.textContent = "Register";
    authError.hidden = true;
});

authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    authError.hidden = true;
    authSubmitBtn.disabled = true;
    authSubmitBtn.textContent = "Processing...";

    try {
        let endpoint, body;
        if (isLoginMode) {
            endpoint = "/auth/login";
            body = new URLSearchParams();
            body.append("username", authEmail.value);
            body.append("password", authPassword.value);
        } else {
            if (authPassword.value !== authConfirmPassword.value) {
                authError.textContent = "Passwords do not match";
                authError.hidden = false;
                authSubmitBtn.disabled = false;
                authSubmitBtn.textContent = "Register";
                return;
            }
            endpoint = "/auth/register";
            body = JSON.stringify({
                name: authName.value,
                email: authEmail.value,
                password: authPassword.value,
                confirm_password: authConfirmPassword.value
            });
        }

        const res = await fetch(`${API_BASE}${endpoint}`, {
            method: "POST",
            headers: isLoginMode ? { "Content-Type": "application/x-www-form-urlencoded" } : { "Content-Type": "application/json" },
            body
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        currentToken = data.access_token;
        currentUser = data.user_name || authEmail.value;
        localStorage.setItem("pai-token", currentToken);
        localStorage.setItem("pai-user", currentUser);
        
        closeAuthModal();
        updateAuthState();
        showToast(isLoginMode ? "Logged in successfully" : "Registered successfully");
    } catch (err) {
        authError.textContent = err.message;
        authError.hidden = false;
    } finally {
        authSubmitBtn.disabled = false;
        authSubmitBtn.textContent = isLoginMode ? "Login" : "Register";
    }
});

updateAuthState();

function setActiveTab(tabName) {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    const tabEl = $(`.tab[data-tab="${tabName}"]`);
    if (tabEl) tabEl.classList.add("active");
    const panel = $(`#panel-${tabName}`);
    if (panel) panel.classList.add("active");
    if (tabName === "home") {
        mainContent.style.display = "none";
    } else {
        mainContent.style.display = "";
        applyAuthLock();
    }
    if (tabName === "files") loadFiles();
}

$$(".tab[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => setActiveTab(tab.dataset.tab));
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

async function apiRequest(endpoint, options = {}) {
    if (!currentToken) {
        openAuthModal();
        throw new Error("No token");
    }

    const headers = { "Authorization": `Bearer ${currentToken}`, ...options.headers };
    let res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });

    // Handle token expiration
    if (res.status === 401) {
        currentToken = null;
        currentUser = null;
        localStorage.removeItem("pai-token");
        localStorage.removeItem("pai-user");
        updateAuthState();
        openAuthModal();
        throw new Error("Session expired. Please log in again.");
    }

    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }

    // 204 No Content — no body to parse
    if (res.status === 204) return null;

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
            startIngestionPoll(result.file_id);
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

/* ── Upload Mode Toggle ────────────────────────────── */

modeFileBtn.addEventListener("click", () => {
    fileUploadSection.hidden = false;
    textUploadSection.hidden = true;
    modeFileBtn.classList.add("active");
    modeTextBtn.classList.remove("active");
});

modeTextBtn.addEventListener("click", () => {
    fileUploadSection.hidden = true;
    textUploadSection.hidden = false;
    modeTextBtn.classList.add("active");
    modeFileBtn.classList.remove("active");
});

function checkTextUploadReady() {
    textUploadBtn.disabled = !textFilenameInput.value.trim() || !textContentInput.value.trim();
}

textFilenameInput.addEventListener("input", checkTextUploadReady);
textContentInput.addEventListener("input", checkTextUploadReady);

textUploadBtn.addEventListener("click", async () => {
    const filename = textFilenameInput.value.trim();
    const content = textContentInput.value;
    if (!filename || !content.trim()) return;

    textUploadBtn.disabled = true;
    uploadProgress.hidden = false;
    uploadResults.innerHTML = "";
    progressFill.style.width = "50%";
    progressText.textContent = `Uploading ${filename}.txt...`;

    const blob = new Blob([content], { type: "text/plain" });
    const file = new File([blob], `${filename}.txt`, { type: "text/plain" });

    const formData = new FormData();
    formData.append("file", file);
    if (tagsInput.value.trim()) formData.append("tags", tagsInput.value.trim());
    if (locationInput.value.trim()) formData.append("location", locationInput.value.trim());

    try {
        const result = await apiRequest("/upload", { method: "POST", body: formData });
        progressFill.style.width = "100%";
        uploadResults.innerHTML += createUploadCard(result, true);
        startIngestionPoll(result.file_id);
        progressText.textContent = "Upload complete!";
        showToast(`${filename}.txt uploaded successfully`);
        setTimeout(() => {
            textFilenameInput.value = "";
            textContentInput.value = "";
            checkTextUploadReady();
            uploadProgress.hidden = true;
            progressFill.style.width = "0%";
        }, 2000);
    } catch (err) {
        uploadResults.innerHTML += createUploadCard({ filename: `${filename}.txt`, error: err.message }, false);
        progressText.textContent = "Upload failed";
        showToast(err.message, "error");
        textUploadBtn.disabled = false;
        checkTextUploadReady();
    }
});

function createUploadCard(data, success) {
    if (success) {
        return `
            <div class="result-card upload-ingest" id="ingest-card-${data.file_id}">
                <div class="result-header">
                    <span class="result-filename">${fileIcon(data.file_type)} ${escapeHtml(data.filename)}</span>
                    <span class="result-badge badge-${data.file_type}">${data.file_type}</span>
                </div>
                <div class="ingest-status ingest-processing">
                    <div class="spinner-sm"></div><span>Ingesting&hellip;</span>
                </div>
            </div>
        `;
    }
    return `
        <div class="result-card upload-error">
            <div class="result-header">
                <span class="result-filename">${escapeHtml(data.filename)}</span>
                <span class="result-badge" style="background:var(--error-light);color:var(--error)">Error</span>
            </div>
            <div class="result-text">${escapeHtml(data.error)}</div>
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
                    <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <p>No results found for &ldquo;${escapeHtml(query)}&rdquo;</p>
                </div>
            `;
            return;
        }

        searchResults.innerHTML = data.results.map(createSearchCard).join("");
        if (data.cached) showToast("Results served from cache");
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
                <span class="result-filename">${fileIcon(r.file_type)} ${escapeHtml(r.filename)}</span>
                <span class="result-score">${score}% match</span>
            </div>
            <div class="result-text">${escapeHtml(text)}</div>
            <div class="result-meta">
                <span class="result-badge badge-${r.file_type}">${r.file_type}</span>
                ${r.location ? `<span>&#8203;${escapeHtml(r.location)}</span>` : ""}
                ${r.tags ? `<span>${r.tags.map(t => escapeHtml(t)).join(", ")}</span>` : ""}
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
                <div class="answer-label">AI Answer</div>
                <div class="answer-text">${escapeHtml(data.answer)}</div>
                <div class="answer-meta">
                    ${data.cached ? "Served from cache" : (data.reasoning_used ? "Claude reasoning used" : "Direct retrieval")}
                    &middot; ${data.sources.length} source(s)
                </div>
            </div>
        `;

        if (data.sources.length > 0) {
            html += `<div class="sources-label">Sources</div>`;
            html += data.sources.map(createSearchCard).join("");
        }

        askResults.innerHTML = html;
        loadRecentAsks(); // reload list
    } catch (err) {
        askResults.innerHTML = `<div class="result-card upload-error"><div class="result-text">${err.message}</div></div>`;
    }
}

/* ── FAQ & Recent Asks ─────────────────────────────── */

function triggerPredefinedQuestion(q) {
    if (!currentToken) {
        openAuthModal();
        return;
    }
    document.querySelector('.tab[data-tab="ask"]').click(); // switch tab
    askInput.value = q;
    doAsk();
}

faqList.addEventListener("click", (e) => {
    if (e.target.tagName === "LI") {
        triggerPredefinedQuestion(e.target.textContent);
    }
});

recentAsksList.addEventListener("click", (e) => {
    if (e.target.tagName === "LI" && !e.target.classList.contains("empty-state-list")) {
        triggerPredefinedQuestion(e.target.textContent);
    }
});

async function loadRecentAsks() {
    if (!currentToken) return;
    try {
        const asks = await apiRequest("/recent-asks");
        if (asks && asks.length > 0) {
            recentAsksList.innerHTML = asks.map(a => `<li>${escapeHtml(a)}</li>`).join("");
        } else {
            recentAsksList.innerHTML = `<li class="empty-state-list">No questions asked recently. Ask something!</li>`;
        }
    } catch (err) {
        console.error("Failed to load recent asks:", err);
    }
}

async function loadFaqSuggestions() {
    if (!currentToken) return;
    try {
        const suggestions = await apiRequest("/files/faq-suggestions");
        if (suggestions && suggestions.length > 0) {
            faqList.innerHTML = suggestions.map(q => `<li>${escapeHtml(q)}</li>`).join("");
        } else {
            faqList.innerHTML = `<li class="empty-state-list">Upload files to see personalized suggestions.</li>`;
        }
    } catch (err) {
        faqList.innerHTML = `<li class="empty-state-list">Could not load suggestions.</li>`;
        console.error("Failed to load FAQ suggestions:", err);
    }
}

/* ── Ingestion Status Polling ──────────────────────────── */

function startIngestionPoll(fileId) {
    // Cancel any existing poll for this file
    if (_ingestionPolls.has(fileId)) {
        clearInterval(_ingestionPolls.get(fileId));
    }

    let attempts = 0;
    const MAX_ATTEMPTS = 48; // 48 × 2.5s = 2 minutes

    const id = setInterval(async () => {
        attempts++;
        try {
            const data = await apiRequest(`/files/${fileId}/status`);
            updateIngestionCard(fileId, data.status, data.error_message);

            if (data.status === "complete" || data.status === "failed") {
                clearInterval(id);
                _ingestionPolls.delete(fileId);
                if (data.status === "complete") loadFaqSuggestions();
            }
        } catch {
            // stop polling on auth errors / network failure
            clearInterval(id);
            _ingestionPolls.delete(fileId);
        }

        if (attempts >= MAX_ATTEMPTS) {
            clearInterval(id);
            _ingestionPolls.delete(fileId);
            updateIngestionCard(fileId, "failed", "Timed out waiting for ingestion");
        }
    }, 2500);

    _ingestionPolls.set(fileId, id);
}

function updateIngestionCard(fileId, status, errorMsg) {
    const card = document.getElementById(`ingest-card-${fileId}`);
    if (!card) return;
    const statusEl = card.querySelector(".ingest-status");
    if (!statusEl) return;

    if (status === "complete") {
        card.classList.replace("upload-ingest", "upload-success");
        statusEl.className = "ingest-status ingest-complete";
        statusEl.innerHTML = `Ingestion complete &mdash; file is searchable`;
    } else if (status === "failed") {
        card.classList.replace("upload-ingest", "upload-error");
        statusEl.className = "ingest-status ingest-failed";
        const errText = errorMsg ? `: ${escapeHtml(errorMsg)}` : "";
        statusEl.innerHTML = `Ingestion failed${errText}
            <button class="btn btn-retry" onclick="retryIngestion('${fileId}')">&#8635; Retry</button>`;
    }
}

async function retryIngestion(fileId) {
    try {
        await apiRequest(`/files/${fileId}/retry`, { method: "POST" });
        const card = document.getElementById(`ingest-card-${fileId}`);
        if (card) {
            card.classList.replace("upload-error", "upload-ingest");
            const statusEl = card.querySelector(".ingest-status");
            if (statusEl) {
                statusEl.className = "ingest-status ingest-processing";
                statusEl.innerHTML = `<div class="spinner-sm"></div><span>Retrying…</span>`;
            }
        }
        startIngestionPoll(fileId);
        showToast("Re-queued for ingestion");
    } catch (err) {
        showToast(err.message, "error");
    }
}

/* ── Helpers ───────────────────────────────────────── */

function fileIcon(type) {
    const labels = { pdf: "PDF", docx: "DOC", text: "TXT", image: "IMG" };
    const label = labels[type] || "FILE";
    return `<span class="file-type-icon file-type-${type || 'file'}">${label}</span>`;
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    let html = div.innerHTML;
    // Parse markdown bold (**text**) into HTML strong tags
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    return html;
}

/* ── Files ────────────────────────────────────────────── */

filesRefreshBtn.addEventListener("click", loadFiles);

async function loadFiles() {
    filesList.innerHTML = `<div class="loading"><div class="spinner"></div> Loading files...</div>`;
    try {
        const files = await apiRequest("/files");
        if (!files || files.length === 0) {
            filesList.innerHTML = `
                <div class="empty-state">
                    <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                    <p>No files uploaded yet. Go to Upload to add some!</p>
                </div>`;
            return;
        }
        filesList.innerHTML = files.map(createFileCard).join("");
    } catch (err) {
        filesList.innerHTML = `<div class="result-card upload-error"><div class="result-text">${err.message}</div></div>`;
    }
}

function createFileCard(f) {
    const date = f.created_at
        ? new Date(f.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })
        : "—";
    const tags = f.tags?.length ? `<span>Tags: ${f.tags.map(t => escapeHtml(t)).join(", ")}</span>` : "";
    const location = f.location ? `<span>Location: ${escapeHtml(f.location)}</span>` : "";
    const caption = f.caption
        ? `<div class="result-text file-caption">${escapeHtml(f.caption.slice(0, 140))}${f.caption.length > 140 ? "…" : ""}</div>`
        : "";
    const safeFilename = f.filename.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    return `
        <div class="result-card file-card" data-file-id="${f.id}">
            <div class="result-header">
                <span class="result-filename">${fileIcon(f.file_type)} ${escapeHtml(f.filename)}</span>
                <span class="result-badge badge-${f.file_type}">${f.file_type}</span>
            </div>
            ${caption}
            <div class="result-meta">
                <span>${date}</span>
                ${location}
                ${tags}
            </div>
            <div class="file-actions">
                <button class="btn btn-file-view" onclick="viewFile('${f.id}')">View</button>
                <button class="btn btn-file-delete" onclick="deleteFile('${f.id}', '${safeFilename}')">Delete</button>
            </div>
        </div>`;
}

async function viewFile(fileId) {
    try {
        const data = await apiRequest(`/files/${fileId}/view`);
        window.open(data.url, "_blank", "noopener,noreferrer");
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function deleteFile(fileId, filename) {
    if (!confirm(`Delete "${filename}"?\nThis will permanently remove the file, its embeddings, and all data. This cannot be undone.`)) return;
    try {
        await apiRequest(`/files/${fileId}`, { method: "DELETE" });
        const card = filesList.querySelector(`.file-card[data-file-id="${fileId}"]`);
        if (card) {
            card.style.transition = "opacity 0.3s, transform 0.3s";
            card.style.opacity = "0";
            card.style.transform = "translateX(12px)";
            setTimeout(() => {
                card.remove();
                if (!filesList.querySelector(".file-card")) {
                    filesList.innerHTML = `
                        <div class="empty-state">
                            <svg class="empty-icon" xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                            <p>No files uploaded yet. Go to Upload to add some!</p>
                        </div>`;
                }
            }, 300);
        }
        showToast(`“${filename}” deleted`);
    } catch (err) {
        showToast(err.message, "error");
    }
}
/* ══════════════════════════════════════════════════════════
   HOME PANEL — CTA updates & interactive demo
   ══════════════════════════════════════════════════════════ */

/* ── Home CTA state ────────────────────────────────────── */

function updateHomePanel() {
    const homeStartBtn = $("#home-get-started-btn");
    const homeFooterBtn = $("#home-footer-cta-btn");
    if (!homeStartBtn) return;

    const arrowSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>`;

    if (currentToken) {
        homeStartBtn.innerHTML = `Go to Upload ${arrowSvg}`;
        homeStartBtn.onclick = () => setActiveTab("upload");
        if (homeFooterBtn) {
            homeFooterBtn.textContent = "Go to My Files";
            homeFooterBtn.onclick = () => setActiveTab("files");
        }
    } else {
        homeStartBtn.innerHTML = `Get Started ${arrowSvg}`;
        homeStartBtn.onclick = openAuthModal;
        if (homeFooterBtn) {
            homeFooterBtn.textContent = "Sign In / Register";
            homeFooterBtn.onclick = openAuthModal;
        }
    }
}

/* ── Interactive demo ──────────────────────────────────── */

const _demoData = {
    confident: [
        {
            keywords: ["revenue", "forecast", "q3", "q4", "q1", "q2", "sales", "profit", "financial"],
            message: "Based on your **Q3 Financial Report**, the revenue forecast is **$2.4M** — a 12% YoY increase. Key growth drivers: new product launch (+$400K) and expanded enterprise contracts (+$800K).",
            source: "Q3_Financial_Report.pdf · Section 3.2 — Revenue Projections"
        },
        {
            keywords: ["action items", "action item", "meeting", "agenda", "tasks", "todo", "to-do"],
            message: "From your **Meeting Notes (Oct 14)**, I found 5 action items:\n1. Finalize design mockups by Friday — Alice\n2. Review API integration contracts — Bob\n3. Update client-facing dashboard — Team\n4. Schedule sprint retrospective\n5. Send weekly stakeholder update",
            source: "Meeting_Notes_Oct14.txt · Action Items section"
        }
    ],
    clarifying: [
        {
            keywords: ["project", "tell me about", "about the"],
            message: "I found references to **3 different projects** in your documents. Which one did you mean?",
            options: ["Project Alpha (product dev)", "Project Beta (client work)", "Q4 Initiative (internal)"]
        },
        {
            keywords: ["last week", "last month", "recently", "recent", "what happened", "update"],
            message: "To give you the most accurate answer, could you clarify what area you're interested in?",
            options: ["Sales & revenue", "Team activities", "Project milestones", "All recent updates"]
        }
    ],
    fallback: {
        message: "Your question is broad and could match several documents. To give you a precise, citation-backed answer — could you clarify?",
        options: ["Which document are you referring to?", "What time period?", "What specific aspect?"]
    }
};

function _classifyDemo(query) {
    const q = query.toLowerCase();
    for (const item of _demoData.confident) {
        if (item.keywords.some((k) => q.includes(k))) return { type: "confident", item };
    }
    for (const item of _demoData.clarifying) {
        if (item.keywords.some((k) => q.includes(k))) return { type: "clarifying", item };
    }
    return { type: "clarifying", item: _demoData.fallback };
}

function runHomeDemo(query) {
    const chatArea = $("#demo-chat-area");
    if (!chatArea || !query.trim()) return;

    chatArea.innerHTML = `
        <div class="demo-bubble demo-bubble-user">
            <div class="demo-bubble-inner">${escapeHtml(query)}</div>
        </div>
        <div class="demo-bubble demo-bubble-ai-wrap" id="_demo-thinking">
            <div class="demo-thinking-wrap">
                <div class="demo-thinking-dots"><span></span><span></span><span></span></div>
            </div>
        </div>`;

    const checkSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
    const questionSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`;

    setTimeout(() => {
        const thinkEl = $("#_demo-thinking");
        if (!thinkEl) return;
        const { type, item } = _classifyDemo(query);

        if (type === "confident") {
            thinkEl.outerHTML = `
                <div class="demo-bubble demo-bubble-ai-wrap">
                    <div class="demo-bubble-answer">
                        <div class="demo-bubble-label">${checkSvg} Confident — answered from your documents</div>
                        <div class="demo-bubble-content">${escapeHtml(item.message).replace(/\n/g, "<br>")}</div>
                        <div class="demo-bubble-source">📄 ${escapeHtml(item.source)}</div>
                    </div>
                </div>`;
        } else {
            const chips = (item.options || [])
                .map((o) => `<button class="demo-option-chip" onclick="this.classList.add('selected')">${escapeHtml(o)}</button>`)
                .join("");
            thinkEl.outerHTML = `
                <div class="demo-bubble demo-bubble-ai-wrap">
                    <div class="demo-bubble-clarify">
                        <div class="demo-bubble-label">${questionSvg} Needs clarification — asking instead of guessing</div>
                        <div class="demo-bubble-content">${escapeHtml(item.message)}</div>
                        <div class="demo-option-chips">${chips}</div>
                        <div class="demo-clarify-note">In the real app, you'd click an option or rephrase your question — the AI never hallucinates.</div>
                    </div>
                </div>`;
        }
    }, 1100);
}

/* ── Demo event listeners ──────────────────────────────── */

const _demoInput = $("#demo-input");
const _demoSendBtn = $("#demo-send-btn");

if (_demoSendBtn) {
    _demoSendBtn.addEventListener("click", () => {
        if (_demoInput) runHomeDemo(_demoInput.value);
    });
}

if (_demoInput) {
    _demoInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") runHomeDemo(_demoInput.value);
    });
}

$$(".demo-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
        const q = chip.dataset.demo;
        if (_demoInput) _demoInput.value = q;
        runHomeDemo(q);
    });
});

$("#home-explore-btn")?.addEventListener("click", () => {
    $("#home-demo")?.scrollIntoView({ behavior: "smooth", block: "start" });
});