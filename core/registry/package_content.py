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
    """The ONE registered roof-system package's text for `key`. RAISES on zero packages, on two or more (core will
    not pick a system's words for a claim), and when that package declared no such text. BRIDGE 4: retires with
    ScopeLine.material_profile_id, when a line states its own system."""
    if key not in TEXT_KEYS:
        raise KeyError(f"unknown claim text key {key!r}; known: {sorted(TEXT_KEYS)}")
    pk = registered_packages()
    if len(pk) != 1:
        raise RegistryWiringError(
            f"FRAME bridge 4: {len(pk)} roof-system packages are registered ({list(pk)}), so the claim-level text "
            f"{key!r} has {'no' if not pk else 'more than one'} answer and core will not pick one. This is the hard "
            f"gate on a second roofing package, not a data problem. Fix: take the text from the line's own system "
            f"(ScopeLine.material_profile_id — bridge 4's retirement).")
    c = _CONTENT.get(pk[0])
    if c is None or key not in c.texts:
        raise RegistryWiringError(
            f"FRAME wiring: package {pk[0]!r} declared no {key!r} text. Fix: pass texts={{{key!r}: ...}} to "
            f"register_package_content in its content module.")
    return c.texts[key]


def registered_content():
    return tuple(sorted(_CONTENT))
