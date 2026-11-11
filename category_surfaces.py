#!/usr/bin/env python3
"""
CATEGORY SURFACES — what each browser category surface lists, from THE category authority (FRAME ARC-06a, B3)
=============================================================================================================
Until ARC-06a, page 3's carrier-line picker (`REGISTRY_28`), its label map (`CAT_LABEL`) and page 2's label map
(`REGISTRY_LABEL`) were LITERAL copies of the registry written into the pages. They were frozen at the wood-shake
vocabulary, so with MODBIT installed the composite registry had four ids no page could show — COUNTERFLASHING,
MODBIT_FIELD_RR, MODBIT_PATCH and SKYLIGHT_UNIT (B3). A carrier's membrane line could not be mapped by hand.

The pages now hold NO category list. They ask the engine once on load (pyodide_bridge.categorySurfaces) and fill
empty containers from this function, which reads only the authorities:
  * the ids         shared_category_registry.REGISTRY — the composite of core and every REGISTERED package (it
                    raises when no package has registered, so a short list never reaches a page);
  * the labels      category_display_names.category_display_name — package content for package ids, core's map
                    for core ids, never blank. A page may WORD a label differently for its own context (page 2
                    says "Box / turtle vent"); that wording is presentation only and can neither add nor remove an
                    id: a page shows exactly the ids listed here, in this order.

Per surface (the same rules registry_all_package_drift_gate judges):
  page3_picker   every composite id, sorted, no duplicates — a user can map ANY carrier line by hand, including the
                 receive-only ids (the v74 rule: "the picker must offer them").
  page3_labels   one non-empty label per picker id.
  page2_ids      the composite MINUS the receive-only ids. Page 2 labels what the engine EMITS; the four v74
                 receive-only categories are carrier-side only and are never emitted by the required scope, so page
                 2 has never labelled them (registry_page_drift_gate's frozen KNOWN_PAGE2_UNLABELLED).
  page2_labels   one non-empty label per page2 id.
Nothing here decides that a category is a SUPPORTED REPAIR OPERATION or a REQUIRED line: it lists vocabulary.
"""
from __future__ import annotations

import shared_category_registry as _R
from category_display_names import category_display_name as _label

# v74: the four RECEIVE-ONLY core ids — recognised on the carrier side, never emitted by the required scope (see
# shared_category_registry's header). Page 2 has never labelled them; page 3's picker offers them. Core vocabulary
# facts, not a material choice. (Moved here from the verification gate's frozen set so the pages and the gate read
# ONE definition.)
RECEIVE_ONLY_IDS = frozenset({"DEBRIS_DISPOSAL", "EQUIPMENT", "FLUE_CAP", "ROOFER_LABOR"})


def category_surfaces() -> dict:
    """The ids and labels each page category surface shows, from the registry of the packages registered NOW."""
    comp = sorted(_R.REGISTRY)                         # raises RegistryWiringError if no package registered
    if len(comp) != len(set(comp)):
        raise ValueError(f"FRAME ARC-06a: the composite registry repeats ids: {comp}")
    labels = {i: str(_label(i)) for i in comp}
    blank = sorted(i for i, v in labels.items() if not v.strip())
    if blank:
        raise ValueError(f"FRAME ARC-06a: categories without a display label: {blank}")
    page2 = [i for i in comp if i not in RECEIVE_ONLY_IDS]
    return {
        "packages": sorted(_R.registered_packages()),
        "composite_hash": _R.composite_registry_hash(),
        "page3_picker": comp,
        "page3_labels": labels,
        "page2_ids": page2,
        "page2_labels": {i: labels[i] for i in page2},
        "receive_only": sorted(RECEIVE_ONLY_IDS & set(comp)),
    }
