// Asset picker for the ArkSD Asset node.
//
// A ComfyUI combo cannot render thumbnails, and picking the wrong asset wastes
// real money on a bad generation. This extension attaches a custom dropdown
// with a thumbnail, name, type badge and id per row, plus a large preview of
// the selection.

import { app } from "../../../scripts/app.js";
import {
	debounce,
	el,
	fetchJson,
	setWidgetValue,
	widgetValue,
} from "./arksd_common.js";

const NODE_NAME = "ArkSD_Asset";

// Cache asset lists per filter tuple so reopening the node does not re-fetch.
// The server also caches for 5 minutes; this only avoids the round trip.
const CACHE_TTL_MS = 5 * 60 * 1000;
const listCache = new Map();

function cacheKey(node) {
	return [
		widgetValue(node, "ak_sk_name", ""),
		widgetValue(node, "group_type", "AIGC"),
		widgetValue(node, "project_name", "default"),
		widgetValue(node, "group_id", ""),
		widgetValue(node, "asset_type", "Image"),
	].join("|");
}

function readCache(key) {
	const hit = listCache.get(key);
	if (!hit) return null;
	if (Date.now() - hit.at > CACHE_TTL_MS) {
		listCache.delete(key);
		return null;
	}
	return hit.items;
}

function typeBadge(type) {
	const colors = { Image: "#3b82f6", Video: "#a855f7", Audio: "#10b981" };
	return el("span", {
		className: "arksd-badge",
		style: {
			background: colors[type] || "#6b7280",
			color: "#fff",
			borderRadius: "4px",
			padding: "0 4px",
			fontSize: "10px",
			marginLeft: "4px",
		},
	}, type || "?");
}

function thumbnail(asset, size) {
	// `contain` keeps the whole asset visible inside the square box instead of
	// cropping it the way `cover` does.
	const box = {
		width: `${size}px`,
		height: `${size}px`,
		objectFit: "contain",
		borderRadius: "4px",
		background: "#ffffff",
		flex: "0 0 auto",
	};
	if (asset.type === "Image") {
		return el("img", { src: asset.url, style: box, loading: "lazy" });
	}
	if (asset.type === "Video") {
		return el("video", {
			src: asset.url,
			style: box,
			muted: "",
			preload: "metadata",
			playsinline: "",
		});
	}
	return el("div", {
		style: { ...box, display: "flex", alignItems: "center", justifyContent: "center" },
	}, "♪");
}

function buildPicker(node) {
	const container = el("div", {
		className: "arksd-asset-picker",
		style: { display: "flex", flexDirection: "column", gap: "6px", padding: "4px", width: "100%" },
	});

	const search = el("input", {
		type: "text",
		placeholder: "Filter assets by name…",
		style: { width: "100%", padding: "2px 6px" },
	});

	const list = el("div", {
		style: {
			display: "flex",
			flexDirection: "column",
			gap: "2px",
			maxHeight: "260px",
			overflowY: "auto",
			border: "1px solid #333",
			borderRadius: "4px",
		},
	});

	const preview = el("div", {
		style: { display: "flex", gap: "8px", alignItems: "center", minHeight: "24px" },
	});

	const status = el("div", {
		style: { fontSize: "11px", color: "#aaa", minHeight: "14px" },
	});

	container.append(search, list, preview, status);

	let assets = [];

	function renderPreview(asset) {
		preview.replaceChildren();
		if (!asset) {
			preview.append(el("span", { style: { color: "#777", fontSize: "12px" } }, "No asset selected"));
			return;
		}
		preview.append(thumbnail(asset, 96));
		preview.append(
			el("div", { style: { display: "flex", flexDirection: "column", gap: "2px" } }, [
				el("div", { style: { fontSize: "12px", fontWeight: "600" } }, [asset.name || "(unnamed)", typeBadge(asset.type)]),
				el("div", { style: { fontSize: "10px", color: "#888", wordBreak: "break-all" } }, asset.id),
			])
		);
	}

	function renderList() {
		const query = search.value.trim().toLowerCase();
		const selected = widgetValue(node, "asset_id", "");
		const rows = assets
			.filter((asset) => !query || (asset.name || "").toLowerCase().includes(query) || asset.id.toLowerCase().includes(query))
			.map((asset) => {
				const row = el(
					"div",
					{
						style: {
							display: "flex",
							alignItems: "center",
							gap: "8px",
							padding: "4px",
							cursor: "pointer",
							background: asset.id === selected ? "#2a3f5f" : "transparent",
							borderRadius: "4px",
						},
						onclick: () => {
							setWidgetValue(node, "asset_id", asset.id);
							renderPreview(asset);
							renderList();
						},
					},
					[
						thumbnail(asset, 48),
						el("div", { style: { display: "flex", flexDirection: "column", overflow: "hidden" } }, [
							el("div", { style: { fontSize: "12px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, [
								asset.name || "(unnamed)",
								typeBadge(asset.type),
							]),
							el("div", { style: { fontSize: "10px", color: "#888", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" } }, asset.id),
						]),
					]
				);
				return row;
			});
		list.replaceChildren(...rows);
		if (!rows.length) {
			list.append(
				el("div", { style: { padding: "6px", fontSize: "11px", color: "#a66", lineHeight: "1.5" } }, [
					"No assets found. Check:",
					el("br"),
					"1. project_name (usually `default`)",
					el("br"),
					"2. your AK/SK belongs to the account that received the authorization",
					el("br"),
					"3. the IAM user has Ark asset permissions",
					el("br"),
					"For an asset another account authorized to you, use ArkSD Asset (Manual ID).",
				])
			);
		}
		const current = assets.find((asset) => asset.id === selected);
		renderPreview(current || null);
	}

	async function refresh(force = false) {
		const key = cacheKey(node);
		const cached = force ? null : readCache(key);
		if (cached) {
			assets = cached;
			renderList();
			status.textContent = assets.length
				? `Loaded ${assets.length} assets (cached).`
				: "0 assets (cached). See the checklist below.";
			status.style.color = assets.length ? "#aaa" : "#a66";
			return;
		}
		status.textContent = "Loading assets…";
		try {
			const payload = await fetchJson("/arksd/assets", {
				ak_sk_name: widgetValue(node, "ak_sk_name", ""),
				group_type: widgetValue(node, "group_type", "AIGC"),
				project_name: widgetValue(node, "project_name", "default"),
				group_id: widgetValue(node, "group_id", ""),
				asset_type: widgetValue(node, "asset_type", "Image"),
				refresh: force ? 1 : 0,
			});
			assets = payload.items || [];
			listCache.set(key, { at: Date.now(), items: assets });
			renderList();
			status.textContent = assets.length
				? `Loaded ${assets.length} assets.`
				: "0 assets. See the checklist below.";
			status.style.color = assets.length ? "#aaa" : "#a66";
		} catch (error) {
			assets = [];
			renderList();
			status.textContent = `Asset list failed: ${error.message}`;
		}
	}

	search.addEventListener("input", debounce(renderList, 150));

	// Re-fetch when a filter changes. The widgets are plain combos, so hook
	// their callbacks without replacing them.
	for (const name of ["ak_sk_name", "group_type", "project_name", "group_id", "asset_type"]) {
		const widget = node.widgets?.find((w) => w.name === name);
		if (!widget) continue;
		const original = widget.callback;
		widget.callback = function (...args) {
			const result = original?.apply(this, args);
			refresh(false);
			return result;
		};
	}

	const refreshWidget = node.widgets?.find((w) => w.name === "refresh");
	if (refreshWidget) {
		const original = refreshWidget.callback;
		refreshWidget.callback = function (...args) {
			const result = original?.apply(this, args);
			if (refreshWidget.value) refresh(true);
			return result;
		};
	}

	refresh(false);
	return container;
}

app.registerExtension({
	name: "arksd.asset",
	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;
		const original = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const result = original?.apply(this, arguments);
			this.addDOMWidget("arksd_asset_picker", "div", buildPicker(this), { serialize: false });
			return result;
		};
	},
});
