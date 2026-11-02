#!/usr/bin/env python3
"""
roof_systems/wood_shake/wood_shake_geometry.py — the wood-shake profile and valley disturbance strategy.

FRAME v95 / Migration Plan step 3b. Moved out of geometry_core.py, code unchanged except where marked "FRAME v95":
the profile constants, EXP / STEP, DEFAULT_SHAKE_MEASUREMENTS, resolve_shake_measurements, _profile_units (with
the CSSB joint-offset assertion), TIE_IN_COURSES / three_course_extent_ft (the v90 tie-in authority) and
stair_edges (the wood-shake valley disturbance).

The dependency runs ONE way: this package imports core (geometry_core's 2 ft clear band, the registry); core
never imports this package. It registers itself at import (core/registry/roof_systems.py), and
geometry_core.affected_area() looks it up by the profile's system_id.
"""
import numpy as np

from geometry_core import BAND        # core's 2 ft clear band: a repair-practice dimension, not a shake one
from roof_systems import register, PROPAGATE_TO_RIDGE
import wood_shake_categories   # FRAME v97: the package registers the category ids it owns, on any entry

SYSTEM_ID = "wood_shake"

EXPOSURE_IN    = 10.0
SHAKE_WIDTH_IN = 7.0
JOINT_OFFSET_IN= 1.5
LATERAL_STEP_IN= SHAKE_WIDTH_IN/2.0
assert LATERAL_STEP_IN >= JOINT_OFFSET_IN, "lateral_step violates CSSB joint offset"
EXP=EXPOSURE_IN/12.; STEP=LATERAL_STEP_IN/12.


DEFAULT_SHAKE_MEASUREMENTS = {
    "width_in": SHAKE_WIDTH_IN,
    "exposure_in": EXPOSURE_IN,
    "length_in": 24.0,
    "thickness": "3/4",
    "measurement_source": "default — not field-measured",
}


def resolve_shake_measurements(measurements=None):
    """Return validated per-job shake measurements with legacy defaults.

    A single measured width drives both the shake count and stagger. Exposure
    drives the course grid. Width below 3 in is rejected because width/2 must
    satisfy the CSSB 1.5 in joint-offset floor. Exposure above the length/
    thickness code cap is allowed with a warning flag because field reality may
    differ and must be documented.
    """
    # FRAME v95: the "wood_shake" default lives HERE, in the package, never in core. A profile labelled for
    # another system is not this package's to resolve.
    if measurements and dict(measurements).get("system_id") not in (None, "", SYSTEM_ID):
        raise ValueError(f"wood_shake cannot resolve a profile labelled system_id={dict(measurements).get('system_id')!r}")
    src = dict(DEFAULT_SHAKE_MEASUREMENTS)
    if measurements:
        src.update({k: v for k, v in dict(measurements).items() if v not in (None, "")})
    width = float(src.get("width_in", SHAKE_WIDTH_IN))
    exposure = float(src.get("exposure_in", EXPOSURE_IN))
    length = float(src.get("length_in", 24.0))
    thickness = str(src.get("thickness", "3/4"))
    if width <= 0 or exposure <= 0:
        raise ValueError("shake width and exposure must be greater than 0")
    if width < 3.0:
        raise ValueError("shake width must be at least 3.0 in so width/2 satisfies the 1.5 in joint-offset floor")
    if width > 14.0:
        raise ValueError("shake width exceeds sane upper bound of 14 in")
    if exposure > max(length / 2.0, 1.0):
        raise ValueError("shake exposure exceeds sane upper bound of length/2")
    code_max = 7.5 if (length == 18.0 or thickness in {"3/8", "0.375", "thin"}) else 10.0
    exposure_over_code_max = exposure > code_max + 1e-9
    return {
        "width_in": width,
        "exposure_in": exposure,
        "length_in": length,
        "thickness": thickness,
        "lateral_step_in": width / 2.0,
        "exposure_over_code_max": exposure_over_code_max,
        "code_max_exposure_in": code_max,
        "measurement_source": src.get("measurement_source") or src.get("source") or "field-measured",
        "system_id": SYSTEM_ID,          # FRAME v95: a resolved profile names its system (additive key)
    }


def _profile_units(shake_measurements=None):
    prof = resolve_shake_measurements(shake_measurements)
    step_in = prof["lateral_step_in"]
    assert step_in >= JOINT_OFFSET_IN, "lateral_step violates CSSB joint offset"
    return prof["exposure_in"] / 12.0, step_in / 12.0

TIE_IN_COURSES = 3          # Joseph 2026-10-17: the tie-in ends at the top of the 3rd course

def three_course_extent_ft(shake_measurements=None):
    """Up-slope extent of the transition tie-in, in FEET.

    Course n's butt sits at (n-1) * exposure; the top of course n is that plus the piece length.
    This is NOT courses * exposure, and it is NOT a constant: a 24 in shake at 10 in exposure gives
    44 in, an 18 in shake at 7.5 in gives 33 in. The CSSB 914 mm (36 in) felt strip it replaces was a
    fixed dimension and is wrong in both directions.
    """
    prof = resolve_shake_measurements(shake_measurements)
    return ((TIE_IN_COURSES - 1) * float(prof["exposure_in"]) + float(prof["length_in"])) / 12.0

def stair_edges(vs,va,fan,top_y,y0,exposure_in=None,shake_width_in=None):
    """Unified per-course band. Below a rising valley's apex the inner edge rides
    the valley line (shared edge with the neighbor) and the outer edge steps out.
    At/above the apex -- and for the whole of a flat valley -- the band fans BOTH
    ways from the valley's cross-slope extent, up to the boundary. The 'both ways'
    open is fan-independent (min edge steps left, max edge steps right)."""
    measurements = {"exposure_in": exposure_in or EXPOSURE_IN, "width_in": shake_width_in or SHAKE_WIDTH_IN}
    exp_ft, step_ft = _profile_units(measurements)
    vs=np.asarray(vs,float); va=np.asarray(va,float); apex=va[1]
    flat = abs(va[1]-vs[1]) < 1e-9
    ax_lo = min(vs[0],va[0]) if flat else float(va[0])
    ax_hi = max(vs[0],va[0]) if flat else float(va[0])
    def vx(yy):
        if yy<=apex and apex!=vs[1]:
            t=(yy-vs[1])/(apex-vs[1]); return vs[0]+t*(va[0]-vs[0])
        return va[0]
    nc=int(np.ceil((top_y-y0)/exp_ft))+1
    oe=np.full(nc,np.nan); ie=np.full(nc,np.nan)
    n0=max(int(np.floor((vs[1]-y0)/exp_ft+1e-9)),0)
    prev_o=prev_i=None
    for n in range(n0,nc):
        yy=y0+n*exp_ft; ye=max(yy,vs[1])
        if ye<=apex and apex!=vs[1]:
            # BELOW apex (rising valley): inner edge = valley line, outer edge steps out. UNCHANGED.
            be=vx(ye)+fan*BAND
            oe[n]=be if prev_o is None else (max(be,prev_o+fan*step_ft) if fan>0 else min(be,prev_o+fan*step_ft))
            ie[n]=vx(ye)
        else:
            # AT/ABOVE apex (or flat valley): fan BOTH ways from the extent, band on fan side.
            seed_lo=ax_lo-(BAND if fan<0 else 0.0)
            seed_hi=ax_hi+(BAND if fan>0 else 0.0)
            if prev_o is None:
                ie[n]=seed_lo; oe[n]=seed_hi
            else:
                cur_lo=min(prev_o,prev_i); cur_hi=max(prev_o,prev_i)
                ie[n]=min(seed_lo, cur_lo-step_ft)   # min edge steps left (outward)
                oe[n]=max(seed_hi, cur_hi+step_ft)   # max edge steps right (outward)
        prev_o=oe[n]; prev_i=ie[n]
    return oe,ie,nc

def valley_disturbance(event, facet, grid, profile):
    """The wood-shake VALLEY strategy under the disturbance contract (Package Contract §1 item 3):
    returns (mask, shadow_rule), a boolean mask over core's facet grid plus PROPAGATE_TO_RIDGE. Never an
    area. These are the lines that sat in geometry_core.affected_area's valley loop in v94, unchanged; core
    keeps the shadow fill, the clip to the field, the union and the area."""
    vs,va,fan = event
    vs=np.asarray(vs,float); va=np.asarray(va,float)
    X, Y = grid.X, grid.Y
    top_y=max(p[1] for p in facet); y0=min(p[1] for p in facet)
    exp_ft = profile["exposure_in"] / 12.0
    oe,ie,nc=stair_edges(vs,va,fan,top_y,y0,exposure_in=profile["exposure_in"],shake_width_in=profile["width_in"])
    nidx=np.clip(((Y-y0)//exp_ft).astype(int),0,nc-1)
    lo=np.minimum(oe[nidx],ie[nidx]); hi=np.maximum(oe[nidx],ie[nidx])
    inband=(X>=lo-1e-9)&(X<=hi+1e-9)&(Y>=vs[1])
    return inband, PROPAGATE_TO_RIDGE


# Registration at import. claims_unlabelled_profiles=True is BRIDGE 1 (Joseph 2026-10-26): every v88-v94 caller
# passes a profile with no system_id, and THIS package — not core — declares it owns them. Retires at Migration
# Plan step 4, when ProjectConfig supplies the system id. Only the VALLEY strategy crosses the interface in 3b;
# transition bands and appurtenance rects are still core's bounded branches inside affected_area (3c or later).
def _expand_scope(iface, *args, **kwargs):
    """FRAME v104b: the package's scope engine, as registered with core (bridge 6 retired: callers ASK the registry for
    it). module2_scope_expansion imports THIS module (three_course_extent_ft), so it cannot be imported here at module
    level without a cycle; the import is at call time, and returns the very function the callers used to import."""
    from module2_scope_expansion import expand_scope
    return expand_scope(iface, *args, **kwargs)


def _course_top_ft(profile, courses=None):
    """FRAME v105.4: wood shake's OWN course geometry, as registered with core — the top of course n is (n-1) x exposure
    + the piece length (three_course_extent_ft's arithmetic). `courses=None` is this package's own tie-in count,
    TIE_IN_COURSES, which stays here as the default; a caller with its own ruling passes an explicit count."""
    prof = resolve_shake_measurements(profile)
    n = TIE_IN_COURSES if courses is None else int(courses)
    return ((n - 1) * float(prof["exposure_in"]) + float(prof["length_in"])) / 12.0


register(SYSTEM_ID,
         resolve_profile=resolve_shake_measurements,
         disturbance={"VALLEY": valley_disturbance},
         expand_scope=_expand_scope,
         claims_unlabelled_profiles=True,
         course_top_ft=_course_top_ft)
