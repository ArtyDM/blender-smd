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
#        Import        #
########################

# Identifies what type of SMD this is. Cannot tell between reference/lod/collision meshes!
def scanSMD():
	for line in smd.file:
		if line == "triangles\n":
			smd.jobType = 'REF'
			print("- This is a mesh")
			break
		if line == "vertexanimation\n":
			print("- This is a flex animation library")
			smd.jobType = 'FLEX'
			break

	# Finished the file

	if smd.jobType == None:
		print("- This is a skeltal animation or pose") # No triangles, no flex - must be animation
		if not smd.multiImport:
			for object in bpy.context.scene.objects:
				if object.type == 'ARMATURE':
					smd.jobType = 'ANIM'
		if smd.jobType == None: # support importing animations on their own
			smd.jobType = 'ANIM_SOLO'

	smd.file.seek(0,0) # rewind to start of file

def uniqueName(name, nameList, limit):
	if name not in nameList and len(name) <= limit:
		return name
	name_orig = name[:limit-3]
	i = 1
	name = '%s_%.2d' % (name_orig, i)
	while name in nameList:
		i += 1
		name = '%s_%.2d' % (name_orig, i)
	return name

# Runs instead of readBones if an armature already exists, testing the current SMD's nodes block against it.
def validateBones():
	countBones = 0
	for line in smd.file:

		if line == "end\n":
			break

		countBones += 1

		s = line.strip()
		m = re.match('([-+]?\d+)\s+"([\S ]+)"\s+([-+]?\d+)', s)
		values = list(m.groups())

		smd_name = values[1]

		foundIt = False
		for bone in smd.a.data.bones:
			if bone.get('smd_name') == smd_name or bone.name == smd_name:
				smd_id = int(values[0])
				smd.boneIDs[smd_id] = bone.name
				smd.boneNameToID[bone.name] = smd_id
				parentID = int(values[2])
				if parentID in smd.boneIDs:
					smd.parentBones[bone.name] = smd.boneIDs[parentID] # parent in this SMD
				#print("found bone #%s %s"%(values[0],smd_name))
				foundIt = True
				break
		if not foundIt:
			pass #raise Exception("no such bone \"%s\" in existing armature" % smd_name)

	print("- Validated %i bones against \"%s\" armature" % (countBones, smd.a.name))

# nodes block
def readBones():
	if not smd.multiImport:
		# Search the current scene for an existing armature - there can only be one skeleton in a Source model
		if bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE':
			smd.a = bpy.context.active_object
		else:
			def isArmIn(list):
				if smd.a: return # already found
				for ob in list:
					if ob.type == 'ARMATURE':
						smd.a = ob
						return True

			isArmIn(bpy.context.selected_objects) # armature in the selection?

			for ob in bpy.context.selected_objects:
				if ob.type == 'MESH':
					smd.a = ob.find_armature() # armature modifying a selected object?
					if smd.a:
						break

			isArmIn(bpy.context.scene.objects) # armature in the scene at all?
		if smd.a:
			if smd.jobType == 'REF':
				smd.jobType = 'REF_ADD'
			validateBones()
			return

	# Got this far? Then this is a fresh import which needs a new armature.
	if bpy.context.active_object:
		bpy.ops.object.mode_set(mode='OBJECT',toggle=False)
	a = smd.a = bpy.data.objects.new(smd_manager.jobName,bpy.data.armatures.new(smd_manager.jobName))
	a.show_x_ray = True
	a.data.use_deform_envelopes = False # Envelope deformations are not exported, so hide them
	a.data.draw_type = 'STICK'
	bpy.context.scene.objects.link(a)
	for i in bpy.context.selected_objects: i.select = False #deselect all objects
	a.select = True
	bpy.context.scene.objects.active = a
	try:
		qc.armature = a
	except NameError:
		pass

	# ***********************************
	# Read bones from SMD
	countBones = 0
	ops.object.mode_set(mode='EDIT')
	for line in smd.file:
		if line == "end\n":
			print("- Imported %i new bones" % countBones)
			break

		countBones += 1
		values = parseQuoteBlockedLine(line,lower=False)

		values[1] = values[1].strip("\"") # all bone names are in quotes
		original_bone_name = values[1]
		# Remove "ValveBiped." prefix, a leading cause of bones name length going over Blender's limit
		ValveBipedCheck = values[1].split(".",1)
		if len(ValveBipedCheck) > 1:
			values[1] = ValveBipedCheck[1]


		newBone = a.data.edit_bones.new(values[1])
		newBone.tail = 0,1,0

		if len(original_bone_name) > 32: # max Blender bone name lenth
			# CONFIRM: Truncation may or may not break compatibility with precompiled animation .mdls
			# (IDs are used but names still recorded)
			log.warning("Bone name '%s' was truncated to 32 characters." % values[1])

		if newBone.name != original_bone_name:
			newBone['smd_name'] = original_bone_name # This is the bone name that will be written to the SMD.

		# Now check if this newly-truncated name is a dupe of another
		# FIXME: this will stop working once a name has been duped 9 times!
		try:
			smd.dupeCount[newBone.name]
		except KeyError:
			smd.dupeCount[newBone.name] = 0 # Initialisation as an interger for += ops. I hate doing this and wish I could specifiy type on declaration.

		for existingName in smd.a.data.edit_bones.keys():
			if newBone.name == existingName and newBone != smd.a.data.edit_bones[existingName]:
				smd.dupeCount[existingName] += 1
				newBone.name = newBone.name[:-1] + str( smd.dupeCount[existingName] )
				try:
					smd.dupeCount[newBone.name] += 1
				except NameError:
					smd.dupeCount[newBone.name] = 1 # Initialise the new name with 1 so that numbers increase sequentially

		parentID = int(values[2])
		if parentID != -1:
			newBone.parent = a.data.edit_bones[smd.boneIDs[parentID]]
			smd.parentBones[newBone.name] = newBone.parent.name

		# Need to keep track of which armature bone = which SMD ID
		smd_id = int(values[0])
		smd.boneIDs[smd_id] = newBone.name # Quick lookup
		smd.boneNameToID[newBone.name] = smd_id

	# All bones parsed!

	ops.object.mode_set(mode='OBJECT')

def applyPoseForThisFrame(matAllRest, matAllPose):

	frame = bpy.context.scene.frame_current

	for boneName in matAllPose.keys():
		matRest = matAllRest[boneName]
		matPose = matAllPose[boneName]
		pose_bone = smd.a.pose.bones[boneName]
		if boneName in smd.parentBones:
			parentName = smd.parentBones[boneName]
			matRest = matAllRest[parentName].copy().invert() * matRest
			matPose = matAllPose[parentName].copy().invert() * matPose
		matDelta = matRest.copy().invert() * matPose

		# Rotation
		rot_quat = matDelta.to_quat()
		pose_bone.rotation_mode = 'QUATERNION'
		pose_bone.rotation_quaternion = rot_quat
		pose_bone.keyframe_insert('rotation_quaternion',-1,frame,boneName)

		# Location
		loc = matDelta.translation_part()
		pose_bone.location = loc
		pose_bone.keyframe_insert('location',-1,frame,boneName)

def cleanFCurves():

	return # <<<<<<==============

	if not smd_manager.cleanAnim:
		return

	# Example of removing a keyframe if it is the "same" as the previous and next ones.
	# Don't know what Blender considers the same (to give an orange line in the dopesheet).
	for fcurve in smd.a.animation_data.action.fcurves:
		last_frame = len(fcurve.keyframe_points)
		i = 1
		while i < last_frame - 1:
			ptPrev = fcurve.keyframe_points[i-1]
			ptCur  = fcurve.keyframe_points[i]
			ptNext = fcurve.keyframe_points[i+1]
			if abs(ptPrev.co[1] - ptCur.co[1]) <= 0.0001 and abs(ptCur.co[1] - ptNext.co[1]) <= 0.0001:
				fcurve.keyframe_points.remove(ptCur,fast=True)
				last_frame -= 1
			else:
				i += 1

	if 0:
		# the code below crashes Blender when the import finishes
		current_type = bpy.context.area.type
		bpy.context.area.type = 'GRAPH_EDITOR'
		bpy.ops.graph.clean()
		bpy.context.area.type = current_type

def readFrames():
	# We only care about the pose data in some SMD types
	if smd.jobType not in [ 'REF', 'ANIM', 'ANIM_SOLO' ]:
		return

	a = smd.a
	bones = a.data.bones
	scn = bpy.context.scene
	startFrame = bpy.context.scene.frame_current
	scn.frame_current = 0
	armature_was_hidden = smd.a.hide
	smd.a.hide = False # ensure an object is visible or mode_set() can't be called on it
	bpy.context.scene.objects.active = smd.a
	ops.object.mode_set(mode='EDIT')

	# Get a list of bone names sorted so parents come before children.
	# Only include bones in the current SMD.
	smd.sortedBoneNames = []
	sortedBones = []
	for bone in smd.a.data.bones:
		if not bone.parent:
			sortedBones.append(bone)
			for child in bone.children_recursive: # depth-first
				sortedBones.append(child)
	for bone in sortedBones:
		for key in smd.boneIDs:
			if smd.boneIDs[key] == bone.name:
				smd.sortedBoneNames.append(bone.name)
				break

	if smd.jobType in ['ANIM','ANIM_SOLO']:
		if not a.animation_data:
			a.animation_data_create()
		a.animation_data.action = bpy.data.actions.new(smd.jobName)

		# Create a new armature we can pose in edit-mode with each frame of animation.
		# This is only needed until the matrix math gets sorted out.
		ops.object.mode_set(mode='OBJECT', toggle=False)
		pose_arm_name = "pose_armature"
		pose_arm_data = bpy.data.armatures.new(pose_arm_name)
		smd.poseArm = pose_arm = bpy.data.objects.new(pose_arm_name,pose_arm_data)
		bpy.context.scene.objects.link(pose_arm)
		#bpy.context.scene.update()
		for i in bpy.context.selected_objects: i.select = False #deselect all objects
		pose_arm.select = True
		bpy.context.scene.objects.active = pose_arm
		ops.object.mode_set(mode='EDIT', toggle=False)
		for bone in smd.a.data.bones:
			pose_bone = pose_arm.data.edit_bones.new(bone.name)
			pose_bone.tail = (0,1,0)
			if bone.parent:
				pose_bone.parent = pose_arm.data.edit_bones[bone.parent.name]
		ops.object.mode_set(mode='OBJECT', toggle=False)
		pose_arm.select = False
		smd.a.select = True
		bpy.context.scene.objects.active = smd.a
		ops.object.mode_set(mode='EDIT')

	print('readFrames: upaxis is ',smd.upAxis,' jobType is ',smd.jobType)
	readFrameData() # Read in all the frames
	if smd.jobType in ['REF','ANIM_SOLO']:
		assert smd.a.mode == 'EDIT'
		applyFrameData(smd.frameData[0],restPose=True)
	if smd.jobType in ['ANIM','ANIM_SOLO']:

		# Get all the armature-space matrices for the bones at their rest positions
		smd.matAllRest = {}
		bpy.ops.object.mode_set(mode='OBJECT', toggle=False) # smd.a -> object mode
		for bone in smd.a.data.bones:
			smd.matAllRest[bone.name] = bone.matrix_local.copy()

		# Step 1: set smd.poseArm pose and store the armature-space matrices in smd.matAllPose for each frame
		smd.matAllPose = []
		bpy.context.scene.objects.active = smd.poseArm
		bpy.ops.object.mode_set(mode='EDIT') # smd.poseArm -> edit mode
		for i in range(len(smd.frameData)):
			applyFrameData(smd.frameData[i])
			bpy.context.scene.frame_current += 1

		# Step 2: set smd.a pose and set keyframes where desired for each frame
		bpy.ops.object.mode_set(mode='OBJECT', toggle=False) # smd.poseArm -> object mode
		bpy.context.scene.objects.active = smd.a
		bpy.ops.object.mode_set(mode='POSE') # smd.a -> pose mode
		bpy.context.scene.frame_set(0)
		for i in range(len(smd.frameData)):
			smd.last_frame_values = applyPoseForThisFrame( smd.matAllRest, smd.matAllPose[i] )
			bpy.context.scene.frame_current += 1

	# All frames read

	if smd.jobType in ['ANIM','ANIM_SOLO']:
		scn.frame_end = scn.frame_current

		# Remove the pose armature
		bpy.context.scene.objects.unlink(pose_arm)
		arm_data = pose_arm.data
		bpy.data.objects.remove(pose_arm)
		bpy.data.armatures.remove(arm_data)

		cleanFCurves()

	if False and smd.jobType in ['REF','ANIM_SOLO'] and smd.upAxis == 'Z' and not smd.connectBones == 'NONE':
		assert smd.a.mode == 'EDIT'
		for bone in smd.a.data.edit_bones:
			m1 = bone.matrix.copy().invert()
			for child in bone.children:
				head = (m1*child.matrix).translation_part() * smd.upAxisMat # child head relative to parent
				#print('%s head %s'%(child.name,vectorString(head)))
				if smd.connectBones == 'ALL' or (abs(head.x) < 0.0001 and abs(head.z) < 0.0001 and head.y > 0.1): # child head is on parent's Y-axis
					bone.tail = child.head
					child.use_connect = True
					# connect to the first valid bone only, otherwise bones already attached will be flung about the place
					# not perfect by any means, but it leads to the right choice in most situations
					# can't just check whether there is only one child, as there are often additional rig helper bones floating around
					break

	ops.object.mode_set(mode='OBJECT')

	def boneShouldBePoint(bone):
		if smd.connectBones == 'ALL':
			return True

		for child in bone.children:
			#if child.head == bone.tail:
			if child.use_connect:
				return False
		return True

	if False and smd.jobType in ['REF','ANIM_SOLO'] and len(smd.a.data.bones) > 1:
		# Calculate armature dimensions...Blender should be doing this!
		maxs = [0,0,0]
		mins = [0,0,0]
		for bone in smd.a.data.bones:
			for i in range(3):
				maxs[i] = max(maxs[i],bone.head_local[i])
				mins[i] = min(mins[i],bone.head_local[i])

		dimensions = []
		for i in range(3):
			dimensions.append(maxs[i] - mins[i])

		length = (dimensions[0] + dimensions[1] + dimensions[2]) / 600 # very small indeed, but a custom bone is used for display
		if length < 0.001: # Blender silently deletes bones whose length is <= 0.000001
			length = 0.001 # could be only a single bone (static prop for example)

		# Generate custom bone shape; a simple sphere
		# TODO: add axis indicators
		bone_vis = bpy.data.objects.get("smd_bone_vis")
		if not bone_vis:
			bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3,size=2)
			bone_vis = bpy.context.active_object
			bone_vis.name = bone_vis.data.name = "smd_bone_vis"
			bone_vis.use_fake_user = True
			bpy.context.scene.objects.unlink(bone_vis) # don't want the user deleting this
			bpy.context.scene.objects.active = smd.a

		bsbp = {}
		ops.object.mode_set(mode='EDIT')
		for bone in smd.a.data.edit_bones:
			bsbp[bone.name] = boneShouldBePoint(bone)
			if bsbp[bone.name]:
				bone.tail = bone.head + (bone.tail - bone.head).normalize() * length # Resize loose bone tails based on armature size

		ops.object.mode_set(mode='POSE')
		for bone in a.pose.bones:
			if bsbp[bone.name]:
				bone.custom_shape = bone_vis # apply bone shape

		ops.object.mode_set(mode='OBJECT')

	if armature_was_hidden:
		smd.a.hide = True

	print("- Imported %i frames of animation" % scn.frame_current)
	bpy.context.scene.frame_set(startFrame)

def readFrameData():
	smd.frameData = []
	frameData = {}
	HaveReadFrame = False
	for line in smd.file:

		if line == "end\n":
			smd.frameData.append(frameData)
			break

		values = line.split()

		if values[0] == "time":
			if HaveReadFrame:
				smd.frameData.append(frameData)
				frameData = {}
			HaveReadFrame = True
			continue

		# Lookup the EditBone for this SMD's bone ID.
		smdID = int(values[0])
		if not smdID in smd.boneIDs:
			continue
		boneName = smd.boneIDs[smdID]
		if not boneName in smd.a.data.edit_bones:
			continue
		bone = smd.a.data.edit_bones[boneName]

		# Where the bone should be, local to its parent
		smd_pos = vector([float(values[1]), float(values[2]), float(values[3])])
		smd_rot = vector([float(values[4]), float(values[5]), float(values[6])])

		# A bone's rotation matrix is used only by its children, a symptom of the transition from Source's 1D bones to Blender's 2D bones.
		# Also, the floats are inversed to transition them from Source (DirectX; left-handed) to Blender (OpenGL; right-handed)
		rotMat = rMat(-smd_rot.x, 3,'X') * rMat(-smd_rot.y, 3,'Y') * rMat(-smd_rot.z, 3,'Z')

		frameData[boneName] = {'pos':smd_pos, 'rot':rotMat}

	# Every bone must be listed for the first frame of an animation.
	# After the first frame a bone may not be listed in the SMD if it didn't change from a previous frame.
	for i in range(1,len(smd.frameData)):
		for boneName in smd.sortedBoneNames:
			if not boneName in smd.frameData[i]:
				smd.frameData[i][boneName] = smd.frameData[i-1][boneName]

def applyFrameData(frameData, restPose=False):

	# smd.rotMats holds the last valid parent-relative matrix we read in.  This holds the armature-relative matrix.
	rotMats = {}

	if not restPose:
		matAllPose = {}
		
	if smd_manager.upAxis == 'Z':
		tail_vec = vector([1,0,0])
		roll_vec = vector([0,1,0])
	elif smd_manager.upAxis == 'Y':
		tail_vec = vector([0,-1,0])
		roll_vec = vector([0,0,1])
		tail_vec = vector([1,0,0])
		roll_vec = vector([0,1,0])
	elif smd_manager.upAxis == 'X':
		# FIXME: same as Z for now
		tail_vec = vector([1,0,0])
		roll_vec = vector([0,1,0])

	for boneName in smd.sortedBoneNames:

		smd_pos = frameData[boneName]['pos']
		rotMats[boneName] = frameData[boneName]['rot']

		# *************************************************
		# Set rest positions. This happens only for the first frame, but not for an animation SMD.

		# rot 0 0 0 means alignment with axes
		if restPose:

			bn = smd.a.data.edit_bones[boneName]

			if bn.parent:
				rotMats[boneName] *= rotMats[bn.parent.name] # make rotations cumulative
				bn.head = bn.parent.head + (smd_pos * rotMats[bn.parent.name])
				bn.tail = bn.head + (tail_vec * rotMats[boneName])
				bn.align_roll(roll_vec * rotMats[boneName])
			else:
				'''
				if smd_manager.upAxis in ['Z','X']: # FIXME: X probably need same treatment as Y
					bn.head = smd_pos
					bn.tail = bn.head + (tail_vec * rotMats[boneName])
					bn.align_roll(roll_vec * rotMats[boneName])
				elif smd_manager.upAxis == 'Y':
					bn.head = vector((smd_pos.x,-smd_pos.z,smd_pos.y)) # same as "bn.head =  smd_pos * upAxisMat" but no loss in precision
					rotMats[boneName] = getUpAxisMat('X') * rotMats[boneName]
					bn.tail = bn.head + (tail_vec * rotMats[boneName])
					bn.align_roll(roll_vec * rotMats[boneName])
				'''
				bn.head = smd_pos
				bn.tail = bn.head + (tail_vec * rotMats[boneName])
				bn.align_roll(roll_vec * rotMats[boneName])
				
		# *****************************************
		# Set pose positions. This happens for every frame, but not for a reference pose.
		else:

			edit_bone = smd.poseArm.data.edit_bones[boneName]

			if boneName in smd.parentBones:
				parentName = smd.parentBones[boneName]
				rotMats[boneName] *= rotMats[parentName] # make rotations cumulative
				edit_bone.head = edit_bone.parent.head + (smd_pos * rotMats[parentName])
				edit_bone.tail = edit_bone.head + (tail_vec * rotMats[boneName])
				edit_bone.align_roll(roll_vec * rotMats[boneName])
			else:
				edit_bone.head = smd_pos
				edit_bone.tail = edit_bone.head + (tail_vec * rotMats[boneName])
				edit_bone.align_roll(roll_vec * rotMats[boneName])

			matAllPose[boneName] = edit_bone.matrix.copy()

	if smd_manager.upAxis == 'Y':
		#upAxisMat = rMat(-math.pi/2,3,'X')
		upAxisMat = rx90n
		for boneName in smd.sortedBoneNames:
			if restPose:
				bone = smd.a.data.edit_bones[boneName]
			else:
				bone = smd.poseArm.data.edit_bones[boneName]
			z_axis = bone.z_axis
			bone.head *= upAxisMat
			bone.tail *= upAxisMat
			#bone.align_roll(roll_vec * rotMats[boneName] * upAxisMat)
			bone.align_roll(z_axis * upAxisMat) # same as above

			if not restPose:
				matAllPose[boneName] = bone.matrix.copy()

	if not restPose:
		smd.matAllPose.append(matAllPose)

# triangles block
def readPolys():
	if smd.jobType not in [ 'REF', 'REF_ADD', 'PHYS' ]:
		return

	# Create a new mesh object, disable double-sided rendering, link it to the current scene
	if smd.jobType == 'REF' and not smd.jobName.lower().find("reference") and not smd.jobName.lower().endswith("ref"):
		meshName = smd.jobName + " ref"
	else:
		meshName = smd.jobName

	smd.m = bpy.data.objects.new(meshName,bpy.data.meshes.new(meshName))
	smd.m.data.show_double_sided = False
	smd.m.parent = smd.a
	bpy.context.scene.objects.link(smd.m)
	if smd.jobType == 'REF':
		try:
			qc.ref_mesh = smd.m # for VTA import
		except NameError:
			pass

	# Create weightmap groups
	for bone in smd.a.data.bones.values():
		smd.m.vertex_groups.new(bone.name)

	# Apply armature modifier
	modifier = smd.m.modifiers.new(type="ARMATURE",name="Armature")
	modifier.use_bone_envelopes = False # Envelopes not exported, so disable them
	modifier.object = smd.a

	# All SMD models are textured
	smd.m.data.uv_textures.new()
	mat = None

	# Initialisation
	md = smd.m.data
	lastWindowUpdate = time.time()
	# Vertex values
	cos = []
	norms = []
	weights = []
	# Face values
	uvs = []
	mats = []

	smdNameToMatName = {}
	for mat in bpy.data.materials:
		smd_name = mat['smd_name'] if mat.get('smd_name') else mat.name
		smdNameToMatName[smd_name] = mat.name

	# *************************************************************************************************
	# There are two loops in this function: one for polygons which continues until the "end" keyword
	# and one for the vertices on each polygon that loops three times. We're entering the poly one now.
	countPolys = 0
	badWeights = 0
	for line in smd.file:
		line = line.rstrip("\n")

		if line == "end" or "":
			break

		# Parsing the poly's material
		original_mat_name = line
		if original_mat_name in smdNameToMatName:
			mat_name = smdNameToMatName[original_mat_name]
		else:
			mat_name = uniqueName(line,bpy.data.materials.keys(),21) # Max 21 chars in a Blender material name :-(
			smdNameToMatName[original_mat_name] = mat_name
		mat = bpy.data.materials.get(mat_name) # Do we have this material already?
		if mat:
			if md.materials.get(mat.name): # Look for it on this mesh
				for i in range(len(md.materials)):
					if md.materials[i].name == mat_name: # No index() func on PropertyRNA :-(
						mat_ind = i
						break
			else: # material exists, but not on this mesh
				md.materials.append(mat)
				mat_ind = len(md.materials) - 1
		else: # material does not exist
			print("- New material: %s" % mat_name)
			mat = bpy.data.materials.new(mat_name)
			md.materials.append(mat)
			# Give it a random colour
			randCol = []
			for i in range(3):
				randCol.append(random.uniform(.4,1))
			mat.diffuse_color = randCol
			if smd.jobType != 'PHYS':
				mat.use_face_texture = True # in case the uninitated user wants a quick rendering
			else:
				smd.m.draw_type = 'SOLID'
			mat_ind = len(md.materials) - 1
			if len(original_mat_name) > 21: # Save the original name as a custom property.
				log.warning("Material name '%s' was truncated to 21 characters." % original_mat_name)
				md.materials[mat_ind]['smd_name'] = original_mat_name

		# Would need to do this if the material already existed, but the material will be a shared copy so this step is redundant.
		#if len(original_mat_name) > 21:
		#	md.materials[mat_ind]['smd_name'] = original_mat_name

		# Store index for later application to faces
		mats.append(mat_ind)

		# ***************************************************************
		# Enter the vertex loop. This will run three times for each poly.
		vertexCount = 0
		for line in smd.file:
			values = line.split()
			vertexCount+= 1

			# TODO: transform coords to flip model onto Blender XZY, possibly scale it too

			# Read co-ordinates and normals
			for i in range(1,4): # Should be 1,3??? Why do I need 1,4?
				cos.append( float(values[i]) )
				norms.append( float(values[i+3]) )

			# Can't do these in the above for loop since there's only two
			uvs.append( float(values[7]) )
			uvs.append( float(values[8]) )

			# Read weightmap data, this is a bit more involved
			weights.append( [] ) # Blank array, needed in case there's only one weightlink
			if len(values) > 10 and values[9] != "0": # got weight links?
				for i in range(10, 10 + (int(values[9]) * 2), 2): # The range between the first and last weightlinks (each of which is *two* values)
					boneID = int(values[i])
					if boneID in smd.boneIDs:
						boneName = smd.boneIDs[boneID]
						vertGroup = smd.m.vertex_groups.get(boneName)
						if vertGroup:
							weights[-1].append( [ vertGroup, float(values[i+1]) ] )
						else:
							badWeights += 1
					else:
						badWeights += 1
			else: # Fall back on the deprecated value at the start of the line
				boneID = int(values[0])
				if boneID in smd.boneIDs:
					boneName = smd.boneIDs[boneID]
					weights[-1].append( [smd.m.vertex_groups[boneName], 1.0] )
				else:
					badWeights += 1

			# Three verts? It's time for a new poly
			if vertexCount == 3:
				uvs.extend([0,1]) # Dunno what this 4th UV is for, but Blender needs it
				break

		# Back in polyland now, with three verts processed.
		countPolys+= 1

	if countPolys:
		# All polys processed. Add new elements to the mesh:
		md.vertices.add(countPolys*3)
		md.faces.add(countPolys)

		# Fast add!
		md.vertices.foreach_set("co",cos)
		md.vertices.foreach_set("normal",norms)
		md.faces.foreach_set("material_index", mats)
		md.uv_textures[0].data.foreach_set("uv",uvs)

		# Apply vertex groups
		for i in range(len(md.vertices)):
			for link in weights[i]:
				smd.m.vertex_groups.assign( [i], link[0], link[1], 'ADD' )

		# Build faces
		# TODO: figure out if it's possible to foreach_set() this data. Note the reversal of indices required.
		i = 0
		for f in md.faces:
			i += 3
			f.vertices = [i-3,i-2,i-1]

		# Remove doubles...is there an easier way?
		bpy.context.scene.objects.active = smd.m
		ops.object.mode_set(mode='EDIT')
		ops.mesh.remove_doubles()
		if smd.jobType != 'PHYS':
			ops.mesh.faces_shade_smooth()
		ops.object.mode_set(mode='OBJECT')

		if smd_manager.upAxis == 'Y':
			md.transform(rx90)

		if badWeights:
			log.warning(badWeights,"vertices weighted to invalid bones!")
		print("- Imported %i polys" % countPolys)

# vertexanimation block
def readShapes():
	if smd.jobType is not 'FLEX':
		return

	if not smd.m:
		try:
			smd.m = qc.ref_mesh
		except NameError:
			smd.m = bpy.context.active_object # user selection

	co_map = {}
	making_base_shape = True
	bad_vta_verts = num_shapes = 0

	for line in smd.file:
		line = line.rstrip("\n")
		if line == "end" or "":
			break
		values = line.split()

		if values[0] == "time":
			if making_base_shape and num_shapes > 0:
				making_base_shape = False

			if making_base_shape:
				smd.m.add_shape_key("Basis")
			else:
				smd.m.add_shape_key("Unnamed")

			num_shapes += 1
			continue # to the first vertex of the new shape

		cur_id = int(values[0])
		cur_cos = vector([ float(values[1]), float(values[2]), float(values[3]) ])

		if making_base_shape: # create VTA vert ID -> mesh vert ID dictionary
			# Blender faces share verts; SMD faces don't. To simulate a SMD-like list of verticies, we need to
			# perform a bit of mathematical kung-fu:
			mesh_vert_id = smd.m.data.faces[math.floor(cur_id/3)].vertices[cur_id % 3]

			if cur_cos == smd.m.data.vertices[mesh_vert_id].co:
				co_map[cur_id] = mesh_vert_id # create the new dict entry
		else:
			try:
				smd.m.data.shape_keys.keys[-1].data[ co_map[cur_id] ].co = cur_cos # write to the shapekey
			except KeyError:
				bad_vta_verts += 1


	if bad_vta_verts > 0:
		log.warning(bad_vta_verts,"VTA vertices were not matched to a mesh vertex!")
	print("- Imported",num_shapes-1,"flex shapes") # -1 because the first shape is the reference position

# Parses a QC file
def readQC( context, filepath, newscene, doAnim, connectBones, cleanAnim, outer_qc = False):
	filename = getFilename(filepath)
	filedir = getFileDir(filepath)

	global qc
	if outer_qc:
		print("\nQC IMPORTER: now working on",filename)
		qc = qc_info()
		qc.startTime = time.time()
		qc.jobName = filename
		qc.root_filedir = filedir
		qc.cleanAnim = cleanAnim
		if newscene:
			bpy.context.screen.scene = bpy.data.scenes.new(filename) # BLENDER BUG: this currently doesn't update bpy.context.scene
		else:
			bpy.context.scene.name = filename
		global smd_manager
		smd_manager = qc

	file = open(filepath, 'r')
	in_bodygroup = False
	for line in file:
		line = parseQuoteBlockedLine(line)
		if len(line) == 0:
			continue
		#print(line)

		# handle individual words (insert QC variable values, change slashes)
		for i in range(len(line)):
			if line[i].strip("$") in qc.vars:
				line[i] = qc.vars[line[i].strip("$")]
			line[i] = line[i].replace("/","\\") # studiomdl is Windows-only

		# register new QC variable
		if "$definevariable" in line:
			qc.vars[line[1]] = line[2]
			continue

		# dir changes
		if "$pushd" in line:
			if line[1][-1] != "\\":
				line[1] += "\\"
			qc.dir_stack.append(line[1])
			continue
		if "$popd" in line:
			try:
				qc.dir_stack.pop()
			except IndexError:
				pass # invalid QC, but whatever
			continue

		# up axis
		if "$upaxis" in line:
			qc.upAxis = line[1].upper()
			qc.upAxisMat = getUpAxisMat(line[1])
			continue

		def loadSMD(word_index,ext,type, multiImport=False):
			path = line[word_index]
			if line[word_index][1] == ":": # absolute path; QCs can only be compiled on Windows
				path = appendExt(path,ext)
			else:
				path = qc.cd() + appendExt(path,ext)
			if not path in qc.imported_smds: # FIXME: an SMD loaded once relatively and once absolutely will still pass this test
				qc.imported_smds.append(path)
				readSMD(context,path,qc.upAxis,connectBones,cleanAnim, False,type,multiImport,from_qc=True)
				qc.numSMDs += 1
			else:
				log.warning("Skipped repeated SMD \"%s\"\n" % getFilename(line[word_index]))

		# meshes
		if "$body" in line or "$model" in line:
			loadSMD(2,"smd",'REF',True) # create new armature no matter what
			continue
		if "replacemodel" in line:
			loadSMD(2,"smd",'REF_ADD')
			continue
		if "$bodygroup" in line:
			in_bodygroup = True
			continue
		if in_bodygroup:
			if "studio" in line:
				loadSMD(1,"smd",'REF') # bodygroups can be used to define skeleton
				continue
			if "}" in line:
				in_bodygroup = False
				continue

		# skeletal animations
		if doAnim and ("$sequence" in line or "$animation" in line):
			if not "{" in line and len(line) > 3: # an advanced $sequence using an existing $animation, or anim redefinition
				loadSMD(2,"smd",'ANIM')
			continue

		# flex animation
		if "flexfile" in line:
			loadSMD(1,"vta",'FLEX')
			continue

		# naming shapes
		if "flex" in line or "flexpair" in line: # "flex" is safe because it cannot come before "flexfile"
			for i in range(1,len(line)):
				if line[i] == "frame":
					qc.ref_mesh.data.shape_keys.keys[int(line[i+1])-1].name = line[1] # subtract 1 because frame 0 isn't a real shape key
					break
			continue

		# physics mesh
		if "$collisionmodel" in line or "$collisionjoints" in line:
			loadSMD(1,"smd",'PHYS')
			continue

		# QC inclusion
		if "$include" in line:
			if line[1][1] == ":": # absolute path; QCs can only be compiled on Windows
				path = appendExt(line[1], "qci")
			else:
				path = filedir + appendExt(line[1], "qci") # special case: ignores dir stack
			try:
				readQC(context,path,False, doAnim, connectBones, cleanAnim)
			except IOError:
				if not line[1].endswith("qci"):
					readQC(context,path[:-3]+"qc",False, doAnim, connectBones, cleanAnim)

	file.close()

	if outer_qc:
		printTimeMessage(qc.startTime,filename,"import","QC")
	return qc.numSMDs

# Parses an SMD file
def readSMD( context, filepath, upAxis, connectBones, cleanAnim, newscene = False, smd_type = None, multiImport = False, from_qc = False):
	# First, overcome Python's awful var redefinition behaviour. The smd object must be
	# explicitly deleted at the end of the script.
	if filepath.endswith("dmx"):
		print("Skipping DMX file import: format unsupported (%s)" % getFilename(filepath))
		return

	global smd
	smd	= smd_info()
	smd.jobName = getFilename(filepath)
	smd.jobType = smd_type
	smd.multiImport = multiImport
	smd.startTime = time.time()
	smd.connectBones = connectBones
	smd.cleanAnim = cleanAnim
	if upAxis:
		smd.upAxis = upAxis
		smd.upAxisMat = getUpAxisMat(upAxis)
	smd.uiTime = 0
	if not from_qc:
		global smd_manager
		smd_manager = smd

	try:
		smd.file = file = open(filepath, 'r')
	except IOError: # TODO: work out why errors are swallowed if I don't do this!
		message = "Could not open SMD file \"{}\"\n\t{}".format(smd.jobName,filepath)
		if smd_type: # called from QC import
			log.warning(message + " - skipping!")
			print("\t" + filepath)
			return
		else:
			raise IOError(message) # just error out if it's a direct SMD import

	if newscene:
		bpy.context.screen.scene = bpy.data.scenes.new(smd.jobName) # BLENDER BUG: this currently doesn't update bpy.context.scene
	elif not smd_type: # only when importing standalone
		bpy.context.scene.name = smd.jobName

	print("\nSMD IMPORTER: now working on",smd.jobName)
	if file.readline() != "version 1\n":
		log.warning ("Unrecognised/invalid SMD file. Import will proceed, but may fail!")

	if smd.jobType == None:
		scanSMD() # What are we dealing with?

	for line in file:
		if line == "nodes\n": readBones()
		if line == "skeleton\n": readFrames()
		if line == "triangles\n": readPolys()
		if line == "vertexanimation\n": readShapes()

	file.close()
	bpy.ops.object.select_all(action='DESELECT')
	smd.a.select = True
	'''
	if smd.upAxisMat and smd.upAxisMat != 1:
		if smd.jobType in ['REF','ANIM_SOLO']:
			smd.a.rotation_euler = smd.upAxisMat.to_euler()
		else:
			smd.m.rotation_euler = smd.upAxisMat.to_euler()
			smd.m.select = True
		bpy.context.scene.update()
		bpy.ops.object.rotation_apply()
	'''
	printTimeMessage(smd.startTime,smd.jobName,"import")

class SmdImporter(bpy.types.Operator):
	bl_idname = "import.smd"
	bl_label = "Import SMD/VTA/QC"
	bl_options = {'REGISTER', 'UNDO'}

	# Properties used by the file browser
	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA/QC file", maxlen=1024, default="")
	filename = StringProperty(name="Filename", description="Name of SMD/VTA/QC file", maxlen=1024, default="")
	if bpy.app.build_revision != 'unknown' and int(bpy.app.build_revision) >= 32095:
		filter_folder = BoolProperty(name="Filter folders", description="", default=True, options={'HIDDEN'})
		filter_glob = StringProperty(default="*.smd;*.qc;*.qci;*.vta", options={'HIDDEN'})
	
	# Custom properties
	multiImport = BoolProperty(name="Import SMD as new model", description="Treats an SMD file as a new Source engine model. Otherwise, it will extend anything existing.", default=False)
	doAnim = BoolProperty(name="Import animations (slow)", description="This process now works, but needs optimisation", default=True)
	#cleanAnim = BoolProperty(name="Clean animation curves",description="Removes closely-spaced keyframes. Recommended, but is slightly destructive.",default=True)
	upAxis = EnumProperty(name="Up axis",items=axes,default='Z',description="Which axis represents 'up'. Ignored for QCs.")
	connectionEnum = ( ('NONE','Do not connect (sphere bones)','All bones will be unconnected spheres'),
	('COMPATIBILITY','Connect retaining compatibility','Only connect bones that will not break compatibility with existing SMDs'),
	('ALL','Connect all','All bones that can be connected will be, disregarding backwards compatibility') )
	connectBones = EnumProperty(name="Bone Connection Mode",items=connectionEnum,description="How to choose which bones to connect together",default='COMPATIBILITY')

	def execute(self, context):
		global log
		log = logger()

		if os.name == 'nt': # windows only
			self.properties.filepath = self.properties.filepath.lower()
		cleanAnim = True # UI option can't be hidden due to Blender bug
		if self.properties.filepath.endswith('.qc') | self.properties.filepath.endswith('.qci'):
			self.countSMDs = readQC(context, self.properties.filepath, False, self.properties.doAnim, self.properties.connectBones, cleanAnim, outer_qc=True)
			bpy.context.scene.objects.active = qc.armature
		elif self.properties.filepath.endswith('.smd'):
			readSMD(context, self.properties.filepath, self.properties.upAxis, self.properties.connectBones, cleanAnim, multiImport=self.properties.multiImport)
			self.countSMDs = 1
		elif self.properties.filepath.endswith ('.vta'):
			readSMD(context, self.properties.filepath, False, self.properties.upAxis, smd_type='FLEX')
			self.countSMDs = 1
		elif self.properties.filepath.endswith('.dmx'):
			return 'CANCELLED'
			self.report('ERROR',"DMX import not supported")
		else:
			self.report('ERROR',"File format not recognised")
			return 'CANCELLED'

		log.errorReport("imported",self)
		if smd.m:
			smd.m.select = True
			for area in context.screen.areas:
				if area.type == 'VIEW_3D':
					space = area.active_space
					# FIXME: small meshes offset from their origins won't extend things far enough
					xy = int(max(smd.m.dimensions[0],smd.m.dimensions[1]))
					space.grid_lines = max(space.grid_lines, xy)
					space.clip_end = max(space.clip_end, max(xy,int(smd.m.dimensions[2])))
		if bpy.context.space_data.type == 'VIEW_3D':
			bpy.ops.view3d.view_selected()
		return 'FINISHED'

	def invoke(self, context, event):
		bpy.context.window_manager.add_fileselect(self)
		return 'RUNNING_MODAL'

class Smd_OT_ImportTextures(bpy.types.Operator):
	bl_idname = "smd_import_textures"
	bl_label = "Import textures"
	bl_description = "Browse to a directory to import textures from"

	# Properties used by the file browser
	directory = StringProperty(name="Directory:", description="Directory to search for texture image files", maxlen=1024, default="", subtype='DIR_PATH')
	filter_folder = BoolProperty(name="Filter folders", description="", default=True, options={'HIDDEN'})
	filter_image = BoolProperty(name="Filter images", description="", default=True, options={'HIDDEN'})

	def findLoadedImage(self, filepath):
		for image in bpy.data.images:
			if image.type == 'IMAGE':
				filepath2 = os.path.abspath(bpy.path.abspath(image.filepath))
				if filepath == filepath2:
					return image

	def loadImage(self, filepath):
		#print('loading %s' % filepath)
		try:
			image = bpy.data.images.load(filepath)
			return image
		except:
			print('error loading %s' % filepath)

	def tryImageName(self, dir, basename, ext):
		filepath = os.path.join(dir,basename+ext)
		#print('trying %s' % filepath)
		image = self.findLoadedImage(filepath)
		if image:
			return image
		if os.path.exists(filepath) and os.path.isfile(filepath):
			return self.loadImage(filepath)

	def materialUsesImage(self, material, image):
		for tex_slot in material.texture_slots:
			if tex_slot and tex_slot.texture and tex_slot.texture.type == 'IMAGE' and tex_slot.texture.image == image:
				return True

	def execute(self, context):
		# Get an absolute pathname to look for image files in.
		# self.directory is always absolute even when the .blend file is unsaved
		dirpath = self.directory
		print(dirpath)

		for object in context.scene.objects:
			for mat_slot in object.material_slots:
				material = mat_slot.material
				mat_name = material['smd_name'] if material.get('smd_name') else material.name
				mat_basename, mat_ext = os.path.splitext(mat_name)
				if len(mat_ext) != 4:
					mat_ext = ''
				tryExt = []
				if mat_ext != '':
					tryExt.append( mat_ext )
				if mat_ext != '.tga':
					tryExt.append( '.tga' )
				if mat_ext != '.bmp':
					tryExt.append( '.bmp' )
				for ext in tryExt:
					image = self.tryImageName(dirpath,mat_basename,ext)
					if image:
						break
				if image and not self.materialUsesImage(material,image):
					for tex_slot in material.texture_slots:
						if not tex_slot:
							texture = bpy.data.textures.new(mat_name,type='IMAGE')
							texture.image = image
							tex_slot = material.texture_slots.add()
							tex_slot.texture = texture
							tex_slot.texture_coords = 'UV'
							#tex_slot.uv_layer = 'UVTex'
							break

		return 'FINISHED'

	def invoke(self, context, event):
		context.window_manager.add_fileselect(self)
		return 'RUNNING_MODAL'

class SMD_PT_material(bpy.types.Panel):
	bl_label = "SMD Import"
	bl_space_type = 'PROPERTIES'
	bl_region_type = 'WINDOW'
	bl_context = "material"

	@classmethod
	def poll(cls, context):
		return context.material is not None

	def draw(self, context):
		layout = self.layout
		layout.operator(Smd_OT_ImportTextures.bl_idname,text='Import textures',icon='TEXTURE')

def menu_func_import(self, context):
	self.layout.operator(SmdImporter.bl_idname, text="Studiomdl Data (.smd, .vta, .qc)")

def register():
	bpy.types.INFO_MT_file_import.append(menu_func_import)

def unregister():
	bpy.types.INFO_MT_file_import.remove(menu_func_import)
