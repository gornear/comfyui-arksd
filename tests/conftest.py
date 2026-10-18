import sys
from pathlib import Path

# Make sure "nodes" resolves to this package's nodes/ directory, not the
# ComfyUI root's nodes.py module when pytest is run from a nested cwd.
PKG_ROOT = Path(__file__).resolve().parent.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

# The node modules import comfy_api, which lives in the ComfyUI root. Walk up
# until we find it so the tests work regardless of where the package is
# installed.
for parent in PKG_ROOT.parents:
    if (parent / "comfy_api").is_dir():
        if str(parent) not in sys.path:
            sys.path.append(str(parent))
        break
