// Editable model dropdown for the ArkSD LLM node.
//
// The model id cannot be a ComfyUI Combo: the option list only exists after an
// API call, while a Combo's options are fixed when the node schema is built.
// This extension keeps the plain text widget (so any id can still be typed) and
// adds a dropdown next to it, populated from /arksd/models on node creation.
//
// Nothing is preselected: the list is a convenience, and the node stays empty
// until the user picks a model or types one.

import { app } from "../../../scripts/app.js";
import { el, fetchJson, widgetValue } from "./arksd_common.js";

const NODE_NAME = "ArkSD_LLM";
const MODEL_CACHE_TTL_MS = 5 * 60 * 1000;

const modelCache = new Map();

function readCache(key) {
	const hit = modelCache.get(key);
	if (!hit) return null;
	if (Date.now() - hit.at > MODEL_CACHE_TTL_MS) {
		modelCache.delete(key);
		return null;
	}
	return hit.items;
}

function buildPicker(node) {
	const container = el("div", {
		style: { display: "flex", flexDirection: "column", gap: "4px", padding: "2px", width: "100%" },
	});

	const select = el("select", {
		style: { width: "100%", padding: "2px" },
	});
	const status = el("div", { style: { fontSize: "11px", color: "#aaa", minHeight: "14px" } });

	container.append(select, status);

	function renderOptions(items) {
		select.replaceChildren();
		select.append(el("option", { value: "" }, items.length ? "— pick a model —" : "— no models —"));

		// Group by domain so video, vision and text models stay readable.
		const byDomain = new Map();
		for (const item of items) {
			const domain = item.domain || "other";
			if (!byDomain.has(domain)) byDomain.set(domain, []);
			byDomain.get(domain).push(item);
		}
		for (const [domain, group] of [...byDomain.entries()].sort()) {
			const groupEl = el("optgroup", { label: domain });
			for (const item of group) {
				groupEl.append(el("option", { value: item.id }, item.id));
			}
			select.append(groupEl);
		}

		const current = widgetValue(node, "model", "");
		select.value = current && items.some((i) => i.id === current) ? current : "";
	}

	async function loadModels(force = false) {
		const key = widgetValue(node, "api_key_name", "");
		if (!key) {
			status.textContent = "Pick an api key to list models.";
			return;
		}
		const cached = force ? null : readCache(key);
		if (cached) {
			renderOptions(cached);
			status.textContent = `${cached.length} models (cached).`;
			return;
		}
		status.textContent = "Loading models…";
		try {
			const payload = await fetchJson("/arksd/models", {
				api_key_name: key,
				refresh: force ? 1 : 0,
			});
			const items = payload.items || [];
			modelCache.set(key, { at: Date.now(), items });
			renderOptions(items);
			status.textContent = items.length
				? `${items.length} models.`
				: "No models returned for this key.";
			status.style.color = items.length ? "#aaa" : "#a66";
		} catch (error) {
			status.style.color = "#a66";
			status.textContent = `Model list failed: ${error.message}`;
		}
	}

	select.addEventListener("change", () => {
		if (!select.value) return;
		const widget = node.widgets?.find((w) => w.name === "model");
		if (!widget) return;
		widget.value = select.value;
		if (widget.callback) widget.callback(widget.value, null, node, null);
	});

	// Reload when the key changes so the list matches the selected credential.
	const keyWidget = node.widgets?.find((w) => w.name === "api_key_name");
	if (keyWidget) {
		const original = keyWidget.callback;
		keyWidget.callback = function (...args) {
			const result = original?.apply(this, args);
			loadModels(false);
			return result;
		};
	}

	loadModels(false);
	return container;
}

app.registerExtension({
	name: "arksd.llm",
	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;
		const original = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const result = original?.apply(this, arguments);
			this.addDOMWidget("arksd_model_picker", "div", buildPicker(this), { serialize: false });
			return result;
		};
	},
});
