"""The ArkSD Asset node.

Picks one asset from the account's Ark asset library and emits it as an
``asset://<id>`` string that the generation nodes accept in their reference
slots.

The asset list is fetched by the frontend extension (``web/js/arksd_asset.js``)
through the ``/arksd/assets`` route, because a ComfyUI combo cannot render
thumbnails. This node only reads the selected id at execution time.
"""

from comfy_api.latest import io

from . import config
from .asset_client import GROUP_TYPES

ASSET_TYPES = ["Image", "Video", "Audio", "All"]


def build_asset_uri(asset_id: str) -> str:
    """Return an ``asset://`` URI for ``asset_id``."""
    asset_id = (asset_id or "").strip()
    if not asset_id:
        raise ValueError("No asset selected. Pick an asset in the ArkSD Asset node.")
    if asset_id.startswith("asset://"):
        return asset_id
    return f"asset://{asset_id}"


class ArkSDAsset(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        names = config.list_ak_sk_names() or ["<none>"]
        return io.Schema(
            node_id="ArkSD_Asset",
            display_name="ArkSD Asset",
            category="api node/ArkSD",
            description=(
                "Pick an asset from your Ark asset library and output it as an "
                "asset:// reference for the Seedance nodes. Requires ak_sk.json."
            ),
            inputs=[
                io.Combo.Input(
                    "ak_sk_name",
                    options=names,
                    tooltip="Which entry of ak_sk.json to use for the asset API.",
                ),
                io.Combo.Input(
                    "group_type",
                    options=[*GROUP_TYPES, "All"],
                    default="AIGC",
                    tooltip="AIGC = virtual avatars, LivenessFace = authorized real-person material.",
                ),
                io.String.Input(
                    "project_name",
                    default="default",
                    optional=True,
                    tooltip=(
                        "Ark project that holds the assets. Authorized assets can live "
                        "in a named project instead of 'default'."
                    ),
                ),
                io.String.Input(
                    "group_id",
                    default="",
                    optional=True,
                    tooltip="Optional asset group id to narrow the list.",
                ),
                io.Combo.Input(
                    "asset_type",
                    options=ASSET_TYPES,
                    default="Image",
                    tooltip="Filter the asset list by media type.",
                ),
                io.Combo.Input(
                    "asset_id",
                    options=[""],
                    default="",
                    tooltip="Selected asset. Populated by the asset picker in the node UI.",
                ),
                io.Boolean.Input(
                    "refresh",
                    default=False,
                    tooltip="Force the asset list to be re-fetched instead of using the 5 minute cache.",
                ),
            ],
            outputs=[io.String.Output("asset", tooltip="asset://<id> reference.")],
        )

    @classmethod
    def execute(
        cls, ak_sk_name, group_type, group_id, asset_type, asset_id, refresh, project_name="default"
    ) -> io.NodeOutput:
        if not (asset_id or "").strip():
            raise config.ConfigError(
                "No asset selected. Pick an asset from the list in ArkSD Asset, then "
                "run the workflow again. For an asset another account authorized to "
                "you, use the ArkSD Asset (Manual ID) node instead."
            )
        return io.NodeOutput(build_asset_uri(asset_id))


class ArkSDAssetManual(io.ComfyNode):
    """Emit an ``asset://`` reference from a typed asset id.

    Ark's asset management API only sees assets owned by your own account; an
    asset another account authorized to you returns NotFound from ListAssets
    and GetAsset. The generation API still accepts it, so the only requirement
    is the id itself. This node is the way in for those assets.
    """

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="ArkSD_AssetManual",
            display_name="ArkSD Asset (Manual ID)",
            category="api node/ArkSD",
            description=(
                "Type an asset id and get an asset:// reference. Use this for "
                "assets another account authorized to you, which the asset list "
                "cannot show."
            ),
            inputs=[
                io.String.Input(
                    "asset_id",
                    default="",
                    tooltip=(
                        "Asset id, for example asset-20261017202759-8x5qv. "
                        "A full asset:// URI is also accepted."
                    ),
                ),
            ],
            outputs=[io.String.Output("asset", tooltip="asset://<id> reference.")],
        )

    @classmethod
    def execute(cls, asset_id="") -> io.NodeOutput:
        if not (asset_id or "").strip():
            raise config.ConfigError(
                "No asset id given. Type the asset id you want to reference."
            )
        return io.NodeOutput(build_asset_uri(asset_id))
