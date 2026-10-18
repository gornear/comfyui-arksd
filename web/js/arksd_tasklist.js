// Task list for the ArkSD Task List node.
//
// This is a pure UI node: it has no sockets and never enters the ComfyUI
// execution queue, so it keeps refreshing and cancelling while a generation is
// running. All work happens over HTTP against the backend routes.
//
// Polling only touches this node's own DOM. It never calls setDirtyCanvas, so
// a 10 second refresh does not repaint the graph.

import { app } from "../../../scripts/app.js";
import { el, fetchJson, mediaSize, widgetValue } from "./arksd_common.js";

const NODE_NAME = "ArkSD_TaskList";
const POLL_MS = 10000;

const STATUS_COLORS = {
	queued: "#f59e0b",
	running: "#3b82f6",
	succeeded: "#10b981",
	failed: "#ef4444",
	cancelled: "#6b7280",
	expired: "#6b7280",
};

function badge(status) {
	return el(
		"span",
		{
			style: {
				background: STATUS_COLORS[status] || "#6b7280",
				color: "#fff",
				borderRadius: "4px",
				padding: "0 5px",
				fontSize: "10px",
				fontWeight: "600",
			},
		},
		status || "?"
	);
}

function buildTaskList(node) {
	const container = el("div", {
		className: "arksd-tasklist",
		style: { display: "flex", flexDirection: "column", gap: "6px", padding: "4px", width: "100%" },
	});

	const autoRefresh = el("input", { type: "checkbox" });
	const statusSelect = el("select", {}, [
		el("option", { value: "all" }, "all"),
		el("option", { value: "queued" }, "queued"),
		el("option", { value: "running" }, "running"),
		el("option", { value: "succeeded" }, "succeeded"),
		el("option", { value: "failed" }, "failed"),
	]);
	const pageSizeSelect = el("select", {}, [
		el("option", { value: "10" }, "10"),
		el("option", { value: "20", selected: "" }, "20"),
		el("option", { value: "50" }, "50"),
	]);

	const refreshButton = el("button", { type: "button" }, "Refresh");
	const status = el("div", { style: { fontSize: "11px", color: "#aaa", minHeight: "14px" } });
	const list = el("div", {
		style: { display: "flex", flexDirection: "column", gap: "6px", maxHeight: "420px", overflowY: "auto" },
	});

	const toolbar = el("div", { style: { display: "flex", gap: "6px", alignItems: "center", flexWrap: "wrap" } }, [
		refreshButton,
		el("label", { style: { display: "flex", gap: "4px", alignItems: "center", fontSize: "11px" } }, [
			autoRefresh,
			"auto 10s",
		]),
		el("label", { style: { display: "flex", gap: "4px", alignItems: "center", fontSize: "11px" } }, ["status", statusSelect]),
		el("label", { style: { display: "flex", gap: "4px", alignItems: "center", fontSize: "11px" } }, ["size", pageSizeSelect]),
	]);

	container.append(toolbar, status, list);

	// Track video elements so they can be released before a re-render.
	const activeVideos = new Set();

	function releaseVideos() {
		for (const video of activeVideos) {
			try {
				video.pause();
				video.removeAttribute("src");
				video.load();
			} catch (error) {
				// A element already detached; nothing to release.
			}
		}
		activeVideos.clear();
	}

	function media(task) {
		const content = task.content || {};
		// Landscape tasks get a 16:9 box and portrait tasks a 9:16 box, so the
		// row height follows the video's real shape.
		const size = mediaSize(task.ratio);
		const box = {
			width: `${size.width}px`,
			height: `${size.height}px`,
			objectFit: "contain",
			borderRadius: "4px",
			background: "#111",
			flex: "0 0 auto",
		};
		if (content.video_url) {
			const video = el("video", {
				src: content.video_url,
				style: box,
				muted: "",
				preload: "metadata",
				playsinline: "",
				controls: "",
			});
			activeVideos.add(video);
			return video;
		}
		if (content.last_frame_url) {
			return el("img", { src: content.last_frame_url, style: box, loading: "lazy" });
		}
		return el("div", {
			style: { ...box, display: "flex", alignItems: "center", justifyContent: "center", color: "#555" },
		}, "—");
	}

	async function copyId(taskId) {
		try {
			await navigator.clipboard.writeText(taskId);
			status.textContent = `Copied ${taskId}`;
		} catch (error) {
			status.textContent = `Copy failed: ${taskId}`;
		}
	}

	async function cancelTask(taskId, rowStatus) {
		rowStatus.textContent = "Cancelling…";
		try {
			await fetchJson(`/arksd/tasks/${encodeURIComponent(taskId)}/cancel`, {
				api_key_name: widgetValue(node, "api_key_name", ""),
			});
			status.textContent = `Cancelled ${taskId}`;
		} catch (error) {
			status.textContent = `Cancel failed: ${error.message}`;
		}
		// Refresh immediately so the row reflects the new state.
		await refresh();
	}

	function renderCard(task) {
		const taskId = task.id || "";
		const rowStatus = el("span", { style: { fontSize: "10px", color: "#f59e0b" } });
		const actions = el("div", { style: { display: "flex", gap: "6px", alignItems: "center" } });

		const idLine = el(
			"div",
			{
				style: { fontSize: "11px", cursor: "pointer", textDecoration: "underline dotted" },
				title: "Click to copy the task id",
				onclick: () => copyId(taskId),
			},
			taskId
		);

		if (task.status === "queued") {
			const cancelButton = el("button", { type: "button" }, "Cancel");
			cancelButton.addEventListener("click", (event) => {
				event.stopPropagation();
				cancelTask(taskId, rowStatus);
			});
			actions.append(cancelButton);
		}
		actions.append(rowStatus);

		const details = el("div", {
			style: {
				display: "flex",
				flexDirection: "column",
				gap: "1px",
				overflow: "hidden",
				justifyContent: "center",
				flex: "1 1 auto",
			},
		}, [
			el("div", { style: { display: "flex", gap: "6px", alignItems: "center" } }, [badge(task.status), idLine]),
			el("div", { style: { fontSize: "10px", color: "#999" } }, [
				task.model || "",
				` ${task.resolution || ""}`,
				` ${task.ratio || ""}`,
				task.duration ? ` ${task.duration}s` : "",
				task.seed !== undefined && task.seed !== null ? ` seed=${task.seed}` : "",
			]),
			el("div", { style: { fontSize: "10px", color: "#777" } }, task.created_at
				? new Date(task.created_at * 1000).toLocaleString()
				: ""),
			actions,
		]);

		return el(
			"div",
			{
				style: {
					display: "flex",
					gap: "8px",
					padding: "6px",
					border: "1px solid #2a2a2a",
					borderRadius: "4px",
					// The row grows with the media, so portrait rows are tall and
					// landscape rows are short.
					alignItems: "stretch",
				},
			},
			[media(task), details]
		);
	}

	async function refresh() {
		status.textContent = "Loading tasks…";
		try {
			const payload = await fetchJson("/arksd/tasks", {
				api_key_name: widgetValue(node, "api_key_name", ""),
				status: statusSelect.value,
				page_num: 1,
				page_size: pageSizeSelect.value,
			});
			releaseVideos();
			const items = payload.items || [];
			list.replaceChildren(...items.map(renderCard));
			if (!items.length) {
				list.append(el("div", { style: { fontSize: "12px", color: "#888", padding: "6px" } }, "No tasks found."));
			}
			status.textContent = `${items.length} of ${payload.total ?? items.length} tasks.`;
		} catch (error) {
			status.textContent = `Task list failed: ${error.message}`;
		}
	}

	let timer = null;

	function stopPolling() {
		if (timer) clearInterval(timer);
		timer = null;
	}

	function startPolling() {
		stopPolling();
		timer = setInterval(() => {
			// Skip work while the tab is in the background.
			if (document.hidden) return;
			refresh();
		}, POLL_MS);
	}

	refreshButton.addEventListener("click", () => refresh());
	statusSelect.addEventListener("change", () => refresh());
	pageSizeSelect.addEventListener("change", () => refresh());
	autoRefresh.addEventListener("change", () => {
		if (autoRefresh.checked) startPolling();
		else stopPolling();
	});

	node.arksdStopPolling = stopPolling;
	node.arksdRefresh = refresh;

	refresh();
	return container;
}

app.registerExtension({
	name: "arksd.tasklist",
	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;

		const originalCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const result = originalCreated?.apply(this, arguments);
			this.addDOMWidget("arksd_tasklist", "div", buildTaskList(this), { serialize: false });
			return result;
		};

		const originalRemoved = nodeType.prototype.onRemoved;
		nodeType.prototype.onRemoved = function () {
			this.arksdStopPolling?.();
			return originalRemoved?.apply(this, arguments);
		};
	},
});
