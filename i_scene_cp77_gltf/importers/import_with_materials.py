import bpy
import os
import re
import json
import time
import traceback

from io_scene_gltf2.io.imp.gltf2_io_gltf import glTFImporter
vers = bpy.app.version
if vers[0] == 4 and vers[1] < 3:
    from io_scene_gltf2.blender.imp.gltf2_blender_gltf import BlenderGlTF
else:
    from io_scene_gltf2.blender.imp.blender_gltf import BlenderGlTF

from ..main.setup import MaterialBuilder
from ..main.bartmoss_functions import UV_by_bounds, get_safe_mode, safe_mode_switch
from .import_from_external import *
from .attribute_import import manage_garment_support
from ..jsontool import JSONTool
from ..main.common import show_message
from .anim_import import get_anim_info # animation handling moved to its own module to make space for float tracks etc...

def objs_in_col(top_coll, objtype):
    return sum(len([o for o in col.objects if o.type == objtype]) for col in top_coll.children_recursive) + \
           len([o for o in top_coll.objects if o.type == objtype])

def disable_collection_by_name(collection_name: str):
    """Hide (exclude) the given collection in all view layers (Blender doesn’t expose true 'collapse')."""
    for vl in bpy.context.scene.view_layers:
        for l in vl.layer_collection.children:
            if l.name.lower() == collection_name.lower():
                l.exclude = True

def make_gltf_importer_kwargs(heuristic, octos):
    """
    Build glTF importer kwargs once, and add to them based on blender version.
    """
    vmaj, vmin = bpy.app.version[0], bpy.app.version[1]
    kwargs = {
        "files": None,
        "loglevel": 0,
        "import_pack_images": True,
        "merge_vertices": False,
        "import_shading": "NORMALS",
        "bone_heuristic": heuristic,
        "guess_original_bind_pose": False,
        "import_user_extensions": "",
        "disable_bone_shape": octos,
        "bone_shape_scale_factor": 1.0,
    }
   # 4.2–4.3: base options only
    if vmaj == 4 and 2 <= vmin < 4:
        return kwargs
    # 4.4 only
    if vmaj == 4 and vmin == 4:
        kwargs.update({
            "import_scene_extras": True,
            "import_select_created_objects": True,
        })
        return kwargs
    # 4.5+: add newer flags
    if vmaj == 4 and vmin >= 5:
        kwargs.update({
            "import_unused_materials": False,
            "import_scene_as_collection": True,
            "import_scene_extras": True,
            "import_select_created_objects": True,
            "import_merge_material_slots": False,
        })
        return kwargs
    # Fallback (pre-4 or other variants): mimic add-on selecting created objects
    kwargs.update({"import_select_created_objects": True})
    return kwargs

def CP77GLBimport(
    with_materials=False,
    remap_depot=False,
    exclude_unused_mats=True,
    image_format='png',
    filepath='',
    hide_armatures=True,
    import_garmentsupport=False,
    files=None,
    directory='',
    appearances=None,
    scripting=False
    ):
    """
    Top-level GLB/GLTF import entrypoint for CP77 assets. Moves anim import to its own module,
    adds safer object capture, per-file scoping, and error aggregation while maintaining compatibility with existing calls
    """
    if appearances is None:
        appearances = []
    if files is None:
        files = []

    cp77_addon_prefs = bpy.context.preferences.addons['i_scene_cp77_gltf'].preferences
    context = bpy.context

    if get_safe_mode() != 'OBJECT':
        safe_mode_switch('OBJECT')

    start_time = time.time()

    # Resolve file list
    if not scripting:
        loadfiles = files
    else:
        f = {'name': os.path.basename(filepath)}
        loadfiles = (f,)
    glbname = os.path.basename(filepath)
    

    if not cp77_addon_prefs.non_verbose:
        if ".anims.glb" in filepath:
            print('\n-------------------- Beginning Cyberpunk Animation Import --------------------')
            print(f"Importing Animations From: {glbname}")
        else:
            print('\n-------------------- Beginning Cyberpunk Model Import --------------------')
            if with_materials:
                print(f"Importing: {glbname} with materials")
                print(f"Appearances to Import: {appearances}")
            else:
                print(f"Importing: {glbname}")

    # Prevent crash if no directory supplied when using filepath
    if not directory or scripting:
        directory = os.path.dirname(filepath)

    heuristic = 'TEMPERANCE' if getattr(cp77_addon_prefs, 'enable_temperance', False) else 'BLENDER'
    octos = bool(getattr(cp77_addon_prefs, 'enable_octo', False))

    kwargs = make_gltf_importer_kwargs(heuristic, octos)
    
    errorMessages = []
    JSONTool.start_caching()
    try:
        for f in loadfiles:
            filename = os.path.splitext(os.path.splitext(f['name'])[0])[0]
            fpath = os.path.join(directory, f['name'])
            current_file_base_path = os.path.join(os.path.dirname(fpath), filename)
            has_material_json = os.path.exists(current_file_base_path + ".Material.json")

            # Snapshot per file (views are dynamic; freeze them)
            existingMeshes = set(bpy.data.meshes.keys())
            existingMaterials = set(bpy.data.materials.keys())

            gltf_importer = glTFImporter(fpath, kwargs)
            gltf_importer.read()
            gltf_importer.checks()

            # capture imported objects
            pre_names = set(bpy.data.objects.keys())
            BlenderGlTF.create(gltf_importer)
            imported = list(context.selected_objects)
            if not imported:
                post_names = set(bpy.data.objects.keys())
                new_names = sorted(list(post_names - pre_names))
                imported = [bpy.data.objects[n] for n in new_names if n in bpy.data.objects]

            # External vs CP77 export heuristics
            imported_meshes = [obj for obj in imported if obj.type == "MESH"]
            imported_empties = [obj for obj in imported if obj.type == "EMPTY"]
            isExternalImport = (
                len(imported_empties) > 0 or
                len([m.name for m in imported_meshes if m.name.startswith("submesh")]) != len(imported_meshes)
            )

            multimesh = False
            meshcount = 0
            for obj in imported:
                if obj.type == 'MESH' and obj.name.startswith(str(meshcount) + "_"):
                    multimesh = True
                    meshcount += 1
                elif obj.type == 'MESH':
                    multimesh = False
                    meshcount += 1
                else:
                    multimesh = False
                    exclude_unused_mats = False

            if multimesh:
                isExternalImport = False

            if isExternalImport:
                CP77_cleanup_external_export(imported)

            # Terrain helper
            if f['name'][:7] == 'terrain':
                UV_by_bounds(imported)

            # Create a per-file collection; link objects and handle anims/armature visibility
            collection = bpy.data.collections.new(filename)
            bpy.context.scene.collection.children.link(collection)

            # If animations exist, set FPS once and attach anim metadata
            animations = getattr(gltf_importer.data, 'animations', None)
            meshes = getattr(gltf_importer.data, 'meshes', None)
            if animations:
                get_anim_info(animations)
                bpy.context.scene.render.fps = 30

            # Link each imported object to the collection and optionally hide armatures
            for o in imported:
                # move object into our collection
                for parent in tuple(o.users_collection):
                    parent.objects.unlink(o)
                collection.objects.link(o)
                # if no animations, optionally hide armatures in this import
                if not animations and meshes and ('Armature' in o.name):
                    o.hide_set(hide_armatures)

            # Tag collection metadata
            collection['orig_filepath'] = fpath
            collection['numMeshChildren'] = objs_in_col(collection, 'MESH')
            collection['numArmatureChildren'] = objs_in_col(collection, 'ARMATURE')

            disable_collection_by_name("glTF_not_exported")

            # For non-external imports, prune only newly-created, unused materials
            if not isExternalImport:
                for name in [n for n in bpy.data.materials.keys() if n not in existingMaterials]:
                    mat = bpy.data.materials.get(name)
                    if mat and mat.users == 0:
                        bpy.data.materials.remove(mat, do_unlink=True, do_id_user=True, do_ui_user=True)

            # Blender 4 bone display scale (no-op before 4.x)
            blender_4_scale_armature_bones()

            # Pure animation GLBs: stop here
            if ".anims.glb" in fpath:
                continue

            # Materials path defaults
            DepotPath = None
            json_apps = {}

            if with_materials and has_material_json:
                try:
                    DepotPath, json_apps, mats = JSONTool.jsonload(current_file_base_path + ".Material.json", errorMessages)
                except Exception as e:
                    errorMessages.append(f"Material.json read failed for '{filename}': {e}")

            # Remap depot if requested and available
            if remap_depot and os.path.exists(cp77_addon_prefs.depotfolder_path):
                DepotPath = cp77_addon_prefs.depotfolder_path
                if not cp77_addon_prefs.non_verbose:
                    print(f"Using depot path: {DepotPath}")
            if DepotPath is not None:
                DepotPath = DepotPath.replace('\\', os.sep)

            # Garment support attributes (before materials)
            if import_garmentsupport:
                manage_garment_support(existingMeshes, gltf_importer)

            # No material import requested
            if not with_materials:
                continue

            # If we still don't have a depot, skip material import
            if DepotPath is None:
                print(f"Failed to read DepotPath, skipping material import (hasMaterialJson: {has_material_json})")
                continue

            # Build valid material list from appearances
            validmats = {}
            if len(json_apps) > 0:
                # Normalize app keys: strip any trailing digits (e.g., "Default01" -> "Default")
                appkeys = list(json_apps.keys())
                for k in appkeys:
                    norm = re.sub(r'\d+$', '', k)
                    if norm != k and norm not in json_apps:
                        json_apps[norm] = json_apps.pop(k)

                # Save normalized apps dictionary for later reuse
                collection['json_apps'] = json.dumps(json_apps)

                if appearances and 'ALL' not in appearances:
                    if 'Default' in appearances:
                        first_key = next(iter(json_apps))
                        for m in json_apps[first_key]:
                            validmats[m] = True
                    else:
                        for key in json_apps.keys():
                            if key in appearances:
                                for m in json_apps[key]:
                                    validmats[m] = True
                # Fallback: include everything
                if len(validmats) == 0:
                    for key in json_apps.keys():
                        for m in json_apps[key]:
                            validmats[m] = True

            # Create/assign materials
            try:
                import_mats(current_file_base_path, DepotPath, exclude_unused_mats, existingMeshes,
                            gltf_importer, image_format, mats if len(json_apps) > 0 else [],
                            validmats, multimesh)
            except Exception:
                errorMessages.append(traceback.format_exc())

    finally:
        JSONTool.stop_caching()

    if len(errorMessages) > 0:
        show_message("\n".join(errorMessages))

    if not cp77_addon_prefs.non_verbose:
        print(f"GLB Import Time: {(time.time() - start_time)} Seconds")
        print('-------------------- Finished importing Cyberpunk 2077 Model --------------------\n')

def reload_mats():
    active_obj = bpy.context.active_object
    if not active_obj or not active_obj.material_slots:
        show_message("No active object/material to reload.")
        return

    mat_idx = active_obj.active_material_index
    if mat_idx >= len(active_obj.material_slots) or not active_obj.material_slots[mat_idx].material:
        show_message("Active slot has no material.")
        return

    mat = active_obj.material_slots[mat_idx].material
    old_mat_name = mat.name

    DepotPath = mat.get('DepotPath')
    BasePath = mat.get('MeshPath')
    if not BasePath:
        show_message("Material has no 'MeshPath' to locate .Material.json")
        return

    errorMessages = []
    matjsonpath = BasePath + ".Material.json"
    image_format = 'png'

    JSONTool.start_caching()
    try:
        _, _, mats = JSONTool.jsonload(matjsonpath, errorMessages)
        Builder = MaterialBuilder(mats, DepotPath, str(image_format), BasePath)

        newmat = None
        for idx, rawmat in enumerate(mats):
            if rawmat.get("Name") == old_mat_name:
                newmat = Builder.create(mats, idx)
                break

        if not newmat:
            show_message(f"Material '{old_mat_name}' not found in {matjsonpath}")
            return

        # Remap all users of old material to the new one
        bpy.data.materials[old_mat_name].user_remap(bpy.data.materials[newmat.name])

        # Copy custom properties
        for k in mat.keys():
            newmat[k] = mat[k]

        # Remove the old material
        if mat:
            bpy.data.materials.remove(mat, do_unlink=True, do_id_user=True, do_ui_user=True)

        newmat.name = old_mat_name

    finally:
        JSONTool.stop_caching()

    if len(errorMessages) > 0:
        show_message("\n".join(errorMessages))

def import_mats(BasePath, DepotPath, exclude_unused_mats, existingMeshes, gltf_importer, image_format, mats, validmats, multimesh=False):
    failedon = []
    cp77_addon_prefs = bpy.context.preferences.addons['i_scene_cp77_gltf'].preferences
    start_time = time.time()

    # Expand validmats with metadata for quick comparisons
    for mat in list(validmats.keys()):
        for m in mats:
            if m.get('Name') != mat:
                continue
            data = m.get('Data', {})
            validmats[mat] = {
                'Name': m['Name'],
                'BaseMaterial': m.get('BaseMaterial'),
                'GlobalNormal': data.get('GlobalNormal', 'None'),
                'MultilayerMask': data.get('MultilayerMask', 'None'),
                'DiffuseMap': data.get('DiffuseMap', 'None')
            }
            break

    MatImportList = [k for k in validmats.keys()]
    Builder = MaterialBuilder(mats, DepotPath, str(image_format), BasePath)
    counter = 0
    bpy_mats = bpy.data.materials

    # Only meshes created by this import pass
    existingMeshes = set(existingMeshes)
    names = [key for key in bpy.data.meshes.keys() if 'Icosphere' not in key and key not in existingMeshes]
    if multimesh:
        try:
            names = sorted(list(names), key=lambda x: int(x.split('_')[0]))
        except Exception:
            pass

    for name in names:
        bpy.data.meshes[name].materials.clear()

        # Use the glTF extras to determine intended materials per submesh
        extras = None
        try:
            extras = gltf_importer.data.meshes[counter].extras
        except Exception:
            extras = None

        # Morph targets or missing extras: either attach all validmats (for morphtarget)
        # or skip if we can't determine materials for this mesh
        if extras is None or ("materialNames" not in extras or extras["materialNames"] is None):
            if BasePath.endswith(".morphtarget"):
                materialNames = list(validmats.keys())
            else:
                counter += 1
                continue
        else:
            materialNames = list(dict.fromkeys(extras["materialNames"]))  # dedupe

        for matname in materialNames:
            if matname not in validmats:
                continue

            meta = validmats[matname]

            # Reuse if an equivalent material already exists
            if matname in bpy_mats.keys():
                bm = bpy_mats[matname]
                try:
                    if (
                        'glass' not in matname and 'MaterialTemplate' not in matname and 'Window' not in matname
                        and not matname.startswith('Atlas') and 'decal_diffuse' not in matname
                        and bm.get('BaseMaterial') == meta['BaseMaterial']
                        and bm.get('GlobalNormal') == meta['GlobalNormal']
                        and bm.get('MultilayerMask') == meta['MultilayerMask']
                    ):
                        bpy.data.meshes[name].materials.append(bm)
                        continue
                    if matname.startswith('Atlas') and bm.get('BaseMaterial') == meta['BaseMaterial'] and bm.get('DiffuseMap') == meta['DiffuseMap']:
                        bpy.data.meshes[name].materials.append(bm)
                        continue
                    if matname == 'decal_diffuse' and bm.get('BaseMaterial') == meta['BaseMaterial'] and bm.get('DiffuseTexture') == meta.get('DiffuseTexture'):
                        bpy.data.meshes[name].materials.append(bm)
                        continue
                except Exception:
                    pass

            # Build new material from material.json
            idx = None
            for i, rawmat in enumerate(mats):
                if rawmat.get("Name") == matname:
                    idx = i
                    break

            if idx is None:
                failedon.append(matname)
                continue

            try:
                bpymat = Builder.create(mats, idx)
                if bpymat:
                    bpymat['BaseMaterial'] = meta['BaseMaterial']
                    bpymat['GlobalNormal'] = meta['GlobalNormal']
                    bpymat['MultilayerMask'] = meta['MultilayerMask']
                    bpymat['DiffuseMap'] = meta['DiffuseMap']
                    bpy.data.meshes[name].materials.append(bpymat)
                    obj = bpy.data.objects.get(name)
                    if obj and hasattr(obj, "visible_shadow") and bpymat.get('no_shadows', False):
                        obj.visible_shadow = False
            except Exception:
                print(traceback.print_exc())
                failedon.append(matname)

        counter += 1

    if not cp77_addon_prefs.non_verbose:
        if len(failedon) == 0:
            print(f'Shader Setup Completed Successfully in {(time.time() - start_time)} Seconds')
        else:
            line_separator = '\n    '
            print(f'Material Setup Failed on: {line_separator}{line_separator.join(failedon)}')
            print(f'Attempted Setup for {(time.time() - start_time)} seconds')

def blender_4_scale_armature_bones():
    vers = bpy.app.version
    if vers[0] >= 4:
        arms = [obj for obj in bpy.data.objects if obj.type == 'ARMATURE' and 'Armature' in obj.name]
        for arm in arms:
            for pb in arm.pose.bones:
                pb.custom_shape_scale_xyz[0] = .0175
                pb.custom_shape_scale_xyz[1] = .0175
                pb.custom_shape_scale_xyz[2] = .0175
                pb.use_custom_shape_bone_size = True
