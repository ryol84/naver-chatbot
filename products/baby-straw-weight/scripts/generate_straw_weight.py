#!/usr/bin/env python3
"""
LV-2602 baby bottle straw weight — clean classic weight (추) shape.

Simple flat oval sinker / capsule. No organic blobs.
- Bottom intake holes (drink when weight settles)
- Smooth exterior (low friction vs plastic bottle)
- Plain Ø4.5 mm stem (easy clean)
- SG 1.8 → 9 g (5000 mm³)
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from trimesh.creation import cylinder, icosphere

ROOT = Path(__file__).resolve().parents[1]
STL_DIR = ROOT / "stl"
RENDER_DIR = ROOT / "renders"
DOCS_DIR = ROOT / "docs"

SG = 1.8
TARGET_MASS_G = 9.0
TARGET_VOLUME_MM3 = TARGET_MASS_G / SG * 1000.0

# Classic flat weight proportions (similar to original LV-2602 envelope)
BODY_RX = 16.0
BODY_RY = 9.5
BODY_RZ = 5.0

# Neat bottom holes — 4 holes in a clean rectangle (not a creepy cluster)
INTAKE_R = 1.55  # Ø3.1 mm
INTAKE_DEPTH = 5.5
INTAKE_XY = [(-4.5, 2.8), (-4.5, -2.8), (2.0, 2.8), (2.0, -2.8)]

BORE_D = 2.2
BORE_R = BORE_D / 2.0

STEM_OD = 4.5
STEM_R = STEM_OD / 2.0
STEM_LEN = 9.0
STEM_LEAD_LEN = 2.0
STEM_LEAD_TIP_R = 2.05

MESH_SUBDIV = 5  # smoother classic surface


def _translate(mesh: trimesh.Trimesh, xyz) -> trimesh.Trimesh:
    m = mesh.copy()
    m.apply_translation(xyz)
    return m


def _boolean(a: trimesh.Trimesh, b: trimesh.Trimesh, op: str) -> trimesh.Trimesh:
    if op == "difference":
        out = a.difference(b)
    elif op == "union":
        out = a.union(b)
    else:
        out = a.intersection(b)
    if isinstance(out, trimesh.Scene):
        out = trimesh.util.concatenate(tuple(out.geometry.values()))
    if not isinstance(out, trimesh.Trimesh):
        raise RuntimeError(f"Boolean {op} failed: {type(out)}")
    return out


def make_body(rx: float, ry: float, rz: float) -> trimesh.Trimesh:
    """Single smooth flat ellipsoid — classic weight / sinker look."""
    body = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    body.apply_scale([rx, ry, rz])
    return body


def make_bottom_intakes(rz: float) -> trimesh.Trimesh:
    cutters = []
    for x, y in INTAKE_XY:
        c = cylinder(radius=INTAKE_R, height=INTAKE_DEPTH + rz, sections=48)
        z_center = -rz + INTAKE_DEPTH * 0.25
        cutters.append(_translate(c, [x, y, z_center]))
    u = cutters[0]
    for c in cutters[1:]:
        u = _boolean(u, c, "union")
    return u


def make_cavity_link() -> trimesh.Trimesh:
    """Shallow internal channel linking holes to the bore — flushable."""
    # Axial slot just above bottom holes
    slot = cylinder(radius=1.4, height=10.0, sections=48)
    slot.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    slot = _translate(slot, [-1.2, 0.0, -1.2])
    # Cross link
    cross = cylinder(radius=1.3, height=7.5, sections=48)
    cross.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    )
    cross = _translate(cross, [-1.2, 0.0, -1.2])
    return _boolean(slot, cross, "union")


def make_bore(rx: float) -> trimesh.Trimesh:
    x_start = -rx - 2.0
    x_end = rx + STEM_LEN + 3.0
    bore = cylinder(radius=BORE_R, height=x_end - x_start, sections=64)
    bore.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    return _translate(bore, [(x_start + x_end) / 2.0, 0.0, 0.0])


def make_stem(rx: float) -> trimesh.Trimesh:
    """Plain Ø4.5 shaft + soft tip taper. No ribs."""
    shaft = cylinder(radius=STEM_R, height=STEM_LEN, sections=64)
    shaft.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    shaft = _translate(shaft, [rx + STEM_LEN / 2.0, 0.0, 0.0])

    n = 64
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    tip_x = rx + STEM_LEN
    ring_base = np.column_stack(
        [np.full(n, tip_x - STEM_LEAD_LEN), STEM_R * np.cos(th), STEM_R * np.sin(th)]
    )
    ring_tip = np.column_stack(
        [
            np.full(n, tip_x + 0.15),
            STEM_LEAD_TIP_R * np.cos(th),
            STEM_LEAD_TIP_R * np.sin(th),
        ]
    )
    cone = trimesh.convex.convex_hull(np.vstack([ring_base, ring_tip]))
    stem = _boolean(shaft, cone, "union")

    # Minimal blend so body→stem isn't a sharp dirt ledge
    blend = icosphere(subdivisions=3, radius=0.7)
    for ang in np.linspace(0, 2 * np.pi, 16, endpoint=False):
        s = blend.copy()
        s.apply_translation(
            [rx, STEM_R * 0.9 * np.cos(ang), STEM_R * 0.9 * np.sin(ang)]
        )
        stem = _boolean(stem, s, "union")
    return stem


def measure_stem_od(mesh: trimesh.Trimesh, rx: float) -> float | None:
    x = rx + STEM_LEN * 0.65
    sec = mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
    if sec is None:
        return None
    planar, _ = sec.to_2D()
    if not planar.polygons_full:
        return None
    poly = max(planar.polygons_full, key=lambda p: abs(p.area))
    minx, miny, maxx, maxy = poly.bounds
    return float(max(maxx - minx, maxy - miny))


def assemble(rx: float, ry: float, rz: float) -> trimesh.Trimesh:
    solid = _boolean(make_body(rx, ry, rz), make_stem(rx), "union")
    solid = _boolean(solid, make_bottom_intakes(rz), "difference")
    solid = _boolean(solid, make_cavity_link(), "difference")
    solid = _boolean(solid, make_bore(rx), "difference")
    comps = solid.split(only_watertight=False)
    if len(comps) > 1:
        solid = max(comps, key=lambda m: abs(m.volume))
    return solid


def tune_body_to_volume(
    target: float = TARGET_VOLUME_MM3,
    tol: float = 30.0,
    max_iter: int = 8,
) -> tuple[trimesh.Trimesh, dict]:
    rx, ry, rz = BODY_RX, BODY_RY, BODY_RZ
    history = []
    mesh = assemble(rx, ry, rz)

    for i in range(max_iter):
        vol = float(mesh.volume)
        history.append({"iter": i, "ry": ry, "rz": rz, "volume_mm3": vol})
        if abs(target - vol) <= tol:
            break
        flat_ratio = rz / ry
        factor = 1.0 + (((target / vol) ** 0.5) - 1.0) * 0.85
        ry *= factor
        rz = min(ry * flat_ratio, 6.0)
        mesh = assemble(rx, ry, rz)

    trimesh.repair.fix_normals(mesh)
    mesh.process(validate=True)

    meta = {
        "revision": 3,
        "target_volume_mm3": target,
        "final_volume_mm3": float(mesh.volume),
        "final_mass_g_at_sg": float(mesh.volume) / 1000.0 * SG,
        "volume_error_mm3": float(mesh.volume) - target,
        "body_rx_mm": rx,
        "body_ry_mm": ry,
        "body_rz_mm": rz,
        "extents_mm": mesh.extents.tolist(),
        "bounds_mm": mesh.bounds.tolist(),
        "watertight": bool(mesh.is_watertight),
        "faces": int(len(mesh.faces)),
        "stem_od_nominal_mm": STEM_OD,
        "stem_od_measured_mm": measure_stem_od(mesh, rx),
        "stem_length_mm": STEM_LEN,
        "bore_d_mm": BORE_D,
        "intake_d_mm": INTAKE_R * 2,
        "intake_count": len(INTAKE_XY),
        "sg": SG,
        "tune_history": history,
        "design": {
            "name": "Classic flat weight (추)",
            "name_ko": "기본 납작 추 모양",
            "material": "100% silicone",
            "features": [
                "simple flat ellipsoid weight shape",
                "4 neat bottom intake holes",
                "plain Ø4.5 mm stem",
                "smooth low-friction exterior",
            ],
        },
    }
    return mesh, meta


def export_preview(mesh: trimesh.Trimesh, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    preview = mesh.copy()
    if len(preview.faces) > 9000:
        preview = preview.simplify_quadric_decimation(face_count=9000)

    fig = plt.figure(figsize=(12.5, 4.2), facecolor="#f4f5f6")
    configs = [
        ("Perspective", 20, -55),
        ("Side", 5, -90),
        ("Bottom holes", -80, -90),
    ]
    for i, (title, elev, azim) in enumerate(configs, 1):
        ax = fig.add_subplot(1, 3, i, projection="3d")
        ax.add_collection3d(
            Poly3DCollection(
                preview.triangles,
                alpha=0.97,
                facecolor="#7a9eab",
                edgecolor="#334850",
                linewidths=0.03,
            )
        )
        b = preview.bounds
        ax.set_xlim(b[0, 0], b[1, 0])
        ax.set_ylim(b[0, 1], b[1, 1])
        ax.set_zlim(b[0, 2], b[1, 2])
        ax.set_title(title, fontsize=10)
        ax.set_facecolor("#f4f5f6")
        ax.view_init(elev=elev, azim=azim)
        try:
            ax.set_aspect("equal")
        except Exception:
            pass
        ax.tick_params(labelsize=6)
    fig.suptitle(
        "LV-2602 rev3 — classic flat weight (추) · bottom holes · Ø4.5 stem",
        fontsize=12,
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def export_hero(mesh: trimesh.Trimesh, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    preview = mesh.copy()
    if len(preview.faces) > 7000:
        preview = preview.simplify_quadric_decimation(face_count=7000)
    fig = plt.figure(figsize=(8, 5.2), facecolor="#eef1f2")
    ax = fig.add_subplot(111, projection="3d")
    ax.add_collection3d(
        Poly3DCollection(
            preview.triangles,
            alpha=0.97,
            facecolor="#6d95a3",
            edgecolor="#2a4148",
            linewidths=0.025,
        )
    )
    b = preview.bounds
    ax.set_xlim(b[0, 0], b[1, 0])
    ax.set_ylim(b[0, 1], b[1, 1])
    ax.set_zlim(b[0, 2], b[1, 2])
    ax.view_init(elev=22, azim=-58)
    try:
        ax.set_aspect("equal")
    except Exception:
        pass
    ax.set_facecolor("#eef1f2")
    ax.set_title("LV-2602 classic weight (추)\n9g · bottom holes · plain Ø4.5", fontsize=11)
    ax.set_xlabel("X mm")
    ax.set_ylabel("Y mm")
    ax.set_zlabel("Z mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    STL_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    mesh, meta = tune_body_to_volume()
    stl_path = STL_DIR / "LV-2602-straw-weight-9g.stl"
    mesh.export(stl_path)

    try:
        export_preview(mesh, RENDER_DIR / "preview_3view.png")
        export_hero(mesh, RENDER_DIR / "hero.png")
        meta["preview"] = "renders/preview_3view.png"
        meta["hero"] = "renders/hero.png"
    except Exception as e:
        meta["preview_error"] = str(e)

    (DOCS_DIR / "design_metrics.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in meta.items() if k != "tune_history"}, indent=2))
    print(f"Wrote {stl_path}")


if __name__ == "__main__":
    main()
