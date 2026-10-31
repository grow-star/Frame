#!/usr/bin/env python3
"""
REPAIR LOGIC LIBRARY — authored explanation entries (DATA + lookup)
===================================================================
Additive layer. This is DATA the Module 3 §5 renderer looks up by
(category_id, required_operation, carrier_operation); it authors no claims beyond the
entries a roof-system package registers (FRAME v101: wood shake's three, S-1..S-3, live in its package). It does NOT go through the frozen Scope Argument Builder /
argument_pack, does NOT touch Module 1/2, geometry, the Carrier Parser, or the operation
dimension logic, and introduces no pricing or coverage language.

CONDITION-class entries are phrased conditionally on purpose ("Where the existing shakes
cannot be returned to service..."). The renderer surfaces them verbatim; it never asserts
the condition as established and never fabricates evidence.
"""

from __future__ import annotations

# arg_class
CONDITION = "CONDITION"
DEFINITIONAL = "DEFINITIONAL"
# outcome
STANDOFF = "STANDOFF"
DISPEL = "DISPEL"


# FRAME v101 (A2 group C): the authored entries are MATERIAL arguments, so the roof-system package owns them
# (roof_systems/wood_shake/wood_shake_content.py holds S-1..S-3, byte-for-byte as they stood here) and registers
# them with core/registry/package_content.py. Core keeps the vocabulary above and the exact-match lookup below.
# ENTRIES stays importable as a READ-ONLY view, resolved at CALL time — never a table built at import (v98 trap).
from collections.abc import Sequence as _Sequence

from package_content import repair_entries as _repair_entries


class _EntriesView(_Sequence):
    """Every registered package's repair entries, in registration order, read when used."""
    def __getitem__(self, i):
        return _repair_entries()[i]

    def __len__(self):
        return len(_repair_entries())

    def __repr__(self):
        return f"ENTRIES({list(_repair_entries())!r})"


ENTRIES = _EntriesView()


def _index():
    # index by exact trigger tuple for an unambiguous lookup (built per call; three entries today)
    return {(e["trigger"]["category_id"], e["trigger"]["required_operation"], e["trigger"]["carrier_operation"]): e
            for e in _repair_entries()}


def lookup_entry(category_id, required_operation, carrier_operation):
    """Return the authored entry whose trigger exactly matches the (category, required op,
    carrier op) triple, or None. Exact match only — no fuzzy/partial matching, so the library
    never surfaces an explanation on an operation pair it was not authored for."""
    return _index().get((category_id, required_operation, carrier_operation))


if __name__ == "__main__":
    for e in ENTRIES:
        t = e["trigger"]
        print(f"{e['id']}: {t['category_id']} · {t['required_operation']} vs "
              f"{t['carrier_operation']}  [{e['arg_class']}/{e['outcome']}]")
