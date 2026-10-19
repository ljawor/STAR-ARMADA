
import os, sys, pathlib
sys.path.insert(0, ".")
import game.core
from render.asset_registry import AssetResolver, AssetError
APP = pathlib.Path("build/s09-dist/STAR ARMADA.app/Contents")
for label, root in [("Frameworks (_MEIPASS)", APP/"Frameworks"), ("Resources", APP/"Resources")]:
    try:
        r = AssetResolver(root)
        print(f"{label}: OK bindings={len(r._bindings)} manifests={len(r._manifests)}")
    except AssetError as exc:
        print(f"{label}: AssetError {exc.code} {exc}")
