#!/usr/bin/env python3
"""
LV-2602 baby bottle straw weight (추빨대 추)

Design goals (rev2 — keep original silhouette)
---------------------------------------------
- Keep the original flat oval / capsule weight shape (not a round dewdrop)
- Bottom intake holes so milk/formula enters when the weight settles down
- Ultra-smooth crowned exterior → low friction vs plastic bottle wall/floor
- Very simple Ø4.5 mm hose stem (easy to clean; no multi-rib trap)
- 100% silicone, SG 1.8 → target mass 9 g (volume 5000 mm³)
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
TARGET_VOLUME_MM3 = TARGET_MASS_G / SG * 1000.0  # 5000

# Original ref ≈ 35.4 × 18.6 × 8.8 mm @ ~2.93 cm³.
# Linear scale ~1.2 keeps the same proportions while approaching 5 cm³,
# then Y/Z are fine-tuned so stem OD stays exactly 4.5 mm.
BODY_RX = 17.5  # half-length along straw axis (X)
BODY_RY = 10.5  # half-width
BODY_RZ = 5.2  # half-thickness (flat profile — low bottle friction)

# Bottom intakes (on -Z face) — milk entry when weight sits at bottle bottom
INTAKE_R = 1.8  # Ø3.6 mm — brushable / flushable
INTAKE_DEPTH = 6.0
INTAKE_XY = [(-6.0, 0.0), (0.0, 3.2), (0.0, -3.2)]  # front + two sides on bottom

BORE_D = 2.2
BORE_R = BORE_D / 2.0

# Simple hose stem — cleanability first (no multi-rib dirt traps)
STEM_OD = 4.5
STEM_R = STEM_OD / 2.0
STEM_LEN = 9.0
STEM_LEAD_LEN = 2.0
STEM_LEAD_TIP_R = 2.05  # soft start into silicone hose (~Ø4.1)
# Retention = hose stretch over Ø4.5 + insertion length (no protruding beads)

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
    """
    Flat oval capsule matching the original weight silhouette.

    Slight crown on top/bottom (rz bias via secondary spheres) so contact
    against the plastic bottle is a small patch → lower sliding friction.
    """
    # Main flat ellipsoid — same family as original 35×18.6×8.8
    main = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    main.apply_scale([rx, ry, rz])

    # Soft nose (front = -X) so it tumbles/slides without catching
    nose = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    nose.apply_scale([rx * 0.38, ry * 0.78, rz * 0.92])
    nose = _translate(nose, [-rx * 0.62, 0.0, 0.0])

    # Mild top/bottom crown (reduces face drag on bottle floor)
    crown_t = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    crown_t.apply_scale([rx * 0.72, ry * 0.72, rz * 0.55])
    crown_t = _translate(crown_t, [-rx * 0.05, 0.0, rz * 0.28])

    crown_b = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    crown_b.apply_scale([rx * 0.72, ry * 0.72, rz * 0.55])
    crown_b = _translate(crown_b, [-rx * 0.05, 0.0, -rz * 0.28])

    # Tail blend into stem (rear = +X) — keep outer curve continuous
    tail = icosphere(subdivisions=MESH_SUBDIV, radius=1.0)
    tail.apply_scale([rx * 0.32, ry * 0.55, rz * 0.85])
    tail = _translate(tail, [rx * 0.55, 0.0, 0.0])

    body = _boolean(main, nose, "union")
    body = _boolean(body, crown_t, "union")
    body = _boolean(body, crown_b, "union")
    body = _boolean(body, tail, "union")
    return body


def make_bottom_intakes(rx: float, rz: float) -> trimesh.Trimesh:
    """
    Holes on the bottom (-Z) face → milk enters when weight is at bottle bottom.
    Vertical cylinders open the underside and meet the axial bore.
    """
    cutters = []
    for x, y in INTAKE_XY:
        c = cylinder(radius=INTAKE_R, height=INTAKE_DEPTH + rz * 1.2, sections=48)
        # cylinder along Z by default; place so it opens the bottom face
        z_center = -rz + INTAKE_DEPTH * 0.35
        cutters.append(_translate(c, [x, y, z_center]))

    u = cutters[0]
    for c in cutters[1:]:
        u = _boolean(u, c, "union")
    return u


def make_bore(rx: float) -> trimesh.Trimesh:
    """Axial bore from intakes through body and out the stem tip."""
    x_start = -rx - 2.0
    x_end = rx + STEM_LEN + 3.0
    length = x_end - x_start
    bore = cylinder(radius=BORE_R, height=length, sections=64)
    bore.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    return _translate(bore, [(x_start + x_end) / 2.0, 0.0, 0.0])


def make_cross_link() -> trimesh.Trimesh:
    """Short Y-link so the three bottom holes share one flushable cavity."""
    link = cylinder(radius=1.5, height=8.5, sections=48)
    link.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])
    )
    return _translate(link, [-1.0, 0.0, -1.5])


def make_stem(rx: float) -> trimesh.Trimesh:
    """
    Minimal Ø4.5 mm stem for easy cleaning:
    - straight shaft (no ribs / beads to trap milk)
    - soft tapered tip for easy hose insertion
    - small smooth fillet into body only
    Retention comes from silicone hose stretch over Ø4.5 + 9 mm engagement.
    """
    shaft = cylinder(radius=STEM_R, height=STEM_LEN, sections=64)
    shaft.apply_transform(
        trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0])
    )
    shaft = _translate(shaft, [rx + STEM_LEN / 2.0, 0.0, 0.0])

    # Lead-in taper
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

    # Tiny smooth fillet into body (no sharp dirt step; still low profile)
    blend = icosphere(subdivisions=3, radius=0.85)
    for ang in np.linspace(0, 2 * np.pi, 20, endpoint=False):
        s = blend.copy()
        s.apply_translation(
            [rx - 0.05, STEM_R * 0.95 * np.cos(ang), STEM_R * 0.95 * np.sin(ang)]
        )
        stem = _boolean(stem, s, "union")

    return stem


def measure_stem_od(mesh: trimesh.Trimesh, rx: float) -> float | None:
    x = rx + STEM_LEN * 0.72  # past bead, on plain shaft
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
    body = make_body(rx, ry, rz)
    stem = make_stem(rx)
    solid = _boolean(body, stem, "union")
    solid = _boolean(solid, make_bottom_intakes(rx, rz), "difference")
    solid = _boolean(solid, make_cross_link(), "difference")
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
    """Tune body Y/Z only — keeps stem OD at absolute 4.5 mm."""
    rx, ry, rz = BODY_RX, BODY_RY, BODY_RZ
    history = []
    mesh = assemble(rx, ry, rz)

    for i in range(max_iter):
        vol = float(mesh.volume)
        history.append({"iter": i, "ry": ry, "rz": rz, "volume_mm3": vol})
        err = target - vol
        if abs(err) <= tol:
            break
        # Prefer growing width/thickness together; keep flat ratio (rz/ry)
        flat_ratio = rz / ry
        factor = (target / vol) ** 0.5
        factor = 1.0 + (factor - 1.0) * 0.8
        ry *= factor
        rz = ry * flat_ratio
        # Cap thickness so it stays "flat weight" like original (~≤12 mm full)
        if rz > 6.2:
            rz = 6.2
            ry = (ry * (target / float(assemble(rx, ry, rz).volume)) ** 0.5)
        mesh = assemble(rx, ry, rz)

    trimesh.repair.fix_normals(mesh)
    mesh.process(validate=True)

    stem_od = measure_stem_od(mesh, rx)
    meta = {
        "revision": 2,
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
        "stem_length_mm": STEM_LEN,
        "bore_d_mm": BORE_D,
        "intake_d_mm": INTAKE_R * 2,
        "intake_count": len(INTAKE_XY),
        "sg": SG,
        "tune_history": history,
        "design": {
            "name": "Flat oval straw weight (original silhouette)",
            "name_ko": "납작 타원 추빨대 추 (원형 실루엣 유지)",
            "material": "100% silicone",
            "features": [
                "flat oval body close to original LV-2602 proportions",
                "crowned faces for low friction vs plastic bottle",
                "3 bottom intake holes for drinking when weight settles",
                "through bore + cross link for easy flush cleaning",
                "plain Ø4.5 mm stem + taper only (no ribs)",
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

    fig = plt.figure(figsize=(12.5, 4.2), facecolor="#f2f5f6")
    tris = preview.triangles
    configs = [
        ("Perspective", 22, -55),
        ("Side (shows flat profile)", 8, -90),
        ("Bottom (intake holes)", -75, -90),
    ]
    for i, (title, elev, azim) in enumerate(configs, 1):
        ax = fig.add_subplot(1, 3, i, projection="3d")
        coll = Poly3DCollection(
            tris,
            alpha=0.96,
            facecolor="#6aa8b8",
            edgecolor="#2a4f59",
            linewidths=0.035,
        )
        ax.add_collection3d(coll)
        b = preview.bounds
        ax.set_xlim(b[0, 0], b[1, 0])
        ax.set_ylim(b[0, 1], b[1, 1])
        ax.set_zlim(b[0, 2], b[1, 2])
        ax.set_title(title, fontsize=10, color="#1e3330")
        ax.set_facecolor("#f2f5f6")
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
        "LV-2602 rev2 — flat oval · bottom intakes · low-friction · plain Ø4.5 stem",
        fontsize=12,
        color="#18302d",
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
    fig = plt.figure(figsize=(8, 5.5), facecolor="#eef3f4")
    ax = fig.add_subplot(111, projection="3d")
    coll = Poly3DCollection(
        preview.triangles,
        alpha=0.97,
        facecolor="#5b9eae",
        edgecolor="#1f4550",
        linewidths=0.03,
    )
    ax.add_collection3d(coll)
    b = preview.bounds
    ax.set_xlim(b[0, 0], b[1, 0])
    ax.set_ylim(b[0, 1], b[1, 1])
    ax.set_zlim(b[0, 2], b[1, 2])
    ax.view_init(elev=25, azim=-58)
    try:
        ax.set_aspect("equal")
    except Exception:
        pass
    ax.set_facecolor("#eef3f4")
    ax.set_title(
        "LV-2602 flat oval straw weight\n"
        "9g @ SG1.8 · bottom holes · low bottle friction · simple stem",
        fontsize=11,
    )
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

    preview_path = RENDER_DIR / "preview_3view.png"
    hero_path = RENDER_DIR / "hero.png"
    try:
        export_preview(mesh, preview_path)
        export_hero(mesh, hero_path)
        meta["preview"] = str(preview_path.relative_to(ROOT))
        meta["hero"] = str(hero_path.relative_to(ROOT))
    except Exception as e:
        meta["preview_error"] = str(e)

    (DOCS_DIR / "design_metrics.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )

    print(json.dumps({k: v for k, v in meta.items() if k != "tune_history"}, indent=2))
    print("tune_history:", json.dumps(meta["tune_history"], indent=2))
    print(f"Wrote {stl_path}")


if __name__ == "__main__":
    main()
