#!/usr/bin/env python3
"""
INSTALLED ROOF-SYSTEM PACKAGES — the application's ONE composition root (FRAME ARC-05a)
=====================================================================================
This is the only module in deploy/ outside roof_systems/ that names an installed package. Everything else — core
geometry, the assembly, Module 1, the diagram, the comparison and the reports — asks the registries
(core/registry/roof_systems.py, shared_category_registry.py, core/registry/package_content.py) and names none.

Until ARC-05a the packages were registered as SIDE EFFECTS of imports scattered through shared code: the bridge's boot
helper imported both category modules, module1_service imported both geometry modules, module2_assembly and
workbench_diagram_data imported wood-shake helpers (which registered wood shake as a by-product), and
regression_test imported the wood-shake geometry module (package_isolation_gate exceptions E1-E4). Those edges are
gone; these functions are what they did, in one place, in a fixed order:

    install_vocabulary()     each installed package's CATEGORY module (which loads its CONTENT module): the category
                             ids it owns, its labels, carrier vocabulary and report text. Registers NO roof system and
                             loads no engine — exactly what the bridge's shared boot helper did on every page.
    install_roof_systems()   the vocabulary, then each installed package's GEOMETRY module, which registers the roof
                             system (profile resolver, disturbance strategies, scope engine, declarations, operations).
                             Exactly what module1_service's two imports did.
    install_assembly_roof_systems()
                             the roof systems the ASSEMBLY entry point (module2_assembly — and through it page 2's
                             workbench_seam) registers. ARC-05a kept this at wood shake only (ASSEMBLY_ENTRY_PACKAGES) as a
                             TEMPORARY no-behaviour-change measure. FRAME ARC-06a (owner direction, ARC-06a assignment
                             §3D): every engine entry point registers EVERY installed package — so page 2 lists both
                             installed coverings on a fresh load and asks the user to declare one (no wood-shake
                             default), exactly as page 1's project declaration already does. ASSEMBLY_ENTRY_PACKAGES is
                             now INSTALLED_PACKAGES itself, kept by name so no caller changes.

All three are idempotent (a module imports once; each registry's own idempotency check holds), deterministic (static
imports in the manifest's order — no filesystem scan, no import by computed name, no network), and FAIL CLOSED: if
a manifest entry did not register, they raise RegistryWiringError naming it.

ADDING AN INSTALLED PACKAGE (an installer's job, not core's): put its files under roof_systems/<id>/, add each file
to pyodide_bridge.js's ENGINE_FILES (and its byte-identical .txt twin), add its id to INSTALLED_PACKAGES, its category
import to install_vocabulary() and its geometry import (an `if` line plus the import) to install_roof_systems(). No
core, assembly, diagram, comparison or report module changes. The registration CONTRACT a package must satisfy is core/registry/roof_systems.register (and register_package_categories for its ids); see
docs/ARC05a_PACKAGE_CONTRACT.md.
"""
from __future__ import annotations

import roof_systems as _roof_systems
import shared_category_registry as _categories

# The installed packages, in installation order. The ORDER is the order the pre-ARC-05a code registered them in
# (wood shake's category module first at boot, wood shake's geometry module first in module1_service).
INSTALLED_PACKAGES = ("wood_shake", "modbit")


def _require_installed(registered, what):
    missing = [p for p in INSTALLED_PACKAGES if p not in registered]
    if missing:
        raise _categories.RegistryWiringError(
            f"FRAME installed_packages: {what} did not register installed package(s) {missing} (registered: "
            f"{sorted(registered)}). The manifest and its import lines disagree. (ARC-05a)")


def install_vocabulary():
    """Register every installed package's category ids and content. No roof system, no engine. Idempotent."""
    import wood_shake_categories   # noqa: F401  wood_shake: category ids (+ wood_shake_content: words)
    import modbit_categories       # noqa: F401  modbit: category ids (+ modbit_content: words)
    _require_installed(_categories.registered_packages(), "install_vocabulary()")
    return tuple(INSTALLED_PACKAGES)


# FRAME ARC-06a: the owner retired ARC-05a's temporary wood-shake-only assembly set — every installed package. The
# availability of a covering is decided HERE, once (the composition root); which covering a facet carries is the
# user's declaration (ProjectConfig / page 2), never a default.
ASSEMBLY_ENTRY_PACKAGES = INSTALLED_PACKAGES


def install_roof_systems(packages=None):
    """Register every installed package's vocabulary AND the roof systems of `packages` (default: every installed
    package), in manifest order. Idempotent. A name that is not an installed package RAISES (no silent subset)."""
    wanted = tuple(INSTALLED_PACKAGES) if packages is None else tuple(packages)
    unknown = [p for p in wanted if p not in INSTALLED_PACKAGES]
    if unknown:
        raise _categories.RegistryWiringError(
            f"FRAME installed_packages: {unknown} are not installed packages (installed: {list(INSTALLED_PACKAGES)}). "
            f"(ARC-05a)")
    install_vocabulary()
    if "wood_shake" in wanted:
        import wood_shake_geometry     # noqa: F401  wood_shake: the roof system (registers at import)
    if "modbit" in wanted:
        import modbit_geometry         # noqa: F401  modbit: the roof system (registers at import)
    missing = [p for p in wanted if p not in _roof_systems.registered()]
    if missing:
        raise _categories.RegistryWiringError(
            f"FRAME installed_packages: install_roof_systems() did not register installed package(s) {missing} "
            f"(registered: {sorted(_roof_systems.registered())}). The manifest and its import lines disagree. (ARC-05a)")
    return wanted


def install_assembly_roof_systems():
    """The assembly entry point's roof systems: every installed package (ARC-06a). Idempotent."""
    return install_roof_systems(ASSEMBLY_ENTRY_PACKAGES)
