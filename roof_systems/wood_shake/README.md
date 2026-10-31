# roof_systems/wood_shake/ — the wood-shake roof-system package

**FRAME v95 / Migration Plan step 3b.** This folder holds everything material-specific to wood shake. The
dependency runs one way: this package imports core, and core never imports this package. Each module here
**registers itself with core at import** (`core/registry/roof_systems.py`). Core then looks the package up by
the profile's `system_id`.

## What is here

**`wood_shake_geometry.py` (3b)** was moved out of `geometry_core.py`. Its code is unchanged except where it is
marked "FRAME v95". It holds:
- the profile constants (`EXPOSURE_IN`, `SHAKE_WIDTH_IN`, `JOINT_OFFSET_IN`, `LATERAL_STEP_IN`) and `EXP` / `STEP`
- `DEFAULT_SHAKE_MEASUREMENTS` and `resolve_shake_measurements`, which now stamps `system_id: "wood_shake"` on
  every profile it resolves. The default lives here, not in core.
- `_profile_units`, together with the CSSB joint-offset assertion
- `TIE_IN_COURSES` / `three_course_extent_ft`, the v90 tie-in authority
- `stair_edges` and `valley_disturbance`, the wood-shake **VALLEY** strategy under Package Contract §1 item 3.
  It returns `(mask, PROPAGATE_TO_RIDGE)` and never an area. Core keeps the grid, the shadow fill, the clip, the
  union, the area integration and the edge-contact measurement.

Only the VALLEY strategy crosses the interface in 3b. Transition bands and appurtenance rects are still core's
bounded branches inside `affected_area()` (3c or later).

## What arrives in 3c

`module2_scope_expansion.py` will be split:
- **Moves here:** `_shakes_per_sq`, `_shake_count`, `_felt_interlayment_ratio`, `CSSB_INTERLAYMENT_STRIP_IN`,
  `SHAKES_PER_SQ`, the item strings ("Wood shake …") and the CSSB citations. The module's own copies of
  `EXPOSURE_IN` / `SHAKE_WIDTH_IN` are removed in the same step.
- **Stays in `core/`:** `ScopeLine` / `M1Interface`, the continuous-run rule, the drip-edge 95 % rule and the
  steep/high tiers.
- **Oracle:** its `SHAKE_FIELD_RR` literals become `profile.field_category_id`.

The work list is generated mechanically by `verification/shared_core_purity_gate.py`, which fails until 3c lands.
That failure is expected.

## Two bridges, both retiring at Migration Plan step 4

1. **Unlabelled profiles.** Every v88–v94 caller passes a profile with no `system_id`. This package declares, at
   `register()`, that it owns such profiles (`claims_unlabelled_profiles=True`). The claim is the package's
   own, and core names no system. A second claimant is refused.
2. **Registration by import.** The package registers when something imports it. An entry point that reaches core
   geometry without importing a package gets an actionable `RoofSystemRegistryError`.

Both retire when `ProjectConfig` supplies the system and the app wires its packages explicitly.

## No compatibility shims (Migration Plan §3.1)

When a rule moves here, its old home is removed in the same build, so one rule never has two homes.
`verification/wood_shake_split_equivalence_regression.py` holds every moved name to a single definition.
