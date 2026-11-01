#!/usr/bin/env python3
# Extracted production geometry primitives from regression_test.py.
# CHANGELOG 2026-07-01: stair_edges inner-edge first-row guard included
# (prev_i is None -> ie[n]=vx(ye)), matching the v3.4 regression source.
# CHANGELOG 2026-07-03: unified centerline-extent stair seed for flat valleys; anchor unchanged 3691.

import re
from math import degrees, atan2
import numpy as np
from matplotlib.path import Path
from facet_basis import facet_frame_axes   # FRAME v105.1: THE ONE fall-line basis

# FRAME v95 / step 3b: the shake profile (constants, EXP/STEP, resolve_shake_measurements, _profile_units,
# the tie-in extent, stair_edges) lives in roof_systems/wood_shake/wood_shake_geometry.py. Core never imports
# a package: affected_area() looks the package up in core's registry by the profile's system_id.
from roof_systems import system_for_profile, FacetGrid, PROPAGATE_TO_RIDGE, BOUNDED, SHADOW_RULES

CLEAR_BAND_FT  = 2.0
APPURT_CLEAR_IN= 21.0
BAND=CLEAR_BAND_FT
CLR=APPURT_CLEAR_IN/12.

def appurt_rect(app):
    """v3.2: appurtenance disturbance footprint, by TYPE (never size threshold).
    app REQUIRES 'kind': 'point' or 'dimensioned'.
      POINT (pipe jack, turtle/box vent, turbine): fixed 21x21 square; no dims.
      DIMENSIONED (chimney, skylight, other/custom): footprint + 21in EACH side;
        requires positive w AND h.
    A dimensioned type with missing/zero dims is an ERROR, never a silent
    fallback to a point — the dropdown type is authoritative (Formula Spec §9).
    Returns rectangle polygon in facet frame (feet)."""
    cx,cy=app['cx'],app['cy']; kind=app.get('kind')
    if kind=='point':
        hx=hy=CLR/2.0
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
# footprint + 21" per side: 5-7x the 21" zone. These two tables are the routing rule, and the one place it lives
# in Python.
#   * label -> category mirrors module2_scope_expansion's type switch exactly (the category each label's
#     material line bills); any other label (OTHER, or anything unknown) takes its other_category, as there.
#     appurtenance_routing_regression asserts the mirror against expand_scope itself.
#   * the point categories are the ones appurt_rect's docstring names POINT (pipe jack, turtle/box vent,
#     turbine), plus the power vent and the vent cap. The LABELS that resolve to them must equal page 2's
#     POINT_APPURTENANCE_TYPES (page2.html) — asserted by the same regression, until page 2 reads this table.
# The category only ever forces POINT. Everything else keeps the geometry as declared or measured (OTHER keeps
# the dimensions the user typed; a dimensioned type with no dims still raises in appurt_rect).
APPURT_LABEL_CATEGORY = {
    "CHIMNEY": "CHIMNEY_FLASH", "SKYLIGHT": "SKYLIGHT_FLASH", "PIPE": "PIPE_JACK_FLASH",
    "TURTLE": "BOX_VENT", "TURBINE": "TURBINE_VENT", "POWER_VENT": "POWER_VENT",
}
POINT_APPURTENANCE_CATEGORIES = frozenset({"PIPE_JACK_FLASH", "BOX_VENT", "TURBINE_VENT", "POWER_VENT", "VENT_CAP"})
POINT_APPURTENANCE_TYPES = tuple(lab for lab, cat in APPURT_LABEL_CATEGORY.items() if cat in POINT_APPURTENANCE_CATEGORIES)

def appurtenance_category(kind_label, other_category=None):
    """The category an appurtenance resolves to: its label's, else (OTHER / unknown) its other_category."""
    lab = str(kind_label or "").strip().upper()
    if lab in APPURT_LABEL_CATEGORY:
        return APPURT_LABEL_CATEGORY[lab]
    return str(other_category).strip() if other_category not in (None, "") else None

def appurtenance_base_fits_point_zone(app_geom):
    """FRAME v103 (Joseph, 2026-10-30): does the measured base fit inside the 21in square in BOTH axes?
    Per axis, never by area — a 6in x 30in base sticks out of the square. No measured base (a hand-placed
    marker) fits. Compared against APPURT_CLEAR_IN, the one definition of the zone."""
    lim = APPURT_CLEAR_IN / 12.0
    w = float(app_geom.get("w") or 0.0); h = float(app_geom.get("h") or 0.0)
    return w <= lim and h <= lim

def appurtenance_zone_geometry(app_geom, kind_label, other_category=None):
    """Route an appurtenance's geometry to its disturbance zone BY TYPE. A point category whose base fits the 21in
    square in both axes (or has no measured base) -> kind "point" (appurt_rect's fixed 21"x21" zone);
    anything else -> app_geom unchanged.

    FRAME v103, Joseph's ruling: over 21in it is not a vent flashing, it is a curb — a DIMENSIONED appurtenance,
    base + 21in each side, as a chimney gets. The step at the boundary (a 21in base scopes 7 EA, a 22in base the
    ring) is RULED, not an artefact: the two branches are different jobs. Do not floor, taper or blend it. The
    predicate only ever WITHHOLDS point routing; it never routes a non-point label by size.

    The routed geometry KEEPS any measured w/h. appurt_rect ignores them for a point, so they no longer size the
    ZONE — but module1_m2interface._surface_appurts reads exactly those keys for Appurt.affected_SF, which drives
    APPURT_IWS. Joseph (v102 Q2): IWS follows the measured footprint. Keeping the keys is the separation: the zone
    is the type's, the IWS is the measurement's, and module1_m2interface stays byte-identical."""
    if app_geom is None or not hasattr(app_geom, "keys"):
        return app_geom
    if appurtenance_category(kind_label, other_category) not in POINT_APPURTENANCE_CATEGORIES:
        return app_geom
    if not appurtenance_base_fits_point_zone(app_geom):
        return app_geom
    routed = dict(app_geom)
    routed["kind"] = "point"
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

def _grid_cache_key(facet,pens,nots,res,prof):
    return (_poly_key(facet),
            tuple(_poly_key(h) for h in (pens or [])),
            tuple(_poly_key(h) for h in (nots or [])),
            float(res),
            float(prof["width_in"]), float(prof["exposure_in"]),
            str(prof["system_id"]))      # FRAME v104b (K9): two systems at the same dimensions are different grids

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

def _area_cache_key(facet,valleys,pens,nots,apps,res,prof,return_zone,bands=None):
    """COMPLETE key: every input affected_area's result depends on. Any difference in
    facet, valleys, penetration holes, notch holes, appurtenances, resolution, the
    resolved measurements, or the ROOF SYSTEM that resolved them is a MISS, so a stale
    result can never be reused (across facets, measurement profiles, roofs, or systems).
    FRAME v104b (K9): until v104b the system id was missing, so this claim was false — two
    systems at the same width and exposure shared one entry. Dispatch made it reachable."""
    return (_poly_key(facet),
            _hashable_valleys(valleys),
            tuple(_poly_key(h) for h in (pens or [])),
            tuple(_poly_key(h) for h in (nots or [])),
            _hashable_apps(apps),
            float(res),
            float(prof["width_in"]), float(prof["exposure_in"]),
            str(prof["system_id"]),   # FRAME v104b (K9)
            bool(return_zone),
            _band_key(bands))

def clear_area_cache():
    _AREA_CACHE.clear()

def _facet_grid(facet,pens,nots,res,prof):
    """Return (gx,gy,X,Y,pts,inside,field) for this facet, from cache when the
    exact same inputs were seen before."""
    key=_grid_cache_key(facet,pens,nots,res,prof)
    hit=_GRID_CACHE.get(key)
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
    if len(_GRID_CACHE)>=_GRID_CACHE_MAX: _GRID_CACHE.clear()
    _GRID_CACHE[key]=val
    return val

def affected_area(facet,valleys,penetrations=None,notches=None,
                  appurtenances=None,res=0.04,return_zone=False,
                  shake_measurements=None, width_in=None, exposure_in=None,
                  transition_bands=None):
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
                             transition_bands)
    except TypeError:
        _key=None                                    # unhashable input -> just compute, never cache
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
    for app in (appurtenances or []):
        rect=Path(appurt_rect(app))
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
