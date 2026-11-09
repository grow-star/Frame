#!/usr/bin/env python3
"""
roof_systems/modbit/modbit_content.py — what the MODBIT package SAYS (FRAME v106.4)
===================================================================================
The words that are modified bitumen's, registered with core/registry/package_content.py so that core's
machinery — the label map, Layer A's matcher — never names this material. Imported by modbit_categories.py,
so the bridge's one boot-helper line loads it on every page.

WHAT THIS MODULE DELIBERATELY DOES NOT REGISTER, and why each omission is a decline rather than a gap:

  * `texts` (sec3_title / method_explanation / felt_interlayment_callout) — NONE. §3 is a REPAIR argument,
    and a membrane facet has no repair scope to argue: patches are ruled out of scope (Joseph, 2026-11-01 —
    "we don't typically argue repairs"), so a MODBIT facet is scoped as a full replacement. There is no
    MODBIT repair argument to state, and inventing one would be writing a carrier argument Joseph has not
    made. The felt callout is a shake concept outright — a membrane has no interlayment. This is the same
    DECLINE as a non-coursed package omitting course_top_ft (v105.4): the package says what it cannot answer,
    and core must omit rather than raise.

  * `repair_entries` — NONE, for the same reason. The authored entries (S-1..S-3) argue detach-and-reset and
    install-only against R&R on a coursed covering; none of that reasoning transfers, and a wrong argument is
    worse than no argument.

So §3 stays wood shake's analysis on a mixed roof — correctly, because wood shake is the only registered
system with a repair argument. v106.4's renderer change must make that an OMISSION, not a raise.
"""
from package_content import CarrierPattern, register_package_content
from modbit_categories import FIELD_CATEGORY_ID, PATCH_CATEGORY_ID, SYSTEM_ID

# ---- the label ------------------------------------------------------------------------------------------
DISPLAY_LABELS = {FIELD_CATEGORY_ID: "Modified bitumen field",
                  # FRAME v106.6: the repair patch. The system IS in the words, deliberately — a patch is
                  # made OF the membrane, and Finding 4's ruling is that FRAME writes the system into the
                  # text whenever the part is, so a MODBIT patch never merges with a TPO one.
                  PATCH_CATEGORY_ID: "Modified bitumen roof patch"}

# ---- Package Contract item 10 — how a carrier writes this material --------------------------------------
# Joseph, binding: "Symbility (Cotality) have similar items but can be named different." So this matches the
# MATERIAL as written in prose, never a selector code.
#
# `field=True` makes this the least specific rule for the system: a carrier line that also names a specific
# component — a tear-off, a flashing, a pipe jack — is that component, not the field. That is what keeps
# "Tear off, haul and dispose of modified bitumen roofing" off the field line without a second pattern here.
#
# "modified bitumen" and "mod bit" only. NOT bare "bitumen": asphalt shingles are bituminous, and a pattern
# matching them would read an asphalt field line as MODBIT. NOT "SBS" or "APP" either — those are modifier
# chemistries Joseph has not ruled on, and a guess here mis-attributes a whole field line.
CARRIER_PATTERNS = (
    CarrierPattern(r"modified\s*bitumen|\bmod\.?\s*bit\b|\bmodbit\b", FIELD_CATEGORY_ID, True, "high", True),
)

register_package_content(
    SYSTEM_ID,
    display_labels=DISPLAY_LABELS,
    carrier_patterns=CARRIER_PATTERNS,
)
