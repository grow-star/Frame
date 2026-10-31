#!/usr/bin/env python3
"""
roof_systems/wood_shake/wood_shake_categories.py — the category ids the wood-shake package OWNS (FRAME v97).

Migration Plan Amendment A2 §1: the registry is two-tier. Core owns the vocabulary every roof system can use;
each package owns its own ids and registers them here, at import. wood_shake owns exactly ONE id, its
field-covering category. STARTER, RIDGE_CAPS, HIP_CAPS, RIDGE_HIP_CAP, FIELD_FELT, FIELD_TEAROFF and
FIELD_COVERING are concepts every roof system has: they stay core, and this package declares that it USES them.

Light on purpose: it imports only the registry, so the bridge's shared boot helper can load it on every page
(page 3's carrier paths never import the geometry). BRIDGE 3 (Joseph 2026-10-29): registration by import side
effect, retiring at Migration Plan step 4 when ProjectConfig wires packages explicitly.
"""
from shared_category_registry import register_package_categories

SYSTEM_ID = "wood_shake"

# FRAME v98: the field covering, DECLARED (Package Contract §1 item 6). Core reads it through
# shared_category_registry.field_category_id() and never names it.
FIELD_CATEGORY_ID = "SHAKE_FIELD_RR"

OWNS = (FIELD_CATEGORY_ID,)
USES = ("DRIP_EDGE", "FIELD_COVERING", "FIELD_FELT", "FIELD_TEAROFF", "HIP_CAPS", "RIDGE_CAPS",
        "RIDGE_HIP_CAP", "STARTER", "STEEP_CHARGE", "HIGH_SLOPE_CHARGE")

# registry_fingerprint(OWNS), pinned. It moves only when THIS package's ids change; adding another package
# never moves it (A2 §5.1).
WOOD_SHAKE_CATEGORY_HASH = "5ad1863d6977ec41e408c4377ca4c0c4fa10e60d6fb9b0f08b66be317953a605"

register_package_categories(SYSTEM_ID, owns=OWNS, uses=USES, expected_hash=WOOD_SHAKE_CATEGORY_HASH,
                            field_category=FIELD_CATEGORY_ID)

# FRAME v101: the package's words (labels, carrier vocabulary, repair entries, report text) — registered from their
# own module, imported HERE so the bridge's one boot-helper line still loads everything on every page (bridge 3).
import wood_shake_content  # noqa: E402,F401  (registers with core/registry/package_content.py)
