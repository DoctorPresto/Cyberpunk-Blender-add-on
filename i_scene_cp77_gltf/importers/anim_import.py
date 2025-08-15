import bpy
from ..cyber_props import add_anim_props

def get_anim_info(animations):
    """Assign CP77 animation metadata to matching Blender actions."""
    cp77_addon_prefs = bpy.context.preferences.addons['i_scene_cp77_gltf'].preferences
    for animation in animations:
        if not cp77_addon_prefs.non_verbose:
            print(f"Processing animation: {animation.name}")

        action = next((act for act in bpy.data.actions if act.name.startswith(animation.name + "_Armature")), None)
        if action:
            add_anim_props(animation, action)
            if not cp77_addon_prefs.non_verbose:
                print("Properties added to", action.name)
        else:
            if not cp77_addon_prefs.non_verbose:
                print("No action found for", animation.name)
    print('')
