#!/usr/bin/env python3
"""
roof_systems/modbit/modbit_geometry.py — the MODBIT profile and disturbance strategy (FRAME v106.4)
===================================================================================================
THE SECOND ROOF-SYSTEM PACKAGE. The dependency runs ONE way, exactly as wood shake's does: this package
imports core (the registry); core never imports this package. It registers itself at import
(core/registry/roof_systems.py), and core looks it up by the facet's declared system.

THREE REGISTRATION CHOICES, each a decline with a reason:

  * `claims_unlabelled_profiles` is NOT set. At most one package may claim unlabelled (pre-ProjectConfig)
    profiles, and wood shake claims them — a second claimant RAISES at registration. That claim is also what
    keeps every saved claim and every verification fixture working once a second package exists: a claim that
    declares nothing resolves to the CLAIMANT, which is wood shake. MODBIT must not take that.

  * `course_top_ft` is OMITTED. A membrane is not coursed, so it has no honest answer for "where is the top
    of course n" — the v105.4 decline, by the mechanism core already has. Asking MODBIT then raises by name
    rather than returning a number invented from shake's exposure.

  * `disturbance` declares VALLEY and REFUSES it, by name (see below). VALLEY is the ONLY event type core
    ever dispatches through the disturbance map (measured: `geometry_core.py:319` is the sole reader), so
    declaring any other type would be a declaration nothing reads — "a guard with no receipt is a claim"
    (entry 120).
"""
from roof_systems import register

import modbit_categories   # the package registers the category ids it owns, on any entry

SYSTEM_ID = "modbit"

# The profile axes that are MODBIT's OWN. Each package defines its own shape — wood shake has
# width_in x exposure_in; MODBIT has the application method. There is NO shared "flat roof profile" struct,
# and there must not be one: EPDM is attachment x thickness, TPO adds fleece-back, BUR is ply count. A common
# struct would be wrong four times out of four.
#
# `application` is None here on purpose: that is the UNQUALIFIED field line (Xactimate's own `BI`), not a
# guess at a method. The qualified variants are recorded for when a per-system profile reaches this engine.
APPLICATION_METHODS = ("TORCH", "COLD_ADHESIVE", "HOT_MOPPED", "SELF_ADHERING")

DEFAULT_MODBIT_MEASUREMENTS = {
    "system_id": SYSTEM_ID,
    "application": None,            # None -> the unqualified "Modified bitumen roof" line
    "measurement_source": "default — not field-measured",
}


def resolve_modbit_profile(measurements=None):
    """Return a validated MODBIT profile with defaults.

    A profile labelled for another system is not this package's to resolve — the same guard wood shake
    carries, and the reason the registry dispatches on the profile's own system_id (v105.4).
    """
    given = dict(measurements or {})
    sid = given.get("system_id")
    if sid not in (None, "", SYSTEM_ID):
        raise ValueError(f"modbit cannot resolve a profile labelled system_id={sid!r}")
    out = dict(DEFAULT_MODBIT_MEASUREMENTS)
    out.update({k: v for k, v in given.items() if v not in (None, "")})
    app = out.get("application")
    if app not in (None, "") and str(app).upper() not in APPLICATION_METHODS:
        raise ValueError(f"modbit application {app!r} is not one of {list(APPLICATION_METHODS)}")
    if app not in (None, ""):
        out["application"] = str(app).upper()
    out["system_id"] = SYSTEM_ID
    return out


def valley_disturbance(event, facet, grid, profile):
    """MODBIT's VALLEY strategy — it REFUSES, and the refusal is the correct answer today.

    A membrane has no courses to step and no shadow that propagates up-slope, so wood shake's stair-step band
    is not merely wrong here, it is meaningless. What a membrane valley repair disturbs is a domain ruling
    Joseph has not made: patches are explicitly out of scope ("we don't typically argue repairs",
    2026-11-01), and a MODBIT facet is scoped as a full replacement, which does not reach this strategy.

    MEASURED, on this tree: with F10/F11 declared MODBIT, core calls this ZERO times — on the Yager repair
    selection and on the full 22-facet replacement alike. Every VALLEY-typed edge on those two facets is a
    CROSS-SYSTEM boundary (L30/L45 to F4/F6, L36/L49 to F4/F8); the only edge with MODBIT on both sides is
    L56, a RIDGE. So no valley on this roof has a MODBIT side to disturb.

    Refusing by name is therefore the honest implementation: it cannot fire on real geometry, and if a claim
    ever does scope one, the user gets the unmade ruling named rather than a band computed from shake's
    exposure. Reusing wood shake's strategy — which a probe package may do, and which v105.3's probes DO —
    would silently bill a membrane by a coursed covering's geometry.
    """
    raise NotImplementedError(
        "FRAME: roof system 'modbit' has no VALLEY repair geometry. A membrane is monolithic — it has no "
        "courses to step and no up-slope shadow — and what a membrane valley repair disturbs has not been "
        "ruled on (patches are out of scope; a MODBIT facet is scoped as a full replacement). Fix: scope "
        "this facet as a replacement, or rule on membrane valley repair and give this package a strategy. "
        "(v106.4)")


def _expand_scope(iface, *args, **kwargs):
    """The package's scope engine, as registered with core (callers ASK the registry for it — bridge 6,
    retired at v104b). Imported at CALL time, mirroring wood shake's `_expand_scope`, so that importing this
    module to REGISTER the package does not pull the scoping module into every page's boot."""
    from modbit_scope_expansion import expand_scope
    return expand_scope(iface, *args, **kwargs)


# FRAME v106.3b — `tie_in_courses = 3`, and it is THIS package's number, not the shake package's.
#
# Mule-Hide `MH-MB-WFT06` rev. 3/12/2020, note 2: "SAMB membrane must extend a minimum of 12" vertically up
# the slope and under a minimum of 3 courses of shingles." Carlisle `U-13E` (© 2025), note 1: "Regardless of
# membrane exposure extend membrane under first 3 courses", with the callout "Roof membrane extended under
# the shingle courses." Two independent membrane manufacturers, one count — and Carlisle's "regardless of
# membrane exposure" is the stronger phrasing: the three courses are required even where little membrane shows.
#
# WHAT IT IS NOT. Wood shake also carries a 3, at `wood_shake_geometry.TIE_IN_COURSES`, and the two are
# DIFFERENT FACTS that happen to share a value today: shake's is CSSB Figure 10's count for a steep-to-steep
# PITCH TRANSITION, this one is a membrane manufacturer's count for a flat-to-steep SYSTEM BOUNDARY. Folding
# them into one constant would mean an EPDM system whose manufacturer specified a different count could not
# express it without moving shake's CSSB figure too. They stay apart deliberately.
#
# `course_top_ft` is still OMITTED (see this module's docstring): this package says HOW MANY courses its
# material runs under, and the coursed package on the other side says HOW FAR that is. Neither holds both
# halves — see roof_systems.system_boundary_tie_in_ft, where the two are composed.
# FRAME v106.6c: THE CUT-BACK IS THE DISTURBANCE. Joseph, 2026-11-05, ruling on the double count the
# v106.6b builder found: "Correct. The cutback is the disturbance."
#
# A membrane has no courses to lift. You cut it back 6 in on all sides of the appurtenance, you patch it, and
# the patch IS the repair — Joseph, 2026-11-04: "we would need to know how much SF is needed to complete the
# repair around the chimney or skylight. If it is a simple point appurtenance, then the appurtenance flashing
# plus 1 patch would be fine." Flashing plus one patch. Not flashing plus a patch plus the field by the SQ.
#
# 6 in per side is EXACTLY Joseph's cut-back, and that is not a coincidence to be re-derived elsewhere:
# appurt_rect grows a dimensioned footprint by the clearance on EACH side, so (w + 2 x 6in) x (h + 2 x 6in)
# = (w + 1 ft)(h + 1 ft) — the formula he gave, and the formula modbit_scope_expansion's patch bands size
# themselves from.
#
# ONE number, declared once, read by the carve and by the patch — TRUE AS OF v106.6d, AND NOT BEFORE.
# This comment said so at v106.6c and was wrong. The carve read this declaration; the patch read a separate
# MEMBRANE_CUTBACK_FT = 1.0 in scope_contract. The two agreed in value and nothing derived either from the
# other, so a change to one moved only its own side — and the gate check whose text asserted otherwise
# PASSED under exactly that mutant. The builder found it, and ledger entry 129 records it as QA error 77.
# v106.6d retired MEMBRANE_CUTBACK_FT and derives the cut-back here (modbit_scope_expansion._cutback_ft),
# so the claim is now a fact rather than an intention.
APPURTENANCE_CLEARANCE_IN = 6.0
# FRAME v106.6g: the BASE-FLASHED allowance. The same six inches as the curb number on this covering, and
# for the same reason rather than by coincidence - Joseph, 2026-11-06: "for flat roofs, you don't need IWS,
# but you do need clearance for the flashing and 6in is pretty standard", and "the patch extends about 6in
# around the appurtenance". On a membrane the two methods want the same distance; on a coursed covering they
# do not, which is why the number is declared per method and per package rather than once.
APPURTENANCE_BASE_CLEARANCE_IN = 6.0

# FRAME ARC-03a — WHAT A DECLARED MODBIT PROFILE MUST CARRY: the application method, chosen by the user. None is
# an explicit answer ("not stated" -> the unqualified line), never an automatic one; the closed list is
# APPLICATION_METHODS above. No preset: there is no MODBIT value to offer that the user did not choose.
PROFILE_SETTINGS = {"application": {"nullable": True, "choices": APPLICATION_METHODS}}

register(SYSTEM_ID,
         resolve_profile=resolve_modbit_profile,
         disturbance={"VALLEY": valley_disturbance},
         expand_scope=_expand_scope,
         tie_in_courses=3,
         appurtenance_clearance_in=APPURTENANCE_CLEARANCE_IN,
         appurtenance_base_clearance_in=APPURTENANCE_BASE_CLEARANCE_IN,
         profile_settings=PROFILE_SETTINGS,
         # FRAME ARC-05a: the VALLEY entry above is a NAMED REFUSAL (valley_disturbance raises NotImplementedError),
         # and the registration now says so, so no capability listing can count it as an implemented strategy.
         # No package operation is declared: a membrane has no piece count, and the roof-level eave ice & water
         # line has never been MODBIT's — asking this package for either raises by name.
         refused_events=("VALLEY",))
