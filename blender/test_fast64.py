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

    mesh2 = bpy.data.meshes.new("DecimTest")
    dec_obj = bpy.data.objects.new("DecimTest", mesh2)
    bpy.context.scene.collection.objects.link(dec_obj)
    bpy.context.view_layer.objects.active = dec_obj

    bm = bmesh.new()
    # Build 6 disconnected quads (like per-material BSP faces) facing different directions
    offsets = [(0,0,0),(5,0,0),(10,0,0),(0,5,0),(0,10,0),(0,0,5)]
    for ox, oy, oz in offsets:
        v0 = bm.verts.new((ox+0, oy+0, oz+0))
        v1 = bm.verts.new((ox+1, oy+0, oz+0))
        v2 = bm.verts.new((ox+1, oy+1, oz+0))
        v3 = bm.verts.new((ox+0, oy+1, oz+0))
        bm.faces.new((v0, v1, v2, v3))
    bm.to_mesh(mesh2)
    bm.free()
    mesh2.update()

    before = len(dec_obj.data.polygons)
    normals_before = [tuple(round(x,3) for x in p.normal) for p in dec_obj.data.polygons]

    # Pass 1: DISSOLVE
    mod_d = dec_obj.modifiers.new(name="Dissolve", type="DECIMATE")
    mod_d.decimate_type = "DISSOLVE"
    mod_d.angle_limit = math.radians(1.0)
    bpy.ops.object.modifier_apply(modifier=mod_d.name)
    after_dissolve = len(dec_obj.data.polygons)

    # Pass 2: COLLAPSE
    target = max(1, int(before * 0.1))
    after = after_dissolve
    if after_dissolve > target:
        effective_ratio = max(0.1, 1.0 / after_dissolve)
        mod_c = dec_obj.modifiers.new(name="Decimate", type="DECIMATE")
        mod_c.ratio = effective_ratio
        bpy.ops.object.modifier_apply(modifier=mod_c.name)
        after = len(dec_obj.data.polygons)

    normals_after = [tuple(round(x,3) for x in p.normal) for p in dec_obj.data.polygons]

    print(f"  Disconnected quads: before={before} dissolve={after_dissolve} collapse={after}")
    assert after >= 1, f"All faces removed! Expected >= 1, got {after}"
    for n in normals_after:
        assert n[2] > 0.9, f"Normal {n} not pointing up (+Z) — winding flipped!"
    print("  Face count OK, normals preserved")

    # Test a connected manifold mesh (solid box)
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
