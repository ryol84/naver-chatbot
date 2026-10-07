#!/usr/bin/env python3
"""
Baby silicone straw weight (추빨대 추) generator.

Targets
-------
- Material: 100% silicone, specific gravity 1.8
- Target mass: 9.0 g  ->  net volume 5.000 cm³ (5000 mm³)
- Hose stem outer diameter: 4.5 mm (easy insert + retention ribs)
- Cleanability: open front intake, through-bore, side flush ports
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh
from trimesh.creation import annulus, cylinder, icosphere

ROOT = Path(__file__).resolve().parents[1]
STL_DIR = ROOT / "stl"
RENDER_DIR = ROOT / "renders"
DOCS_DIR = ROOT / "docs"

SG = 1.8
TARGET_MASS_G = 9.0
TARGET_VOLUME_MM3 = TARGET_MASS_G / SG * 1000.0  # 5000

# Body half-axes (mm) — tuned iteratively toward target volume
BODY_RX = 15.4
BODY_RY = 9.6
BODY_RZ = 7.6

INTAKE_DEPTH = 8.2
INTAKE_RY = 4.0
INTAKE_RZ = 3.2

BORE_D = 2.2
BORE_R = BORE_D / 2.0

STEM_OD = 4.5
STEM_R = STEM_OD / 2.0
STEM_LEN = 11.0
STEM_LEAD_LEN = 2.4
STEM_LEAD_TIP_R = 1.95  # ~3.9 mm tip for easy hose start
RIB_COUNT = 2
RIB_OD = 5.4
RIB_LEN = 1.05
RIB_SPACING = 3.3
RIB_START = 3.6

MESH_SUBDIV = 4


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
    """Plump dewdrop silhouette — soft, baby-friendly, no sharp edges."""
    main = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    main.apply_scale([rx, ry, rz])

    cheek = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    cheek.apply_scale([rx * 0.55, ry * 1.06, rz * 1.03])
    cheek = _translate(cheek, [-1.2, 0, 0])

    nose = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    nose.apply_scale([rx * 0.40, ry * 0.70, rz * 0.76])
    nose = _translate(nose, [-rx * 0.58, 0, 0])

    # Gentle top ridge for a prettier, less “blob” look (still fully rounded)
    crest = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    crest.apply_scale([rx * 0.62, ry * 0.42, rz * 0.55])
    crest = _translate(crest, [-0.8, 0, rz * 0.35])

    body = _boolean(main, cheek, "union")
    body = _boolean(body, nose, "union")
    body = _boolean(body, crest, "union")
    return body


def make_intake_cutter(rx: float) -> trimesh.Trimesh:
    cutter = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    cutter.apply_scale([INTAKE_DEPTH * 0.55, INTAKE_RY, INTAKE_RZ])
    return _translate(cutter, [-rx + INTAKE_DEPTH * 0.12, 0, 0])


def make_bore(rx: float) -> trimesh.Trimesh:
    """Through-bore from front intake past the stem tip (must clear +X end)."""
    x_start = -rx - 4.0
    x_end = rx + STEM_LEN + 4.0
    length = x_end - x_start
    bore = cylinder(radius=BORE_R, height=length, sections=72)
    bore.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    mid = (x_start + x_end) / 2.0
    return _translate(bore, [mid, 0, 0])


def make_side_flush_ports(rx: float, ry: float, rz: float) -> trimesh.Trimesh:
    """Cross ports near the mouth so rinse water exits freely."""
    y_port = cylinder(radius=1.55, height=ry * 2.4, sections=48)
    y_port.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    )
    y_port = _translate(y_port, [-rx * 0.38, 0, 0])

    z_port = cylinder(radius=1.45, height=rz * 2.5, sections=48)
    z_port = _translate(z_port, [-rx * 0.38, 0, 0])

    return _boolean(y_port, z_port, "union")


def make_stem(rx: float) -> trimesh.Trimesh:
    """Exact 4.5 mm OD stem + lead-in taper + retention ribs."""
    shaft = cylinder(radius=STEM_R, height=STEM_LEN, sections=72)
    shaft.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    shaft = _translate(shaft, [rx + STEM_LEN / 2, 0, 0])

    n = 72
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    tip_x = rx + STEM_LEN
    ring_base = np.column_stack(
        [np.full(n, tip_x - STEM_LEAD_LEN), STEM_R * np.cos(th), STEM_R * np.sin(th)]
    )
    ring_tip = np.column_stack(
        [
            np.full(n, tip_x + 0.2),
            STEM_LEAD_TIP_R * np.cos(th),
            STEM_LEAD_TIP_R * np.sin(th),
        ]
    )
    cone = trimesh.convex.convex_hull(np.vstack([ring_base, ring_tip]))
    stem = _boolean(shaft, cone, "union")

    for i in range(RIB_COUNT):
        cx = rx + RIB_START + i * RIB_SPACING
        rib = annulus(
            r_min=STEM_R * 0.8,
            r_max=RIB_OD / 2,
            height=RIB_LEN,
            sections=72,
        )
        rib.apply_transform(
            trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
        )
        rib = _translate(rib, [cx, 0, 0])
        soft = icosphere(subdivisions=3, radius=RIB_LEN * 0.55)
        for ang in th[::3]:
            s = soft.copy()
            s.apply_translation(
                [
                    cx,
                    (RIB_OD / 2 * 0.9) * np.cos(ang),
                    (RIB_OD / 2 * 0.9) * np.sin(ang),
                ]
            )
            rib = _boolean(rib, s, "union")
        stem = _boolean(stem, rib, "union")

    # Soft fillet into body
    blend = icosphere(subdivisions=3, radius=1.3)
    for ang in np.linspace(0, 2 * np.pi, 28, endpoint=False):
        s = blend.copy()
        s.apply_translation(
            [rx - 0.15, STEM_R * 1.05 * np.cos(ang), STEM_R * 1.05 * np.sin(ang)]
        )
        stem = _boolean(stem, s, "union")

    return stem


def measure_stem_od(mesh: trimesh.Trimesh, rx: float) -> float | None:
    """Section the mid-shaft (between ribs) and return outer diameter."""
    x = rx + RIB_START + RIB_SPACING * 0.5
    sec = mesh.section(plane_origin=[x, 0, 0], plane_normal=[1, 0, 0])
    if sec is None:
        return None
    planar, _ = sec.to_2D()
    if not planar.polygons_full:
        return None
    # outermost polygon
    poly = max(planar.polygons_full, key=lambda p: abs(p.area))
    minx, miny, maxx, maxy = poly.bounds
    return float(max(maxx - minx, maxy - miny))


def assemble(rx: float, ry: float, rz: float) -> trimesh.Trimesh:
    body = make_body(rx, ry, rz)
    stem = make_stem(rx)
    solid = _boolean(body, stem, "union")
    solid = _boolean(solid, make_intake_cutter(rx), "difference")
    solid = _boolean(solid, make_bore(rx), "difference")
    solid = _boolean(solid, make_side_flush_ports(rx, ry, rz), "difference")

    comps = solid.split(only_watertight=False)
    if len(comps) > 1:
        solid = max(comps, key=lambda m: abs(m.volume))
    return solid


def tune_body_to_volume(
    target: float = TARGET_VOLUME_MM3,
    tol: float = 25.0,
    max_iter: int = 8,
) -> tuple[trimesh.Trimesh, dict]:
    """
    Adjust body Y/Z scale only so stem OD stays exactly 4.5 mm.
    X (length) stays fixed so stem geometry remains in absolute mm.
    """
    rx, ry, rz = BODY_RX, BODY_RY, BODY_RZ
    history = []
    mesh = assemble(rx, ry, rz)

    for i in range(max_iter):
        vol = float(mesh.volume)
        history.append({"iter": i, "ry": ry, "rz": rz, "volume_mm3": vol})
        err = target - vol
        if abs(err) <= tol:
            break
        # V ∝ ry * rz roughly for similar shapes; scale both equally
        factor = (target / vol) ** 0.5
        # damp to avoid overshoot
        factor = 1.0 + (factor - 1.0) * 0.85
        ry *= factor
        rz *= factor
        mesh = assemble(rx, ry, rz)

    trimesh.repair.fix_normals(mesh)
    mesh.process(validate=True)

    stem_od = measure_stem_od(mesh, rx)
    meta = {
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
        "stem_od_measured_mm": stem_od,
        "rib_od_mm": RIB_OD,
        "stem_length_mm": STEM_LEN,
        "bore_d_mm": BORE_D,
        "sg": SG,
        "tune_history": history,
        "design": {
            "name": "Dewdrop straw weight",
            "name_ko": "이슬방울 추빨대 추",
            "material": "100% silicone",
            "features": [
                "soft dewdrop body",
                "open front intake",
                "cross flush ports",
                "through bore",
                "4.5mm OD hose stem with tapered tip",
                "dual retention ribs OD 5.4mm",
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

    fig = plt.figure(figsize=(12.5, 4.2), facecolor="#f3f6f4")
    tris = preview.triangles
    configs = [
        ("Perspective", 18, -55),
        ("Side", 8, -90),
        ("Top", 90, -90),
    ]
    for i, (title, elev, azim) in enumerate(configs, 1):
        ax = fig.add_subplot(1, 3, i, projection="3d")
        coll = Poly3DCollection(
            tris,
            alpha=0.96,
            facecolor="#6fb3a4",
            edgecolor="#2c5c52",
            linewidths=0.04,
        )
        ax.add_collection3d(coll)
        b = preview.bounds
        ax.set_xlim(b[0, 0], b[1, 0])
        ax.set_ylim(b[0, 1], b[1, 1])
        ax.set_zlim(b[0, 2], b[1, 2])
        ax.set_title(title, fontsize=11, color="#1e3330")
        ax.set_facecolor("#f3f6f4")
        ax.view_init(elev=elev, azim=azim)
        try:
            ax.set_aspect("equal")
        except Exception:
            pass
        ax.tick_params(labelsize=6)
        ax.set_xlabel("X mm", fontsize=7)
        ax.set_ylabel("Y mm", fontsize=7)
        ax.set_zlabel("Z mm", fontsize=7)
    fig.suptitle(
        "LV-2602 silicone straw weight — 9 g @ SG 1.8",
        fontsize=13,
        color="#18302d",
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)


def main() -> None:
    STL_DIR.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    mesh, meta = tune_body_to_volume()

    stl_path = STL_DIR / "LV-2602-straw-weight-9g.stl"
    mesh.export(stl_path)
    mesh.export(STL_DIR / "LV-2602-straw-weight-9g-v1.stl")

    preview_path = RENDER_DIR / "preview_3view.png"
    try:
        export_preview(mesh, preview_path)
        meta["preview"] = str(preview_path.relative_to(ROOT))
    except Exception as e:
        meta["preview_error"] = str(e)

    meta_path = DOCS_DIR / "design_metrics.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(json.dumps({k: v for k, v in meta.items() if k != "tune_history"}, indent=2))
    print("tune_history:", json.dumps(meta["tune_history"], indent=2))
    print(f"Wrote {stl_path}")


if __name__ == "__main__":
    main()
