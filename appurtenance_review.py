"""THE ONE SHARED APPURTENANCE REVIEW AUTHORITY — item-specific size/label review and confirmation.

WHAT PROBLEM THIS SOLVES
------------------------
`appurtenance_types.size_suggests_mislabel()` already decides, for both installed roof-system
packages, that an item measures so much more than its declared type's standard base that the label is
in doubt. Through v106.6g2/B1 the only thing done with that decision was to append
`mislabel_citation()`'s sentence to a package-produced scope line's `citation` and raise its `gate`
to CONFIRM. Three things were wrong with stopping there, and B2 fixes exactly those three:

  1. NOBODY IS ASKED. Neither page 2 nor pages 3/4 presents the discrepancy as an actionable item. The
     user with the authority to correct or confirm a label never sees the question.
  2. THE QUESTION LEAKS INTO A CARRIER DOCUMENT. The exported report can carry
     "SIZE DOES NOT MATCH THE LABEL … confirm the type" on an AGGREGATED line. That is an internal
     question printed in a document an adjuster and an appraiser read.
  3. THE LINE CANNOT SAY WHICH THING IT MEANS. Aggregation merges by
     (category_id, unit, gate, xact_code, item_key, material); two visually identical pipe-jack lines
     on the same slope do not tell an estimator WHICH physical penetration is in doubt.

So this module turns one engine opinion into an ITEM-SPECIFIC REVIEW with an explicit user decision,
and it is the single authority for that. It does NOT re-decide anything: the factor, the standard
bases, the flashing methods and the 2.0 threshold stay in `appurtenance_types`, and this module calls
them. Nothing here is duplicated in JavaScript — page 2 asks the engine, through the bridge, and
renders the answer.

WHAT IS AND IS NOT A REVIEW
---------------------------
A material line's existing `gate="CONFIRM"` tier and an UNRESOLVED SIZE-MISLABEL REVIEW are not the
same thing and must never be conflated. A power vent is CONFIRM because the user must say cover-vs-fan;
a chimney is CONFIRM because its flashing is mfr/IRC; a user-defined OTHER is CONFIRM because the tool
did not classify it. All three are legitimate and none is a review. Only the size/label question is,
and only while it is unresolved. Code that blocks or strips "all CONFIRM lines" would break three
working features to fix one.

THE SIX RULES THIS MODULE IMPLEMENTS, each because it is the thing that goes wrong without it
----------------------------------------------------------------------------------------------
R1  ONE ITEM, NOT A CATEGORY AND NOT A LINE. A review names its source (XML or user-placed), its
    item id (penetration face id, or the user's designator), its host facet, the type and - for OTHER
    - the category the user declared, the MEASURED width and height, the standard base those were
    compared against, the factor, and a stable reason code. Enough to tell two matching-looking
    penetrations on one slope apart, which is the thing the aggregated line could not do.

R2  IN THE SELECTED WORK, OR NOT BLOCKING. An XML marker the parser found but the user never put in
    scope is not a reason to stop the whole roof. The in-scope set is the user's own: a penetration is
    in scope when page 2 emitted a row for it (`selectedRepairAppurtenanceRows()` -> the selection's
    `appurtenances`), and a user item when its row says `repair_event`. Detection still reports
    out-of-scope suspicious items - `blocking=False` - so a later selection change surfaces them
    rather than discovering them at export time.

R3  THE DECISION IS KEYED TO THE FACTS, NOT TO THE ITEM'S NAME. A confirmation authorises exactly the
    reviewed fact. The key covers the ROOF (a fingerprint of the XML), the source, the item (or the
    group of markers that are one physical item), the declared type and category, and the measured
    dimensions. Change any of them and the old key no longer matches, so the item returns to
    unreviewed while the discrepancy stands. A new upload cannot inherit acceptance; a different roof
    that happens to reuse `F71` cannot inherit it; deleting a user item and creating another with the
    same designator cannot inherit it.

R4  ONE PHYSICAL ITEM, ONE DECISION, NO HIDDEN MARKER. EagleView splits one chimney into one marker
    per facet it crosses, and the packages already dedupe the MATERIAL line by `group`. Reviews follow
    the same grouping for the DECISION - every marker in a group shares one `decision_key`, so the
    user answers once - while every affected marker still gets its own record, so none is hidden and
    none is charged twice.

R5  CONFIRMING PRESERVES; CORRECTING RECOMPUTES. An explicit confirmation changes NOTHING about the
    computation: the selected type, the engine-chosen flashing method and every quantity stay exactly
    as they were. It only records that a human accepted the fact. A correction is not handled here at
    all - the user changes the type in the selection through page 2's existing validated controls, and
    the package's existing engine recalculates. This module never guesses a better type and never
    clamps an oversized measurement down to its nominal base.

R6  FAIL CLOSED. Missing review data, an engine error, an unknown identifier, a malformed confirmation
    payload: all of those mean UNRESOLVED, never "nothing pending". An empty review set is trusted
    only when the check actually ran to completion, which is why `review_report()` returns an explicit
    `ok` flag rather than just a list - an exception path that returned `[]` would read as "all clear".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from appurtenance_types import (MISLABEL_FACTOR, mislabel_citation, resolve_type,
                                size_suggests_mislabel, standard_base_in)

# The one reason code this module emits today. A code, not a sentence, so a caller can branch on it
# and a future reason can be added without re-parsing English.
REASON_SIZE_EXCEEDS_BASE = "SIZE_EXCEEDS_STANDARD_BASE"

SOURCE_XML = "XML"
SOURCE_USER = "USER"

DECISION_CONFIRMED = "CONFIRMED"


@dataclass
class ReviewItem:
    """One physical item whose declared type its measurement disagrees with. R1."""
    source: str                     # SOURCE_XML | SOURCE_USER
    item_id: str                    # penetration face id, or the user's designator
    host_id: str                    # host facet / structure, where known ("" when not)
    declared_type: str              # the type the user selected
    declared_category: str          # for OTHER: the registry category; "" otherwise
    width_in: float
    height_in: float
    standard_base_in: float
    factor: float
    reason_code: str
    group: str                      # the physical-item group this marker belongs to (R4)
    blocking: bool                  # is it in the selected work? (R2)
    decision_key: str = ""          # the fingerprint a confirmation must carry (R3)

    def label(self) -> str:
        host = f" / host {self.host_id}" if self.host_id else ""
        return f"{self.item_id}{host}"

    def reason_text(self) -> str:
        """The concrete, intelligible sentence page 2 shows. The item's OWN figures, always.

        Deliberately built from this record's fields rather than from a template with example
        numbers in it: the B2 assignment is explicit that F70's figures must never appear as
        literals for another roof's item.
        """
        t = resolve_type(self.declared_type, self.declared_category)
        name = (t.note.split(",")[0] if t is not None and t.note else self.declared_type)
        return (f"{self.label()} is marked {self.declared_type.title()}"
                + (f" ({self.declared_category})" if self.declared_category else "")
                + f"; its longest measured dimension is {max(self.width_in, self.height_in):g} in, "
                f"while {name} normally has a {self.standard_base_in:g} in flashing base "
                f"({self.factor:g}x). Please verify the type.")

    def as_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label()
        d["reason_text"] = self.reason_text()
        return d


@dataclass
class ReviewReport:
    """The result of a completed check. R6: `ok` is what makes an empty list trustworthy."""
    ok: bool
    items: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)
    error: str = ""
    roof_fingerprint: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error": self.error,
            "roof_fingerprint": self.roof_fingerprint,
            "items": [i.as_dict() for i in self.items],
            "unresolved": [i.as_dict() for i in self.unresolved],
            "unresolved_ids": sorted({i.item_id for i in self.unresolved}),
            "blocked": bool(self.unresolved) or not self.ok,
        }


# ---------------------------------------------------------------------------
def roof_fingerprint(xml_text: str) -> str:
    """Identifies THE ROOF, so a confirmation cannot cross claims. R3.

    A different upload is a different roof even when its face ids collide with the old one's, which
    is exactly the case `F71` makes likely: EagleView numbers faces per report, so two unrelated
    claims routinely both contain an F71. Keying on ids alone would let one roof's acceptance silence
    another roof's question.
    """
    return hashlib.sha256((xml_text or "").encode("utf-8")).hexdigest()[:16]


def _num(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return f if f == f and abs(f) != float("inf") else 0.0


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _member_identity(item, dims) -> tuple:
    """One member's contribution to its group's identity: (item_id, host_id, w_in, h_in).

    B2r1 / B2-F03. `dims` is the SAME measured pair this member already contributes to the key's
    dimension list, passed in rather than re-read off the item, so the two can never disagree: a
    member's identity and its measurement are built from one value.
    """
    w, h = dims
    return (_norm(item.item_id), _norm(item.host_id), _num(w), _num(h))


def _nominal_member(item_id, host_id, w_in, h_in, declared_type, declared_category) -> tuple:
    """One NOMINAL member's contribution to its group's identity. B2r2 / B2r1-F04.

    A nominal member is an explicit item in a group whose own measurement the shared predicate does
    NOT flag, so it never becomes a ReviewItem. It is still part of the physical item, so its full
    facts -- id, host, measured width and height, declared type and category -- go into the group's
    key. The type and category are carried per member because, unlike reviewed members, a nominal
    member's declaration is not otherwise in the key."""
    return (_norm(item_id), _norm(host_id), _num(w_in), _num(h_in), _norm(declared_type),
            _norm(declared_category))


def decision_key(*, roof: str, source: str, group: str, declared_type: str, declared_category: str,
                 width_in: float = 0.0, height_in: float = 0.0, dims: Sequence = (),
                 members: Sequence = (), nominal: Sequence = ()) -> str:
    """The fingerprint a confirmation authorises. R3 + R4.

    ONE KEY PER PHYSICAL ITEM, OVER THE WHOLE GROUP'S FACTS — and getting that right took measuring.
    The first version put the single marker's width and height in the key, which made grouped markers
    produce DIFFERENT keys and so demanded a separate decision for each. That is wrong on the facts:
    EagleView splits one physical chimney into one marker per facet it crosses, and each marker's
    footprint on its own plane is genuinely a different rectangle (Yager's F70 is 24 x 46.32in while
    F71 is 78 x 30.01in). A group key therefore cannot carry "the" dimensions, because there is no
    such thing.

    So the key carries the group's dimensions as a SORTED LIST of every member's rounded (w, h). That
    gives exactly the two properties R4 needs at once: every marker in the group computes the same
    key, so the user answers once — and a change to ANY member's measurement changes the list, so the
    whole physical item returns to unreviewed. `width_in`/`height_in` remain for the single-marker
    case, where the list is just that one pair.

    B2r1 / finding B2-F03 — WHY THE DIMENSION LIST IS NOT ENOUGH. Independent QA reproduced a false
    acceptance that this function allowed: confirm `U1` on host `F1` in group `G`, then replace it
    with `U2` on host `F2` in the SAME group `G`, same type, category and dimensions. Every field the
    key hashed was unchanged, so the key was unchanged, so a DIFFERENT physical item on a DIFFERENT
    facet inherited the acceptance and `review_report()` returned `blocked=False` with no unresolved
    ids. The group name was being trusted to identify the item, but a group name is a user-editable
    link label: it survives the item it was created for.

    The key therefore also carries `members` — the group's membership as a SORTED LIST of
    (item_id, host_id, w, h). Identity now travels with the facts:

      * every marker of one genuinely linked item builds the SAME list, so one answer still clears
        the whole item in one click (R4 is preserved, not traded away);
      * an added, removed or replaced member changes the list;
      * a member that MOVES to another facet changes the list, even at identical dimensions — that
        is precisely the reproduced case;
      * and the per-member dimensions stay in it, so the old invalidation behaviour is unchanged.

    `dims` is retained alongside `members` rather than folded into it. It is what the single-marker
    and 0.01in-tolerance paths already hash, and collapsing the two would quietly restate an
    established behaviour while fixing a different one.

    Dimensions are rounded to 0.01in before hashing, in `members` exactly as in `dims`. Without that,
    a re-parse that produced 46.3199999 instead of 46.32 would silently invalidate a perfectly good
    confirmation; 0.01in is far below the 2.0x threshold's sensitivity, so nothing a user could care
    about is lost.

    B2r2 / finding B2r1-F04 — WHY `members` WAS STILL NOT THE WHOLE GROUP. `members` is built from the
    REVIEWED markers only, because pass 1 of `review_items()` keeps an item only when the shared
    predicate flags it. A group member whose own size is ordinary was therefore absent from the key,
    and independent QA reproduced the consequence twice: confirm U1 (30in OTHER/VENT_CAP) in group G,
    then add U2 (3in) to G -- or confirm Yager's F70+F71 as one PIPE group, then add F73 (0.6x) to it
    -- and the old key was returned unchanged with `blocked=False`. A changed physical item inherited
    an answer given about a different one.

    `nominal` is therefore the rest of the group: one (item_id, host_id, w, h, type, category) per
    explicit member that the predicate does NOT flag, built by `review_items()` from the same rows.
    It is hashed as a sorted list with the same normalisation and the same 0.01in rounding as
    `members`, so adding, deleting, replacing, moving, resizing or re-declaring a nominal member
    changes the key, while list order and sub-0.01in re-parse drift do not.

    Review DETECTION is untouched: a nominal member is never a ReviewItem, never warns and never
    blocks on its own. It only stops an old answer from being inherited by a changed group.

    The field is added to the payload ONLY WHEN THE GROUP HAS NOMINAL MEMBERS. A group whose members
    are all reviewed -- the only kind B2r1 could key correctly -- therefore produces exactly the key it
    produced before, so this repair invalidates no confirmation that was given about an unchanged
    group.
    """
    pairs = ([(round(_num(w), 2), round(_num(h), 2)) for w, h in dims] if dims
             else [(round(_num(width_in), 2), round(_num(height_in), 2))])
    # Identity is normalised the same way everywhere else in this module, so that "f1" and " F1 "
    # cannot be two different physical items.
    who = sorted((_norm(i).upper(), _norm(h).upper(),
                  round(_num(w), 2), round(_num(ht), 2)) for i, h, w, ht in members)
    body = {
        "roof": _norm(roof),
        "source": _norm(source).upper(),
        "group": _norm(group),
        "type": _norm(declared_type).upper(),
        "category": _norm(declared_category).upper(),
        "dims": sorted(pairs),
        "members": who,
    }
    if nominal:
        body["nominal"] = sorted((_norm(i).upper(), _norm(h).upper(), round(_num(w), 2),
                                  round(_num(ht), 2), _norm(t).upper(), _norm(c).upper())
                                 for i, h, w, ht, t, c in nominal)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
def _xml_measurements(geom) -> dict:
    """{penetration_face_id: (host_facet_id, w_ft, h_ft)} from the SAME emitter the estimator uses.

    Not a second measurement: `emit_penetration_candidates` is what `module1_service` consumes, and
    `appurtenance_zone_geometry` leaves the measured w/h untouched when it routes by type ("The
    routed geometry KEEPS any measured w/h"), so the numbers compared here are the numbers the
    packages compare. A measurement computed independently here could drift from the estimator's, and
    then page 2 would ask about a figure the report does not contain.
    """
    from candidate_emitters import emit_penetration_candidates
    out = {}
    for cand in emit_penetration_candidates(geom):
        params = cand.params or {}
        g = params.get("appurtenance_geometry") or {}
        pid = _norm(params.get("penetration_face_id"))
        if not pid:
            continue
        out[pid] = (_norm(params.get("host_facet_id")), g.get("w"), g.get("h"))
    return out


def review_items(xml_text: str, ui_selection: Mapping[str, Any] | None, *, geom=None):
    """Every suspicious item on this roof, each marked `blocking` if it is in the selected work.

    Raises nothing on ordinary bad input: a caller gets a ReviewReport with ok=False instead, because
    an exception that a caller swallows becomes "nothing pending". R6.
    """
    sel = ui_selection if isinstance(ui_selection, Mapping) else {}
    roof = roof_fingerprint(xml_text)
    items: list = []

    if geom is None:
        from eagleview_geometry_parser import parse_eagleview_geometry
        geom = parse_eagleview_geometry(xml_text)
    measured = _xml_measurements(geom)

    # ---- the in-scope sets, taken from the USER's own selection (R2) --------------------------
    rows = [r for r in (sel.get("appurtenances") or ()) if isinstance(r, Mapping)]
    in_scope_pens = {_norm(r.get("penetration_face_id")): r for r in rows}

    # FAIL CLOSED ON AN UNKNOWN IDENTIFIER (R6). A selection that names a penetration this geometry
    # does not contain means the facts could not be established for it -- the commonest cause being
    # that the XML did not parse into the roof the selection was built against. Without this, an
    # unparseable or swapped XML yields zero measurements, hence zero suspicious items, hence
    # "nothing pending" -- the exact fail-OPEN this module exists to prevent. The parser is lenient
    # enough to return an empty geometry for garbage, so the mismatch is what has to be detected.
    unknown = sorted(pid for pid in in_scope_pens if pid and pid not in measured)
    if unknown:
        raise LookupError(
            f"selection names penetration(s) {unknown} that this roof's geometry does not contain; "
            f"the review facts cannot be established, so nothing may be treated as resolved")

    # ---- pass 1: collect every suspicious marker, WITHOUT its key ----------------------------
    collected: list = []        # (ReviewItem, group_dims_contribution)
    # B2r2 / B2r1-F04: every explicit member the predicate does NOT flag, by (source, group). These
    # are NOT reviews -- they never become ReviewItems, never warn and never block -- but they are part
    # of the physical item, so pass 2 puts them into the group's key. Kept apart from `collected` so
    # that review DETECTION stays exactly what the shared predicate says it is.
    nominal: dict = {}
    for pid, (host, w_ft, h_ft) in sorted(measured.items()):
        row = in_scope_pens.get(pid)
        declared_type = _norm((row or {}).get("kind_label") or (row or {}).get("type"))
        declared_cat = _norm((row or {}).get("other_category"))
        if not declared_type:
            # Undefined on page 2. Page 2 already refuses to continue past an undefined penetration
            # that sits in a repair area, so there is no second question to ask here and nothing to
            # compare: a type the user has not chosen cannot disagree with a measurement.
            continue
        group = _norm((row or {}).get("group")) or pid
        mis = size_suggests_mislabel(declared_type, declared_cat or None, w_ft, h_ft)
        if mis is None:
            nominal.setdefault((SOURCE_XML, group), []).append(_nominal_member(
                pid, host, _num(w_ft) * 12.0, _num(h_ft) * 12.0, declared_type, declared_cat))
            continue
        base, measured_in, factor = mis
        collected.append((ReviewItem(
            source=SOURCE_XML, item_id=pid, host_id=host,
            declared_type=declared_type, declared_category=declared_cat,
            width_in=round(_num(w_ft) * 12.0, 2), height_in=round(_num(h_ft) * 12.0, 2),
            standard_base_in=float(base), factor=float(factor),
            reason_code=REASON_SIZE_EXCEEDS_BASE, group=group,
            blocking=row is not None), (_num(w_ft) * 12.0, _num(h_ft) * 12.0)))

    for r in (sel.get("user_appurtenance_repairs") or ()):
        if not isinstance(r, Mapping):
            continue
        designator = _norm(r.get("designator") or r.get("label"))
        declared_type = _norm(r.get("kind_label") or r.get("type"))
        declared_cat = _norm(r.get("other_category"))
        if not designator or not declared_type:
            continue
        # A hand-placed POINT states no size, so there is nothing for a measurement to disagree with
        # (size_suggests_mislabel returns None for that, and this loop relies on it rather than
        # inventing a dimension).
        w_ft, h_ft = r.get("width"), r.get("height")
        group = _norm(r.get("group")) or designator
        mis = size_suggests_mislabel(declared_type, declared_cat or None, w_ft, h_ft)
        if mis is None:
            nominal.setdefault((SOURCE_USER, group), []).append(_nominal_member(
                designator, r.get("host_facet_id"), _num(w_ft) * 12.0, _num(h_ft) * 12.0,
                declared_type, declared_cat))
            continue
        base, measured_in, factor = mis
        collected.append((ReviewItem(
            source=SOURCE_USER, item_id=designator, host_id=_norm(r.get("host_facet_id")),
            declared_type=declared_type, declared_category=declared_cat,
            width_in=round(_num(w_ft) * 12.0, 2), height_in=round(_num(h_ft) * 12.0, 2),
            standard_base_in=float(base), factor=float(factor),
            reason_code=REASON_SIZE_EXCEEDS_BASE, group=group,
            blocking=bool(r.get("repair_event", True))), (_num(w_ft) * 12.0, _num(h_ft) * 12.0)))

    # ---- pass 2: ONE key per (source, group), over that group's whole set of facts (R4) -------
    # Two passes are needed and not a style choice: a group's key depends on EVERY member's
    # dimensions AND on every member's identity (B2r1 / B2-F03), so no member can be keyed until all
    # of them have been seen.
    buckets: dict = {}
    for item, dims in collected:
        buckets.setdefault((item.source, item.group), []).append((item, dims))
    items = []
    for (source, group), members in buckets.items():
        # B2r2 / B2r1-F04: the rest of THIS group's physical membership -- same source, same group,
        # never another's -- goes into every key the group produces, including the per-marker keys of
        # a contradictory group, so no key for this group can outlive a change to who is in it.
        rest = nominal.get((source, group), [])
        types = {(m.declared_type.upper(), m.declared_category.upper()) for m, _ in members}
        if len(types) > 1:
            # One physical item declared as two different things is a contradiction the user must
            # resolve; keying it would authorise one reading of it. Each marker keeps its own key —
            # and that key carries its own identity, so a marker swapped into this contradictory
            # group cannot inherit the other marker's answer either.
            for item, dims in members:
                item.decision_key = decision_key(
                    roof=roof, source=source, group=f"{group}#{item.item_id}",
                    declared_type=item.declared_type, declared_category=item.declared_category,
                    dims=[dims], members=[_member_identity(item, dims)], nominal=rest)
                items.append(item)
            continue
        dtype, dcat = next(iter(types))
        # B2r1 / B2-F03: the membership goes into the key. The whole group shares ONE identity list,
        # so one confirmation still clears every marker of the same physical item in one click, while
        # any change to who is in the group — added, removed, replaced, or moved to another facet —
        # produces a different key and returns the item to unreviewed.
        key = decision_key(roof=roof, source=source, group=group, declared_type=dtype,
                           declared_category=dcat, dims=[d for _, d in members],
                           members=[_member_identity(m, d) for m, d in members], nominal=rest)
        for item, _ in members:
            item.decision_key = key
            items.append(item)
    items.sort(key=lambda i: (i.source, i.item_id))
    return items, roof


def confirmed_keys(ui_selection: Mapping[str, Any] | None):
    """The decision keys this selection carries an explicit confirmation for. R6.

    A malformed payload contributes NOTHING rather than raising: a raise here would be caught
    somewhere and turn into "nothing pending", which is the failure this whole module exists to
    prevent. Anything that is not a mapping with a 32-hex `key` and decision CONFIRMED is ignored, so
    a tampered or truncated payload leaves its item unresolved.
    """
    sel = ui_selection if isinstance(ui_selection, Mapping) else {}
    out = set()
    for row in (sel.get("appurtenance_reviews") or ()):
        if not isinstance(row, Mapping):
            continue
        key = _norm(row.get("key"))
        if len(key) != 32 or any(c not in "0123456789abcdef" for c in key.lower()):
            continue
        if _norm(row.get("decision")).upper() != DECISION_CONFIRMED:
            continue
        out.add(key.lower())
    return out


def review_report(xml_text: str, ui_selection: Mapping[str, Any] | None, *, geom=None) -> ReviewReport:
    """THE ONE ENTRY POINT. Recomputes the reviews from the CURRENT facts and validates the
    confirmations the selection carries against them.

    Recomputing is the point: a caller must never be able to decide "nothing pending" from a stored
    boolean, from the absence of a warning in a `citation`, or from what page 2's UI once showed. All
    three were reachable before B2 and all three are what §5 of the assignment calls the export
    backstop. R6 — any failure is `ok=False`, which `as_dict()['blocked']` reports as blocked.
    """
    try:
        items, roof = review_items(xml_text, ui_selection, geom=geom)
    except Exception as exc:                                       # noqa: BLE001 -- fail closed
        return ReviewReport(ok=False, error=f"{type(exc).__name__}: {exc}",
                            roof_fingerprint=roof_fingerprint(xml_text))
    have = confirmed_keys(ui_selection)
    unresolved = [i for i in items if i.blocking and i.decision_key not in have]
    return ReviewReport(ok=True, items=items, unresolved=unresolved, roof_fingerprint=roof)


def strip_internal_question(citation: str) -> str:
    """Remove the catalog's unresolved-question clause from a citation, leaving every other authority.

    Used ONLY once a review is resolved, and only on the clause this module's own catalog wrote. It
    matches on `mislabel_citation`'s actual prefix rather than on a hand-copied sentence, so the two
    cannot drift; and it leaves everything before the clause untouched, because that part is the
    legitimate authority (mfr / IRC, user-defined, a chimney code) that the carrier report must keep.
    """
    text = str(citation or "")
    marker = "; SIZE DOES NOT MATCH THE LABEL"
    at = text.find(marker)
    return text[:at].rstrip() if at >= 0 else text


# the clause's own prefix, exported so a test can assert the two are the same string rather than
# two copies of one sentence that could drift apart.
MISLABEL_CLAUSE_PREFIX = "; SIZE DOES NOT MATCH THE LABEL"
assert mislabel_citation((10.0, 78.0, 7.8)).startswith(MISLABEL_CLAUSE_PREFIX), (
    "appurtenance_types.mislabel_citation no longer starts with the clause this module strips; "
    "strip_internal_question would silently stop working")


# ---------------------------------------------------------------------------
def clear_resolved_questions(result) -> int:
    """Strip the catalog's unresolved-question clause from a computed result's citations.

    Called ONLY after `review_report()` says nothing is unresolved. PRESENTATION ONLY, and the
    boundary is exact: it rewrites `citation` text and touches nothing else. Quantities, categories,
    units, `xact_code`, `item_key`, `material` and the `gate` TIER are all left alone — a power vent
    or a chimney that is legitimately CONFIRM stays CONFIRM, because that tier is a real material
    assertion and not the size question. Returns how many citations it changed, so a caller can
    assert it did something rather than assume it.

    Why here rather than in the renderer: the clause can reach a carrier document through §3's lines,
    §5's comparison lines, a duplicate line and both report modes. Clearing it once at the computed
    result covers every one of those by construction, where a renderer-side filter would have to be
    repeated per section and would be one section behind the next report change.
    """
    import dataclasses

    # BOTH RoofAssemblyResult and AggregatedScopeLine are FROZEN dataclasses, so this rebuilds
    # rather than mutates: `line.citation = ...` raises FrozenInstanceError, which is the engine
    # correctly refusing to let a presentation step reach into a computed result. Each affected line
    # is replaced with a copy whose ONLY difference is the citation text -- dataclasses.replace
    # carries every other field forward verbatim, so qty, unit, gate, category_id, xact_code and
    # material_profile_id cannot be touched even by accident. That is what makes "presentation only"
    # a property of the code and not a promise in a comment.
    n = 0
    for bucket in ("aggregated_scope", "scope_lines", "lines"):
        lines = getattr(result, bucket, None)
        if not lines:
            continue
        rebuilt, changed = [], False
        for line in lines:
            cite = getattr(line, "citation", None)
            if isinstance(cite, str) and MISLABEL_CLAUSE_PREFIX in cite:
                rebuilt.append(dataclasses.replace(line, citation=strip_internal_question(cite)))
                changed = True
                n += 1
            else:
                rebuilt.append(line)
        if changed:
            object.__setattr__(result, bucket, type(lines)(rebuilt)
                               if isinstance(lines, tuple) else rebuilt)
    return n


def export_review_gate(xml_text: str, ui_selection: Mapping[str, Any] | None, *, geom=None) -> dict:
    """THE EXPORT BACKSTOP. Recompute the reviews and say whether a report may be produced.

    Independent of page 2 by construction: it takes the xml and the selection and recomputes, so it
    cannot be satisfied by a stored boolean, by what page 2's UI once displayed, by a bypassed
    Continue handler, or by the absence of a warning in a citation. A claim reached directly from
    stored session data, an old snapshot and a tampered confirmation all arrive here the same way.

    Returns the report as a dict, whose `blocked` is true when anything is unresolved OR when the
    check itself could not complete (R6).
    """
    return review_report(xml_text, ui_selection, geom=geom).as_dict()
