#!/usr/bin/env python3
"""Facet basis helpers for production geometry intake."""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

Point3 = Tuple[float, float, float]


def facet_fall_xy(points3d: Sequence[Point3]) -> Tuple[float, float]:
    """Return the world-XY downslope vector for an ordered facet vertex loop."""
    # Deliberately mirrors mkframe_pts' internal normal/fall basis so it can later be merged into the sealed engine.
    pp = [np.array(p, dtype=float) for p in points3d]
    nrm = np.zeros(3, dtype=float)
    for i in range(len(pp)):
        nrm += np.cross(pp[i], pp[(i + 1) % len(pp)])
    nrm /= np.linalg.norm(nrm)
    if nrm[2] < 0:
        nrm = -nrm
    g = np.array([0.0, 0.0, -1.0])
    fall = g - np.dot(g, nrm) * nrm
    return (float(fall[0]), float(fall[1]))


def facet_frame_axes(points3d_order: Sequence[Point3], eave_a: Point3, eave_b: Point3):
    """(origin, x_axis, up) for a facet. THE ONE fall-line basis (FRAME v105.1).

    The facet's in-plane frame: up is the uphill direction (minus gravity's in-plane part, the fall line), x_axis is
    perpendicular to it in the plane, flipped to agree with the anchor edge eave_a -> eave_b, and origin is the loop's
    first vertex. Every site that frames a facet calls this — geometry_core.mkframe_pts, both copies of
    _face_local_point_to_3d (module1_service, module2_assembly) and workbench_roof_layout._local_to_shared_transform.
    Through v105 the same arithmetic was written out FIVE times, and v105 guarded one: page 1's layout still divided
    by a zero fall on a flat facet and handed page 2 bare NaN (QA error 58).

    A FLAT facet has no fall line: its normal is (0,0,1), gravity's in-plane part is the ZERO vector, and normalising
    it is the NaN. The guard tests the RAW vector, before any divide. Below 1e-9 the basis comes from the anchor edge
    instead — x along it, up = cross(nrm, x), so cross(up, nrm) == x, the pitched branch's own handedness, and no flip
    is needed. Threshold measured: flat is exactly 0; the flattest PITCHED facet in any claim is 0.083045 (1/12).
    The pitched branch is the five copies' arithmetic, operation for operation, so every pitched facet frames
    bit-identically. facet_fall_xy above is NOT this: it returns the raw downslope, (0, 0) on a flat facet — honest."""
    pp = [np.array(p, dtype=float) for p in points3d_order]
    nrm = np.zeros(3)
    for i in range(len(pp)):
        nrm += np.cross(pp[i], pp[(i + 1) % len(pp)])
    nrm /= np.linalg.norm(nrm)
    if nrm[2] < 0:
        nrm = -nrm
    g = np.array([0.0, 0.0, -1.0])
    fall = g - np.dot(g, nrm) * nrm
    er = np.array(eave_b, dtype=float) - np.array(eave_a, dtype=float)
    if np.linalg.norm(fall) < 1e-9:                   # FLAT: no fall line exists
        x_axis = er / np.linalg.norm(er)
        up = np.cross(nrm, x_axis)
    else:
        fall /= np.linalg.norm(fall)
        up = -fall
        x_axis = np.cross(up, nrm)
        x_axis /= np.linalg.norm(x_axis)
        if np.dot(x_axis, er) < 0:
            x_axis = -x_axis
    return pp[0], x_axis, up
