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
    "version": "0.4",
    "blender": (2, 5, 3),
    "category": "Import/Export",
    "location": "File > Import/Export",
    "warning": 'No animation support yet.',
    "wiki_url": "http://developer.valvesoftware.com/wiki/Blender_SMD_tools",
    "tracker_url": "http://developer.valvesoftware.com/wiki/Talk:Blender_SMD_tools",
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
	a = None # Armature object
	m = None # Mesh datablock
	file = None
	jobName = None
	jobType = None
	startTime = 0
	uiTime = 0
	started_in_editmode = None
	multiImport = False
	
	# Checks for dupe bone names due to truncation
	dupeCount = {}
	# boneIDs contains the ID-to-name mapping of *this* SMD's bones.
	# - Key: ID (as string due to potential storage in registry)
	# - Value: bone name (storing object itself is not safe)
	# Use boneOfID(id) to easily look up a value from here
	boneIDs = {}
	
	# For recording rotation matrices. Children access their parent's matrix.
	# USE BONE NAME STRING - MULTIPLE BONE TYPES NEED ACCESS (bone, editbone, posebone)
	rotMats = {}
	# For connecting bones to their first child only
	hasBeenLinked = {}

class qc_info:
	startTime = 0
	imported_smds = []
	vars = {}
	ref_mesh = None # for VTA import
	
	in_block_comment = False
	
	root_filename = ""
	root_filedir = ""
	dir_stack = []
	
	def cd(self):
		return self.root_filedir + "".join(self.dir_stack)
		
# rudimentary error reporting...will get UI in the future
class logger:
	warnCount = 0
	errorCount = 0
	
	def warning(self, *string):
		print("** WARNING:"," ".join(str(s) for s in string))
		self.warnCount += 1
		
	def error(self, *string):
		print("** ERROR:"," ".join(str(s) for s in string))
		self.errorCount += 1
		
	def errorReport(self, jobName, deleteSelf = True):
		print("Encountered %i errors and %i warnings during %s.\n" % (self.errorCount, self.warnCount, jobName))
		if deleteSelf:
			del self
	

#################################
#        Shared utilities       #
#################################

def getFilename(filepath):
	return filepath.split('\\')[-1].split('/')[-1].rsplit(".")[0]
def getFiledir(filepath):
	return filepath.rstrip(filepath.split('\\')[-1].split('/')[-1])
	
import decimal
# rounds to 6 decimal places, converts between "1e-5" and "0.000001", outputs str
def getSmdFloat(fval):
	return str(decimal.Decimal(str(round(float(fval),6)))) # yes, it really is all needed

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
		if qc.in_block_comment:
			if char == "/" and pchar == "*": # done backwards so we don't have to skip two chars
				qc.in_block_comment = False
			continue
		elif char == "/" and nchar == "*":
			qc.in_block_comment = True
			continue
		
		# quote block
		if char == "\"" and not pchar == "\\": # quotes can be escaped
			in_quote = (in_quote == False)
		if not in_quote:
			if not in_whitespace and char in [" ","\t"]:
				cur_word = line[last_word_start:i].strip("\"") # characters between last whitespace and here
				if len(cur_word) > 0:
					words.append(cur_word)
				in_whitespace = True
				last_word_start = i+1 # we are in whitespace, first new char is the next one
			else:
				in_whitespace = False
	
	# catch last word, removing '{'s crashing into it (char not currently used)
	cur_word = line[last_word_start:i].strip("\"{")
	if len(cur_word) > 0:
		words.append(cur_word)

	return words
	
def appendExt(path,ext):
	if not path.endswith("." + ext) and not path.endswith(".dmx"):
		path += "." + ext
	return path

def boneOfID( id ):
	try:
		if bpy.context.mode == 'EDIT_ARMATURE':
			return smd.a.data.edit_bones[ smd.boneIDs[int(id)] ]
		else:
			return smd.a.data.bones[ smd.boneIDs[int(id)] ]
	except:
		return None
		
def printTimeMessage(start_time,name,type="SMD"):
	elapsedtime = int(time.time() - start_time)
	if elapsedtime == 1:
		elapsedtime = "1 second"
	elif elapsedtime > 1:
		elapsedtime = str(elapsedtime) + " seconds"
	else:
		elapsedtime = "under 1 second"
	
	print(type,name,"imported successfully in",elapsedtime,"\n")
	
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
	
# deletes any global objects hanging around from failed operations earlier in the session
def cleanupInfoObjects():
	global qc
	global smd
	global log
	try:
		del qc
	except NameError:
		pass
	try:
		del smd
	except NameError:
		pass
	try:
		del log
	except NameError:
		pass

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
		print("- This is a skeltal animation") # No triangles, no flex - must be animation
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
	a.data.draw_axes = True
	a.data.deform_envelope = False # Envelope deformations are not exported, so hide them
	a.data.drawtype = 'STICK'
	bpy.context.scene.objects.link(a)
	bpy.context.scene.objects.active = a
	
	# ***********************************
	# Read bones from SMD
	countBones = 0
	ops.object.mode_set(mode='EDIT')
	for line in smd.file:
		if line == "end\n":
			print("- Imported %i new bones" % countBones)
			break

		countBones += 1
		values = line.split()

		values[1] = values[1].strip("\"") # remove quotemarks
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
			log.warning("-Bone name '%s' was truncated to 32 characters." % values[1])
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
		newBone['smd_id'] = values[0] # Persistent, and stored on each bone so handles deletion

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
				bn.tail = bn.head + (vector([0,1,0])*smd.rotMats[bn.name]) # Another 1D to 2D artifact. Bones must point down the Y axis so that their co-ordinates remain stable
				
			else:
				bn.translate(destOrg) # LOCATION WITH NO PARENT
				bn.tail = bn.head + (vector([0,1,0])*smd.rotMats[bn.name])
				#bn.transform(smd.rotMats[bn.name])
				
			# Store rotation either way
			bn['smd_rot'] = euler([float(values[4]),float(values[5]),float(values[6])])
			
			# Take a stab at parent-child connections. Not fully effective since only one child can be linked, so I
			# assume that the first child is the one to go for. It /usually/ is.
	#		if bn.parent and not smd.hasBeenLinked.get(bn.parent):
	#			bn.parent.tail = bn.head
	#			bn.connected = True
	#			smd.hasBeenLinked[bn.parent] = True

		
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
	
	if smd.jobType is 'ANIM' or 'ANIM_SOLO':
		scn.frame_end = scn.frame_current
	
	# TODO: clean curves automagically (ops.graph.clean)

	ops.object.mode_set(mode='OBJECT')	
	
	print("- Imported %i frames of animation" % scn.frame_current)
	scn.frame_current = startFrame
	
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
			smd.m = bpy.context.object # user selection
		
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
def readQC( context, filepath, newscene, doAnim):
	filename = getFilename(filepath)
	filedir = getFiledir(filepath)
	
	is_root_qc = False
	global qc
	try:
		qc
	except NameError: # we are the outermost QC
		print("\nQC IMPORTER: now working on",filename)
		is_root_qc = True
		qc = qc_info()
		qc.startTime = time.time()
		qc.root_filename = filename
		qc.root_filedir = filedir
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
				readSMD(context,path,False,type,multiImport)
		
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
				path = qc.cd() + appendExt(line[2],"smd")
				if not path in qc.imported_smds:
					qc.imported_smds.append(path)
					readSMD(context,path,False,'ANIM')
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
	
	if is_root_qc:
		printTimeMessage(qc.startTime,filename,"QC")
	
# Parses an SMD file
def readSMD( context, filepath, newscene = False, smd_type = None, multiImport = False ):
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
	smd.uiTime = 0
	
	try:
		smd.file = file = open(filepath, 'r')
	except IOError: # TODO: work out why errors are swallowed if I don't do this!
		if smd_type: # called from QC import
			log.error("could not open SMD file \"%s\" - skipping!" % smd.jobName)
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
		warning ("unrecognised/invalid SMD file. Import will proceed, but may fail!")
	
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
	printTimeMessage(smd.startTime,smd.jobName)
	del smd

class SmdImporter(bpy.types.Operator):
	'''Load a Source engine SMD, VTA or QC file'''
	bl_idname = "import_scene.smd"
	bl_label = "Import SMD/VTA/QC"
	
	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA/QC file", maxlen=1024, default="")
	filename = StringProperty(name="Filename", description="Name of SMD/VTA/QC file", maxlen=1024, default="")
	#freshScene = BoolProperty(name="Import to new scene", description="Create a new scene for this import", default=False) # nonfunctional due to Blender limitation
	multiImport = BoolProperty(name="Import SMD as new model", description="Treats an SMD file as a new Source engine model. Otherwise, it will extend anything existing.", default=False)
	doAnim = BoolProperty(name="Import animations (broken)", description="Use for comedic effect only", default=False)
	
	def execute(self, context):
		cleanupInfoObjects()
		global log
		log = logger()
		
		self.properties.filepath = self.properties.filepath.lower()
		if self.properties.filepath.endswith('.qc') | self.properties.filepath.endswith('.qci'):
			readQC(context, self.properties.filepath, False, self.properties.doAnim)
		elif self.properties.filepath.endswith('.smd'):
			readSMD(context, self.properties.filepath, multiImport=self.properties.multiImport)
		elif self.properties.filepath.endswith ('.vta'):
			readSMD(context, self.properties.filepath, smd_type='FLEX')
		elif self.properties.filepath.endswith('.dmx'):
			log.error("DMX import not supported")
		else:
			log.error("File format not recognised")
		
		log.errorReport("import")
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
			try:
				bone['smd_id']
			except KeyError:
				top_id += 1
				bone['smd_id'] = top_id # re-using lower IDs risks collision
	
	# Write to file
	for bone in smd.a.data.bones:
		line = str(bone['smd_id']) + " "
		
		try:
			bone_name = bone['smd_name']
		except KeyError:
			bone_name =  bone.name
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
	
	#context.scene.objects.active = smd.a
	#ops.object.mode_set(mode='EDIT')
	smd.file.write("time 0\n")
	for bone in smd.a.data.bones:
		pos = rot = ""
		
	#	bone_rot = vector( [math.atan2(bone.vector[2], math.sqrt( (bone.vector[0]*bone.vector[0]*) + (bone.vector[1]*bone.vector[1]) )), math.atan2(bone.vector[0],bone.vector[1]), bone.roll] )
		
		
	#	bone_rot[0] += 1.570796 
	#	bone_rot[1] = -bone_rot[2] # y
	#	bone_rot[2] = bone.roll # z = bone roll
		
		if bone.parent:
			bone_rot = matrixToEuler( bone.matrix * bone.parent.matrix )
			bone_pos = (bone.head_local - bone.parent.head_local)
		else:
			bone_rot = matrixToEuler( bone.matrix )
			bone_pos = bone.head_local
		
		bone_rot[0] += 1.570796
		
		for i in range(3):
			pos += getSmdFloat( bone_pos[i] )
			rot += "0" #getSmdFloat(bone_rot[i])
			
			if i != 2:
				pos += " "
				rot += " "
			
		smd.file.write( str(bone['smd_id']) + " " + pos + " " + rot + "\n")	
	
	smd.file.write("end\n")
	#ops.object.mode_set(mode='OBJECT')
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
					# There is no certainty that a bone and its vertex group will share the same ID. Thus this monster:
					groups += " " + str(smd.a.data.bones[smd.m.vertex_groups[v.groups[j].group].name]['smd_id']) + " " + getSmdFloat(v.groups[j].weight)
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
def writeSMD( context, filepath, smd_type = None, doVTA = True, quiet = False ):
	if filepath.endswith("dmx"):
		print("Skipping DMX file export: format unsupported (%s)" % getFilename(filepath))
		return

		
	global smd
	smd	= smd_info()
	smd.jobName = bpy.context.object.name
	smd.jobType = smd_type
	smd.startTime = time.time()
	smd.uiTime = 0
	
	if bpy.context.object.type == 'MESH':
		if not smd.jobType:
			smd.jobType = 'REF'
		smd.m = bpy.context.object
		if smd.m.modifiers:
			for i in range(len(smd.m.modifiers)):
				if smd.m.modifiers[i].type == 'ARMATURE':
					smd.a = smd.m.modifiers[i].object
	elif bpy.context.object.type == 'ARMATURE':
		if not smd.jobType:
			smd.jobType = 'ANIM'
		smd.a = bpy.context.object
	else:
		log.error("invalid object selected!")
		del smd
		return
	
	smd.file = open(filepath, 'w')
	if not quiet: print("\nSMD EXPORTER: now working on",smd.jobName)
	smd.file.write("version 1\n")

	writeBones()
	writeFrames()
	
	if smd.m:
		if smd.jobType in ['REF','PHYS']:
			writePolys()
			
		if doVTA and smd.m.data.shape_keys: 
			# Start a new file
			smd.file.close()
			smd.file = open(filepath[0:filepath.rfind(".")] + ".vta", 'w')
			smd.jobType = 'FLEX'
			
			writeBones(quiet=True)
			writeShapes()

	smd.file.close()
	if not quiet: printTimeMessage(smd.startTime,smd.jobName)
	del smd
	
from bpy.props import *

class SmdExporter(bpy.types.Operator):
	'''Export to the Source engine SMD/VTA format'''
	bl_idname = "export_scene.smd"
	bl_label = "Export SMD/VTA"
	
	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA file", maxlen=1024, default="")
	filename = StringProperty(name="Filename", description="Name of SMD/VTA file", maxlen=1024, default="")
	doVTA = BoolProperty(name="Export VTA", description="Export a mesh's shape key", default=True)
	
	def execute(self, context):
		cleanupInfoObjects()
		global log
		log = logger()
		
		prev_mode = None
		if bpy.context.mode != "OBJECT":
			prev_mode = bpy.context.mode
			if prev_mode.startswith("EDIT"):
				prev_mode = "EDIT" # remove any suffixes
			ops.object.mode_set(mode='OBJECT')
		
		#if self.properties.filepath.endswith('.qc') | self.properties.filepath.endswith('.qci'):
		#	writeQC(context, self.properties.filepath, self.properties.freshScene, self.properties.doVTA, self.properties.doAnim )
		if self.properties.filepath.endswith('.smd'):
			writeSMD(context, self.properties.filepath, doVTA = self.properties.doVTA )
		elif self.properties.filepath.endswith ('.vta'):
			writeSMD(context, self.properties.filepath, 'FLEX', True, False)
		elif self.properties.filepath.endswith('.dmx'):
			log.error("DMX export not supported")
		else:
			log.error("File format not recognised")
		
		log.errorReport("export")
		if prev_mode:
			ops.object.mode_set(mode=prev_mode)
		return {'FINISHED'}
	
	def invoke(self, context, event):
		if not bpy.context.object:
			print( "SMD Export error: no object selected.")
			return {'CANCELLED'}
			
		wm = context.manager
		wm.add_fileselect(self)
		return {'RUNNING_MODAL'}

def export_menu_item(self, context):
    self.layout.operator(SmdExporter.bl_idname, text="Studiomdl Data (.smd, .vta)").filepath = os.path.splitext(bpy.data.filepath)[0] + ".smd"
	

####################################
#        Shared registration       #
####################################

def register():
	bpy.types.register(SmdImporter)
	bpy.types.register(SmdExporter)
	bpy.types.INFO_MT_file_import.append(import_menu_item)
	bpy.types.INFO_MT_file_export.append(export_menu_item)

def unregister():
	bpy.types.unregister(SmdImporter)
	bpy.types.unregister(SmdExporter)
	bpy.types.INFO_MT_file_import.remove(import_menu_item)
	bpy.types.INFO_MT_file_export.remove(export_menu_item)

if __name__ == "__main__":
	register()
