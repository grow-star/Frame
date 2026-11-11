#!/usr/bin/env python3
# Extracted production geometry primitives from regression_test.py.
# CHANGELOG 2026-07-01: stair_edges inner-edge first-row guard included
# (prev_i is None -> ie[n]=vx(ye)), matching the v3.4 regression source.
# CHANGELOG 2026-07-03: unified centerline-extent stair seed for flat valleys; anchor unchanged 3691.

import re
import hashlib as _hashlib                     # FRAME ARC-06a: the profile fingerprint (F-1/F-2)
import json as _json
import numbers as _numbers
from collections.abc import Mapping as _Mapping
from math import degrees, atan2, hypot        # FRAME v106.6d: hypot, for shared_edge_overlap_ft
import numpy as np
from matplotlib.path import Path
from appurtenance_types import BASE_FLASHED as _BASE_FLASHED           # FRAME v106.6g
from appurtenance_types import is_base_flashed as _is_base_flashed      # FRAME v106.6g: the
from appurtenance_types import standard_base_in as _standard_base_in   # TYPE decides, not the size
from appurtenance_types import resolve_type as _resolve_type           # by LABEL or by CATEGORY
from appurtenance_types import declared_categories as _declared_categories
from facet_basis import facet_frame_axes   # FRAME v105.1: THE ONE fall-line basis

# FRAME v95 / step 3b: the shake profile (constants, EXP/STEP, resolve_shake_measurements, _profile_units,
# the tie-in extent, stair_edges) lives in roof_systems/wood_shake/wood_shake_geometry.py. Core never imports
# a package: affected_area() looks the package up in core's registry by the profile's system_id.
from roof_systems import (system_for_profile, FacetGrid, PROPAGATE_TO_RIDGE, BOUNDED, SHADOW_RULES,
                          get as _rs_get, appurtenance_clearance_in as _appurtenance_clearance_in)

CLEAR_BAND_FT  = 2.0
BAND=CLEAR_BAND_FT

# FRAME v106.6c: `APPURT_CLEAR_IN = 21.0` AND ITS DERIVED `CLR` ARE GONE FROM CORE.
# The 21 in was wood shake's: it is how far the interlocking courses must be lifted to reach the flashing. It
# sat here, applied to every roof system alike, so a membrane could not decline it — and a membrane has no
# courses to lift, it is cut where it is cut (Joseph, 2026-11-05: "The cutback is the disturbance"). The number
# is now DECLARED by each package through `register(appurtenance_clearance_in=...)` and reaches this module the
# same way a VALLEY strategy does: looked up, never assumed.
#
# WHY IT HID FOR TWO ROOF SYSTEMS. The shared-core purity gate scans core for material WORDS — "shake",
# "exposure", "course". A bare `21.0` carries none, so the gate was structurally unable to see the single most
# load-bearing coursed assumption in core geometry. The gate catches NAMED coursed assumptions, not numeric
# ones, and nothing in this build changes that: the lesson belongs in the ledger, not in a scan.

def appurt_rect(app, clearance_in):
    """v3.2: appurtenance disturbance footprint, by TYPE (never size threshold).
    app REQUIRES 'kind': 'point' or 'dimensioned'.
      POINT (every BASE_FLASHED type: pipe jack, box vent, turbine, power vent, vent cap): the type's
        STANDARD FLASHING BASE plus clearance_in each side, taken from app['standard_base_in'] where the
        router put it (v106.6g). A point zone with no standard base falls back to a bare clearance_in
        square, which is now only the untyped hand-placed case; no dims either way.
      DIMENSIONED (chimney, skylight, other/custom): footprint + clearance_in EACH side;
        requires positive w AND h.
    A dimensioned type with missing/zero dims is an ERROR, never a silent
    fallback to a point — the dropdown type is authoritative (Formula Spec §9).
    Returns rectangle polygon in facet frame (feet)."""
    # FRAME v106.6c: clearance_in is REQUIRED and comes from the package that owns the facet. Core keeps the
    # rectangle's SHAPE (geometry) and holds none of its SIZE (material). No default: a wrong clearance is a
    # silently wrong scope, which is the defect this signature exists to prevent.
    if not (isinstance(clearance_in, (int, float)) and not isinstance(clearance_in, bool) and clearance_in > 0):
        raise ValueError(f"appurt_rect needs the owning package's appurtenance clearance, in inches; got "
                         f"{clearance_in!r}. Core holds no clearance of its own (FRAME v106.6c).")
    CLR = float(clearance_in) / 12.0
    cx,cy=app['cx'],app['cy']; kind=app.get('kind')
    if kind=='point':
        # FRAME v106.6g: base-flashed - the type's standard flashing base plus the package's allowance on
        # EACH side. Joseph, 2026-11-06: "For a typical box vent or pipe jack, you would need roughly a
        # 21in x 21in square that gives enough room to place the 12in x 12in vent and place a strip of IWS
        # around the flashing." A 12in base at 6in per side is a 24in square - ROOMIER than the 21in he
        # described, not equal to it, and that is the authorized figure: asked for the rule rather than the
        # example, he set the allowance itself ("A 5in to 6in area for IWS to be placed around the flashing on
        # its common flashing base size would be fine"). Do not cut the allowance to 4.5in to make the
        # arithmetic land on 21in; the allowance is the ruling and 21in was the illustration.
        #
        # The pre-v106.6g form, a bare clearance square with no base in it, is kept for a zone that carries
        # no standard base. That is not a fallback for a base-flashed type - the router always stamps one -
        # it is what a hand-placed marker with no type still gets, and it is what every construction written
        # before this build gets, which is why no frozen figure in the suite moves on it.
        #
        # TRUTHFUL TO THE XML (Joseph, 2026-11-07). The base is the LARGER of the type's standard base and
        # what the item actually measures, PER AXIS. His two requirements come apart exactly at a mislabel:
        #   "My meaning for an XML pipe jack being the same disturbance as a user defined pipe jack is so I
        #    don't have 1 at 34 each and 1 at 7. That looks odd and wrong. But, I can't have the program just
        #    accept a label from a user when it is obviously not even close (e.g. labeling a chimney a pipe
        #    jack and only giving it a pipe jack disturbance. That's not being truthful to the XML)."
        # Taking the larger satisfies both. Two genuine pipe jacks both measure about their standard base, so
        # they bill alike - the consistency he asked for. A 33in hole labelled a pipe jack bills for a 33in
        # hole - the truthfulness he asked for. An earlier draft read his first requirement as "never consult
        # the polygon" and so billed that hole as a 10in jack, which is the under-scope he rejected.
        #
        # THIS IS NOT v103's SIZE TEST RETURNING. v103 inferred the FLASHING METHOD from size: over 21in a
        # vent became a curb and took the 21in curb allowance, a 7x jump in disturbance across a threshold.
        # Formula Spec v3.4 section 9 forbids exactly that, and it is what made Yager's F73 - a nominal 6in
        # vent measuring 6.0022 x 5.9975in - route as a curb for want of two thousandths of an inch. Here the
        # METHOD still comes from the type and only the EXTENT follows the measurement, which is what a
        # measurement is for. max() is continuous, so there is no threshold and no cliff: F73 takes
        # max(10, 6.0022) = its 10in standard base and nothing happens at any boundary.
        #
        # A zone sized from the measurement rather than the declaration is a probable MISLABEL, and the user
        # has to be told. The number is already truthful without the telling, which is why the two ship
        # separately: v106.6h carries the CONFIRM gate and the citation naming both figures. See the prompt's
        # section 8 - and note the figure is right whether or not anyone reads that warning.
        _base_ft = app.get('standard_base_in')
        if _base_ft is None:
            hx = hy = CLR / 2.0
        else:
            _std = float(_base_ft) / 12.0
            hx = max(_std, float(app.get('w') or 0.0)) / 2.0 + CLR
            hy = max(_std, float(app.get('h') or 0.0)) / 2.0 + CLR
    elif kind=='dimensioned':
        w=app.get('w',0.0); h=app.get('h',0.0)
        if not (w>0 and h>0):
            raise ValueError(f"dimensioned appurtenance requires positive w and h; "
                             f"got w={w}, h={h} (type must not silently become a point)")
        hx=w/2.0+CLR; hy=h/2.0+CLR
    else:
        raise ValueError(f"appurtenance 'kind' must be 'point' or 'dimensioned'; got {kind!r}")
    return [(cx-hx,cy-hy),(cx+hx,cy-hy),(cx+hx,cy+hy),(cx-hx,cy+hy)]

# FRAME v102: APPURTENANCE ROUTING — the TYPE decides the disturbance zone, never the measurement.
# appurt_rect (above) has always said so; nothing upstream ever asked the type. An XML penetration arrives from
# the parser as kind "dimensioned" (its polygon is a measurement), so a pipe jack / box vent / turbine scoped at
# footprint + 21" per side: 5-7x the point zone of the day. These two tables are the routing rule, and the one
# place it lives in Python.
#   * label -> category mirrors module2_scope_expansion's type switch exactly (the category each label's
#     material line bills); any other label (OTHER, or anything unknown) takes its other_category, as there.
#     appurtenance_routing_regression asserts the mirror against expand_scope itself.
#   * v106.6g: which labels are POINT labels is no longer stated here. It is the TYPE table's BASE_FLASHED
#     set, read below through _is_base_flashed. The LABELS must still equal page 2's
#     POINT_APPURTENANCE_TYPES (page2.html) — asserted by the same regression, until page 2 reads this table.
# The flashing method only ever forces POINT. Everything else keeps the geometry as declared or measured (OTHER keeps
# the dimensions the user typed; a dimensioned type with no dims still raises in appurt_rect).
APPURT_LABEL_CATEGORY = {
    "CHIMNEY": "CHIMNEY_FLASH", "SKYLIGHT": "SKYLIGHT_FLASH", "PIPE": "PIPE_JACK_FLASH",
    "TURTLE": "BOX_VENT", "TURBINE": "TURBINE_VENT", "POWER_VENT": "POWER_VENT",
}
# FRAME v106.6g: derived from the TYPE table, which is the one place that knows how an item is flashed.
# POINT_APPURTENANCE_TYPES used to be derived from POINT_APPURTENANCE_CATEGORIES, so "which types are point
# types" had two sources that happened to agree - and they agree in VALUE to this day, which is why no value
# check can tell the two derivations apart. QA's G9 mutant reverted this line to the category set and the
# ENTIRE suite stayed green. So the dependency is INVERTED instead: the categories are now derived FROM the
# labels, below, and reverting this line to read the category set is a NameError at import rather than a
# silent regression. The duplicate authority is not asserted away, it is unexpressible.
POINT_APPURTENANCE_TYPES = tuple(lab for lab in APPURT_LABEL_CATEGORY if _is_base_flashed(lab))
# Derived from the TYPE TABLE across BOTH its keys, which matters: a category can be a point without having
# a dropdown label of its own. VENT_CAP is exactly that, and it is why this set is not derived from the four
# labels above.
#   The hand-written set this replaces held those same FIVE members, and it was RIGHT. v106.6g's first draft
# called the fifth one dead - "no label resolves to VENT_CAP, so it routes nothing" - and dropped it. The
# label part was true and the conclusion was false: page 2 offers VENT_CAP as a CATEGORY under "other" on all
# three surfaces, so it routed, as a point, and the draft sent it curb-flashed at about 19 SF instead of
# about 3 on shake. Deriving the set properly reproduces the original five member for member, which is the
# cleanest evidence that the old hand-written value was correct and the draft's reasoning was not.
POINT_APPURTENANCE_CATEGORIES = frozenset(
    c for c in _declared_categories() if _is_base_flashed(category=c))

def appurtenance_category(kind_label, other_category=None):
    """The category an appurtenance resolves to: its label's, else (OTHER / unknown) its other_category."""
    lab = str(kind_label or "").strip().upper()
    if lab in APPURT_LABEL_CATEGORY:
        return APPURT_LABEL_CATEGORY[lab]
    return str(other_category).strip() if other_category not in (None, "") else None

def face_plan_points(geom, face_id):
    """Every distinct plan point of a face, in the roof's shared frame (FRAME v106.6d)."""
    ids = []
    for lid in geom.faces[face_id].line_ids:
        ids += list(geom.lines[lid].path)
    return [geom.points[p] for p in dict.fromkeys(ids)]


def shared_edge_overlap_ft(geom, host_a, host_b, pen_a, pen_b) -> float:
    """How much of two markers' footprints face each other ACROSS the edge their host facets share.

    FRAME v106.6d. EagleView splits one physical chimney that crosses a ridge into one ROOFPENETRATION
    marker per facet. Each marker is a closed rectangle on its own plane, so each contributes a FOURTH SIDE
    LYING ON THE RIDGE — and that side is not a chase wall. It is the cut line where EagleView divided one
    object. Two markers, two phantom walls.

    Measured on Yager, F68 (2.50 x 2.00) and F67 (2.50 x 4.50) across ridge L56: the two perimeters sum to
    23.0036 LF, the chase's real perimeter along the roof is 18.0030, and the difference is 5.0006 = 2 x the
    chimney's 2.50 ft width along the ridge. That difference is the OVER-BILL, and it is what the caller has
    to remove.

    This function does NOT return that width. It returns the OVERLAP of the two footprints projected onto the
    shared edge's direction — on Yager 2.4554, against either marker's 2.5003 — so the correction it funds
    is 4.9108 and the billed perimeter lands at 18.0929, about 1.16 in above the chase's real perimeter.
    FRAME v106.6e: an earlier version of this docstring said in one paragraph that the width is returned and
    in the next that it is not. The width was never returned; the first claim was wrong (QA error 77's family
    again — a comment asserting what the code beside it disproves). The two numbers are a width and an
    overlap, they differ, and which one is returned decides whether the correction lands on the true
    perimeter or an inch above it.

    The overlap is the right one of the two, for two reasons. A chimney may cross the ridge at an angle or only clip it, and then
    the shared cut is shorter than either side. And where the two markers disagree slightly — on Yager they
    differ by 0.045 ft of survey noise — the overlap is the SMALLER figure, so the correction UNDER-corrects
    by about an inch rather than over-correcting. That direction is deliberate and is this project's standing
    one: an over-bill is visible on the estimate and correctable, an under-bill is not.

    0.0 — never an error — when there is nothing to correct: the same facet twice, the same marker twice, no
    shared edge, or footprints that do not face each other across the edge they could have shared. Each of
    those is a guard QA's first draft lacked, and the same-facet case returned 3.16 ft before they existed —
    a correction invented out of nothing."""
    if host_a == host_b or pen_a == pen_b:
        return 0.0
    try:
        shared = set(geom.faces[host_a].line_ids) & set(geom.faces[host_b].line_ids)
    except (KeyError, AttributeError):
        return 0.0
    if not shared:
        return 0.0
    try:
        pts_a, pts_b = face_plan_points(geom, pen_a), face_plan_points(geom, pen_b)
    except (KeyError, AttributeError):
        return 0.0
    if not pts_a or not pts_b:
        return 0.0
    best = 0.0
    for lid in sorted(shared):
        try:
            a, b = (geom.points[p] for p in geom.lines[lid].path)
        except (KeyError, ValueError, AttributeError):
            continue
        ux, uy = b[0] - a[0], b[1] - a[1]
        n = hypot(ux, uy)
        if n == 0:
            continue
        ux, uy = ux / n, uy / n
        ra = [p[0] * ux + p[1] * uy for p in pts_a]
        rb = [p[0] * ux + p[1] * uy for p in pts_b]
        ov = min(max(ra), max(rb)) - max(min(ra), min(rb))
        if ov > best:
            best = ov
    return max(best, 0.0)


def appurtenance_base_fits_point_zone(app_geom, clearance_in):
    """FRAME v103 (Joseph, 2026-10-30): does the measured base fit inside the clearance square in BOTH axes?
    Per axis, never by area — a 6in x 30in base sticks out of a 21in square. No measured base (a hand-placed
    marker) fits.

    FRAME v106.6c: the square is the OWNING PACKAGE's clearance, not core's old 21 in, so the question is
    asked in the same units the carve will use.

    RETIRED IN v106.6g, AND IT ROUTES NOTHING. Nothing in production calls this. It is kept, with its
    arithmetic still asserted, because a capability with no caller is a smaller change than deleting a public
    function, and appurtenance_routing_regression pins it as exactly that — so the day a build wires
    size-based routing back in, a check says so. Do NOT read the paragraph above as a live constraint: the
    threshold and the carve no longer have to be one number, because there is no threshold. Formula Spec v3.4
    section 9 always forbade inferring point vs. dimensioned from size, and this function was the inference.
    What killed it was Yager's F73 — a nominal 6in vent measuring 6.0022 x 5.9975in — missing a 6in square by
    two thousandths of an inch and routing as a curb on a membrane facet."""
    lim = float(clearance_in) / 12.0
    w = float(app_geom.get("w") or 0.0); h = float(app_geom.get("h") or 0.0)
    return w <= lim and h <= lim

def appurtenance_zone_geometry(app_geom, kind_label, other_category=None):
    """Route an appurtenance's geometry to its disturbance zone BY TYPE, and by nothing else. A BASE_FLASHED
    type -> kind "point", carrying that type's standard flashing base; a CURB_FLASHED type, and any type this
    table does not declare, -> app_geom unchanged, to be measured.

    FRAME v106.6g: there is NO clearance parameter. It was the third positional parameter through v106.6c and
    v106.6f, because routing then needed to compare a measured base against the package's square. Routing no
    longer asks how big anything is, so the parameter is gone rather than ignored: sizing happens at the ONE
    site that sizes a zone, and threading a clearance back in here is a TypeError, not a quiet regression.

    SUPERSEDED, and recorded so that nobody restores it: FRAME v103 ruled a step at the 21in boundary — over
    21in it is not a vent flashing but a curb, so a 21in base scoped 7 EA and a 22in base the ring, and that
    step was "RULED, not an artefact: do not floor, taper or blend it." Formula Spec v3.4 section 9 had always
    said the opposite ("the disturbance footprint is set by the appurtenance TYPE, never by a size
    threshold... The program must NOT infer point vs. dimensioned from size"), and the step is what made
    Yager's F73 — a nominal 6in vent measuring 6.0022 x 5.9975in — route as a curb on a membrane facet. The
    spec wins. The step does not exist: a base-flashed type is a point at any measured size, and
    appurtenance_routing_regression sweeps 6in to 48in to assert the disturbance never moves.

    The routed geometry KEEPS any measured w/h. appurt_rect ignores them for a point, so they no longer size the
    ZONE — but module1_m2interface._surface_appurts reads exactly those keys for Appurt.affected_SF, which drives
    APPURT_IWS. Joseph (v102 Q2): IWS follows the measured footprint. Keeping the keys is the separation: the zone
    is the type's, the IWS is the measurement's, and module1_m2interface stays byte-identical."""
    if app_geom is None or not hasattr(app_geom, "keys"):
        return app_geom
    # FRAME v106.6g: routed by the TYPE's flashing method and by nothing else. Formula Spec v3.4 section 9:
    # "the disturbance footprint is set by the appurtenance TYPE, never by a size threshold... The program
    # must NOT infer point vs. dimensioned from size." The measured base is no longer consulted, so an item
    # of a type behaves identically whether EagleView measured it or a user placed it - Joseph's requirement,
    # 2026-11-06. A curb-flashed or unknown type keeps its measured geometry, unchanged.
    # C-2: a row may say OTHER and name its real thing as a CATEGORY (a user picking "other" and then "pipe
    # jack flashing"). Both names are keys into the shared type table, so ONE resolver takes both and the
    # table decides. Two drafts got this wrong and both were caught by a reader, not by a gate:
    #   * the first read kind_label alone, and billed a declared pipe jack as a curb;
    #   * the second resolved a category by SCANNING THE LABEL TABLE for a matching one, which works only for
    #     categories that happen to have a label. VENT_CAP has none — page 2 offers it under "other" and
    #     always has — so it fell through to unknown, went curb-flashed, and billed about 19 SF instead of
    #     about 3 on shake. That is the 4-7x overbill Joseph refused on 2026-11-06, reintroduced by the build
    #     meant to prevent it. A category is now LOOKED UP, never inferred from the labels.
    _t = _resolve_type(kind_label, other_category)
    if _t is None or _t.flashing_method != _BASE_FLASHED:
        return app_geom
    base_in = _t.standard_base_in
    if base_in is None:
        return app_geom
    routed = dict(app_geom)
    routed["kind"] = "point"
    # The type's own base travels with the zone so that the ONE site which sizes it can, without having to
    # know the type. Core still holds no material number: this came from the shared type table, and the
    # allowance it gets added to comes from the package.
    routed["standard_base_in"] = float(base_in)
    return routed

def appurtenance_zone_holes(app_geom, holes):
    """FRAME v103: the holes carved from an appurtenance's OWN disturbance zone. A point zone is not carved by the
    hole it sits in — a vent flange sits ON shakes, which come off to install the flashing, so nothing beneath it is
    subtracted (Joseph). Its own hole is the one containing its centre: the detected penetration's polygon, a
    hand-dimensioned footprint centred on the marker, or the detected polygon a hand marker was placed on. Every
    other hole keeps carving; a dimensioned zone (chimney, skylight, curb) keeps carving its own, because it IS a
    hole in the deck and only the ring around it is scope."""
    holes = list(holes)
    if app_geom is None or not hasattr(app_geom, "get") or app_geom.get("kind") != "point":
        return holes
    c = (float(app_geom["cx"]), float(app_geom["cy"]))
    return [h for h in holes if not Path(np.asarray(h, dtype=float)[:, :2]).contains_point(c)]

def _shadow_fill_column(fld, bnd):
    """Shared shadow rule: within each contiguous field segment, fill from the
    first band-hit upward to the top of that segment. Used by valley AND
    appurtenance events identically.

    REFERENCE IMPLEMENTATION (v3.8): retained verbatim as the definition of the
    rule and as the equivalence oracle for the vectorized `shadow_fill` below.
    It is no longer called per-column in the hot path (that cost 46% of runtime);
    `shadow_fill` computes the identical result for the whole grid at once."""
    out=np.zeros(len(fld),bool); i=0; N=len(fld)
    while i<N:
        if not fld[i]: i+=1; continue
        k=i
        while k<N and fld[k]: k+=1
        seg=bnd[i:k]
        if seg.any(): out[i+int(np.argmax(seg)):k]=True
        i=k
    return out

def shadow_fill(field, band):
    """VECTORIZED shadow fill (v3.8 performance). Bit-identical to applying
    `_shadow_fill_column` down every column, computed over the whole 2-D grid in
    one pass.

    The RULE IS UNCHANGED: within each contiguous True-run of `field` down a
    column, fill from that run's first band-hit row through the end of the run.
    Implementation: label each contiguous field run down a column (`segid`), take
    the minimum band-hit row within each (segment, column) via `np.minimum.at`,
    then keep the field cells at or below their segment's first hit. `big` (= n)
    is the "no hit in this segment" sentinel, so segments without a hit stay
    empty exactly as the per-column version leaves them.

    Formulation: a cell is filled iff it is field AND at least one band-hit has
    occurred at-or-above it WITHIN its own contiguous run. Let c = cumulative
    count of hits down the column. For a run beginning at row s, the number of
    hits inside the run at-or-above row r is c[r] - c_excl[s], where c_excl[s] is
    the hit count strictly above s. Because run starts move downward and c_excl is
    non-decreasing, `np.maximum.accumulate` of "c_excl at run starts, -1 elsewhere"
    propagates each run's baseline to its own rows. This uses only cumsum and
    maximum.accumulate (fast C reductions) — no `np.minimum.at`, which is an
    unbuffered scatter and was itself a major cost.

    field, band: 2-D bool arrays (rows = y, cols = x). Returns a 2-D bool array."""
    F=np.asarray(field,bool); B=np.asarray(band,bool)&F
    n,m=F.shape
    if n==0 or m==0: return np.zeros(F.shape,bool)
    prevF=np.vstack([np.zeros((1,m),bool),F[:-1,:]])
    start=F&~prevF                                     # first row of each contiguous field run
    c=np.cumsum(B,axis=0,dtype=np.int32)               # hits at-or-above, cumulative
    c_excl=c-B                                         # hits strictly above this row
    base=np.where(start,c_excl,-1).astype(np.int32)    # baseline recorded at each run start
    seg_base=np.maximum.accumulate(base,axis=0)        # each cell inherits its run's baseline
    return F&(seg_base>=0)&((c-seg_base)>0)            # a hit occurred at-or-above, within this run

# ---- v3.8 performance: per-facet grid + point-in-polygon mask cache ----------
# The meshgrid and the containment masks depend ONLY on the facet polygon, the
# penetration holes, the notch holes, `res`, and the resolved shake measurements.
# They do NOT depend on which valley is being processed, yet affected_area was
# rebuilding them on every call (79 calls on Yager). Cache them on a key that
# includes every one of those inputs, so a different facet / hole set / resolution
# / measurement profile can never hit a stale entry (and neither can another roof,
# since its polygons differ).
_GRID_CACHE = {}
_GRID_CACHE_MAX = 64          # bounded: cannot grow without limit across roofs

def _poly_key(poly):
    return tuple((float(x),float(y)) for x,y in poly)

# ---- FRAME ARC-06a (F-1 / F-2): THE PROFILE FINGERPRINT — package-neutral cache identity -------------------------
# Until ARC-06a both cache keys read prof["width_in"] and prof["exposure_in"] — wood-shake course dimensions — out of
# EVERY resolved profile (F-1: a membrane had to invent them to reach core geometry) and NOTHING ELSE from it (F-2: a
# package's own setting, e.g. a band width, did not reach the key, so a changed setting was served the stale area).
#
# THE CONTRACT. A package's resolved profile is OPAQUE to core. Core never names a setting; it fingerprints the WHOLE
# resolved profile, together with the roof system that resolved it, as data:
#   * canonical, type-tagged form: None, bool, int (incl. numpy integers), float (exact: float.hex, so 0.1 and the
#     next double apart are different; NaN refused), str, Mapping with str keys (sorted), list/tuple (ordered),
#     set/frozenset (sorted by canonical form) — recursively, any depth;
#   * the system id rides OUTSIDE the profile dict as well, so two systems can never share a key even if a package
#     forgot to label its profile;
#   * SHA-256 over the canonical JSON, prefixed by a format tag ("frame-profile-v1") so a later change of form is a
#     clean miss, never a collision with an old key.
# ANY value that cannot be canonicalised (an object, a callable, a non-str key, NaN, a numpy bool …) makes the
# profile UNFINGERPRINTABLE: the cache is BYPASSED for that call (computed, never stored, never served) — a slower
# answer is acceptable, a shared answer across unknown semantics is not.
# Type tags mean 7 and 7.0 are different keys: that can only cost a cache MISS, never return a wrong area.
class _Unfingerprintable(Exception):
    """A resolved profile holds a value core cannot canonicalise: do not cache this call."""


def _fp_canon(v):
    if v is None:
        return ["n"]
    if isinstance(v, bool):
        return ["b", v]
    if isinstance(v, _numbers.Integral):
        return ["i", int(v)]
    if isinstance(v, _numbers.Real):
        f = float(v)
        if f != f:
            raise _Unfingerprintable("NaN in a resolved profile")
        return ["f", f.hex()]
    if isinstance(v, str):
        return ["s", v]
    if isinstance(v, _Mapping):
        items = []
        for k in v:
            if not isinstance(k, str):
                raise _Unfingerprintable(f"non-string profile key {k!r}")
            items.append(k)
        return ["d", [[k, _fp_canon(v[k])] for k in sorted(items)]]
    if isinstance(v, (list, tuple)):
        return ["l", [_fp_canon(x) for x in v]]
    if isinstance(v, (set, frozenset)):
        return ["S", sorted(_json.dumps(_fp_canon(x), separators=(",", ":")) for x in v)]
    raise _Unfingerprintable(f"profile value of type {type(v).__name__}")


def profile_fingerprint(system_id, prof):
    """Deterministic, collision-resistant identity of (roof system, fully resolved profile). Raises
    _Unfingerprintable when the profile holds a value core cannot canonicalise (the callers then bypass the cache)."""
    canon = ["frame-profile-v1", str(system_id), _fp_canon(prof)]
    return _hashlib.sha256(_json.dumps(canon, separators=(",", ":"), ensure_ascii=True).encode("ascii")).hexdigest()


def _grid_cache_key(facet,pens,nots,res,prof,system_id=None):
    """The grid depends on the facet, its holes and the resolution only; the profile identity is kept in the key all
    the same (FRAME v104b K9: grids of two systems are never shared), now as the package-neutral fingerprint
    (ARC-06a F-1: no course dimension is read). Raises _Unfingerprintable -> the caller computes without caching."""
    return (_poly_key(facet),
            tuple(_poly_key(h) for h in (pens or [])),
            tuple(_poly_key(h) for h in (nots or [])),
            float(res),
            profile_fingerprint(prof.get("system_id") if system_id is None else system_id, prof))

def clear_grid_cache():
    """Drop all cached grids/masks (e.g. between roofs). Purely a memory control:
    correctness never depends on this, because the key is complete."""
    _GRID_CACHE.clear()

_AREA_CACHE = {}
_AREA_CACHE_MAX = 64

def _hashable_valleys(valleys):
    out=[]
    for vs,va,fan in valleys:
        out.append((tuple(float(v) for v in np.asarray(vs,float).ravel()),
                    tuple(float(v) for v in np.asarray(va,float).ravel()),
                    repr(fan)))
    return tuple(out)

def _hashable_apps(apps):
    return tuple(tuple(sorted((str(k),repr(v)) for k,v in a.items())) for a in (apps or []))

def _band_key(bands):
    return tuple((float(b["x0"]),float(b["x1"]),float(b["y0"]),float(b["y1"])) for b in (bands or []))

def _area_cache_key(facet,valleys,pens,nots,apps,res,prof,return_zone,bands=None,facet_system_id=None):
    """COMPLETE key: every input affected_area's result depends on. Any difference in
    facet, valleys, penetration holes, notch holes, appurtenances, resolution, the
    resolved measurements, or the ROOF SYSTEM that resolved them is a MISS, so a stale
    result can never be reused (across facets, measurement profiles, roofs, or systems).
    FRAME v104b (K9): until v104b the system id was missing, so this claim was false — two
    systems at the same width and exposure shared one entry. Dispatch made it reachable.

    FRAME v106.6c: `facet_system_id` joins the key, and it is NOT redundant with the profile's system id.
    The appurtenance clearance now comes from the FACET's declared covering while `prof` still carries the
    PREDOMINANT system's measurements, so the same facet, appurtenance and profile can be carved at 21 in
    (as wood shake) or at 6 in (as a membrane). Without this term the first of those two carves would be
    served to the second from cache — a stale area, silently. That is the same defect K9 fixed one layer up,
    and the docstring above would have gone back to being false.

    FRAME ARC-06a (F-2): the docstring above was false again in one respect — "the resolved measurements" meant two
    wood-shake dimensions only, so a package setting that changes the disturbance (a band width) was not in the key and
    a changed setting was served the stale area (independent QA: 27.3393 SF returned for band_ft=2). The profile is
    now fingerprinted WHOLE (profile_fingerprint). An unfingerprintable profile raises _Unfingerprintable, which the
    caller treats exactly like an unhashable input: compute, never cache."""
    return (_poly_key(facet),
            _hashable_valleys(valleys),
            tuple(_poly_key(h) for h in (pens or [])),
            tuple(_poly_key(h) for h in (nots or [])),
            _hashable_apps(apps),
            float(res),
            # FRAME ARC-06a (F-1/F-2): the WHOLE resolved profile and the system that resolved it, fingerprinted as
            # opaque data — every package setting reaches the key; no course dimension is required of any package.
            # (Replaces float(width_in), float(exposure_in), str(system_id); K9's system separation is inside it.)
            profile_fingerprint(prof.get("system_id"), prof),
            bool(return_zone),
            _band_key(bands),
            None if facet_system_id is None else str(facet_system_id))   # FRAME v106.6c

def clear_area_cache():
    _AREA_CACHE.clear()

def _facet_grid(facet,pens,nots,res,prof):
    """Return (gx,gy,X,Y,pts,inside,field) for this facet, from cache when the
    exact same inputs were seen before."""
    try:
        key=_grid_cache_key(facet,pens,nots,res,prof)
    except (_Unfingerprintable, TypeError):
        key=None                                     # ARC-06a: cannot identify the profile -> compute, never cache
    hit=_GRID_CACHE.get(key) if key is not None else None
    if hit is not None: return hit
    pf=Path(facet)
    pen_paths=[Path(h) for h in (pens or [])]
    not_paths=[Path(h) for h in (nots or [])]
    top_y=max(p[1] for p in facet); y0=min(p[1] for p in facet)
    gx=np.arange(min(p[0] for p in facet)-0.3,max(p[0] for p in facet)+0.3,res)
    gy=np.arange(y0-0.3,top_y+0.3,res)
    X,Y=np.meshgrid(gx,gy)
    pts=np.column_stack([X.ravel(),Y.ravel()])
    in_facet=pf.contains_points(pts).reshape(X.shape)
    in_pen=np.zeros(X.shape,bool); in_not=np.zeros(X.shape,bool)
    for h in pen_paths: in_pen|=h.contains_points(pts).reshape(X.shape)
    for h in not_paths: in_not|=h.contains_points(pts).reshape(X.shape)
    inside=in_facet&~in_pen&~in_not                 # countable shake field
    field =in_facet&~in_not                          # shadow medium
    val=(gx,gy,X,Y,pts,inside,field)
    if key is not None:
        if len(_GRID_CACHE)>=_GRID_CACHE_MAX: _GRID_CACHE.clear()
        _GRID_CACHE[key]=val
    return val

def affected_area(facet,valleys,penetrations=None,notches=None,
                  appurtenances=None,res=0.04,return_zone=False,
                  shake_measurements=None, width_in=None, exposure_in=None,
                  transition_bands=None, facet_system_id=None):
    """Union of per-event zones (valleys + appurtenances), shadow-filled per
    rule (C), clipped to facet minus all holes. Source-agnostic: events from
    EagleView and user placement are identical here (rule F).
    penetrations: ROOFPENETRATION holes (shadow continues through).
    notches: dormer/separate-section holes (shadow stops).
    appurtenances: list of dict(cx,cy,w,h) confirmed appurtenance events.
    transition_bands: list of dict(x0,x1,y0,y1) in FACET-FRAME coords — the tear-off band of a
    user-confirmed pitch-transition repair event (spec amendment: Transition Repair Events v0.1).
    ADDITIVE: default None -> not one bit of existing behavior changes. Like appurtenances, a
    transition band is a localized strip (its extent is specified: to the top of the 3rd course
    up-slope — three_course_extent_ft, v90 — / 1 course down-slope), so it is clipped to the facet
    and UNIONED with every other event's zone —
    never summed.
    return_zone: if True, also return (zone_mask, gx, gy) for edge-contact
    extraction (v3.3 stable). Default False keeps the frozen (per, area) signature."""
    if shake_measurements is None and (width_in is not None or exposure_in is not None):
        # FRAME v95: a falsy value was replaced here by the shake constant; it is now dropped, and the
        # package's resolver supplies the same default from the same constant. Identical result, and no
        # material constant in core.
        shake_measurements = {k: v for k, v in (("width_in", width_in), ("exposure_in", exposure_in)) if v}
    # FRAME v95: the roof system is LOOKED UP, never assumed. system_for_profile raises on an unknown
    # system_id, and on a profile without one unless a registered package has claimed unlabelled profiles
    # (the package's own declaration — core/registry/roof_systems.py, bridge 1).
    _system = system_for_profile(shake_measurements)
    prof = _system.resolve_profile(shake_measurements)
    if prof.get("system_id") != _system.system_id:
        raise ValueError(f"roof system {_system.system_id!r} resolved a profile labelled "
                         f"{prof.get('system_id')!r}; a package must label the profiles it resolves")
    # v3.8: memoize the whole result. edge_contacts() calls affected_area once per
    # component and Module 2 calls it again directly, so the SAME (facet, valleys,
    # holes, appurtenances, res, measurements) zone was being recomputed many times
    # (79 calls for ~13 distinct inputs on Yager). The key below is complete, so this
    # is a pure speed change. `per` is copied out so no caller can mutate cached state;
    # the mask/grid arrays are treated as read-only by every caller (verified).
    try:
        _key=_area_cache_key(facet,valleys,penetrations,notches,appurtenances,res,prof,return_zone,
                             transition_bands,facet_system_id)
    except (TypeError, _Unfingerprintable):
        _key=None                                    # unhashable input / unfingerprintable profile -> compute, never cache
    if _key is not None:
        _hit=_AREA_CACHE.get(_key)
        if _hit is not None:
            if return_zone:
                _per,_area,_zone,_gx,_gy=_hit
                return list(_per),_area,_zone,_gx,_gy
            _per,_area=_hit
            return list(_per),_area
    # v3.8: grid + containment masks are identical for every valley on this facet ->
    # build once and reuse (cache key covers facet, holes, res, and measurements).
    gx,gy,X,Y,pts,inside,field=_facet_grid(facet,penetrations,notches,res,prof)
    union=np.zeros(X.shape,bool); per=[]
    # ---- VALLEY events — FRAME v95: the PACKAGE's disturbance strategy (Package Contract §1 item 3) ----
    # The package returns (mask, shadow_rule); core applies the rule, clips to the field, unions and integrates.
    if valleys:
        _valley = _system.disturbance.get("VALLEY")
        if _valley is None:
            raise ValueError(f"roof system {_system.system_id!r} supplies no VALLEY disturbance strategy")
        _grid = FacetGrid(gx, gy, X, Y)
    for vs,va,fan in valleys:
        mask, shadow_rule = _valley((vs, va, fan), facet, _grid, prof)
        mask = np.asarray(mask)
        if mask.shape != X.shape or mask.dtype != bool:
            raise ValueError(f"{_system.system_id!r} VALLEY strategy must return a boolean mask over the facet "
                             f"grid {X.shape}; got {mask.dtype} {mask.shape}")
        if shadow_rule == PROPAGATE_TO_RIDGE:
            # v3.8: whole-grid vectorized shadow fill, bit-identical to the per-column loop.
            dist=shadow_fill(field, mask&field)
        elif shadow_rule == BOUNDED:
            dist=mask&field
        else:
            raise ValueError(f"{_system.system_id!r} VALLEY strategy returned shadow rule {shadow_rule!r}; "
                             f"must be one of {sorted(SHADOW_RULES)}")
        per.append((dist&inside).sum()*res*res)
        union|=dist
    # ---- TRANSITION repair events (user-confirmed; band of defined extent) ----
    # The band's extent is SPECIFIED (to the top of the 3rd course up-slope on the upper facet —
    # three_course_extent_ft, v90; was 36 in — and 1 course down-slope on the lower one), so like an
    # appurtenance it is a localized strip: clipped to the facet, unioned with every other zone. It is
    # NOT valley-style shadow-filled to the ridge — that would erase the specified extent and strip the
    # whole upper slope.
    for band in (transition_bands or []):
        bx0=float(band["x0"]); bx1=float(band["x1"]); by0=float(band["y0"]); by1=float(band["y1"])
        dist=(X>=bx0-1e-9)&(X<=bx1+1e-9)&(Y>=by0-1e-9)&(Y<=by1+1e-9)&field
        per.append((dist&inside).sum()*res*res)
        union|=dist

    # ---- APPURTENANCE events (localized spot repair, no valley-style shadow fill) ----
    # FRAME v106.6c: the clearance is the OWNING PACKAGE's, looked up exactly as the VALLEY strategy is. The
    # facet's declared covering decides it (facet_system_id), falling back to the profile's system when the
    # caller names none — which is every pre-v106.6c caller, and for them the number is unchanged because wood
    # shake declares the same 21 in core used to hold. A package that declares no clearance RAISES, named.
    # FRAME v106.6g: this is now the ONLY site that resolves an appurtenance clearance. Five others used to,
    # all of them only to ask "is this a point?", and the TYPE answers that itself now (appurtenance_types).
    # The allowance is picked per zone by its flashing method, because the two are different distances for
    # different reasons: a curb-flashed item needs an 18in IWS strip round its perimeter, a base-flashed one
    # needs room to set a flange and lap it. A zone carrying a standard base came from the type table and is
    # base-flashed; anything else takes the curb allowance. "Anything else" is NOT the same as "measured":
    # a dimensioned item is measured, and an UNTYPED POINT item keeps its point shape and takes a bare
    # allowance square. A hand-placed marker is not in that bucket merely for being hand-placed either - a
    # hand-placed PIPE carries its type's standard base exactly as an EagleView one does, which was the whole
    # point of the type table. An earlier comment here said otherwise and was wrong on both counts.
    if appurtenances:
        _clr_system = _rs_get(facet_system_id) if facet_system_id is not None else _system
        _clr_curb = _appurtenance_clearance_in(_clr_system.system_id)
        _clr_base = None
    for app in (appurtenances or []):
        if hasattr(app, "get") and app.get("standard_base_in") is not None:
            if _clr_base is None:
                _clr_base = _appurtenance_clearance_in(_clr_system.system_id, _BASE_FLASHED)
            _clr_in = _clr_base
        else:
            _clr_in = _clr_curb
        rect=Path(appurt_rect(app, _clr_in))
        dist=rect.contains_points(pts).reshape(X.shape)&field
        per.append((dist&inside).sum()*res*res)
        union|=dist
    zone=union&inside
    area=zone.sum()*res*res
    if _key is not None:
        if len(_AREA_CACHE)>=_AREA_CACHE_MAX: _AREA_CACHE.clear()
        _AREA_CACHE[_key]=(list(per),area,zone,gx,gy) if return_zone else (list(per),area)
    if return_zone:
        return per,area,zone,gx,gy
    return per,area

# ---- v3.3 RELEASED: edge-contact extractor (Module 1 output -> contacted_edges[]) ----
def edge_contact_lf(A,B,zone,gx,gy,res,facet):
    """Strip-integration contact length (diagonal-stable). Probes PERPENDICULAR
    into the facet at depths 1-4 cells and counts an along-edge position as
    contacted when a majority of those depths fall in the zone. Averaging over
    depth makes it orientation-independent and convergent across resolution for
    the edges that drive materials (ridge/eave/rake/hip). An earlier
    perpendicular-only/omnidirectional probe under-counted steep diagonals
    (a 45-deg edge staircases through the grid); this does not.
    NOTE: valleys are NOT measured by contact (scoped by their own length);
    edge_contacts() skips them. Valley contact is intrinsically unstable here
    (sub-cell gap on a 45-deg edge) and unused."""
    A=np.asarray(A,float); B=np.asarray(B,float); L=float(np.hypot(*(B-A)))
    if L<=0: return 0.0
    d=(B-A)/L; nrm=np.array([-d[1],d[0]])
    pf=Path([tuple(p) for p in facet]); mid=(A+B)/2
    if not pf.contains_point(tuple(mid+nrm*res*3)): nrm=-nrm   # inward normal
    H,W=zone.shape; n=max(int(L/(res*0.5)),2)
    # v3.8: vectorized over the n along-edge positions x 4 probe depths. Same rule,
    # same arithmetic, same rounding (np.rint == round-half-to-even, matching Python's
    # round() used before), same majority threshold (>=2 of 4 depths inside the zone).
    t=((np.arange(n)+0.5)/n)[:,None]                       # (n,1)
    base=A[None,:]+t*(B-A)[None,:]                         # (n,2)
    k=np.array([1.0,2.0,3.0,4.0])[None,:,None]             # (1,4,1)
    p=base[:,None,:]+nrm[None,None,:]*(k*res)              # (n,4,2)
    jx=np.rint((p[:,:,0]-gx[0])/res).astype(np.int64)
    iy=np.rint((p[:,:,1]-gy[0])/res).astype(np.int64)
    ok=(iy>=0)&(iy<H)&(jx>=0)&(jx<W)
    z=np.zeros((n,4),bool)
    z[ok]=zone[iy[ok],jx[ok]]
    hit=int((z.sum(axis=1)>=2).sum())
    return hit/n*L

def edge_contacts(facet,valleys,edges,penetrations=None,notches=None,
                  appurtenances=None,res=0.04,shake_measurements=None):
    """edges: list of (A, B, etype, total_lf). Returns {etype: (contact_lf,
    total_lf)} — the contacted_edges[] interface Module 2 consumes. VALLEY-type
    edges are SKIPPED (valley metal/underlayment scoped by the valley's own
    length, never by contact). Contact is honest geometry; Module 2 applies the
    material rules (95% round-to-full on ridge/hip caps, drip edge, transition)."""
    _,_,zone,gx,gy=affected_area(facet,valleys,penetrations,notches,
                                 appurtenances,res=res,return_zone=True,
                                 shake_measurements=shake_measurements)
    out={}
    for A,B,et,tot in edges:
        if 'VALLEY' in et.upper():
            continue
        out[et]=(edge_contact_lf(A,B,zone,gx,gy,res,facet),tot)
    return out


def transition_detect(eA, eB, pA, pB, fA, fB):
    """Return (two_condition, true_transition) for a shared roof edge.

    Production transition primitive formerly hosted in regression_test.py and
    consumed by transition_enumerator.py.
    """
    c1 = abs(pA - pB) > 0.5
    dz = abs(eA[2] - eB[2])
    ln = np.hypot(eA[0] - eB[0], eA[1] - eB[1])
    c2 = degrees(atan2(dz, ln)) <= 15
    c3 = np.dot(fA, fB) > 0
    return (c1 and c2), (c1 and c2 and c3)

# ---- XML helpers ----
def getP(txt,ids):
    P={}
    for c in ids:
        m=re.search(rf'POINT id="{c}" data="([-\d.]+),([-\d.]+),([-\d.]+)"',txt)
        if m: P[c]=tuple(float(z) for z in m.groups())
    return P

def mkframe_pts(points3d_order, eave_a, eave_b):
    """Fall-line frame per rule (D). FRAME v105.1: the basis is facet_basis.facet_frame_axes — THE ONE copy, flat
    facets included (v105 guarded it here only; four other copies still divided by a zero fall)."""
    O,x,up=facet_frame_axes(points3d_order, eave_a, eave_b)
    return lambda p3: np.array([np.dot(np.array(p3,float)-O,x),
                                np.dot(np.array(p3,float)-O,up)])

def excluded_region_aware_notch_fan(facet, holes, seg_a, seg_b, band=2.0, reach=8.0, res=0.4):
    """Excluded-region-aware notch fan (general, topology-driven).

    On a merged slope, a repair cascade must fan into the OPEN roof field -- inside the
    merged facet and OUTSIDE every excluded region. An excluded region is any hole in the
    repair field: a dormer, a courtyard, a chimney chase, a mechanical well, a cluster of
    skylights -- they are ALL treated identically here. The rule never asks what created a
    hole; it only asks which side of the valley leads to open field.

    Determined as PURE GEOMETRY, before any affected_area/cascade runs:
      1. Adjacency: if exactly one side within `band` of the valley is blocked (inside an
         excluded region or outside the facet), fan to the clear side.
      2. Otherwise, fan toward the side whose LOCAL open field (up the fall line, within
         `reach`, inside facet and outside all excluded regions) is larger -- the connected
         repair region, not merely the nearest hole.
      3. If both sides are geometrically symmetric, mark ambiguous and fall back
         deterministically toward the facet centroid x.

    Returns +1 (fan toward +x in the frame) or -1. Independent of cascade fragmentation.
    """
    fp = np.asarray(facet, dtype=float)[:, :2]
    def _pip(pt, poly):
        x, y = pt; n = len(poly); c = False; j = n - 1
        for i in range(n):
            xi, yi = poly[i][0], poly[i][1]; xj, yj = poly[j][0], poly[j][1]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-30) + xi):
                c = not c
            j = i
        return c
    def _in_excluded(pt):
        return any(_pip(pt, h) for h in holes)
    a = np.asarray(seg_a, dtype=float)[:2]; b = np.asarray(seg_b, dtype=float)[:2]
    mid = (a + b) / 2.0
    d = b - a; d = d / (np.linalg.norm(d) + 1e-30)
    nrm = np.array([-d[1], d[0]])
    def _xfan(vec): return 1 if vec[0] > 0 else -1
    p_plus = mid + nrm * band; p_minus = mid - nrm * band
    plus_valid = _pip(p_plus, fp) and not _in_excluded(p_plus)
    minus_valid = _pip(p_minus, fp) and not _in_excluded(p_minus)
    if plus_valid and not minus_valid:
        return _xfan(nrm)
    if minus_valid and not plus_valid:
        return _xfan(-nrm)
    up = float(fp[:, 1].max() - mid[1]); up = up if up > 1.0 else 25.0
    def _open(side):
        perp = side * nrm; area = 0.0
        for i in range(1, int(reach / res) + 1):
            for k in range(0, int(up / res) + 1):
                pt = mid + perp * (i * res) + np.array([0.0, k * res])
                if _pip(pt, fp) and not _in_excluded(pt):
                    area += res * res
        return area
    pa, ma = _open(1), _open(-1)
    if abs(pa - ma) > 3.0:
        return _xfan(nrm) if pa > ma else _xfan(-nrm)
    cen = fp.mean(axis=0)
    return 1 if cen[0] > mid[0] else -1


# =============================================================================================
# FRAME v104d — A RIDGE OR HIP GETS AN IDENTITY: THE CONTINUOUS RUN (ledger entry 94, Joseph)
# =============================================================================================
# "One material is picked for the whole length of the continuous ridge or hip ... wherever there is a ridge or hip
# that is adjoining 2 separate roof coverings then the ridge and hip caps connecting those 2 separate roof systems
# have to be defined by the user." The unit of declaration is the CONTINUOUS RUN — not the segment, not the facet.
# This builds the identity only (the per-run material control waits for a second covering).
#
# A run is a maximal chain of ridge (or hip) LINEs joined end to end: two lines of the SAME type join when they share
# an endpoint (by point id, or by coordinates — EagleView may repeat a corner under two ids across a facet boundary)
# AND they continue in a straight line through it (opposite directions from the shared point). A ridge meeting hips
# at a junction is not collinear with them, so it ends there. The run id is DERIVED FROM ITS MEMBER LINE IDS, never
# from iteration order: "<TYPE>:<ids joined by '+'>", ids in natural order — the same XML always yields the same ids,
# so a run survives a claim save and a re-parse.
RUN_EDGE_TYPES = ("RIDGE", "HIP")
_RUN_COLLINEAR_COS = 0.999       # within ~2.6 degrees: a straight continuation, not a bend
_RUN_POINT_DIGITS = 4            # coordinates equal to 1e-4 ft are the same point


def _run_natural_key(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", str(s))]


def _run_len3d(pts):
    return float(sum(np.linalg.norm(np.subtract(pts[k + 1], pts[k])) for k in range(len(pts) - 1)))


def ridge_hip_runs(geom):
    """The continuous ridge and hip runs of an EagleView geometry (duck-typed: .lines, .points, .faces).

    Returns a list, sorted by run id, of dicts:
      run_id         "<TYPE>:<member ids>" — derived from the members, stable across save and re-parse
      type           "RIDGE" or "HIP"
      edge_ids       the member LINE ids, in natural order
      total_LF       the run's 3D length: the sum of its members' lengths
      facets_left / facets_right
                     the ROOF facets bordering the run on each side (plan view, looking along the run from its
                     first point), facet ids in natural order
    Every RIDGE/HIP line belongs to exactly one run (a partition)."""
    pts = geom.points
    lines = [l for l in geom.lines.values() if l.type in RUN_EDGE_TYPES and len(l.path) >= 2]

    def _key(pid):
        return tuple(round(float(c), _RUN_POINT_DIGITS) for c in pts[pid])

    def _unit(a, b):
        v = np.subtract(pts[b], pts[a]).astype(float)
        n = float(np.linalg.norm(v))
        return v / n if n > 0 else v

    parent = {l.id: l.id for l in lines}

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # endpoint -> [(line, direction pointing AWAY from that endpoint)]
    ends = {}
    for l in lines:
        ends.setdefault(_key(l.path[0]), []).append((l, _unit(l.path[0], l.path[1])))
        ends.setdefault(_key(l.path[-1]), []).append((l, _unit(l.path[-1], l.path[-2])))
    for members in ends.values():
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                (la, da), (lb, db) = members[i], members[j]
                if la.id != lb.id and la.type == lb.type and float(np.dot(da, db)) <= -_RUN_COLLINEAR_COS:
                    ra, rb = _find(la.id), _find(lb.id)
                    if ra != rb:
                        parent[rb] = ra

    groups = {}
    for l in lines:
        groups.setdefault(_find(l.id), []).append(l)

    roof_faces = {fid: f for fid, f in geom.faces.items() if getattr(f, "type", "") == "ROOF"}
    out = []
    for members in groups.values():
        members = sorted(members, key=lambda l: _run_natural_key(l.id))
        ids = [l.id for l in members]
        typ = members[0].type
        total = sum(_run_len3d([pts[p] for p in l.path]) for l in members)
        # a reference direction for the whole run (all members are collinear): the first member, as written
        a0, b0 = members[0].path[0], members[0].path[-1]
        ref = np.subtract(pts[b0], pts[a0]).astype(float)[:2]
        left, right = set(), set()
        idset = set(ids)
        for fid, f in roof_faces.items():
            if not idset.intersection(f.line_ids):
                continue
            fpts = [pts[p] for lid in f.line_ids for p in geom.lines[lid].path if lid in geom.lines]
            cx = float(np.mean([p[0] for p in fpts])); cy = float(np.mean([p[1] for p in fpts]))
            side = ref[0] * (cy - pts[a0][1]) - ref[1] * (cx - pts[a0][0])
            (left if side > 0 else right).add(fid)
        out.append({"run_id": f"{typ}:{'+'.join(ids)}", "type": typ, "edge_ids": ids, "total_LF": total,
                    "facets_left": sorted(left, key=_run_natural_key),
                    "facets_right": sorted(right, key=_run_natural_key)})
    return sorted(out, key=lambda r: _run_natural_key(r["run_id"]))
