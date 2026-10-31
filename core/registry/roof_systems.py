"""
core/registry/roof_systems.py — the roof-system registry (FRAME v95 / Migration Plan step 3b).

Shared core NEVER imports a roof-system package. A package imports THIS module and registers itself at import
time; core looks the package up by the profile's `system_id`. The dependency points one way: package -> core.

    register(system_id, resolve_profile=..., disturbance={...}, claims_unlabelled_profiles=False)
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
"""
from __future__ import annotations

from collections import namedtuple
from collections.abc import Mapping
from types import MappingProxyType

PROPAGATE_TO_RIDGE = "PROPAGATE_TO_RIDGE"     # the zone is shadow-filled up-slope to the top of its field run
BOUNDED = "BOUNDED"                           # the zone is exactly the mask, clipped to the field
SHADOW_RULES = frozenset((PROPAGATE_TO_RIDGE, BOUNDED))

EVENT_TYPES = frozenset(("VALLEY", "TRANSITION", "APPURTENANCE", "PENETRATION", "FACET_REPLACEMENT"))

# What core hands a disturbance strategy: the facet grid, read-only by contract (Package Contract §1.1).
FacetGrid = namedtuple("FacetGrid", "gx gy X Y")

RoofSystem = namedtuple("RoofSystem", "system_id resolve_profile disturbance claims_unlabelled_profiles")


class RoofSystemRegistryError(LookupError):
    """The registry cannot decide which roof system a request belongs to. This is a WIRING error, never a
    geometry error, and the message says how to fix it."""


_SYSTEMS: "dict[str, RoofSystem]" = {}
_UNLABELLED_CLAIMANT = None


def register(system_id, *, resolve_profile, disturbance, claims_unlabelled_profiles=False):
    """Called BY a package, at its own import. Idempotent for an identical registration. A second, DIFFERENT
    registration of one id raises (one rule, one home), as does a second claimant of unlabelled profiles."""
    global _UNLABELLED_CLAIMANT
    if not isinstance(system_id, str) or not system_id.strip():
        raise ValueError(f"system_id must be a non-empty string; got {system_id!r}")
    if not callable(resolve_profile):
        raise TypeError(f"{system_id}: resolve_profile must be callable")
    if not isinstance(disturbance, Mapping) or not disturbance:
        raise TypeError(f"{system_id}: disturbance must be a non-empty mapping of event type -> strategy")
    unknown = sorted(set(disturbance) - EVENT_TYPES)
    if unknown:
        raise ValueError(f"{system_id}: unknown repair-event type(s) {unknown}; known: {sorted(EVENT_TYPES)}")
    for ev, fn in disturbance.items():
        if not callable(fn):
            raise TypeError(f"{system_id}: disturbance[{ev!r}] must be callable")
    entry = RoofSystem(system_id, resolve_profile, MappingProxyType(dict(disturbance)),
                       bool(claims_unlabelled_profiles))
    existing = _SYSTEMS.get(system_id)
    if existing is not None:
        if (existing.resolve_profile is entry.resolve_profile
                and dict(existing.disturbance) == dict(entry.disturbance)
                and existing.claims_unlabelled_profiles == entry.claims_unlabelled_profiles):
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
