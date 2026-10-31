#!/usr/bin/env python3
"""
roof_systems/wood_shake/wood_shake_content.py — what the wood-shake package SAYS (FRAME v101)
=============================================================================================
The words, numbers and authorities that are wood shake's, registered with core/registry/package_content.py so that
core's machinery — the report renderer, the comparison argument lookup, the label map, Layer A's matcher — never
names this material (Migration Plan Amendment A2 §2 groups B–E, §3 item 10):

  B  the felt-interlayment callout's numbers and text, and the §3 section title   (were module3_report_renderer)
  C  the three authored repair-logic entries (S-1..S-3) and the shake-vs-laminate
     method explanation                                                             (were repair_logic_library,
                                                                                      scope_argument_builder)
  D  the field covering's display label                                             (was category_display_names)
  E  the carrier vocabulary for the field covering                                  (was carrier_layer_a)

Every string and number below is the one core held at v100, moved byte-for-byte; the frozen reports prove it
(A4/A5). Imported by wood_shake_categories.py, so the bridge's one boot-helper line still loads it on every page.
"""
from package_content import CarrierPattern, register_package_content
from repair_logic_library import CONDITION, DEFINITIONAL, DISPEL, STANDOFF   # core's vocabulary for an entry
from wood_shake_categories import FIELD_CATEGORY_ID, SYSTEM_ID

# ---- D: the label (category_display_names held it at v100) ----------------------------------------------------
DISPLAY_LABELS = {FIELD_CATEGORY_ID: "Wood shake field"}

# ---- E: Package Contract item 10 — how a carrier writes this material (carrier_layer_a._RULES held it) ----------
CARRIER_PATTERNS = (
    # field=True: the FIELD covering, the least specific rule — a line naming a specific component as well
    # (starter, ridge/hip cap, valley metal, a flashing, a vent, tear-off) is that component, not the field.
    CarrierPattern(r"wood\s*shake|shakes?\b|cedar\s*shake", FIELD_CATEGORY_ID, True, "high", True),
)

# ---- C: the authored repair-logic entries (repair_logic_library.ENTRIES held them) -------------------------------
REPAIR_ENTRIES = (
    {
        "id": "S-1",
        "trigger": {
            "category_id": FIELD_CATEGORY_ID,
            "required_operation": "R_AND_R",
            "carrier_operation": "DETACH_RESET",
        },
        "explanation": (
            "A detach-and-reset operation assumes the existing cedar shakes can be removed "
            "and reinstalled while remaining a serviceable weather-shedding roof covering. "
            "Whether that assumption is valid depends on the physical condition of the "
            "existing roof. Where the existing shakes cannot be removed and returned to "
            "service without compromising their ability to perform as the roof covering, "
            "detach-and-reset is not an equivalent repair operation to remove-and-replace."
        ),
        "arg_class": CONDITION,
        "authority_primary": (
            "Physical condition and serviceability of the existing cedar roof covering"
        ),
        "authority_supporting": (
            "CSSB repair-versus-replacement methodology recognizes repair decisions depend "
            "on roof condition and method rather than a single universal rule "
            "(CSSB Adjusters Guide to Hail)."
        ),
        "outcome": STANDOFF,
        "evidence_required": True,
        "evidence_basis": [
            "brittleness/splitting", "weathering", "enlarged nail holes",
            "damage on withdrawal", "loss of weather resistance",
            "repair difficulty on a poor-condition roof",
        ],
        "suppressed": ["careful-storage-labor argument"],
    },
    {
        "id": "S-2",
        "trigger": {
            "category_id": FIELD_CATEGORY_ID,
            "required_operation": "R_AND_R",
            "carrier_operation": "INSTALL_ONLY",
        },
        "explanation": (
            "A remove-and-replace operation consists of removing and disposing of the "
            "existing roofing material, furnishing new roofing material, and installing that "
            "new material. An install-only operation addresses only the installation of "
            "roofing material; it does not include removal and disposal of the existing roof "
            "covering or furnishing the replacement material. The operations describe "
            "different scopes of work and are therefore not equivalent repair operations."
        ),
        "arg_class": DEFINITIONAL,
        "authority_primary": "Definitional / scope composition",
        "authority_supporting": None,
        "outcome": DISPEL,
        "evidence_required": False,
        "evidence_basis": [],
        "suppressed": [],
    },
    {
        "id": "S-3",
        "trigger": {
            "category_id": FIELD_CATEGORY_ID,
            "required_operation": "R_AND_R",
            "carrier_operation": "REPLACE",
        },
        "explanation": (
            "A remove-and-replace operation includes removal and disposal of the existing "
            "roofing material, furnishing replacement material, and installation of that "
            "replacement material. A replace operation includes furnishing and installing "
            "replacement material but does not, by itself, describe removal and disposal of "
            "the existing roof covering. The operations describe different scopes of work "
            "and are therefore not equivalent repair operations."
        ),
        "arg_class": DEFINITIONAL,
        "authority_primary": "Definitional / scope composition",
        "authority_supporting": None,
        "outcome": DISPEL,
        "evidence_required": False,
        "evidence_basis": [],
        "suppressed": [],
    },
)

# ---- C: Section 3's method explanation (scope_argument_builder held it) -------------------------------------------
METHOD_EXPLANATION = (
    "Wood shake repairs differ from laminate shingle repairs. Wood shakes are individual shake "
    "components installed in overlapping courses, and the felt interlayment is integrated between "
    "the shake courses rather than sitting as one continuous layer beneath the roof covering. "
    "Because the components interlock course over course, a localized repair requires opening and "
    "rebuilding the affected assembly piece-by-piece; the repair affects the surrounding assembly, "
    "not just the single damaged component."
)

# ---- B: the report's §3 title and the felt-interlayment callout (module3_report_renderer held them) --------------
SEC3_TITLE = "Wood shake repair analysis"

# Quoted verbatim from the CSSB FAQ (cssbureau.com). The strip-width sentence is the AUTHORITY for
# the interlayment quantity; the second sentence is CSSB's own deferral to the local Building
# Official — the burden-shift framing this report is built on. The placement sentence ("bottom edge
# ... twice the weather exposure") is deliberately omitted: it is a PLACEMENT rule, not the quantity
# ratio, and this report never states it as the multiplier.
CSSB_INTERLAYMENT_QUOTE = ('The CSSB recommends using an 18" wide strip of No.30 ASTM D226 Type II '
                           'or ASTM D4869 Type IV roofing felt laid over the top portion of the '
                           'shakes and extending on to the sheathing. Check with your local '
                           'Building Official for exact specifications in your area.')


def felt_interlayment_callout(felt_sq, affected_sq):
    """The felt callout's NUMBERS and TEXT, for core to render. The measured exposure is recovered from the
    interlayment ratio (strip / ratio) — the section projection does not carry exposure. `heading` and `body` are
    HTML-safe text (they carry HTML character entities); `source` and `quote` are plain text the renderer escapes.
    Raises ZeroDivisionError / ValueError on degenerate inputs; the renderer then omits the callout."""
    # function-local: this module loads on EVERY page through the boot helper; a top-level import would pull the
    # whole scoping engine (and the geometry registration it imports) into page 3's boot. One authority, read here.
    from module2_scope_expansion import CSSB_INTERLAYMENT_STRIP_IN
    ratio = felt_sq / affected_sq
    exposure = CSSB_INTERLAYMENT_STRIP_IN / ratio
    affected_sf = affected_sq * 100.0
    felt_sf = felt_sq * 100.0
    return {
        "heading": "Felt interlayment &mdash; why it exceeds the affected area.",
        "body": (f"One {CSSB_INTERLAYMENT_STRIP_IN:.0f}&Prime; CSSB felt strip is laid over the top of "
                 f"every shake course, and courses repeat every {exposure:.1f}&Prime; of measured "
                 f"exposure, so the interlayment overlaps itself up the slope: "
                 f"{CSSB_INTERLAYMENT_STRIP_IN:.0f}&Prime; &divide; {exposure:.1f}&Prime; = "
                 f"{ratio:.2f} SF of felt per SF of roof. Therefore {affected_sf:,.1f} SF affected "
                 f"&times; {ratio:.2f} = {felt_sf:,.1f} SF = {felt_sq:,.2f} SQ &mdash; the felt quantity "
                 "is larger than the affected area for this reason, not by error."),
        "source": "CSSB",
        "quote": CSSB_INTERLAYMENT_QUOTE,
    }


register_package_content(
    SYSTEM_ID,
    display_labels=DISPLAY_LABELS,
    carrier_patterns=CARRIER_PATTERNS,
    repair_entries=REPAIR_ENTRIES,
    texts={"sec3_title": SEC3_TITLE, "method_explanation": METHOD_EXPLANATION,
           "felt_interlayment_callout": felt_interlayment_callout},
)
