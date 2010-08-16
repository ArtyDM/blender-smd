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
	"author": "Tom Edwards",
	"version": "0.5",
	"blender": (2, 5, 3),
	"category": "Import/Export",
	"location": "File > Import/ File > Export",
	"warning": 'No animation support yet',
	"wiki_url": "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools",
	"tracker_url": "http://developer.valvesoftware.com/wiki/Talk:Blender_SMD_Tools",
	"description": "Importer and exporter for Valve Software's StudioMdl Data format."}

import math, os, time, bpy, random, mathutils
from bpy import ops
from bpy.props import *
vector = mathutils.Vector
euler = mathutils.Euler
matrix = mathutils.Matrix
rMat = mathutils.RotationMatrix
tMat = mathutils.TranslationMatrix

# SMD types:
# 'REF' - $body, $model, $bodygroup (if before a $body or $model)
# 'REF_ADD' - $bodygroup, $lod replacemodel
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
		self.maintainBoneRot = False
		self.in_block_comment = False
		
		# Checks for dupe bone names due to truncation
		self.dupeCount = {}
		# boneIDs contains the ID-to-name mapping of *this* SMD's bones.
		# - Key: ID (as string due to potential storage in registry)
		# - Value: bone name (storing object itself is not safe)
		# Use boneOfID(id) to easily look up a value from here
		self.boneIDs = {}
		
		# For recording rotation matrices. Children access their parent's matrix.
		# USE BONE NAME STRING - MULTIPLE BONE TYPES NEED ACCESS (bone, editbone, posebone)
		self.rotMats = {}

class qc_info:
	def __init__(self):
		self.startTime = 0
		self.imported_smds = []
		self.vars = {}
		self.ref_mesh = None # for VTA import
		self.armature = None
		self.maintainBoneRot = False
		self.numSMDs = 0
		
		self.in_block_comment = False
		
		self.root_filename = ""
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
		print("** WARNING:",message)
		self.warnings.append(message)
	
	def error(self, caller, *string):
		message = " ".join(str(s) for s in string)
		print("** ERROR:",message)
		caller.report('ERROR',message)
		self.errors.append(message)
		
	def errorReport(self, jobName, caller):
		message = "Encountered " + str(len(self.errors)) + " errors and " + str(len(self.warnings)) + " warnings during SMD " + jobName + "."
		print(message)
		
		if len(self.errors) or len(self.warnings):
			caller.report('ERROR',message)
		else:
			caller.report('INFO',str(caller.countSMDs) + " SMDs " + jobName + "ed in " + str(round(time.time() - self.startTime,1)) + " seconds")
	

##################################
#        Shared utilities        #
##################################

def getFilename(filepath):
	return filepath.split('\\')[-1].split('/')[-1].rsplit(".")[0]
def getFileDir(filepath):
	return filepath.rstrip(filepath.split('\\')[-1].split('/')[-1])
	
# rounds to 6 decimal places, converts between "1e-5" and "0.000001", outputs str
def getSmdFloat(fval):
	return "%f" % round(float(fval),6)

# joins up "quoted values" that would otherwise be delimited, removes comments
def parseQuoteBlockedLine(line):
	line = line.lower()
	words = []
	last_word_start = 0
	in_quote = in_whitespace = False
	for i in range(len(line)):

		char = line[i]
		try: nchar = line[i+1]
		except IndexError: nchar = None
		try: pchar = line[i-1]
		except IndexError: pchar = None
		
		# line comment - precedence over block comment
		if (char == "/" and nchar == "/") or char in ['#',';']:
			i = i-1 # last word will be caught after the loop
			break # nothing more this line
		
		#block comment
		try:
			manager = qc
		except NameError:
			manager = smd

		if manager.in_block_comment:
			if char == "/" and pchar == "*": # done backwards so we don't have to skip two chars
				manager.in_block_comment = False
			continue
		elif char == "/" and nchar == "*":
			manager.in_block_comment = True
			continue
		
		# quote block
		if char == "\"" and not pchar == "\\": # quotes can be escaped
			in_quote = (in_quote == False)
		if not in_quote:
			if char in [" ","\t"]:
				cur_word = line[last_word_start:i].strip("\"") # characters between last whitespace and here
				if len(cur_word) > 0:
					words.append(cur_word)
				last_word_start = i+1 # we are in whitespace, first new char is the next one
	
	# catch last word, removing '{'s crashing into it (char not currently used)
	cur_word = line[last_word_start:i].strip("\"{")
	if len(cur_word) > 0:
		words.append(cur_word)

	return words
	
def appendExt(path,ext):
	if not path.endswith("." + ext) and not path.endswith(".dmx"):
		path += "." + ext
	return path

def boneOfID(id):
	if bpy.context.mode == 'EDIT_ARMATURE':
		boneList = smd.a.data.edit_bones
	else:
		boneList = smd.a.data.bones
	
	for bone in boneList:
		if bone.get('smd_id') == int(id):
			return bone
	
	#log.warning("Could not find bone of ID",id) # FIXME: slow if SMD is broken
	return None
		
def printTimeMessage(start_time,name,job,type="SMD"):
	elapsedtime = int(time.time() - start_time)
	if elapsedtime == 1:
		elapsedtime = "1 second"
	elif elapsedtime > 1:
		elapsedtime = str(elapsedtime) + " seconds"
	else:
		elapsedtime = "under 1 second"
	
	print(type,name,"{}ed successfully in".format(job),elapsedtime,"\n")
	
def matrixToEuler( matrix ):
	euler = matrix.to_euler()
	return vector( [-euler.x, euler.y, -euler.z] )
	
def vector_by_matrix( m, p ):
  return vector( [	p[0] * m[0][0] + p[1] * m[1][0] + p[2] * m[2][0],
					p[0] * m[0][1] + p[1] * m[1][1] + p[2] * m[2][1],
					p[0] * m[0][2] + p[1] * m[1][2] + p[2] * m[2][2]] )

# CONFIRM THIS: OpenGL (Blender) is left-handed, DirectX (Source) is right-handed
def matrix_reverse_handedness( matrix ):
	axisX = vector( [ -matrix[0][1], -matrix[0][0], matrix[0][2], 0 ] )
	axisX.normalize()
	axisY = vector( [ -matrix[1][1], -matrix[1][0], matrix[1][2], 0 ] )
	axisY.normalize()
	axisZ = vector( [ -matrix[2][1], -matrix[2][0], matrix[2][2], 0 ] )
	axisZ.normalize()
	pos = vector( [ -matrix[3][1], -matrix[3][0], matrix[3][2], 1 ] )
	return mathutils.Matrix( axisY, axisX, axisZ, pos )
	
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
	
# Runs instead of readBones if an armature already exists, testing the current SMD's nodes block against it.
def validateBones():
	ignoreErrors = False
	
	# Copy stored data to smd.boneIDs, assigning new IDs if applicable
	for existingBone in smd.a.data.bones:
		try:
			smd.boneIDs[ existingBone['smd_id'] ] = existingBone
		except KeyError:
			smd.boneIDs.append(existingBone)
			existingBone['smd_id'] = len(smd.boneIDs)
		
	for line in smd.file:
		if line == "end\n":
			break
		values = line.split()
		errors = False

		
	#		if values[2] != "-1" and boneOfID(values[2]).name != boneOfID(values[0]).parent.name:
	#			errors = True
	#	except:
	#		errors = True

		if errors and not ignoreErrors:
			smd.uiTime = time.time()
			log.warning("skeleton failed validation against %s! Awaiting user input..." % smd.a.name)
			#retVal = Blender.Draw.PupMenu( smd.jobName + " failed skeleton validation%t|Ignore once|Ignore all errors in SMD|Create new scene|Abort")
			#if retVal == 1:
			#	print("           ...ignoring this error.")
			#if retVal == -1 or 2:
			#	print("           ...ignoring all errors in this SMD.")
			#	ignoreErrors = True
			#if retVal == 3: # New scene
			#	print("           New scene not implemented")
			#if retVal == 4:
			#	print("           ...aborting!")
			#	sys.exit()
			#	return # TODO: work out how to cleanly abort the whole script
			
			smd.uiTime = time.time() - smd.uiTime

	# datablock has been read
	print("- SMD bones validated against \"%s\" armature" % smd.a.name)

# nodes block
def readBones():
	#Blender.Window.DrawProgressBar( 0, "Skeleton..." )

	if not smd.multiImport:
		# Search the current scene for an existing armature - can only be one skeleton in a Source model
		for a in bpy.context.scene.objects:
			# Currently assuming that the first armature is the one to go for...there shouldn't be any others in the scene
			if a.type == 'ARMATURE':
				smd.a = a
				if smd.jobType == 'REF':
					smd.jobType = 'REF_ADD'
				validateBones()
				return
	
	# Got this far? Then this is a fresh import which needs a new armature.
	try:
		arm_name = qc.root_filename
	except NameError:
		arm_name = smd.jobName
	a = smd.a = bpy.data.objects.new(arm_name,bpy.data.armatures.new(arm_name))
	a.x_ray = True
	a.data.deform_envelope = False # Envelope deformations are not exported, so hide them
	a.data.drawtype = 'STICK'
	bpy.context.scene.objects.link(a)
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
		values = parseQuoteBlockedLine(line)

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
			newBone['smd_name'] = original_bone_name
		
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

		if values[2] != "-1":
			newBone.parent = boneOfID(values[2])

		# Need to keep track of which armature bone = which SMD ID
		smd.boneIDs[ int(values[0]) ] = newBone.name # Quick lookup
		newBone['smd_id'] = int(values[0]) # Persistent, and stored on each bone so handles deletion

	# All bones parsed!
	
	ops.object.mode_set(mode='OBJECT')

# skeleton block
def readFrames():
	# We only care about the pose data in some SMD types
	if smd.jobType not in [ 'REF', 'ANIM', 'ANIM_SOLO' ]:
		return
	
	a = smd.a
	bones = a.data.bones
	scn = bpy.context.scene
	startFrame = bpy.context.scene.frame_current
	scn.frame_current = 0
	bpy.context.scene.objects.active = smd.a
	ops.object.mode_set(mode='EDIT')
	
	if smd.jobType is 'ANIM' or 'ANIM_SOLO':
		ac = bpy.data.actions.new(smd.jobName)
		if not a.animation_data:
			a.animation_data_create()
		a.animation_data.action = ac
		
	# Enter the pose-reading loop
	for line in smd.file:
		if line == "end\n":
			break

		values = line.split()
		if values[0] == "time":
			scn.frame_current += 1
			if scn.frame_current == 2 and smd.jobType == 'ANIM_SOLO':
				# apply smd_rot properties
				ops.object.mode_set(mode='OBJECT')
				ops.object.mode_set(mode='EDIT')
			continue # skip to next line

		# The current bone
		bn = boneOfID(values[0])
		if not bn:
			#print("Invalid bone ID %s; skipping..." % values[0])
			continue
			
		# Where the bone should be, local to its parent
		destOrg = vector([float(values[1]), float(values[2]), float(values[3])])
		# A bone's rotation matrix is used only by its children, a symptom of the transition from Source's 1D bones to Blender's 2D bones.
		# Also, the floats are inversed to transition them from Source (DirectX; left-handed) to Blender (OpenGL; right-handed)
		smd.rotMats[bn.name] = rMat(-float(values[4]), 3,'X') * rMat(-float(values[5]), 3,'Y') * rMat(-float(values[6]), 3,'Z')
		
		# *************************************************
		# Set rest positions. This happens only for the first frame, but not for an animation SMD.
		
		# rot 0 0 0 means alignment with axes
		if smd.jobType is 'REF' or (smd.jobType is 'ANIM_SOLO' and scn.frame_current == 1):

			if bn.parent:
				smd.rotMats[bn.name] *= smd.rotMats[bn.parent.name] # make rotations cumulative
				bn.transform(smd.rotMats[bn.parent.name]) # ROTATION
				bn.translate(bn.parent.head + (destOrg * smd.rotMats[bn.parent.name]) ) # LOCATION
				bn.tail = bn.head + (vector([0,0,1])*smd.rotMats[bn.name]) # Another 1D to 2D artifact. Bones must point down the Y axis so that their co-ordinates remain stable
				bn.roll = float(values[6])
				recurse_parent = bn.parent
				while recurse_parent:
					bn.roll += recurse_parent.roll
					try:
						recurse_parent = parent.parent
					except:
						break
				bn.roll = bn.roll % math.pi
				
			else:
				bn.translate(destOrg) # LOCATION WITH NO PARENT
				bn.tail = bn.head + (vector([0,0,1])*smd.rotMats[bn.name])
				bn.roll = float(values[6])
				#bn.transform(smd.rotMats[bn.name])
			
			
			
		# *****************************************
		# Set pose positions. This happens for every frame, but not for a reference pose.
		elif smd.jobType in [ 'ANIM', 'ANIM_SOLO' ]:
			pbn = smd.a.pose.bones[ boneOfID(values[0]).name ]
			# Blender stores posebone positions as offsets of their *rest* location. Source stores them simply as offsets of their parent.
			# Thus, we must refer to the rest bone when positioning.
			bn = smd.a.data.bones[pbn.name]
			pbn.rotation_mode = 'XYZ'
			
			smd_rot = vector(bn['smd_rot'])
			ani_rot = vector([float(values[4]),float(values[5]),float(values[6])])
			
			pbn.rotation_euler = (ani_rot - smd_rot)
			
			if bn.parent:
				smd.rotMats[bn.name] *= smd.rotMats[bn.parent.name] # make rotations cumulative
				pbn.location = destOrg * smd.rotMats[bn.parent.name] - (bn.head_local - bn.parent.head_local)
			else:
				pbn.location = destOrg - bn.head_local
				
			# TODO: compare to previous frame and only insert if different
			pbn.keyframe_insert('location') # ('location', 0)
			pbn.keyframe_insert('rotation_euler')

	
	# All frames read	
	
	if smd.jobType in ['ANIM','ANIM_SOLO']:
		scn.frame_end = scn.frame_current
		
	if smd.jobType in ['REF','ANIM_SOLO']:
		# Take a stab at parent-child connections. Not fully effective since only one child can be linked, so I
		# assume that the first child is the one to go for. It /usually/ is.
		for bn in smd.a.data.edit_bones:
			if not smd.maintainBoneRot and len(bn.children) > 0:
				bn.tail = bn.children[0].head
				bn.children[0].connected = True
	
	# TODO: clean curves automagically (ops.graph.clean)

	ops.object.mode_set(mode='OBJECT')	
	
	print("- Imported %i frames of animation" % scn.frame_current)
	scn.frame_current = startFrame
	
# triangles block - also resizes loose bone tails based on reference mesh dimensions
def readPolys():
	if smd.jobType not in [ 'REF', 'REF_ADD', 'PHYS' ]:
		return

	# Create a new mesh object, disable double-sided rendering, link it to the current scene
	if smd.jobType == 'REF' and not smd.jobName.lower().find("reference") and not smd.jobName.lower().endswith("ref"):
		meshName = smd.jobName + " ref"
	else:
		meshName = smd.jobName
	
	smd.m = bpy.data.objects.new(meshName,bpy.data.meshes.new(meshName))
	smd.m.data.double_sided = False
	smd.m.parent = smd.a
	bpy.context.scene.objects.link(smd.m)
	if smd.jobType == 'REF':
		try:
			qc.ref_mesh = smd.m # for VTA import
		except NameError:
			pass
	
	#TODO: put meshes in separate layers
	
	# Create weightmap groups
	for bone in smd.a.data.bones.values():
		smd.m.add_vertex_group(name=bone.name)

	# Apply armature modifier
	modifier = smd.m.modifiers.new(type="ARMATURE",name="Armature")
	modifier.use_bone_envelopes = False # Envelopes not exported, so disable them
	modifier.object = smd.a

	# All SMD models are textured
	smd.m.data.add_uv_texture()
	mat = None

	# Initialisation
	md = smd.m.data
	lastWindowUpdate = time.time()
	# Vertex values
	cos = []
	uvs = []
	norms = []
	weights = []
	# Face values
	mats = []

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
		line = line[:21] # Max 21 chars in a Blender material name :-(
		try:
			mat = bpy.context.main.materials[line] # Do we have this material already?
			try:
				md.materials[mat.name] # Look for it on this mesh
				for i in range(len(md.materials)):
					if md.materials[i].name == line: # No index() func on PropertyRNA :-(
						mat_ind = i
			except KeyError: # material exists, but not on this mesh
				md.add_material(mat)
				mat_ind = len(md.materials) - 1
		except KeyError: # material does not exist
			print("- New material: %s" % line)
			mat = bpy.context.main.materials.new(name=line)
			md.add_material(mat)
			# Give it a random colour
			randCol = []
			for i in range(3):
				randCol.append(random.uniform(.4,1))
			mat.diffuse_color = randCol
			if smd.jobType != 'PHYS':
				mat.face_texture = True # in case the uninitated user wants a quick rendering
			else:
				smd.m.max_draw_type = 'SOLID'
			mat_ind = len(md.materials) - 1
			
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
					try:
						weights[-1].append( [ smd.m.vertex_groups[boneOfID(values[i]).name], float(values[i+1]) ] ) # [Pointer to the vert group, Weight]
					except AttributeError:
						badWeights += 1
			else: # Fall back on the deprecated value at the start of the line
				weights[-1].append( [smd.m.vertex_groups[boneOfID(values[0]).name], 1.0] )

			# Three verts? It's time for a new poly
			if vertexCount == 3:
				# Dunno what the 4th UV is for, but Blender needs it
				uvs.append( 0.0 )
				uvs.append( 1.0 )
				break

		# Back in polyland now, with three verts processed.
		countPolys+= 1
		
	
	if countPolys:
		# All polys processed. Add new elements to the mesh:
		md.add_geometry(countPolys*3,0,countPolys)

		# Fast add!
		md.verts.foreach_set("co",cos)
		md.verts.foreach_set("normal",norms)
		md.faces.foreach_set("material_index", mats)
		md.uv_textures[0].data.foreach_set("uv",uvs)
		
		# Apply vertex groups
		i = 0
		for v in md.verts:
			for link in weights[i]:
				smd.m.add_vertex_to_group( i, link[0], link[1], 'ADD' )
			i += 1
		
		# Build faces
		# TODO: figure out if it's possible to foreach_set() this data. Note the reversal of indices required.
		i = 0
		for f in md.faces:
			i += 3
			f.verts = [i-3,i-2,i-1]
		
		# Remove doubles...is there an easier way?
		bpy.context.scene.objects.active = smd.m
		ops.object.mode_set(mode='EDIT')
		ops.mesh.remove_doubles()
		if smd.jobType != 'PHYS':
			ops.mesh.faces_shade_smooth()
		ops.object.mode_set(mode='OBJECT')
		
		if smd.jobType in ['REF','ANIM_SOLO']:
			# Go back to the armature and resize loose bone tails based on mesh size
			bpy.context.scene.objects.active = smd.a
			ops.object.mode_set(mode='EDIT')
			length = (smd.m.dimensions[0] + smd.m.dimensions[1] + smd.m.dimensions[2] / 3) / 60 # 1/60th average dimension
			for bone in smd.a.data.edit_bones:
				if len(bone.children) == 0 or smd.maintainBoneRot:
					bone.tail = bone.head + vector([0,0,length]) * smd.rotMats[bone.name] # This is wrong!			
			ops.object.mode_set(mode='OBJECT')
				
		
		if badWeights:
			log.warning(badWeights,"vertices weighted to invalid bones!")
		print("- Imported %i polys" % countPolys)

#	# delete empty vertex groups - they don't deform, so aren't relevant
#	for vertGroup in smd.m.vertex_groups:
#		if not smd.m.getVertsFromGroup(vertGroup):
#			smd.m.removeVertGroup(vertGroup)
#			# DON'T delete the bone as well! It may be required for future imports
#			# TODO: place bones without verts in a different armature layer?
	
	# triangles complete!

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
				smd.m.add_shape_key()
			
			num_shapes += 1
			continue # to the first vertex of the new shape
		
		cur_id = int(values[0])
		cur_cos = vector([ float(values[1]), float(values[2]), float(values[3]) ])
		
		if making_base_shape: # create VTA vert ID -> mesh vert ID dictionary
			# Blender faces share verts; SMD faces don't. To simulate a SMD-like list of verticies, we need to
			# perform a bit of mathematical kung-fu:
			mesh_vert_id = smd.m.data.faces[math.floor(cur_id/3)].verts[cur_id % 3]
			
			if cur_cos == smd.m.data.verts[mesh_vert_id].co:
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
def readQC( context, filepath, newscene, doAnim, outer_qc = False, maintainBoneRot = False):
	filename = getFilename(filepath)
	filedir = getFileDir(filepath)
	
	global qc
	if outer_qc:
		print("\nQC IMPORTER: now working on",filename)
		qc = qc_info()
		qc.startTime = time.time()
		qc.root_filename = filename
		qc.root_filedir = filedir
		qc.maintainBoneRot = maintainBoneRot
		if newscene:
			bpy.context.screen.scene = bpy.data.scenes.new(filename) # BLENDER BUG: this currently doesn't update bpy.context.scene
		else:
			bpy.context.scene.name = filename
	
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
				
		def loadSMD(word_index,ext,type, multiImport=False):
			path = qc.cd() + appendExt(line[word_index],ext)
			if not path in qc.imported_smds or type == 'FLEX':
				qc.imported_smds.append(path)
				readSMD(context,path,False,type,multiImport,qc.maintainBoneRot)
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
			if not "{" in line: # an advanced $sequence using an existing $animation
				loadSMD(line[2],"smd",'ANIM')
			continue
		
		# flex animation
		if "flexfile" in line:
			loadSMD(1,"vta",'FLEX')
			continue
			
		# physics mesh
		if "$collisionmodel" in line or "$collisionjoints" in line:
			loadSMD(1,"smd",'PHYS')
			continue
		
		# QC inclusion
		if "$include" in line:
			try:
				readQC(context,filedir + appendExt(line[1], "qci"),False, doAnim) # special case: ALWAYS relative to current QC dir
			except IOError:
				if not line[1].endswith("qci"):
					readQC(context,filedir + appendExt(line[1], "qc"),False, doAnim)

	file.close()
	
	if outer_qc:
		printTimeMessage(qc.startTime,filename,"import","QC")
	
	return qc.numSMDs
	
# Parses an SMD file
def readSMD( context, filepath, newscene = False, smd_type = None, multiImport = False, maintainBoneRot = False):
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
	smd.maintainBoneRot = maintainBoneRot
	smd.uiTime = 0
	
	try:
		smd.file = file = open(filepath, 'r')
	except IOError: # TODO: work out why errors are swallowed if I don't do this!
		if smd_type: # called from QC import
			log.warning("could not open SMD file \"%s\" - skipping!" % smd.jobName)
			print("\t" + filepath)
			return
		else:
			raise(IOError) # just error out if it's a direct SMD import
		
	if newscene:
		bpy.context.screen.scene = bpy.data.scenes.new(smd.jobName) # BLENDER BUG: this currently doesn't update bpy.context.scene
	elif not smd_type: # only when importing standalone
		bpy.context.scene.name = smd.jobName

	print("\nSMD IMPORTER: now working on",smd.jobName)
	if file.readline() != "version 1\n":
		log.warning ("unrecognised/invalid SMD file. Import will proceed, but may fail!")
	
	#if context.mode == 'EDIT':
	#	smd.started_in_editmode = True
	#	ops.object.mode_set(mode='OBJECT')
	
	if smd.jobType == None:
		scanSMD() # What are we dealing with?

	for line in file:
		if line == "nodes\n": readBones()
		if line == "skeleton\n": readFrames()
		if line == "triangles\n": readPolys()
		if line == "vertexanimation\n": readShapes()

	file.close()
	printTimeMessage(smd.startTime,smd.jobName,"import")

class SmdImporter(bpy.types.Operator):
	bl_idname = "import.smd"
	bl_label = "Import SMD/VTA/QC"
	bl_options = {'REGISTER', 'UNDO'}
	
	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA/QC file", maxlen=1024, default="")
	filename = StringProperty(name="Filename", description="Name of SMD/VTA/QC file", maxlen=1024, default="")
	#freshScene = BoolProperty(name="Import to new scene", description="Create a new scene for this import", default=False) # nonfunctional due to Blender limitation
	multiImport = BoolProperty(name="Import SMD as new model", description="Treats an SMD file as a new Source engine model. Otherwise, it will extend anything existing.", default=False)
	maintainBoneRot = BoolProperty(name="Maintain bone rotation", description="Blender's bones behave differently from Source's. If you are creating animations for an existing compiled model, check this box.", default=True)
	doAnim = BoolProperty(name="Import animations (broken)", description="Use for comedic effect only", default=False)
	
	def execute(self, context):
		global log
		log = logger()
		
		self.properties.filepath = self.properties.filepath.lower()
		if self.properties.filepath.endswith('.qc') | self.properties.filepath.endswith('.qci'):
			self.countSMDs = readQC(context, self.properties.filepath, False, self.properties.doAnim, outer_qc=True, maintainBoneRot=self.properties.maintainBoneRot)
			bpy.context.scene.objects.active = qc.armature
		elif self.properties.filepath.endswith('.smd'):
			readSMD(context, self.properties.filepath, multiImport=self.properties.multiImport, maintainBoneRot=self.properties.maintainBoneRot)
			self.countSMDs = 1
		elif self.properties.filepath.endswith ('.vta'):
			readSMD(context, self.properties.filepath, smd_type='FLEX')
			self.countSMDs = 1
		elif self.properties.filepath.endswith('.dmx'):
			return {'CANCELLED'}
			self.report('ERROR',"DMX import not supported")
		else:
			self.report('ERROR',"File format not recognised")
			return {'CANCELLED'}
		
		log.errorReport("import",self)
		bpy.ops.view3d.view_all()
		return {'FINISHED'}
	
	def invoke(self, context, event):	
		wm = bpy.context.manager
		wm.add_fileselect(self)
		return {'RUNNING_MODAL'}

def import_menu_item(self, context):
	self.layout.operator(SmdImporter.bl_idname, text="Studiomdl Data (.smd, .vta, .qc)")

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
	
	top_id = -1
	new_ids_needed = False
	
	# See if any bones need IDs; record highest ID
	for bone in smd.a.data.bones:
		try:
			top_id = max(top_id,int(bone['smd_id']))
		except KeyError:
			new_ids_needed = True
	
	# Assign new IDs if needed
	if new_ids_needed:
		for bone in smd.a.data.bones:
			if not bone.get('smd_id'):
				top_id += 1
				bone['smd_id'] = top_id # re-using lower IDs risks collision
	
	# Write to file
	for bone in smd.a.data.bones:
		line = str(bone['smd_id']) + " "
		
		bone_name = bone.get('smd_name')
		if not bone_name:
			bone_name = bone.name
		line += "\"" + bone_name + "\" "
		
		try:
			line += str(bone.parent['smd_id'])
		except TypeError:
			line += "-1"
		
		smd.file.write(line + "\n")
		
	smd.file.write("end\n")
	if not quiet: print("- Exported",len(smd.a.data.bones),"bones")
	
# skeleton block
def writeFrames():
	
	if smd.jobType == 'FLEX': # writeShapes() does its own skeleton block
		return
		
	smd.file.write("skeleton\n")
	
	if not smd.a:
		smd.file.write("time 0\n0 0 0 0 0 0 0\nend\n")
		return
	
	bpy.context.scene.objects.active = smd.a
	ops.object.mode_set(mode='EDIT')
	
	smd.file.write("time 0\n")
	for bone in smd.a.data.edit_bones:
		pos_str = rot_str = ""
		
		#vector in, euler out
		vec = bone.tail - bone.head
		euler = vector()
		# the values are negated to transfer between Source's right-handed and Blender's left-handed rotations
		euler[0] = -math.atan2(vec[2], math.sqrt((vec[0] * vec[0]) + (vec[1] * vec[1]))) # pitch
		euler[1] = -bone.roll # roll
		euler[2] = -math.atan2(vec[0],vec[1]) # yaw
		
		# euler in, matrix out
		smd.rotMats[bone.name] = rMat(euler[0], 3,'X') * rMat(euler[1], 3,'Y') * rMat(euler[2], 3,'Z')
		
		if bone.parent:
			smd.rotMats[bone.name] *= smd.rotMats[bone.parent.name].invert()
			smd_rot = euler * smd.rotMats[bone.name]
			smd_pos = bone.parent.head - bone.head #(bone.head * smd.rotMats[bone.name])
		else:
			smd_rot = euler
			smd_pos = bone.head
		
		for i in range(3):
			pos_str += " " + getSmdFloat(smd_pos[i])
			rot_str += " " + "0" #getSmdFloat(smd_rot[i])
			
		smd.file.write( str(bone['smd_id']) + pos_str + rot_str + "\n")	
	
	smd.file.write("end\n")
	ops.object.mode_set(mode='OBJECT')
	return

# triangles block
def writePolys():
	smd.file.write("triangles\n")
	
	bpy.context.scene.objects.active = smd.m
	ops.object.mode_set(mode='EDIT')
	ops.mesh.quads_convert_to_tris() # ops calls make baby jesus cry
	ops.object.mode_set(mode='OBJECT')

	md = smd.m.data
	face_index = 0
	for face in md.faces:
		if smd.m.material_slots:
			smd.file.write(smd.m.material_slots[face.material_index].name + "\n")
		else:
			smd.file.write(smd.jobName + "\n")
		for i in range(3):
			
			# Vertex locations, normal directions
			verts = norms = ""
			v = md.verts[face.verts[i]]
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
						groups += " " + str(smd.a.data.bones[smd.m.vertex_groups[v.groups[j].group].name]['smd_id']) + " " + getSmdFloat(v.groups[j].weight)
					except AttributeError:
						pass # bone doesn't have a vert group on this mesh; not necessarily a problem
			else:
				groups = " 0"
			
			# Finally, write it all to file
			smd.file.write("0" + verts + norms + uv + groups + "\n")
			
		face_index += 1
	
	smd.file.write("end\n")
	print("- Exported",face_index,"polys")
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
			for vert in face.verts:
				shape_vert = shape.data[vert]
				mesh_vert = smd.m.data.verts[vert]
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
		if smd.m.hide:
			smd.m.hide = False
			mesh_was_hidden = True
		
		if smd.m.modifiers:
			for i in range(len(smd.m.modifiers)):
				if smd.m.modifiers[i].type == 'ARMATURE':
					smd.a = smd.m.modifiers[i].object
	elif object.type == 'ARMATURE':
		if not smd.jobType:
			smd.jobType = 'ANIM'
		smd.a = object
	else:
		print("PROGRAMMER ERROR: writeSMD() has object not in [mesh,armature]")
		raise
		
	
	smd.file = open(filepath, 'w')
	if not quiet: print("\nSMD EXPORTER: now working on",smd.jobName)
	smd.file.write("version 1\n")

	if smd.m:
		if smd.jobType in ['REF','PHYS']:
			writeBones()
			writeFrames()
			writePolys()
		elif smd.jobType == 'FLEX' and smd.m.data.shape_keys:
			writeBones(quiet=True)
			writeShapes()

	smd.file.close()
	if mesh_was_hidden:
		smd.m.hide = True
	if not quiet: printTimeMessage(smd.startTime,smd.jobName,"export")

from bpy.props import *

class SMD_MT_ExportChoice(bpy.types.Menu):
	bl_label = "SMD export mode"

	def draw(self, context):
		try:
			# this func is also embedded in the "export scene" panel
			l = self.embed_layout
			is_embedded = True
		except AttributeError:
			l = self.layout
			is_embedded = False
		
		ob = context.active_object
		
		if is_embedded and (len(context.selected_objects) == 0 or not ob):
			row = l.row()
			row.operator(SmdExporter.bl_idname, text="No selection") # filler to stop the scene button moving
			row.enabled = False
		elif ob and len(context.selected_objects) == 1:
			subdir = ob.get('smd_subdir')
			if subdir and len(subdir):
				label = subdir + "\\"
			else:
				label = ""
			if ob.type == 'MESH':
				label += ob.name + ".smd"
				if ob.data.shape_keys and len(ob.data.shape_keys.keys) > 1:
					label += "/.vta"
				l.operator(SmdExporter.bl_idname, text=label, icon="OUTLINER_OB_MESH").exportMode = 'SINGLE' # single mesh
			elif ob.type == 'ARMATURE':
				l.label(text="Animations unsupported",icon="ACTION")
				#if ob.animation_data:
				#	l.operator(SmdExporter.bl_idname, text=label + ob.animation_data.action.name + ".smd", icon="ACTION") # single armature
				#else:
				#	l.label(text="(No animations)",icon='ACTION')
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
		
		elif len(context.selected_objects) > 1:
			l.operator(SmdExporter.bl_idname, text="Selected objects", icon='GROUP').exportMode = 'MULTI' # multiple obects
			
		l.operator(SmdExporter.bl_idname, text="Scene as configured", icon='SCENE_DATA').exportMode = 'SCENE'
	#	l.operator(SmdExporter.bl_idname, text="Whole .blend", icon='FILE_BLEND').exportMode = 'FILE' # can't do this until scene changes become possible
		
class SMD_PT_ExportProfile(bpy.types.Panel):
	bl_label = "SMD Export"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	
	def draw(self, context):
		l = self.layout
		scene = context.scene
		
		self.embed_layout = l.column_flow(columns=2)
		SMD_MT_ExportChoice.draw(self,context)
		
		l.prop(scene,"smd_path",text="Output folder")
		
		if scene.get("smd_path"):
			l.label(text="Scene configuration:")
			box = l.box()
			columns = box.column()
			header = columns.column_flow(columns=2)
			header.label(text="Object:")
			header.label(text="Subfolder:")
			foundObjs = False
			for object in scene.objects:
				if object.type in ['MESH','ARMATURE']:
					foundObjs = True
					row = columns.row()
					row.prop(object,"smd_export",icon="OUTLINER_OB_" + object.type,emboss=True,text=object.name)
					row.enabled = object.type != 'ARMATURE'
					
					rhs = row.split()
					rhs.prop(object,"smd_subdir")
					rhs.enabled = object.smd_export
			if not foundObjs:
				box.label(text="(No valid objects)")
		
		l.separator()
		l.operator(SmdExporter.bl_idname,text="Clean all SMD data from scene and objects",icon='RADIO').exportMode='CLEAN'
		

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
		('SCENE','Scene','Export the objects and animations selected in Scene Properties'),
		('FILE','Whole .blend file','Export absolutely everything, from all scenes'),
		('CLEAN',"Clean SMD data from scene","Deletes all SMD-related properties from the scene and its contents")
		)
	exportMode = EnumProperty(items=exportMode_enum,options={'HIDDEN'})
	
	def execute(self, context):
		props = self.properties
		
		if props.exportMode == 'CLEAN':
			def removeProps(object):
				for prop in object.items():
					if prop[0].startswith("smd_"):
						del object[prop[0]]
						
			for object in context.scene.objects:
				removeProps(object)
				if object.type == 'ARMATURE':
					for bone in object.data.bones:
						removeProps(bone)
			removeProps(context.scene)
			return {'FINISHED'}
		
		# no animation support yet
		if props.exportMode == 'SINGLE' and context.active_object.type == 'ARMATURE':
			self.report('ERROR',"Animation export not supported yet")
			return {'CANCELLED'}
		
		if len(props.filepath):
			# We've got a file path from the file selector, write it and continue
			context.scene['smd_path'] = getFileDir(props.filepath)
		else:
			# Get a path from the scene object
			prop_path = context.scene.get("smd_path")
			if prop_path and len(prop_path):
				props.filepath = prop_path
			else:
				props.filename = "<folder select>"
				context.manager.add_fileselect(self)
				return {'RUNNING_MODAL'}
		
		global log
		log = logger()
		
		print("\nSMD EXPORTER RUNNING")
		prev_active_ob = context.active_object
		
		# store Blender mode user was in before export
		prev_mode = None
		if bpy.context.mode != "OBJECT":
			prev_mode = bpy.context.mode
			if prev_mode.startswith("EDIT"):
				prev_mode = "EDIT" # remove any suffixes
			ops.object.mode_set(mode='OBJECT')
		
		# check export mode and perform appropriate jobs
		self.countSMDs = 0
		if props.exportMode == 'SINGLE':
			self.exportObject(context,context.active_object)
			
		elif props.exportMode == 'MULTI':
			for object in context.selected_objects:
				if object.type in ['MESH', 'ARMATURE']:
					self.exportObject(context,object)
					
		elif props.exportMode == 'SCENE':
			for object in bpy.context.scene.objects:
				if object.get('smd_export') != False: # can be None, which means unset
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
		
		# Finished! Clean up...
		context.scene.objects.active = prev_active_ob
		if prev_mode:
			ops.object.mode_set(mode=prev_mode)
		if self.countSMDs == 0:
			log.error(self,"Found no valid objects for export")
			return {'CANCELLED'}

		log.errorReport("export",self)
		return {'FINISHED'}
	
	# indirection to support batch exporting
	def exportObject(self,context,object,flex=False):
		props = self.properties
		
		# handle subfolder
		subdir = object.get('smd_subdir')
		if not subdir or len(subdir) == 0:
			if object.type == 'ARMATURE':
				subdir = "anims"
			else:
				subdir = ""
		object['smd_subdir'] = subdir = subdir.lstrip("/") # don't want //s here!
		
		# assemble filename and export
		path = bpy.utils.expandpath(getFileDir(props.filepath.lower()) + subdir)
		
		if not object.type == 'ARMATURE': # this test will go when animations are supported
			try:
				os.stat(path)
			except:
				os.mkdir(path)
		
		if object.type == 'MESH':
			path += object.name
			writeSMD(context, object, path + ".smd")
			self.countSMDs += 1
			if object.data.shape_keys and len(object.data.shape_keys.keys) > 1:
				writeSMD(context, object, path + ".vta", 'FLEX')
				self.countSMDs += 1
		elif object.type == 'ARMATURE':
			pass # TODO: loop over all actions for this armature, exporting each one to a new SMD
	
	def invoke(self, context, event):
		if self.properties.exportMode == 'NONE':
			bpy.ops.wm.call_menu(name="SMD_MT_ExportChoice")
			return {'PASS_THROUGH'}
		else: # a UI element has chosen a mode for us
			return self.execute(context)

def export_menu_item(self, context):
	self.layout.operator(SmdExporter.bl_idname, text="Studiomdl Data (.smd, .vta)")

#####################################
#        Shared registration        #
#####################################

smd_types = [ SmdImporter, SmdExporter, SMD_MT_ExportChoice, SMD_PT_ExportProfile]
type = bpy.types

def register():
	for obj in smd_types:
		type.register(obj)
	type.Scene.StringProperty(attr="smd_path", description="Root SMD export folder",subtype='DIR_PATH')
	type.Object.BoolProperty(attr="smd_export",description="Whether this object should export with the scene",default=True)
	type.Object.StringProperty(attr="smd_subdir", description="Folder, relative to scene root, for SMDs from this object")
	type.INFO_MT_file_import.append(import_menu_item)
	type.INFO_MT_file_export.append(export_menu_item)

def unregister():
	for obj in smd_types:
		type.unregister(obj)
	type.INFO_MT_file_import.remove(import_menu_item)
	type.INFO_MT_file_export.remove(export_menu_item)

if __name__ == "__main__":
	register()
