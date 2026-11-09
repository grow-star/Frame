#!/usr/bin/env python3
"""
roof_systems/modbit/modbit_categories.py — the category ids the MODBIT package OWNS (FRAME v106.4).

THE SECOND ROOF-SYSTEM PACKAGE. Mirrors wood_shake_categories structurally (Migration Plan Amendment A2 §1):
core owns the vocabulary every roof system can use; each package owns its own ids and registers them here, at
import. MODBIT owns exactly ONE id, its field covering, and declares it USES none of core's — see USES below
for why each candidate is left out rather than declared and unemitted.

Light on purpose: it imports only the registry, so the bridge's shared boot helper can load it on every page
(page 3's carrier paths never import the geometry). BRIDGE 3: registration by import side effect.
"""
from shared_category_registry import register_package_categories

SYSTEM_ID = "modbit"

# The field covering, DECLARED (Package Contract §1 item 6). Core reads it through
# shared_category_registry.field_category_id() and never names it.
#
# ONE field line, and it carries the WHOLE system — base sheet AND cap sheet (Joseph, 2026-11-01: "The entire
# system (base and cap sheet for MODBIT) is included"). That settles the one-ply-or-two question AT THIS LINE:
# base + cap is what is scoped, and Mule-Hide's two-ply SA build-up (MH-MB-WFT06) is a 20-year-warranty
# UPGRADE argument, not the default. ISO board is scoped separately on the SINGLE-PLY systems (EPDM, TPO)
# only, so MODBIT owns no substrate id.
FIELD_CATEGORY_ID = "MODBIT_FIELD_RR"

# FRAME v106.6 — the patch is OWNED, not shared, and that is the Finding 4 test applied honestly: a patch
# is made OF the membrane, so a MODBIT patch and a TPO patch are different materials whose lines must NOT
# merge. Sharing the id would merge them. (Counterflashing is the opposite case — metal, no system in its
# text, must merge — which is why it is in the SHARED tier and not here.)
PATCH_CATEGORY_ID = "MODBIT_PATCH"

OWNS = (FIELD_CATEGORY_ID, PATCH_CATEGORY_ID)

# USES names the core ids THIS package's engine actually emits, and nothing it does not. A declared id that is
# never emitted reads as coverage and provides none — "a guard with no receipt is a claim" (entry 120).
#
# FRAME v106.5: DRIP_EDGE, now that the engine emits it. The 12" wall leg needs no id of its own — it is
# field membrane and rides on the id MODBIT already OWNS (Joseph: "into field SQ").
#   * NOT FIELD_TEAROFF. Measured: no package emits a tear-off line and the assembly does not either — a
#     Yager full replacement produces 13 lines and none is FIELD_TEAROFF. Tear-off lives on the CARRIER side
#     only. Declaring it here because MODBIT's `BIRMV` exists in Xactimate would be declaring an id nothing
#     emits (see modbit_scope_expansion's header).
#   * NOT STEP_FLASH, and that is the point of the leg: on a membrane the wall is NOT flashed with a
#     separate metal item, so the shake-side id would be the wrong one. The metal that TERMINATES the leg is
#     a later build.
# Note wood shake declares two ids it does not emit (FIELD_TEAROFF, FIELD_COVERING). That is pre-existing
# looseness, logged here rather than copied.
USES = ("BOX_VENT", "COUNTERFLASHING", "DRIP_EDGE", "PIPE_JACK_FLASH", "POWER_VENT",
        "SKYLIGHT_UNIT", "TURBINE_VENT", "UNMAPPED")

# registry_fingerprint(OWNS), pinned. It moves only when THIS package's ids change; adding another package
# never moves another package's hash (A2 §5.1) — which is why WOOD_SHAKE_CATEGORY_HASH is untouched by this
# build. The COMPOSITE hash does move, because the composite is every package's ids together.
MODBIT_CATEGORY_HASH = "b0fe2de344d72b2232c76d6460c6f86e29f2a5ac07ec6f2c3ca7ef1f2837a627"

register_package_categories(SYSTEM_ID, owns=OWNS, uses=USES, expected_hash=MODBIT_CATEGORY_HASH,
                            field_category=FIELD_CATEGORY_ID)

# The package's words (labels, carrier vocabulary), registered from their own module, imported HERE so the
# bridge's one boot-helper line still loads everything on every page (bridge 3).
import modbit_content  # noqa: E402,F401  (registers with core/registry/package_content.py)
