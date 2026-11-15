"""Студийное окружение для веба — 1:1 со студией постера.

Рендерит равнопромежуточную (equirectangular) HDR-карту из той же схемы света,
что build.py: те же четыре area-лампы, тот же мир, та же точка съёма.
Поэтому металл в браузере видит ровно те отражения, что и в постере.

Запуск:
  "C:\\Program Files\\Blender Foundation\\Blender 5.3\\blender.exe" -b --factory-startup -P tools/blender/env.py
"""

import os
import bpy
import math
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(bpy.data.filepath or __file__))
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "public", "hdr", "studio.hdr")


def srgb(hex_str):
    h = hex_str.lstrip('#')
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.samples = 96
    sc.cycles.use_denoising = False
    sc.render.resolution_x = 1536
    sc.render.resolution_y = 768
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    # Raw, а не AgX: тонмаппинг сделает three.js на своей стороне.
    sc.view_settings.view_transform = 'Raw'
    sc.view_settings.look = 'None'
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = 'HDR'
    sc.render.image_settings.color_depth = '32'


def aim(ob, target):
    d = Vector(target) - Vector(ob.location)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def area_light(name, loc, target, size, power, color=(1.0, 0.94, 0.86)):
    """Плоскость-эмиттер вместо AREA-лампы.

    Area-лампы Blender в панорамном рендере камерой не видны (проверено: max
    карты 0.03), а свечение площадки видно всегда. Радианс считаем по той же
    формуле: L = power / (площадь * pi) — тогда отражение совпадает с постером.
    """
    area = size[0] * size[1]
    strength = power / (area * math.pi)
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=loc)
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0], size[1], 1.0)
    aim(ob, target)

    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    em = nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (color[0], color[1], color[2], 1.0)
    em.inputs["Strength"].default_value = strength
    mat.node_tree.links.new(em.outputs["Emission"], out.inputs["Surface"])
    ob.data.materials.append(mat)
    return ob

def world_gradient():
    """Мир постера: та же рампа и та же сила, иначе фон отражается иначе."""
    w = bpy.data.worlds.new('W_Dark')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs[1].default_value = 0.95
    ramp = nodes.new("ShaderNodeValToRGB")
    tc = nodes.new("ShaderNodeTexCoord")
    sep = nodes.new("ShaderNodeSeparateXYZ")

    el = ramp.color_ramp.elements
    el[0].position = 0.0
    el[0].color = (*srgb('#141110'), 1.0)
    el[1].position = 0.40
    el[1].color = (*srgb('#4A4033'), 1.0)
    e2 = el.new(0.55)
    e2.color = (*srgb('#8A7A62'), 1.0)
    e3 = el.new(0.90)
    e3.color = (*srgb('#3A322A'), 1.0)

    links.new(tc.outputs['Generated'], sep.inputs[0])
    links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bg.inputs['Color'])
    links.new(bg.outputs['Background'], out.inputs['Surface'])


def main():
    reset()
    world_gradient()

    # Дословно из build.py (строки 995–998): положение, цель, размер, мощность, цвет.
    area_light('Key', (-1.05, -1.25, 1.28), (0.0, -0.02, 0.24), (2.20, 1.60), 110)
    area_light('Fill', (1.25, -0.95, 0.52), (0.0, 0.0, 0.18), (1.40, 1.05), 45, (0.95, 0.92, 0.90))
    area_light('Rim', (0.30, 1.30, 1.00), (0.0, 0.0, 0.22), (1.00, 0.70), 70, (1.0, 0.88, 0.74))
    area_light('Cavity', (0.16, -0.13, 0.122), (0.0, -0.15, 0.05), (0.16, 0.09), 3.5, (1.0, 0.88, 0.72))

    # Точка съёма — центр модели, как смотрит камера постера.
    cam_data = bpy.data.cameras.new("Pano")
    cam_data.type = 'PANO'
    cam_data.panorama_type = 'EQUIRECTANGULAR'
    cam = bpy.data.objects.new("Pano", cam_data)
    bpy.context.scene.collection.objects.link(cam)
    cam.location = (0.0, 0.0, 0.195)
    bpy.context.scene.camera = cam

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    bpy.context.scene.render.filepath = OUT
    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(OUT)
    px = list(img.pixels[:])
    step = 4 * 997
    total = 0.0
    count = 0
    for i in range(0, len(px) - 3, step):
        total += 0.2126 * px[i] + 0.7152 * px[i + 1] + 0.0722 * px[i + 2]
        count += 1
    print("HDR_MEAN_LUMA %.4f" % (total / max(1, count)))
    print("HDR " + OUT)
    print("ENV_OK")


main()
