"""The one colony dome both renderers are measured on.

A planet big enough that its field is hundreds of pixels across, so the shell's detail level and
rim falloff are actually resolved. Numbers only - both the Python capture and the native fixture
read this file, so neither can drift from the other.
"""
from __future__ import annotations

PLANET = (0.0, 6000.0, 0.0)          # lifted clear of the map plane, like the shield fixture
RADIUS = 900.0
DOME_RADIUS = RADIUS * 1.04 + 48.0   # render/planet_building_geometry.py::planet_shield_fields
STRENGTH = 1.0                       # a full field: the top stop of the renderer's strength ramp
HIT_STRENGTH = 0.5                   # the frame after a loss, when the dome pulses
CAMERA = dict(target=PLANET, distance=2600.0, pitch=22.0, yaw=10.0)
# The window's projection is handed degrees where bgfx wants radians, so it frames everything at
# about 54 per cent of the intended size; equal framing is this much further back. The dome is
# measured on shape and brightness, never on an exact pixel overlay.
NATIVE_DISTANCE = 2600.0 * 1.36
