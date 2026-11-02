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

from shared_category_registry import RegistryWiringError   # FRAME v104a: the bridge-4 wiring error, one type

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
                                       "course_top_ft", defaults=(None,))   # FRAME v105.4: course_top_ft OPTIONAL


class RoofSystemRegistryError(LookupError):
    """The registry cannot decide which roof system a request belongs to. This is a WIRING error, never a
    geometry error, and the message says how to fix it."""


_SYSTEMS: "dict[str, RoofSystem]" = {}
_UNLABELLED_CLAIMANT = None


def register(system_id, *, resolve_profile, disturbance, expand_scope, claims_unlabelled_profiles=False,
             course_top_ft=None):
    """Called BY a package, at its own import. Idempotent for an identical registration. A second, DIFFERENT
    registration of one id raises (one rule, one home), as does a second claimant of unlabelled profiles.

    FRAME v105.4: `course_top_ft(profile, courses=None) -> feet` is OPTIONAL — the package's own course geometry, the
    height to the top of course `courses` (None = the package's own tie-in count). A covering that is not coursed (a
    membrane, a standing-seam panel) has no honest answer and declines by omitting it; asking it then RAISES, named
    (see course_top_ft below). Like expand_scope, it joins the idempotency comparison."""
    global _UNLABELLED_CLAIMANT
    if not isinstance(system_id, str) or not system_id.strip():
        raise ValueError(f"system_id must be a non-empty string; got {system_id!r}")
    if not callable(resolve_profile):
        raise TypeError(f"{system_id}: resolve_profile must be callable")
    if not callable(expand_scope):
        raise TypeError(f"{system_id}: expand_scope must be callable (the package's scope engine — FRAME v104b)")
    if course_top_ft is not None and not callable(course_top_ft):
        raise TypeError(f"{system_id}: course_top_ft must be callable when declared (FRAME v105.4), or omitted")
    if not isinstance(disturbance, Mapping) or not disturbance:
        raise TypeError(f"{system_id}: disturbance must be a non-empty mapping of event type -> strategy")
    unknown = sorted(set(disturbance) - EVENT_TYPES)
    if unknown:
        raise ValueError(f"{system_id}: unknown repair-event type(s) {unknown}; known: {sorted(EVENT_TYPES)}")
    for ev, fn in disturbance.items():
        if not callable(fn):
            raise TypeError(f"{system_id}: disturbance[{ev!r}] must be callable")
    entry = RoofSystem(system_id, resolve_profile, MappingProxyType(dict(disturbance)),
                       bool(claims_unlabelled_profiles), expand_scope, course_top_ft)
    existing = _SYSTEMS.get(system_id)
    if existing is not None:
        if (existing.resolve_profile is entry.resolve_profile
                and dict(existing.disturbance) == dict(entry.disturbance)
                and existing.claims_unlabelled_profiles == entry.claims_unlabelled_profiles
                and existing.expand_scope is entry.expand_scope
                and existing.course_top_ft is entry.course_top_ft):
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
    return sole_registered_system(f"system_for_facet({str(face_id)!r})")


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
    """THE SOLE registered roof system — system_for_facet's third step, named so that a caller with NO face id in hand
    (FRAME v104b: a per-edge or per-transition scope call, the oracle's fixture) resolves by the SAME rule rather than
    a third path. Zero, or two or more, RAISES RegistryWiringError: core never picks a system. A BRIDGE 4 member;
    v104c routes these calls per facet."""
    pk = registered()
    if not pk:
        raise RegistryWiringError(
            f"FRAME wiring: {context} — the claim declares no {PREDOMINANT_SYSTEM_KEY} and no roof-system package has "
            f"registered, so there is no answer. This is missing wiring, not a data problem. Fix: declare "
            f"{PREDOMINANT_SYSTEM_KEY} on the claim, and import the installed package's geometry module (every engine "
            f"module does).")
    if len(pk) > 1:
        raise RegistryWiringError(
            f"FRAME bridge 4: {context} — {len(pk)} roof-system packages are registered ({list(pk)}), so core will not "
            f"pick one. Fix: declare {PREDOMINANT_SYSTEM_KEY} on the claim (and {FACET_SYSTEMS_KEY} for any facet that "
            f"differs); a call with no facet in hand is routed per facet by v104c.")
    return pk[0]


def validate_roof_system_selection(confirmed_selection, roof_face_ids):
    """Raise, actionably, on a bad declaration; return None when it is sound. A selection declaring neither key is
    not inspected at all (every pre-v104a claim). `roof_face_ids` are this roof's facets (ROOF faces, not
    penetrations): an exception keyed by anything else raises."""
    sel = confirmed_selection or {}
    if PREDOMINANT_SYSTEM_KEY not in sel and FACET_SYSTEMS_KEY not in sel:
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
    return None


def roof_system_keys(selection):
    """The two keys exactly as the selection gives them (a dict map is copied), for the code that CARRIES a selection
    from one shape to another. Absent keys stay absent: a claim that declares nothing changes shape nowhere."""
    sel = selection or {}
    out = {}
    for key in (PREDOMINANT_SYSTEM_KEY, FACET_SYSTEMS_KEY):
        if key in sel:
            v = sel[key]
            out[key] = dict(v) if isinstance(v, Mapping) else v
    return out
