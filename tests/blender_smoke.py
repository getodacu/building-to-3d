"""Background-only integration fixture. Blender --python this_file -- create|verify OUTPUT."""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

if not bpy.app.background:
    raise RuntimeError('This disposable fixture must run in background Blender, never the live scene.')
mode, directory = sys.argv[sys.argv.index('--') + 1:]
ROOT = Path(directory).resolve()


def signature():
    result = {}
    for ob in bpy.data.collections['Synthetic pavilion'].objects:
        mesh = ob.data
        result[ob.name] = {
            'vertices': [list(v.co) for v in mesh.vertices],
            'faces': [list(p.vertices) for p in mesh.polygons],
            'matrix': [list(row) for row in ob.matrix_world],
            'materials': [m.name for m in mesh.materials],
            'uv': [[list(item.uv) for item in layer.data] for layer in mesh.uv_layers],
        }
    return result


def counts():
    return {name: len(getattr(bpy.data, name)) for name in ('objects', 'meshes', 'materials', 'images')}


def build():
    collection = bpy.data.collections.get('Synthetic pavilion')
    if collection:
        for ob in list(collection.objects):
            mesh = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
    else:
        collection = bpy.data.collections.new('Synthetic pavilion')
        bpy.context.scene.collection.children.link(collection)
    image = bpy.data.images.get('Fixture masonry')
    if not image:
        image = bpy.data.images.new('Fixture masonry', width=32, height=32)
        pixels = []
        for y in range(32):
            for x in range(32):
                shade = .62 + .035 * math.sin(x * 2.1 + y * 1.7)
                pixels.extend((shade, shade * .94, shade * .84, 1))
        image.pixels = pixels
        image.filepath_raw = str(ROOT / 'textures/stone.png')
        image.file_format = 'PNG'
        image.save()
        image.pack()
    material = bpy.data.materials.get('Fixture stone') or bpy.data.materials.new('Fixture stone')
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    principled = nodes.new('ShaderNodeBsdfPrincipled')
    texture = nodes.new('ShaderNodeTexImage')
    texture.image = image
    principled.inputs['Roughness'].default_value = .8
    material.node_tree.links.new(texture.outputs['Color'], principled.inputs['Base Color'])
    material.node_tree.links.new(principled.outputs['BSDF'], output.inputs['Surface'])
    meshes = [
        ('Pavilion body', [(-3,-2,0),(3,-2,0),(3,2,0),(-3,2,0),(-3,-2,3),(3,-2,3),(3,2,3),(-3,2,3)], [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]),
        ('Gabled roof', [(-3.3,-2.3,3),(3.3,-2.3,3),(3.3,2.3,3),(-3.3,2.3,3),(-3.3,0,4.4),(3.3,0,4.4)], [(0,3,2,1),(0,1,5,4),(4,5,2,3),(0,4,3),(1,2,5)])
    ]
    for name, verts, faces in meshes:
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        uv = mesh.uv_layers.new(name='Metres')
        for face in mesh.polygons:
            for li in face.loop_indices:
                co = mesh.vertices[mesh.loops[li].vertex_index].co
                uv.data[li].uv = (co.x, co.y if abs(face.normal.z) > .5 else co.z)
        ob = bpy.data.objects.new(name, mesh)
        collection.objects.link(ob)
        mesh.materials.append(material)
    bpy.context.view_layer.update()


if mode == 'create':
    ROOT.mkdir(parents=True, exist_ok=False)
    for name in ('models', 'textures', 'renders', 'proof'):
        (ROOT / name).mkdir()
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    build()
    camera = bpy.data.objects.new('Fixture camera', bpy.data.cameras.new('Fixture camera'))
    scene.collection.objects.link(camera)
    camera.location = (10,-13,10)
    camera.rotation_euler = (Vector((0,0,1.8)) - camera.location).to_track_quat('-Z','Y').to_euler()
    scene.camera = camera
    light = bpy.data.objects.new('Fixture light', bpy.data.lights.new('Fixture light', 'AREA'))
    scene.collection.objects.link(light)
    light.location = (2,-5,10)
    light.rotation_euler = (Vector((0,0,1)) - light.location).to_track_quat('-Z','Y').to_euler()
    light.data.energy = 1800
    light.data.shape = 'DISK'
    light.data.size = 7
    scene.world.color = (.3,.3,.3)
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 12
    scene.render.resolution_x = 960
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(ROOT / 'renders/pavilion.png')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'models/pavilion.blend'))
    for ob in scene.objects:
        ob.select_set(ob.type == 'MESH')
    bpy.ops.export_scene.gltf(filepath=str(ROOT / 'models/pavilion.glb'), export_format='GLB', use_selection=True)
    bpy.ops.render.render(write_still=True)
    (ROOT / 'proof/baseline.json').write_text(json.dumps(signature(), sort_keys=True))
    print('FIXTURE_CREATED', json.dumps(counts()))
elif mode == 'verify':
    baseline = json.loads((ROOT / 'proof/baseline.json').read_text())
    assert signature() == baseline, 'Reopened geometry/transforms/UVs/materials differ'
    assert bpy.data.images['Fixture masonry'].packed_file, 'Missing packed texture'
    before = counts()
    build()
    assert signature() == baseline, 'Clean rebuild differs'
    assert counts() == before, 'Rebuild accumulated data'
    build()
    assert signature() == baseline and counts() == before, 'Repeated rebuild differs'
    proof = {'reopened_blend': True, 'packed_textures': True, 'rebuild_consistency': True, 'no_duplicate_data': True, 'counts': counts()}
    (ROOT / 'proof/reopen.json').write_text(json.dumps(proof, indent=2))
    print('FIXTURE_REOPEN_VERIFIED', json.dumps(proof))
else:
    raise ValueError('Expected create or verify')
