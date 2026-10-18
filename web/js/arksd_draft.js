// Draft mode linkage for the ArkSD Seedance 2.5 node.
//
// Ark rejects any resolution other than 480p while draft mode is on, and only
// accepts 1080p when rendering the final video from a draft task. The backend
// already forces 480p, but leaving the widget showing 1080p makes the node
// look like it will produce a 1080p preview. This extension keeps the widget
// honest by setting it to 480p and locking it while draft is enabled.

import { app } from "../../../scripts/app.js";

const NODE_NAME = "ArkSD_Seedance25";
const DRAFT_RESOLUTION = "480p";

function widget(node, name) {
	return node.widgets?.find((w) => w.name === name);
}

function applyDraftState(node) {
	const draftWidget = widget(node, "draft");
	const resolutionWidget = widget(node, "resolution");
	if (!draftWidget || !resolutionWidget) return;

	const draftOn = Boolean(draftWidget.value);
	if (draftOn) {
		resolutionWidget.value = DRAFT_RESOLUTION;
	}
	// ComfyUI disables a widget's control when `disabled` is set; keeping the
	// stored value means turning draft off restores nothing, so remember it.
	resolutionWidget.disabled = draftOn;
	if (resolutionWidget.options) {
		resolutionWidget.options.disabled = draftOn;
	}
}

app.registerExtension({
	name: "arksd.draft",
	async beforeRegisterNodeDef(nodeType, nodeData) {
		if (nodeData.name !== NODE_NAME) return;

		const originalCreated = nodeType.prototype.onNodeCreated;
		nodeType.prototype.onNodeCreated = function () {
			const result = originalCreated?.apply(this, arguments);

			const draftWidget = widget(this, "draft");
			if (!draftWidget) return result;

			const previous = draftWidget.callback;
			draftWidget.callback = (...args) => {
				const value = previous?.apply(draftWidget, args);
				applyDraftState(this);
				return value;
			};
			applyDraftState(this);
			return result;
		};

		// Restore the correct widget state when a saved workflow is loaded.
		const originalConfigure = nodeType.prototype.onConfigure;
		nodeType.prototype.onConfigure = function () {
			const result = originalConfigure?.apply(this, arguments);
			applyDraftState(this);
			return result;
		};
	},
});
