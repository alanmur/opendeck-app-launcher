// Property inspector for the App Launch action.
// Shared options (language, colour mode, scale, labels) are stored by the
// plugin backend in OpenDeck's global settings; the chosen app is stored in
// this key's settings when the user presses OK.

const DEFAULT_OPTIONS = { lang: "", mode: "full", color: "#FFFFFFFF", scale: 100, renderLabels: true };

let websocket = null;
let actionInfo = null;
let options = { ...DEFAULT_OPTIONS };
let keySettings = {};
let apps = [];
let selectedId = null;
let currentThumb = "";

const $ = (id) => document.getElementById(id);

function connectElgatoStreamDeckSocket(inPort, inPropertyInspectorUUID, inRegisterEvent, inInfo, inActionInfo) {
	actionInfo = JSON.parse(inActionInfo);
	keySettings = actionInfo.payload?.settings ?? {};
	showCurrentApp();

	websocket = new WebSocket("ws://localhost:" + inPort);
	websocket.onopen = () => {
		websocket.send(JSON.stringify({ event: inRegisterEvent, uuid: inPropertyInspectorUUID }));
		toPlugin({ request: "hello" });
	};
	websocket.onmessage = (event) => {
		const msg = JSON.parse(event.data);
		if (msg.event === "sendToPropertyInspector") handlePluginMessage(msg.payload ?? {});
		else if (msg.event === "didReceiveSettings") {
			keySettings = msg.payload?.settings ?? {};
			showCurrentApp();
		}
	};
}

function toPlugin(payload) {
	websocket?.send(
		JSON.stringify({ event: "sendToPlugin", action: actionInfo.action, context: actionInfo.context, payload }),
	);
}

function handlePluginMessage(p) {
	switch (p.type) {
		case "hello":
			// A configured key shows its own options; the shared ones only seed new keys.
			options = { ...DEFAULT_OPTIONS, ...(p.options ?? {}), ...(p.keyOptions ?? {}) };
			if (!options.lang) options.lang = normalizeLanguage(p.systemLanguage) ?? "en";
			currentThumb = p.thumb ?? "";
			showOptions();
			showCurrentApp();
			break;
		case "apps":
			apps = p.apps ?? [];
			selectedId = apps.some((a) => a.id === keySettings.app?.id) ? keySettings.app.id : null;
			renderList();
			break;
		case "applied":
			keySettings = p.settings;
			currentThumb = p.thumb ?? "";
			showCurrentApp();
			closeModal();
			break;
		case "error":
			showError(p.message);
			$("ok").disabled = !selectedId;
			break;
	}
}

function showError(message) {
	$("error").textContent = message ? "Error: " + message : "";
	$("error").classList.toggle("hidden", !message);
	if (message) $("list-status").textContent = message;
}

// ---- current key -------------------------------------------------------

function showCurrentApp() {
	const app = keySettings.app;
	$("current-name").textContent = app ? app.name : "None selected";
	$("current-name").classList.toggle("muted", !app);
	$("current-name").title = app ? app.id : "";
	const thumb = app && currentThumb;
	$("current-icon").classList.toggle("hidden", !thumb);
	if (thumb) $("current-icon").src = thumb;
}

// ---- shared options ----------------------------------------------------

function isValidColor(value) {
	return /^#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i.test(value.trim());
}

function showOptions() {
	$("lang").value = options.lang;
	updateLanguageName();
	document.querySelector(`input[name="mode"][value="${options.mode}"]`).checked = true;
	$("color").value = options.color;
	$("scale").value = options.scale;
	document.querySelector(`input[name="labels"][value="${options.renderLabels ? "render" : "title"}"]`).checked = true;
	updateColorControls();
	updateScaleLabel();
}

function updateLanguageName() {
	const name = languageName($("lang").value);
	$("lang-name").textContent = name ?? ($("lang").value.trim() ? "Unknown language" : "");
	$("lang").classList.toggle("invalid", !name && !!$("lang").value.trim());
}

function updateColorControls() {
	const custom = options.mode === "custom";
	$("color").disabled = !custom;
	$("swatch").classList.toggle("disabled", !custom);
	const valid = isValidColor($("color").value);
	$("color").classList.toggle("invalid", custom && !valid);
	$("swatch").firstElementChild.style.background = valid ? $("color").value.trim() : "transparent";
}

function updateScaleLabel() {
	$("scale-value").textContent = $("scale").value + "%";
}

// Re-render this key with the current app and options, if an app is chosen.
function reapply() {
	const app = keySettings.app;
	if (!app) return;
	if (options.mode === "custom" && !isValidColor(options.color)) return;
	toPlugin({ request: "apply", app: { id: app.id, path: app.path }, options });
}

let saveTimer = null;
function saveOptions() {
	clearTimeout(saveTimer);
	saveTimer = setTimeout(() => {
		toPlugin({ request: "saveOptions", options });
		reapply();
	}, 300);
}

function wireOptions() {
	$("lang").addEventListener("input", () => {
		updateLanguageName();
		const norm = normalizeLanguage($("lang").value);
		if (norm) {
			options.lang = norm;
			saveOptions();
		}
	});
	$("lang").addEventListener("change", () => {
		const norm = normalizeLanguage($("lang").value);
		if (norm) $("lang").value = norm;
		updateLanguageName();
	});

	document.querySelectorAll('input[name="mode"]').forEach((radio) =>
		radio.addEventListener("change", () => {
			options.mode = radio.value;
			updateColorControls();
			saveOptions();
		}),
	);

	$("color").addEventListener("input", () => {
		updateColorControls();
		if (isValidColor($("color").value)) {
			options.color = $("color").value.trim().toUpperCase();
			saveOptions();
		}
	});

	// The native picker is RGB only, so keep the alpha from the text field.
	$("swatch").addEventListener("click", () => {
		const hex = options.color.replace("#", "");
		const full = hex.length <= 4 ? [...hex].map((c) => c + c).join("") : hex;
		$("color-picker").value = "#" + full.slice(0, 6);
		$("color-picker").click();
	});
	$("color-picker").addEventListener("input", () => {
		const hex = options.color.replace("#", "");
		const full = hex.length <= 4 ? [...hex].map((c) => c + c).join("") : hex;
		const alpha = full.length === 8 ? full.slice(6) : "FF";
		options.color = ($("color-picker").value + alpha).toUpperCase();
		$("color").value = options.color;
		updateColorControls();
		saveOptions();
	});

	$("scale").addEventListener("input", () => {
		options.scale = Number($("scale").value);
		updateScaleLabel();
		saveOptions();
	});

	document.querySelectorAll('input[name="labels"]').forEach((radio) =>
		radio.addEventListener("change", () => {
			options.renderLabels = radio.value === "render";
			saveOptions();
		}),
	);
}

// ---- application picker ------------------------------------------------

function openModal() {
	if (options.mode === "custom" && !isValidColor(options.color)) {
		showError("Enter a valid custom colour (e.g. #10901080) first.");
		return;
	}
	showError("");
	apps = [];
	selectedId = null;
	$("search").value = "";
	$("app-list").innerHTML = "";
	$("list-status").textContent = "Loading applications…";
	$("ok").disabled = true;
	$("modal").classList.remove("hidden");
	$("search").focus();
	toPlugin({ request: "getApps", lang: options.lang, mode: options.mode, color: options.color });
}

function closeModal() {
	$("modal").classList.add("hidden");
}

function renderList() {
	const query = $("search").value.trim().toLowerCase();
	const list = $("app-list");
	list.innerHTML = "";
	const shown = apps.filter((a) => !query || a.name.toLowerCase().includes(query) || a.id.toLowerCase().includes(query));
	for (const app of shown) {
		const li = document.createElement("li");
		li.setAttribute("role", "option");
		li.dataset.id = app.id;
		li.setAttribute("aria-selected", app.id === selectedId);
		const img = document.createElement("img");
		img.src = app.thumb || "";
		img.alt = "";
		const text = document.createElement("span");
		text.textContent = app.name;
		const id = document.createElement("span");
		id.className = "id";
		id.textContent = app.id;
		text.appendChild(id);
		li.append(img, text);
		list.appendChild(li);
	}
	$("list-status").textContent = `${shown.length} of ${apps.length} applications`;
	$("ok").disabled = !selectedId;
	list.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}

function select(id) {
	selectedId = id;
	for (const li of $("app-list").children) li.setAttribute("aria-selected", li.dataset.id === id);
	$("app-list").querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
	$("ok").disabled = !id;
}

function confirmSelection() {
	const app = apps.find((a) => a.id === selectedId);
	if (!app) return;
	$("ok").disabled = true;
	$("list-status").textContent = "Applying…";
	toPlugin({ request: "apply", app: { id: app.id, path: app.path }, options });
}

function wireModal() {
	$("select-app").addEventListener("click", openModal);
	$("cancel").addEventListener("click", closeModal);
	$("ok").addEventListener("click", confirmSelection);
	$("search").addEventListener("input", renderList);

	$("app-list").addEventListener("click", (e) => {
		const li = e.target.closest("li");
		if (li) select(li.dataset.id);
	});
	$("app-list").addEventListener("dblclick", (e) => {
		const li = e.target.closest("li");
		if (li) {
			select(li.dataset.id);
			confirmSelection();
		}
	});

	document.addEventListener("keydown", (e) => {
		if ($("modal").classList.contains("hidden")) return;
		if (e.key === "Escape") closeModal();
		else if (e.key === "Enter" && selectedId) confirmSelection();
		else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
			e.preventDefault();
			const items = [...$("app-list").children];
			const i = items.findIndex((li) => li.dataset.id === selectedId);
			const next = items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))];
			if (next) select(next.dataset.id);
		}
	});
}

document.addEventListener("DOMContentLoaded", () => {
	showOptions();
	wireOptions();
	wireModal();
});
