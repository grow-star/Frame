#!/usr/bin/env python3
"""
roof_systems/modbit/modbit_scope_expansion.py — MODBIT's scope engine (FRAME v106.4)
====================================================================================
The package's `expand_scope`, as registered with core. Core ASKS the registry for it
(get(system_id).expand_scope) and never imports it by name — bridge 6, retired at v104b.

WHAT IT EMITS: exactly ONE line, the field covering, in SQ.

  Joseph, 2026-11-01: "Measured in SQ — all 3 systems." And: "The entire system (base and cap sheet for
  MODBIT) is included." So one SQ line carries base + cap, and there is no second field line to add.

WHY NO TEAR-OFF LINE, even though MODBIT's tear-off id (`BIRMV`) is captured. MEASURED on this tree: a Yager
full replacement of all 22 roof facets emits 13 lines and **not one of them is FIELD_TEAROFF** — no package
emits it and nothing in the assembly does. Tear-off lives on the CARRIER side only (`carrier_layer_a`'s
`tear\\s*-?\\s*off|remove\\s*roof` rule) and the comparison reads it there. A MODBIT tear-off line would be the
only one of its kind in the required scope, with no counterpart rule on the shake side to compare against.
The house pattern decides this, not the id's availability.

WHY NO EDGE LINES AT ALL, and why that is a decline rather than an oversight. MEASURED: on a Yager
replacement with F10/F11 declared MODBIT, core calls this engine 13 times — twice with facet area
(is_replacement=True) and **11 times with affected_SF == 0.0 and a single Edge** (the non-valley edges of its
two facets: 6 STEPFLASH, 1 RIDGE, 2 RAKE, 2 EAVE). Every one of those 11 returns nothing, for three separate
reasons, none of which is "not got to it yet":

  * EAVE / RAKE -> DRIP_EDGE is system-agnostic metal that MERGES like kind, and the rule that decides it is
    the 95% continuous-run rule. That threshold ALREADY EXISTS IN TWO COPIES — `transition_events.py:144` and
    wood_shake's `module2_scope_expansion.py:55`, the core one carrying a comment that it duplicates the
    other. A third copy here is the failure this codebase keeps collapsing (entry 87; v105.1's five copies of
    the fall basis). The edge rules move to CORE as one copy with two callers, in the build that needs them.
  * STEPFLASH / FLASHING -> the 12" membrane leg (wall LF x 1 ft, into field SQ — Joseph: "The flat roof
    membrane acts as the flashing", so it is field membrane, not a flashing item). AUTO, and it belongs with
    the metal that terminates it, which needs the `counter` and `parapet` Xactimate searches. Shipping the
    leg without its termination would put half a wall treatment in the report.
  * RIDGE -> a membrane has no ridge cap. Yager's L56 is a 33 LF ridge with MODBIT on BOTH sides (measured:
    F10 and F11 share L56, a RIDGE, not a valley), and what caps a continuous run spanning two coverings is
    Joseph's open per-run cap-material question (roadmap item 7). Emitting nothing is right; emitting a
    guess is not.

So on Yager this engine's whole output is F10's and F11's field area. Every quantity that STOPS being billed
because those facets are no longer shake is listed in v106.4's prompt with its number, and the three that are
GAPS rather than corrections are named there and in the ledger.

THE VALLEY DISTURBANCE lives in modbit_geometry.py, and refuses by name: see its docstring.
"""
from scope_contract import (CAP_THRESHOLD, MEMBRANE_LEG_FT,
                            MEMBRANE_PATCH_BANDS, MEMBRANE_SKYLIGHT_CURB_FT, ScopeLine, SYSTEM_BOUNDARY)
# FRAME v106.6d: the cut-back is DERIVED from this package's own declared setback, so the carve and the
# patch read ONE number. Asking the registry rather than importing modbit_geometry directly keeps the single
# source of truth at the declaration, and avoids this module importing its own package's geometry.
from roof_systems import appurtenance_clearance_in as _declared_clearance_in
from shared_category_registry import skylight_operation as _skylight_operation

from modbit_categories import FIELD_CATEGORY_ID, PATCH_CATEGORY_ID, SYSTEM_ID

# The membrane turned up a wall: 12 inches, as one foot, because the field line is in SQ.
WALL_LEG_FT = 1.0
# The edge types that ARE a wall. STEPFLASH is a sidewall the roof runs into; FLASHING is an end wall.
# A PARAPET is neither and is not in this set — a parapet is flashed on both faces and capped on top, which
# is a different detail and a later build.
WALL_EDGE_TYPES = ("STEPFLASH", "FLASHING")
# Where continuous metal runs at the roof's lower and raking edges.
DRIP_EDGE_TYPES = ("EAVE", "RAKE")

# The scope TEXT, which is FRAME's own and not a selector code (Joseph, binding: "Symbility (Cotality) have
# similar items but can be named different"). Deliberately UNQUALIFIED: Xactimate's `BI` "Modified bitumen
# roof" is itself the unqualified item, and the application method (cold adhesive `BIC`, hot mopped `BIM`,
# self-adhering `BISA`) is a profile axis this interface does not carry — M1Interface holds one claim-level
# profile (entry 109), and a per-system profile is its own build. Emitting the unqualified line asserts only
# what the user declared: that this facet is modified bitumen. It does not GUESS a method, which would change
# a priced line.
FIELD_ITEM = "Modified bitumen roof"

# Not CSSB — that authority is wood shake's. A membrane's field quantity rests on the manufacturer's own
# installation instructions for a base-and-cap system; FRAME states the basis without citing a document
# number it has not verified.
FIELD_CITATION = "Manufacturer installation instructions — base and cap sheet system"

# The leg's own description and authority. The text states the DERIVATION — wall LF x 12 inches — so the
# quantity is checkable from the diagram without reading this file, and says in its own words that the
# membrane is the flashing, which is why no separate wall-flashing item appears beside it.
WALL_LEG_ITEM = "Modified bitumen roof — 12″ membrane leg at wall (the membrane IS the flashing)"
WALL_LEG_CITATION = ("Manufacturer 12″ vertical termination — wall LF × 1 ft, billed as field "
                     "membrane, not as a flashing item")

# FRAME v106.3b — THE CROSS-SYSTEM TIE-IN. The membrane does not stop at the boundary: it runs UP the
# neighbouring steep slope and under its first three courses, so the area it covers there is membrane this
# package installs on a surface the flat facet does not contain. The text states the derivation — boundary LF
# × the extent core measured — so the quantity is checkable from the diagram without reading this file.
#
# BILLED AS FIELD SQ, IN ITS OWN ROW, exactly as the 12″ wall leg is (v106.5), and for the same two reasons:
# it is the same material and the same billed item, so it takes the same category id, unit and gate; and it
# is area BEYOND the facet's own, so summing it into the facet row would make the field quantity exceed
# EagleView's facet area with nothing on the page saying why. The aggregation key includes the item text, so
# a distinct description keeps it a traceable row that shares the id. Joseph's open question of 2026-11-01
# was whether this is additional field SQ or a separate transition line; the wall leg settled the same
# question the same way one build earlier, and answering it differently here would put two shapes of the one
# answer in one package.
TIE_IN_ITEM = "Modified bitumen roof — membrane run up the steep slope under the first 3 courses at the system boundary"
TIE_IN_CITATION = ("Mule-Hide MH-MB-WFT06 note 2 / Carlisle U-13E note 1 — membrane extended under the first "
                   "3 courses; boundary LF × the top of the 3rd course of the abutting covering")


# ---- FRAME v106.6: APPURTENANCES ON A MEMBRANE ---------------------------------------------------
# Joseph, 2026-11-04. The whole section rests on one sentence of his, which this codebase already encodes
# twice: "You don't put the IWS around the appurtenances on flat roof surfaces because the flat roof surface
# is a waterproof barrier." The other two instances are `transition_emits_underlayment`, which is literally
# `metal != METAL_MEMBRANE`, and the wall at v106.5, where the membrane IS the flashing and so there is no
# STEP_FLASH. A membrane needs no separate underlayment and no separate flashing ANYWHERE, because it is
# both — so this engine emits NO APPURT_IWS, and the absence is the rule rather than an omission.

CHIMNEY_LEG_ITEM = "Modified bitumen roof — 12″ membrane leg up the chimney chase"
CHIMNEY_LEG_CITATION = ("Manufacturer vertical termination — chase perimeter × 12 in, billed as field "
                        "membrane; the membrane IS the flashing, as at a wall")
SKYLIGHT_LEG_ITEM = "Modified bitumen roof — 4″ membrane leg up the skylight curb"
SKYLIGHT_LEG_CITATION = ("Manufacturer vertical termination — curb perimeter × 4 in (the minimum curb "
                         "height), billed as field membrane")
COUNTERFLASH_ITEM = "Counterflashing"
COUNTERFLASH_CITATION = "mfr — metal lapping the membrane's vertical termination"
PATCH_ITEM_FMT = "Modified bitumen roof patch — {band}"
PATCH_CITATION = ("Repair cut-back: appurtenance footprint + 6 in on all sides, billed per patch by the "
                  "SF band it falls in")
_BAND_TEXT = {15.0: "10–15 SF", 9.0: "5–9 SF", 4.0: "up to 4 SF"}

# The appliance lines. These are the APPLIANCE, not the covering — a turbine vent is a turbine vent whatever
# is under it — so they take CORE's ids and MERGE like kind with the coursed side's, exactly as DRIP_EDGE
# does. MODBIT owns no pipe-jack id on purpose: Joseph, 2026-11-01, "MODBIT has NO special pipe jack
# flashing in Xactimate — it takes the generic one", and declining to own an id is the same mechanism as a
# non-coursed package declining course_top_ft (v105.4).
_APPLIANCE = {
    "PIPE":       ("Pipe-jack flashing", "PIPE_JACK_FLASH", "AUTO"),
    "TURTLE":     ("Turtle / box vent", "BOX_VENT", "AUTO"),
    "TURBINE":    ("Turbine vent", "TURBINE_VENT", "AUTO"),
    "POWER_VENT": ("Power attic vent", "POWER_VENT", "CONFIRM"),
}


# FRAME v106.6g2: shared vocabulary, not a package number. Whether a measurement contradicts a declared
# type is a fact about the TYPE, so both packages ask the type table and answer the same way. Joseph,
# 2026-11-07: "Pershing should give a prompt or warning to confirm the label since the size suggests
# otherwise." A membrane's border is 6in for BOTH flashing methods, so a mislabel costs less here than on a
# coursed roof (where a curb gets 21in) - but a mislabelled item still bills the wrong ITEM, so it still asks.
from appurtenance_types import size_suggests_mislabel as _size_suggests_mislabel
from appurtenance_types import mislabel_citation as _mislabel_citation
from shared_category_registry import user_category_or_unmapped as _user_category_or_unmapped


def _perimeter_ft(a) -> float:
    """The appurtenance's perimeter, or 0.0 when it was never measured. 2(w + h) — a rectangle, because that
    is what the payload carries and what the diagram draws; a round chase would need its own shape and the
    payload has no way to say so yet."""
    w, h = getattr(a, "width_ft", None), getattr(a, "height_ft", None)
    if w is None or h is None:
        return 0.0
    w, h = float(w), float(h)
    if not (w > 0 and h > 0):
        return 0.0
    # FRAME v106.6d — SUBTRACT THE CUT LINE, WHICH IS NOT A WALL.
    # Joseph, 2026-11-05, on the split chimney: "I do want the chimney counterflashing over-bill when
    # splitting a ridge looked at. That's important."
    #
    # EagleView splits one physical chimney that crosses a ridge into one marker per facet. Each marker is a
    # closed rectangle on its own plane, so each hands this function a fourth side lying ON the ridge — and
    # there is no chase wall there. The chase is continuous over the ridge; that side is the cut EagleView
    # made. Measured on Yager: F68 and F67 sum to 23.0036 LF of perimeter for a chase whose real perimeter
    # along the roof is 18.0030, over by 5.0006 = 2 x the 2.50 ft the chimney spans along the ridge.
    #
    # THE CORRECTION LANDS HERE, ON THE PERIMETER, which is exactly the set of lines that bill a wall: the
    # 12in chase leg and the counterflashing. It must NOT reach the cut-back, and does not — `_cutback_SF`
    # grows the footprint and never calls this. The ridge strip IS membrane that gets cut on both planes,
    # once per plane, so three patches for this chimney is right and stays right.
    #
    # Only a LINKED group is corrected. `shared_edge_ft` is 0.0 unless the assembly found this marker a
    # group-mate on an adjacent facet, and the group comes from the user's "Same physical item as…" link on
    # page 2 — the same authority that already decides the flashing dedupe. Two separate chimneys either side
    # of a ridge are corrected by nothing, which is correct: they have four walls each.
    shared = float(getattr(a, "shared_edge_ft", 0.0) or 0.0)
    return max(2.0 * (w + h) - max(shared, 0.0), 0.0)


def _cutback_ft() -> float:
    """The cut-back added to EACH dimension: twice this package's declared setback, because the membrane is
    cut back on BOTH sides of every axis. 2 x 6 in = 1 ft, which is Joseph's formula (w + 1 ft)(h + 1 ft).

    FRAME v106.6d, and it is a correction. v106.6c claimed in a code comment and in its prompt that one
    number fed the carve and the patch; it did not — the carve read the declared 6 in and the patch read a
    separate MEMBRANE_CUTBACK_FT = 1.0. They agreed in value and nothing tied them, so moving one moved only
    its own side, and the check whose text asserted otherwise passed under exactly that mutant. ONE
    declaration now, read here and by core's appurt_rect through the same registry accessor."""
    return 2.0 * _declared_clearance_in(SYSTEM_ID) / 12.0


def _cutback_SF(a) -> float:
    """Joseph's repair cut-back: 12 in onto BOTH dimensions, for 6 in of membrane removed on all sides.
    His worked example is the test — a 2ft x 2ft skylight gives 3ft x 3ft = 9 SF. The quantity INCLUDES the
    appurtenance's own footprint: it is the rectangle that comes out, not a collar with a hole in it."""
    w, h = getattr(a, "width_ft", None), getattr(a, "height_ft", None)
    if w is None or h is None or float(w) <= 0 or float(h) <= 0:
        return 0.0
    cut = _cutback_ft()
    return (float(w) + cut) * (float(h) + cut)


def _patch_bands(sf: float):
    """Which patch bands cover `sf`, largest first — Joseph's "multiple patches", approved 2026-11-04.

    A POINT appurtenance measures 0.0 SF (there is no footprint to grow), and his rule for that case is
    explicit: "the appurtenance flashing plus 1 patch". So zero yields ONE smallest band rather than
    nothing — the only case in this engine where 0.0 is not "emit nothing", and it is a ruling, not a
    fallback."""
    if sf <= 0:
        return [MEMBRANE_PATCH_BANDS[-1]]
    out, rem = [], float(sf)
    biggest = MEMBRANE_PATCH_BANDS[0]
    while rem > biggest:
        out.append(biggest)
        rem -= biggest
    for b in reversed(MEMBRANE_PATCH_BANDS):      # smallest band that still covers the remainder
        if rem <= b:
            out.append(b)
            break
    return out


def _appurtenance_lines(iface):
    """Every line this package emits for the appurtenances on one facet."""
    out, seen = [], set()
    for a in iface.appurts:
        if not a.contacted:
            continue
        gid = a.group if a.group is not None else id(a)
        if gid in seen:
            continue                      # one assembly per physical object, as the coursed side dedupes
        seen.add(gid)
        ty = str(a.type).upper()
        per = _perimeter_ft(a)

        # A DIMENSIONED APPURTENANCE WITH NO DIMENSIONS IS AN ERROR, NEVER A QUIET PARTIAL SCOPE.
        # Without this, a CHIMNEY or SKYLIGHT carrying no measured w/h falls past its own branch (which
        # requires `per > 0`) AND is excluded by name from the user-defined branch below, so it emits the
        # repair patch and NOTHING ELSE: a cut-back with no flashing, which reads on the estimate as a
        # priced answer. That is the exact fault v106.6a was built to delete, and reintroducing it one
        # version later for the undimensioned case would be the same defect wearing a different hat.
        #
        # It cannot fire today, and the guard is here anyway. Page 2 filters user rows through
        # `isUserAppComplete`, which requires positive width AND height for a dimensioned type, and the
        # XML path cannot produce one either because `geometry_core.appurt_rect` raises for a dimensioned
        # type with missing or zero dims. Both doors are shut — but v106.6a exists precisely because a
        # silence that looked unreachable became reachable the moment a second roof system arrived, so the
        # latent case gets a named stop rather than a comment saying it cannot happen.
        #
        # ValueError, not NotImplementedError, and the distinction is load-bearing: NotImplementedError is
        # this codebase's "the package does not answer that yet" (modbit_geometry.valley_disturbance,
        # v106.6a's refusal). This is not an unanswered question, it is impossible input — the same
        # judgment `appurt_rect` makes, so it raises the same type with the same shape of message.
        if ty in ("CHIMNEY", "SKYLIGHT") and per <= 0:
            raise ValueError(
                f"FRAME: a {ty} on a '{SYSTEM_ID}' facet needs a measured footprint to scope its membrane "
                f"leg; got width_ft={getattr(a, 'width_ft', None)!r}, height_ft={getattr(a, 'height_ft', None)!r}. "
                f"The type is authoritative and must not silently become a point: billing the repair patch "
                f"without the leg and counterflashing would be a partial scope. Fix: give the marker its "
                f"width and height on page 2."
            )

        if ty == "CHIMNEY" and per > 0:
            out.append(ScopeLine(CHIMNEY_LEG_ITEM, FIELD_CATEGORY_ID,
                                 round(per * MEMBRANE_LEG_FT / 100.0, 4), "SQ", "AUTO",
                                 CHIMNEY_LEG_CITATION, material_profile_id=SYSTEM_ID))
            # The metal that laps the leg. CONFIRM — it is one of the sidewall control's checkboxes
            # (Joseph, 2026-11-01), and it carries NO system in its text because it is metal and must merge
            # with the coursed side's (Finding 4).
            out.append(ScopeLine(COUNTERFLASH_ITEM, "COUNTERFLASHING", round(per, 2), "LF", "CONFIRM",
                                 COUNTERFLASH_CITATION, material_profile_id=SYSTEM_ID))
        elif ty == "SKYLIGHT" and per > 0:
            out.append(ScopeLine(SKYLIGHT_LEG_ITEM, FIELD_CATEGORY_ID,
                                 round(per * MEMBRANE_SKYLIGHT_CURB_FT / 100.0, 4), "SQ", "AUTO",
                                 SKYLIGHT_LEG_CITATION, material_profile_id=SYSTEM_ID))
            # NO COUNTERFLASHING, and that is Joseph correcting QA on 2026-11-04: "Skylight doesn't get
            # counterflashing… there's not typically room. A skylight curb is minimum 4", so either skylight
            # needs detached & Reset or replaced depending on if there's damage to the skylight." The unit
            # comes off instead — which is a DAMAGE judgement this engine cannot make, so the operation is
            # read from the row and an unstated one is named rather than guessed.
            op = _skylight_operation({"kind_label": "SKYLIGHT",
                                      "operation": getattr(a, "operation", None) or ""})
            out.append(ScopeLine(
                {"RESET": "Skylight — detach and reset",
                 "REPLACE": "Skylight — replace (damaged)"}.get(op, "Skylight — detach and reset, or replace if damaged"),
                "SKYLIGHT_UNIT", 1, "EA", "CONFIRM",
                "no counterflashing fits a 4 in curb; the unit is removed to re-membrane",
                material_profile_id=SYSTEM_ID))
        elif ty in _APPLIANCE:
            item, cat, gate = _APPLIANCE[ty]
            _mis = _size_suggests_mislabel(a.type, a.other_category, a.width_ft, a.height_ft)
            out.append(ScopeLine(item, cat, 1, "EA", "CONFIRM" if _mis else gate,
                                 f"mfr / IRC flashing{_mislabel_citation(_mis)}",
                                 material_profile_id=SYSTEM_ID))
        elif ty not in ("CHIMNEY", "SKYLIGHT"):
            # USER-DEFINED. The coursed side's own branch exists because a user-defined appurtenance that
            # emits nothing is silently dropped (entry 100's defect); the same is true here, so the same
            # answer: the user's own words, their category if they gave a valid one, UNMAPPED otherwise so
            # the comparison routes it to human review.
            label = str(a.other_label).strip() if a.other_label else ""
            _mis = _size_suggests_mislabel(a.type, a.other_category, a.width_ft, a.height_ft)
            # FRAME v106.6g2: VALIDATED, as page2.html says the engine does. This branch used to emit
            # `cat if cat else "UNMAPPED"` - any non-empty string became a category id, so a payload
            # carrying "totally bogus !!" billed a line under that id while the coursed side routed the
            # same payload to UNMAPPED. One copy of the rule now, in the registry that owns the ids.
            out.append(ScopeLine(label or "User-defined appurtenance",
                                 _user_category_or_unmapped(a.other_category), 1, "EA", "CONFIRM",
                                 f"user-defined{_mislabel_citation(_mis)}",
                                 material_profile_id=SYSTEM_ID))

        # THE PATCH — REPAIR ONLY. Joseph, 2026-11-04: "this is only for repairs, not for facet replacement.
        # Replacement facet just gets the SQ." A replaced facet already bills its whole area in SQ, so a
        # patch inside it would be the same membrane twice. This is the same replacement-vs-repair gate the
        # cross-system tie-in and the coursed band use (v106.3b), not a new kind of condition.
        if not bool(getattr(a, "host_replaced", False)):
            for b in _patch_bands(_cutback_SF(a)):
                out.append(ScopeLine(PATCH_ITEM_FMT.format(band=_BAND_TEXT[b]), PATCH_CATEGORY_ID,
                                     1, "EA", "AUTO", PATCH_CITATION, material_profile_id=SYSTEM_ID))
    return out


def _boundary_run_LF(e) -> float:
    """How much of a SYSTEM_BOUNDARY edge this work bills, in LF — core's 95% continuous-run rule
    (scope_contract.CAP_THRESHOLD, the ONE copy since v106.5), identical to the drip edge's treatment a few
    lines below, because both are about continuous material along a run."""
    total = float(e.edge_total_LF)
    contact = float(e.contact_LF)
    if total <= 0:
        return 0.0
    return total if contact >= CAP_THRESHOLD * total else contact


def expand_scope(iface, repair_factor: float = 1.0, **_kwargs):
    """Module 1 interface -> MODBIT scope lines.

    `repair_factor` is accepted for interface compatibility and NEVER APPLIED. It is wood shake's
    repair-count multiplier, fixed at 1.0 in production; a membrane bills area, and an area does not take a
    repair multiplier. Silently ignoring it would be wrong, so it is named here as deliberately unused.

    A membrane is monolithic, so there is no repair/replacement split in the UNIT the way shake splits EA
    (localized repair) from SQ (full slope): any membrane area in scope is re-membraned, and that bills in
    SQ either way. `is_replacement` is therefore not read.

    HOW CORE CALLS THIS, measured, because both edge rules below depend on it: on a mixed Yager replacement
    core calls this engine with facet AREA twice, and with a SINGLE EDGE eleven times. The area calls also
    carry their facet's edges — but every one of them has `contact_LF == 0.0`, so the `contact_LF > 0` guards
    below mean an area call contributes no edge line and nothing is counted twice. (The per-edge dispatch
    itself runs twice, once for the roof-level aggregate and once per structure; those land in different
    outputs, which is how every package avoids doubling.)
    """
    out = []
    sf = float(iface.affected_SF)

    # THE 12" WALL LEG (Joseph, 2026-11-02) — "the flat roof membrane acts as the flashing", so this is NOT
    # a flashing line item: it is FIELD MEMBRANE turned up the wall, wall LF x 1 ft, into the field SQ.
    # AUTO, because geometry knows the wall is there and a proper install turns the membrane up it — there
    # is nothing to ask. Blank is not nothing: Joseph's ruling is that an untouched wall still gets the leg,
    # "12 inch vertical flashing per manufacturer guidelines", because the leg is the manufacturer's FLOOR
    # rather than a guess. What sits ON TOP of it — termination bar, counterflashing — is CONFIRM and is a
    # later build; it needs the `counter` and `parapet` searches.
    leg_sf = sum(float(e.contact_LF) * WALL_LEG_FT for e in iface.edges
                 if e.edge_type in WALL_EDGE_TYPES and float(e.contact_LF) > 0)

    # ---- THE PATCH IS THE LINE FOR ITS OWN AREA (FRAME v106.6c) -------------------------------------
    # Joseph, 2026-11-05, ruling on the double count the v106.6b builder found: "Correct. The cutback is the
    # disturbance." The two halves of that ruling land in two places, and BOTH are needed:
    #
    #   1. the CARVE became the cut-back — modbit declares appurtenance_clearance_in = 6.0, so core's
    #      appurt_rect grows the footprint by 6 in per side instead of wood shake's 21 in;
    #   2. and the AREA so carved bills as the PATCH, not as field SQ — this guard.
    #
    # Shipping only (1) would have left the same defect with matching numbers: the ring of membrane around
    # the appurtenance billed once by the SQ and again inside the patch EA, which carries its own membrane in
    # Xactimate. Joseph, 2026-11-04, on what a repair bills: "the appurtenance flashing plus 1 patch would be
    # fine." Flashing plus one patch. Not flashing, one patch, AND the field.
    #
    # WHY THE GUARD IS "A PATCH WAS BILLED" AND NOT "THIS IS AN APPURTENANCE COMPONENT". The interface does
    # not carry a component type, and inferring one from `appurts` being non-empty would be wrong twice over:
    # an UNCONTACTED marker rides along on an ordinary facet component (informational, bills nothing), and a
    # facet component can carry both a carved area of its own and a marker. The patch lines are the honest
    # signal, because they are emitted by exactly the branch whose area this is: `_patch_lines` runs only for
    # a CONTACTED appurtenance on a NON-replaced host, which is the one case where the carve is the cut-back.
    # Measured on Yager F68 before this guard: MODBIT_FIELD_RR 0.0476 SQ and MODBIT_PATCH 1 EA on the same
    # repair — 4.76 SF of membrane billed twice.
    #
    # ON A REPLACEMENT NOTHING CHANGES. `host_replaced` suppresses the patch, so no patch is billed, so this
    # guard does not fire and the facet's field SQ stands — which is Joseph's other half: "Replacement facet
    # just gets the SQ."
    _appurt_lines = _appurtenance_lines(iface)
    _patch_billed = any(l.category_id == PATCH_CATEGORY_ID for l in _appurt_lines)

    if sf > 0 and not _patch_billed:
        out.append(ScopeLine(FIELD_ITEM, FIELD_CATEGORY_ID, round(sf / 100.0, 4), "SQ", "AUTO",
                             FIELD_CITATION, material_profile_id=SYSTEM_ID))

    # THE LEG IS ITS OWN ROW, not summed into the one above — and that is a deliberate choice, not a
    # mechanical one. It is the SAME category id, the SAME unit and the SAME gate, so it is the same billed
    # item (Joseph: "into field SQ"); the aggregation key includes the ITEM TEXT, so a different description
    # keeps it a separate, traceable row that happens to share the id.
    #
    # WHY NOT SUM IT. The field quantity would then exceed the facet's own area with nothing on the page
    # saying why — 6.8673 SQ against EagleView's 6.6659 — and the first person to notice would be the
    # adjuster. That is the exact shape the CSSB felt-interlayment callout exists to pre-empt on the shake
    # side ("larger than the affected area for this reason, not by error"). Itemising it needs no callout,
    # no new text key, and no explanation anywhere else: the row states its own quantity and authority.
    if leg_sf > 0:
        out.append(ScopeLine(WALL_LEG_ITEM, FIELD_CATEGORY_ID, round(leg_sf / 100.0, 4), "SQ", "AUTO",
                             WALL_LEG_CITATION, material_profile_id=SYSTEM_ID))

    out.extend(_appurt_lines)   # FRAME v106.6c: built above, because the patch decides the field row

    # THE CROSS-SYSTEM TIE-IN (Joseph, 2026-11-01): "MODBIT or whatever flat surface system being installed
    # gets installed with enough material up the steep slope to reach the top portion of the third course of
    # shingle material being installed on the steep slope. Then the roofing system being installed on the
    # steep slope gets installed." Each side does its OWN thing, so this package never asks what is on the
    # other side of the boundary beyond its identity: it declared `tie_in_courses = 3` at registration, core
    # composed that with the OTHER package's own course geometry, and `tie_in_extent_ft` is the answer in feet.
    #
    # A ZERO EXTENT IS A REAL ANSWER AND EMITS NOTHING. It means the covering on the other side declares no
    # course geometry — a membrane-to-membrane boundary, a standing-seam panel — so there is no "top of the
    # 3rd course" to run under. roof_systems.system_boundary_tie_in_ft returns 0.0 rather than raising,
    # precisely so this engine needs no branch for it and no knowledge of which systems exist.
    #
    # AUTO, not CONFIRM: the boundary is not a judgement about existing condition. The claim DECLARED two
    # coverings, both manufacturer details require the membrane under the courses, and geometry gives the run.
    # THE LENGTH BILLED IS THE SAME CONTINUOUS-RUN RULE THE DRIP EDGE USES, from core's one copy: the full
    # run when the work sweeps essentially all of it, otherwise only what it touches. Core hands a boundary
    # edge contact == total today, because every path that builds one claims a whole valley, so this changes
    # no quantity — and that is the point. A membrane tie-in is continuous material along a run, and writing
    # the rule rather than relying on the equality means a future partial-valley selection bills the part
    # instead of silently billing the whole boundary. Entry 124's lesson, applied before it costs anything.
    tie_in_sf = sum(_boundary_run_LF(e) * float(e.tie_in_extent_ft) for e in iface.edges
                    if e.edge_type == SYSTEM_BOUNDARY and float(e.tie_in_extent_ft) > 0
                    and _boundary_run_LF(e) > 0)
    if tie_in_sf > 0:
        out.append(ScopeLine(TIE_IN_ITEM, FIELD_CATEGORY_ID, round(tie_in_sf / 100.0, 4), "SQ", "AUTO",
                             TIE_IN_CITATION, material_profile_id=SYSTEM_ID))

    # THE DRIP EDGE — system-agnostic METAL (Joseph: "Any system can use drip edge, termination bars, cap
    # flashing"), so it uses CORE's id and MERGES like kind with the steep side's. The 95% continuous-run
    # rule is core's ONE copy since v106.5 (scope_contract.CAP_THRESHOLD); a copy here would have been the
    # third. Quantity is the FULL run and the gate is CONFIRM, identical to the coursed side's treatment,
    # because the rule is about continuous metal and not about what is under it.
    for e in iface.edges:
        if e.edge_type in DRIP_EDGE_TYPES and float(e.edge_total_LF) > 0 \
                and float(e.contact_LF) >= CAP_THRESHOLD * float(e.edge_total_LF):
            out.append(ScopeLine("Drip edge", "DRIP_EDGE", round(float(e.edge_total_LF), 2), "LF",
                                 "CONFIRM", "IRC drip edge", material_profile_id=SYSTEM_ID))
    return out
