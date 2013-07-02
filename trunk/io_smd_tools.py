import bpy, os

@bpy.app.handlers.persistent
def pass_torch(scene):
	bpy.app.handlers.scene_update_post.remove(pass_torch)
	
	bpy.ops.wm.addon_enable('EXEC_SCREEN',module="io_scene_valvesource")
	bpy.ops.wm.addon_disable('EXEC_SCREEN',module="io_smd_tools")
	bpy.ops.wm.save_userpref('EXEC_AREA')
	
	for s_path in bpy.utils.script_paths():
		for k_path in [ os.path.abspath(os.path.join(s_path,"modules","datamodel.py")), os.path.abspath(os.path.join(s_path,"addons","io_smd_tools.py")) ]:
			if os.path.exists(k_path):
				try: os.remove(k_path)
				except: pass

def register():
	for s_path in bpy.utils.script_paths():
		if os.path.exists(os.path.join(s_path,"addons","io_scene_valvesource")):
			bpy.app.handlers.scene_update_post.append(pass_torch)
			break

def unregister():
	pass
