def install_dependency(dependency_name):
    print(f"required package: {dependency_name} not found")
    from pip import _internal as pip
    print(f"Attempting to install {dependency_name}")
    try:
        pip.main(['install', dependency_name])
        print(f"Successfully installed {dependency_name}")
    except Exception as e:
        print(f"Failed to install {dependency_name}: {e}")
        
print('-------------------- Cyberpunk IO Suite Starting--------------------')
print()
from .cyber_prefs import *
from .cyber_props import *
import bpy
import sys
import textwrap
from bpy.props import (StringProperty, EnumProperty, BoolProperty)
from bpy.types import (Scene, Operator, Panel)
from . collisiontools import *
from . meshtools import *
from . animtools import *
from . importers import *
from . exporters import *
from . scriptman import *
from .main.common import get_classes
from .main.bartmoss_functions import *
from .icons.cp77_icons import *

bl_info = {
    "name": "Cyberpunk 2077 IO Suite",
    "author": "HitmanHimself, Turk, Jato, dragonzkiller, kwekmaster, glitchered, Simarilius, Doctor Presto, shotlastc, Rudolph2109, Holopointz",
    "version": (1, 5, 5, 3),
    "blender": (4, 0, 0),
    "location": "File > Import-Export",
    "description": "Import and Export WolvenKit Cyberpunk2077 gLTF models with materials, Import .streamingsector and .ent from .json",
    "warning": "",
    "category": "Import-Export",
    "doc_url": "https://github.com/WolvenKit/Cyberpunk-Blender-add-on#readme",
    "tracker_url": "https://github.com/WolvenKit/Cyberpunk-Blender-add-on/issues/new/choose",
}

plugin_version = ".".join(map(str, bl_info["version"]))
blender_version = ".".join(map(str, bpy.app.version))
script_dir = get_script_dir()

print()
print(f"Blender Version:{blender_version}")
print(f"Cyberpunk IO Suite version: {plugin_version}")
print()

res_dir = get_resources_dir()

class ShowMessageBox(Operator):
    bl_idname = "cp77.message_box"
    bl_label = "Cyberpunk 2077 IO Suite"

    message: StringProperty(default="")

    def execute(self, context):
        self.report({'INFO'}, self.message)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)
        
    def draw_header(self, context):
        layout = self.layout
        layout.label(text='Cyberpunk 2077 IO Suite')
        
    def draw(self, context):
        wrapp = textwrap.TextWrapper(width=50) #50 = maximum length       
        wList = wrapp.wrap(text=self.message) 
        for text in wList: 
            row = self.layout.row(align = True)
            row.alignment = 'EXPAND'
            row.label(text=text)     

class CollectionAppearancePanel(Panel):
    bl_label = "Ent Appearances"
    bl_idname = "PANEL_PT_appearance_variants"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "collection"

    #only draw the if the collector has an appearanceName property
    @classmethod
    def poll(cls, context):
        collection = context.collection
        return hasattr(collection, "appearanceName")

    def draw(self, context):
        layout = self.layout
        collection = context.collection
        layout.prop(collection, "appearanceName")       

operators, other_classes = get_classes(sys.modules[__name__])

def register():
    register_prefs()
    register_props() 
    register_animtools()
    register_collisiontools()
    register_importers()
    register_exporters()
    register_scriptman()
    register_meshtools()
    
    
    for cls in operators:
        if not hasattr(bpy.types, cls.__name__):
            bpy.utils.register_class(cls)
    for cls in other_classes:
        if not hasattr(bpy.types, cls.__name__):
            bpy.utils.register_class(cls)
    load_icons()

    print('-------------------- Cyberpunk IO Suite Finished--------------------')

def unregister():
    unregister_scriptman()
    unregister_meshtools()
    unregister_collisiontools()
    unregister_importers()
    unregister_exporters()
    unregister_animtools()
    unregister_props()  
    unregister_prefs()
    
    for cls in reversed(other_classes):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)

    for cls in reversed(operators):
        if hasattr(bpy.types, cls.__name__):
            bpy.utils.unregister_class(cls)
    unload_icons()
           
if __name__ == "__main__":
    register()