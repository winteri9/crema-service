# -*- coding: utf-8 -*-
"""CREMA — процедурная кофемашина для сайта.

Запуск:
  blender -b -P tools/blender/build.py -- --stage 3

Стадии:
  1  корпус: цоколь, рама, щёки, панель, площадка
  2  + лицо: дисплей, кнопки, клавиши, группа, рожок, кран, поддон, бак, бункер
  3  + нутро: заварочный блок, бойлер, помпа, кофемолка, шланги
  4  разборка (explode) — рендер разнесённой машины
  5  постер 1200x1200 (Cycles) + экспорт public/model/machine.glb

Габарит: W 0.210 x D 0.390 x H 0.390 м, низ на z=0, фронт в -Y.
"""

import bpy
import bmesh
import math
import os
import sys
import json
import random
from mathutils import Vector, Euler, Matrix

# ---------------------------------------------------------------- CLI / пути

ARGV = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def argv_num(name, default):
    if name in ARGV:
        i = ARGV.index(name)
        if i + 1 < len(ARGV):
            try:
                return int(ARGV[i + 1])
            except ValueError:
                pass
    return default


STAGE = argv_num('--stage', 5)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PICS = os.path.join(ROOT, 'pics')
GLB = os.path.join(ROOT, 'public', 'model', 'machine.glb')
STILL = os.path.join(ROOT, 'public', 'img', 'model-still.png')
BLEND = os.path.join(HERE, 'machine.blend')

for _p in (PICS, os.path.dirname(GLB), os.path.dirname(STILL)):
    os.makedirs(_p, exist_ok=True)

# ---------------------------------------------------------------- размеры

W = 0.210          # ширина
D = 0.390          # глубина
H = 0.390          # высота корпуса
X1 = W / 2.0       # 0.105
X2 = -X1
YF = -D / 2.0      # -0.195 фронт
YB = D / 2.0       # 0.195 тыл
Z0 = 0.022         # низ корпуса (на цоколе)
ZTOP = 0.384       # верх корпуса

FRONT = YF

C = bpy.context
SC = C.scene
ROOTS = {}
STUDIO = []


# ---------------------------------------------------------------- утилиты


def srgb(hex_str):
    h = hex_str.lstrip('#')
    out = []
    for i in (0, 2, 4):
        c = int(h[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return out


def link(ob):
    SC.collection.objects.link(ob)
    return ob


def mat_make(name, color, metallic=0.0, rough=0.5, alpha=1.0,
             emis=None, emis_str=0.0, coat=0.0, coat_rough=0.08,
             transmission=0.0, ior=1.5, rough_var=None):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    b.inputs['Base Color'].default_value = (*srgb(color), 1.0)
    b.inputs['Metallic'].default_value = metallic
    b.inputs['Roughness'].default_value = rough
    b.inputs['IOR'].default_value = ior
    b.inputs['Alpha'].default_value = alpha
    if coat:
        b.inputs['Coat Weight'].default_value = coat
        b.inputs['Coat Roughness'].default_value = coat_rough
    if transmission:
        b.inputs['Transmission Weight'].default_value = transmission
    if emis:
        b.inputs['Emission Color'].default_value = (*srgb(emis), 1.0)
        b.inputs['Emission Strength'].default_value = emis_str
    if alpha < 1.0:
        m.blend_method = 'BLEND'
        m.use_backface_culling = False
    m.roughness = rough
    m.metallic = metallic
    if rough_var:
        # металл без шума в шероховатости выглядит пластиковым
        lo, hi, scale = rough_var
        nt = m.node_tree
        tex = nt.nodes.new('ShaderNodeTexCoord')
        noi = nt.nodes.new('ShaderNodeTexNoise')
        noi.inputs['Scale'].default_value = scale
        noi.inputs['Detail'].default_value = 3.0
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0.32
        ramp.color_ramp.elements[0].color = (lo, lo, lo, 1.0)
        ramp.color_ramp.elements[1].position = 0.68
        ramp.color_ramp.elements[1].color = (hi, hi, hi, 1.0)
        nt.links.new(tex.outputs['Generated'], noi.inputs['Vector'])
        nt.links.new(noi.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], b.inputs['Roughness'])
    return m


M = {}


def materials():
    M['alu'] = mat_make('M_Alu_Body', '#565049', 0.88, 0.31, coat=0.26, coat_rough=0.10, rough_var=(0.28, 0.34, 220.0))
    M['alu_dark'] = mat_make('M_Alu_Frame', '#232322', 0.78, 0.44, rough_var=(0.40, 0.48, 200.0))
    M['gold'] = mat_make('M_Gold', '#E5B45E', 1.0, 0.20, coat=0.45, coat_rough=0.06, rough_var=(0.17, 0.23, 320.0))
    M['gold_satin'] = mat_make('M_Gold_Satin', '#C08A33', 1.0, 0.30, coat=0.28, coat_rough=0.10)
    M['chrome'] = mat_make('M_Chrome', '#E9E5DD', 1.0, 0.055)
    M['steel'] = mat_make('M_Steel', '#9C9891', 1.0, 0.22)
    M['plastic'] = mat_make('M_Plastic_Dark', '#171410', 0.0, 0.40, coat=0.25, coat_rough=0.12)
    M['soft'] = mat_make('M_Plastic_Soft', '#221E19', 0.0, 0.68)
    M['rubber'] = mat_make('M_Rubber', '#0C0B0A', 0.0, 0.88)
    M['glass_tank'] = mat_make('M_Glass_Tank', '#AFBCBE', 0.0, 0.05, alpha=0.10,
                               transmission=0.0, coat=0.45, coat_rough=0.03)
    M['glass_smoke'] = mat_make('M_Glass_Smoke', '#3E3930', 0.0, 0.08, alpha=0.20, coat=0.5, coat_rough=0.03)
    M['water'] = mat_make('M_Water', '#8FA6A4', 0.0, 0.12, alpha=0.42, coat=0.6, coat_rough=0.02)
    M['display'] = mat_make('M_Glass_Display', '#0A0B0D', 0.25, 0.05, coat=1.0, coat_rough=0.02)
    M['glow'] = mat_make('M_Display_Glow', '#F2C06A', 0.0, 0.30, emis='#FFC879', emis_str=2.6)
    M['copper'] = mat_make('M_Copper', '#B06A3C', 1.0, 0.30)
    M['brass'] = mat_make('M_Brass', '#C08B45', 1.0, 0.26)
    M['felt'] = mat_make('M_Felt', '#2A2722', 0.0, 0.95)
    M['silicone'] = mat_make('M_Silicone', '#3B3833', 0.0, 0.52, coat=0.10, coat_rough=0.20)
    M['bean'] = mat_make('M_Bean', '#2A1809', 0.0, 0.66)
    M['bean_d'] = mat_make('M_Bean_Dark', '#2B1A0C', 0.0, 0.60)
    M['bean_m'] = mat_make('M_Bean_Medium', '#3E2511', 0.0, 0.56)
    M['bean_l'] = mat_make('M_Bean_Light', '#54341A', 0.0, 0.54)
    M['red'] = mat_make('M_Led_Red', '#C0392B', 0.0, 0.40, emis='#FF3B22', emis_str=1.6)


def part(name):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 0.035
    link(ob)
    ob.parent = ROOTS['__root']
    ROOTS[name] = ob
    return ob


def finish(name, bm, matname, parent=None, bevel_w=0.0012, bevel_seg=3,
           smooth=34, recalc=True):
    if recalc:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob)
    if matname:
        me.materials.append(M[matname])
    if parent is not None:
        ob.parent = parent
    if bevel_w:
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width = bevel_w
        md.segments = bevel_seg
        md.limit_method = 'ANGLE'
        md.angle_limit = math.radians(32)
        md.miter_outer = 'MITER_ARC'
        md.use_clamp_overlap = True
    if smooth:
        smooth_by_angle(ob, smooth)
    return ob


def smooth_by_angle(ob, angle=34):
    me = ob.data
    if not me.polygons:
        return
    for p in me.polygons:
        p.use_smooth = True
    bm = bmesh.new()
    bm.from_mesh(me)
    lim = math.radians(angle)
    for e in bm.edges:
        if len(e.link_faces) == 2 and e.calc_face_angle(0.0) > lim:
            e.smooth = False
    bm.to_mesh(me)
    bm.free()


def rrect(w, h, r, seg=6, cx=0.0, cy=0.0):
    """Скруглённый прямоугольник в локальных (x,y), против часовой."""
    hw, hh = w / 2.0, h / 2.0
    r = max(0.0002, min(r, hw * 0.999, hh * 0.999))
    pts = []
    corners = ((hw - r, -hh + r, -90.0), (hw - r, hh - r, 0.0),
               (-hw + r, hh - r, 90.0), (-hw + r, -hh + r, 180.0))
    for ox, oy, a0 in corners:
        n = seg if r > 0.001 else 1
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((cx + ox + r * math.cos(a), cy + oy + r * math.sin(a)))
    return pts


def prism_xz(name, pts, y0, y1, matname, parent=None, bevel_w=0.0012, bevel_seg=3):
    """Полигон в плоскости XZ, выдавленный по Y."""
    bm = bmesh.new()
    v0 = [bm.verts.new((x, y0, z)) for x, z in pts]
    v1 = [bm.verts.new((x, y1, z)) for x, z in pts]
    n = len(pts)
    bm.faces.new(v0[:])
    bm.faces.new(v1[:])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
    return finish(name, bm, matname, parent, bevel_w, bevel_seg)


def prism_xy(name, pts, z0, z1, matname, parent=None, bevel_w=0.0012, bevel_seg=3):
    """Полигон в плоскости XY, выдавленный по Z."""
    bm = bmesh.new()
    v0 = [bm.verts.new((x, y, z0)) for x, y in pts]
    v1 = [bm.verts.new((x, y, z1)) for x, y in pts]
    n = len(pts)
    bm.faces.new(v0[:])
    bm.faces.new(v1[:])
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((v0[i], v0[j], v1[j], v1[i]))
    return finish(name, bm, matname, parent, bevel_w, bevel_seg)


def box(name, size, loc, matname, parent=None, bevel_w=0.0009, bevel_seg=2, rot=None):
    bm = bmesh.new()
    sx, sy, sz = size
    for ix in (-1, 1):
        for iy in (-1, 1):
            for iz in (-1, 1):
                bm.verts.new((ix * sx / 2.0, iy * sy / 2.0, iz * sz / 2.0))
    bm.verts.ensure_lookup_table()
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
           (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for f in idx:
        bm.faces.new([bm.verts[i] for i in f])
    if rot:
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler(rot, 'XYZ').to_matrix(), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return finish(name, bm, matname, parent, bevel_w, bevel_seg)


def cyl_bm(r0, r1, h, seg=32, cap=True):
    bm = bmesh.new()
    bot, top = [], []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        bot.append(bm.verts.new((r0 * math.cos(a), r0 * math.sin(a), -h / 2.0)))
        if r1 > 1e-6:
            top.append(bm.verts.new((r1 * math.cos(a), r1 * math.sin(a), h / 2.0)))
    if not top:
        top = [bm.verts.new((0, 0, h / 2.0))]
    if cap:
        bm.faces.new(bot[:])
        if len(top) > 2:
            bm.faces.new(top[:])
    if len(top) > 2:
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((bot[i], bot[j], top[j], top[i]))
    else:
        for i in range(seg):
            j = (i + 1) % seg
            bm.faces.new((bot[i], bot[j], top[0]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm


def cyl(name, r, h, loc, matname, parent=None, seg=32, axis='Z', rot=None,
        bevel_w=0.0006, bevel_seg=2, r1=None):
    bm = cyl_bm(r, r if r1 is None else r1, h, seg)
    if axis == 'X':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((0, math.pi / 2, 0)).to_matrix(), verts=bm.verts[:])
    elif axis == 'Y':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((math.pi / 2, 0, 0)).to_matrix(), verts=bm.verts[:])
    if rot:
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler(rot, 'XYZ').to_matrix(), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return finish(name, bm, matname, parent, bevel_w, bevel_seg)


def torus(name, R, r, loc, matname, parent=None, seg=40, rseg=10,
          axis='Z', rot=None, bevel_w=0.0):
    bm = bmesh.new()
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ring = []
        for j in range(rseg):
            b = 2 * math.pi * j / rseg
            x = (R + r * math.cos(b)) * math.cos(a)
            y = (R + r * math.cos(b)) * math.sin(a)
            z = r * math.sin(b)
            ring.append(bm.verts.new((x, y, z)))
        rings.append(ring)
    for i in range(seg):
        i2 = (i + 1) % seg
        for j in range(rseg):
            j2 = (j + 1) % rseg
            bm.faces.new((rings[i][j], rings[i2][j], rings[i2][j2], rings[i][j2]))
    if axis == 'X':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((0, math.pi / 2, 0)).to_matrix(), verts=bm.verts[:])
    elif axis == 'Y':
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler((math.pi / 2, 0, 0)).to_matrix(), verts=bm.verts[:])
    if rot:
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Euler(rot, 'XYZ').to_matrix(), verts=bm.verts[:])
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return finish(name, bm, matname, parent, bevel_w, bevel_seg=2)


def sphere(name, r, loc, matname, parent=None, seg=20, rings=12, scale=(1, 1, 1)):
    bm = bmesh.new()
    verts = []
    for i in range(1, rings):
        phi = math.pi * i / rings
        ring = []
        for j in range(seg):
            th = 2 * math.pi * j / seg
            x = r * math.sin(phi) * math.cos(th) * scale[0]
            y = r * math.sin(phi) * math.sin(th) * scale[1]
            z = r * math.cos(phi) * scale[2]
            ring.append(bm.verts.new((x, y, z)))
        verts.append(ring)
    top = bm.verts.new((0, 0, r * scale[2]))
    bot = bm.verts.new((0, 0, -r * scale[2]))
    for i in range(len(verts) - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            bm.faces.new((verts[i][j], verts[i + 1][j], verts[i + 1][j2], verts[i][j2]))
    for j in range(seg):
        j2 = (j + 1) % seg
        bm.faces.new((top, verts[0][j2], verts[0][j]))
        bm.faces.new((bot, verts[-1][j], verts[-1][j2]))
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts[:])
    return finish(name, bm, matname, parent, 0.0, smooth=60)


def tube(name, pts, r, matname, parent=None, seg=8, radii=None, smooth=60):
    """Труба по безье-кривой, конвертируется в меш."""
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.resolution_u = 6
    cu.bevel_depth = r
    cu.bevel_resolution = seg // 2
    cu.fill_mode = 'FULL'
    sp = cu.splines.new('BEZIER')
    sp.bezier_points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        bp = sp.bezier_points[i]
        bp.co = Vector(p)
        bp.handle_left_type = 'AUTO'
        bp.handle_right_type = 'AUTO'
        if radii:
            bp.radius = radii[i]
    ob = bpy.data.objects.new(name, cu)
    link(ob)
    if parent is not None:
        ob.parent = parent
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.convert(target='MESH')
    ob = bpy.context.view_layer.objects.active
    if matname:
        ob.data.materials.append(M[matname])
    smooth_by_angle(ob, smooth)
    return ob


def screw(name, loc, direction, parent=None, R=0.0026, matname='steel'):
    """Винт: головка + тёмное гнездо. direction: 'X+','X-','Y+','Y-','Z+'."""
    d = {'X+': (0.005, 0, 0), 'X-': (-0.005, 0, 0), 'Y+': (0, 0.005, 0),
         'Y-': (0, -0.005, 0), 'Z+': (0, 0, 0.005), 'Z-': (0, 0, -0.005)}[direction]
    ax = 'X' if d[0] else ('Y' if d[1] else 'Z')
    cyl(name, R, 0.0018, loc, matname, parent, seg=14, axis=ax, bevel_w=0.0002)
    off = Vector(loc) + Vector(d) * 0.85
    cyl(name + ' гнездо', R * 0.55, 0.0006, off, 'rubber', parent, seg=12, axis=ax, bevel_w=0.0)



# ---------------------------------------------------------------- части

def build_chassis(p):
    """Цоколь, рама, крепёж, шильдик, нутряная связка."""
    # цоколь
    prism_xy('Цоколь', rrect(0.214, 0.394, 0.014), 0.006, 0.022, 'plastic', p, 0.0022, 3)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl('Ножка', 0.008, 0.006, (sx * 0.078, sy * 0.158, 0.003), 'rubber', p, seg=16, axis='Z', bevel_w=0.0004)
    # золотая полоса-фаска над цоколем
    prism_xy('Золотая фаска', rrect(0.208, 0.388, 0.013), 0.020, 0.030, 'gold_satin', p, 0.0016, 3)
    # рама
    box('Задняя стенка', (0.198, 0.008, 0.300), (0, 0.190, 0.185), 'alu_dark', p, 0.0012, 2)
    box('Дно рамы', (0.196, 0.380, 0.008), (0, 0.0, 0.028), 'alu_dark', p, 0.0012, 2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box('Стойка', (0.010, 0.010, 0.290), (sx * 0.094, sy * 0.180, 0.180), 'alu_dark', p, 0.0008, 2)
    box('Нижняя перекладина', (0.176, 0.008, 0.012), (0, -0.190, 0.042), 'alu_dark', p, 0.0008, 2)
    box('Верхняя перекладина', (0.176, 0.008, 0.012), (0, -0.190, 0.318), 'alu_dark', p, 0.0008, 2)
    # ниша под чашку: задняя стенка и боковины, чтобы нутро не просвечивало
    box('Стенка ниши', (0.176, 0.006, 0.078), (0, -0.166, 0.095), 'plastic', p, 0.0008, 2)
    for sx in (-1, 1):
        box('Бок ниши', (0.008, 0.030, 0.078), (sx * 0.084, -0.178, 0.095), 'plastic', p, 0.0006, 2)
    # шильдик
    box('Шильдик', (0.040, 0.0016, 0.009), (0, -0.1980, 0.014), 'gold_satin', p, 0.0006, 2)
    badge_text(p)
    # подсветка ниши под чашку (тонкая лента)
    box('Подсветка ниши', (0.150, 0.004, 0.0025), (0, -0.1740, 0.1272), 'glow', p, 0.0002, 1)
    # гидравлика: шланг от порта к порту, на концах — штуцеры и хомуты
    tube('Шланг помпа-бойлер', [(-0.055, 0.075, 0.112), (-0.050, 0.066, 0.140),
                                (-0.012, 0.040, 0.182), (0.030, 0.030, 0.230)], 0.0048, 'silicone', p)
    cyl('Штуцер помпы', 0.0062, 0.010, (-0.055, 0.075, 0.116), 'brass', p, seg=16, bevel_w=0.0004)
    cyl('Штуцер бойлера', 0.0062, 0.014, (0.030, 0.030, 0.238), 'brass', p, seg=16, axis='Y', bevel_w=0.0004)
    torus('Хомут шланга', 0.0072, 0.0013, (-0.055, 0.075, 0.124), 'steel', p, seg=20, rseg=6)
    torus('Хомут шланга', 0.0072, 0.0013, (0.030, 0.022, 0.234), 'steel', p, seg=20, rseg=6, axis='Y')

    tube('Шланг бойлер-группа', [(0.014, 0.080, 0.276), (0.000, 0.030, 0.296),
                                  (-0.026, -0.060, 0.288), (-0.030, -0.120, 0.256)], 0.0048, 'silicone', p)
    cyl('Штуцер крышки', 0.0062, 0.008, (0.014, 0.080, 0.278), 'brass', p, seg=16, bevel_w=0.0004)
    torus('Хомут шланга', 0.0072, 0.0013, (0.014, 0.080, 0.284), 'steel', p, seg=20, rseg=6)
    torus('Хомут шланга', 0.0072, 0.0013, (-0.030, -0.120, 0.250), 'steel', p, seg=20, rseg=6)

    tube('Паровая линия', [(0.030, 0.118, 0.290), (0.056, 0.040, 0.296),
                            (0.052, -0.100, 0.276), (0.050, -0.184, 0.256)], 0.0042, 'silicone', p)
    cyl('Штуцер пара', 0.0052, 0.010, (0.030, 0.118, 0.292), 'brass', p, seg=14, bevel_w=0.0003)

    tube('Дренаж группы', [(-0.030, -0.120, 0.176), (-0.026, -0.150, 0.120),
                            (-0.012, -0.156, 0.062)], 0.0042, 'silicone', p)

    # электрика
    tube('Жгут', [(0.086, 0.170, 0.070), (0.086, 0.176, 0.200), (0.060, 0.176, 0.300)], 0.0048, 'plastic', p)
    box('Стяжка', (0.014, 0.010, 0.004), (0.086, 0.172, 0.240), 'plastic', p, 0.0004, 1)
    tube('Кабель помпы', [(-0.070, 0.100, 0.078), (-0.020, 0.150, 0.092), (0.070, 0.176, 0.122)], 0.0026, 'plastic', p, seg=6)
    tube('Кабель бойлера', [(0.040, 0.104, 0.250), (0.060, 0.140, 0.228), (0.080, 0.176, 0.180)], 0.0026, 'plastic', p, seg=6)
    box('Реле', (0.030, 0.014, 0.026), (0.060, 0.181, 0.142), 'plastic', p, 0.0008, 2)
    box('Клеммник', (0.052, 0.012, 0.010), (-0.058, 0.182, 0.102), 'plastic', p, 0.0006, 2)
    for i, zz in enumerate((0.100, 0.320)):
        screw('Винт рамы', (0.088 if i else -0.088, -0.1965, zz), 'Y-', p, R=0.0028)


def badge_text(p):
    cu = bpy.data.curves.new('Шильдик текст', 'FONT')
    cu.body = 'CREMA'
    cu.size = 0.0055
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = 0.00018
    cu.resolution_u = 2
    ob = bpy.data.objects.new('Шильдик текст', cu)
    link(ob)
    ob.parent = p
    ob.location = (0, -0.1986, 0.0135)
    ob.rotation_euler = (math.radians(90), 0, 0)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.convert(target='MESH')
    ob = bpy.context.view_layer.objects.active
    ob.data.materials.append(M['chrome'])


def panel_profile(sign, th=0.006, r_out=0.020):
    """Сечение щёки в XY: боковина + заворот на лицо (рамка 31 мм)."""
    xi = sign * (X1 - th)
    ri = r_out - th
    cx, cy = sign * (X1 - r_out), -0.175
    pts = [(sign * X1, YB), (sign * X1, cy)]
    for i in range(9):
        a = -90.0 * i / 8.0
        ar = math.radians(a)
        pts.append((cx + sign * r_out * math.cos(ar), cy + r_out * math.sin(ar)))
    pts.append((sign * 0.074, -0.195))
    pts.append((sign * 0.074, -0.189))
    for i in range(9):
        a = -90.0 + 90.0 * i / 8.0
        ar = math.radians(a)
        pts.append((cx + sign * ri * math.cos(ar), cy + ri * math.sin(ar)))
    pts.append((xi, YB))
    return pts


def build_panel(p, sign, title):
    pts = panel_profile(sign)
    prism_xy(title, pts, 0.030, 0.380, 'alu', p, 0.0028, 4)
    # рёбра жёсткости и бобышки на внутренней стороне
    xi = sign * (X1 - 0.006)
    for z in (0.150, 0.250):
        box('Ребро', (0.005, 0.230, 0.012), (xi - sign * 0.0025, 0.030, z), 'alu', p, 0.0006, 2)
    for y in (-0.080, 0.080):
        cyl('Бобышка', 0.0065, 0.010, (xi - sign * 0.005, y, 0.300), 'alu', p, seg=16, axis='X', bevel_w=0.0006)
        screw('Винт щёки', (xi - sign * 0.0105, y, 0.300), 'X-' if sign > 0 else 'X+', p, R=0.0026)
    box('Прокладка', (0.003, 0.210, 0.100), (xi - sign * 0.0015, 0.040, 0.205), 'felt', p, 0.0004, 1)
    return p


def build_front(p):
    # верхняя плита (под группу) — выступает вперёд
    prism_xz('Верхняя плита', rrect(0.160, 0.077, 0.006, 5, 0, 0.2785), -0.1935, -0.1915, 'gold', p, 0.0008, 3)
    # нижняя плита — утоплена на 2 мм, шов 4 мм; под ней открытая ниша под чашку
    prism_xz('Нижняя плита', rrect(0.160, 0.106, 0.006, 5, 0, 0.183), -0.1915, -0.1895, 'gold', p, 0.0008, 3)
    for x in (-0.072, 0.072):
        screw('Винт панели', (x, -0.1920, 0.140), 'Y-', p, R=0.0022)


def build_deck(p):
    prism_xy('Площадка', rrect(0.196, 0.380, 0.020), 0.330, 0.352, 'alu', p, 0.0020, 3)
    box('Губа', (0.196, 0.013, 0.012), (0, -0.188, 0.326), 'alu_dark', p, 0.0012, 3)
    prism_xy('Корона', rrect(0.190, 0.290, 0.024, 5, 0, 0.030), 0.352, 0.370, 'alu_dark', p, 0.0020, 3)
    for i, y in enumerate((-0.060, -0.012, 0.036)):
        cyl('Прут', 0.0022, 0.150, (-0.010, y, 0.3725), 'gold', p, seg=16, axis='X', bevel_w=0.0004)
    # гнездо бункера
    cyl('Обойма бункера', 0.052, 0.014, (0, 0.115, 0.371), 'gold_satin', p, seg=48, bevel_w=0.0012)
    torus('Кольцо обоймы', 0.050, 0.0028, (0, 0.115, 0.377), 'gold', p, seg=48, rseg=8)
    # ручка-скоба
    tube('Скоба', [(-0.078, -0.075, 0.368), (-0.072, -0.075, 0.382),
                   (-0.034, -0.075, 0.384), (-0.028, -0.075, 0.368)], 0.0072, 'gold', p, seg=12)
    # мелкие детали на площадке
    cyl('Стойка', 0.0045, 0.016, (0.088, -0.060, 0.374), 'chrome', p, seg=20, bevel_w=0.0006)
    cyl('Маховик', 0.0095, 0.011, (0.062, 0.040, 0.373), 'gold', p, seg=28, bevel_w=0.0008)
    torus('Обод маховика', 0.0095, 0.0016, (0.062, 0.040, 0.378), 'gold', p, seg=28, rseg=8)


def build_controls(p):
    # окно уровня воды: прорезь в золотой плите, за ней стекло и вода с мениском
    prism_xz('Рамка окна уровня', rrect(0.030, 0.078, 0.012, 6, -0.020, 0.199), -0.1968, -0.1950, 'chrome', p, 0.0006, 3)
    prism_xz('Стекло окна уровня', rrect(0.022, 0.070, 0.010, 6, -0.020, 0.199), -0.1979, -0.1968, 'glass_tank', p, 0.0006, 3)
    prism_xz('Вода в окне', rrect(0.019, 0.040, 0.008, 5, -0.020, 0.184), -0.1982, -0.1979, 'water', p, 0.0)
    prism_xz('Мениск', rrect(0.019, 0.0026, 0.001, 4, -0.020, 0.2042), -0.1984, -0.1982, 'water', p, 0.0)
    for z in (0.172, 0.184, 0.196, 0.208, 0.220):
        box('Риска уровня', (0.006, 0.0008, 0.0008), (0.0135, -0.1983, z), 'gold_satin', p, 0.0)

    # дисплей — маленький экранчик над клавишами
    prism_xz('Рамка дисплея', rrect(0.050, 0.020, 0.006, 6, -0.020, 0.1585), -0.1968, -0.1950, 'chrome', p, 0.0006, 3)
    prism_xz('Стекло дисплея', rrect(0.043, 0.014, 0.005, 6, -0.020, 0.1585), -0.1977, -0.1968, 'display', p, 0.0006, 3)
    prism_xz('Свечение', rrect(0.026, 0.0035, 0.0016, 4, -0.020, 0.1605), -0.1980, -0.1977, 'glow', p, 0.0)
    cyl('Индикатор', 0.0020, 0.0006, (0.008, -0.1980, 0.1565), 'glow', p, seg=16, axis='Y', bevel_w=0.0)
    # кнопки с ходом
    for z in (0.135, 0.118):
        torus('Гнездо кнопки', 0.0074, 0.0011, (-0.058, -0.1962, z), 'rubber', p, seg=28, rseg=8, axis='Y')
        cyl('Кнопка', 0.0060, 0.0048, (-0.058, -0.1984, z), 'gold_satin', p, seg=28, axis='Y', bevel_w=0.0010, bevel_seg=3)
    # клавиши
    for z in (0.1385, 0.1455, 0.1525):
        prism_xz('Клавиша', rrect(0.030, 0.0042, 0.0018, 4, 0.038, z), -0.1965, -0.1932, 'gold_satin', p, 0.0005, 2)


def build_group(p):
    prism_xz('Кожух группы', rrect(0.060, 0.068, 0.028, 8, -0.030, 0.284), -0.242, -0.1915, 'gold', p, 0.0050, 4)
    prism_xz('Хромовая лента', rrect(0.0628, 0.0072, 0.0034, 6, -0.030, 0.305), -0.2440, -0.1910, 'steel', p, 0.0006, 2)
    prism_xz('Шейка', rrect(0.042, 0.026, 0.008, 5, -0.030, 0.240), -0.2350, -0.1915, 'gold', p, 0.0010, 3)
    cyl('Носик', 0.0080, 0.016, (-0.030, -0.232, 0.219), 'gold', p, seg=28, bevel_w=0.0010, r1=0.0052)
    torus('Кольцо носика', 0.0130, 0.0022, (-0.030, -0.232, 0.2315), 'chrome', p, seg=32, rseg=8)
    box('Рычаг группы', (0.024, 0.010, 0.006), (0.004, -0.214, 0.264), 'gold', p, 0.0012, 2, rot=(0, 0, math.radians(-8)))
    for i in range(2):
        screw('Винт группы', (-0.030 + 0.0, -0.2435, 0.252 + i * 0.060), 'Y-', p, R=0.0020)


def build_portafilter(p):
    cyl('Чаша', 0.0190, 0.017, (-0.030, -0.236, 0.207), 'chrome', p, seg=32, bevel_w=0.0012, bevel_seg=3)
    cyl('Корзина', 0.0158, 0.015, (-0.030, -0.236, 0.2055), 'rubber', p, seg=28, bevel_w=0.0)
    cyl('Носик рожка', 0.0068, 0.011, (-0.030, -0.236, 0.1935), 'chrome', p, seg=24, bevel_w=0.0006, r1=0.0046)
    axis = Vector((0, -math.sin(math.radians(120)), math.cos(math.radians(120))))
    start = Vector((-0.030, -0.238, 0.205))
    mid = start + axis * 0.036
    cyl('Рукоять', 0.0068, 0.062, tuple(mid), 'plastic', p, seg=24, rot=(math.radians(120), 0, 0), bevel_w=0.0016, bevel_seg=3)
    fer = start + axis * 0.004
    cyl('Латунная втулка', 0.0082, 0.009, tuple(fer), 'gold_satin', p, seg=24, rot=(math.radians(120), 0, 0), bevel_w=0.0008)
    end = start + axis * 0.068
    sphere('Торец рукояти', 0.0068, tuple(end), 'plastic', p, seg=16, rings=10)


def build_steam(p):
    prism_xz('Кожух крана', rrect(0.050, 0.068, 0.023, 8, 0.050, 0.284), -0.240, -0.1915, 'gold', p, 0.0046, 4)
    prism_xz('Хромовая лента крана', rrect(0.0525, 0.0070, 0.0032, 6, 0.050, 0.305), -0.2422, -0.1910, 'steel', p, 0.0006, 2)
    box('Клапан', (0.034, 0.026, 0.024), (0.050, -0.200, 0.248), 'gold', p, 0.0016, 3)
    sphere('Шарнир', 0.0095, (0.052, -0.214, 0.233), 'chrome', p, seg=20, rings=12)
    tube('Трубка пара', [(0.053, -0.218, 0.229), (0.058, -0.228, 0.196),
                         (0.062, -0.236, 0.160), (0.060, -0.233, 0.140)],
         0.0052, 'gold', p, seg=12, radii=[1.0, 0.95, 0.85, 0.72])
    cyl('Наконечник', 0.0044, 0.008, (0.060, -0.233, 0.135), 'chrome', p, seg=20, bevel_w=0.0006)
    cyl('Вентиль', 0.0100, 0.013, (0.050, -0.150, 0.380), 'gold', p, seg=24, bevel_w=0.0012)
    torus('Обод вентиля', 0.0100, 0.0016, (0.050, -0.150, 0.386), 'gold', p, seg=24, rseg=8)
    tube('Трубка подачи', [(0.030, -0.198, 0.252), (0.030, -0.207, 0.200), (0.031, -0.211, 0.142)],
         0.0030, 'gold', p, seg=8)


def build_tray(p):
    prism_xy('Лоток', rrect(0.184, 0.096, 0.012, 5, 0, -0.146), 0.026, 0.050, 'gold', p, 0.0016, 3)
    box('Борт перед', (0.184, 0.007, 0.010), (0, -0.1935, 0.053), 'gold', p, 0.0012, 2)
    box('Борт зад', (0.184, 0.007, 0.010), (0, -0.0995, 0.053), 'gold', p, 0.0012, 2)
    for sx in (-1, 1):
        box('Борт бок', (0.007, 0.096, 0.010), (sx * 0.0885, -0.146, 0.053), 'gold', p, 0.0012, 2)
    for i in range(8):
        y = -0.186 + i * 0.0088
        box('Прут решётки', (0.152, 0.0046, 0.0030), (0, y, 0.0505), 'gold', p, 0.0006, 2)
    box('Вставка', (0.046, 0.022, 0.0016), (0.044, -0.180, 0.0512), 'rubber', p, 0.0004, 1)
    cyl('Индикатор лотка', 0.0024, 0.0016, (-0.074, -0.180, 0.0510), 'red', p, seg=16, bevel_w=0.0)
    box('Язычок лотка', (0.048, 0.005, 0.006), (0, -0.102, 0.055), 'plastic', p, 0.0006, 2)


def build_tank(p):
    prism_xy('Корпус бака', rrect(0.104, 0.056, 0.010), 0.048, 0.318, 'glass_tank', p, 0.0012, 2)
    box('Крышка бака', (0.106, 0.058, 0.008), (-0.042, 0.156, 0.3225), 'soft', p, 0.0012, 2)
    box('Ручка бака', (0.042, 0.010, 0.006), (-0.042, 0.156, 0.329), 'gold_satin', p, 0.0010, 2)
    box('Окно уровня', (0.005, 0.0025, 0.180), (0.0095, 0.150, 0.180), 'glass_smoke', p, 0.0004, 1)
    box('Вода', (0.098, 0.050, 0.170), (-0.042, 0.156, 0.135), 'glass_tank', p, 0.0)


def build_hopper(p):
    cyl('Обойма', 0.050, 0.014, (0, 0.115, 0.372), 'gold_satin', p, seg=48, bevel_w=0.0012)
    cyl('Стакан', 0.048, 0.058, (0, 0.115, 0.408), 'glass_smoke', p, seg=40, bevel_w=0.0010, r1=0.043)
    torus('Кольцо', 0.0428, 0.0030, (0, 0.115, 0.434), 'gold', p, seg=40, rseg=8)
    sphere('Крышка', 0.045, (0, 0.115, 0.436), 'gold_satin', p, seg=28, rings=12, scale=(1, 1, 0.34))
    cyl('Ручка крышки', 0.0085, 0.010, (0, 0.115, 0.4485), 'gold', p, seg=20, bevel_w=0.0010)
    beans(p)


def beans(p):
    # стакан заполняется целиком, но без «военной» сетки: позиции и повороты вразброс
    bm = bmesh.new()
    # три оттенка: однородная тёмная масса читается как шоколад
    bms = (bmesh.new(), bmesh.new(), bmesh.new())
    rnd = random.Random(11)
    z0, z1 = 0.3815, 0.4185
    layers = 6
    for li in range(layers):
        t = li / (layers - 1)
        z = z0 + (z1 - z0) * t
        R = 0.0405 - 0.0045 * t
        step = 0.0084
        n = int(R / step) + 2
        for ix in range(-n, n + 1):
            for iy in range(-n, n + 1):
                jx = rnd.uniform(-0.0032, 0.0032)
                jy = rnd.uniform(-0.0032, 0.0032)
                x = ix * step + jx
                y = iy * step * 0.94 + jy
                if x * x + y * y > (R - 0.0022) ** 2:
                    continue
                s = rnd.uniform(0.72, 1.22)
                rot = (rnd.uniform(-1.2, 1.2), rnd.uniform(-1.2, 1.2), rnd.uniform(0, 6.283))
                g = rnd.choice(bms)
                add_blob(g, 0.0054 * s, (x, 0.115 + y, z + rnd.uniform(-0.0040, 0.0040)),
                         (1.0, rnd.uniform(0.64, 0.78), rnd.uniform(0.50, 0.66)), rot)
    for i, g in enumerate(bms):
        finish('Зёрна %d' % (i + 1), g, ('bean_d', 'bean_m', 'bean_l')[i], p, 0.0, smooth=55)
    # низ стакана закрываем «массой кофе» того же материала, но сажаем её ниже среза
    cyl('Кофейная масса', 0.0360, 0.009, (0, 0.115, 0.3835), 'bean', p, seg=32, bevel_w=0.0)


def add_blob(bm, r, loc, scale, rot):
    seg, rings = 8, 5
    if not isinstance(rot, (tuple, list)):
        rot = (0.0, 0.0, rot)
    rx0, ry0, rz0 = rot
    cx, sx = math.cos(rx0), math.sin(rx0)
    cy, sy = math.cos(ry0), math.sin(ry0)
    cz, sz = math.cos(rz0), math.sin(rz0)
    verts = []

    def place(px, py, pz):
        # Rz * Ry * Rx
        y1 = py * cx - pz * sx
        z1 = py * sx + pz * cx
        x2 = px * cy + z1 * sy
        z2 = -px * sy + z1 * cy
        x3 = x2 * cz - y1 * sz
        y3 = x2 * sz + y1 * cz
        return (x3 + loc[0], y3 + loc[1], z2 + loc[2])

    for i in range(1, rings):
        phi = math.pi * i / rings
        ring = []
        for j in range(seg):
            th = 2 * math.pi * j / seg
            x = r * math.sin(phi) * math.cos(th) * scale[0]
            y = r * math.sin(phi) * math.sin(th) * scale[1]
            z = r * math.cos(phi) * scale[2]
            # борозда зерна: поджимаем поясок по середине — читается как разлом
            if abs(phi - math.pi / 2) < 0.55:
                y *= 0.64
            ring.append(bm.verts.new(place(x, y, z)))
        verts.append(ring)
    top = bm.verts.new(place(0.0, 0.0, r * scale[2]))
    bot = bm.verts.new(place(0.0, 0.0, -r * scale[2]))
    for i in range(len(verts) - 1):
        for j in range(seg):
            j2 = (j + 1) % seg
            bm.faces.new((verts[i][j], verts[i + 1][j], verts[i + 1][j2], verts[i][j2]))
    for j in range(seg):
        j2 = (j + 1) % seg
        bm.faces.new((top, verts[0][j2], verts[0][j]))
        bm.faces.new((bot, verts[-1][j], verts[-1][j2]))


def build_brew(p):
    cyl('Камера', 0.029, 0.070, (-0.030, -0.120, 0.215), 'plastic', p, seg=32, bevel_w=0.0012, bevel_seg=3)
    cyl('Крышка камеры', 0.031, 0.008, (-0.030, -0.120, 0.252), 'alu_dark', p, seg=32, bevel_w=0.0008)
    cyl('Поршень', 0.022, 0.016, (-0.030, -0.120, 0.263), 'chrome', p, seg=28, bevel_w=0.0008)
    box('Кулачок', (0.040, 0.010, 0.007), (0.000, -0.120, 0.271), 'gold', p, 0.0010, 2, rot=(0, 0, math.radians(14)))
    box('Кронштейн', (0.070, 0.006, 0.006), (-0.030, -0.150, 0.181), 'alu_dark', p, 0.0006, 2)
    cyl('Сетка', 0.0245, 0.0025, (-0.030, -0.120, 0.1815), 'steel', p, seg=32, bevel_w=0.0)
    tube('Патрубок', [(-0.030, -0.120, 0.180), (-0.032, -0.152, 0.199), (-0.030, -0.188, 0.214)], 0.0040, 'brass', p, seg=8)
    box('Фиксатор', (0.022, 0.008, 0.010), (-0.062, -0.120, 0.215), 'alu_dark', p, 0.0006, 2)
    box('Рычаг блока', (0.038, 0.006, 0.006), (-0.030, -0.146, 0.267), 'steel', p, 0.0006, 2)
    cyl('Пружина', 0.0050, 0.014, (-0.052, -0.120, 0.240), 'steel', p, seg=14, bevel_w=0.0003)
    for z in (0.196, 0.236):
        screw('Винт блока', (-0.030, -0.1500, z), 'Y-', p, R=0.0022)


def build_boiler(p):
    cyl('Корпус бойлера', 0.034, 0.150, (0.030, 0.080, 0.190), 'copper', p, seg=36, bevel_w=0.0014, bevel_seg=3)
    cyl('Изоляция', 0.0365, 0.120, (0.030, 0.080, 0.190), 'felt', p, seg=36, bevel_w=0.0010)
    cyl('Верхняя крышка', 0.030, 0.012, (0.030, 0.080, 0.271), 'copper', p, seg=32, bevel_w=0.0010)
    cyl('Термостат', 0.012, 0.009, (0.030, 0.080, 0.281), 'plastic', p, seg=20, bevel_w=0.0006)
    cyl('Штуцер', 0.0055, 0.016, (0.030, 0.118, 0.238), 'brass', p, seg=16, axis='Y', bevel_w=0.0004)
    cyl('Штуцер', 0.0055, 0.016, (0.030, 0.042, 0.238), 'brass', p, seg=16, axis='Y', bevel_w=0.0004)
    cyl('Дренаж', 0.0055, 0.014, (0.066, 0.080, 0.150), 'brass', p, seg=16, axis='X', bevel_w=0.0004)
    cyl('Клапан', 0.0060, 0.014, (0.030, 0.118, 0.286), 'brass', p, seg=16, bevel_w=0.0004)
    box('Хомут', (0.012, 0.070, 0.010), (0.058, 0.080, 0.300), 'steel', p, 0.0006, 2)
    cyl('Фланец ТЭНа', 0.0160, 0.006, (0.030, 0.115, 0.212), 'steel', p, seg=22, axis='Y', bevel_w=0.0006)
    box('Клемма ТЭНа', (0.016, 0.008, 0.011), (0.030, 0.124, 0.212), 'plastic', p, 0.0008, 2)
    cyl('Датчик тепла', 0.0040, 0.010, (0.030, 0.115, 0.168), 'brass', p, seg=14, axis='Y', bevel_w=0.0003)
    cyl('Предохранитель', 0.0052, 0.016, (0.062, 0.080, 0.238), 'brass', p, seg=14, axis='X', bevel_w=0.0003)


def build_pump(p):
    cyl('Корпус помпы', 0.019, 0.062, (-0.055, 0.075, 0.075), 'steel', p, seg=28, axis='X', bevel_w=0.0010)
    box('Мотор', (0.044, 0.046, 0.044), (-0.090, 0.075, 0.075), 'plastic', p, 0.0016, 3)
    cyl('Крыльчатка', 0.017, 0.008, (-0.114, 0.075, 0.075), 'alu_dark', p, seg=24, axis='X', bevel_w=0.0008)
    for sy in (-1, 1):
        cyl('Лапа', 0.006, 0.010, (-0.055, 0.075 + sy * 0.026, 0.049), 'rubber', p, seg=14, bevel_w=0.0004)
    cyl('Патрубок помпы', 0.006, 0.016, (-0.055, 0.075, 0.110), 'brass', p, seg=16, bevel_w=0.0004)


def build_grinder(p):
    cyl('Корпус кофемолки', 0.026, 0.046, (0, 0.115, 0.348), 'alu', p, seg=32, bevel_w=0.0012, bevel_seg=3)
    torus('Кольцо кофемолки', 0.0270, 0.0028, (0, 0.115, 0.370), 'gold', p, seg=32, rseg=8)
    cyl('Мотор кофемолки', 0.022, 0.042, (0, 0.115, 0.311), 'plastic', p, seg=24, bevel_w=0.0010)
    box('Кронштейн кофемолки', (0.070, 0.010, 0.008), (0, 0.150, 0.330), 'alu_dark', p, 0.0008, 2)
    tube('Течка', [(0, 0.108, 0.330), (0.000, 0.050, 0.300), (-0.020, -0.030, 0.284), (-0.030, -0.096, 0.274)],
         0.0072, 'alu', p, seg=8)
    box('Заслонка', (0.016, 0.003, 0.014), (-0.030, -0.099, 0.274), 'chrome', p, 0.0006, 2)


# ---------------------------------------------------------------- разборка

EXPLODE = {
    'Корпус': (0.0, 0.0, 0.0),
    'Левая панель': (-0.046, 0.0, -0.184),
    'Правая панель': (0.046, 0.0, -0.184),
    'Лицевая панель': (0.0, -0.130, 0.0),
    'Верхняя площадка': (0.0, 0.015, 0.138),
    'Панель управления': (0.006, -0.161, 0.009),
    'Варочная группа': (-0.015, -0.146, 0.015),
    'Держатель фильтра': (-0.018, -0.192, -0.015),
    'Паровой кран': (0.046, -0.115, 0.0),
    'Каплесборник': (0.0, -0.146, -0.046),
    'Бак для воды': (-0.138, 0.046, 0.015),
    'Контейнер для зёрен': (0.0, 0.015, 0.138),
    'Заварочный блок': (0.0, -0.077, 0.031),
    'Бойлер': (-0.069, 0.061, 0.054),
    'Помпа': (-0.107, -0.046, -0.031),
    'Кофемолка': (0.054, 0.054, 0.115),
}

WAVES = [
    ['Левая панель', 'Правая панель', 'Верхняя площадка', 'Контейнер для зёрен'],
    ['Лицевая панель', 'Панель управления'],
    ['Варочная группа', 'Держатель фильтра', 'Паровой кран', 'Каплесборник'],
    ['Бак для воды'],
    ['Заварочный блок', 'Бойлер', 'Помпа', 'Кофемолка'],
]


def explode_all():
    for name, vec in EXPLODE.items():
        ob = ROOTS.get(name)
        if ob is None:
            print('MISSING PART', name)
            continue
        ob['explode'] = list(vec)
    # порядок волн тоже уезжает в extras — пригодится сайту
    for i, wave in enumerate(WAVES):
        for name in wave:
            ob = ROOTS.get(name)
            if ob is not None:
                ob['wave'] = i


# ---------------------------------------------------------------- сцена

def reset_scene():
    global SC, C
    bpy.ops.wm.read_factory_settings(use_empty=True)
    SC = bpy.context.scene
    C = bpy.context
    SC.render.engine = 'BLENDER_EEVEE'
    SC.render.resolution_x = 1600
    SC.render.resolution_y = 1200
    SC.render.resolution_percentage = 100
    SC.render.image_settings.file_format = 'PNG'
    SC.render.image_settings.color_mode = 'RGBA'
    SC.render.film_transparent = False
    try:
        SC.view_settings.view_transform = 'AgX'
    except Exception:
        pass
    try:
        SC.view_settings.look = 'None'
    except Exception:
        pass
    try:
        SC.eevee.taa_render_samples = 64
        SC.eevee.use_raytracing = True
    except Exception:
        pass
    try:
        SC.eevee.ray_tracing_options.use_denoise = True
    except Exception:
        pass
    w = bpy.data.worlds.new('W_Dark')
    SC.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    nt = w.node_tree
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    el = ramp.color_ramp.elements
    el[0].position = 0.0
    el[0].color = (*srgb('#141110'), 1.0)
    el[1].position = 0.40
    el[1].color = (*srgb('#4A4033'), 1.0)
    e2 = el.new(0.55)
    e2.color = (*srgb('#8A7A62'), 1.0)
    e3 = el.new(0.90)
    e3.color = (*srgb('#3A322A'), 1.0)
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs[1].default_value = 0.95


def aim(ob, target):
    d = Vector(target) - Vector(ob.location)
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def add_light(name, loc, target, size, power, color=(1.0, 0.94, 0.86)):
    d = bpy.data.lights.new(name, 'AREA')
    d.shape = 'RECTANGLE'
    d.size = size[0]
    d.size_y = size[1]
    d.energy = power
    d.color = color
    ob = bpy.data.objects.new(name, d)
    link(ob)
    ob.location = loc
    aim(ob, target)
    STUDIO.append(ob)
    return ob


def add_ground(z=-0.0006):
    me = bpy.data.meshes.new('Ground')
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((-4, -4, z), (4, -4, z), (4, 4, z), (-4, 4, z))]
    bm.faces.new(v)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('Ground', me)
    link(ob)
    me.materials.append(mat_make('M_Ground', '#050403', 0.0, 0.90))
    ob.visible_shadow = True
    STUDIO.append(ob)
    return ob


def blob_mat():
    """Мягкая контактная тень: радиальный градиент в альфу."""
    mt = bpy.data.materials.new('M_Blob')
    mt.use_nodes = True
    nt = mt.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    mix = nt.nodes.new('ShaderNodeMixShader')
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    df = nt.nodes.new('ShaderNodeBsdfDiffuse')
    df.inputs['Color'].default_value = (0.012, 0.010, 0.008, 1.0)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    comb = nt.nodes.new('ShaderNodeCombineXYZ')
    comb.inputs['X'].default_value = 0.5
    comb.inputs['Y'].default_value = 0.5
    sub = nt.nodes.new('ShaderNodeVectorMath')
    sub.operation = 'SUBTRACT'
    nt.links.new(tc.outputs['Generated'], sub.inputs[0])
    nt.links.new(comb.outputs[0], sub.inputs[1])
    leng = nt.nodes.new('ShaderNodeVectorMath')
    leng.operation = 'LENGTH'
    nt.links.new(sub.outputs['Vector'], leng.inputs[0])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    ramp.color_ramp.elements[1].position = 0.38
    ramp.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    nt.links.new(leng.outputs['Value'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], mix.inputs['Fac'])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(df.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    return mt


def add_shadow_blob(r=0.62):
    me = bpy.data.meshes.new('Blob')
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((-r, -r, 0.0), (r, -r, 0.0), (r, r, 0.0), (-r, r, 0.0))]
    bm.faces.new(v)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('Blob', me)
    ob.location = (0.0, -0.01, 0.0006)
    link(ob)
    me.materials.append(blob_mat())
    STUDIO.append(ob)
    return ob

def add_wall():
    me = bpy.data.meshes.new('Wall')
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((-3, 1.45, 0), (3, 1.45, 0), (3, 1.45, 3), (-3, 1.45, 3))]
    bm.faces.new(v)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new('Wall', me)
    link(ob)
    me.materials.append(mat_make('M_Wall', '#100C0A', 0.0, 0.72))
    STUDIO.append(ob)
    return ob


def add_camera(loc, target, lens=70, name='Cam'):
    d = bpy.data.cameras.new(name)
    d.lens = lens
    d.sensor_width = 36
    ob = bpy.data.objects.new(name, d)
    link(ob)
    ob.location = loc
    aim(ob, target)
    SC.camera = ob
    STUDIO.append(ob)
    return ob


def studio(stage):
    """Три зоны света + тёмный пол; на разборке пол уезжает вниз."""
    add_light('Key', (-1.05, -1.25, 1.28), (0.0, -0.02, 0.24), (2.20, 1.60), 110)
    add_light('Fill', (1.25, -0.95, 0.52), (0.0, 0.0, 0.18), (1.40, 1.05), 45, (0.95, 0.92, 0.90))
    add_light('Rim', (0.30, 1.30, 1.00), (0.0, 0.0, 0.22), (1.00, 0.70), 70, (1.0, 0.88, 0.74))
    add_light('Cavity', (0.16, -0.13, 0.122), (0.0, -0.15, 0.05), (0.16, 0.09), 3.5, (1.0, 0.88, 0.72))
    if stage == 4:
        add_ground(-0.42)
        add_camera((1.22, -1.52, 0.86), (0.01, 0.0, 0.12), 52)
    else:
        add_ground()
        add_camera((-0.44, -1.68, 0.57), (0.0, 0.0, 0.215), 85)


def render(path, transparent=False, size=(1600, 1200)):
    SC.render.resolution_x, SC.render.resolution_y = size
    SC.render.film_transparent = transparent
    SC.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('RENDER', path)


def poster():
    """Постер 1200x1200 на Cycles: shadow catcher + прозрачный фон."""
    SC.render.engine = 'CYCLES'
    try:
        SC.cycles.device = 'CPU'
        SC.cycles.samples = 96
        SC.cycles.use_denoising = True
        SC.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception as e:
        print('cycles opt', e)
    try:
        SC.cycles.max_bounces = 8
        SC.cycles.transmission_bounces = 8
        SC.cycles.glossy_bounces = 6
    except Exception:
        pass
    for ob in [o for o in STUDIO if o.type == 'CAMERA']:
        bpy.data.objects.remove(ob, do_unlink=True)
        STUDIO.remove(ob)
    g = bpy.data.objects.get('Ground')
    if g is not None:
        g.hide_render = True
    # тень рисуется в вебе (blob-плейн в three.js), в постере — прозрачный PNG
    add_camera((-0.34, -1.22, 0.32), (0.0, 0.015, 0.190), 72, 'PosterCam')
    render(STILL, True, (1200, 1200))


# ---------------------------------------------------------------- видимость

FACE_PARTS = ['Лицевая панель', 'Панель управления', 'Варочная группа',
              'Держатель фильтра', 'Паровой кран', 'Каплесборник',
              'Бак для воды', 'Контейнер для зёрен']
INNER_PARTS = ['Заварочный блок', 'Бойлер', 'Помпа', 'Кофемолка']
SHELL_PARTS = ['Левая панель', 'Правая панель', 'Верхняя площадка']


def walk(ob):
    for ch in ob.children:
        yield ch
        yield from walk(ch)


def visibility(stage):
    hide = set()
    if stage <= 1:
        hide |= set(['Панель управления', 'Варочная группа', 'Держатель фильтра',
                     'Паровой кран', 'Каплесборник', 'Бак для воды', 'Контейнер для зёрен'])
        hide |= set(INNER_PARTS)
    elif stage == 2:
        hide |= set(INNER_PARTS)
    elif stage == 3:
        hide |= set(SHELL_PARTS) | set(['Лицевая панель', 'Панель управления',
                                        'Варочная группа', 'Держатель фильтра',
                                        'Паровой кран', 'Каплесборник'])
    for name in hide:
        ob = ROOTS.get(name)
        if not ob:
            continue
        ob.hide_render = True
        ob.hide_viewport = True
        for ch in walk(ob):
            ch.hide_render = True
            ch.hide_viewport = True


# ---------------------------------------------------------------- сборка

def build_all():
    root = bpy.data.objects.new('Машина', None)
    root.empty_display_size = 0.06
    link(root)
    ROOTS['__root'] = root
    build_chassis(part('Корпус'))
    build_panel(part('Левая панель'), -1, 'Левая панель')
    build_panel(part('Правая панель'), 1, 'Правая панель')
    build_front(part('Лицевая панель'))
    build_deck(part('Верхняя площадка'))
    build_controls(part('Панель управления'))
    build_group(part('Варочная группа'))
    build_portafilter(part('Держатель фильтра'))
    build_steam(part('Паровой кран'))
    build_tray(part('Каплесборник'))
    build_tank(part('Бак для воды'))
    build_hopper(part('Контейнер для зёрен'))
    build_brew(part('Заварочный блок'))
    build_boiler(part('Бойлер'))
    build_pump(part('Помпа'))
    build_grinder(part('Кофемолка'))


def export_glb():
    # процедурный шум шероховатости в glTF не переживает экспорт: он теряет
    # конкретное значение roughness, и металл в вебе становится плоским.
    # Рендеры к этому моменту уже сняты — расцепляем шум перед выгрузкой.
    for m in bpy.data.materials:
        if not m.use_nodes:
            continue
        b = m.node_tree.nodes.get('Principled BSDF')
        if not b:
            continue
        for lk in list(m.node_tree.links):
            if lk.to_node == b and lk.to_socket.name == 'Roughness':
                m.node_tree.links.remove(lk)
    for ob in list(STUDIO):
        try:
            bpy.data.objects.remove(ob, do_unlink=True)
        except Exception:
            pass
    STUDIO.clear()
    kw = dict(filepath=GLB, export_format='GLB', export_apply=True,
              export_yup=True, export_extras=True, export_cameras=False,
              export_lights=False, export_animations=False,
              export_draco_mesh_compression_enable=False)
    try:
        bpy.ops.export_scene.gltf(**kw)
    except TypeError as e:
        print('gltf kwargs', e)
        bpy.ops.export_scene.gltf(filepath=GLB, export_format='GLB')
    print('GLB', GLB, os.path.getsize(GLB))


def summary():
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    faces = sum(len(o.data.polygons) for o in meshes)
    parts = [n for n in ROOTS if n != '__root']
    print('BLENDER_OK')
    print(json.dumps({
        'stage': STAGE,
        'parts': parts,
        'meshes': len(meshes),
        'faces': faces,
        'glb_bytes': os.path.getsize(GLB) if os.path.exists(GLB) else 0,
        'explode': {n: list(ROOTS[n].get('explode', [])) for n in parts},
    }, ensure_ascii=False))


def main():
    reset_scene()
    materials()
    build_all()
    visibility(STAGE)
    if STAGE >= 4:
        explode_all()
        for name, vec in EXPLODE.items():
            ob = ROOTS.get(name)
            if ob is not None and STAGE == 4:
                ob.location = Vector(vec)
    studio(STAGE)
    render(os.path.join(PICS, 'model-stage%d.png' % STAGE))
    if STAGE >= 5:
        poster()
        export_glb()
        bpy.ops.wm.save_as_mainfile(filepath=BLEND)
    summary()


if __name__ == '__main__':
    main()


