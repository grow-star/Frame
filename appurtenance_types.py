"""APPURTENANCE TYPE ATTRIBUTES — what an item IS, independent of the roof it sits on.

FRAME v106.6g. This module exists because of a diagnosis Joseph made (2026-11-06) after four builds of
appurtenance defects in a row: "I just couldn't understand why appurtenances were being so difficult, and
thought maybe what we discussed was the issue since I keep hearing things live in different spots."

He was right, and the scattering was the cause. FRAME's architecture is already the one he described — an
appurtenance is a data record (scope_contract.Appurt), a roof-system package is an object whose methods get
called on it (roof_systems.RoofSystem is a namedtuple of function references, one of them expand_scope), and
the registry dispatches. What was wrong is that THREE attributes belonging to the TYPE did not live with the
type:

  1. point vs dimensioned        -> was POINT_APPURTENANCE_CATEGORIES in core, PLUS a size test that could
                                    override it, which Formula Spec v3.4 section 9 explicitly forbids
  2. the standard flashing base  -> did not exist at all, so the MEASURED polygon was used instead. That is
                                    why an XML-derived box vent and a hand-placed one behaved differently,
                                    which is the complaint Joseph raised before either of us knew the cause
  3. the per-side allowance      -> correctly the package's, but one number where two are needed

(1) and (2) live here. (3) stays with the package, where it belongs, keyed by the flashing method below.

WHY HERE AND NOT IN CORE. geometry_core says it "keeps the rectangle's SHAPE (geometry) and holds none of
its SIZE (material)". A standard flashing base IS a size, so core must not hold it. But it is not a package's
either: a box vent is a 12in box vent on shake, on modified bitumen and on asphalt. It is shared vocabulary,
exactly like shared_category_registry, and it lives beside it.

THE DISTINCTION IS FLASHING METHOD, NOT SIZE. Joseph, 2026-11-06: "Skylights and chimneys genuinely need a
21 inch clearance around the perimeter of these areas to get an 18 inch strip around the dimensional
appurtenance. The smaller stuff doesn't need an 18 inch strip around the flashing."

  CURB_FLASHED (chimney, skylight)  -> an 18in IWS strip around the perimeter: 21in per side on shake.
  BASE_FLASHED (vents, pipe jacks)  -> room to set the flange plus a small strip: about 6in per side.

QA had proposed collapsing both into one rule. Joseph refused and was right: measured, that would have
billed FOUR TO SEVEN TIMES too much for every vent on a shake roof, because a 12in box vent is 3.06 SF as a
fixed point square and 20.25 SF as a measured footprint plus 21in on each side.

TWO KEYS, ONE DECLARATION. A row reaches the engine either as a dropdown LABEL ("TURTLE") or, when the user
picks "other" and then names the real thing, as kind_label OTHER plus a billing CATEGORY ("BOX_VENT"). Those
are two names for one physical object, so each object is declared ONCE below, carrying its category, and the
table is indexed both ways. The category index is not a convenience: page 2 offers eleven categories under
OTHER and that is a live scoping path, which v106.6g's FIRST DRAFT broke. It resolved a category by scanning
the LABEL table for a matching one, so a category with no label of its own — VENT_CAP — fell through to
"unknown", went curb-flashed, and billed about 19 SF instead of about 3 on shake. The builder caught it and
stopped. Nothing had read the hand-written point set that used to carry VENT_CAP, so re-adding it there
would have changed nothing; a category must be LOOKED UP, which is what happens now.

EVERY CATEGORY PAGE 2 OFFERS IS DECLARED HERE, EXPLICITLY, including the four that are measured anyway. A
category that falls through to the default is indistinguishable from one somebody forgot, and that is exactly
how the VENT_CAP defect hid. appurtenance_routing_regression asserts the two lists against each other, so a
category added to page 2 without a declaration here fails rather than defaulting.

AN UNKNOWN TYPE IS CURB_FLASHED. What follows from that depends on the item's shape, and the distinction
matters because the two paths bill very differently:

  * a DIMENSIONED item is measured — its own footprint plus the package's curb allowance per side. This is
    the conservative reading on a claim: an unidentified item gets the larger disturbance, visible and
    arguable rather than quietly short. It is also what the tree did before this module existed, which is
    why the frozen Yager anchor does not move — the anchor's only appurtenance is F69 on F7, "Facet P
    chimney appurtenance", carrying no kind_label at all.
  * a POINT item is NOT measured. It keeps its point shape and takes the bare allowance square: 21in on
    shake, 6in on a membrane. On a membrane that is 0.25 SF, the SMALLEST zone the system can produce and
    about a fourteenth of a declared pipe jack's 3.36 — so for a point item the "conservative direction"
    claim is false, and an earlier draft of this docstring said otherwise. The behaviour predates v106.6g
    and is unchanged by it. It is recorded as a known-open for Joseph's ruling, not fixed here.
"""
from __future__ import annotations

from collections import namedtuple
from typing import Optional

BASE_FLASHED = "BASE_FLASHED"
CURB_FLASHED = "CURB_FLASHED"
FLASHING_METHODS = (BASE_FLASHED, CURB_FLASHED)
FLASHING_METHOD_SET = frozenset(FLASHING_METHODS)

# standard_base_in is the type's COMMON FLASHING BASE SIZE, in inches, square.
# None means "measure it" — the item has no standard size, so its own footprint is used.
# category is the registry id this type BILLS as, and the second key this table is indexed by.
AppurtType = namedtuple("AppurtType", "flashing_method standard_base_in category note")

# Joseph confirmed every base size below on 2026-11-06, against the question "what is the common flashing
# base size for each of these". They are what makes an item of a type behave identically whether EagleView
# measured it or a user placed it, which was his stated requirement: "I just want every box vent to act the
# same whether XML derived or user placed. Same for pipe jacks, and turbine vents, and 6 inch pipe jacks."
#
# Keyed by the page-2 dropdown LABEL. Each entry's `category` must equal geometry_core's
# APPURT_LABEL_CATEGORY for the same label; the gate asserts it, because this module cannot import
# geometry_core (geometry_core imports this one).
APPURTENANCE_TYPES = {
    "PIPE":       AppurtType(BASE_FLASHED, 10.0, "PIPE_JACK_FLASH", "pipe jack flashing, 1.5-2in pipe"),
    "TURTLE":     AppurtType(BASE_FLASHED, 12.0, "BOX_VENT", "box / turtle vent"),
    "TURBINE":    AppurtType(BASE_FLASHED, 14.0, "TURBINE_VENT", "turbine vent"),
    "POWER_VENT": AppurtType(BASE_FLASHED, 18.0, "POWER_VENT", "power attic vent"),
    "CHIMNEY":    AppurtType(CURB_FLASHED, None, "CHIMNEY_FLASH",
                             "measured; an 18in IWS strip around the perimeter"),
    "SKYLIGHT":   AppurtType(CURB_FLASHED, None, "SKYLIGHT_FLASH",
                             "measured; an 18in IWS strip around the perimeter"),
}

# Things page 2 offers as a CATEGORY under "other" but which have no dropdown label of their own. They are
# reachable only as kind_label OTHER plus other_category, and that is a real scoping path on all three
# surfaces (page2.html: APPURTENANCE_CATEGORIES, "Defined ONCE and used by all three surfaces").
#
# VENT_CAP's 10in base is the figure Joseph gave on 2026-11-06 listing the standard flashing bases, and it is
# the right figure under BOTH readings of this id, which is why it is safe to set before v106.6h renames
# anything: as the Broan-style exhaust cap Xactimate means by "vent cap" it is a capped penetration with a
# base of its own; as the rain cap FRAME's comparison layer currently means by it, Joseph's rule is that it is
# "sized by the jack beneath it — no zone of its own, same hole", which is a base, not a bare clearance
# square. v106.6h settles the NAMES (VENT_CAP taking Xactimate's meaning, a new RAIN_CAP for the rain cap and
# collar); it does not change this geometry.
#
# The four measured ones are declared, not left to the default, so that the coverage check has teeth.
CATEGORY_ONLY_TYPES = {
    "VENT_CAP":         AppurtType(BASE_FLASHED, 10.0, "VENT_CAP", "Broan-style exhaust cap"),
    "ENDWALL_FLASH":    AppurtType(CURB_FLASHED, None, "ENDWALL_FLASH", "measured; a run, not a penetration"),
    "RIDGE_VENT":       AppurtType(CURB_FLASHED, None, "RIDGE_VENT", "measured; a run along the ridge"),
    "STEP_FLASH":       AppurtType(CURB_FLASHED, None, "STEP_FLASH", "measured; a run up a wall"),
    "TRANSITION_FLASH": AppurtType(CURB_FLASHED, None, "TRANSITION_FLASH",
                                   "measured; a run along a system boundary"),
}

# The second index. Built from the same records, so a type cannot be base-flashed by one key and
# curb-flashed by the other.
APPURTENANCE_TYPES_BY_CATEGORY = {t.category: t for t in APPURTENANCE_TYPES.values()}
for _cat, _t in CATEGORY_ONLY_TYPES.items():
    assert _cat == _t.category, f"category-only entry {_cat!r} declares category {_t.category!r}"
    assert _cat not in APPURTENANCE_TYPES_BY_CATEGORY, (
        f"{_cat!r} is already reachable through a label; declare it once, in APPURTENANCE_TYPES")
    APPURTENANCE_TYPES_BY_CATEGORY[_cat] = _t
del _cat, _t


def _norm(v) -> str:
    return str(v or "").strip().upper()


def resolve_type(appurt_type=None, category=None) -> Optional[AppurtType]:
    """The declared AppurtType for a row: by dropdown LABEL first, then by billing CATEGORY.

    This is the one resolver. A row saying OTHER carries no usable label, so its category is what names the
    physical thing — and a category with no label of its own (VENT_CAP) is reachable ONLY this way. Returns
    None when neither key is declared, which the callers below read as "unknown"."""
    t = APPURTENANCE_TYPES.get(_norm(appurt_type))
    if t is not None:
        return t
    return APPURTENANCE_TYPES_BY_CATEGORY.get(_norm(category))


def flashing_method(appurt_type: Optional[str] = None, category: Optional[str] = None) -> str:
    """How this item is flashed, which is what decides its disturbance footprint.

    An unknown type is CURB_FLASHED. See the module docstring for what that means for a dimensioned item
    (measured, the larger allowance) versus a point item (the bare allowance square)."""
    t = resolve_type(appurt_type, category)
    return t.flashing_method if t is not None else CURB_FLASHED


def standard_base_in(appurt_type: Optional[str] = None,
                     category: Optional[str] = None) -> Optional[float]:
    """The item's common flashing base size in inches, or None when it must be measured."""
    t = resolve_type(appurt_type, category)
    return t.standard_base_in if t is not None else None


def is_base_flashed(appurt_type: Optional[str] = None, category: Optional[str] = None) -> bool:
    return flashing_method(appurt_type, category) == BASE_FLASHED


def declared_types():
    """Every LABEL this table knows, sorted — for a gate that wants to enumerate rather than hard-code."""
    return tuple(sorted(APPURTENANCE_TYPES))


def declared_categories():
    """Every CATEGORY this table knows, sorted. A gate asserts page 2's offered list against this."""
    return tuple(sorted(APPURTENANCE_TYPES_BY_CATEGORY))


# A measurement this many times the type's standard base says the label is probably not what the item is.
# Joseph, 2026-11-07: "I can't have the program just accept a label from a user when it is obviously not even
# close ... Pershing should give a prompt or warning to confirm the label since the size suggests otherwise."
#
# WHY A WARNING IS NOT OPTIONAL HERE, and why sizing the zone from the measurement does not make it so.
# Taking the larger of base and measurement fixes the zone's EXTENT. It cannot fix its BORDER, because the
# border comes from the flashing method and the method comes from the label. Measured on Yager's F70, which
# is 24in x 46.3in and is plainly a chimney:
#       labelled PIPE / TURTLE / POWER_VENT (base-flashed, 6in a side) -> 14.64 SF
#       labelled CHIMNEY / SKYLIGHT        (curb-flashed, 21in a side) -> 25.8016 SF
# So a mislabel still under-scopes by 11.16 SF, 43%, with the extent already truthful. Only the user can
# correct a flashing method, so the only fix is to ask - which is what this threshold exists to trigger.
#
# WHY 2.0. It has to clear the ordinary case and catch the real one, and on the live fixtures it does: a
# genuine pipe jack's EagleView polygon runs a little over its nominal base (Devore F48 and Pershing F52 both
# measure 12in against a 10in standard, 1.2x) while the mislabels are nowhere near (F70 at 4.6x, Yager F71 at
# 7.8x, Pershing F54 at 13.8x). It is a WARNING threshold, never a billing one: the figure is already
# truthful whether or not this fires, so getting it slightly wrong costs noise rather than money. That is
# also why it is one number here rather than a per-package or per-type table.
MISLABEL_FACTOR = 2.0


def size_suggests_mislabel(appurt_type=None, category=None, width_ft=None, height_ft=None):
    """Does this item measure so much more than its declared type's standard base that the label is in doubt?

    Returns None when there is nothing to doubt - no declared type, no standard base (a curb-flashed item is
    measured by definition, so a large one says nothing), or no measurement (a hand-placed point states no
    size, so there is nothing to disagree with). Otherwise returns the facts a caller needs to say so:
    (standard_base_in, measured_in, factor), measured on whichever axis is worse."""
    t = resolve_type(appurt_type, category)
    if t is None or t.standard_base_in is None:
        return None
    try:
        worst_ft = max(float(width_ft or 0.0), float(height_ft or 0.0))
    except (TypeError, ValueError):
        return None
    if worst_ft <= 0.0:
        return None
    measured_in = worst_ft * 12.0
    if measured_in < t.standard_base_in * MISLABEL_FACTOR:
        return None
    return (t.standard_base_in, round(measured_in, 1), round(measured_in / t.standard_base_in, 1))


def mislabel_citation(mis):
    """The clause a package appends to a scope line's citation when size_suggests_mislabel fired.

    THE CATALOG OWNS THE WORDING, NOT THE PACKAGES. v106.6g2 first wrote this f-string three times - once
    on the coursed side, twice on the membrane side - and three copies of a sentence drift. What the
    catalog does NOT own is the decision to flag or where the clause lands: each package applies this to
    its own line, because which line carries an appurtenance differs by material (one on shake, up to three
    on a membrane) and that is the package's business. See the module docstring.

    Takes size_suggests_mislabel's triple, returns a clause that begins with '; ' so it concatenates onto
    an existing citation. Returns '' for None so a caller may append unconditionally."""
    if mis is None:
        return ""
    standard_in, measured_in, factor = mis
    return (f"; SIZE DOES NOT MATCH THE LABEL: measures {measured_in:g}in against a "
            f"{standard_in:g}in standard base ({factor:g}x) — confirm the type")
