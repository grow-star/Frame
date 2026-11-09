"""
core/registry/package_content.py — what a roof-system package SAYS, read by core at call time (FRAME v101)
=========================================================================================================
Migration Plan Amendment A2 §2 groups B–E and §3 (Package Contract item 10). Core owns the machinery — the
renderer, the comparison argument lookup, the label map, Layer A's matcher — and each package owns the words:

  display_labels     {category_id: label}         for ids the package OWNS             (A2 group D)
  carrier_patterns   (CarrierPattern, ...)        the words a carrier uses for this     (A2 group E, §3 item 10)
                                                  system's materials -> category ids
  repair_entries     (entry dict, ...)            authored repair-logic explanations,   (A2 group C)
                                                  triggered on ids the package OWNS
  texts              {key: value}                 claim-level report / argument text    (A2 groups B, C)

A package registers at its own import (bridge 3), after it has registered its category ids with
shared_category_registry. Core NEVER imports a package: it calls the lookups below, and only at CALL time — a
module-level table built from these at import is the v98 import-time-lookup trap.

TWO KINDS OF LOOKUP, because the two kinds of content differ:
  * PER-CATEGORY (labels, patterns, repair entries) are keyed by a category, so two packages cannot collide:
    the lookup is the UNION over every package that registered content. With no package registered at all it
    RAISES (missing wiring, never a short answer — the v97 rule).
  * CLAIM-LEVEL (texts) have no category to key on. They resolve like field_category_id(): from the ONE
    registered roof-system package; zero or two-plus RAISE. These are new members of BRIDGE 4 and retire with
    it, when a line states its own material (ScopeLine.material_profile_id).
"""
from __future__ import annotations

import re
from collections import namedtuple
from collections.abc import Mapping
from types import MappingProxyType

from shared_category_registry import RegistryWiringError, package_categories, registered_packages, validate_category_id

# Package Contract item 10. `field=True` marks the system's FIELD-covering vocabulary — the least specific rule:
# a line that also names a specific component (starter, ridge cap, a flashing, ...) is that component. (This
# replaces Layer A's hand-written _GENERIC_FIELD set.)
CarrierPattern = namedtuple("CarrierPattern", "pattern category_id in_scope confidence field")
CONFIDENCES = frozenset(("high", "medium", "low"))
TEXT_KEYS = frozenset(("sec3_title", "method_explanation", "felt_interlayment_callout"))

PackageContent = namedtuple("PackageContent", "display_labels carrier_patterns repair_entries texts")
_CONTENT: "dict[str, PackageContent]" = {}


def _freeze_entry(e):
    if not isinstance(e, Mapping) or not isinstance(e.get("trigger"), Mapping):
        raise TypeError(f"repair entry {e!r} must be a mapping with a 'trigger' mapping")
    return e


def register_package_content(system_id, *, display_labels=None, carrier_patterns=(), repair_entries=(), texts=None):
    """Called BY a package at its own import, after register_package_categories(system_id, ...). Validated: a label
    or repair entry may name only an id the package OWNS; a pattern must compile and name a known id; text keys
    must be known. Idempotent for an identical registration; a different one RAISES (one home)."""
    if system_id not in registered_packages():
        raise RegistryWiringError(
            f"FRAME wiring: package {system_id!r} registered content before registering its category ids. Fix: "
            f"call register_package_categories({system_id!r}, ...) first, in its category module.")
    owned = set(package_categories(system_id))
    labels = dict(display_labels or {})
    stray = sorted(set(labels) - owned)
    if stray:
        raise ValueError(f"{system_id}: display labels for ids it does not own: {stray} (a package labels its own ids)")
    pats = tuple(carrier_patterns)
    for p in pats:
        if not isinstance(p, CarrierPattern):
            raise TypeError(f"{system_id}: carrier pattern {p!r} must be a CarrierPattern")
        re.compile(p.pattern)
        validate_category_id(p.category_id)
        if p.confidence not in CONFIDENCES:
            raise ValueError(f"{system_id}: pattern {p.pattern!r} confidence {p.confidence!r} not in {sorted(CONFIDENCES)}")
    entries = tuple(_freeze_entry(e) for e in repair_entries)
    for e in entries:
        if e["trigger"].get("category_id") not in owned:
            raise ValueError(f"{system_id}: repair entry {e.get('id')!r} triggers on {e['trigger'].get('category_id')!r}, "
                             f"which it does not own")
    txt = dict(texts or {})
    unknown = sorted(set(txt) - TEXT_KEYS)
    if unknown:
        raise ValueError(f"{system_id}: unknown text key(s) {unknown}; known: {sorted(TEXT_KEYS)}")
    entry = PackageContent(MappingProxyType(labels), pats, entries, MappingProxyType(txt))
    existing = _CONTENT.get(system_id)
    if existing is not None:
        if (dict(existing.display_labels) == labels and existing.carrier_patterns == pats
                and existing.repair_entries == entries and dict(existing.texts) == txt):
            return existing
        raise RegistryWiringError(f"FRAME wiring: package {system_id!r} registered DIFFERENT content twice — two homes "
                                  f"for one package's words. A package registers its content exactly once.")
    for other, c in _CONTENT.items():
        clash = sorted({(t["trigger"]["category_id"], t["trigger"]["required_operation"], t["trigger"]["carrier_operation"])
                        for t in c.repair_entries}
                       & {(t["trigger"]["category_id"], t["trigger"]["required_operation"], t["trigger"]["carrier_operation"])
                          for t in entries})
        if clash:
            raise ValueError(f"{system_id}: repair-entry triggers {clash} already registered by {other!r}")
    _CONTENT[system_id] = entry
    return entry


def _content_packages():
    if not _CONTENT:
        raise RegistryWiringError(
            "FRAME wiring: no roof-system package has registered its content (labels, carrier vocabulary, repair "
            "entries, report text) with core/registry/package_content.py. This is missing wiring, not a data "
            "problem. Fix: import the installed package's category module — the bridge's shared boot helper does "
            "this for every page — before rendering, parsing a carrier estimate, or building an argument.")
    return [_CONTENT[k] for k in sorted(_CONTENT)]


# ---- PER-CATEGORY: the union -------------------------------------------------------------------------------
def display_labels():
    out = {}
    for c in _content_packages():
        out.update(c.display_labels)
    return out


def carrier_patterns():
    return tuple(p for c in _content_packages() for p in c.carrier_patterns)


def repair_entries():
    return tuple(e for c in _content_packages() for e in c.repair_entries)


# ---- CLAIM-LEVEL: exactly one package (BRIDGE 4) --------------------------------------------------------------
def claim_text(key):
    """The claim-level text for `key`, from the package that DECLARED one.

    FRAME v106.4 — BRIDGE 4 RETIRED HERE. This used to ask "is exactly ONE PACKAGE registered?" when the question
    it needs answered is "is there exactly ONE ANSWER?". Those two came apart the moment a second package
    registered: the message this function raised called itself "the hard gate on a second roofing package", and it
    was exactly that — all three keys raised on every claim, taking out §3's title, the method explanation and the
    felt-interlayment callout together.

    A package with no honest text for a key DECLARES NONE, and a package that declares none is not counted. That is
    the same decline as a non-coursed covering omitting course_top_ft (v105.4), by the mechanism already here:
    `texts` is optional per key. MODBIT registers none of these three — §3 is a REPAIR argument and a membrane facet
    is scoped as a full replacement (patches out of scope, Joseph 2026-11-01), while a felt interlayment is a
    coursed-covering concept a membrane does not have. So on a shake+MODBIT roof every key still has exactly one
    answer and every rendered word is unchanged.

    Exactly one declared -> that text, whatever else is registered. ZERO declared RAISES: core cannot invent the
    words. MORE THAN ONE declared RAISES, naming them: two systems both claiming a claim-level section is a real
    ambiguity and core will not pick between them — not reachable while only one registered package declares any
    text, and a raise rather than a silent choice when it becomes reachable.
    """
    if key not in TEXT_KEYS:
        raise KeyError(f"unknown claim text key {key!r}; known: {sorted(TEXT_KEYS)}")
    _content_packages()          # zero registered content is missing WIRING — one message, raised there
    have = [(sid, _CONTENT[sid].texts[key]) for sid in sorted(_CONTENT) if key in _CONTENT[sid].texts]
    if len(have) == 1:
        return have[0][1]
    if not have:
        raise RegistryWiringError(
            f"FRAME wiring: no registered roof-system package declares a {key!r} text (registered: "
            f"{list(registered_packages())}). Core cannot supply a system's own words. Fix: pass "
            f"texts={{{key!r}: ...}} to register_package_content in the package that owns this section, or have "
            f"the caller OMIT the section when no package claims it.")
    raise RegistryWiringError(
        f"FRAME: {len(have)} roof-system packages declare a {key!r} text ({[s for s, _ in have]}), so the "
        f"claim-level text has more than one answer and core will not pick one. Fix: take the text from the "
        f"line's own system (ScopeLine.material_profile_id), or have one package stop claiming this section. "
        f"(v106.4)")


def registered_content():
    return tuple(sorted(_CONTENT))
