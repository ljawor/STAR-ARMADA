# Support orders, boarding and construction spacing

Status: **implemented and verified on `feat/planet-colonies-satellites`**, extending PR #40; awaiting merge, not packaged. Full headless suite: **766 tests passed**. Real Cocoa SDL/OpenGL support-order diagnostics passed at 1280×800 and 1024×768, including exhaustive crew-cost labels, actual repair billing, fighter discovery/avoidance, cancellation and immutable rendering. Independent support-order review passed.

## Approved rules

### Boarding

- All target shields must be down to attempt boarding. A disabled engine, weapon or life-support subsystem is **no longer required**.
- Existing ownership, source capability, range, detection and crew-resistance checks remain. Planetary satellites still must be destroyed rather than boarded.
- A successful capture restores life-support health to **at least 10% of its maximum**, preserving any higher existing health. Failed or interrupted attempts provide no repair.
- This does not resurrect crew. The separate safe crew-replenishment admission threshold remains unchanged.

### Engineer / builder repair

- Real engineer/constructor ships can receive an **explicit repair order** for one owned ship, fighter squadron or station at a time. Colony ships do not gain engineer repair capability.
- Repair restores hull and all damaged subsystems, but not crew. Abandoned owned hulls may have equipment repaired without becoming staffed automatically.
- Repair consumes **credits and materials over time**, based on actual repaired damage. Healthy targets, invalid targets, out-of-range work and resource-starved work cannot create free repairs or charge for nonexistent repair.
- Target/source ownership changes, destruction, loss of operation or replacement orders end the mission.
- Targets are owned, not allied or hostile.

### Repair docks

- Docks repair **ships and fighter squadrons only**, never stations or planetary terrain.
- A station needing equipment repair must use an engineer order or another explicitly eligible repair source.

### Construction spacing

- Trade stations require **1,500 units center-to-center** from other trade stations. Pending paid trade construction also reserves spacing; the rule is not limited to a single player.
- New stations, including planetary satellites, require **3,000 units center-to-center** from a live enemy command center. Allied command centers do not create this exclusion.
- Distances exactly at the limit are allowed. Both limits remain configurable.
- Existing stations are not removed, and ship/fighter production at existing yards is not blocked by these placement rules.
- Placement previews must not reveal hidden enemy command-center locations. Simulation acceptance remains authoritative, with generic failure feedback for hidden physical restrictions.

### Crew-cost display

- Every ship/fighter build entry displays required crew, alongside the other costs. Crew requirements must reflect the actual build data and remain readable at the supported diagnostic screen sizes.

### Automatic fighter exploration

- Fighters can be ordered to automatically explore unexplored map regions until given another order.
- This is automatic exploration, not a manually specified two-point patrol.
- Fighters avoid **detected enemies** and continue exploring elsewhere. Hidden enemy positions must not influence route choices.
- Exploration reveals terrain through actual movement and normal sensors, not direct artificial map discovery.
- Exploration orders, route state and repairs must continue deterministically across precise saves/restores and serialized commands.

## Proposed initial repair tuning

Repair speed, service range and resource prices are configurable balance values, not further gameplay approvals. Initial implementation proposal: **20 total health points per second**, **0.2 credits and 0.1 materials per point actually repaired**, with **400 units** of service reach beyond the combined hull radii. Staffing and repair modifiers apply once. Life support receives deterministic repair priority so equipment rescue remains possible.

## Acceptance requirements

- Incremental failing-then-passing simulation regressions for boarding admission, capture support floors, repair authorization/payment/interruption, repair-dock target filtering, spacing boundaries and hidden-placement privacy.
- Fighter exploration must visibly increase explored cells through manager ticks, avoid detected threats, remain invariant to hidden-enemy mutations and survive exact restored continuation.
- Player controls must emit serialized intent without spending before simulation consumption.
- Real SDL/OpenGL tests must verify repair/explore input, crew-cost labels, control cancellation, panel containment and read-only rendering at 1280×800 and 1024×768.
- Independent review, the serialized full suite, compilation and diff checks precede commit/push. Updating the branch does not itself merge or package the feature.
