import bpy
import sys

print("=== Blender version:", bpy.app.version_string)
print("=== Python version:", sys.version)

print("=== Testing fast64 availability...")
try:
    import fast64
    print("fast64 imported OK, module:", fast64)
except Exception as e:
    print("fast64 import FAILED:", e)

print("=== Testing sm64_obj_type on Object...")
try:
    obj = bpy.data.objects.new("TestObj", None)
    bpy.context.scene.collection.objects.link(obj)
    val = obj.sm64_obj_type
    print("sm64_obj_type =", val)
except Exception as e:
    print("sm64_obj_type access FAILED:", e)

print("=== Testing createF3DMat...")
try:
    from fast64.fast64_internal.f3d.f3d_material import createF3DMat
    print("createF3DMat imported OK")
    mesh = bpy.data.meshes.new("TestMesh")
    mesh_obj = bpy.data.objects.new("TestMesh", mesh)
    bpy.context.scene.collection.objects.link(mesh_obj)
    mat = createF3DMat(mesh_obj, "Shaded Solid")
    print("createF3DMat returned:", mat)
except Exception as e:
    print("createF3DMat FAILED:", e)

print("=== Testing scene.fast64.sm64 properties...")
try:
    scene = bpy.context.scene
    sm64 = scene.fast64.sm64
    sm64.export_type = "C"
    ce = sm64.combined_export
    ce.non_decomp_level = True
    print("non_decomp_level =", ce.non_decomp_level)
    print("sm64 props OK")
except Exception as e:
    print("sm64 props FAILED:", e)

print("=== Testing decimation on non-manifold BSP-like mesh...")
try:
    import math
    import bmesh

    # Helper: count boundary (open) edges — a hole-free mesh has 0 on a closed surface,
    # or only perimeter edges on a flat surface (shared count=1). Check no edge has count=0.
    def count_boundary_edges(obj):
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        boundary = sum(1 for e in bm.edges if len(e.link_faces) < 2)
        bm.free()
        return boundary

    # BSP-like non-manifold mesh: 4x4 grid of CONNECTED coplanar quads but emitted as
    # fully independent quads (no shared vertices), exactly like bsp2obj output
    mesh2 = bpy.data.meshes.new("DecimTest")
    dec_obj = bpy.data.objects.new("DecimTest", mesh2)
    bpy.context.scene.collection.objects.link(dec_obj)
    bpy.context.view_layer.objects.active = dec_obj

    bm = bmesh.new()
    # 4x4 grid of independent unit quads (co-located edges, but NO shared vertices — like bsp2obj)
    for row in range(4):
        for col in range(4):
            ox, oy = float(col), float(row)
            v0 = bm.verts.new((ox,   oy,   0))
            v1 = bm.verts.new((ox+1, oy,   0))
            v2 = bm.verts.new((ox+1, oy+1, 0))
            v3 = bm.verts.new((ox,   oy+1, 0))
            bm.faces.new((v0, v1, v2, v3))
    bm.to_mesh(mesh2)
    bm.free()
    mesh2.update()

    before = len(dec_obj.data.polygons)
    boundary_before = count_boundary_edges(dec_obj)
    print(f"  BSP-like grid: before={before} polys, boundary_edges_before={boundary_before}")

    _bm = bmesh.new()
    _bm.from_mesh(dec_obj.data)
    bmesh.ops.remove_doubles(_bm, verts=_bm.verts, dist=0.01)
    _bm.to_mesh(dec_obj.data)
    _bm.free()
    dec_obj.data.update()
    after_merge = len(dec_obj.data.polygons)
    boundary_merged = count_boundary_edges(dec_obj)
    print(f"  After merge_by_distance: polys={after_merge}, boundary_edges={boundary_merged}")

    mod_d = dec_obj.modifiers.new(name="Dissolve", type="DECIMATE")
    mod_d.decimate_type = "DISSOLVE"
    mod_d.angle_limit = math.radians(1.0)
    bpy.ops.object.modifier_apply(modifier=mod_d.name)
    after_dissolve = len(dec_obj.data.polygons)
    boundary_dissolve = count_boundary_edges(dec_obj)
    print(f"  After dissolve: polys={after_dissolve}, boundary_edges={boundary_dissolve}")

    target = max(1, int(before * 0.1))
    after = after_dissolve
    if after_dissolve > target:
        effective_ratio = max(0.1, 1.0 / after_dissolve)
        mod_c = dec_obj.modifiers.new(name="Decimate", type="DECIMATE")
        mod_c.ratio = effective_ratio
        bpy.ops.object.modifier_apply(modifier=mod_c.name)
        after = len(dec_obj.data.polygons)

    boundary_after = count_boundary_edges(dec_obj)
    print(f"  After collapse: polys={after}, boundary_edges={boundary_after}")

    assert after >= 1, f"All faces removed! Expected >= 1, got {after}"
    assert boundary_after == boundary_dissolve, (
        f"Collapse INTRODUCED holes: boundary edges {boundary_dissolve} -> {boundary_after}"
    )
    print("  No holes introduced by collapse — OK")

    # Reconnected manifold mesh (solid box)
    mesh3 = bpy.data.meshes.new("DecimManifold")
    mobj = bpy.data.objects.new("DecimManifold", mesh3)
    bpy.context.scene.collection.objects.link(mobj)
    bpy.context.view_layer.objects.active = mobj
    bm2 = bmesh.new()
    bmesh.ops.create_uvsphere(bm2, u_segments=16, v_segments=8, radius=1)
    bm2.to_mesh(mesh3)
    bm2.free()
    mesh3.update()

    before2 = len(mobj.data.polygons)
    _bm2 = bmesh.new()
    _bm2.from_mesh(mobj.data)
    bmesh.ops.remove_doubles(_bm2, verts=_bm2.verts, dist=0.01)
    _bm2.to_mesh(mobj.data)
    _bm2.free()
    mobj.data.update()
    mod_d2 = mobj.modifiers.new(name="Dissolve", type="DECIMATE")
    mod_d2.decimate_type = "DISSOLVE"
    mod_d2.angle_limit = math.radians(1.0)
    bpy.ops.object.modifier_apply(modifier=mod_d2.name)
    after_d2 = len(mobj.data.polygons)
    target2 = max(1, int(before2 * 0.1))
    after2 = after_d2
    if after_d2 > target2:
        eff2 = max(0.1, 1.0 / after_d2)
        mod_c2 = mobj.modifiers.new(name="Decimate", type="DECIMATE")
        mod_c2.ratio = eff2
        bpy.ops.object.modifier_apply(modifier=mod_c2.name)
        after2 = len(mobj.data.polygons)

    print(f"  Sphere (manifold): before={before2} dissolve={after_d2} collapse={after2} target={target2}")
    assert after2 >= 1, f"All sphere faces removed! Got {after2}"
    print("  Manifold decimation OK")

    print("=== Decimation tests PASSED")
except AssertionError as e:
    print(f"=== Decimation test FAILED: {e}")
    sys.exit(1)
except Exception as e:
    print(f"=== Decimation test ERROR: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

print("=== Test complete")
sys.exit(0)
