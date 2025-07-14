import time
import traceback
import bpy
import json
import math
from mathutils import Vector, Quaternion, Matrix
from ..main.common import loc, show_message
from ..jsontool import JSONTool
from ..cyber_props import CP77animBones
from ..main.bartmoss_functions import *

def convert_matrix_from_game_to_blender(mat):
    # Mirror X to change handedness (REDengine → Blender)
    mirror_x = Matrix.Scale(-1, 4, Vector((1, 0, 0)))
    return mirror_x @ mat @ mirror_x

def apply_bone_from_matrix(bone, mat, length=0.01):
    head = mat.to_translation()
    y_axis = mat.to_3x3() @ Vector((0, length, 0))
    tail = head + y_axis
    bone.head = head
    bone.tail = tail

    # Optional: align bone roll to X axis of matrix
    x_axis = mat.to_3x3() @ Vector((1, 0, 0))
    bone.align_roll(x_axis)

def compute_global_transform(index, transforms, parents, global_transforms):
    if index in global_transforms:
        return global_transforms[index]

    local_translation = Vector((
        transforms[index]["Translation"]["X"],
        transforms[index]["Translation"]["Y"],
        transforms[index]["Translation"]["Z"]
    ))        
    local_rotation = Quaternion((
        transforms[index]["Rotation"]["r"],        
        transforms[index]["Rotation"]["i"],
        transforms[index]["Rotation"]["j"],
        transforms[index]["Rotation"]["k"]

    ))
    local_scale = Vector((
        transforms[index]["Scale"]["X"],
        transforms[index]["Scale"]["Y"],
        transforms[index]["Scale"]["Z"]
    ))

    local_mat = Matrix.Translation(local_translation) @ local_rotation.to_matrix().to_4x4() @ Matrix.Diagonal(local_scale).to_4x4()

    if parents[index] == -1:
        global_transforms[index] = local_mat
    else:
        parent_mat = compute_global_transform(parents[index], transforms, parents, global_transforms)
        global_transforms[index] = parent_mat @ local_mat

    return global_transforms[index]

def build_apose_matrices(apose_ms, apose_ls, bone_names, bone_parents):
    if apose_ms:
        def build_matrix(pose):
            T = Vector([pose["Translation"]["X"], pose["Translation"]["Y"], pose["Translation"]["Z"]])
            Q = Quaternion([pose["Rotation"]["r"], pose["Rotation"]["i"], pose["Rotation"]["j"], pose["Rotation"]["k"]])
            S = Vector([pose["Scale"]["X"], pose["Scale"]["Y"], pose["Scale"]["Z"]])
            return Matrix.Translation(T) @ Q.to_matrix().to_4x4() @ Matrix.Diagonal(S).to_4x4()
        return [build_matrix(p) for p in apose_ms]
    elif apose_ls:
        global_poses = {}
        for i in range(len(bone_names)):
            global_poses[i] = convert_matrix_from_game_to_blender(compute_global_transform(i, apose_ls, bone_parents, global_poses))
        return [global_poses[i] for i in range(len(bone_names))]
    return None

def create_bone_shape():
    shape = bpy.data.objects.get("BoneCustomShape")
    if shape is None:
        current_mode = get_safe_mode()
        if current_mode != 'OBJECT':
            safe_mode_switch("OBJECT")
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_ico_sphere_add(radius=1.0, enter_editmode=False)
        shape = bpy.context.active_object
        shape.name = "BoneCustomShape"
        bpy.ops.object.shade_smooth()

    # Make sure it's linked to the view layer
    if shape.name not in bpy.context.view_layer.objects:
        bpy.context.collection.objects.link(shape)

    shape.hide_viewport = True
    shape.hide_render = True
    try:
        shape.hide_set(True)
    except RuntimeError as e:
        print(f"[create_bone_shape] Warning: Could not hide object: {e}")

    shape.select_set(False)
    return shape

def assign_bone_shapes(arm, disable_connect, shape=None):
    anim_bones = CP77animBones()
    if shape is None or not isinstance(shape, bpy.types.Object):
        shape = create_bone_shape()

    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='POSE')

    for pb in arm.pose.bones:
        name = pb.name
        use_shape = (
            disable_connect or
            name not in anim_bones or
            name.endswith("JNT") or
            name.endswith("GRP") or
            name.endswith("IK")
        )
        if use_shape:
            pb.custom_shape = shape
            if disable_connect:
                pb.custom_shape_scale_xyz = Vector((0.05, 0.05, 0.05))
                pb.use_custom_shape_bone_size = False
            elif name not in anim_bones:
                pb.custom_shape_scale_xyz = Vector((0.1, 0.1, 0.1))
            else:
                pb.custom_shape_scale_xyz = Vector((0.05, 0.05, 0.05))
        else:
            pb.custom_shape = None

def assign_part_groups(arm_obj, parts):
    if not parts or not isinstance(parts, list):
        return  # Nothing to do

    arm_data = arm_obj.data

    # Ensure object is visible and selectable
    arm_obj.hide_set(False)
    arm_obj.hide_viewport = False
    arm_obj.hide_render = False
    arm_obj.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj

    # Detect current mode so we can restore it later
    current_mode = get_safe_mode()
    target_layer = arm_data.bones if current_mode != 'POSE' else arm_obj.pose.bones

    if current_mode == 'OBJECT':
        safe_mode_switch("EDIT")
        target_layer = arm_data.edit_bones
    elif current_mode == 'EDIT':
        target_layer = arm_data.edit_bones

    def collect_root_bones(tree):
        bones = []
        root_entry = tree.get("rootBone", {}) if isinstance(tree, dict) else {}
        root = root_entry.get("$value") if isinstance(root_entry, dict) else None
        if root:
            bones.append(root)
        for subtree in tree.get("subtreesToChange", []):
            bones.extend(collect_root_bones(subtree))
        return bones

    def get_descendants(bone_name, bone_map):
        descendants = []
        for b in bone_map.values():
            if b.parent and b.parent.name == bone_name:
                descendants.append(b.name)
                descendants.extend(get_descendants(b.name, bone_map))
        return descendants

    # Detect current mode so we can restore it later
    current_mode = get_safe_mode()
    target_layer = []

    if current_mode == 'OBJECT':
        safe_mode_switch("EDIT")
        target_layer = arm_data.edit_bones
    elif current_mode == 'EDIT':
        target_layer = arm_data.edit_bones
    elif current_mode == 'POSE':
        target_layer = arm_data.bones 

    for part in parts:
        if not isinstance(part, dict):
            continue

        part_name = part.get("name", {}).get("$value")
        if not isinstance(part_name, str):
            continue

        # Create or reuse collection
        if part_name not in arm_data.collections:
            collection = arm_data.collections.new(name=part_name)
        else:
            collection = arm_data.collections[part_name]

        # Handle singleBones
        for bone_entry in part.get("singleBones", []):
            bone_name = bone_entry.get("$value") if isinstance(bone_entry, dict) else None
            if isinstance(bone_name, str):
                bone = arm_data.bones.get(bone_name)
                if bone:
                    collection.assign(bone)

        # Handle treeBones
        for tree in part.get("treeBones", []):
            if not isinstance(tree, dict):
                continue
            root_bones = collect_root_bones(tree)
            for root_name in root_bones:
                if not isinstance(root_name, str):
                    continue
                root_bone = arm_data.bones.get(root_name)
                if root_bone:
                    collection.assign(root_bone)
                for child_name in get_descendants(root_name, arm_data.bones):
                    child_bone = arm_data.bones.get(child_name)
                    if child_bone:
                        collection.assign(child_bone)

        # Optional rig data stored as custom props
        bones_with_rot_ms = [
            entry.get("$value") for entry in part.get("bonesWithRotationInModelSpace", [])
            if isinstance(entry, dict) and "$value" in entry
        ]
        mask_entries = {
            str(entry["index"]): entry["weight"]
            for entry in part.get("mask", [])
            if isinstance(entry, dict) and "index" in entry and "weight" in entry
        }
        mask_rot_ms = part.get("maskRotMS", [])

        # Set armature-level props
        arm_obj["bonesWithRotationInModelSpace"] = bones_with_rot_ms
        arm_obj["mask"] = json.dumps(mask_entries)
        arm_obj["maskRotMS"] = mask_rot_ms
        
        safe_mode_switch("POSE")
        pose_bones = arm_obj.pose.bones

        for bone_name in bones_with_rot_ms:
            if not isinstance(bone_name, str):
                continue
            pb = pose_bones.get(bone_name)
            if pb:
                pb["maskRotMS"] = True
        print(f"Assigned part: {part_name}")
        print("  bonesWithRotationInModelSpace:", bones_with_rot_ms)
        print("  mask:", mask_entries)
        print("  maskRotMS:", mask_rot_ms)
    # Restore original mode
    if current_mode != bpy.context.mode:
        restore_previous_context()

def assign_reference_tracks(arm_obj, track_names, reference_tracks):
    for i, track in enumerate(track_names):
        track_name = track.get("$value")
        if track_name and i < len(reference_tracks):
            arm_obj[track_name] = reference_tracks[i]

def create_armature_from_data(filepath):
    """
    Loads a .rig.json file, creates and configures a Blender armature object.

    Args:
        filepath (str): The absolute path to the .rig.json file.

    Returns:
        The created armature object on success, otherwise None.
    """
    start_time = time.time()
    
    try:
        # Load the file using JSONTool to get the RigData object
        rig_data = JSONTool.jsonload(filepath)
        if not rig_data:
            show_message(f"Failed to load rig data from {filepath} ERROR")
            return None

        # --- 1. Create Armature Object ---
        context = bpy.context
        safe_mode_switch('OBJECT')
        bpy.ops.object.add(type='ARMATURE', enter_editmode=True, location=(0,0,0))
        arm_obj = context.object
        arm_data = arm_obj.data
        arm_obj.name = rig_data.rig_name
        arm_data.name = f"{rig_data.rig_name}_Data"
        arm_data['source_rig_file'] = filepath
        arm_data['boneNames'] = rig_data.bone_names
        arm_data['boneParentIndexes'] = rig_data.bone_parents
        
        edit_bones = arm_data.edit_bones
        bone_index_map = {} # Maps bone index (int) to EditBone
        
        # Build the Skeleton ---
        global_transforms = {}
        for i, transform_data in enumerate(rig_data.bone_transforms):
            mat = compute_global_transform(i, rig_data.bone_transforms, rig_data.bone_parents, global_transforms)
            mat_blender = convert_matrix_from_game_to_blender(mat)
            
            bone = edit_bones.new(rig_data.bone_names[i])
            bone_index_map[i] = bone
            apply_bone_from_matrix(bone, mat_blender)

        # Apply A-Pose if available ---
        pose_matrices = build_apose_matrices(rig_data.apose_ms, rig_data.apose_ls, rig_data.bone_names, rig_data.bone_parents)
        if pose_matrices:
            for i, mat in enumerate(pose_matrices):
                bone = edit_bones.get(rig_data.bone_names[i])
                if bone:
                    mat_blender = convert_matrix_from_game_to_blender(mat)
                    apply_bone_from_matrix(bone, mat_blender)

        # Set Bone Parenting and Connections ---
        for i, parent_idx in enumerate(rig_data.bone_parents):
            if parent_idx != -1:
                child_bone = bone_index_map[i]
                parent_bone = bone_index_map[parent_idx]
                child_bone.parent = parent_bone
                
                is_special_bone = child_bone.name.endswith(("GRP", "IK", "JNT"))
                if not rig_data.disable_connect and not is_special_bone:
                    child_bone.use_connect = True

        # --- 5. Finalize Armature Setup ---
        safe_mode_switch('OBJECT')
        
        assign_part_groups(arm_obj, rig_data.parts)
        assign_bone_shapes(arm_obj, rig_data.disable_connect)
        assign_reference_tracks(arm_obj, rig_data.track_names, rig_data.reference_tracks)
        
        context.view_layer.objects.active = arm_obj
        arm_obj.select_set(True)
        restore_previous_context()

    except Exception as e:
        print(traceback.format_exc())
        show_message(f"Failed to import rig: {e}")
        return None

    print(f"Successfully imported {rig_data.rig_name} in {time.time() - start_time:.2f} seconds.")
    show_message(f"Imported rig: {rig_data.rig_name}")
    return arm_obj