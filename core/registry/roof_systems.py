"""
core/registry/roof_systems.py — the roof-system registry (FRAME v95 / Migration Plan step 3b).

Shared core NEVER imports a roof-system package. A package imports THIS module and registers itself at import
time; core looks the package up by the profile's `system_id`. The dependency points one way: package -> core.

    register(system_id, resolve_profile=..., disturbance={...}, expand_scope=..., claims_unlabelled_profiles=False)
    get(system_id)               -> RoofSystem          RAISES on an unknown id
    system_for_profile(profile)  -> RoofSystem          RAISES when it cannot be decided — never guesses

The disturbance contract (Package Contract §1 item 3, Shared-Core Contract §4.3): for each repair-event type it
supports, a package supplies `fn(event, facet, grid, profile) -> (mask, shadow_rule)`, a boolean mask over the
facet grid plus PROPAGATE_TO_RIDGE or BOUNDED. Never an area, never a scope line. The grid, the clipping, the
union, the area integration and the edge-contact measurement stay in core.

NO DEFAULTS HERE. This module names no roof system. A profile carrying an unknown `system_id` raises.

TWO BRIDGES, both retiring at Migration Plan step 4, when ProjectConfig supplies the system and the app wires
its packages explicitly (Joseph 2026-10-26):
  1. UNLABELLED PROFILES. Every v88-v94 caller passes a profile with no `system_id` (None, or a raw
     {width_in, exposure_in} dict). One package may DECLARE, at register(), that it owns such profiles
     (Shared-Core Contract §1.2 rule 5: an absent field must mean "behave as before"). The claim is the
     package's own; core holds no system name. With no claimant an unlabelled profile raises; a second
     claimant raises at register().
  2. REGISTRATION BY IMPORT. A package registers when something imports it. An entry point that reaches
     core geometry without importing any package gets the actionable error below, not a KeyError.

FRAME v104a — WHICH ROOF SYSTEM DOES A FACET CARRY? (the per-facet contract; the first of three mixed-roof builds)
    system_for_facet(face_id, confirmed_selection)   -> system_id   one authority
    validate_roof_system_selection(sel, roof_face_ids)              raises on a bad declaration; a no-op when absent
    roof_system_keys(selection)                       -> dict        the two keys, exactly as given, for carrying
Joseph, 2026-10-30: one predominant system per claim, plus a map of exceptions. confirmed_selection carries
`predominant_system_id` and `facet_systems` ({face_id: system_id}, EXCEPTIONS ONLY: a facet absent from it carries
the predominant). A map, not a field on facet rows, because a repair facet has no row. NOTHING READS THIS TO DECIDE
SCOPE YET (v104b dispatches on it); with one package registered every claim renders byte-identically.
  BRIDGE 4 MEMBER (new in v104a): a claim that declares neither key resolves to THE SOLE registered roof system, and
  zero or two-plus registered RAISES (RegistryWiringError, as field_category_id() does). Retires when every claim
  declares predominant_system_id.
"""
from __future__ import annotations

from collections import namedtuple
from collections.abc import Mapping
from types import MappingProxyType

from appurtenance_types import BASE_FLASHED as _BASE_FLASHED   # FRAME v106.6g: a WORD, not a size. Core
from appurtenance_types import CURB_FLASHED as _CURB_FLASHED   # still holds no material number of its own.
from shared_category_registry import RegistryWiringError   # FRAME v104a: the bridge-4 wiring error, one type
from shared_category_registry import set_default_category_package   # FRAME v106.4: one claim, pushed down a layer

PROPAGATE_TO_RIDGE = "PROPAGATE_TO_RIDGE"     # the zone is shadow-filled up-slope to the top of its field run
BOUNDED = "BOUNDED"                           # the zone is exactly the mask, clipped to the field
SHADOW_RULES = frozenset((PROPAGATE_TO_RIDGE, BOUNDED))

EVENT_TYPES = frozenset(("VALLEY", "TRANSITION", "APPURTENANCE", "PENETRATION", "FACET_REPLACEMENT"))

# What core hands a disturbance strategy: the facet grid, read-only by contract (Package Contract §1.1).
FacetGrid = namedtuple("FacetGrid", "gx gy X Y")

# FRAME v104b: `expand_scope` — the package's scope engine — is a REQUIRED registration field. The engine is ASKED FOR
# (get(system_id).expand_scope), never imported by name: that retires bridge 6 ("the scope engine is called, not
# dispatched"). With one package registered, dispatch resolves to the very same function the imports reached.
RoofSystem = namedtuple("RoofSystem", "system_id resolve_profile disturbance claims_unlabelled_profiles expand_scope "
                                       "course_top_ft tie_in_courses appurtenance_clearance_in "
                                       "appurtenance_base_clearance_in",
                        defaults=(None, None, None, None))  # FRAME v105.4: course_top_ft OPTIONAL; v106.3b:
                                                       # tie_in_courses; v106.6c: appurtenance_clearance_in;
                                                       # v106.6g: appurtenance_base_clearance_in


class RoofSystemRegistryError(LookupError):
    """The registry cannot decide which roof system a request belongs to. This is a WIRING error, never a
    geometry error, and the message says how to fix it."""


_SYSTEMS: "dict[str, RoofSystem]" = {}
_UNLABELLED_CLAIMANT = None


def register(system_id, *, resolve_profile, disturbance, expand_scope, claims_unlabelled_profiles=False,
             course_top_ft=None, tie_in_courses=None, appurtenance_clearance_in=None,
             appurtenance_base_clearance_in=None):
    """Called BY a package, at its own import. Idempotent for an identical registration. A second, DIFFERENT
    registration of one id raises (one rule, one home), as does a second claimant of unlabelled profiles.

    FRAME v105.4: `course_top_ft(profile, courses=None) -> feet` is OPTIONAL — the package's own course geometry, the
    height to the top of course `courses` (None = the package's own tie-in count). A covering that is not coursed (a
    membrane, a standing-seam panel) has no honest answer and declines by omitting it; asking it then RAISES, named
    (see course_top_ft below). Like expand_scope, it joins the idempotency comparison.

    FRAME v106.3b: `tie_in_courses` is OPTIONAL — a positive int, THIS package's manufacturer count for how many
    courses of the NEIGHBOURING coursed covering its own material must run under at a system boundary. It is the
    other half of the pair `course_top_ft` belongs to, and the two halves are deliberately owned by different
    packages (see system_boundary_tie_in_ft below). MODBIT declares 3 — Mule-Hide `MH-MB-WFT06` note 2 ("SAMB
    membrane must extend a minimum of 12" vertically up the slope and under a minimum of 3 courses of shingles")
    and Carlisle `U-13E` note 1 ("regardless of membrane exposure extend membrane under first 3 courses").
    A coursed covering declines it by omission: wood shake's own 3-course figure is CSSB Figure 10's count for a
    STEEP-TO-STEEP pitch transition, which is a different fact that happens to share a value, and it stays inside
    that package (wood_shake_geometry.TIE_IN_COURSES). It joins the idempotency comparison.

    FRAME v106.6c: `appurtenance_clearance_in` is REQUIRED OF EVERY PACKAGE THAT CARVES — a positive number of
    inches, how far back from an appurtenance THIS covering is disturbed. It is declared rather than defaulted
    because it is a MATERIAL fact, not a geometric one: wood shake's 21 in is the distance the interlocking
    courses must be lifted to reach the flashing, and a membrane's 6 in is Joseph's cut-back, because a membrane
    has no courses to lift — you cut it where you cut it. Until v106.6c the number lived in core as
    `geometry_core.APPURT_CLEAR_IN = 21.0` and applied to every roof system alike, so a membrane could not decline
    a coursed assumption. It survived two roof systems because the shared-core purity gate scans for material
    WORDS — "shake", "exposure" — and a bare 21.0 contains none: the gate catches named coursed assumptions, not
    numeric ones.

    It is validated but kept OPTIONAL at registration, because a package that never carves an appurtenance zone
    has no honest answer and declines by omission, exactly as a non-coursed covering declines course_top_ft.
    Asking a package that declined then RAISES, named, rather than falling back to anyone else's number — the
    same refusal `affected_area` already makes for a missing VALLEY strategy. It joins the idempotency
    comparison."""
    global _UNLABELLED_CLAIMANT
    if not isinstance(system_id, str) or not system_id.strip():
        raise ValueError(f"system_id must be a non-empty string; got {system_id!r}")
    if not callable(resolve_profile):
        raise TypeError(f"{system_id}: resolve_profile must be callable")
    if not callable(expand_scope):
        raise TypeError(f"{system_id}: expand_scope must be callable (the package's scope engine — FRAME v104b)")
    if course_top_ft is not None and not callable(course_top_ft):
        raise TypeError(f"{system_id}: course_top_ft must be callable when declared (FRAME v105.4), or omitted")
    if tie_in_courses is not None and not (isinstance(tie_in_courses, int) and not isinstance(tie_in_courses, bool)
                                           and tie_in_courses > 0):
        raise TypeError(f"{system_id}: tie_in_courses must be a positive int when declared (FRAME v106.3b), or "
                        f"omitted; got {tie_in_courses!r}")
    if appurtenance_clearance_in is not None and not (
            isinstance(appurtenance_clearance_in, (int, float)) and not isinstance(appurtenance_clearance_in, bool)
            and appurtenance_clearance_in > 0):
        raise TypeError(f"{system_id}: appurtenance_clearance_in must be a positive number of inches when "
                        f"declared (FRAME v106.6c), or omitted; got {appurtenance_clearance_in!r}")
    if appurtenance_base_clearance_in is not None and not (
            isinstance(appurtenance_base_clearance_in, (int, float))
            and not isinstance(appurtenance_base_clearance_in, bool)
            and appurtenance_base_clearance_in > 0):
        raise TypeError(f"{system_id}: appurtenance_base_clearance_in must be a positive number of inches "
                        f"when declared (FRAME v106.6g), or omitted; got "
                        f"{appurtenance_base_clearance_in!r}")
    if not isinstance(disturbance, Mapping) or not disturbance:
        raise TypeError(f"{system_id}: disturbance must be a non-empty mapping of event type -> strategy")
    unknown = sorted(set(disturbance) - EVENT_TYPES)
    if unknown:
        raise ValueError(f"{system_id}: unknown repair-event type(s) {unknown}; known: {sorted(EVENT_TYPES)}")
    for ev, fn in disturbance.items():
        if not callable(fn):
            raise TypeError(f"{system_id}: disturbance[{ev!r}] must be callable")
    entry = RoofSystem(system_id, resolve_profile, MappingProxyType(dict(disturbance)),
                       bool(claims_unlabelled_profiles), expand_scope, course_top_ft,
                       None if tie_in_courses is None else int(tie_in_courses),
                       None if appurtenance_clearance_in is None else float(appurtenance_clearance_in),
                       None if appurtenance_base_clearance_in is None
                       else float(appurtenance_base_clearance_in))
    existing = _SYSTEMS.get(system_id)
    if existing is not None:
        if (existing.resolve_profile is entry.resolve_profile
                and dict(existing.disturbance) == dict(entry.disturbance)
                and existing.claims_unlabelled_profiles == entry.claims_unlabelled_profiles
                and existing.expand_scope is entry.expand_scope
                and existing.course_top_ft is entry.course_top_ft
                and existing.tie_in_courses == entry.tie_in_courses
                and existing.appurtenance_clearance_in == entry.appurtenance_clearance_in
                and existing.appurtenance_base_clearance_in == entry.appurtenance_base_clearance_in):
            return existing
        raise RoofSystemRegistryError(
            f"roof system {system_id!r} is already registered with different strategies — two homes for one "
            f"system. A package registers exactly once.")
    if entry.claims_unlabelled_profiles and _UNLABELLED_CLAIMANT not in (None, system_id):
        raise RoofSystemRegistryError(
            f"{system_id!r} claims unlabelled profiles, but {_UNLABELLED_CLAIMANT!r} already does. At most one "
            f"package may own unlabelled (pre-ProjectConfig) profiles.")
    _SYSTEMS[system_id] = entry
    if entry.claims_unlabelled_profiles:
        _UNLABELLED_CLAIMANT = system_id
        # FRAME v106.4: THE SAME CLAIM, PUSHED DOWN ONE LAYER. shared_category_registry needs this answer for a
        # line that carries no material (the assembly's eave-IWS and ridge-vent lines, via line_system) but sits
        # below this module and cannot ask. Telling it here keeps ONE declaration site: a package says
        # claims_unlabelled_profiles once, and both registries know it. A second flag on
        # register_package_categories would be the same fact in two places, and a package that set one and
        # forgot the other would be silently wrong at exactly the sites bridge 4 used to guard.
        set_default_category_package(system_id)
    return entry


def registered():
    return tuple(sorted(_SYSTEMS))


def _none_registered():
    return RoofSystemRegistryError(
        "FRAME wiring: no roof-system package has registered with core/registry/roof_systems.py, so core "
        "geometry cannot resolve a disturbance strategy. This is missing wiring, not a geometry bug. Fix: import "
        "a roof-system package module (each module under deploy/roof_systems/<system>/ registers itself when "
        "imported) before calling core geometry from this entry point.")


def get(system_id):
    """The registered RoofSystem for `system_id`. RAISES on an unknown id; never substitutes one."""
    if not _SYSTEMS:
        raise _none_registered()
    try:
        return _SYSTEMS[system_id]
    except (KeyError, TypeError):
        raise RoofSystemRegistryError(
            f"FRAME wiring: no roof-system package registered system_id {system_id!r}. Registered: "
            f"{list(registered())}. Fix: import that system's package module, or correct the profile's "
            f"system_id.") from None


def course_top_ft(system_id, profile, courses=None):
    """FRAME v105.4: the height, in FEET, to the top of course `courses` — answered by THAT system's own package (each
    package answers for its own course geometry; core holds no course arithmetic). `courses=None` asks for the
    package's OWN tie-in count; a caller with a ruling of its own (the membrane manufacturer's count, entry 104) passes
    it explicitly. A package that declared no course geometry RAISES, named: a non-coursed covering cannot answer."""
    entry = get(system_id)
    if entry.course_top_ft is None:
        raise RegistryWiringError(
            f"FRAME: roof system {system_id!r} declares no course geometry (course_top_ft), so it cannot say where the "
            f"top of a course is — a covering that is not coursed has no answer. Fix: ask the coursed system, or have "
            f"the package declare course_top_ft at registration. (v105.4)")
    return entry.course_top_ft(profile, courses)


def declares_course_top_ft(system_id) -> bool:
    """Does this system declare course geometry at all? MEMBERSHIP, so it answers without raising (FRAME v106.3b).

    `course_top_ft` above RAISES for a non-coursed covering, which is right when a caller needs the answer and
    wrong when a caller needs to know whether there IS one. Asking-then-catching would make the refusal a control
    flow rather than an error, which is how a refusal quietly becomes a default — the same reason bridge 4's
    line-less sites moved to `field_category_ids()` membership instead of `field_category_id(sole_...)` (v106.4).
    An unknown system_id still raises through get(): this answers "declared or not", never "registered or not"."""
    return get(system_id).course_top_ft is not None


def tie_in_courses(system_id):
    """This system's own manufacturer tie-in count, or None when it declares none (FRAME v106.3b). Membership, like
    declares_course_top_ft: a covering with no boundary-termination rule of its own is not an error."""
    return get(system_id).tie_in_courses


def appurtenance_clearance_in(system_id, flashing_method=None) -> float:
    """FRAME v106.6c: how far back from an appurtenance THIS covering is disturbed, in inches — the number core's
    `appurt_rect` grows the footprint by.

    FRAME v106.6g: there are TWO such numbers per covering, because the distance is set by how the item is
    flashed and not by how big it is (Joseph, 2026-11-06: "Skylights and chimneys genuinely need a 21 inch
    clearance around the perimeter of these areas to get an 18 inch strip around the dimensional
    appurtenance. The smaller stuff doesn't need an 18 inch strip around the flashing."):

      CURB_FLASHED  a chimney or skylight, needing an 18in IWS strip round its perimeter   21in on shake
      BASE_FLASHED  a vent or pipe jack, needing room for the flange and a small strip     about 6in

    `flashing_method` is appurtenance_types.BASE_FLASHED or CURB_FLASHED, and **defaults to CURB_FLASHED** so
    that every caller written before v106.6g keeps the number it already had. That default is what holds the
    frozen Yager anchor and every chimney and skylight figure in the suite unmoved by this build: an untyped
    appurtenance is curb-flashed and measured, which is both the conservative reading on a claim and what the
    tree already did.

    This RAISES for a package that declared none, and that is deliberate. It is the same refusal `affected_area`
    makes for a missing VALLEY strategy, and for the same reason: core holds no material number, so when the
    package that owns the answer has not given one there is nothing to fall back to except somebody else's
    assumption. A silent fallback here is precisely the defect this function exists to end — the 21 in coursed
    ring applying to a membrane because core, not the package, owned it.

    Use `declares_appurtenance_clearance` when the question is whether an answer EXISTS."""
    s = get(system_id)
    if flashing_method == _BASE_FLASHED:
        clr = s.appurtenance_base_clearance_in
        if clr is None:
            raise RoofSystemRegistryError(
                f"roof system {system_id!r} declares no appurtenance_base_clearance_in, so core cannot size "
                f"the disturbance round a base-flashed item \u2014 a vent or a pipe jack \u2014 on one of its "
                f"facets. How far back a covering is disturbed to set a flange and lap it is a fact about "
                f"that covering, so the package must declare it; core holds no clearance of its own. Fix: "
                f"pass appurtenance_base_clearance_in to register() in {system_id}'s geometry module.")
        return float(clr)
    clr = s.appurtenance_clearance_in
    if clr is None:
        # The message names NO roof system but the one asked for. A core module that spells out another
        # package's name and number has taken a position on what that package's material does, which is the
        # whole failure this function exists to end — and roof_system_registry_regression catches it, which
        # is how QA found this sentence after writing it.
        raise RoofSystemRegistryError(
            f"roof system {system_id!r} declares no appurtenance_clearance_in, so core cannot carve an "
            f"appurtenance disturbance zone for one of its facets. Core holds no clearance of its own: how "
            f"far back a covering is disturbed is a fact about that covering's material, so the package must "
            f"declare it. Fix: pass appurtenance_clearance_in to register() in {system_id}'s geometry "
            f"module.")
    return float(clr)


def declares_appurtenance_clearance(system_id) -> bool:
    """Does this system declare an appurtenance clearance at all? MEMBERSHIP, so it answers without raising —
    the same pairing as course_top_ft / declares_course_top_ft (FRAME v106.6c)."""
    return get(system_id).appurtenance_clearance_in is not None


def system_boundary_tie_in_ft(asking_system_id, other_system_id, profile) -> float:
    """THE ONE EVALUATION of Joseph's boundary ruling (2026-11-01), in feet.

    > "Each side doing its thing. MODBIT or whatever flat surface system being installed gets installed with
    >  enough material up the steep slope to reach the top portion of the third course of shingle material being
    >  installed on the steep slope. Then the roofing system being installed on the steep slope gets installed."

    He was given three choices and picked the third: not a lookup per ordered pair of systems (N² cells, most
    never seen), not a question on every boundary, but **each side applies its OWN standard termination and FRAME
    bills both.** So this function is NOT keyed by a pair and never can be. It composes two one-sided declarations:

        asking.tie_in_courses   — HOW MANY courses, the ASKING system's manufacturer count (MODBIT: 3)
        other.course_top_ft(n)  — HOW FAR that is, the OTHER system's own course geometry (shake: 44 in at 24"/10")

    which is the sentence's own two halves: *"enough material"* is the membrane manufacturer's, *"the top portion
    of the third course of shingle material being installed on the steep slope"* is the shake's. **Neither package
    holds both numbers, and core holds neither** — it only multiplies. That is why a MODBIT↔TPO boundary correctly
    produces nothing: two flat packages, and neither declares course geometry for the other to measure.

    RETURNS 0.0, NOT AN ERROR, when either declaration is absent, because absence is an ANSWER here and both
    absences are meaningful:
      * the asking side declares no tie_in_courses -> it has no boundary-termination rule of its own. Wood shake
        asking about a membrane neighbour lands here, and 0.0 is correct in the physical detail too: both
        manufacturer drawings put the membrane UNDER the courses, never the courses under the membrane.
      * the other side declares no course_top_ft -> it is not coursed, so "the top of its 3rd course" does not
        exist. This is v105.4's refusal, reached through declares_course_top_ft so that it stays a refusal rather
        than an exception used as a branch.
    A zero means "this side terminates onto the other without running material up it", which the engine that asked
    then bills as nothing. It never means "not got to it yet": the caller that must disclose an untouched boundary
    does so from the boundary itself (module2_assembly's SystemBoundaryDisclosure), not from this number.
    """
    n = tie_in_courses(asking_system_id)
    if n is None:
        return 0.0
    if not declares_course_top_ft(other_system_id):
        return 0.0
    return float(course_top_ft(other_system_id, profile, n))


def system_for_profile(profile):
    """Which roof system owns this profile. A `system_id` on the profile decides it (unknown -> raise). A profile
    without one is resolved only through a package's explicit unlabelled-profile claim (bridge 1, above);
    with no claimant it raises. Core never picks a system itself."""
    sid = None
    if profile is not None:
        sid = (profile if isinstance(profile, Mapping) else dict(profile)).get("system_id")
    if sid not in (None, ""):
        return get(sid)
    if not _SYSTEMS:
        raise _none_registered()
    if _UNLABELLED_CLAIMANT is None:
        raise RoofSystemRegistryError(
            f"FRAME: the profile carries no system_id and no registered package claims unlabelled profiles "
            f"(registered: {list(registered())}). Core does not assume a roof system. Fix: give the profile "
            f"a system_id.")
    return _SYSTEMS[_UNLABELLED_CLAIMANT]


# =============================================================================================
# FRAME v104a — the per-facet roof-system contract. See the module docstring. Tier 1: names no roof system.
# =============================================================================================
PREDOMINANT_SYSTEM_KEY = "predominant_system_id"
FACET_SYSTEMS_KEY = "facet_systems"
# FRAME v106.1 — A FACET THAT IS NOT SCOPED HERE. Joseph, 2026-11-02, on Killarney F36: "F36 on Killarney
# does not have wood shake on it. I think it has standing seam, but I can't remember. … It doesn't matter
# what that surface is. We just know it's not wood shake."
#
# WHY THIS IS NOT facet_systems. Declaring a facet's system requires that system to be REGISTERED
# (_require_registered_system), and registering a pseudo-system to mean "other" would make registered()
# return two — which trips bridge 4 and forces a declaration on EVERY claim, including every legacy one.
# An exclusion is a scope fact, not a system fact: the user knows what the facet is NOT, need not name what
# it IS, and no package has to exist for them to say so.
EXCLUDED_FACETS_KEY = "excluded_facets"


def excluded_facets(confirmed_selection) -> frozenset:
    """The facets this claim does not scope. Absent, None and () are all "none"; a non-sequence raises.

    THE ONE reader of the key: every consumer asks here rather than reading the selection itself, so the
    normalisation (str ids, order-insensitive, de-duplicated) has one definition.
    """
    raw = (confirmed_selection or {}).get(EXCLUDED_FACETS_KEY)
    if raw is None:
        return frozenset()
    if isinstance(raw, (str, bytes)) or isinstance(raw, Mapping):
        raise TypeError(f"FRAME: {EXCLUDED_FACETS_KEY} must be a sequence of face ids; got {type(raw).__name__}")
    return frozenset(str(f) for f in raw)


def _facet_exceptions(confirmed_selection):
    """The exceptions map. Absent, None and {} are all "no exceptions"; anything that is not a mapping raises."""
    raw = (confirmed_selection or {}).get(FACET_SYSTEMS_KEY)
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise TypeError(f"FRAME: {FACET_SYSTEMS_KEY} must be a mapping {{face_id: system_id}} (exceptions only); "
                        f"got {type(raw).__name__}")
    return {str(k): v for k, v in raw.items()}


def _require_registered_system(system_id, where):
    if system_id in _SYSTEMS:
        return system_id
    raise RegistryWiringError(
        f"FRAME: {where} names roof system {system_id!r}, which no package has registered (registered: "
        f"{list(registered())}). Fix: import that system's package module, or correct {where}.")


def system_for_facet(face_id, confirmed_selection):
    """The roof system a facet carries. ONE authority, three steps:
      1. an entry for the facet in `facet_systems` wins;
      2. otherwise the claim's `predominant_system_id`;
      3. otherwise — the claim declares neither — THE SOLE registered roof system. Zero, or two or more, RAISES:
         core never picks a system. This step is a BRIDGE 4 member (see the module docstring).
    A named system that no package registered raises. An exception naming the predominant system is a no-op."""
    sel = confirmed_selection or {}
    sid = _facet_exceptions(sel).get(str(face_id))
    if sid not in (None, ""):
        return _require_registered_system(sid, f"{FACET_SYSTEMS_KEY}[{str(face_id)!r}]")
    pre = sel.get(PREDOMINANT_SYSTEM_KEY)
    if pre not in (None, ""):
        return _require_registered_system(pre, PREDOMINANT_SYSTEM_KEY)
    # FRAME v106.4 — AN INCOMPLETE DECLARATION IS NOT A LEGACY CLAIM, and the difference is the whole reason
    # step 3's fallback is safe. A claim declaring NEITHER key is pre-declaration: every saved claim, every
    # verification fixture, the frozen Yager anchor selection — and the claimant owns it (below).
    #
    # A claim declaring `facet_systems` and NO predominant is something else: the user has said this roof
    # carries more than one covering and has NOT said which covering the rest of it is. That is ambiguous on
    # its face, and answering it with the claimant would bill every undeclared facet as wood shake on a roof
    # the user just told us is mixed. So it RAISES.
    #
    # This is what keeps page 2's §1d overlay honest. Its stated justification is that the ENGINE refuses an
    # undeclared multi-covering roof, so the page asks before computing; if the engine quietly answered
    # instead, the page would be the only guard and that justification would be a claim rather than a
    # receipt (entry 119: a principle implemented in one direction only does not hold). v105.5's overlay
    # means page 2 always emits a predominant once two coverings are registered, so this raise does not fire
    # on anything the page can produce — it fires on a hand-built or corrupted selection, which is exactly
    # what a defensive guard is for.
    if _facet_exceptions(sel):
        raise RegistryWiringError(
            f"FRAME: system_for_facet({str(face_id)!r}) — this claim declares {FACET_SYSTEMS_KEY} but no "
            f"{PREDOMINANT_SYSTEM_KEY}, so it says the roof carries more than one covering without saying which "
            f"covering {str(face_id)} is. Core will not assume the rest of a mixed roof. Fix: declare "
            f"{PREDOMINANT_SYSTEM_KEY} on the claim. (v106.4)")
    return sole_registered_system(f"system_for_facet({str(face_id)!r})")


def appurtenance_clearance_for_facet(face_id, confirmed_selection) -> float:
    """FRAME v106.6c: the appurtenance setback, in inches, for the covering THIS FACET carries.

    ONE function, so that the question "whose clearance carves this facet?" has one answer. The appurtenance
    carve helpers exist as near-duplicates in BOTH module1_service.py (which feeds the diagram) and
    module2_assembly.py (which feeds the scope), and this project has shipped "the engine computed it correctly
    and a downstream path disagreed" more than once. Two copies of this lookup would let the diagram carve a
    facet at 21 in while the scope carved it at 6 in, and nothing would say so.

    It composes the two existing authorities and adds no rule of its own: `system_for_facet` decides which
    covering the facet carries, `appurtenance_clearance_in` asks that package how far back it is disturbed."""
    # (No roof system is named anywhere in this module's clearance code, by rule — see the error above.)
    return appurtenance_clearance_in(system_for_facet(face_id, confirmed_selection))


def appurtenance_clearance_for_facets(face_ids, confirmed_selection,
                                      context="an appurtenance carve on a merged slope") -> float:
    """FRAME v106.6c: the appurtenance setback for a MERGED slope, which spans several member faces.

    A merged slope is one carving surface built from several facets, so one clearance has to carve all of it.
    `system_for_facets` is the existing authority for that question and it REFUSES a merge whose facets carry
    different coverings rather than picking one — which is the right refusal here too: a merged slope that is
    part membrane and part shake has no single setback, and guessing one would carve half the surface at the
    wrong distance. Core will not guess; the message names every facet and its system."""
    return appurtenance_clearance_in(system_for_facets(face_ids, confirmed_selection, context))


def system_for_facets(face_ids, confirmed_selection, context="a scope call spanning several facets"):
    """THE roof system shared by SEVERAL facets (FRAME v105.3) — system_for_facet applied to each, and they must AGREE.

    One authority: every facet resolves through system_for_facet (the three steps are not re-implemented here). One
    distinct answer is returned. More than one RAISES RegistryWiringError naming every facet and its system: an object
    spanning facets of different systems sits on a SYSTEM BOUNDARY, and what a boundary bills is each system's own
    termination (Joseph, 2026-11-01) — a domain rule the packages own, which core will not guess. No facets RAISES: an
    empty question has no answer. It never reads how many systems are registered, so it is correct at any count."""
    ids = [str(f) for f in face_ids]
    if not ids:
        raise RegistryWiringError(f"FRAME: {context} — no facets were given, so there is no roof system to resolve.")
    per = [(f, system_for_facet(f, confirmed_selection)) for f in ids]
    distinct = list(dict.fromkeys(s for _f, s in per))
    if len(distinct) == 1:
        return distinct[0]
    raise RegistryWiringError(
        f"FRAME: {context} spans facets carrying DIFFERENT roof systems ("
        + ", ".join(f"{f}: {s}" for f, s in per)
        + "). That is a SYSTEM BOUNDARY: what it bills is each system's own termination, which core will not guess. "
          "(v105.3)")


def sole_registered_system(context="a scope call with no facet in hand"):
    """THE system a claim that declares NOTHING resolves to — system_for_facet's third step, named so that a caller
    with NO face id in hand (FRAME v104b: a per-edge or per-transition scope call, the oracle's fixture) resolves by
    the SAME rule rather than a third path.

    FRAME v106.4 — TWO packages are registered now, and this step stopped being "the sole one". The answer is the
    package that CLAIMED unlabelled profiles, which is bridge 1's existing declaration extended by one word: a
    profile with no system_id and a claim with no predominant_system_id are the same pre-declaration case, and the
    registration guard already allows AT MOST ONE claimant, so there is no ambiguity to resolve. CORE STILL NEVER
    PICKS A SYSTEM — a package declared that it owns this case.

    This is what keeps the documented invariant true at two packages (module docstring: "NOTHING DECLARED -> NEITHER
    key is emitted, so a claim that never opens the control has exactly the shape it had before v105.5 — every saved
    claim keeps working"). Measured: that invariant was FALSE the moment a second package registered — 36 of the 38
    verification scripts that call the scope engine, and the frozen Yager anchor selection itself, declare no
    predominant and raised here.

    Zero packages RAISES. Two or more with NO claimant RAISES, naming them: nothing has declared it owns the
    undeclared case, and core will not choose.
    """
    pk = registered()
    if not pk:
        raise RegistryWiringError(
            f"FRAME wiring: {context} — the claim declares no {PREDOMINANT_SYSTEM_KEY} and no roof-system package has "
            f"registered, so there is no answer. This is missing wiring, not a data problem. Fix: declare "
            f"{PREDOMINANT_SYSTEM_KEY} on the claim, and import the installed package's geometry module (every engine "
            f"module does).")
    if _UNLABELLED_CLAIMANT is not None:
        return _UNLABELLED_CLAIMANT
    if len(pk) > 1:
        raise RegistryWiringError(
            f"FRAME bridge 4: {context} — {len(pk)} roof-system packages are registered ({list(pk)}) and NONE claims "
            f"unlabelled profiles, so nothing has declared it owns a claim that declares no "
            f"{PREDOMINANT_SYSTEM_KEY}, and core will not pick one. Fix: declare {PREDOMINANT_SYSTEM_KEY} on the "
            f"claim (and {FACET_SYSTEMS_KEY} for any facet that differs), or have the predominant package declare "
            f"claims_unlabelled_profiles at registration. (v106.4)")
    return pk[0]


def validate_roof_system_selection(confirmed_selection, roof_face_ids):
    """Raise, actionably, on a bad declaration; return None when it is sound. A selection declaring neither key is
    not inspected at all (every pre-v104a claim). `roof_face_ids` are this roof's facets (ROOF faces, not
    penetrations): an exception keyed by anything else raises."""
    sel = confirmed_selection or {}
    if (PREDOMINANT_SYSTEM_KEY not in sel and FACET_SYSTEMS_KEY not in sel
            and EXCLUDED_FACETS_KEY not in sel):
        return None
    pre = sel.get(PREDOMINANT_SYSTEM_KEY)
    if pre not in (None, ""):
        if not isinstance(pre, str):
            raise TypeError(f"FRAME: {PREDOMINANT_SYSTEM_KEY} must be a system id string; got {type(pre).__name__}")
        _require_registered_system(pre, PREDOMINANT_SYSTEM_KEY)
    faces = {str(f) for f in roof_face_ids}
    for fid, sid in sorted(_facet_exceptions(sel).items()):
        if fid not in faces:
            raise ValueError(
                f"FRAME: {FACET_SYSTEMS_KEY} names {fid!r}, which is not a roof facet of this roof (its facets: "
                f"{sorted(faces, key=lambda v: (len(v), v))}). Fix: key {FACET_SYSTEMS_KEY} by this roof's face ids.")
        if not isinstance(sid, str) or not sid.strip():
            raise ValueError(f"FRAME: {FACET_SYSTEMS_KEY}[{fid!r}] must name a roof system; got {sid!r}")
        _require_registered_system(sid, f"{FACET_SYSTEMS_KEY}[{fid!r}]")
    # FRAME v106.1 — an excluded facet must be a facet of THIS roof, by the same rule and the same
    # message shape as a declared one. It needs no registered system: that is the point of the key.
    for fid in sorted(excluded_facets(sel)):
        if fid not in faces:
            raise ValueError(
                f"FRAME: {EXCLUDED_FACETS_KEY} names {fid!r}, which is not a roof facet of this roof (its "
                f"facets: {sorted(faces, key=lambda v: (len(v), v))}). Fix: key {EXCLUDED_FACETS_KEY} by this "
                f"roof's face ids.")
    # A facet cannot be both declared and excluded: the two answers contradict, and core will not pick.
    both = sorted(excluded_facets(sel) & set(_facet_exceptions(sel)))
    if both:
        raise ValueError(
            f"FRAME: {both} appear in BOTH {FACET_SYSTEMS_KEY} and {EXCLUDED_FACETS_KEY}. A facet is either "
            f"scoped as a declared system or not scoped at all — not both. Fix: remove each from one key.")
    return None


def roof_system_keys(selection):
    """The three keys exactly as the selection gives them (a mapping or sequence is COPIED), for the code that
    CARRIES a selection from one shape to another. Absent keys stay absent: a claim that declares nothing changes
    shape nowhere. FRAME v106.1 added excluded_facets, whose value is a sequence — copied for the same reason the
    map always was, so a carried selection can never alias the caller's container."""
    sel = selection or {}
    out = {}
    for key in (PREDOMINANT_SYSTEM_KEY, FACET_SYSTEMS_KEY, EXCLUDED_FACETS_KEY):
        if key in sel:
            v = sel[key]
            if isinstance(v, Mapping):
                out[key] = dict(v)
            elif isinstance(v, (list, tuple, set, frozenset)):
                out[key] = list(v)
            else:
                out[key] = v
    return out
