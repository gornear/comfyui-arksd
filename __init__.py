# ArkSD - Volcengine Ark Seedance 2.x video generation nodes for ComfyUI.

import logging

LOGGER = logging.getLogger("arksd")

WEB_DIRECTORY = "./web"

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

try:
    import httpx  # noqa: F401
except ImportError:  # pragma: no cover - only hit on a broken install
    LOGGER.error(
        "[ArkSD] the 'httpx' package is missing. Install the dependencies with "
        "'pip install -r custom_nodes/comfyui-arksd/requirements.txt' and restart ComfyUI."
    )
    raise

try:
    from .nodes.nodes_asset import ArkSDAsset, ArkSDAssetManual

    NODE_CLASS_MAPPINGS["ArkSD_Asset"] = ArkSDAsset
    NODE_DISPLAY_NAME_MAPPINGS["ArkSD_Asset"] = "ArkSD Asset"
    NODE_CLASS_MAPPINGS["ArkSD_AssetManual"] = ArkSDAssetManual
    NODE_DISPLAY_NAME_MAPPINGS["ArkSD_AssetManual"] = "ArkSD Asset (Manual ID)"
except ImportError as exc:  # pragma: no cover - only hit outside ComfyUI
    LOGGER.debug("[ArkSD] asset node not registered: %s", exc)

try:
    from .nodes.nodes_video import (
        ArkSDSeedance20,
        ArkSDSeedance20Fast,
        ArkSDSeedance20Mini,
        ArkSDSeedance25,
    )

    NODE_CLASS_MAPPINGS.update(
        {
            "ArkSD_Seedance25": ArkSDSeedance25,
            "ArkSD_Seedance20": ArkSDSeedance20,
            "ArkSD_Seedance20Fast": ArkSDSeedance20Fast,
            "ArkSD_Seedance20Mini": ArkSDSeedance20Mini,
        }
    )
    NODE_DISPLAY_NAME_MAPPINGS.update(
        {
            "ArkSD_Seedance25": "ArkSD Seedance 2.5",
            "ArkSD_Seedance20": "ArkSD Seedance 2.0",
            "ArkSD_Seedance20Fast": "ArkSD Seedance 2.0 Fast",
            "ArkSD_Seedance20Mini": "ArkSD Seedance 2.0 Mini",
        }
    )
except ImportError as exc:  # pragma: no cover - only hit outside ComfyUI
    LOGGER.debug("[ArkSD] generation nodes not registered: %s", exc)

try:
    from .nodes.nodes_draft import ArkSDDraftToVideo
    from .nodes.nodes_task import ArkSDQueryTask, ArkSDTaskList

    NODE_CLASS_MAPPINGS.update(
        {
            "ArkSD_DraftToVideo": ArkSDDraftToVideo,
            "ArkSD_QueryTask": ArkSDQueryTask,
            "ArkSD_TaskList": ArkSDTaskList,
        }
    )
    NODE_DISPLAY_NAME_MAPPINGS.update(
        {
            "ArkSD_DraftToVideo": "ArkSD Draft to Video",
            "ArkSD_QueryTask": "ArkSD Query Task",
            "ArkSD_TaskList": "ArkSD Task List",
        }
    )
except ImportError as exc:  # pragma: no cover - only hit outside ComfyUI
    LOGGER.debug("[ArkSD] task nodes not registered: %s", exc)

try:
    from .nodes.routes import register_routes

    register_routes()
except (ImportError, AttributeError) as exc:  # pragma: no cover - only outside ComfyUI
    LOGGER.debug("[ArkSD] HTTP routes not registered: %s", exc)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
