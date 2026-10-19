# CPU campaign-preview entry acceptance

Owned test: tests/test_s07_campaign_preview_entry.py. No production edits, commits or GL context creation.

Final isolated ordered union: campaign-attempt-06-isolated-union.txt, 17 tests PASS. New module contributes three tests (positive preview on/off and two negative controls).

The real MenuStack campaign screen paints CPU hitboxes; a click selects a mission, the real briefing paints its Launch mission hitbox, and a click produces START_MISSION. The unmodified AST-extracted main START_MISSION branch calls the actual extracted start_game. Rendering/audio/input view constructors are doubles from the established factories; real GameManager, recording, presentation initialization, configure_from_settings, configure and AssetResolver execute. The renderer double uses real attach/release ownership and observes real selected mesh/cache revision. This is CPU behavioral entry acceptance only, not actual Renderer construction or a real GL campaign frame.

Preview-on observes pinned rebel:frigate revision 60ba4e69d91f20b3a7cd4c62d88b2b6b4d8625070734e4883c139ff61218a0df (historical manifest filename alliance_frigate.json). Preview-off observes no authored mesh and the legacy cache key. Both initial campaign state digests are 4cbf9ac99eea8a5bdd1a19fd2160994cbedcd18558a437419d13ca68f1101d6b.

Ordering negative: deliberately do not release the old renderer token; actual configure raises its renderers-closed session-boundary refusal before the new renderer constructor. Selection negative: deliberately route the opposite preference; new-renderer observation raises the exact legacy-versus-preview assertion. Neither control mocks configure or resolver output.

All five menu persistence constants are scoped before MenuStack construction. Existing save and migrated progression bytes, settings bytes, absence of balance/replay writes, recording user root, DataStore singleton and resolver singleton restoration are checked/scoped. Menu resources and owned font state are cleaned without display initialization.

Retained attempts:
- 01: fixture failure, mouse hover queried an uninitialized video subsystem; replaced only mouse position lookup with an offscreen CPU value.
- 02: positive assertion exposed a nonexistent alliance:frigate binding; corrected to real rebel:frigate (historical filename retained).
- 03: sentinel preservation exposed legitimate legacy progression migration; perform that migration in isolated root before snapshotting launch invariants.
- 04: three new tests pass.
- 05: 17-test union passes but pre-existing test_campaign_main writes two replay files outside its own fixture. Removed only the two exact replay filenames printed in that attempt, then reran under outer five-path isolation.
- 06: isolated 17-test ordered union passes; existing campaign test replay writes remain inside disposable outer root.

Remaining gap: a naturally entered campaign rendered through the real Renderer on a real GL context, with a captured campaign frame/pixel/revision proof. This CPU suite does not close that gate.
