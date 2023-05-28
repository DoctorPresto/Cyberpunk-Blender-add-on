import bpy 

def default_cp77_options():
    options = {
        'export_format': 'GLB',
        'export_normals': True,
        'check_existing': True,
        'export_skins': True,
        'export_cameras': False,
        'export_yup': True,
        'export_tangents': True,
        'export_materials': 'NONE',
        'export_all_influences': True,
        'export_lights': False,
        'export_morph_tangent': True,
        'export_morph_normal': True,
        'export_apply': False
    }
    return options

def cp77_mesh_options():
    options = {
        'export_morph': True,
        'export_morph_normal': True,
        'export_colors': True
    }
    return options

def pose_export_options():
    options = {
        'export_animations': True,
        'export_frame_range': False,
        'export_anim_single_armature': True       
    }
    return options
    
def export_cyberpunk_glb(context, filepath, export_poses):
    # Retrieve the selected objects
    objects = context.selected_objects
    #if for photomode, make sure theres an armature selected, if not use the message box to show an error
    if export_poses:
        armatures = [obj for obj in objects if obj.type == 'ARMATURE']
        if not armatures:
            bpy.ops.cp77.message_box('INVOKE_DEFAULT', message="No armature selected, please select an armature")
            return {'CANCELLED'}
        #if the export poses value is True, set the export options to ensure the armature is exported properly with the animations
        options = default_cp77_options()
        options.update(pose_export_options())
    else:
    #if export_poses option isn't used, check to make sure there are meshes selected and throw an error if not
        meshes = [obj for obj in objects if obj.type == 'MESH']
        if not meshes:
            bpy.ops.cp77.message_box('INVOKE_DEFAULT', message="No meshes selected, please select at least one mesh")
            return {'CANCELLED'}
    #check that meshes include UVs and have less than 65000 verts, throw an error if not
        for mesh in meshes:
            if not mesh.data.uv_layers:
                bpy.ops.cp77.message_box('INVOKE_DEFAULT', message="Meshes must have UV layers in order to import in Wolvenkit")
                return {'CANCELLED'}
            for submesh in mesh.data.polygons:
                if len(submesh.vertices) > 65000:
                    bpy.ops.cp77.message_box('INVOKE_DEFAULT', message="Each submesh must have less than 65,000 vertices")
                    return {'CANCELLED'}
        #use the right options for exporting a mesh
        options = default_cp77_options()
        options.update(cp77_mesh_options())

    print(options)  
    # if exporting meshes, iterate through any attached armatures, storing their original state. if hidden, unhide them and select them for export
armature_states = {}  # Dictionary to store original armature states

for obj in objects:
    if obj.type == 'MESH':
        for modifier in obj.modifiers:
            if modifier.type == 'ARMATURE' and modifier.object and modifier.object.hide_get():
                # Store original visibility and selection state
                armature_states[modifier.object] = {"hide": modifier.object.hide_get(),
                                                    "select": modifier.object.select_get()}
                # Make necessary changes for export
                modifier.object.hide_set(False)
                modifier.object.select_set(True)

# Export the meshes to glb
bpy.ops.export_scene.gltf(filepath=filepath, use_selection=True, **options)

# Restore original armature visibility and selection state
for armature, state in armature_states.items():
    armature.select_set(state["select"])  # Restore original selection state
    armature.hide_set(state["hide"]) 
