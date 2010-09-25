# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

from io_smd_tools.smd_utils import *

########################
#        Export        #
########################

# Get a list of bone names sorted so parents come before children.
# Also assign a unique SMD ID to every bone.
# Changes smd.boneIDs, smd.boneNameToID, and smd.sortedBones
# NOTE: This seems to return the same order that bones are read in.
def sortBonesForExport():

	def addBonesToSortedList(smd_id,bone,boneList):
		boneList.append(bone.name)
		smd.boneIDs[smd_id] = bone.name
		smd.boneNameToID[bone.name] = smd_id
		smd_id += 1
		for child in bone.children:
			smd_id = addBonesToSortedList(smd_id,child,boneList)
		return smd_id

	smd_id = 0
	smd.sortedBones = []
	for bone in smd.a.data.bones:
		if not bone.parent:
			smd_id = addBonesToSortedList(smd_id,bone,smd.sortedBones)

# nodes block
def writeBones(quiet=False):

	smd.file.write("nodes\n")

	if not smd.a:
		smd.file.write("0 \"root\" -1\nend\n")
		if not quiet: print("- No skeleton to export")
		return

	# Write to file
	for boneName in smd.sortedBones:
		line = str(smd.boneNameToID[boneName]) + " "

		bone = smd.a.data.bones[boneName]
		bone_name = bone.get('smd_name')
		if not bone_name:
			bone_name = bone.name
		line += "\"" + bone_name + "\" "

		if bone.parent:
			line += str(smd.boneNameToID[bone.parent.name])
		else:
			line += "-1"

		smd.file.write(line + "\n")

	smd.file.write("end\n")
	if not quiet: print("- Exported",len(smd.a.data.bones),"bones")
	if len(smd.a.data.bones) > 128:
		log.warning(smd,"Source only supports 128 bones!")

# NOTE: added this to keep writeFrames() a bit simpler, uses smd.sortedBones and smd.boneNameToID, replaces getBonesForSMD()
def writeRestPose():
	smd.file.write("time 0\n")
	for boneName in smd.sortedBones:
		bone = smd.a.data.bones[boneName]
		if bone.parent:
			parentRotated = bone.parent.matrix_local * ryz90
			childRotated = bone.matrix_local * ryz90
			rot = parentRotated.invert() * childRotated
			pos = rot.translation_part()
			rot = rot.to_euler('XYZ')
		else:
			pos = bone.matrix_local.translation_part()
			rot = (bone.matrix_local * ryz90).to_euler('XYZ')

		pos_str = rot_str = ""
		for i in range(3):
			pos_str += " " + getSmdFloat(pos[i])
			rot_str += " " + getSmdFloat(rot[i])
		smd.file.write( str(smd.boneNameToID[boneName]) + pos_str + rot_str + "\n" )
	smd.file.write("end\n")

# skeleton block
def writeFrames():
	if smd.jobType == 'FLEX': # writeShapes() does its own skeleton block
		return

	smd.file.write("skeleton\n")

	if not smd.a:
		smd.file.write("time 0\n0 0 0 0 0 0 0\nend\n")
		return

	if smd.jobType != 'ANIM':
		writeRestPose()
		return

	scene = bpy.context.scene
	prev_frame = scene.frame_current
	#scene.frame_current = scene.frame_start

	armature_was_hidden = smd.a.hide
	smd.a.hide = False # ensure an object is visible or mode_set() can't be called on it
	scene.objects.active = smd.a
	bpy.ops.object.mode_set(mode='POSE')

	#last_frame = 0
	#for fcurve in smd.a.animation_data.action.fcurves:
		# Get the length of the action
	#	last_frame = max(last_frame,fcurve.keyframe_points[-1].co[0]) # keyframe_points are always sorted by time
	start_frame, last_frame = smd.a.animation_data.action.frame_range
	start_frame = int(start_frame)
	last_frame = int(last_frame)
	scene.frame_set(start_frame)

	while scene.frame_current <= last_frame:
		smd.file.write("time %i\n" % (scene.frame_current-start_frame))

		for boneName in smd.sortedBones:
			pbn = smd.a.pose.bones[boneName]
			if pbn.parent:
				parentRotated = pbn.parent.matrix * ryz90
				childRotated = pbn.matrix * ryz90
				rot = parentRotated.invert() * childRotated
				pos = rot.translation_part()
				rot = rot.to_euler('XYZ')
			else:
				pos = pbn.matrix.translation_part()
				rot = (pbn.matrix * ryz90).to_euler('XYZ')

			pos_str = rot_str = ""
			for i in range(3):
				pos_str += " " + getSmdFloat(pos[i])
				rot_str += " " + getSmdFloat(rot[i])
			smd.file.write( str(smd.boneNameToID[boneName]) + pos_str + rot_str + "\n" )

		scene.frame_set(scene.frame_current + 1)

	if armature_was_hidden:
		smd.a.hide = True

	smd.file.write("end\n")
	scene.frame_set(prev_frame)
	return

# triangles block
def writePolys():
	smd.file.write("triangles\n")
	md = smd.m.data
	face_index = 0
	for face in md.faces:
		if smd.m.material_slots:
			mat = smd.m.material_slots[face.material_index].material
			mat_name = mat['smd_name'] if mat.get('smd_name') else mat.name
			smd.file.write(mat_name + "\n")
		else:
			smd.file.write(smd.jobName + "\n")
		for i in range(3):

			# Vertex locations, normal directions
			verts = norms = ""
			v = md.vertices[face.vertices[i]]

			for j in range(3):
				verts += " " + getSmdFloat(v.co[j])
				norms += " " + getSmdFloat(v.normal[j])

			# UVs
			if len(md.uv_textures):
				uv = ""
				for j in range(2):
					uv += " " + getSmdFloat(md.uv_textures[0].data[face_index].uv[i][j])
			else:
				if i == 0:
					uv = " 0 0"
				elif i == 1:
					uv = " 0 1"
				else:
					uv = " 1 1"

			# Weightmaps
			if len(v.groups):
				groups = " " + str(len(v.groups))
				for j in range(len(v.groups)):
					try:
						# There is no certainty that a bone and its vertex group will share the same ID. Thus this monster:
						groups += " " + str(smd.boneNameToID[smd.m.vertex_groups[v.groups[j].group].name]) + " " + getSmdFloat(v.groups[j].weight)
					except AttributeError:
						pass # bone doesn't have a vert group on this mesh; not necessarily a problem
			else:
				groups = " 0"

			# Finally, write it all to file
			smd.file.write("0" + verts + norms + uv + groups + "\n")

		face_index += 1

	smd.file.write("end\n")
	print("- Exported",face_index,"polys")

	bpy.ops.object.mode_set(mode='OBJECT')

	return

# vertexanimation block
def writeShapes():

	# VTAs are always separate files. The nodes block is handled by the normal function, but skeleton is done here to afford a nice little hack
	smd.file.write("skeleton\n")
	for i in range(len(smd.m.data.shape_keys.keys)):
		smd.file.write("time %i\n" % i)
	smd.file.write("end\n")

	# OK, on to the meat!
	smd.file.write("vertexanimation\n")
	num_shapes = 0

	for shape_id in range(len(smd.m.data.shape_keys.keys)):
		shape = smd.m.data.shape_keys.keys[shape_id]
		smd.file.write("time %i\n" % shape_id)

		smd_vert_id = 0
		for face in smd.m.data.faces:
			for vert in face.vertices:
				shape_vert = shape.data[vert]
				mesh_vert = smd.m.data.vertices[vert]
				cos = norms = ""

				if shape_id == 0 or (shape_id > 0 and shape_vert.co != mesh_vert.co):
					for i in range(3):
						cos += " " + getSmdFloat(shape_vert.co[i])
						norms += " " + getSmdFloat(mesh_vert.normal[i]) # Blender's shape keys do not store normals
					smd.file.write(str(smd_vert_id) + cos + norms + "\n")
				smd_vert_id +=1
		num_shapes += 1
	smd.file.write("end\n")
	print("- Exported",num_shapes,"vertex animations")
	return

# Creates a duplicate datablock with object transformations and modifiers applied
def bakeObj(in_object):
	bi = {}
	bi['src'] = in_object
	baked = bi['baked'] = in_object.copy()
	
	bi['disabled_modifiers'] = []
	bpy.context.scene.objects.link(baked)
	bpy.context.scene.objects.active = baked	
	for object in bpy.context.selected_objects:
		object.select = False
	baked.select = True
	
	for mod in baked.modifiers:
		if mod.type == 'ARMATURE':
			mod.show_render = False # the mesh will be baked in rendering mode
		
	if baked.type == 'MESH':
		smd.m = baked
		baked.data = baked.create_mesh(bpy.context.scene,True,'RENDER') # the important command

		# quads > tris
		bpy.ops.object.mode_set(mode='EDIT')
		bpy.ops.mesh.select_all(action='SELECT')
		bpy.ops.mesh.quads_convert_to_tris()
		bpy.ops.object.mode_set(mode='OBJECT')

		if baked.parent or baked.find_armature(): # do not translate standalone meshes (and never translate armatures)
			bpy.ops.object.location_apply()
			
	elif baked.type == 'ARMATURE':
		baked.data = in_object.data.copy()
		smd.a = baked
	
	bpy.ops.object.rotation_apply()
	bpy.ops.object.scale_apply()
	
	if bpy.context.scene.smd_up_axis != 'Z':
		# Object rotation is in local space, requiring this second rotation_apply() step
		baked.rotation_mode = 'QUATERNION'
		baked.rotation_quaternion = getUpAxisMat(bpy.context.scene.smd_up_axis).invert().to_quat()
		bpy.ops.object.rotation_apply()
	
	smd.bakeInfo.append(bi) # save to manager

def unBake():
	for bi in smd.bakeInfo:
		baked_data = bi['baked'].data
		type = bi['baked'].type
		bpy.ops.object.mode_set(mode='OBJECT')
		
		bpy.context.scene.objects.unlink(bi['baked'])
		bpy.data.objects.remove(bi['baked'])
		
		if type == 'MESH':
			bpy.data.meshes.remove(baked_data)
			smd.m = bi['src']
		elif type == 'ARMATURE':
			bpy.data.armatures.remove(baked_data)
			smd.a = bi['src']
		
		del bi

# Creates an SMD file
def writeSMD( context, object, filepath, smd_type = None, quiet = False ):
	if filepath.endswith("dmx"):
		print("Skipping DMX file export: format unsupported (%s)" % getFilename(filepath))
		return

	global smd
	smd	= smd_info()
	smd.jobName = object.name
	smd.jobType = smd_type
	smd.startTime = time.time()
	smd.uiTime = 0
	mesh_was_hidden = False

	if object.type == 'MESH':
		if not smd.jobType:
			smd.jobType = 'REF'
		smd.m = object
		bakeObj(smd.m)
		smd.a = smd.m.find_armature()
		if smd.m.hide:
			smd.m.hide = False
			mesh_was_hidden = True
	elif object.type == 'ARMATURE':
		if not smd.jobType:
			smd.jobType = 'ANIM'
		smd.a = object
	else:
		raise TypeError("PROGRAMMER ERROR: writeSMD() has object not in [mesh,armature]")

	smd.file = open(filepath, 'w')
	if not quiet: print("\nSMD EXPORTER: now working on",smd.jobName)
	smd.file.write("version 1\n")

	if smd.a:
		bakeObj(smd.a) # MUST be baked after the mesh
		sortBonesForExport() # Get a list of bone names sorted in the order to be exported, and assign a unique SMD ID to every bone.
		if smd.jobType == 'FLEX':
			writeBones(quiet=True)
		else:
			writeBones()
			writeFrames()
	elif smd.jobType in ['REF','PHYS']:
		writeBones()
		writeFrames()

	if smd.m:
		if smd.jobType in ['REF','PHYS']:
			writePolys()
		elif smd.jobType == 'FLEX' and smd.m.data.shape_keys:
			writeShapes()

	unBake()

	smd.file.close()
	if mesh_was_hidden:
		smd.m.hide = True
	if not quiet: printTimeMessage(smd.startTime,smd.jobName,"export")

class SMD_MT_ExportChoice(bpy.types.Menu):
	bl_label = "SMD export mode"

	def draw(self, context):
		# This function is also embedded in property panels on scenes and armatures
		l = self.layout
		try:
			l = self.embed_scene
			embed_scene = True
		except AttributeError:
			embed_scene = False
		try:
			l = self.embed_arm
			embed_arm = True
		except AttributeError:
			embed_arm = False

		ob = context.active_object
		if embed_scene and (len(context.selected_objects) == 0 or not ob):
			row = l.row()
			row.operator(SmdExporter.bl_idname, text="No selection") # filler to stop the scene button moving
			row.enabled = False
		elif (ob and len(context.selected_objects) == 1) or embed_arm:
			subdir = ob.get('smd_subdir')
			if subdir:
				label = subdir + "\\"
			else:
				label = ""
			if ob.type == 'MESH':
				label += ob.name + ".smd"
				if ob.data.shape_keys and len(ob.data.shape_keys.keys) > 1:
					label += "/.vta"
				l.operator(SmdExporter.bl_idname, text=label, icon="OUTLINER_OB_MESH").exportMode = 'SINGLE' # single mesh
			elif ob.type == 'ARMATURE':
				# current action
				if ob.animation_data and ob.animation_data.action:
					label += ob.animation_data.action.name + ".smd"
					l.operator(SmdExporter.bl_idname, text=label, icon="ACTION").exportMode = 'SINGLE'
				else:
					l.label(text="No actions", icon="ACTION")

				if len(bpy.data.actions) and not embed_scene:
					# filtered action list
					if ob.smd_action_filter:
						global cached_action_filter_list
						global cached_action_count
						if ob.smd_action_filter != cached_action_filter_list:
							cached_action_filter_list = ob.smd_action_filter
							cached_action_count = 0
							for action in bpy.data.actions:
								if action.name.lower().find(ob.smd_action_filter.lower()) != -1:
									cached_action_count += 1
						text = "\"" + ob.smd_action_filter + "\" actions (" + str(cached_action_count) + ")"
					else:
						text = "All actions (" + str(len(bpy.data.actions)) + ")"
					l.operator(SmdExporter.bl_idname, text=text, icon='ARMATURE_DATA').exportMode = 'ALL_ACTIONS'
			else:
				label = "Cannot export " + ob.name
				if ob.type == 'TEXT':
					type = 'FONT'
				else:
					type = ob.type
				try:
					l.label(text=label,icon='OUTLINER_OB_' + type)
				except: # bad icon
					l.label(text=label,icon='ERROR')

		elif len(context.selected_objects) > 1 and not embed_arm:
			l.operator(SmdExporter.bl_idname, text="Selected objects", icon='GROUP').exportMode = 'MULTI' # multiple obects


		if not embed_arm:
			l.operator(SmdExporter.bl_idname, text="Scene as configured", icon='SCENE_DATA').exportMode = 'SCENE'
		#l.operator(SmdExporter.bl_idname, text="Whole .blend", icon='FILE_BLEND').exportMode = 'FILE' # can't do this until scene changes become possible

class SMD_PT_Scene(bpy.types.Panel):
	bl_label = "SMD Export"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	bl_default_closed = True

	def __init__(self, context):
		from io_smd_tools.smd_test_suite import available
		self.smd_test_suite = available()

	def draw(self, context):
		l = self.layout
		scene = context.scene

		self.embed_scene = l.row()
		SMD_MT_ExportChoice.draw(self,context)

		l.prop(scene,"smd_path",text="Output Folder")
		l.prop(scene,"smd_up_axis",text="Target Up Axis")

		validObs = []
		for object in scene.objects:
			if object.type in ['MESH','ARMATURE']:
				validObs.append(object)

		if len(validObs):
			l.label(text="Scene Configuration:")
			box = l.box()
			columns = box.column()
			header = columns.row()
			header.label(text="Object:")
			header.label(text="Subfolder:")
			foundObjs = False
			for object in validObs:
				row = columns.row()
				row.prop(object,"smd_export",icon="OUTLINER_OB_" + object.type,emboss=True,text=object.name)
				row.prop(object,"smd_subdir",text="")

		r = l.row()
		r.prop(scene,"smd_qc_compile")
		rhs = r.row()
		rhs.prop(scene,"smd_studiomdl_branch",text="")
		c = l.column()
		c.prop(scene,"smd_qc_path")
		rhs.enabled = c.enabled = scene.smd_qc_compile
		if scene.smd_studiomdl_branch == 'CUSTOM':
			c.prop(scene,"smd_studiomdl_custom_path")
		l.separator()
		l.operator(SmdClean.bl_idname,text="Clean all SMD data from scene and objects",icon='RADIO')
		if self.smd_test_suite:
			l.operator(self.smd_test_suite,text="Run test suite",icon='FILE_TICK')

class SMD_PT_Armature(bpy.types.Panel):
	bl_label = "SMD Export"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "data"

	@classmethod
	def poll(self,context):
		return context.active_object.type == 'ARMATURE' # the panel isn't displayed unless there is an active object

	def draw(self, context):
		l = self.layout
		arm = context.active_object
		anim_data = arm.animation_data

		l.prop(arm,"smd_subdir",text="Export Subfolder")
		l.prop(arm,"smd_action_filter",text="Action Filter")

		self.embed_arm = l.row()
		SMD_MT_ExportChoice.draw(self,context)

		if anim_data:
			l.template_ID(anim_data, "action", new="action.new")

class SmdClean(bpy.types.Operator):
	bl_idname = "smd.clean"
	bl_label = "Clean SMD data"
	bl_description = "Deletes all SMD-related properties from the scene and its contents"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self,context):
		self.numPropsRemoved = 0
		def removeProps(object):
			for prop in object.items():
				if prop[0].startswith("smd_"):
					del object[prop[0]]
					self.numPropsRemoved += 1

		active_obj = bpy.context.active_object
		active_mode = active_obj.mode if active_obj else None

		for object in context.scene.objects:
			removeProps(object)
			if object.type == 'ARMATURE':
				# For some reason deleting custom properties from bones doesn't work well in Edit Mode
				bpy.context.scene.objects.active = object
				object_mode = object.mode
				bpy.ops.object.mode_set(mode='OBJECT')
				for bone in object.data.bones:
					removeProps(bone)
				bpy.ops.object.mode_set(mode=object_mode)
		removeProps(context.scene)

		bpy.context.scene.objects.active = active_obj
		if active_obj != None:
			bpy.ops.object.mode_set(mode=active_mode)

		self.report('INFO',"Deleted {} SMD properties".format(self.numPropsRemoved))
		return 'FINISHED'

class SmdExporter(bpy.types.Operator):
	bl_idname = "export.smd"
	bl_label = "Export SMD/VTA"
	bl_description = "Export meshes, actions and shape keys to Studiomdl Data"

	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA file", maxlen=1024, default="", subtype='FILE_PATH')
	filename = StringProperty(name="Filename", description="Name of SMD/VTA file", maxlen=1024, default="", subtype='FILENAME')
	exportMode_enum = (
		('NONE','No mode','The user will be prompted to choose a mode'),
		('SINGLE','Active','Only the active object'),
		('MULTI','Selection','All selected objects'),
		('ALL_ACTIONS','All actions','Export all actions attached to the current Armature'),
		('SCENE','Scene','Export the objects and animations selected in Scene Properties'),
		#('FILE','Whole .blend file','Export absolutely everything, from all scenes'),
		)
	exportMode = EnumProperty(items=exportMode_enum,options={'HIDDEN'})

	def execute(self, context):
		props = self.properties

		if props.exportMode == 'NONE':
			self.report('ERROR',"Programmer error: bpy.ops.export.smd called without exportMode")
			return 'CANCELLED'

		# Handle export root path
		if len(props.filepath):
			# We've got a file path from the file selector, write it and continue
			context.scene['smd_path'] = getFileDir(props.filepath)
		else:
			# Get a path from the scene object
			export_root = context.scene.get("smd_path")

			# No root defined, pop up a file select
			if not export_root:
				props.filename = "<folder select>"
				context.window_manager.add_fileselect(self)
				return 'RUNNING_MODAL'

			if export_root.startswith("//") and not bpy.context.blend_data.filepath:
				self.report('ERROR',"Relative scene output path, but .blend not saved")
				return 'CANCELLED'

			if export_root[-1] not in ['\\','/']: # append trailing slash
				if os.name == 'nt':
					export_root += "\\"
				else:
					export_root += "/"

			props.filepath = export_root

		global log
		log = logger()

		print("\nSMD EXPORTER RUNNING")
		prev_active_ob = context.active_object
		if prev_active_ob:
			prev_active_hide = prev_active_ob.hide
		prev_selection = context.selected_objects

		# store Blender mode user was in before export
		prev_mode = bpy.context.mode
		if prev_mode.startswith("EDIT"):
			prev_mode = "EDIT" # remove any suffixes
		if prev_active_ob:
			prev_active_ob.hide = False # ensure an object is visible or mode_set() can't be called on it
			ops.object.mode_set(mode='OBJECT')

		# check export mode and perform appropriate jobs
		self.countSMDs = 0
		if props.exportMode in ['SINGLE','ALL_ACTIONS']:
			self.exportObject(context,context.active_object)

		elif props.exportMode == 'MULTI':
			for object in context.selected_objects:
				if object.type in ['MESH', 'ARMATURE']:
					self.exportObject(context,object)

		elif props.exportMode == 'SCENE':
			for object in bpy.context.scene.objects:
				if object.smd_export:
					self.exportObject(context,object)

		elif props.exportMode == 'FILE': # can't be done until Blender scripts become able to change the scene
			for scene in bpy.data.scenes:
				scene_root = scene.get("smd_path")
				if not scene_root:
					log.warning("Skipped unconfigured scene",scene.name)
					continue
				else:
					props.filepath = scene_root

				for object in bpy.data.objects:
					if object.type in ['MESH', 'ARMATURE']:
						self.exportObject(context,object)

		# Export jobs complete! Clean up...
		context.scene.objects.active = prev_active_ob
		if prev_active_ob:
			ops.object.mode_set(mode=prev_mode)
			prev_active_ob.hide = prev_active_hide
		for object in context.scene.objects:
			if object in prev_selection:
				object.select = True
			else:
				object.select = False
		if self.countSMDs == 0:
			log.error(self,"Found no valid objects for export")
			return 'CANCELLED'

		# ...and compile the QC
		if context.scene.smd_qc_compile:
			branch = context.scene.smd_studiomdl_branch
			try:
				sdk_path = os.environ['SOURCESDK']
				ncf_path = sdk_path + "\\..\\..\\common\\"

				if branch == 'CUSTOM':
					studiomdl_path = context.scene.smd_studiomdl_custom_path = bpy.path.abspath(context.scene.smd_studiomdl_custom_path)

				if branch in ['ep1','source2007','orangebox']:
					studiomdl_path = sdk_path + "\\bin\\" + branch + "\\bin\\"
				if branch in ['left 4 dead', 'left 4 dead 2', 'alien swarm']:
					studiomdl_path = ncf_path + branch + "\\bin\\"

				if studiomdl_path and studiomdl_path[-1] in ['/','\\']:
					studiomdl_path += "studiomdl.exe"

				if os.path.exists(studiomdl_path):
					import subprocess
					print("Running studiomdl for \"" + getFilename(context.scene.smd_qc_path) + "\"...\n")
					subprocess.call([studiomdl_path, "-nop4", bpy.path.abspath(context.scene.smd_qc_path)])
					print("\n")
				else:
					log.error(self,"Could not access studiomdl at \"" + studiomdl_path + "\"")

			except KeyError:
				log.error(self,"Source SDK not configured. Launch it, or run a custom QC compile")

		jobMessage = "exported"
		if context.scene.smd_qc_compile:
			jobMessage += " and QC compiled"
		log.errorReport(jobMessage,self)
		return 'FINISHED'

	# indirection to support batch exporting
	def exportObject(self,context,object,flex=False):
		props = self.properties

		# handle subfolder
		if len(object.smd_subdir) == 0 and object.type == 'ARMATURE':
			object.smd_subdir = "anims"
		object.smd_subdir = object.smd_subdir.lstrip("/") # don't want //s here!

		if props.exportMode != 'ALL_ACTIONS' and object.type == 'ARMATURE' and not object.animation_data:
			return; # otherwise we create a folder but put nothing in it

		# assemble filename
		path = bpy.path.abspath(getFileDir(props.filepath) + object.smd_subdir)
		if path and path[-1] not in ['/','\\']:
			if os.name is 'nt':
				path += "\\"
			else:
				path += "/"

		if not os.path.exists(path):
			os.makedirs(path)

		if object.type == 'MESH':
			path += object.name
			writeSMD(context, object, path + ".smd")
			self.countSMDs += 1
			if object.data.shape_keys and len(object.data.shape_keys.keys) > 1:
				writeSMD(context, object, path + ".vta", 'FLEX')
				self.countSMDs += 1
		elif object.type == 'ARMATURE' and object.animation_data:
			ad = object.animation_data
			if ad.action:
				prev_action = ad.action
				if self.properties.exportMode == 'ALL_ACTIONS':
					for action in bpy.data.actions:
						if not object.smd_action_filter or action.name.lower().find(object.smd_action_filter.lower()) != -1:
							ad.action = action
							writeSMD(context,object,path + action.name + ".smd",'ANIM')
							self.countSMDs += 1
				else:
					writeSMD(context,object,path + ad.action.name + ".smd",'ANIM')
					self.countSMDs += 1
				ad.action = prev_action

	def invoke(self, context, event):
		if self.properties.exportMode == 'NONE':
			bpy.ops.wm.call_menu(name="SMD_MT_ExportChoice")
			return 'PASS_THROUGH'
		else: # a UI element has chosen a mode for us
			return self.execute(context)

def menu_func_export(self, context):
	self.layout.operator(SmdExporter.bl_idname, text="Studiomdl Data (.smd, .vta)")

def register():
	type = bpy.types
	type.INFO_MT_file_export.append(menu_func_export)

	global cached_action_filter_list
	cached_action_filter_list = 0

	type.Scene.smd_path = StringProperty(name="SMD Export Root",description="The root folder into which SMDs from this scene are written",subtype='DIR_PATH')
	type.Scene.smd_qc_compile = BoolProperty(name="QC Compile on Export",description="Compile the specified QC file on export",default=False)
	type.Scene.smd_qc_path = StringProperty(name="QC File",description="QC file to compile on export. Cannot be internal to Blender.",subtype="FILE_PATH")
	src_branches = (
	('CUSTOM','Custom Path','User-defined compiler path'),
	('orangebox','Source 2009','Source 2009'),
	('source2007','Source 2007','Source 2007'),
	('ep1','Source 2006','Source 2006'),
	('left 4 dead 2','Left 4 Dead 2','Left 4 Dead 2'),
	('left 4 dead','Left 4 Dead','Left 4 Dead'),
	('alien swarm','Alien Swarm','Alien Swarm')
	)
	type.Scene.smd_studiomdl_branch = EnumProperty(name="Studiomdl Branch",items=src_branches,description="The Source tool branch to compile with",default='orangebox')
	type.Scene.smd_studiomdl_custom_path = StringProperty(name="Studiomdl Path",description="User-defined path to Studiomdl, for Custom compiles.",subtype="FILE_PATH")
	type.Scene.smd_up_axis = EnumProperty(name="SMD Target Up Axis",items=axes,default='Z',description="Use for compatibility with existing SMDs")

	type.Object.smd_export = BoolProperty(name="SMD Scene Export",description="Export this object with the scene",default=True)
	type.Object.smd_subdir = StringProperty(name="SMD Subfolder",description="Location, relative to scene root, for SMDs from this object")
	type.Object.smd_action_filter = StringProperty(name="SMD Action Filter",description="Only actions with names matching this filter will be exported")


def unregister():
	bpy.types.INFO_MT_file_export.remove(menu_func_export)
	Scene = bpy.types.Scene
	del Scene.smd_path
	del Scene.smd_qc_compile
	del Scene.smd_studiomdl_branch
	del Scene.smd_studiomdl_custom_path
	del Scene.smd_up_axis
	Object = bpy.types.Object
	del Object.smd_export
	del Object.smd_subdir
	del Object.smd_action_filter
