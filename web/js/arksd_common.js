// Shared helpers for the ArkSD frontend extensions.

const { api } = window.comfyAPI?.api ?? {};

/**
 * Fetch JSON from one of this package's backend routes.
 * Throws when the server reports an { error } payload.
 */
export async function fetchJson(path, params = {}) {
	const query = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value !== undefined && value !== null) query.set(key, String(value));
	}
	const url = query.toString() ? `${path}?${query}` : path;
	const response = await api.fetchApi(url);
	const payload = await response.json().catch(() => ({}));
	if (payload?.error) throw new Error(payload.error);
	if (!response.ok) throw new Error(`HTTP ${response.status}`);
	return payload;
}

/** Build an element tree. Props starting with "on" become listeners. */
export function el(tag, props = {}, children = []) {
	const node = document.createElement(tag);
	for (const [key, value] of Object.entries(props)) {
		if (key === "style" && typeof value === "object") {
			Object.assign(node.style, value);
		} else if (key.startsWith("on") && typeof value === "function") {
			node.addEventListener(key.slice(2).toLowerCase(), value);
		} else if (key === "className") {
			node.className = value;
		} else if (value !== undefined && value !== null) {
			node.setAttribute(key, value);
		}
	}
	for (const child of [].concat(children)) {
		if (child == null) continue;
		node.append(typeof child === "string" ? document.createTextNode(child) : child);
	}
	return node;
}

/** Coalesce rapid calls into one trailing invocation. */
export function debounce(fn, wait = 250) {
	let timer = null;
	return (...args) => {
		clearTimeout(timer);
		timer = setTimeout(() => fn(...args), wait);
	};
}

/** Read a widget value from a node by name. */
export function widgetValue(node, name, fallback = undefined) {
	const widget = node.widgets?.find((w) => w.name === name);
	return widget ? widget.value : fallback;
}

/** Write a widget value on a node by name. */
export function setWidgetValue(node, name, value) {
	const widget = node.widgets?.find((w) => w.name === name);
	if (!widget) return;
	widget.value = value;
	if (widget.callback) widget.callback(value, null, node, null);
}

// Media box sizes for task cards. Landscape and portrait tasks keep 16:9 and
// 9:16 respectively; anything unknown falls back to a square box.
const MEDIA_SIZES = {
	landscape: { width: 176, height: 99 },
	portrait: { width: 99, height: 176 },
	square: { width: 128, height: 128 },
};

/** Pick a media box for a task from its `ratio` field (e.g. "16:9"). */
export function mediaSize(ratio) {
	if (!ratio || ratio === "adaptive") return MEDIA_SIZES.square;
	const parts = String(ratio).split(":");
	if (parts.length !== 2) return MEDIA_SIZES.square;
	const width = Number(parts[0]);
	const height = Number(parts[1]);
	if (!width || !height) return MEDIA_SIZES.square;
	if (width === height) return MEDIA_SIZES.square;
	return width > height ? MEDIA_SIZES.landscape : MEDIA_SIZES.portrait;
}
