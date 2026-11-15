"""
Сборка кофемашины в Blender через bpy.

Запуск:
    blender -b -P tools/blender/build.py -- --stage 1

Этапы:
    1 — корпус и панели
    2 — внешние узлы (группа, кран, поддон, бункер, бак)
    3 — внутренние узлы (бойлер, помпа, заварочный блок)
    4 — разборка: rest_matrix и explode_vector
    5 — экспорт GLB

Сцена в метрах: 0.24 (X, ширина) × 0.44 (Y, глубина) × 0.34 (Z, высота).
Перед камерой стоит −Y, поэтому фронт машины смотрит в −Y.
"""

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

W, D, H = 0.240, 0.440, 0.340
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PICS = os.path.join(ROOT, "pics")
BLEND = os.path.join(ROOT, "tools", "blender", "machine.blend")


# ---------------------------------------------------------------- utilities


def args():
    argv = sys.argv
    return argv[argv.index("--") + 1 :] if "--" in argv else []


def get_arg(name, default=None):
    a = args()
    if name in a:
        i = a.index(name)
        return a[i + 1] if i + 1 < len(a) else default
    return default


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "EEVEE_NEXT" in [
        e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items
    ] else "BLENDER_EEVEE"
    sc.render.resolution_x = 1600
    sc.render.resolution_y = 1200
    sc.render.film_transparent = False
    sc.view_settings.view_transform = "AgX"
    world = bpy.data.worlds.new("W")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.045, 0.040, 0.035, 1)
    bg.inputs[1].default_value = 1.0


def mat(name, color, metallic=0.0, rough=0.4, alpha=1.0, emission=None):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, alpha)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = alpha
    if alpha < 1.0:
        m.blend_method = "BLEND"
    if emission:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1)
        bsdf.inputs["Emission Strength"].default_value = 1.0
    return m


def M():
    return {
        "alu": mat("M_Aluminium", (0.055, 0.051, 0.047), 0.88, 0.34),
        "gold": mat("M_Gold", (0.72, 0.50, 0.20), 1.0, 0.18),
        "chrome": mat("M_Chrome", (0.80, 0.78, 0.74), 1.0, 0.12),
        "dark": mat("M_Plastic_Dark", (0.028, 0.024, 0.021), 0.0, 0.45),
        "matte": mat("M_Plastic_Matte", (0.060, 0.054, 0.047), 0.0, 0.62),
        "glass": mat("M_Glass_Display", (0.012, 0.011, 0.010), 0.1, 0.08),
        "copper": mat("M_Copper", (0.40, 0.20, 0.09), 1.0, 0.38),
        "bean": mat("M_Bean", (0.055, 0.030, 0.014), 0.0, 0.55),
        "tint": mat("M_Tank_Tint", (0.52, 0.56, 0.58), 0.15, 0.10, alpha=0.30),
        "glow": mat("M_Display_Glow", (0.02, 0.02, 0.02), 0.0, 0.30, emission=(0.80, 0.48, 0.16)),
        "smoke": mat("M_Hopper_Smoke", (0.10, 0.09, 0.08), 0.4, 0.12, alpha=0.55),
    }


def set_material(obj, material):
    obj.data.materials.clear()
    obj.data.materials.append(material)


def bevel(obj, width=0.004, segments=4, angle=0.6):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    mod.angle_limit = angle
    mod.harden_normals = True
    return mod


def shade_smooth(obj, auto=math.radians(35)):
    """Сглаживание по углу: в Blender 4.1+ только через оператор."""
    prev = bpy.context.view_layer.objects.active
    for o in bpy.context.selected_objects:
        o.select_set(False)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    try:
        bpy.ops.object.shade_smooth_by_angle(angle=auto)
    except Exception:
        for p in obj.data.polygons:
            p.use_smooth = True
        if hasattr(obj.data, "use_auto_smooth"):
            obj.data.use_auto_smooth = True
            obj.data.auto_smooth_angle = auto
    obj.select_set(False)
    bpy.context.view_layer.objects.active = prev
    return obj


def box(name, size, loc=(0, 0, 0), rot=(0, 0, 0), material=None, bevel_w=0.004, parent=None):
    """Плита со скруглёнными рёбрами."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (size[0], size[1], size[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel_w:
        bevel(obj, bevel_w, 4)
    if material:
        set_material(obj, material)
    shade_smooth(obj)
    if parent:
        obj.parent = parent
    return obj


def rounded_rect_prism(name, w, h, depth, radius, loc=(0, 0, 0), rot=(0, 0, 0), material=None, parent=None):
    """Плита с закруглёнными углами в плоскости XZ, толщина по Y (как панель).

    Профиль строится в плоскости XY, затем поворот на 90° вокруг X.
    """
    r = min(radius, min(w, h) / 2 - 0.001)
    pts = []
    steps = 12
    corners = [
        (w / 2 - r, h / 2 - r, 0),
        (-(w / 2 - r), h / 2 - r, 90),
        (-(w / 2 - r), -(h / 2 - r), 180),
        (w / 2 - r, -(h / 2 - r), 270),
    ]
    for cx, cy, a0 in corners:
        for i in range(steps + 1):
            a = math.radians(a0 + 90 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))

    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    verts = [bm.verts.new((x, -depth / 2, y)) for x, y in pts]
    bm.verts.ensure_lookup_table()
    face = bm.faces.new(verts)
    r_ext = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [e for e in r_ext["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=moved, vec=(0, depth, 0))
    bm.faces.ensure_lookup_table()
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    bpy.context.view_layer.objects.active = obj
    bevel(obj, 0.0015, 3)
    if material:
        set_material(obj, material)
    shade_smooth(obj)
    if parent:
        obj.parent = parent
    return obj


def cylinder(name, radius, depth, loc=(0, 0, 0), rot=(0, 0, 0), material=None, verts=64, parent=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    bevel(obj, min(0.0015, depth / 4), 2)
    if material:
        set_material(obj, material)
    shade_smooth(obj)
    if parent:
        obj.parent = parent
    return obj


def empty(name, loc=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.02
    obj.location = loc
    bpy.context.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


# ---------------------------------------------------------------- stage 1


def stage1(mats):
    root = empty("Machine_Root")
    shell = empty("Shell", parent=root)

    body_w, body_d, body_h = W, D, H
    body = rounded_rect_prism(
        "Body_Main",
        body_w,
        body_h - 0.016,
        body_d,
        0.020,
        loc=(0, 0, body_h / 2 - 0.008),
        material=mats["alu"],
        parent=shell,
    )
    body.scale = (1, 1, 1)
    # Скруглённая крышка сверху — даёт мягкий силуэт вместо кирпича.
    rounded_rect_prism(
        "Body_Crown",
        body_w - 0.002,
        0.026,
        body_d - 0.002,
        0.012,
        loc=(0, 0, body_h - 0.006),
        material=mats["alu"],
        parent=shell,
    )

    # Внутренняя выборка: видно нутро, когда панели сняты.
    inner = box("Body_Core", (body_w - 0.03, body_d - 0.05, body_h - 0.05), loc=(0, -0.01, body_h / 2), material=mats["dark"], bevel_w=0.004, parent=shell)
    inner.hide_render = False

    # Щёки: чуть уже корпуса, с зазором 1.2 мм.
    for side, x in (("Left", -(body_w / 2)), ("Right", body_w / 2)):
        p = box(
            f"Panel_{side}",
            (0.012, body_d - 0.024, body_h - 0.03),
            loc=(x + (0.004 if side == "Left" else -0.004), 0, body_h / 2),
            material=mats["alu"],
            bevel_w=0.004,
            parent=shell,
        )
        p.rotation_euler[1] = math.radians(1.2 if side == "Left" else -1.2)

    # Лицевая золотая панель: втоплена на 4 мм, по контуру остаётся кожух.
    rounded_rect_prism(
        "Panel_Front",
        W - 0.030,
        H - 0.048,
        0.014,
        0.020,
        loc=(0, -body_d / 2 - 0.001, H / 2 - 0.004),
        material=mats["gold"],
        parent=root,
    )

    # Верхняя площадка подогрева.
    box("Panel_Top", (W + 0.002, D - 0.018, 0.008), loc=(0, 0, H + 0.009), material=mats["alu"], bevel_w=0.003, parent=shell)
    for i in range(3):
        box(
            "Grille_Top",
            (W - 0.070, 0.005, 0.005),
            loc=(0, -0.120 + i * 0.105, H + 0.0135),
            material=mats["gold"],
            bevel_w=0.002,
            parent=shell,
        )

    # Плинтус.
    box("Base_Plinth", (W + 0.006, D - 0.004, 0.012), loc=(0, 0, 0.006), material=mats["gold"], bevel_w=0.003, parent=shell)

    # Шильдик на лицевой панели снизу.
    box("Badge", (0.036, 0.002, 0.008), loc=(0, -body_d / 2 - 0.008, 0.022), material=mats["chrome"], bevel_w=0.001, parent=root)

    # Заглушка дисплея не нужна: на этапе 2 строится Control_Panel.

    return root


# ---------------------------------------------------------------- camera / lights


def studio(target=(0, 0, 0.17)):
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 85
    cam = bpy.data.objects.new("Cam", cam_data)
    cam.location = (0.86, -1.62, 0.58)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam

    track = cam.constraints.new("TRACK_TO")
    emp = empty("Cam_Target", loc=target)
    track.target = emp
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"

    def area(name, loc, rot, size, power, color):
        d = bpy.data.lights.new(name, "AREA")
        d.shape = "RECTANGLE"
        d.size, d.size_y = size
        d.energy = power
        d.color = color
        o = bpy.data.objects.new(name, d)
        o.location = loc
        o.rotation_euler = rot
        bpy.context.collection.objects.link(o)
        return o

    area("Key", (0.45, -0.55, 0.62), (math.radians(48), 0, math.radians(38)), (0.7, 0.5), 90, (1.0, 0.92, 0.82))
    area("Fill", (-0.55, -0.35, 0.28), (math.radians(78), 0, math.radians(-58)), (0.9, 0.7), 22, (0.85, 0.80, 0.72))
    area("Rim", (0.0, 0.55, 0.45), (math.radians(120), 0, 0), (0.8, 0.3), 60, (0.95, 0.90, 0.85))

    # Тёмный стол, чтобы машина стояла на поверхности.
    box("Ground", (1.6, 1.6, 0.008), loc=(0, 0, -0.004), material=mat("M_Ground", (0.055, 0.040, 0.028), 0.0, 0.5), bevel_w=0.001)
    return cam


def render(path, transparent=False, size=None):
    sc = bpy.context.scene
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGBA" if transparent else "RGB"
    sc.render.film_transparent = transparent
    if size:
        sc.render.resolution_x, sc.render.resolution_y = size
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------- stage 2

FRONT = -D / 2


def control_panel(mats, root):
    """Лицевая панель: дисплей, две кнопки, ряд клавиш."""
    g = empty("Control_Panel", parent=root)

    # Дисплей: хромированная рамка, внутри стекло.
    rounded_rect_prism(
        "Display_Frame", 0.056, 0.070, 0.004, 0.009,
        loc=(-0.046, FRONT - 0.012, 0.212), material=mats["chrome"], parent=g,
    )
    rounded_rect_prism(
        "Display_Glass", 0.049, 0.062, 0.003, 0.008,
        loc=(-0.046, FRONT - 0.015, 0.212), material=mats["glass"], parent=g,
    )
    rounded_rect_prism(
        "Display_Glow", 0.034, 0.013, 0.001, 0.004,
        loc=(-0.046, FRONT - 0.017, 0.216), material=mats["glow"], parent=g,
    )

    # Две круглые кнопки.
    for i, x in enumerate((-0.008, 0.034)):
        cylinder(
            f"Button_{i + 1}", 0.011, 0.010,
            loc=(x + 0.026, FRONT - 0.014, 0.262),
            rot=(math.radians(90), 0, 0), material=mats["chrome"], parent=g,
        )
        cylinder(
            f"Button_{i + 1}_Cap", 0.0075, 0.004,
            loc=(x + 0.026, FRONT - 0.019, 0.262),
            rot=(math.radians(90), 0, 0), material=mats["dark"], parent=g,
        )

    # Ряд клавиш под дисплеем.
    for i in range(3):
        box(
            f"Key_{i + 1}", (0.026, 0.008, 0.012),
            loc=(-0.070 + i * 0.030, FRONT - 0.012, 0.104),
            material=mats["gold"], bevel_w=0.0015, parent=g,
        )
    return g


def group_head(mats, root):
    """Варочная группа: корпус, кольцо, носик, держатель фильтра."""
    g = empty("Group_Head", parent=root)
    box(
        "Group_Housing", (0.082, 0.072, 0.086),
        loc=(0.030, FRONT - 0.030, 0.150),
        material=mats["gold"], bevel_w=0.010, parent=g,
    )
    cylinder(
        "Group_Ring", 0.036, 0.014,
        loc=(0.030, FRONT - 0.074, 0.150),
        rot=(math.radians(90), 0, 0), material=mats["chrome"], parent=g,
    )
    cylinder(
        "Group_Spout", 0.014, 0.020,
        loc=(0.030, FRONT - 0.086, 0.120),
        rot=(math.radians(90), 0, 0), material=mats["gold"], parent=g,
    )
    # Рукоятка сверху группы.
    box(
        "Group_Lever", (0.012, 0.062, 0.012),
        loc=(0.030, FRONT - 0.030, 0.196),
        material=mats["chrome"], bevel_w=0.004, parent=g,
    )

    pf = empty("Portafilter", parent=root)
    cylinder(
        "Portafilter_Cup", 0.040, 0.022,
        loc=(0.030, FRONT - 0.088, 0.146),
        rot=(math.radians(90), 0, 0), material=mats["chrome"], parent=pf,
    )
    cylinder(
        "Portafilter_Neck", 0.010, 0.016,
        loc=(0.030, FRONT - 0.104, 0.140),
        rot=(math.radians(90), 0, 0), material=mats["chrome"], parent=pf,
    )
    handle = cylinder(
        "Portafilter_Handle", 0.011, 0.090,
        loc=(0.034, FRONT - 0.152, 0.108),
        material=mats["dark"], parent=pf,
    )
    handle.rotation_euler = (math.radians(28), 0, math.radians(6))
    return g, pf


def steam_wand(mats, root):
    g = empty("Steam_Wand", parent=root)
    cylinder(
        "Wand_Tube", 0.007, 0.135,
        loc=(0.124, FRONT + 0.050, 0.185),
        rot=(math.radians(10), 0, math.radians(-8)), material=mats["chrome"], parent=g,
    )
    cylinder(
        "Wand_Joint", 0.014, 0.020,
        loc=(0.116, FRONT + 0.030, 0.250), material=mats["chrome"], parent=g,
    )
    cylinder(
        "Wand_Tip", 0.009, 0.018,
        loc=(0.128, FRONT + 0.078, 0.115), material=mats["dark"], parent=g,
    )
    return g


def drip_tray(mats, root):
    g = empty("Drip_Tray", parent=root)
    rounded_rect_prism(
        "Tray_Body", 0.170, 0.110, 0.016, 0.010,
        loc=(0, FRONT + 0.010, 0.022), material=mats["chrome"], parent=g,
    )
    rounded_rect_prism(
        "Tray_Well", 0.150, 0.090, 0.004, 0.008,
        loc=(0, FRONT + 0.010, 0.031), material=mats["dark"], parent=g,
    )
    for i in range(5):
        box(
            f"Tray_Grate_{i + 1}", (0.140, 0.008, 0.004),
            loc=(0, FRONT - 0.028 + i * 0.019, 0.034),
            material=mats["gold"], bevel_w=0.0015, parent=g,
        )
    return g


def bean_hopper(mats, root):
    g = empty("Bean_Hopper", parent=root)
    cylinder("Hopper_Collar", 0.054, 0.012, loc=(0, 0.130, 0.346), material=mats["dark"], parent=g)
    cylinder("Hopper_Body", 0.046, 0.100, loc=(0, 0.130, 0.402), material=mats["smoke"], parent=g)
    cylinder("Hopper_Ring", 0.049, 0.008, loc=(0, 0.130, 0.455), material=mats["chrome"], parent=g)
    cylinder("Hopper_Lid", 0.050, 0.014, loc=(0, 0.130, 0.464), material=mats["dark"], parent=g)
    cylinder("Hopper_Knob", 0.009, 0.012, loc=(0, 0.130, 0.476), material=mats["gold"], parent=g)
    return g


def water_tank(mats, root):
    g = empty("Water_Tank", parent=root)
    rounded_rect_prism(
        "Tank_Body", 0.150, 0.240, 0.090, 0.014,
        loc=(0, 0.150, 0.140), material=mats["tint"], parent=g,
    )
    rounded_rect_prism(
        "Tank_Cap", 0.120, 0.030, 0.020, 0.008,
        loc=(0, 0.150, 0.272), material=mats["chrome"], parent=g,
    )
    return g


# ---------------------------------------------------------------- stage 3


def internals(mats, root):
    bu = empty("Brewing_Unit", parent=root)
    cylinder("Brew_Chamber", 0.036, 0.070, loc=(0.030, -0.060, 0.148), material=mats["chrome"], parent=bu)
    box("Brew_Block", (0.070, 0.056, 0.050), loc=(0.030, -0.020, 0.148), material=mats["dark"], bevel_w=0.006, parent=bu)
    cylinder("Brew_Piston", 0.022, 0.040, loc=(0.030, -0.060, 0.198), material=mats["chrome"], parent=bu)

    boiler = empty("Boiler", parent=root)
    cylinder("Boiler_Body", 0.046, 0.150, loc=(-0.052, 0.040, 0.210), material=mats["copper"], parent=boiler)
    cylinder("Boiler_Face", 0.048, 0.012, loc=(-0.052, 0.040, 0.286), material=mats["chrome"], parent=boiler)
    cylinder("Boiler_Pipe", 0.009, 0.090, loc=(-0.052, 0.040, 0.120), material=mats["chrome"], parent=boiler)

    pump = empty("Pump", parent=root)
    cylinder("Pump_Body", 0.020, 0.070, loc=(-0.070, -0.090, 0.070), material=mats["dark"], parent=pump)
    cylinder("Pump_Motor", 0.024, 0.030, loc=(-0.070, -0.090, 0.110), material=mats["chrome"], parent=pump)

    grinder = empty("Grinder", parent=root)
    cylinder("Grinder_Cones", 0.032, 0.050, loc=(0, 0.120, 0.316), material=mats["chrome"], parent=grinder)
    cylinder("Grinder_Motor", 0.028, 0.060, loc=(0, 0.120, 0.262), material=mats["dark"], parent=grinder)
    return bu, boiler, pump, grinder


# ---------------------------------------------------------------- stage 4

EXPLODE = {
    "Panel_Left": (-0.21, 0, 0),
    "Panel_Right": (0.21, 0, 0),
    "Panel_Top": (0, 0.03, 0.17),
    "Panel_Front": (-0.02, -0.10, 0.26),
    "Control_Panel": (-0.22, -0.08, 0.18),
    "Group_Head": (0.10, -0.12, 0.26),
    "Portafilter": (0.26, -0.06, 0.20),
    "Steam_Wand": (0.30, -0.02, 0.06),
    "Bean_Hopper": (0.06, 0.08, 0.22),
    "Water_Tank": (0, 0.28, 0.02),
    "Drip_Tray": (0.02, -0.06, -0.22),
    "Brewing_Unit": (0.07, 0.06, -0.08),
    "Boiler": (-0.17, 0.05, 0.03),
    "Pump": (-0.16, 0.05, -0.09),
    "Grinder": (0.09, 0.13, 0.15),
    "Shell": (0, 0, 0),
}


def explode(root):
    for o in root.children_recursive:
        vec = EXPLODE.get(o.name)
        if vec is not None:
            o["explode"] = list(vec)
    return EXPLODE


# ---------------------------------------------------------------- stage 5


def export_glb(root):
    bpy.ops.object.select_all(action="DESELECT")
    root.select_set(True)
    for o in root.children_recursive:
        o.select_set(True)
    path = os.path.join(ROOT, "public", "model", "machine.glb")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_extras=True,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_materials="EXPORT",
    )
    return path


# ---------------------------------------------------------------- main


def main():
    stage = int(get_arg("--stage", "1"))
    reset_scene()
    mats = M()
    root = stage1(mats)

    if stage >= 2:
        control_panel(mats, root)
        group_head(mats, root)
        steam_wand(mats, root)
        drip_tray(mats, root)
        bean_hopper(mats, root)
        water_tank(mats, root)
    if stage >= 3:
        internals(mats, root)
    if stage >= 4:
        explode(root)

    studio()
    os.makedirs(PICS, exist_ok=True)
    os.makedirs(os.path.dirname(BLEND), exist_ok=True)
    render(os.path.join(PICS, f"model-stage{stage}.png"))
    if stage >= 5:
        # Прозрачный кадр для статичного постера в секции «Анатомия».
        os.makedirs(os.path.join(ROOT, "public", "img"), exist_ok=True)
        ground = bpy.data.objects.get("Ground")
        if ground:
            ground.hide_render = True
        render(os.path.join(ROOT, "public", "img", "model-still.png"), transparent=True, size=(1200, 1200))
        if ground:
            ground.hide_render = False

    glb = export_glb(root) if stage >= 5 else None
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)

    data = []
    for o in bpy.data.objects:
        if o.type == "MESH":
            data.append(
                {
                    "name": o.name,
                    "loc": [round(v, 4) for v in o.location],
                    "dims": [round(v, 4) for v in o.dimensions],
                    "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                }
            )
    print("BLENDER_OK " + json.dumps({"stage": stage, "objects": data}))


main()
