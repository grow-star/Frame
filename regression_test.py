#!/usr/bin/env python3
# CHANGELOG 2026-07-01: stair_edges inner-edge first-row guard added (prev_i is None ->
# seed ie[n]=vx(ye), mirroring the outer-edge guard). Fixes TypeError crash on multi-valley
# cascades whose first course row is above the valley apex (e.g. L45/L49 facets F6/F8/F11).
# Verified: Yager 3382/1639.4/134.03 (Build 2b: Path A activated — L33 fires at 100% contact and
# carves its band; RE-GROUNDED from 3360/1628.9, which was missing a real repair event).
"""
REGRESSION TEST — Wood Shake Affected-Area Engine
=================================================
PASS/FAIL GUARDRAIL. Run after ANY change to engine code. All tests must pass.

VERSION: v3.4 STABLE SUITE (31 cases / 42 checks, all released). Matches Formula
Spec v3.4 / Program Logic v2.5 / Module 2 v1.3 / Architecture v1.6 and is what the
builder implements against. ENGINE RULES ARE UNCHANGED FROM v3.3 — v3.4 adds test
COVERAGE only (tests 29-31 = Yager selected-event inside/outside coverage), proven
against the same canonical engine. No geometry rule, formula, or frozen expected
value moved.
  - Tests 1-28 (the former v3.3 stable suite): valley firewall (1-6), appurtenance +
    source (7-11), stress hardening (12-16), edge-contact extractor across six facets
    (17-25), Module 2 guards (26-28). All frozen and untouched.
  - Tests 29-31 (added at the v3.4 coordinated bump, 2026-06-17): full Yager
    selected-event coverage — inside selected sides (29: D/E/M/L/J/F/I/K/G/H),
    R/L10 outside contribution + full N/R outside union (30), and the L45/L49
    zero-over-scope guard (31). Engine-first from live XML.txt; human-reviewed and
    signed off (Module 1 Full Yager Selected-Event Coverage, COMBINED sign-off).
Any future change follows the same discipline: dev-branch ledger + growing tests
first, one coordinated bump only after the public spec is updated and the full
suite passes.

v3.3 RELEASED RULES (tests 17-28, now stable)
---------------------------------------------
(G) EDGE-CONTACT EXTRACTOR — new Module 1 output (contacted_edges[]) that
    Module 2 consumes. edge_contacts() returns, per facet edge, the honest
    measured contact length and the edge total length. Contact is measured by
    STRIP-INTEGRATION — probe perpendicular into the facet at depths 1-4 cells,
    count an along-edge position contacted when a majority fall in the zone.
    This is orientation-independent and convergent across resolution; an earlier
    omnidirectional probe under-counted steep diagonals and was replaced.
    VALLEYS ARE EXCLUDED from contact (scoped by their own length). Module 1
    reports RAW geometry; the 95% round-to-full-run on caps and continuous
    metals is a Module 2 material decision, never done here.
    Refactor: affected_area gained return_zone=True (exposes the zone mask);
    the default (per, area) signature is unchanged, so tests 1-16 are untouched.
    FIREWALL held: all 16 stable area values reproduce exactly.
    Validated across six facets (Yager): D (eave 2.00, rake 0.00, hip 2.62
    partial, ridge 6.32 of 6.56 = 96% -> full cap), N/R, L, M, V, P (tests
    17-25). Released in the coordinated v3.3 bump (2026-06-15) alongside the
    ridge/hip 95% cap rule, transition-detector third condition, and appurtenance
    grouping (tests 26-28).

Release history below.

CHANGE LOG (v3.1 -> v3.2) — two ADDITIVE changes; confirmed 2026-06-14
-------------------------------------------------------------------------------
(E) APPURTENANCE DISTURBANCE — a confirmed appurtenance repair event generates
    a disturbance zone the same way a valley does: a footprint band, shadow-
    filled upward through the continuous field, clipped to the facet, unioned
    with all other zones (overlap counted once). The footprint rule is set by
    appurtenance TYPE, never a size threshold:
      POINT types (pipe jack, turtle/box vent, turbine): fixed 21in x 21in
        square (no user dimensions; half-side = 21in/2 = 10.5in each way).
      DIMENSIONED types (chimney, skylight, other/custom): footprint + 21in
        clearance on EACH side -> (L+42in) x (W+42in). Dimensions required.
    The 21in is the IWS clearance: ~18in onto the deck + a few inches up the
    curb ~= 21in of membrane; disturbance and IWS share this footprint.
    "Sides touching shingle" needs NO user input: the facet clip handles it
    (a chimney against a ridge/wall simply has its band clipped on that side).

(F) USER-PLACED EVENTS — the engine is SOURCE-AGNOSTIC. Valley and appurtenance
    events are computed identically whether EagleView detected them or the user
    placed them on the diagram. Placement = candidate; user confirmation = a
    scoped repair event; informational = shown only, never scoped (the gate is
    enforced in the UI/program-logic layer, not here).

FIREWALL: changes E and F do not touch the valley path. The six v3.1 frozen
values (tests 1-6) MUST reproduce unchanged. Verified on build 2026-06-14.

HARDENING (same day, no frozen value moved): explicit appurtenance 'kind' is
now required and validated (a dimensioned type with missing dims raises instead
of silently becoming a point); five "uglier" cases added as frozen tests 12-16
(dimensioned corner-clip, appurtenance shadow-stop at a notch, jack+jack union,
chimney-as-penetration-plus-appurtenance, and the bad-input guard). All caught
behavior that was claimed but previously unexercised; #16's gap was real.

CHANGE LOG (v3.0 -> v3.1) — confirmed by Joseph 2026-06-12
---------------------------------------------------------
ENGINE CHANGES (moved frozen values):
  (A) CLEARANCE BAND — Option B. The 24-in band is the STARTING CLEARANCE,
      measured HORIZONTALLY ALONG THE SHINGLE COURSE from the valley
      centerline: band_edge(n) = centerline_x(n) + fan*clearance_band.
      NOT a perpendicular offset.
  (B) COURSE GRID — whole-slope. Course rows defined ONCE per physical slope,
      anchored at the slope's eave datum, shared by every valley on that slope.
ENGINE CHANGES (verified zero effect on frozen values):
  (C) SHADOW CLASSIFICATION — shadow propagates upward only within a CONTINUOUS
      shake field. THROUGH a ROOFPENETRATION (one continuous course run around
      the object). STOPS at a notch (dormer / separate roof section) and at any
      facet boundary.
  (D) FRAME X-AXIS — along-course x from slope plane + gravity:
        up_slope = gravity projected onto facet plane, reversed uphill
        x = normalize(cross(up_slope, facet_normal)); eave signs x only.
PROGRAM-LOGIC DECISIONS (reporting/parse layer; not exercised numerically here):
  (E1) 75% RULE — affected_SF / slope_SF, both NET of the same penetration
       holes (net/net); denominator = merged physical slope.
  (F1) FAN DIRECTION — from the confirmed valley-side/facet assignment against
       the ORIGINAL EagleView facet; never from the merged centroid.
  (G1) FLAT-VALLEY FLAG — informational only; never controls scope.
  (H1) SHAKE-COUNT ROUNDING — ceil ONCE per scope line, after repair_factor:
       EA = ceil(SQ x 14400/(measured_width_in × exposure_in) x repair_factor).

THE MODEL
---------
Affected area per in-scope VALLEY is a closed per-course region on the slope-
wide course grid (inner = centerline to apex then free cut edge; outer =
governing of band_edge and prior+lateral_step; shadow upward; clipped to facet
minus holes). Affected area per in-scope APPURTENANCE is its type-set footprint
band, shadow-filled upward, clipped. Hidden-line slope groups merge first.
Multiple in-scope events on one slope -> UNION, overlap counted once.

PARAMETERS (user-adjustable inputs; validated defaults)
-------------------------------------------------------
  exposure       = 10 in    (24-in shake; 18-in shake uses 7.5 in)
  shake_width    = 7 in
  joint_offset   = 1.5 in   CSSB minimum. COMPLIANCE CONSTRAINT ONLY.
  lateral_step   = shake_width / 2 = 3.5 in/course. PHYSICS, never from offset.
  clearance_band = 24 in    valley STARTING CLEARANCE along the course.
  appurt_clear   = 21 in    appurtenance clearance (point=21x21 total;
                            dimensioned=21in each side). IWS shares footprint.
  shakes_per_SQ  = 14400/(width_in × exposure_in); default 7 in × 10 in = 205.714
  repair_factor  = 1.0/1.5/2.0  shake COUNT only, never area.

FROZEN EXPECTED VALUES (tolerance: max(1.5 SF, 2.5%))
-----------------------------------------------------
  VALLEY (v3.1, unchanged — firewall):
  1. Synthetic 45 deg valley, 20x10 ft rectangle ........ 65.7 SF
  2. Synthetic + 2x2 ft ROOFPENETRATION inside zone ..... 61.8 SF
  3. Facet D inside (valley L4), Yager XML .............. 28.2 SF
  4. Dormer outside L4 (rake-bounded side), merged N/R .. 65.5 SF
  5. Dormer outside L5 (open side), merged N/R .......... 85.5 SF
  6. Dormer outside union (overlap counted once) ........ 142.1 SF
  APPURTENANCE (v3.2, new — validated vs hand-calc):
  7. Point pipe jack, open 40x40 facet, localized 21x21 . 3.0 SF
  8. Dimensioned skylight 2x4 ft -> 5.5x7.5 + shadow .... 185.6 SF
  9. Point appurtenance clipped at facet edge .......... 28.8 SF
 10. Valley + point jack, union counts overlap once .... 66.5 SF
 11. User-placed point jack on bare facet (source test)  13.7 SF
  APPURTENANCE STRESS (v3.2 hardening — uglier cases):
 12. Dimensioned object clipped at a CORNER (two edges) . 150.4 SF
 13. Appurtenance shadow STOPS at a notch (field break) . 27.6 SF
 14. Jack + jack overlap, union counts overlap once ..... 84.6 SF
 15. Chimney as ROOFPENETRATION + appurtenance: shadow
     through the hole, footprint excluded from count .... 176.1 SF
 16. BAD INPUT: dimensioned type with no/zero dims, or a
     missing 'kind', RAISES ValueError (never a silent
     fallback to a point). Type is authoritative.
NEGATIVE GUARD: a point appurtenance must be 21x21 (not 42x42). Test 7 fails
high (~93) if the point branch is wrongly given +21in-each-side.
INPUT CONTRACT: every appurtenance dict requires 'kind' = 'point' or
'dimensioned'; dimensioned requires positive w AND h. The footprint rule is
set by TYPE, never inferred from dimension values (Formula Spec §9).
  EDGE CONTACT + MODULE 2 GUARDS (v3.3 RELEASED — Module 1 output -> Module 2):
 17. Facet D edge contacts at res=0.04: eave 2.00, rake 0.00,
     hip 2.62, ridge 6.32 (of 6.56) ...................... (honest geometry)
 18. Module 2 cap decision from #17: ridge 96% >= 95% -> full
     6.56; hip 65% < 95% -> partial 2.62 ................. (95% all-or-nothing)
 19-21. N/R / L / M edge contacts (no-starter negatives; M drip-edge POSITIVE
     fires at 100%; two ridge segments both -> full) ..... (representative facets)
 22-24. V dormer wrap: J-side rake 99% drip + jack subsumed; east side mirror;
     full union 98% area, ridge closed 40.5, both rakes drip (strip-integration
     diagonal-stable; fan-direction guard) ............... (14-edge non-convex)
 25. Facet P appurtenance-only: localized chimney as penetration+appurtenance, footprint
     excluded, 21in ring clipped to facet = 17.5 SF ...... (no-valley case)
 26. Transition detector: L33 V/P true transition; saltbox ridge caught by the
     3rd condition (fall-same-way); same-pitch / climbing edge excluded.
 27. Transition firing: synthetic 100% -> full LF + underlayment LF x3; 31% -> no.
 28. Appurtenance grouping: naive per-face = 2 chimneys (double-count); grouped
     per-object = 1; standalone falls back to id.
Contact tolerance +/-0.30 LF (absorbs grid-resolution sensitivity; the
meaningful distinctions 0 / 2 / 2.5 / 6.3 are far wider than the tolerance).
"""
import numpy as np, re, sys
from geometry_core import *
# FRAME ARC-05a: `import wood_shake_geometry` (package isolation exception E4) is gone. It registered the wood-shake
# package for this module's self-test, which ARC-04a moved, with that same import, to
# verification/regression_test_engine_suite.py — the test carries its own setup, and this shipped module now names no
# package and dispatches nothing.


if __name__ == "__main__":
    # FRAME ARC-04a: this module's self-test (the 31-case / 42-check suite listed in the docstring above) MOVED,
    # byte-for-byte, to verification/regression_test_engine_suite.py — it held 8 shipped material-term sites. Running
    # this file no longer runs it; it says where it went and exits non-zero rather than passing silently.
    print("deploy/regression_test.py: the affected-area regression suite moved to "
          "verification/regression_test_engine_suite.py (FRAME ARC-04a). Run it from deploy/ as documented there.")
    raise SystemExit(2)
