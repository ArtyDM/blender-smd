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

bl_addon_info = {
	"name": "SMD Tools",
	"author": "Tom Edwards, EasyPickins",
	"version": "0.7.1b",
	"blender": (2, 5, 4),
	"category": "Import/Export",
	"location": "File > Import/Export; Properties > Scene/Armature",
	"wiki_url": "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools",
	"tracker_url": "http://developer.valvesoftware.com/wiki/Talk:Blender_SMD_Tools",
	"description": "Importer and exporter for Valve Software's Studiomdl Data format."}

import math, os, time, bpy, random, mathutils, re, ctypes
from bpy import ops
from bpy.props import *
vector = mathutils.Vector
euler = mathutils.Euler
matrix = mathutils.Matrix
rMat = mathutils.Matrix.Rotation
tMat = mathutils.Matrix.Translation
pi = math.pi

rx90 = rMat(math.radians(90),4,'X')
ry90 = rMat(math.radians(90),4,'Y')
rz90 = rMat(math.radians(90),4,'Z')
ryz90 = ry90 * rz90

rx90n = rMat(math.radians(-90),4,'X')
ry90n = rMat(math.radians(-90),4,'Y')
rz90n = rMat(math.radians(-90),4,'Z')

# SMD types:
# 'REF' - $body, $model, $bodygroup (if before a $body or $model)
# 'REF_ADD' - $bodygroup, $lod->replacemodel
# 'PHYS' - $collisionmesh, $collisionjoints
# 'ANIM' - $sequence, $animation
# 'ANIM_SOLO' - for importing animations to scenes without an existing armature
# 'FLEX' - $model VTA

# I hate Python's var redefinition habits
class smd_info:
	def __init__(self):
		self.a = None # Armature object
		self.m = None # Mesh datablock
		self.file = None
		self.jobName = None
		self.jobType = None
		self.startTime = 0
		self.uiTime = 0
		self.started_in_editmode = None
		self.multiImport = False
		self.in_block_comment = False
		self.connectBones = False
		self.upAxis = 'Z'
		self.upAxisMat = 1 # vec * 1 == vec
		self.cleanAnim = False

		self.bakeInfo = []

		# Checks for dupe bone names due to truncation
		self.dupeCount = {}
		# boneIDs contains the ID-to-name mapping of *this* SMD's bones.
		# - Key: integer ID
		# - Value: bone name (storing object itself is not safe)
		self.boneIDs = {}

		# Reverse of the above.
		# - Key: Bone name
		# - Value: integer ID
		# NOTE: Not setting bone['smd_id'] anymore because I ran into problems with duplicating a bone -> 2 bones with same ID!
		# NOTE: Also if bones get deleted (useless rigging bones in Antlion Guard for example) there will be gaps in the IDs.
		self.boneNameToID = {}

		# For recording rotation matrices. Children access their parent's matrix.
		# USE BONE NAME STRING - MULTIPLE BONE TYPES NEED ACCESS (bone, editbone, posebone)
		self.rotMats = {}

		self.location = {}

		# Animation SMD may remove some parent bones (for example SDK buggy anims remove Gun_Parent)
		self.parentBones = {}

class qc_info:
	def __init__(self):
		self.startTime = 0
		self.imported_smds = []
		self.vars = {}
		self.ref_mesh = None # for VTA import
		self.armature = None
		self.upAxis = 'Z'
		self.upAxisMat = None
		self.numSMDs = 0
		self.cleanAnim = False

		self.in_block_comment = False

		self.jobName = ""
		self.root_filedir = ""
		self.dir_stack = []

	def cd(self):
		return self.root_filedir + "".join(self.dir_stack)

# error reporting
class logger:
	def __init__(self):
		self.warnings = []
		self.errors = []
		self.startTime = time.time()

	def warning(self, *string):
		message = " ".join(str(s) for s in string)
		printColour(STD_YELLOW," WARNING:",message)
		self.warnings.append(message)

	def error(self, caller, *string):
		message = " ".join(str(s) for s in string)
		printColour(STD_RED," ERROR:",message)
		caller.report('ERROR',message)
		self.errors.append(message)

	def errorReport(self, jobName, caller):
		message = "SMD " + jobName + " with " + str(len(self.errors)) + " errors and " + str(len(self.warnings)) + " warnings."
		print(message)

		if len(self.errors) or len(self.warnings):
			caller.report('ERROR',message)
		else:
			caller.report('INFO',str(caller.countSMDs) + " SMDs " + jobName + " in " + str(round(time.time() - self.startTime,1)) + " seconds")

##################################
#        Shared utilities        #
##################################

def getFilename(filepath):
	return filepath.split('\\')[-1].split('/')[-1].rsplit(".")[0]
def getFileDir(filepath):
	return filepath.rstrip(filepath.split('\\')[-1].split('/')[-1])

# rounds to 6 decimal places, converts between "1e-5" and "0.000001", outputs str
def getSmdFloat(fval):
	return "%0.06f" % float(fval)

# joins up "quoted values" that would otherwise be delimited, removes comments
def parseQuoteBlockedLine(line,lower=True):
	words = []
	last_word_start = 0
	in_quote = in_whitespace = False

	for i in range(len(line)):
		char = line[i]
		nchar = pchar = None
		if i < len(line)-1:
			nchar = line[i+1]
		if i > 0:
			pchar = line[i-1]

		# line comment - precedence over block comment
		if (char == "/" and nchar == "/") or char in ['#',';']:
			i = i-1 # last word will be caught after the loop
			break # nothing more this line

		#block comment
		global smd_manager
		if smd_manager.in_block_comment:
			if char == "/" and pchar == "*": # done backwards so we don't have to skip two chars
				smd_manager.in_block_comment = False
			continue
		elif char == "/" and nchar == "*": # note: nchar, not pchar
			smd_manager.in_block_comment = True
			continue

		# quote block
		if char == "\"" and not pchar == "\\": # quotes can be escaped
			in_quote = (in_quote == False)
		if not in_quote:
			if char in [" ","\t"]:
				cur_word = line[last_word_start:i].strip("\"") # characters between last whitespace and here
				if len(cur_word) > 0:
					if (lower and os.name == 'nt') or cur_word[0] == "$":
						cur_word = cur_word.lower()
					words.append(cur_word)
				last_word_start = i+1 # we are in whitespace, first new char is the next one

	# catch last word and any '{'s crashing into it
	needBracket = False
	cur_word = line[last_word_start:i]
	if cur_word.endswith("{"):
		needBracket = True

	cur_word = cur_word.strip("\"{")
	if len(cur_word) > 0:
		words.append(cur_word)

	if needBracket:
		words.append("{")

	return words

def appendExt(path,ext):
	if not path.lower().endswith("." + ext) and not path.lower().endswith(".dmx"):
		path += "." + ext
	return path

def printTimeMessage(start_time,name,job,type="SMD"):
	elapsedtime = int(time.time() - start_time)
	if elapsedtime == 1:
		elapsedtime = "1 second"
	elif elapsedtime > 1:
		elapsedtime = str(elapsedtime) + " seconds"
	else:
		elapsedtime = "under 1 second"

	print(type,name,"{}ed successfully in".format(job),elapsedtime,"\n")

try:
	kernel32 = ctypes.windll.kernel32
	STD_RED = 0x04
	STD_YELLOW = 0x02|0x04
	STD_WHITE = 0x01|0x02|0x04
	def stdOutColour(colour):
		kernel32.SetConsoleTextAttribute(kernel32.GetStdHandle(-11),colour|0x08)
	def stdOutReset():
		kernel32.SetConsoleTextAttribute(kernel32.GetStdHandle(-11),STD_WHITE)
	def printColour(colour,*string):
		stdOutColour(colour)
		print(*string)
		stdOutReset()
except AttributeError:
	STD_RED = STD_YELLOW = STD_WHITE = None
	def stdOutColour(colour):
		pass
	def stdOutReset():
		pass
	def printColour(colour,*string):
		print(*string)

def getUpAxisMat(axis):
	if axis.upper() == 'X':
		return rMat(pi/2,4,'Y')
	if axis.upper() == 'Y':
		return rMat(pi/2,4,'X')
	if axis.upper() == 'Z':
		return 1 # vec * 1 == vec
	else:
		raise AttributeError("getUpAxisMat got invalid axis argument '{}'".format(axis))

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

def getRotAsEuler(thing):
	out = vector()
	mode = thing.rotation_mode
	if len(mode) == 3: # matches XYZ and variants
		# CRIKEY! But exec() is needed to turn the rotation_mode string into a property on the vector
		exec("out." + thing.rotation_mode.lower() + " = vector(thing.rotation_euler) * ryz90")
	elif mode == 'QUATERNION':
		out = thing.rotation_quaternion.to_euler()
	elif mode == 'AXIS_ANGLE':
		# Blender provides no conversion function!
		x = thing.rotation_axis_angle[0]
		y = thing.rotation_axis_angle[1]
		z = thing.rotation_axis_angle[2]
		ang = thing.rotation_axis_angle[3]
		s = math.sin(ang)
		c = math.cos(ang)
		t = 1-c
		if (x*y*t + z*s) > 0.998: # north pole singularity
			out.x = 2 * math.atan2( x*math.sin(ang/2), math.cos(ang/2) )
			out.y = pi/2
			out.z = 0
		elif (x*y*t + z*s) < -0.998: # south pole singularity
			out.x = -2 * math.atan2( x*math.sin(ang/2), math.cos(ang/2) )
			out.y = -pi/2
			out.z = 0
		else:
			out.x = math.atan2(y * s- x * z * t , 1 - (y*y+ z*z ) * t)
			out.y = math.asin(x * y * t + z * s)
			out.z = math.atan2(x * s - y * z * t , 1 - (x*x + z*z) * t)
	else:
		log.error(smd,thing.name,"uses an unknown rotation mode.")
	return out

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
	a = smd.a = bpy.data.objects.new(smd_manager.jobName,bpy.data.armatures.new(smd_manager.jobName))
	a.show_x_ray = True
	a.data.use_deform_envelopes = False # Envelope deformations are not exported, so hide them
	a.data.draw_type = 'STICK'
	a.data.smd_bone_up_axis = smd.upAxis
	bpy.context.scene.objects.link(a)
	for i in bpy.context.scene.objects: i.select = False #deselect all objects
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
		for i in bpy.context.scene.objects: i.select = False #deselect all objects
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

	readFrameData() # Read in all the frames
	if smd.jobType in ['REF','ANIM_SOLO']:
		assert smd.a.mode == 'EDIT'
		applyFrameData(smd.frameData[0],restPose=True)
	if smd.jobType in ['ANIM','ANIM_SOLO']:

		# Get all the armature-space matrices for the bones at their rest positions
		smd.matAllRest = {}
		for bone in smd.a.data.bones:
			smd.matAllRest[bone.name] = bone.matrix_local.copy()

		# Step 1: set smd.poseArm pose and store the armature-space matrices in smd.matAllPose for each frame
		smd.matAllPose = []
		bpy.ops.object.mode_set(mode='OBJECT', toggle=False) # smd.a -> object mode
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

	if smd.upAxis == 'Z' and not smd.connectBones == 'NONE':
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

		childConnect = False
		for child in bone.children:
			if child.head == bone.tail:
				return False
		return True

	if smd.jobType in ['REF','ANIM_SOLO']:
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

		# Generate custom bone shape; a simple sphere
		# TODO: add axis indicators
		bone_vis = bpy.data.objects.get("smd_bone_vis")
		if not bone_vis:
			bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3,size=2)
			bone_vis = bpy.context.active_object
			bone_vis.data.name = "smd_bone_vis"
			bone_vis.use_fake_user = True
			bpy.context.scene.objects.unlink(bone_vis) # don't want the user deleting this
			bpy.context.scene.objects.active = smd.a

		for bone in a.pose.bones:
			if boneShouldBePoint(bone):
				bone.custom_shape = bone_vis # apply bone shape

		ops.object.mode_set(mode='EDIT')
		for bone in smd.a.data.edit_bones:
			if boneShouldBePoint(bone):
				bone.tail = bone.head + (bone.tail - bone.head).normalize() * length # Resize loose bone tails based on armature size
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
				bn.tail = bn.head + (vector([1,0,0]) * rotMats[boneName])
				bn.align_roll(vector([0,1,0]) * rotMats[boneName])

				# $upaxis Y
				if False:
					bn.tail = bn.head + (vector([0,-1,0]) * rotMats[boneName]) # maya bones point down X
					bn.align_roll(vector([0,0,1]) * rotMats[boneName])
			else:
				bn.head = smd_pos # LOCATION WITH NO PARENT
				bn.tail = bn.head + (vector([1,0,0]) * rotMats[boneName])
				bn.align_roll(vector([0,1,0]) * rotMats[boneName])

				# $upaxis Y
				if False:
					upAxisMat = rMat(-math.pi/2,3,'X')
					bn.head = vector((smd_pos.x,-smd_pos.z,smd_pos.y)) # same as "bn.head =  smd_pos * upAxisMat" but no loss in precision
					rotMats[boneName] = upAxisMat * rotMats[boneName]
					bn.tail = bn.head + (vector([0,-1,0]) * rotMats[boneName])
					bn.align_roll(vector([0,0,1]) * rotMats[boneName])

		# *****************************************
		# Set pose positions. This happens for every frame, but not for a reference pose.
		else:

			edit_bone = smd.poseArm.data.edit_bones[boneName]

			if boneName in smd.parentBones:
				parentName = smd.parentBones[boneName]
				rotMats[boneName] *= rotMats[parentName] # make rotations cumulative
				edit_bone.head = edit_bone.parent.head + (smd_pos * rotMats[parentName])
				edit_bone.tail = edit_bone.head + (vector([1,0,0]) * rotMats[boneName])
				edit_bone.align_roll(vector([0,1,0]) * rotMats[boneName])
			else:
				edit_bone.head = smd_pos # LOCATION WITH NO PARENT
				edit_bone.tail = edit_bone.head + (vector([1,0,0]) * rotMats[boneName])
				edit_bone.align_roll(vector([0,1,0]) * rotMats[boneName])

			matAllPose[boneName] = edit_bone.matrix.copy()

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

	if smd.upAxisMat and smd.upAxisMat != 1:
		if smd.jobType in ['REF','ANIM_SOLO']:
			smd.a.rotation_euler = smd.upAxisMat.to_euler()
		else:
			smd.m.rotation_euler = smd.upAxisMat.to_euler()
			smd.m.select = True
		bpy.context.scene.update()
		bpy.ops.object.rotation_apply()

	printTimeMessage(smd.startTime,smd.jobName,"import")

axes = (('X','X','X axis'),('Y','Y','Y axis'),('Z','Z','Z axis'))

class SmdImporter(bpy.types.Operator):
	bl_idname = "import.smd"
	bl_label = "Import SMD/VTA/QC"
	bl_options = {'REGISTER', 'UNDO'}

	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA/QC file", maxlen=1024, default="")
	filename = StringProperty(name="Filename", description="Name of SMD/VTA/QC file", maxlen=1024, default="")
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

########################
#        Export        #
########################

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

def bakeObj(object):
	bi = {}
	bi['object'] = object

	# make a new datablock and back up user settings
	bi['user_data'] = object.data
	bi['baked_data'] = object.data = object.data.copy()
	bi['loc'] = object.location.copy()
	bi['rot'] = object.rotation_euler.copy()
	bi['scale'] = object.scale.copy()

	if object.type == 'MESH':
		# quads > tris
		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.context.scene.objects.active = object
		object.select=True
		bpy.ops.object.mode_set(mode='EDIT')
		bpy.ops.mesh.select_all(action='SELECT')
		bpy.ops.mesh.quads_convert_to_tris()
		bpy.ops.object.mode_set(mode='OBJECT')

		if object.parent or object.find_armature(): # don't translate standalone meshes
			bpy.ops.object.location_apply()

	# Do rot and scale on both meshes and armatures
	bpy.ops.object.rotation_apply()
	bpy.ops.object.scale_apply()

	smd.bakeInfo.append(bi) # save to manager

def unBake():
	for bi in smd.bakeInfo:
		object = bi['object']

		object.data = bi['user_data']
		object.location = bi['loc']
		object.rotation_euler = bi['rot']
		object.scale = bi['scale']

		if object.type == 'MESH':
			bpy.data.meshes.remove(bi['baked_data'])
		elif object.type == 'ARMATURE':
			bpy.data.armatures.remove(bi['baked_data'])

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
			if smd.a.data.smd_bone_up_axis != 'Z':
				smd.a.rotation_euler = getUpAxisMat(smd.a.data.smd_bone_up_axis).invert().to_euler()
				for object in bpy.context.scene.objects:
					object.select = False
				smd.a.select = True
				bpy.ops.object.rotation_apply() # this doesn't affect the armature post-export because it's already been baked
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

	def draw(self, context):
		l = self.layout
		scene = context.scene

		self.embed_scene = l.row()
		SMD_MT_ExportChoice.draw(self,context)

		l.prop(scene,"smd_path",text="Output Folder")

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
		if smd_test_suite:
			l.operator(smd_test_suite.SmdTestSuite.bl_idname,text="Run test suite",icon='FILE_TICK')

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
		l.prop(arm.data,"smd_bone_up_axis",text="Target Up Axis")

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
		path = bpy.path.abspath(getFileDir(props.filepath) + subdir)
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

#####################################
#        Shared registration        #
#####################################

type = bpy.types

def menu_func_import(self, context):
	self.layout.operator(SmdImporter.bl_idname, text="Studiomdl Data (.smd, .vta, .qc)")

def menu_func_export(self, context):
	self.layout.operator(SmdExporter.bl_idname, text="Studiomdl Data (.smd, .vta)")

def register():
	type.INFO_MT_file_import.append(menu_func_import)
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

	type.Object.smd_export = BoolProperty(name="SMD Scene Export",description="Export this object with the scene",default=True)
	type.Object.smd_subdir = StringProperty(name="SMD Subfolder",description="Location, relative to scene root, for SMDs from this object")
	type.Object.smd_action_filter = StringProperty(name="SMD Action Filter",description="Only actions with names matching this filter will be exported")

	type.Armature.smd_bone_up_axis = EnumProperty(name="SMD Bone Up Axis",items=axes,default='Z',description="The up axis of bones in the target reference mesh")

def unregister():
	type.INFO_MT_file_import.remove(menu_func_import)
	type.INFO_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
	register()

# this must come last; needs direct function/object access
try:
	import smd_test_suite
	bpy.types.register(smd_test_suite.SmdTestSuite)
except:
	smd_test_suite = False
