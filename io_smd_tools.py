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

# DISABLE SmdToolsUpdate IF YOU MAKE THIRD-PARTY CHANGES TO THE SCRIPT!

bl_info = {
	"name": "SMD\DMX Tools",
	"author": "Tom Edwards, EasyPickins",
	"version": (1, 0, 2),
	"blender": (2, 58, 0),
	"api": 37702,
	"category": "Import-Export",
	"location": "File > Import/Export; Properties > Scene/Armature",
	"wiki_url": "http://code.google.com/p/blender-smd/",
	"tracker_url": "http://code.google.com/p/blender-smd/issues/list",
	"description": "Importer and exporter for Valve Software's Source Engine. Supports SMD\VTA, DMX and QC."}

import math, os, time, bpy, random, mathutils, re, ctypes, urllib.request, struct, subprocess, io
from bpy import ops
from bpy.props import *
from struct import unpack,calcsize
from mathutils import *
from math import *

intsize = calcsize("i")
floatsize = calcsize("f")

rx90 = Matrix.Rotation(radians(90),4,'X')
ry90 = Matrix.Rotation(radians(90),4,'Y')
rz90 = Matrix.Rotation(radians(90),4,'Z')
ryz90 = ry90 * rz90

rx90n = Matrix.Rotation(radians(-90),4,'X')
ry90n = Matrix.Rotation(radians(-90),4,'Y')
rz90n = Matrix.Rotation(radians(-90),4,'Z')

mat_BlenderToSMD = ry90n * rz90n * rx90n

# SMD types
REF = 0x1 # $body, $model, $bodygroup->studio (if before a $body or $model)
REF_ADD = 0x2 # $bodygroup, $lod->replacemodel
PHYS = 0x3 # $collisionmesh, $collisionjoints
ANIM = 0x4 # $sequence, $animation
ANIM_SOLO = 0x5 # for importing animations to scenes without an existing armature
FLEX = 0x6 # $model VTA

mesh_compatible = [ 'MESH', 'TEXT', 'FONT', 'SURFACE', 'META', 'CURVE' ]
exportable_types = mesh_compatible[:]
exportable_types.append('ARMATURE')
shape_types = ['MESH' , 'SURFACE']

src_branches = (
('CUSTOM','Custom SDK',''),
('orangebox','Source 2009',''),
('source2007','Source 2007',''),
('ep1','Source 2006',''),
('left 4 dead 2','Left 4 Dead 2',''),
('left 4 dead','Left 4 Dead',''),
('alien swarm','Alien Swarm',''),
('portal 2','Portal 2','')
)

# I hate Python's var redefinition habits
class smd_info:
	def __init__(self):
		self.isDMX = 0 # version number, or 0 for SMD
		self.a = None # Armature object
		self.amod = None # Original armature modifier
		self.m = None # Mesh datablock
		self.shapes = None
		self.g = None # Group being exported
		self.file = None
		self.jobName = None
		self.jobType = None
		self.startTime = 0
		self.uiTime = 0
		self.started_in_editmode = None
		self.append = False
		self.in_block_comment = False
		self.upAxis = 'Z'
		self.upAxisMat = 1 # vec * 1 == vec
		self.truncMaterialNames = []
	
		# DMX stuff
		self.attachments = []
		self.meshes = []
		self.parent_chain = []

		self.frameData = []

		self.bakeInfo = []

		# boneIDs contains the ID-to-name mapping of *this* SMD's bones.
		# - Key: integer ID
		# - Value: bone name (storing object itself is not safe)
		self.boneIDs = {}

class qc_info:
	def __init__(self):
		self.startTime = 0
		self.imported_smds = []
		self.vars = {}
		self.ref_mesh = None # for VTA import
		self.a = None
		self.origin = None
		self.upAxis = 'Z'
		self.upAxisMat = None
		self.numSMDs = 0
		self.makeCamera = False

		self.in_block_comment = False

		self.jobName = ""
		self.root_filedir = ""
		self.dir_stack = []

	def cd(self):
		return self.root_filedir + "".join(self.dir_stack)

class SMD_MT_GetDMXModel(bpy.types.Menu):
	bl_label = "DMX support unavailable"
	def draw(self,context):
		self.layout.operator("wm.url_open",text="Could not locate DMX-Model. Download now?",icon='SCRIPTWIN').url = "http://code.google.com/p/blender-smd/downloads/list"

# error reporting
class logger:
	def __init__(self):
		self.warnings = []
		self.errors = []
		self.startTime = time.time()
		self.wantDMXDownloadPrompt = False

	def warning(self, *string):
		message = " ".join(str(s) for s in string)
		printColour(STD_YELLOW," WARNING:",message)
		self.warnings.append(message)

	def error(self, *string):
		message = " ".join(str(s) for s in string)
		printColour(STD_RED," ERROR:",message)
		self.errors.append(message)

	def errorReport(self, jobName, output, caller, numOut):
		message = "{} {}{} {}".format(numOut,output,"s" if numOut != 1 else "",jobName)
		if numOut:
			message += " in {} seconds".format( round( time.time() - self.startTime, 1 ) )

		if len(self.errors) or len(self.warnings):
			message += " with {} errors and {} warnings:".format(len(self.errors),len(self.warnings))
	
			# like it or not, Blender automatically prints operator reports to the console these days
			'''print(message)
			stdOutColour(STD_RED)
			for msg in self.errors:
				print("  " + msg)
			stdOutColour(STD_YELLOW)
			for msg in self.warnings:
				print("  " + msg)
			stdOutReset()'''
	
			for err in self.errors:
				message += "\nERROR: " + err
			for warn in self.warnings:
				message += "\nWARNING: " + warn
			caller.report('ERROR',message)	
		else:
			caller.report('INFO',message)
			print(message)
	
		if self.wantDMXDownloadPrompt:
			stdOutColour(STD_YELLOW)
			print("\nFor DMX support, download DMX-Model from http://code.google.com/p/blender-smd/downloads/list")
			stdOutReset()

log = None # Initialize this so it is easier for smd_test_suite to access

##################################
#        Shared utilities        #
##################################

def benchReset():
	global benchLast
	global benchStart
	benchStart = benchLast = time.time()
benchReset()
def bench(label):
	global benchLast
	now = time.time()
	print("{}: {:.4f}".format(label,now-benchLast))
	benchLast = now
def benchTotal():
	global benchStart
	return time.time() - benchStart

def ValidateBlenderVersion(op):
	if int(bpy.app.build_revision[:5]) >= bl_info['api']:
		return True
	else:
		op.report('ERROR',"SMD Tools {} require Blender {} or later, but this is {}".format(PrintVer(bl_info['version']), PrintVer(self.cur_entry['bpy']), PrintVer(bpy.app.version)) )
		return False

def getFileExt(flex=False):
	if flex and bpy.context.scene.smd_format == 'SMD':
		return ".vta"
	else:
		return "." + bpy.context.scene.smd_format.lower()

def getFilename(filepath):
	return filepath.split('\\')[-1].split('/')[-1].rsplit(".")[0]
def getFileDir(filepath):
	return filepath.rstrip(filepath.split('\\')[-1].split('/')[-1])

def isWild(in_str):
	wcards = [ "*", "?", "[", "]" ]
	for char in wcards:
		if in_str.find(char) != -1: return True

def getEngineBranchName():
	for branch in src_branches:
		if branch[0] == bpy.context.scene.smd_studiomdl_branch:
			return branch[1]

# rounds to 6 decimal places, converts between "1e-5" and "0.000001", outputs str
def getSmdFloat(fval):
	val = "{:.6f}".format(float(fval))
	if val[0] != "-": val = " " + val
	return val

# joins up "quoted values" that would otherwise be delimited, removes comments
def parseQuoteBlockedLine(line,lower=True):
	if len(line) == 0:
		return ["\n"]

	words = []
	last_word_start = 0
	in_quote = in_whitespace = False

	# The last char of the last line in the file was missed
	if line[-1] != '\n':
		line += '\n'

	for i in range(len(line)):
		char = line[i]
		nchar = pchar = None
		if i < len(line)-1:
			nchar = line[i+1]
		if i > 0:
			pchar = line[i-1]

		# line comment - precedence over block comment
		if (char == "/" and nchar == "/") or char in ['#',';']:
			if i > 0:
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

	if line.endswith("\\\\\n") and (len(words) == 0 or words[-1] != "\\\\"):
		words.append("\\\\") # macro continuation beats everything

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

def PrintVer(in_seq,sep="."):
		rlist = list(in_seq[:])
		rlist.reverse()
		out = ""
		for val in rlist:
			if int(val) == 0 and not len(out):
				continue
			out = "{}{}{}".format(str(val),sep if sep else "",out) # NB last value!
		if out.count(sep) == 1:
			out += "0" # 1.0 instead of 1
		return out.rstrip(sep)

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
		return Matrix.Rotation(pi/2,4,'Y')
	if axis.upper() == 'Y':
		return Matrix.Rotation(pi/2,4,'X')
	if axis.upper() == 'Z':
		return Matrix.Rotation(0,4,'Z')
	else:
		raise AttributeError("getUpAxisMat got invalid axis argument '{}'".format(axis))

def VecXMat(vec, mat):
	return vec * mat.inverted()

# Get a list of bone names sorted so parents come before children.
# Also assign a unique SMD ID to every bone.
# Changes smd.boneIDs, smd.boneNameToID, and smd.sortedBones
# NOTE: This seems to return the same order that bones are read in.
def sortBonesForExport():

	smd.boneIDs = {}
	smd.boneNameToID = {}

	def addBonesToSortedList(smd_id,bone,boneList):
		boneList.append(bone.name)
		smd.boneIDs[smd_id] = bone.name
		smd.boneNameToID[bone.name] = smd_id
		smd_id += 1
		for child in bone.children:
			smd_id = addBonesToSortedList(smd_id,child,boneList)
		return smd_id

	if smd.a.data.smd_implicit_zero_bone:
		smd_id = 1
	else:
		smd_id = 0
	smd.sortedBones = []
	for bone in smd.a.data.bones:
		if not bone.parent:
			smd_id = addBonesToSortedList(smd_id,bone,smd.sortedBones)

def getRotAsEuler(thing):
	out = Vector()
	mode = thing.rotation_mode
	if len(mode) == 3: # matches XYZ and variants
		# CRIKEY! But exec() is needed to turn the rotation_mode string into a property on the Vector
		exec("out." + thing.rotation_mode.lower() + " = Vector(thing.rotation_euler) * ryz90")
	elif mode == 'QUATERNION':
		out = thing.rotation_Quaternionernion.to_euler()
	elif mode == 'AXIS_ANGLE':
		# Blender provides no conversion function!
		x = thing.rotation_axis_angle[0]
		y = thing.rotation_axis_angle[1]
		z = thing.rotation_axis_angle[2]
		ang = thing.rotation_axis_angle[3]
		s = sin(ang)
		c = cos(ang)
		t = 1-c
		if (x*y*t + z*s) > 0.998: # north pole singularity
			out.x = 2 * atan2( x*sin(ang/2), cos(ang/2) )
			out.y = pi/2
			out.z = 0
		elif (x*y*t + z*s) < -0.998: # south pole singularity
			out.x = -2 * atan2( x*sin(ang/2), cos(ang/2) )
			out.y = -pi/2
			out.z = 0
		else:
			out.x = atan2(y * s- x * z * t , 1 - (y*y+ z*z ) * t)
			out.y = asin(x * y * t + z * s)
			out.z = atan2(x * s - y * z * t , 1 - (x*x + z*z) * t)
	else:
		log.error(thing.name,"uses an unknown rotation mode.")
	return out

axes = (('X','X',''),('Y','Y',''),('Z','Z',''))

def MakeObjectIcon(object,prefix=None,suffix=None):
	if not (prefix or suffix):
		raise TypeError("A prefix or suffix is required")

	if object.type == 'TEXT':
		type = 'FONT'
	else:
		type = object.type

	out = ""
	if prefix:
		out += prefix
	out += type
	if suffix:
		out += suffix
	return out

def getObExportName(ob):
	if ob.get('smd_name'):
		return ob['smd_name']
	else:
		return ob.name

def removeObject(obj):
	d = obj.data
	type = obj.type

	if type == "ARMATURE":
		for child in obj.children:
			if child.type == 'EMPTY':
				removeObject(child)

	bpy.context.scene.objects.unlink(obj)
	if obj.users == 0:
		if type == 'ARMATURE' and obj.animation_data:
			obj.animation_data.action = None # avoid horrible Blender bug that leads to actions being deleted

		bpy.data.objects.remove(obj)
		if d and d.users == 0:
			if type == 'MESH':
				bpy.data.meshes.remove(d)
			if type == 'ARMATURE':
				bpy.data.armatures.remove(d)

	return None if d else type

def hasShapes(ob,groupIndex = -1):
	def _test(t_ob):
		return t_ob.type in shape_types and t_ob.data.shape_keys and len(t_ob.data.shape_keys.key_blocks) > 1

	if groupIndex != -1:
		for g_ob in ob.users_group[groupIndex].objects:
			if _test(g_ob): return True
		return False
	else:
		return _test(ob)

def getDirSep():
	if os.name is 'nt':
		return "\\"
	else:
		return "/"

########################
#        Import        #
########################

# Identifies what type of SMD this is. Cannot tell between reference/lod/collision meshes!
def scanSMD():
	for line in smd.file:
		if line == "triangles\n":
			smd.jobType = REF
			print("- This is a mesh")
			break
		if line == "vertexanimation\n":
			print("- This is a flex animation library")
			smd.jobType = FLEX
			break

	# Finished the file

	if smd.jobType == None:
		print("- This is a skeltal animation or pose") # No triangles, no flex - must be animation
		if smd.append:
			for object in bpy.context.scene.objects:
				if object.type == 'ARMATURE':
					smd.jobType = ANIM
		if smd.jobType == None: # support importing animations on their own
			smd.jobType = ANIM_SOLO

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
def validateBones(target):
	bpy.ops.object.mode_set(mode='OBJECT',toggle=False)
	smd.aBoneInfo = bones_info.fromArmature(smd_manager.a)
	extraAncestors = []
	missingBones = []
	if smd.isDMX:
		smd.boneInfo = bones_info.fromArmature(smd.a)
	for poseBoneInfo in smd.boneInfo.boneList():
		# If the pose armature has a bone that the rest armature does not, just ignore it.
		if not smd.aBoneInfo.hasBone(poseBoneInfo.smdName):
			missingBones.append(poseBoneInfo.smdName)
			continue
		restBoneInfo = smd.aBoneInfo.boneBySmdName(poseBoneInfo.smdName)
		restParentName = restBoneInfo.parent.smdName.lower() if restBoneInfo.parent else None
		poseParentName = poseBoneInfo.parent.smdName.lower() if poseBoneInfo.parent else None
		# Typical case: both pose and rest bones have the same parent (or None).
		if poseParentName == restParentName:
			#print('pose bone %s parent same as in rest armature' % poseBoneInfo.smdName)
			#poseBoneInfo.animParent = restBoneInfo.parent.mangledName if restBoneInfo.parent else None
			continue
		# Now there can be 2 situations:
		# 1) the pose bone has extra ancestor bones between it and the rest bone's parent (which may be None)
		# 2) the rest bone has extra ancestor bones between it and the pose bone's parent (which may be None)
		# Case 1) is solved by simply ignoring the extra ancestor pose bones.
		# Case 2) is tricky, must insert extra ancestor bones into the pose armature.

		poseAncestors = poseBoneInfo.ancestors()
		restAncestors = restBoneInfo.ancestors()

		poseBoneInfo.animParent = None

		if len(restAncestors) > 0:
			# Case 1) extra pose bone ancestors ignored
			poseBoneInfo.animParent = restAncestors[0].smdName

		for restAncInfo in restAncestors:
			commonAncestor = None
			for poseAncInfo in poseAncestors:
				if poseAncInfo.sameName(restAncInfo):
					commonAncestor = restAncInfo
					break
			if commonAncestor == restAncInfo:
				print('common ancestor of %s is %s' % (poseBoneInfo.smdName,restAncInfo.smdName))
				break
			# buggy_reference:                    tau_reference:
			#   Frame                               Frame
			#     Gun_Base                            Gun_Base
			#       Gun_Parent                      Gun
			#         Gun
			if smd.boneInfo.hasBone(restAncInfo.smdName):
				continue
			# Case 2) extra rest bone ancestor detected
			if not restAncInfo in extraAncestors:
				extraAncestors.append(restAncInfo)
			print('extra ancestor of %s is %s' % (poseBoneInfo.smdName,restAncInfo.smdName))

	# Now add the extra ancestors to the bone list
	for extraInfo in reversed(extraAncestors):
		info = bone_info()
		info.mangledName = smd.boneInfo.uniqueBoneName(extraInfo.smdName)
		info.smdName = extraInfo.smdName
		info.ID = smd.boneInfo.nextID
		if extraInfo.parent:
			info.setParent(smd.boneInfo.boneBySmdName(extraInfo.parent.smdName)) # FIXME: not certain parent was created yet
			info.animParent = info.parent.smdName
		info.isExtra = True
		smd.boneInfo.addBone(info)

	if len(missingBones) > 0:
		print('The following bones are missing in the \"%s\" armature:' % smd.a.name)
		for boneName in missingBones:
			print('  ',boneName)
	
	if smd.a != target:
		removeObject(smd.a)
		smd.a = target

	print("- Validated %i bones against \"%s\" armature" % (smd.boneInfo.numBones(), smd.a.name))

class bone_info:
	def __init__(self):
		self.mangledName = None
		self.smdName = None
		self.ID = None
		self.parent = None
		self.children = []
		self.animParent = None
		self.extraAncestors = []
		self.isExtra = False
		self.head = Vector([0,0,0])

	def setParent(self,parent):
		self.parent = parent
		if parent:
			parent.addChild(self)

	def addChild(self,child):
		assert(not child in self.children)
		self.children.append(child)

	def ancestors(self):
		result = []
		iter = self.parent
		while iter:
			result.append(iter)
			iter = iter.parent
		return result

	def sameName(self,other):
		if not other: return False
		return self.smdName.lower() == other.smdName.lower()

	def children_recursive(self):
		result = []
		for child in self.children:
			result.append(child)
			result.extend(child.children_recursive())
		return result

	@classmethod
	def fromArmature(cls,bone,ID,parent=None):
		boneInfo = bone_info()
		boneInfo.ID = ID
		boneInfo.mangledName = bone.name
		boneInfo.smdName = bone.get('smd_name') or bone.name
		boneInfo.setParent(parent)
		boneInfo.animParent = parent.mangledName if parent else None # was " = parent"
		return boneInfo

	#def __repr__(self):
	#	return self.smdName

class bones_info:
	def __init__(self):
		self.bones = []
		self.mangledNameToBone = {}
		self.smdNameToBone = {}
		self.IDToBone = {}
		self.nextID = 0

	def addBone(self,bone):
		assert(not bone in self.bones)
		assert(not bone.mangledName in self.mangledNameToBone.keys())
		assert(not bone.ID in self.IDToBone.keys())
		self.bones.append(bone)
		self.mangledNameToBone[bone.mangledName] = bone
		# In the case of duplicate bone names, the first bone is the one
		# matched when looking up a bone by its smd name.  I believe this
		# is how studiomdl matches bone names in the case of duplicates.
		if not bone.smdName.lower() in self.smdNameToBone.keys():
			self.smdNameToBone[bone.smdName.lower()] = bone
		self.IDToBone[bone.ID] = bone
		if bone.ID >= self.nextID:
			self.nextID = bone.ID + 1

	def uniqueBoneName(self,smdName):
		mangledBoneName = smdName

		# Remove "ValveBiped." prefix, a leading cause of bones name length going over Blender's limit.
		ValveBipedCheck = mangledBoneName.split("ValveBiped.",1)
		if len(ValveBipedCheck) > 1:
			mangledBoneName = ValveBipedCheck[1]

		# Ensure the truncated bone name is unique.
		# 31 is the max Blender bone name length (32 with null-terminator).
		return uniqueName(mangledBoneName, self.mangledNameToBone.keys(), 31)

	def boneList(self):
		return self.bones

	def hasBone(self,smdName):
		return smdName.lower() in self.smdNameToBone

	def boneByName(self,name):
		return self.mangledNameToBone[name]

	def boneBySmdName(self,name):
		return self.smdNameToBone[name.lower()]

	def boneByID(self,id):
		return self.IDToBone[id]

	def numBones(self):
		return len(self.bones)

	@classmethod
	def fromArmature(cls,arm):
		info = bones_info()
		assert(len(arm.data.bones) > 0)
		for bone in arm.data.bones:
			if not bone.parent:
				boneInfo = bone_info.fromArmature(bone,info.nextID)
				info.addBone(boneInfo)
				for child in bone.children_recursive: # depth-first
					parentInfo = info.boneByName(child.parent.name)
					childInfo = bone_info.fromArmature(child,info.nextID,parentInfo)
					info.addBone(childInfo)
		return info

# Read the 'nodes' block in the SMD file.
# Info about the bones is stored in a new object of class 'bones_info'.
def readNodes():
	mangledBoneList = []
	duplicateBoneNames = []
	bones = bones_info()
	for line in smd.file:
		if line == "end\n":
			break

		values = parseQuoteBlockedLine(line,lower=False)

		if bones.hasBone(values[1]):
			if not values[1] in duplicateBoneNames:
				duplicateBoneNames.append(values[1])

		bone = bone_info()
		bone.ID = int(values[0])
		bone.smdName = values[1]
		parentID = int(values[2])
		if parentID != -1:
			bone.setParent(bones.boneByID(parentID))
			bone.animParent = bone.parent.smdName
		bone.mangledName = bones.uniqueBoneName(bone.smdName)

		bones.addBone(bone)

	if len(duplicateBoneNames) > 0:
		log.warning('%d bone names appear more than once' % len(duplicateBoneNames))
		print('The following bone names appear more than once:')
		for boneName in duplicateBoneNames:
			print('  ',boneName)

	# All bones parsed!
	return bones

def findArmature():
	# Search the current scene for an existing armature - there can only be one skeleton in a Source model
	if bpy.context.active_object and bpy.context.active_object.type == 'ARMATURE':
		smd.a = bpy.context.active_object
	else:
		def isArmIn(list):
			for ob in list:
				if ob.type == 'ARMATURE':
					smd.a = ob
					return True

		isArmIn(bpy.context.selected_objects) # armature in the selection?

		if not smd.a:
			for ob in bpy.context.selected_objects:
				if ob.type == 'MESH':
					smd.a = ob.find_armature() # armature modifying a selected object?
					if smd.a:
						break
		if not smd.a:
			isArmIn(bpy.context.scene.objects) # armature in the scene at all?

	return smd.a

# nodes block
def readBones():
	smd.boneInfo = readNodes()

	if smd.append and findArmature():
		if smd.jobType == REF:
			smd.jobType = REF_ADD
		validateBones(smd.a)
		return

	# Got this far? Then this is a fresh import which needs a new armature.
	smd.a = createArmature(smd_manager.jobName)
	smd.a.data.smd_implicit_zero_bone = False # Too easy to break compatibility, plus the skeleton is probably set up already

	try:
		qc.a = smd.a
	except NameError:
		pass

	print("- Imported %i new bones" % smd.boneInfo.numBones())

	if len(smd.a.data.bones) > 128:
		log.warning("Source only supports 128 bones!")

# Creates a new armature based on the smd.boneInfo object of class 'bones_info'.
# This may get called twice, once on initial import and again if importing an animation.
def createArmature(armature_name):

	if bpy.context.active_object:
		bpy.ops.object.mode_set(mode='OBJECT',toggle=False)
	a = bpy.data.objects.new(armature_name,bpy.data.armatures.new(armature_name))
	a.show_x_ray = True
	a.data.draw_type = 'STICK'
	bpy.context.scene.objects.link(a)
	for i in bpy.context.selected_objects: i.select = False #deselect all objects
	a.select = True
	bpy.context.scene.objects.active = a
	ops.object.mode_set(mode='EDIT')

	if not smd.isDMX:
		warnNames = []

		for bone in smd.boneInfo.boneList():

			newBone = a.data.edit_bones.new(bone.mangledName)
			newBone.tail = 0,1,0

			if not bone.mangledName in bone.smdName:
				warnNames.append(bone.smdName)

			if newBone.name != bone.smdName:
				newBone['smd_name'] = bone.smdName # This is the bone name that will be written to the SMD.

			if bone.parent != None:
				newBone.parent = a.data.edit_bones[bone.parent.mangledName]

		ops.object.mode_set(mode='OBJECT')

		length = len(warnNames)
		if length > 0:
			log.warning('%d bone name%s truncated to 31 characters' % (length,'s were' if length > 1 else ' was'))
			print("The following bone names were truncated to 31 characters:")
			for name in warnNames:
				print('  ',name)

	return a

# matAllRest - one matrix per bone (in target armature) in armature-space coordinates.
# matAllPose - one matrix per bone (in pose armature) in armature-space coordinates.
def applyPoseForThisFrame(matAllRest, matAllPose):
	frame = bpy.context.scene.frame_current

	for boneName in matAllRest.keys():
		if not boneName in matAllPose.keys():
			continue
		matRest = matAllRest[boneName]
		matPose = matAllPose[boneName]['mat']

		restBone = smd.a.pose.bones[boneName]
		if restBone.parent:
			parentName = restBone.parent.name
			matRest = matAllRest[parentName].inverted() * matRest

		boneInfo = smd.boneInfo.boneByName(boneName)
		if boneInfo.animParent:
			parentName = smd.boneInfo.boneBySmdName(boneInfo.animParent).mangledName
			matPose = matAllPose[parentName]['mat'].inverted() * matPose
		matDelta = matRest.inverted() * matPose

		if matAllPose[boneName]['rot']:
			rot_quat = matDelta.to_quaternion()
			restBone.rotation_mode = 'QUATERNION'
			restBone.rotation_quaternion = rot_quat
			restBone.keyframe_insert('rotation_quaternion',-1,frame,boneName)

		if matAllPose[boneName]['pos']:
			loc = matDelta.to_translation()
			restBone.location = loc
			restBone.keyframe_insert('location',-1,frame,boneName)

def sortBonesForImport():
	# Get a list of bone names sorted so parents come before children.
	# Include all bones in the target armature.
	smd.restBoneNames = []
	for bone in smd.a.data.bones:
		if not bone.parent:
			smd.restBoneNames.append(bone.name)
			for child in bone.children_recursive: # depth-first
				smd.restBoneNames.append(child.name)

def TidyArmature():
	ops.object.mode_set(mode='OBJECT')

	if smd.jobType in [REF,ANIM_SOLO] and len(smd.a.data.bones) > 1:
		# Calculate armature dimensions...Blender should be doing this!
		maxs = [0,0,0]
		mins = [0,0,0]
		for bone in smd.a.data.bones:
			#if not smd.m or smd.m.vertex_groups.get(bone.name):
			for i in range(3):
				maxs[i] = max(maxs[i],bone.head_local[i])
				mins[i] = min(mins[i],bone.head_local[i])

		dimensions = []
		for i in range(3):
			dimensions.append(maxs[i] - mins[i])
		smd_manager.dimensions = dimensions

		length = (dimensions[0] + dimensions[1] + dimensions[2]) / 600 # very small indeed, but a custom bone is used for display
		if length < 0.001: # Blender silently deletes bones whose length is <= 0.000001
			length = 0.001 # could be only a single bone (static prop for example)

		# Generate custom bone shape; a simple sphere
		# It would be nice if Blender could draw bones in this way by itself
		bone_vis = bpy.data.objects.get("smd_bone_vis")
		if not bone_vis:
			bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3,size=2)
			bone_vis = bpy.context.active_object
			bone_vis.data.name = bone_vis.name = "smd_bone_vis"
			bone_vis.use_fake_user = True
			bpy.context.scene.objects.unlink(bone_vis) # don't want the user deleting this
			bpy.context.scene.objects.active = smd.a

		ops.object.mode_set(mode='EDIT')
		for bone in smd.a.data.edit_bones:
			bone.tail = bone.head + (bone.tail - bone.head).normalized() * length # Resize loose bone tails based on armature size

		ops.object.mode_set(mode='POSE')
		for bone in smd.a.pose.bones:
			bone.custom_shape = bone_vis # apply bone shape

		ops.object.mode_set(mode='OBJECT')

def readFrames():
	# We only care about the pose data in some SMD types
	if smd.jobType not in [ REF, ANIM, ANIM_SOLO ]:
		return

	a = smd.a
	bones = a.data.bones
	scn = bpy.context.scene
	prevFrame = scn.frame_current
	scn.frame_set(0)
	bpy.context.scene.objects.active = smd.a
	ops.object.mode_set(mode='OBJECT')

	if smd.jobType in [ANIM,ANIM_SOLO]:
		if not a.animation_data:
			a.animation_data_create()
		act = a.animation_data.action = bpy.data.actions.new(smd.jobName)
		if act.name != smd.jobName:
			act['smd_name'] = smd.jobName
		act.use_fake_user = True

		# Get a list of bone names sorted so parents come before children.
		# Include all bones in the current SMD.
		smd.poseBoneNames = []
		for bone in smd.boneInfo.boneList():
			if not bone.parent:
				smd.poseBoneNames.append(bone.mangledName)
				for child in bone.children_recursive(): # depth-first
					smd.poseBoneNames.append(child.mangledName)

	sortBonesForImport()

	if not smd.isDMX:
		readFrameData() # Read in all the frames
	
	if smd.jobType in [REF,ANIM_SOLO]:
		assert bpy.context.scene.objects.active == smd.a
		bpy.ops.object.mode_set(mode='EDIT', toggle=False) # smd.a -> edit mode
		applyFrameDataRest(smd.frameData[0])
		# Got to go from EDIT to OBJECT to ensure changes are copied from smd.a.data.edit_bones to smd.a.data.bones
		bpy.ops.object.mode_set(mode='OBJECT', toggle=False) # smd.a -> object mode

	if smd.jobType in [ANIM,ANIM_SOLO]:
		# Get all the armature-space matrices for the bones at their rest positions
		smd.matAllRest = {}
		assert bpy.context.scene.objects.active == smd.a
		assert smd.a.mode == 'OBJECT'
		for bone in smd.a.data.bones:
			smd.matAllRest[bone.name] = bone.matrix_local.copy() * Matrix.Scale(smd.a.scale.x,4,Vector([1,0,0])) * Matrix.Scale(smd.a.scale.y,4,Vector([0,1,0])) * Matrix.Scale(smd.a.scale.z,4,Vector([0,0,1]))

		# Step 1: set smd.poseArm pose and store the armature-space matrices in smd.matAllPose for each frame
		smd.matAllPose = []	
		for i in range(len(smd.frameData)):
			applyFrameDataPose(smd.frameData[i])
			bpy.context.scene.frame_current += 1

		# Step 2: set smd.a pose and set keyframes where desired for each frame
		assert bpy.context.scene.objects.active == smd.a
		bpy.ops.object.mode_set(mode='POSE') # smd.a -> pose mode
		bpy.context.scene.frame_set(0)
		for i in range(len(smd.frameData)):
			smd.last_frame_values = applyPoseForThisFrame( smd.matAllRest, smd.matAllPose[i] )
			bpy.context.scene.frame_current += 1

	# All frames read

	if smd.jobType in [ANIM,ANIM_SOLO]:
		scn.frame_start = 0
		scn.frame_end = scn.frame_current - 1

		if not smd.isDMX:
			# Remove every point but the first if every following point is within a certain deviation
			for fcurve in smd.a.animation_data.action.fcurves:
				last_frame = len(fcurve.keyframe_points)
				co = fcurve.keyframe_points[0].co[1]
				deviant = 0
				for i in range(1,last_frame):
					co2 = fcurve.keyframe_points[i].co[1]
					if abs(co-co2) > 0.0001:
						deviant = 1
						break
				if not deviant:
					for i in reversed(range(1,last_frame)):
						pt = fcurve.keyframe_points[i]
						fcurve.keyframe_points.remove(pt,fast=True)
		if 0:
			# Remove points that are the same as the previous and next points
			for fcurve in smd.a.animation_data.action.fcurves:
				last_frame = len(fcurve.keyframe_points)
				i = 1
				while i < last_frame - 1:
					ptPrev = fcurve.keyframe_points[i-1]
					ptCur  = fcurve.keyframe_points[i]
					ptNext = fcurve.keyframe_points[i+1]
					if abs(ptPrev.co[1] - ptCur.co[1]) <= 0.00001 and abs(ptCur.co[1] - ptNext.co[1]) <= 0.00001:
						fcurve.keyframe_points.remove(ptCur,fast=True)
						last_frame -= 1
					else:
						i += 1

	TidyArmature()

	print("- Imported %i frames of animation" % scn.frame_current)
	if prevFrame == 1: # Blender starts on 1, Source starts on 0
		prevFrame = 0
	bpy.context.scene.frame_set(prevFrame)

def readFrameData():
	smd.frameData = []
	cur_frame = {}
	if smd.file.readline() == "end\n": return # skip first frame header

	for line in smd.file:

		if line == "end\n":
			smd.frameData.append(cur_frame)
			break

		values = line.split()

		if values[0] == "time": # n.b. frame number is a dummy value, all frames are equally spaced
			if smd.jobType == REF:
				log.warning("Found animation in reference mesh \"{}\", ignoring!".format(smd.jobName))
				continue
			smd.frameData.append(cur_frame)
			cur_frame = {}
			continue

		# Lookup the mangled bone name for this SMD's bone ID.
		smdID = int(values[0])
		boneInfo = smd.boneInfo.boneByID(smdID)
		boneName = boneInfo.mangledName

		# Where the bone should be, local to its parent
		smd_pos = Vector([float(values[1]), float(values[2]), float(values[3])])
		smd_rot = Vector([float(values[4]), float(values[5]), float(values[6])])

		# A bone's rotation matrix is used only by its children, a symptom of the transition from Source's 1D bones to Blender's 2D bones.
		# Also, the floats are inversed to transition them from Source (DirectX; left-handed) to Blender (OpenGL; right-handed)
		rotMat = Matrix.Rotation(-smd_rot.x, 3,'X') * Matrix.Rotation(-smd_rot.y, 3,'Y') * Matrix.Rotation(-smd_rot.z, 3,'Z')

		cur_frame[boneName] = {'pos':smd_pos, 'rot':rotMat}

	# Handle any extra bones added to the pose armature.
	# This code is just like the rest-pose export code, used to determine the smd_pos and smd_rot
	# of the extra bones in the rest armature.
	assert(smd.a == bpy.context.scene.objects.active)
	assert smd.a.mode == 'OBJECT'
	#bpy.ops.object.mode_set(mode='OBJECT', toggle=False) # smd.a -> object mode
	for boneInfo in smd.boneInfo.boneList():
		if not boneInfo.isExtra: continue
		aBoneInfo = smd.aBoneInfo.boneBySmdName(boneInfo.smdName)
		pbn = smd.a.data.bones[aBoneInfo.mangledName]
		if pbn.parent:
			parentRotated = pbn.parent.matrix_local * ryz90
			childRotated = pbn.matrix_local * ryz90
			rot = parentRotated.inverted() * childRotated
			pos = rot.to_translation()
		else:
			rot = pbn.matrix_local * ryz90
			if smd_manager == 'Y':
				rot = rx90n * rot
			pos = rot.to_translation()
		rot = rot.to_euler('XYZ')
		rotMat = Matrix.Rotation(-rot.x, 3,'X') * Matrix.Rotation(-rot.y, 3,'Y') * Matrix.Rotation(-rot.z, 3,'Z')
		smd.frameData[0][boneInfo.mangledName] = {'pos':pos, 'rot':rotMat} # every frame is the same as the first
	#bpy.ops.object.mode_set(mode='EDIT', toggle=False) # smd.a -> edit mode

	# Every bone must be listed for the first frame of an animation.
	# After the first frame a bone may not be listed in the SMD if it didn't change from a previous frame.
	for i in range(1,len(smd.frameData)):
		for boneName in smd.poseBoneNames:
			if not boneName in smd.frameData[i]:
				smd.frameData[i][boneName] = smd.frameData[i-1][boneName]

def applyFrameDataRest(frameData):

	# frameData[boneName]['rot'] holds the last valid parent-relative matrix we read in.  This holds the armature-relative matrix.
	rotMats = {}

	if smd_manager.upAxis == 'Z':
		tail_vec = Vector([1,0,0])
		roll_vec = Vector([0,1,0])
	elif smd_manager.upAxis == 'Y':
		tail_vec = Vector([0,-1,0])
		roll_vec = Vector([0,0,1])
		# Bone axis is a whole other can of worms that will have to be looked at.
		# If this changes the export code may need updating.
		tail_vec = Vector([1,0,0])
		roll_vec = Vector([0,1,0])
	elif smd_manager.upAxis == 'X':
		# FIXME: same as Z for now
		tail_vec = Vector([1,0,0])
		roll_vec = Vector([0,1,0])
	for boneName in smd.restBoneNames:

		try:
			smd_pos = frameData[boneName]['pos']
		except KeyError:
			log.error("Bone \"{}\" on armature \"{}\" has no rest position".format(boneName,smd.a.name))
			continue

		rotMats[boneName] = frameData[boneName]['rot']

		# *************************************************
		# Set rest positions. This happens only for the first frame, but not for an animation SMD.

		assert smd.a.mode == 'EDIT'
		bn = smd.a.data.edit_bones[boneName]

		if bn.parent:
			rotMats[boneName] *= rotMats[bn.parent.name] # make rotations cumulative
			bn.head = bn.parent.head + VecXMat(smd_pos, rotMats[bn.parent.name])
			bn.tail = bn.head + VecXMat(tail_vec, rotMats[boneName])
			bn.align_roll( VecXMat(roll_vec, rotMats[boneName]) )
		else:
			bn.head = smd_pos
			bn.tail = bn.head + VecXMat(tail_vec, rotMats[boneName])
			bn.align_roll( VecXMat(roll_vec, rotMats[boneName]) )

	#bpy.context.scene.update() # https://projects.blender.org/tracker/index.php?func=detail&aid=25830&group_id=9&atid=498
	#for atch in smd.attachments:
	#	atch.matrix_local *= rotMats[ atch.constraints[-1].subtarget ].to_4x4().inverted()

	#for atch in smd.attachments:
	#	pMat = rotMats[ atch.constraints[-1].subtarget ].inverted() * rx90.to_3x3()
	#	atch.location = VecXMat(atch.location, pMat) #* rx90.to_3x3()
	#	atch.rotation_euler = VecXMat(Vector(atch.rotation_euler), pMat) #* rx90

	if smd_manager.upAxis == 'Y':
		upAxisMat = rx90
		for boneName in smd.restBoneNames:
			bone = smd.a.data.edit_bones[boneName]
			z_axis = bone.z_axis
			bone.head *= upAxisMat
			bone.tail *= upAxisMat
			#bone.align_roll(roll_vec * rotMats[boneName] * upAxisMat)
			bone.align_roll(z_axis * upAxisMat) # same as above

def applyFrameDataPose(frameData):
	# frameData[boneName]['rot'] holds the last valid parent-relative matrix we read in.  This holds the armature-relative matrix.
	rotMats = {}
	matAllPose = {}

	if smd_manager.upAxis == 'Z':
		x_vec = Vector([0,0,1])
		y_vec = Vector([1,0,0])
		z_vec = Vector([0,1,0])
	elif smd_manager.upAxis == 'Y':
		x_vec = Vector([1,0,0])
		y_vec = Vector([0,-1,0])
		z_vec = Vector([0,0,1])
		# Bone axis is a whole other can of worms that will have to be looked at.
		# If this changes the export code may need updating.
		x_vec = Vector([0,0,1])
		y_vec = Vector([1,0,0])
		z_vec = Vector([0,1,0])
	elif smd_manager.upAxis == 'X':
		# FIXME: same as Z for now
		x_vec = Vector([0,0,1])
		y_vec = Vector([1,0,0])
		z_vec = Vector([0,1,0])

	for boneName in smd.poseBoneNames:

		if not frameData.get(boneName):
			continue

		smd_pos = frameData[boneName]['pos']
		rotMats[boneName] = frameData[boneName]['rot']

		# *****************************************
		# Set pose positions. This happens for every frame, but not for a reference pose.

		boneInfo = smd.boneInfo.boneByName(boneName)
		if boneInfo.parent:
			parentName = boneInfo.parent.mangledName
		
		if rotMats[boneName] != "empty":
			if boneInfo.parent:
				rotMats[boneName] *= rotMats[parentName] # make rotations cumulative
		else:
			rotMats[boneName] = Matrix.Rotation(0,3,'Z')
		
		if smd_pos != "empty":
			if boneInfo.parent:
				boneInfo.head = boneInfo.parent.head + VecXMat(smd_pos, rotMats[parentName])
			else:
				boneInfo.head = smd_pos

		x_axis = VecXMat(x_vec, rotMats[boneName])
		y_axis = VecXMat(y_vec, rotMats[boneName])
		z_axis = VecXMat(z_vec, rotMats[boneName])
		if boneInfo.head:
			location = boneInfo.head.copy()
		else:
			location = smd.a.bones[poseBoneNames].head

		x_axis.resize_4d()
		x_axis[3] = 0
		y_axis.resize_4d()
		y_axis[3] = 0
		z_axis.resize_4d()
		z_axis[3] = 0
		location.resize_4d()

		matAllPose[boneName] = { 'mat':mathutils.Matrix( (x_axis,y_axis,z_axis,location) ), 'pos':smd_pos != "empty", 'rot': frameData[boneName]['rot'] != "empty" }

	if smd_manager.upAxis == 'Y':
		for boneName in smd.poseBoneNames:
			if matAllPose.get(boneName):
				matAllPose[boneName]['mat'] = rx90 * matAllPose[boneName]['mat']# global rot around X

	smd.matAllPose.append(matAllPose)

def getMeshMaterial(in_name):
	if in_name == "": # buggered SMD
		in_name = "Material"
	md = smd.m.data
	long_name = len(in_name) > 21
	mat = None
	for candidate in bpy.data.materials: # Do we have this material already?
		if candidate.name == in_name or candidate.get('smd_name') == in_name:
			mat = candidate
	if mat:
		if md.materials.get(mat.name): # Look for it on this mesh
			for i in range(len(md.materials)):
				if md.materials[i].name == mat.name:
					mat_ind = i
					break
		else: # material exists, but not on this mesh
			md.materials.append(mat)
			mat_ind = len(md.materials) - 1
	else: # material does not exist
		print("- New material: %s" % in_name)
		mat = bpy.data.materials.new(in_name)
		md.materials.append(mat)
		# Give it a random colour
		randCol = []
		for i in range(3):
			randCol.append(random.uniform(.4,1))
		mat.diffuse_color = randCol
		if smd.jobType != PHYS:
			mat.use_face_texture = True # in case the uninitated user wants a quick rendering
		else:
			smd.m.draw_type = 'SOLID'
		mat_ind = len(md.materials) - 1
		if long_name: # Save the original name as a custom property.
			mat['smd_name'] = in_name
			if not in_name in smd.truncMaterialNames:
				smd.truncMaterialNames.append(in_name)

	return mat, mat_ind

def setLayer():
	layers = [False] * len(smd.m.layers)
	layers[smd.layer] = bpy.context.scene.layers[smd.layer] = True
	smd.m.layers = layers
	if smd.jobType == PHYS:
		smd.a.layers[smd.layer] = True
		for child in smd.a.children:
			if child.type == 'EMPTY':
				child.layers[smd.layer] = True

# triangles block
def readPolys():
	if smd.jobType not in [ REF, REF_ADD, PHYS ]:
		return

	# Create a new mesh object, disable double-sided rendering, link it to the current scene
	if smd.jobType == REF and not smd.jobName.lower().find("reference") and not smd.jobName.lower().endswith("ref"):
		meshName = smd.jobName + " ref"
	else:
		meshName = smd.jobName

	smd.m = bpy.data.objects.new(meshName,bpy.data.meshes.new(meshName))	
	if smd.m.name != smd.jobName:
		smd.m['smd_name'] = smd.jobName
	smd.m.data.show_double_sided = False
	smd.m.parent = smd.a
	bpy.context.scene.objects.link(smd.m)
	setLayer()
	if smd.jobType == REF:
		try:
			qc.ref_mesh = smd.m # for VTA import
		except NameError:
			pass

	# Create weightmap groups
	for bone in smd.a.data.bones.values():
		smd.m.vertex_groups.new(bone.name)

	# Apply armature modifier
	modifier = smd.m.modifiers.new(type="ARMATURE",name="Armature")
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

	smd.smdNameToMatName = {}
	for mat in bpy.data.materials:
		smd_name = mat['smd_name'] if mat.get('smd_name') else mat.name
		smd.smdNameToMatName[smd_name] = mat.name

	# *************************************************************************************************
	# There are two loops in this function: one for polygons which continues until the "end" keyword
	# and one for the vertices on each polygon that loops three times. We're entering the poly one now.
	countPolys = 0
	badWeights = 0
	for line in smd.file:
		line = line.rstrip("\n")

		if line == "end" or "":
			break

		mat, mat_ind = getMeshMaterial(line)
		mats.append(mat_ind)

		# ***************************************************************
		# Enter the vertex loop. This will run three times for each poly.
		vertexCount = 0
		for line in smd.file:
			values = line.split()
			vertexCount+= 1

			# TODO: transform coords to flip model onto Blender XZY, possibly scale it too

			# Read co-ordinates and normals
			for i in range(1,4): # 0 is deprecated bone weight value
				cos.append( float(values[i]) )
				norms.append( float(values[i+3]) ) # Blender currenty ignores this data!

			# Can't do these in the above for loop since there's only two
			uvs.append( float(values[7]) )
			uvs.append( float(values[8]) )

			# Read weightmap data, this is a bit more involved
			weights.append( [] ) # Blank array, needed in case there's only one weightlink
			if len(values) > 10 and values[9] != "0": # got weight links?
				for i in range(10, 10 + (int(values[9]) * 2), 2): # The range between the first and last weightlinks (each of which is *two* values)
					boneID = int(values[i])
					bone = smd.boneInfo.boneByID(boneID)
					if bone:
						boneName = bone.mangledName
						vertGroup = smd.m.vertex_groups.get(boneName)
						if vertGroup:
							weights[-1].append( [ vertGroup, float(values[i+1]) ] )
						else:
							badWeights += 1
					else:
						badWeights += 1
			else: # Fall back on the deprecated value at the start of the line
				boneID = int(values[0])
				bone = smd.boneInfo.boneByID(boneID)
				if bone:
					boneName = bone.mangledName
					weights[-1].append( [smd.m.vertex_groups[boneName], 1.0] )
				else:
					badWeights += 1

			# Three verts? It's time for a new poly
			if vertexCount == 3:
				uvs.extend([0,1]) # Dunno what this 4th UV is for, but Blender needs it
				break

		# Back in polyland now, with three verts processed.
		countPolys+= 1

	length = len(smd.truncMaterialNames)
	if length > 0:
		log.warning('%d material name%s truncated to 21 characters' % (length,'s were' if length > 1 else ' was'))
		print("The following material names were truncated to 21 characters:")
		for smdName in smd.truncMaterialNames:
			print('  ',smdName)

	if countPolys:
		# All polys processed. Add new elements to the mesh:
		md.vertices.add(countPolys*3)
		md.faces.add(countPolys)

		# Fast add!
		md.vertices.foreach_set("co",cos)
		md.vertices.foreach_set("normal",norms) # Blender currently ignores this data!
		md.faces.foreach_set("material_index", mats)
		md.uv_textures[0].data.foreach_set("uv",uvs)

		# Apply vertex groups
		for i in range(len(md.vertices)):
			for link in weights[i]:
				link[0].add( [i], link[1], 'REPLACE' )

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
		ops.mesh.faces_shade_smooth()
		ops.object.mode_set(mode='OBJECT')

		if smd.jobType == PHYS:
			# Phys meshes must have smoothed normals if they are to compile properly,
			# so now doing this instead
			smd.m.show_wire = True

		if smd_manager.upAxis == 'Y':
			md.transform(rx90)
			md.update()

		if badWeights:
			log.warning(badWeights,"vertices weighted to invalid bones!")
		print("- Imported %i polys" % countPolys)

# vertexanimation block
def readShapes():
	if smd.jobType is not FLEX:
		return

	if not smd.m:
		try:
			smd.m = qc.ref_mesh
		except NameError:
			smd.m = bpy.context.active_object # user selection
	smd.m.show_only_shape_key = True # easier to view each shape, less confusion when several are active at once
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
				smd.m.shape_key_add("Basis")
			else:
				smd.m.shape_key_add("Unnamed")

			num_shapes += 1
			continue # to the first vertex of the new shape

		cur_id = int(values[0])
		cur_cos = Vector([ float(values[1]), float(values[2]), float(values[3]) ])

		if making_base_shape: # create VTA vert ID -> mesh vert ID dictionary
			# Blender faces share verts; SMD faces don't. To simulate a SMD-like list of vertices, we need to
			# perform a bit of mathematical kung-fu:
			mesh_vert_id = smd.m.data.faces[floor(cur_id/3)].vertices[cur_id % 3] # FIXME: breaks if a face has any unique verts

			if cur_cos == smd.m.data.vertices[mesh_vert_id].co:
				co_map[cur_id] = mesh_vert_id # create the new dict entry
		else:
			try:
				smd.m.data.shape_keys.key_blocks[-1].data[ co_map[cur_id] ].co = cur_cos # write to the shapekey
			except KeyError:
				bad_vta_verts += 1


	if bad_vta_verts > 0:
		log.warning(bad_vta_verts,"VTA vertices were not matched to a mesh vertex!")
	print("- Imported",num_shapes-1,"flex shapes") # -1 because the first shape is the reference position

# Parses a QC file
def readQC( context, filepath, newscene, doAnim, makeCamera, outer_qc = False):
	filename = getFilename(filepath)
	filedir = getFileDir(filepath)

	global qc
	if outer_qc:
		print("\nQC IMPORTER: now working on",filename)
		qc = qc_info()
		qc.startTime = time.time()
		qc.jobName = filename
		qc.root_filedir = filedir
		qc.makeCamera = makeCamera
		qc.animation_names = []
		if newscene:
			bpy.context.screen.scene = bpy.data.scenes.new(filename) # BLENDER BUG: this currently doesn't update bpy.context.scene
		else:
			bpy.context.scene.name = filename
		global smd_manager
		smd_manager = qc

	file = open(filepath, 'r')
	in_bodygroup = in_lod = False
	lod = 0
	for line_str in file:
		line = parseQuoteBlockedLine(line_str)
		if len(line) == 0:
			continue
		#print(line)

		# handle individual words (insert QC variable values, change slashes)
		i = 0
		for word in line:
			for var in qc.vars.keys():
				kw = "${}$".format(var)
				pos = word.lower().find(kw)
				if pos != -1:
					word = word.replace(word[pos:pos+len(kw)], qc.vars[var])			
			line[i] = word.replace("/","\\") # studiomdl is Windows-only
			i += 1
		
		# Skip macros
		if line[0] == "$definemacro":
			log.warning("Skipping macro in QC {}".format(filename))
			while line[-1] == "\\\\":
				line = parseQuoteBlockedLine( file.readline())

		# register new QC variable
		if line[0] == "$definevariable":
			qc.vars[line[1]] = line[2].lower()
			continue

		# dir changes
		if line[0] == "$pushd":
			if line[1][-1] != "\\":
				line[1] += "\\"
			qc.dir_stack.append(line[1])
			continue
		if line[0] == "$popd":
			try:
				qc.dir_stack.pop()
			except IndexError:
				pass # invalid QC, but whatever
			continue

		# up axis
		if line[0] == "$upaxis":
			qc.upAxis = bpy.context.scene.smd_up_axis = line[1].upper()
			qc.upAxisMat = getUpAxisMat(line[1])
			continue
	
		# bones in pure animation QCs
		if line[0] == "$definebone":
			pass # TODO

		def loadSMD(word_index,ext,type, append=True,layer=0,in_file_recursion = False):
			path = line[word_index]
			if line[word_index][1] == ":": # absolute path; QCs can only be compiled on Windows
				path = appendExt(path,ext)
			else:
				path = qc.cd() + appendExt(path,ext)
			if not os.path.exists(path):
				if not in_file_recursion:
					if loadSMD(word_index,"dmx",type,append,layer,True):
						return True
					else:
						log.error("Could not open file",path)
						return False
			if not path in qc.imported_smds: # FIXME: an SMD loaded once relatively and once absolutely will still pass this test
				qc.imported_smds.append(path)
				if path.endswith("dmx"):
					readDMX(context,path,qc.upAxis,False,type,append,from_qc=True,target_layer=layer)
				else:
					readSMD(context,path,qc.upAxis,False,type,append,from_qc=True,target_layer=layer)		
				qc.numSMDs += 1			
			return True

		# meshes
		if line[0] in ["$body","$model"]:
			loadSMD(2,"smd",REF,True) # create new armature no matter what
			continue
		if line[0] == "$lod":
			in_lod = True
			lod += 1
			continue
		if in_lod:
			if line[0] == "replacemodel":
				loadSMD(2,"smd",REF_ADD,layer=lod)
				continue
			if "}" in line:
				in_lod = False
				continue
		if line[0] == "$bodygroup":
			in_bodygroup = True
			continue
		if in_bodygroup:
			if line[0] == "studio":
				loadSMD(1,"smd",REF) # bodygroups can be used to define skeleton
				continue
			if "}" in line:
				in_bodygroup = False
				continue

		# skeletal animations
		if doAnim and line[0] in ["$sequence","$animation"]:
			# there is no easy way to determine whether a SMD is being defined here or elsewhere, or even precisely where it is being defined
			num_words_to_skip = 0
			for i in range(2, len(line)):
				if num_words_to_skip:
					num_words_to_skip -= 1
					continue
				if line[i] == "{":
					break
				if line[i] in ["hidden","autolay","realtime","snap","spline","xfade","delta","predelta"]:
					continue
				if line[i] in ["fadein","fadeout","addlayer","blendwidth","node"]:
					num_words_to_skip = 1
					continue
				if line[i] in ["activity","transision","rtransition"]:
					num_words_to_skip = 2
					continue
				if line[i] in ["blend"]:
					num_words_to_skip = 3
					continue
				if line[i] in ["blendlayer"]:
					num_words_to_skip = 5
					continue
				# there are many more keywords, but they can only appear *after* an SMD is referenced
			
				if not qc.a: qc.a = findArmature()
			
				if line[i].lower() not in qc.animation_names:
					loadSMD(i,"smd",ANIM)
					if line[0] == "$animation":
						qc.animation_names.append(line[1].lower())
				break
			continue

		# flex animation
		if line[0] == "flexfile":
			loadSMD(1,"vta",FLEX)
			continue

		# naming shapes
		if line[0] in ["flex","flexpair"]: # "flex" is safe because it cannot come before "flexfile"
			for i in range(1,len(line)):
				if line[i] == "frame":
					qc.ref_mesh.data.shape_keys.key_blocks[int(line[i+1])-1].name = line[1] # subtract 1 because frame 0 isn't a real shape key
					break
			continue

		# physics mesh
		if line[0] in ["$collisionmodel","$collisionjoints"]:
			loadSMD(1,"smd",PHYS,layer=10) # FIXME: what if there are >10 LODs?
			continue

		# origin; this is where viewmodel editors should put their camera, and is in general something to be aware of
		if line[0] == "$origin":
			if qc.makeCamera:
				data = bpy.data.cameras.new(qc.jobName + "_origin")
				name = "camera"
			else:
				data = None
				name = "empty object"
			print("QC IMPORTER: created {} at $origin\n".format(name))

			origin = bpy.data.objects.new(qc.jobName + "_origin",data)
			bpy.context.scene.objects.link(origin)

			origin.rotation_euler = Vector([pi/2,0,pi]) + Vector(getUpAxisMat(qc.upAxis).inverted().to_euler()) # works, but adding seems very wrong!
			bpy.ops.object.select_all(action="DESELECT")
			origin.select = True
			bpy.ops.object.transform_apply(rotation=True)

			for i in range(3):
				origin.location[i] = float(line[i+1])
			origin.location *= getUpAxisMat(qc.upAxis).inverted()

			if qc.makeCamera:
				bpy.context.scene.camera = origin
				origin.data.lens_unit = 'DEGREES'
				origin.data.lens = 31.401752 # value always in mm; this number == 54 degrees
				# Blender's FOV isn't locked to X or Y height, so a shift is needed to get the weapon aligned properly.
				# This is a nasty hack, and the values are only valid for the default 54 degrees angle
				origin.data.shift_y = -0.27
				origin.data.shift_x = 0.36
				origin.data.passepartout_alpha = 1
			else:
				origin.empty_draw_type = 'PLAIN_AXES'

			qc.origin = origin

		# QC inclusion
		if line[0] == "$include":
			if line[1][1] == ":": # absolute path; QCs can only be compiled on Windows
				path = line[1]
			else:
				path = qc.root_filedir + line[1] # special case: ignores dir stack

			if not path.endswith(".qc") and not path.endswith(".qci"):
				if os.path.exists(appendExt(path,".qci")):
					path = appendExt(path,".qci")
				elif os.path.exists(appendExt(path,".qc")):
					path = appendExt(path,".qc")
			try:
				readQC(context,path,False, doAnim, makeCamera)
			except IOError:
				message = 'Could not open QC $include file "%s"' % path
				log.warning(message + " - skipping!")

	file.close()

	if qc.origin:
		qc.origin.parent = qc.a
		if qc.dimensions:
			size = min(qc.dimensions) / 15
			if qc.makeCamera:
				qc.origin.data.draw_size = size
			else:
				qc.origin.empty_draw_size = size

	if outer_qc:
		printTimeMessage(qc.startTime,filename,"import","QC")
	return qc.numSMDs

def initSMD(filepath,smd_type,append,upAxis,from_qc,target_layer):
	global smd
	smd	= smd_info()
	smd.jobName = getFilename(filepath)
	smd.jobType = smd_type
	smd.append = append
	smd.startTime = time.time()
	smd.layer = target_layer
	if upAxis:
		smd.upAxis = upAxis
		smd.upAxisMat = getUpAxisMat(upAxis)
	smd.uiTime = 0
	if not from_qc:
		global smd_manager
		smd_manager = smd

	return smd

# Parses an SMD file
def readSMD( context, filepath, upAxis, newscene = False, smd_type = None, append = True, from_qc = False,target_layer = 0):
	if filepath.endswith("dmx"):
		return readDMX( context, filepath, upAxis, newscene, smd_type, append, from_qc)

	global smd
	initSMD(filepath,smd_type,append,upAxis,from_qc,target_layer)

	try:
		smd.file = file = open(filepath, 'r')
	except IOError as err: # TODO: work out why errors are swallowed if I don't do this!
		message = "Could not open SMD file \"{}\": {}".format(smd.jobName,err)
		log.error(message)
		return 0

	if newscene:
		bpy.context.screen.scene = bpy.data.scenes.new(smd.jobName) # BLENDER BUG: this currently doesn't update bpy.context.scene
	elif bpy.context.scene.name == "Scene":
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
	if smd.m and smd.upAxisMat and smd.upAxisMat != 1:
		smd.m.rotation_euler = smd.upAxisMat.to_euler()
		smd.m.select = True
		bpy.context.scene.update()
		bpy.ops.object.transform_apply(rotation=True)
	'''
	printTimeMessage(smd.startTime,smd.jobName,"import")

	return 1

def readDMX( context, filepath, upAxis, newscene = False, smd_type = None, append = True, from_qc = False,target_layer = 0):
	global smd
	initSMD(filepath,smd_type,append,upAxis,from_qc,target_layer)
	smd.isDMX = 16
	smd.smdNameToMatName = {}
	target_arm = findArmature()
	if target_arm:
		arm_hide = target_arm.hide
	benchReset()
	ob = bone = restData = smd.atch = smd.a = None

	print( "\nDMX IMPORTER: now working on",getFilename(filepath) )

	try:
		dmx = subprocess.Popen( ("dmx_model.exe", filepath) ,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	except OSError as err:
		log.error("Could not launch DMX-Model:",str(err))
		log.wantDMXDownloadPrompt = True
		return 0

	out, err = dmx.communicate()
	if (err):
		msg = "{} ({})".format(err.decode('ASCII'), getFilename(filepath))
		if dmx.returncode > 0:
			log.error(msg)
			return 0
		else:
			log.warning(msg)

	smd.file = io.BufferedReader(io.BytesIO(out))

	def get_bool():
		return smd.file.read(1) != b'\x00'
	def get_int():
		return int( unpack("i",smd.file.read(intsize))[0] )
	def get_float():
		return float( unpack("f",smd.file.read(floatsize))[0] )
	def get_vec(dim):
		return Vector( unpack("{}f".format(dim),smd.file.read(floatsize*dim)) )
	def get_Quaternion():
		raw = unpack("4f",smd.file.read(floatsize*4))
		return Quaternion( [ raw[3], raw[0], raw[1], raw[2] ] ) # XYZW > WXYZ
	def get_string(len):
		bin = smd.file.read(len)
		try:
			str = bin.decode('ASCII')
		except UnicodeDecodeError:
			#raise ValueError("{} at offset {}".format(bin,smd.file.tell() - len))
			return ""
		return str
	def get_name():
		return get_string( get_int() )

	def FindParent(debug = False):
		result = None
		while len(smd.parent_chain):
			candidate = smd.parent_chain[-1]
			if candidate['chdn'] > 0:
				if not result:
					result = candidate
					if debug: print("Got",result.name,"({})".format(candidate['chdn']))
					candidate['chdn'] -= 1
				else:
					break
			else:
				if debug: print("Popping",smd.parent_chain[-1].name)
				smd.parent_chain.pop()
		#if result:
		#	print(bone.name if bone else atch.name,"parent is",result.name)
		return result

	def dmxGenerateArmature():
		bpy.context.scene.objects.active = smd.a
		if restData:
			bpy.ops.object.mode_set(mode='OBJECT')
			sortBonesForImport()
			smd.frameData.append(restData)
			bpy.ops.object.mode_set(mode='EDIT')
			applyFrameDataRest(restData)
		TidyArmature()
	
	def readDMXTransform(target = None):
		pos = get_vec(3)
		rot = get_Quaternion()
		def GetMat():
			return Matrix.Translation(pos * rot.to_matrix().inverted())

		if target:
			target.matrix_local *= GetMat()		
		elif smd.atch:
			atch = smd.atch
			atch.location = pos * rz90 * ry90 # works?!?
			atch.rotation_euler = Vector(rot.to_euler()) # doesn't
		elif bone:
			restData[bone.name] = {'pos':pos, 'rot':rot.inverted().to_matrix()}
		elif ob:
			ob.matrix_local *= GetMat()
		else:
			pass #g_trans *= GetMat()
		bpy.context.scene.update()
		
	def readDMXMesh():
		if not smd.jobType: smd.jobType = REF
		lastob = smd.m
		ob = bone = smd.atch = None

		if bpy.context.active_object:
			bpy.ops.object.mode_set(mode='OBJECT')
		name = get_name()
		ob = smd.m = bpy.data.objects.new(name=name, object_data=bpy.data.meshes.new(name=name))
		context.scene.objects.link(ob)
		context.scene.objects.active = ob
		ob.matrix_world *= getUpAxisMat(upAxis)
		if smd_type == PHYS:
			ob.show_wire = True;
		bpy.context.scene.update()

		if len(smd.meshes):
			group = bpy.data.groups.get(smd.jobName)
			if not group: group = bpy.data.groups.new(smd.jobName)
			group.objects.link(ob)
			if len(smd.meshes) == 1:
				group.objects.link(lastob)

		setLayer()

		if from_qc: smd.a = qc.a
		ob.parent = smd.a # FIXME: can meshes be parented to each other?
		smd.meshes.append(ob)
		#ob.modifiers.new(name="Edge Split",type='EDGE_SPLIT').use_edge_angle = False
		if smd.a:
			amod = ob.modifiers.new(name="Armature",type='ARMATURE')
			amod.object = smd.a
			amod.use_bone_envelopes = False

		while( smd.file.readable() ):
			block_name = get_string(4)
		
			if block_name == "TRFM":
				readDMXTransform(ob)

			elif block_name == "VERT":
				num_verts = get_int()
				ob.data.vertices.add(num_verts)
				verts = []
				for vert in range(num_verts):
					verts.extend( get_vec(3) )

				ob.data.vertices.foreach_set("co",verts)
				#bench("VERT")

			elif block_name == "NORM":
				smd.file.seek(num_verts * floatsize * 3, io.SEEK_CUR)
				#for i in range(num_verts):
				#	norms.append( get_vec(3) )
				#now = time.time()
				#norm_time = last - now
				#last = now

			elif block_name == "FACE":
				mat_info = get_name().replace("\\","/").rsplit("/",1)
				if len(mat_info) == 2:
					mat_name = mat_info[1]
				else:
					mat_name = mat_info[0]

				mat, mat_ind = getMeshMaterial(mat_name)
		
				if len(mat_info) == 2:
					mat['smd_dir'] = mat_info[0] + "/"

				face_array_len = get_int()
				faces = []
				cur_face_len = 0
				for i in range( face_array_len ):
					val = get_int()
					if val == -1: # delimiter
						while cur_face_len < 4:
							faces.append(0)
							cur_face_len += 1
						cur_face_len = 0
						continue
					if cur_face_len == 4: #got a quad already, this is an n-gon
						faces.extend([ faces[-4], faces[-1] ])
						cur_face_len = 2
					faces.append(val)
					cur_face_len += 1

				cur_faces = len(ob.data.faces)
				new_faces = int(len(faces) / 4)

				import array
				from array import array

				all_inds = array('f', [0] * cur_faces)
				ob.data.faces.foreach_get("material_index",all_inds)
				all_inds += array('f', [mat_ind] * new_faces)

				all_faces = array('f', [0] * cur_faces * 4)
				ob.data.faces.foreach_get("vertices_raw",all_faces)
				all_faces += array('f',faces)

				ob.data.faces.add(new_faces)
				ob.data.faces.foreach_set("vertices_raw",all_faces)
				ob.data.faces.foreach_set("material_index",all_inds)

				#bench("FACE")

			elif block_name == "TEXC":
				ob.data.uv_textures.new()

				uvs = []
				for i in range(num_verts):
					uvs.append( get_vec(2) )

				for i in range (len(ob.data.uv_textures[0].data)):
					uv_face = ob.data.uv_textures[0].data[i]
					me_face = ob.data.faces[i]

					for j in range(len(me_face.vertices)):
						for k in range(2):
							uv_face.uv[j][k] = uvs[ me_face.vertices[j] ][k]

				#bench("TEXC")

			elif block_name == "WMAP":
				num_weighted_bones = get_int()
				full_weights = {}

				for vert in range(len(ob.data.vertices)):
					for link in range(num_weighted_bones):
						weight = get_float()
						bone_id = get_int()

						if weight:
							vg_name = smd.boneIDs[bone_id]
							vg = ob.vertex_groups.get(vg_name)
							if not vg:
								vg = ob.vertex_groups.new(vg_name)
								full_weights[vg_name] = []

							if weight == 1:
								full_weights[vg_name].append(vert)
							else:
								vg.add([vert],weight,'REPLACE')

				for vg_name, verts in iter(full_weights.items()):
					ob.vertex_groups[vg_name].add( verts, 1, 'REPLACE')

				#bench("WMAP")

			else:
				if smd.file.peek():
					smd.file.seek(-4,1)
				bpy.ops.object.mode_set(mode='OBJECT')
				bpy.context.scene.objects.active = ob
				if smd.jobType == PHYS:
					ob.draw_type = 'SOLID'
				else:
					bpy.ops.object.select_all(action="DESELECT")
					ob.select = True
					bpy.ops.object.shade_smooth()
				bpy.ops.object.mode_set(mode='EDIT')
				bpy.ops.mesh.select_all(action='SELECT')
				bpy.ops.mesh.remove_doubles()
				bpy.ops.object.mode_set(mode='OBJECT')
				return

	def readDMXAtch():
		name = get_name()
		atch = smd.atch = bpy.data.objects.new(name=name, object_data=None)
		context.scene.objects.link(atch)
		#smd.meshes.append(atch)
		smd.attachments.append(atch)
		atch.show_x_ray = True
		atch.empty_draw_type = 'ARROWS'

		atch.parent = smd.a
		atch.parent_type = 'BONE'
		parent = FindParent()
		if parent:
			atch.parent_bone = parent.name

		rigid = get_bool()
		world_align = get_bool()
		if world_align:
			atch['smd_world_align'] = True

	def readDMXAnim():
		smd.jobType = ANIM
		ops.object.mode_set(mode='OBJECT')
		'''if smd.a and smd_manager.a != smd.a:
			validateBones(smd_manager.a)
		else:
			removeObject(smd.a)
			smd.a = findArmature()
			print("ARM",smd.a.name)'''
		if target_arm:
			removeObject(smd.a)
		else:
			dmxGenerateArmature()
		smd.a = target_arm
		smd.a.hide = False
	
		fps = get_float()
		length = get_float()
		total_frames = int(round(length*fps,0)) + 1
		num_shifted_frames = 0

		smd.frameData = []
		for i in range(total_frames):
			smd.frameData.append({}) # "[{}] * total frames" creates pointers to the same dict!

		a = smd.a
		bones = a.data.bones
		scn = bpy.context.scene
		prevFrame = scn.frame_current
		scn.objects.active = smd.a

		smd.boneInfo = bones_info.fromArmature(smd_manager.a)

		while get_string(4) == "CHAN":
			data_type = get_string(1)
			boneid = get_int()
			try:
				bone_name = smd.boneIDs[boneid]
			except KeyError:
				bone_name = "DMXNULL"
				frame = -1 # read to dummy frame
			num_layers = get_int()
	
			for layer in range(num_layers):
				assert(get_string(1) == "L") # start of a new layer
		
				num_frames = get_int()
				for frame in range(num_frames):
					frame_float = get_float() * fps
					frame = frame_int = int(round(frame_float,0))
					if abs(frame_float - frame_int) > 0.01:
						num_shifted_frames += 1
			
					if not smd.frameData[frame].get(bone_name):
						smd.frameData[frame][bone_name] = {}

					if data_type == "p":
						smd.frameData[frame][bone_name]['pos'] = get_vec(3)
					elif data_type == "o":
						smd.frameData[frame][bone_name]['rot'] = get_Quaternion().to_matrix().inverted()
				
		if smd.file.peek():
			smd.file.seek(-4,1)

		for i in range(1,len(smd.frameData)):
			for bone in smd.a.data.bones:
				cur = smd.frameData[i].get(bone.name)
				pre = smd.frameData[i-1].get(bone.name)
				if not pre:
					pre = smd.frameData[i-1][bone.name] = { 'pos': 'empty', 'rot': 'empty' }
				if not cur:
					cur = pre
				if not cur.get('pos'):
					cur['pos'] = "empty"
				if not cur.get('rot'):
					cur['rot'] = "empty"
	
		# Remove children of missing bones...depending on how DMX works this may have to be changed to the
		# SMD system of "bridging the gap"
		for i in range(1,len(smd.frameData)):
			for bone in smd.a.data.bones:
				if smd.frameData[i].get(bone.name) and bone.parent and not smd.frameData[i].get(bone.parent.name):
					del smd.frameData[i][bone.name]
					continue

		readFrames() # actually applies them
	
	while( smd.file.peek() ):

		block_name = get_string(4)

		if block_name == "MODL":
			modl_ver = get_int()
			if modl_ver != 1:
				log.error("dmx-model version is {}, expected 1".format(modl_ver))
				return 0
			g_trans = Matrix.Rotation(0,4,"Z")
			mdl_name = get_string( get_int() )
			if context.scene.name.startswith("Scene"):
				context.scene.name = mdl_name

		elif block_name == "TRFM":
			readDMXTransform()

		elif block_name == "CHDN":
			parent = bone if bone else ob
			if parent:
				smd.parent_chain.append(parent)
				val = get_int()
				parent['chdn'] = val

		elif block_name == "SKEL":
			if context.active_object:
				bpy.ops.object.mode_set(mode='OBJECT')

			bone = None
			restData = {}
			max_bone_id = 0
			if not findArmature():
				smd.append = False
			ob = smd.a = createArmature(mdl_name)
			if not smd_manager.a: smd_manager.a = ob
			#smd.meshes.append(ob)
			bpy.context.scene.objects.active = smd.a
			bpy.ops.object.mode_set(mode='EDIT')

		elif block_name == "BONE":
			smd.atch = None
			name = get_name()
			id = get_int()
		
			bone = smd.a.data.edit_bones.new(name=name[:29]) # Blender RC2 hang avoidance
			if bone.name != name:
				bone['smd_name'] = name
			bone['smd_id'] = id
			smd.boneIDs[id] = name
			max_bone_id = max(max_bone_id,id)
			bone.tail = (0,1,0)

			bone.parent = FindParent()

		elif block_name == "ATCH":
			readDMXAtch()
		elif block_name == "MESH":
			bone = None
			if smd.a and smd_manager.a != smd.a:
				validateBones(qc.a)
			if not smd.a and append:
				smd.a = findArmature()
			readDMXMesh()	
		elif block_name == "ANIM":
			readDMXAnim()

		else:
			print("unrecognised MODL block at {}".format(smd.file.tell()))
			break

	if smd.a and smd.jobType == REF:
		dmxGenerateArmature()

	if smd.a and target_arm:
		smd.a.hide = arm_hide
	bench("DMX imported in")
	return 1

class SmdImporter(bpy.types.Operator):
	bl_idname = "import_scene.smd"
	bl_label = "Import SMD/VTA, DMX, QC"
	bl_description = "Imports uncompiled Source Engine model data"
	bl_options = {'UNDO'}

	# Properties used by the file browser
	filepath = StringProperty(name="File path", description="File filepath used for importing the SMD/VTA/DMX/QC file", maxlen=1024, default="")
	filename = StringProperty(name="Filename", description="Name of SMD/VTA/DMX/QC file", maxlen=1024, default="")
	filter_folder = BoolProperty(name="Filter folders", description="", default=True, options={'HIDDEN'})
	filter_glob = StringProperty(default="*.smd;*.vta;*.dmx;*.qc;*.qci", options={'HIDDEN'})

	# Custom properties
	append = BoolProperty(name="Extend any existing model", description="Whether imports will latch onto an existing armature or create their own.", default=True)
	doAnim = BoolProperty(name="Import animations (slow)", default=True)
	upAxis = EnumProperty(name="Up axis",items=axes,default='Z',description="Which axis represents 'up'. Ignored for QCs.")
	makeCamera = BoolProperty(name="Make camera at $origin",description="For use in viewmodel editing. If not set, an empty will be created instead.",default=False)

	def execute(self, context):
		if not ValidateBlenderVersion(self):
			return 'CANCELLED'

		global log
		log = logger()

		filepath_lc = self.properties.filepath.lower()
		if filepath_lc.endswith('.qc') or filepath_lc.endswith('.qci'):
			self.countSMDs = readQC(context, self.properties.filepath, False, self.properties.doAnim, self.properties.makeCamera, outer_qc=True)
			bpy.context.scene.objects.active = qc.a
		elif filepath_lc.endswith('.smd'):
			self.countSMDs = readSMD(context, self.properties.filepath, self.properties.upAxis, append=self.properties.append)
		elif filepath_lc.endswith ('.vta'):
			self.countSMDs = readSMD(context, self.properties.filepath, self.properties.upAxis, smd_type=FLEX)
		elif filepath_lc.endswith('.dmx'):
			self.countSMDs = readDMX(context, self.properties.filepath, self.properties.upAxis, append=self.properties.append)
		else:
			if len(filepath_lc) == 0:
				self.report('ERROR',"No file selected")
			else:
				self.report('ERROR',"Format of {} not recognised".format(getFilename(self.properties.filepath)))
			return 'CANCELLED'

		log.errorReport("imported","file",self,self.countSMDs)
		if self.countSMDs and smd.m:
			smd.m.select = True
			for area in context.screen.areas:
				if area.type == 'VIEW_3D':
					space = area.spaces.active
					# FIXME: small meshes offset from their origins won't extend things far enough
					xy = int(max(smd.m.dimensions[0],smd.m.dimensions[1]))
					space.grid_lines = max(space.grid_lines, xy)
					space.clip_end = max(space.clip_end, max(xy,int(smd.m.dimensions[2])))
		if bpy.context.space_data.type == 'VIEW_3D':		
			bpy.ops.view3d.view_all()
		return 'FINISHED'

	def invoke(self, context, event):
		if not ValidateBlenderVersion(self):
			return 'CANCELLED'
		self.properties.upAxis = context.scene.smd_up_axis
		bpy.context.window_manager.fileselect_add(self)
		return 'RUNNING_MODAL'

class Smd_OT_ImportTextures(bpy.types.Operator):
	bl_idname = "smd.import_textures"
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
		bone = smd.a.data.bones[boneName]
		if not bone.use_deform:
			print("- Skipping non-deforming bone \"{}\"".format(bone.name))
			continue

		parent = bone.parent
		while parent:
			if parent.use_deform:
				break
			parent = parent.parent

		line = str(smd.boneNameToID[boneName]) + " "

		bone_name = bone.get('smd_name')
		if bone_name:
			comment = " # smd_name override from \"{}\"".format(bone.name)
		else:
			bone_name = bone.name
			comment = ""	
		line += "\"" + bone_name + "\" "

		if parent:
			line += str(smd.boneNameToID[parent.name])
		else:
			line += "-1"

		smd.file.write(line + comment + "\n")

	smd.file.write("end\n")
	if not quiet: print("- Exported",len(smd.a.data.bones),"bones")
	if len(smd.a.data.bones) > 128:
		log.warning("Source only supports 128 bones!")

# NOTE: added this to keep writeFrames() a bit simpler, uses smd.sortedBones and smd.boneNameToID, replaces getBonesForSMD()
def writeRestPose():
	smd.file.write("time 0\n")
	for boneName in smd.sortedBones:
		bone = smd.a.data.bones[boneName]
		if not bone.use_deform: continue

		parent = bone.parent
		while parent:
			if parent.use_deform:
				break
			parent = parent.parent

		if parent:
			parentRotated = parent.matrix_local * ryz90
			childRotated = bone.matrix_local * ryz90
			mat = parentRotated.inverted() * childRotated

			if bpy.context.scene.smd_up_axis == 'Y':
				pos = rx90n * pos
				mat = (rx90n * mat).to_euler()
				pass
		else:
			mat = bone.matrix_local * ryz90
			if bpy.context.scene.smd_up_axis == 'Y':
				mat = rx90n * mat

		if smd.a.scale.x != Vector([0,0,0]):
			mat *= Matrix.Scale(smd.a.scale.x,4,Vector([1,0,0])) * Matrix.Scale(smd.a.scale.y,4,Vector([0,1,0])) * Matrix.Scale(smd.a.scale.z,4,Vector([0,0,1]))
		
		pos = mat.to_translation()
		rot = mat.to_euler('XYZ')

		pos_str = rot_str = ""
		for i in range(3):
			pos_str += " " + getSmdFloat(pos[i])
			rot_str += " " + getSmdFloat(rot[i])
		smd.file.write( str(smd.boneNameToID[boneName]) + pos_str + rot_str + "\n" )
	smd.file.write("end\n")

# skeleton block
def writeFrames():
	if smd.jobType == FLEX: # writeShapes() does its own skeleton block
		return

	smd.file.write("skeleton\n")

	if not smd.a:
		smd.file.write("time 0\n0 0 0 0 0 0 0\nend\n")
		return

	if smd.jobType != ANIM:
		writeRestPose()
		return

	scene = bpy.context.scene
	prev_frame = scene.frame_current
	#scene.frame_current = scene.frame_start

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
			if not pbn.bone.use_deform: continue

			parent = pbn.parent
			while parent:
				if parent.bone.use_deform:
					break
				parent = parent.parent

			if parent:
				parentRotated = parent.matrix * ryz90
				childRotated = pbn.matrix * ryz90
				rot = parentRotated.inverted() * childRotated
				pos = rot.to_translation()
			else:
				#pos = pbn.matrix.to_translation()
				#rot = (pbn.matrix * ryz90)
				rot = pbn.matrix * ryz90
				if bpy.context.scene.smd_up_axis == 'Y':
					rot = rx90n * rot
				pos = rot.to_translation()

			rot = rot.to_euler('XYZ')

			pos_str = rot_str = ""
			for i in range(3):
				pos_str += " " + getSmdFloat(pos[i])
				rot_str += " " + getSmdFloat(rot[i])
			smd.file.write( str(smd.boneNameToID[boneName]) + pos_str + rot_str + "\n" )

		scene.frame_set(scene.frame_current + 1)

	smd.file.write("end\n")
	scene.frame_set(prev_frame)
	return

# triangles block
def writePolys(internal=False):

	if not internal:
		smd.file.write("triangles\n")
		prev_frame = bpy.context.scene.frame_current
		have_cleared_pose = False
	
		if not bpy.context.scene.smd_use_image_names:
			materials = []
			for bi in smd.bakeInfo:
				if bi['baked'].type == 'MESH':
					for mat_slot in bi['baked'].material_slots:
						mat = mat_slot.material
						if mat and mat.get('smd_name') and mat not in materials:
							smd.file.write( "// Blender material \"{}\" has smd_name \"{}\"\n".format(mat.name,mat['smd_name']) )
							materials.append(mat)

		for bi in smd.bakeInfo:
			if bi['baked'].type == 'MESH':
				# write out each object in turn. Joining them would destroy unique armature modifier settings
				smd.m = bi['baked']
				if bi.get('arm_mod') and bi.get('arm_mod').object:
					smd.amod = bi['arm_mod']
				else:
					smd.amod = None
				if len(smd.m.data.faces) == 0:
					log.error("Object {} has no faces, cannot export".format(smd.jobName))
					continue

				if smd.amod and not have_cleared_pose:
					# This is needed due to a Blender bug. Setting the armature to Rest mode doesn't actually
					# change the pose bones' data!
					bpy.context.scene.objects.active = smd.amod.object
					bpy.ops.object.mode_set(mode='POSE')
					bpy.ops.pose.select_all()
					bpy.ops.pose.transforms_clear()
					have_cleared_pose = True
				bpy.ops.object.mode_set(mode='OBJECT')

				writePolys(internal=True)

		smd.file.write("end\n")
		bpy.context.scene.frame_set(prev_frame)
		return

	# internal mode:

	md = smd.m.data
	face_index = 0
	# bone parent?
	ob_weight_str = " 1 {} 1".format(smd.boneNameToID[smd.m['bp']]) if smd.m.get('bp') else None

	for uvtex in md.uv_textures:
		if uvtex.active_render:
			active_uv_tex = uvtex
			break

	bad_face_mats = 0
	for face in md.faces:
		if smd.m.material_slots:
			mat = smd.m.material_slots[face.material_index].material
			image = active_uv_tex.data[face_index].image
			if bpy.context.scene.smd_use_image_names and image:
				mat_name = getFilename(image.filepath) # not using data name as it can be truncated and custom props can't be used here
			else:
				if mat:
					mat_name = mat['smd_name'] if mat.get('smd_name') else mat.name
				else:
					mat_name = "Material"
					bad_face_mats += 1
			smd.file.write(mat_name + "\n")
		else:
			smd.file.write(smd.jobName + "\n")
		for i in range(3):

			# Vertex locations, normal directions
			loc = norms = ""
			v = md.vertices[face.vertices[i]]
			norm = v.normal if face.use_smooth else face.normal
			for j in range(3):
				loc += " " + getSmdFloat(v.co[j])
				norms += " " + getSmdFloat(norm[j])

			# UVs
			if not len(md.uv_textures):
				unBake()
				raise Exception("PROGRAMMER ERROR: Mesh was not unwrapped")

			uv = ""
			for j in range(2):
				uv += " " + getSmdFloat(active_uv_tex.data[face_index].uv[i][j])

			# Weightmaps
			weights = []
			if ob_weight_str:
				weight_string = ob_weight_str
			elif smd.amod:			
				am_vertex_group_weight = 0

				if smd.amod.use_vertex_groups:
					for j in range(len(v.groups)):
						group_index = v.groups[j].group
						if group_index < len(smd.m.vertex_groups):
							# Vertex group might not exist on object if it's re-using a datablock
							group_name = smd.m.vertex_groups[group_index].name
							group_weight = v.groups[j].weight
						else:
							continue

						if group_name == smd.amod.vertex_group:
							am_vertex_group_weight = group_weight

						bone = smd.amod.object.data.bones.get(group_name)
						if bone and bone.use_deform:
							weights.append([smd.boneNameToID[bone.name], group_weight])

				if smd.amod.use_bone_envelopes and not weights: # vertex groups completely override envelopes
					for pose_bone in smd.amod.object.pose.bones:
						if not pose_bone.bone.use_deform:
							continue
						weight = pose_bone.bone.envelope_weight * pose_bone.evaluate_envelope( v.co * smd.m.matrix_world )
						if weight:
							weights.append([smd.boneNameToID[pose_bone.name], weight])
						
			total_weight = 0
			if smd.amod:
				for link in weights:
					total_weight += link[1]

			if not smd.amod or total_weight == 0:
				if not ob_weight_str: weight_string = " 0"
				# In Source, unlike in Blender, verts HAVE to be attached to bones. This means that if you have only one bone,
				# all verts will be 100% attached to it. To transform only some verts you need a second bone that stays put.
			else:
				# Shares out unused weight between extant bones, like Blender does, otherwise Studiomdl puts it onto the root		
				for link in weights:
					link[1] *= 1/total_weight # This also handles weights totalling more than 100%

				weight_string = " " + str(len(weights))
				for link in weights: # one link on one vertex
					if smd.amod.vertex_group: # strength modifier
						link[1] *= am_vertex_group_weight
						if smd.amod.invert_vertex_group:
							link[1] = 1 - link[1]

					weight_string += " " + str(link[0]) + " " + getSmdFloat(link[1])

			# Finally, write it all to file
			smd.file.write("0" + loc + norms + uv + weight_string + "\n")

		face_index += 1

	if bad_face_mats:
		log.warning("{} faces on {} assigned to empty material slots".format(bad_face_mats,smd.jobName))
	print("- Exported",face_index,"polys")
	return

# vertexanimation block
def writeShapes(cur_shape = 0):
	num_verts = 0

	def _writeTime(time, shape = None):
		if shape:
			src_name = ""
			for bi in smd.bakeInfo:
				for shape_candidate in bi['shapes']:
					if shape_candidate['shape_name'] == shape['shape_name']:
						src_name += shape_candidate['src_name'] + ", "
			src_name = src_name[:-2]
		smd.file.write( "time {}{}\n".format(time, " # {} ({})".format(shape['shape_name'],src_name) if shape else "") )

	# VTAs are always separate files. The nodes block is handled by the normal function, but skeleton is done here to afford a nice little hack
	smd.file.write("skeleton\n")
	_writeTime(0) # shared basis
	num_shapes = 1
	shapes_written = []
	for bi in smd.bakeInfo:
		cur_shapes = len(bi['shapes']) - 1 # don't include basis shapes
		for i in range(cur_shapes):
			shape = bi['shapes'][i+1] # i+1 to skip basis
			if shape['shape_name'] in shapes_written: continue
			_writeTime(num_shapes + i, shape )
			shapes_written.append(shape['shape_name'])
		num_shapes += cur_shapes
	smd.file.write("end\n")

	smd.file.write("vertexanimation\n")
	def _writeVerts(shape, smd_vert_id = 0):
		start_time = time.time()
		num_verts = 0
		num_bad_verts = 0
		for face in smd.m.data.faces:
			for vert in face.vertices:
				shape_vert = shape.data.vertices[vert]
				mesh_vert = smd.m.data.vertices[vert]
				if cur_shape != 0:
					diff_vec = shape_vert.co - mesh_vert.co
					bad_vert = False
					for ordinate in diff_vec:
						if not bad_vert and ordinate > 8:
							num_bad_verts += 1
							bad_vert = True

				if cur_shape == 0 or (shape_vert.co != mesh_vert.co or shape_vert.normal != mesh_vert.normal):
					cos = norms = ""
					for i in range(3):
						cos += " " + getSmdFloat(shape_vert.co[i])
						norms += " " + getSmdFloat(shape_vert.normal[i])
					smd.file.write(str(smd_vert_id) + cos + norms + "\n")
					num_verts += 1
			
				smd_vert_id +=1
		if num_bad_verts:
			log.error("Shape \"{}\" has {} vertex movements that exceed eight units. Source does not support this!".format(shape['shape_name'],num_bad_verts))
		return num_verts

	cur_shape = 0
	vert_offset = 0
	total_verts = 0

	# Basis
	_writeTime(0)
	for bi in smd.bakeInfo:
		smd.m = bi['shapes'][0]
		total_verts += _writeVerts(bi['shapes'][0], total_verts) # write out every vert in the group
	cur_shape += 1

	# Everything else
	shapes_written = []
	for bi in smd.bakeInfo:
		smd.shapes = bi['shapes']
		smd.m = bi['shapes'][0]
		for shape in smd.shapes:
			if shape == bi['shapes'][0] or shape['shape_name'] in shapes_written:
				continue # don't write basis shapes, don't re-write shared shapes
			_writeTime(cur_shape,shape)
			cur_shape += 1
			vert_offset = 0
			for bi in smd.bakeInfo:
				for shape_candidate in bi['shapes']:
					if shape_candidate['shape_name'] == shape['shape_name']:
						last_verts = _writeVerts(shape_candidate,vert_offset)
						total_verts += last_verts
				for face in bi['baked'].data.faces:
					for vert in face.vertices:
						vert_offset += 1 # len(verts) doesn't give doubles
			shapes_written.append(shape['shape_name'])

	smd.file.write("end\n")
	print("- Exported {} vertex animations ({} verts)".format(cur_shape,total_verts))
	return

# Creates a mesh with object transformations and modifiers applied
def bakeObj(in_object):
	bi = {}
	bi['src'] = in_object

	for object in bpy.context.selected_objects:
		object.select = False

	def _ApplyVisualTransform(obj):
		top_parent = cur_parent = obj
		while(cur_parent):
			if not cur_parent.parent:
				top_parent = cur_parent
			cur_parent = cur_parent.parent

		bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
		obj.location -= top_parent.location # undo location of topmost parent
		bpy.ops.object.transform_apply(location=True)

	# Indirection to support groups
	def _ObjectCopy(obj):
		solidify_fill_rim = False

		selection_backup = bpy.context.selected_objects

		if obj.type in shape_types and obj.data.shape_keys:
			shape_keys = obj.data.shape_keys.key_blocks
		else:
			shape_keys = None

		if smd.jobType == FLEX:
			num_out = len(shape_keys)
			bi['shapes'] = []
		
			if num_out:
				# create an intermediate object without shapes
				obj_name = obj.name
				obj = obj.copy()
				obj.data = obj.data.copy()
				if not bi.get('baked'):
					bi['baked'] = obj
				bpy.context.scene.objects.link(obj)			
				bpy.context.scene.objects.active = obj
				bpy.ops.object.select_all(action="DESELECT")
				obj.select = True
			
				for shape in obj.data.shape_keys.key_blocks:
					bpy.ops.object.shape_key_remove('EXEC_SCREEN')
		else:
			num_out = 1

		for i in range(num_out):
			if shape_keys:
				cur_shape = shape_keys[i]
			if smd.jobType == FLEX and cur_shape.mute:
				print("- Skipping muted shape \"{}\"".format(cur_shape.name))
				continue

			baked = obj.copy()		
			if not bi.get('baked'):
				bi['baked'] = baked
			bpy.context.scene.objects.link(baked)
			bpy.context.scene.objects.active = baked
			bpy.ops.object.select_all(action="DESELECT")
			baked.select = True

			if shape_keys:
				baked.data = obj.data.copy()
			
				# transfer desired shape to copy
				if baked.type == 'MESH':				
					import array
					cos = array.array('f', [0] * len(baked.data.vertices) * 3 )
					cur_shape.data.foreach_get("co",cos)
					baked.data.vertices.foreach_set("co",cos)
				elif baked.type == 'SURFACE':
					# assuming shape keys only modify spline locations here...
					for i in range( len(baked.data.splines) ):
						for j in range( len(baked.data.splines[i].points) ):
							baked.data.splines[i].points[j].co[:3] = cur_shape.data[(i*2)+j].co # what is the 4th value?
				else:
					raise TypeError( "Shapes found on unsupported object type (\"{}\", {})".format(obj.name,obj.type) )
		
			if obj.type == 'ARMATURE':
				baked.data = baked.data.copy()
			elif obj.type in mesh_compatible:
				has_edge_split = False
				for mod in obj.modifiers:
					if mod.type == 'EDGE_SPLIT':
						has_edge_split = True
					if mod.type == 'SOLIDIFY' and not solidify_fill_rim:
						solidify_fill_rim = mod.use_rim

				if not has_edge_split and obj.type == 'MESH':
					edgesplit = baked.modifiers.new(name="SMD Edge Split",type='EDGE_SPLIT') # creates sharp edges
					edgesplit.use_edge_angle = False


				bpy.ops.object.convert(keep_original=True) # bake it!

				# did convert() make a new object?
				if bpy.context.active_object == baked: # no
					baked.data = baked.data.copy()
				else: # yes
					removeObject(baked)
					baked = bi['baked'] = bpy.context.active_object

				if smd.jobType == FLEX:
					baked.name = baked.data.name = baked['shape_name'] = cur_shape.name
					baked['src_name'] = obj_name
					bi['shapes'].append(baked)
			
				# Handle bone parents / armature modifiers, and warn of multiple associations
				baked['bp'] = ""
				envelope_described = False
				if obj.parent_bone and obj.parent_type == 'BONE':
					baked['bp'] = obj.parent_bone
					smd.a = obj.parent
				for con in obj.constraints:
					if con.mute:
						continue
					if con.type in ['CHILD_OF','COPY_TRANSFORMS'] and con.target.type == 'ARMATURE' and con.subtarget:
						if baked['bp']:
							if not envelope_described:
								print(" - Enveloped to bone \"{}\"".format(baked['bp']))
							log.warning("Bone constraint \"{}\" found on \"{}\", which already has an envelope. Ignoring.".format(con.name,obj.name))
						else:
							baked['bp'] = con.subtarget
							smd.a = con.target
				for mod in obj.modifiers:
					if mod.type == 'ARMATURE':
						if (smd.a and mod.object != smd.a) or baked['bp']:
							if not envelope_described:
								msg = " - Enveloped to {} \"{}\""
								if baked['bp']: print( msg.format("bone",baked['bp']) )
								else: print( msg.format("armature",smd.a.name) )
							log.warning("Armature modifier \"{}\" found on \"{}\", which already has an envelope. Ignoring.".format(mod.name,obj.name))
						else:
							smd.a = mod.object
							bi['arm_mod'] = mod
			
				# work on the vertices
				bpy.ops.object.mode_set(mode='EDIT')
				bpy.ops.mesh.reveal()
				bpy.ops.mesh.select_all(action='SELECT')
			
				if not smd.isDMX:
					bpy.ops.mesh.quads_convert_to_tris()
			
				# handle which sides of a curve should have polys
				if obj.type == 'CURVE':
					if obj.data.smd_faces == 'RIGHT':
						bpy.ops.mesh.duplicate()
						bpy.ops.mesh.flip_normals()
					if not obj.data.smd_faces == 'BOTH':
						bpy.ops.mesh.select_inverse()
						bpy.ops.mesh.delete()
					elif solidify_fill_rim:
						log.warning("Curve {} has the Solidify modifier with rim fill, but is still exporting polys on both sides.".format(obj.name))

				bpy.ops.object.mode_set(mode='OBJECT')
			
				# project a UV map
				if len(baked.data.uv_textures) == 0 and smd.jobType != FLEX:
					bpy.ops.object.select_all(action="DESELECT")
					baked.select = True
					bpy.ops.uv.smart_project()

					for object in selection_backup:
						object.select = True

				if bpy.context.scene.smd_up_axis == 'Y':
					baked.data.transform(rx90n)
		
			# Apply object transforms to the data
			if baked.type == 'MESH':
				_ApplyVisualTransform(baked)
			bpy.ops.object.transform_apply(scale=True,rotation=True)
	
		if smd.jobType == FLEX:
			removeObject(obj)
		return baked
		# END _ObjectCopy()

	if in_object.type == 'ARMATURE':
		_ObjectCopy(in_object)
		smd.a = bi['baked']
	elif in_object.type in mesh_compatible:
		# hide all metaballs that we don't want
		metaballs = []
		for object in bpy.context.scene.objects:
			if (smd.g or object != in_object) and object.type == 'META' and (not object.smd_export or not (smd.g and smd.g in object.users_group)):
				element_states = []
				for i in range(len(object.data.elements)):
					element_states.append(object.data.elements[i].hide)
					object.data.elements[i].hide = True
				metaballs.append( dict( ob=object, states = element_states) )
		bpy.context.scene.update() # actually found a use for this!!

		if not smd.g:
			_ObjectCopy(in_object)
		else:
			have_baked_metaballs = False
			validObs = getValidObs()
			for object in smd.g.objects:
				if object.smd_export and object in validObs and not (object.type == 'META' and have_baked_metaballs):
					if smd.jobType == FLEX and not object.data.shape_keys:
						continue
					bi['baked'] = _ObjectCopy(object)
					smd.bakeInfo.append(bi) # save to manager
					bi = dict(src=object)
					if not have_baked_metaballs: have_baked_metaballs = object.type == 'META'
				
		# restore metaball state
		for meta_state in metaballs:
			for i in range(len(meta_state['states'])):
				meta_state['ob'].data.elements[i].hide = meta_state['states'][i]

	if bi.get('baked') or (bi.get('shapes') and len(bi.get('shapes'))):
		smd.bakeInfo.append(bi) # save to manager

def unBake():
	bpy.ops.object.mode_set(mode='OBJECT')
	for bi in smd.bakeInfo:
		if bi.get('shapes'):
			for shape in bi['shapes']:
				type = removeObject(shape)
		else:
			type = removeObject(bi['baked'])

		if type == 'MESH':
			smd.m = bi['src']
		elif type == 'ARMATURE':
			smd.a = bi['src']

		del bi

# Creates an SMD file
def writeSMD( context, object, groupIndex, filepath, smd_type = None, quiet = False ):
	if filepath.endswith("dmx"):
		return writeDMX( context, object, groupIndex, filepath, smd_type, quiet )

	global smd
	smd	= smd_info()
	smd.jobType = smd_type
	if groupIndex != -1:
		smd.g = object.users_group[groupIndex]
	smd.startTime = time.time()
	smd.uiTime = 0

	def _workStartNotice():
		if not quiet:
			print( "\nSMD EXPORTER: now working on {}{}".format(smd.jobName," (shape keys)" if smd.jobType == FLEX else "") )

	if object.type in mesh_compatible:
		# We don't want to bake any meshes with poses applied
		# NOTE: this won't change the posebone values, but it will remove deformations
		armatures = []
		for scene_object in bpy.context.scene.objects:
			if scene_object.type == 'ARMATURE' and scene_object.data.pose_position == 'POSE':
				scene_object.data.pose_position = 'REST'
				armatures.append(scene_object)

		if not smd.jobType:
			smd.jobType = REF
		if smd.g:
			smd.jobName = smd.g.name
		else:
			smd.jobName = getObExportName(object)
		smd.m = object
		_workStartNotice()
		#smd.a = smd.m.find_armature() # Blender bug: only works on meshes
		bakeObj(smd.m)

		# re-enable poses
		for object in armatures:
			object.data.pose_position = 'POSE'
		bpy.context.scene.update()
	elif object.type == 'ARMATURE':
		if not smd.jobType:
			smd.jobType = ANIM
		smd.a = object
		smd.jobName = getObExportName(object.animation_data.action)
		_workStartNotice()
	else:
		raise TypeError("PROGRAMMER ERROR: writeSMD() has object not in",exportable_types)

	if smd.a:
		if smd.jobType != FLEX:
			bakeObj(smd.a) # MUST be baked after the mesh
		sortBonesForExport() # Get a list of bone names sorted in the order to be exported, and assign a unique SMD ID to every bone.

	smd.file = open(filepath, 'w')
	smd.file.write("version 1\n")

	# these write empty blocks if no armature is found. Required!
	writeBones(quiet = smd.jobType == FLEX)
	writeFrames()


	if smd.m:
		if smd.jobType in [REF,PHYS]:
			writePolys()
		elif smd.jobType == FLEX:
			writeShapes()

	unBake()
	smd.file.close()
	if not quiet: printTimeMessage(smd.startTime,smd.jobName,"export")

	return True

def getQCs(path = None):
	import glob
	ext = ".qc"
	out = []
	internal = False
	if not path:
		path = bpy.path.abspath(bpy.context.scene.smd_qc_path)
		internal = True
	for result in glob.glob(path):
		if result.endswith(ext):
			out.append(result)

	if not internal and not len(out) and not path.endswith(ext):
		out = getQCs(path + ext)
	return out

def compileQCs(path=None):
	scene = bpy.context.scene
	branch = scene.smd_studiomdl_branch
	print("\n")

	sdk_path = os.getenv('SOURCESDK')
	ncf_path = None
	if sdk_path:
		ncf_path = sdk_path + "\\..\\..\\common\\"
	else:
		# Python vanilla can't access the registry! (I will use the DMX bytecode to work around this)
		for path in [ os.getenv('PROGRAMFILES(X86)'), os.getenv('PROGRAMFILES') ]:
			path += "\\steam\\steamapps\\common"
			if os.path.exists(path):
				ncf_path = path

	studiomdl_path = None
	if branch in ['ep1','source2007','orangebox'] and sdk_path:
		studiomdl_path = sdk_path + "\\bin\\" + branch + "\\bin\\"
	elif branch in ['left 4 dead', 'left 4 dead 2', 'alien swarm', 'portal 2'] and ncf_path:
		studiomdl_path = ncf_path + branch + "\\bin\\"
	elif branch == 'CUSTOM':
		studiomdl_path = scene.smd_studiomdl_custom_path = bpy.path.abspath(scene.smd_studiomdl_custom_path)

	if not studiomdl_path:
		log.error("Could not locate Source SDK installation. Launch it to create the relevant files, or run a custom QC compile")
	else:
		if studiomdl_path and studiomdl_path[-1] in ['/','\\']:
			studiomdl_path += "studiomdl.exe"

		if path:
			qc_paths = [path]
		else:
			qc_paths = getQCs()
		num_good_compiles = 0
		if len( qc_paths ) == 0:
			log.error("Cannot compile, no QCs provided. The SMD Tools do not generate QCs.")
		elif not os.path.exists(studiomdl_path):
			log.error( "Could not execute studiomdl from \"{}\"".format(studiomdl_path) )
		else:
			for qc in qc_paths:		
				# save any version of the file currently open in Blender
				qc_mangled = qc.lower().replace('\\','/')
				for candidate_area in bpy.context.screen.areas:
					if candidate_area.type == 'TEXT_EDITOR' and candidate_area.spaces[0].text.filepath.lower().replace('\\','/') == qc_mangled:
						oldType = bpy.context.area.type
						bpy.context.area.type = 'TEXT_EDITOR'
						bpy.context.area.spaces[0].text = candidate_area.spaces[0].text
						bpy.ops.text.save()
						bpy.context.area.type = oldType
						break #what a farce!
					
				print( "Running studiomdl for \"{}\"...\n".format(getFilename(qc)) )
				studiomdl = subprocess.Popen([studiomdl_path, "-nop4", qc])
				studiomdl.communicate()

				if studiomdl.returncode == 0:
					num_good_compiles += 1
				else:
					log.error("Compile of {}.qc failed. Check the console for details".format(getFilename(qc)))
		return num_good_compiles

class SMD_MT_ExportChoice(bpy.types.Menu):
	bl_label = "SMD export mode"

	# returns an icon, a label, and the number of valid actions
	# supports single actions, NLA tracks, or nothing
	def getActionSingleTextIcon(self,context,ob = None):
		icon = "OUTLINER_DATA_ARMATURE"
		count = 0
		text = "No Actions or NLA"
		export_name = False
		if not ob:
			ob = context.active_object
			export_name = True # slight hack since having ob currently aligns with wanting a short name
		if ob:
			ad = ob.animation_data
			if ad:
				if ad.action:
					icon = "ACTION"
					count = 1
					if export_name:
						text = ob.smd_subdir + (getDirSep() if ob.smd_subdir else "") + ad.action.name + getFileExt()
					else:
						text = ad.action.name
				elif ad.nla_tracks:
					nla_actions = []
					for track in ad.nla_tracks:
						if not track.mute:
							for strip in track.strips:
								if not strip.mute and strip.action not in nla_actions:
									nla_actions.append(strip.action)
					icon = "NLA"
					count = len(nla_actions)
					text = "NLA actions (" + str(count) + ")"

		return text,icon,count

	# returns the appropriate text for the filtered list of all action
	def getActionFilterText(self,context):
		ob = context.active_object
		if ob.smd_action_filter:
			global cached_action_filter_list
			global cached_action_count
			if ob.smd_action_filter != cached_action_filter_list:
				cached_action_filter_list = ob.smd_action_filter
				cached_action_count = 0
				for action in bpy.data.actions:
					if action.name.lower().find(ob.smd_action_filter.lower()) != -1:
						cached_action_count += 1
			return "\"" + ob.smd_action_filter + "\" actions (" + str(cached_action_count) + ")"
		else:
			return "All actions (" + str(len(bpy.data.actions)) + ")", len(bpy.data.actions)

	def draw(self, context):
		# This function is also embedded in property panels on scenes and armatures
		l = self.layout
		ob = context.active_object

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

		if embed_scene and (len(context.selected_objects) == 0 or not ob):
			row = l.row()
			row.operator(SmdExporter.bl_idname, text="No selection") # filler to stop the scene button moving
			row.enabled = False

		# Normal processing
		# FIXME: in the properties panel, hidden objects appear in context.selected_objects...in the 3D view they do not
		elif (ob and len(context.selected_objects) == 1) or embed_arm:
			subdir = ob.get('smd_subdir')
			if subdir:
				label = subdir + getDirSep()
			else:
				label = ""


			if ob.type in mesh_compatible:
				want_single_export = True
				# Groups
				if ob.users_group:
					for i in range(len(ob.users_group)):
						group = ob.users_group[i]
						if group.smd_export:
							want_single_export = False
							label = group.name + getFileExt()
							if bpy.context.scene.smd_format == 'SMD':
								if hasShapes(ob,i):
									label += "/.vta"

							op = l.operator(SmdExporter.bl_idname, text=label, icon="GROUP") # group
							op.exportMode = 'SINGLE' # will be merged and exported as one
							op.groupIndex = i
				# Single
				if want_single_export:
					label = getObExportName(ob) + getFileExt()
					if bpy.context.scene.smd_format == 'SMD' and hasShapes(ob):
						label += "/.vta"
					l.operator(SmdExporter.bl_idname, text=label, icon=MakeObjectIcon(ob,prefix="OUTLINER_OB_")).exportMode = 'SINGLE'


			elif ob.type == 'ARMATURE':
				if embed_arm or ob.data.smd_action_selection == 'CURRENT':
					text,icon,count = SMD_MT_ExportChoice.getActionSingleTextIcon(self,context)
					if count:
						l.operator(SmdExporter.bl_idname, text=text, icon=icon).exportMode = 'SINGLE_ANIM'
					else:
						l.label(text=text, icon=icon)
				if embed_arm or (len(bpy.data.actions) and ob.data.smd_action_selection == 'FILTERED'):
					# filtered action list
					l.operator(SmdExporter.bl_idname, text=SMD_MT_ExportChoice.getActionFilterText(self,context)[0], icon='ACTION').exportMode= 'SINGLE'

			else: # invalid object
				label = "Cannot export " + ob.name
				try:
					l.label(text=label,icon=MakeObjectIcon(ob,prefix='OUTLINER_OB_'))
				except: # bad icon
					l.label(text=label,icon='ERROR')

		# Multiple objects
		elif len(context.selected_objects) > 1 and not embed_arm:
			l.operator(SmdExporter.bl_idname, text="Selected objects\\groups", icon='GROUP').exportMode = 'MULTI' # multiple obects


		if not embed_arm:
			l.operator(SmdExporter.bl_idname, text="Scene as configured", icon='SCENE_DATA').exportMode = 'SCENE'
		#l.operator(SmdExporter.bl_idname, text="Whole .blend", icon='FILE_BLEND').exportMode = 'FILE' # can't do this until scene changes become possible

class SMD_OT_Compile(bpy.types.Operator):
	bl_idname = "smd.compile_qc"
	bl_label = "Compile QC"
	bl_description = "Compile QCs with the Source SDK"

	filepath = StringProperty(name="File path", description="QC to compile", maxlen=1024, default="", subtype='FILE_PATH')

	def execute(self,context):
		global log
		log = logger()
		num = compileQCs(self.properties.filepath)
		if not self.properties.filepath:
			self.properties.filepath = "QC"
		log.errorReport("compiled","{} QC".format(getEngineBranchName()),self, num)
		return 'FINISHED'

def getValidObs():
	validObs = []
	s = bpy.context.scene
	for o in s.objects:
		if o.type in exportable_types:
			if s.smd_layer_filter:
				for i in range( len(o.layers) ):
					if o.layers[i] and s.layers[i]:
						validObs.append(o)
						break
			else:
				validObs.append(o)
	return validObs

qc_path = qc_paths = qc_path_last_update = 0
class SMD_PT_Scene(bpy.types.Panel):
	bl_label = "SMD Export"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	bl_default_closed = True

	def draw(self, context):
		l = self.layout
		scene = context.scene
		num_to_export = 0

		self.embed_scene = l.row()
		SMD_MT_ExportChoice.draw(self,context)

		l.prop(scene,"smd_path",text="Output Folder")
		l.prop(scene,"smd_studiomdl_branch",text="Target Engine")
		if scene.smd_studiomdl_branch == 'CUSTOM':
			l.prop(scene,"smd_studiomdl_custom_path",text="Studiomdl path")
		row = l.row().split(0.33)
		row.label(text="Target Up Axis:")
		row.row().prop(scene,"smd_up_axis", expand=True)

		validObs = getValidObs()
		l.row()
		scene_config_row = l.row()

		if len(validObs):
			validObs.sort(key=lambda ob: ob.name.lower())
			box = l.box()
			columns = box.column()
			header = columns.row()
			header.label(text="Object / Group:")
			header.label(text="Subfolder:")

			had_groups = False
			groups_sorted = []
			for group in bpy.data.groups:
				groups_sorted.append(group)
			groups_sorted.sort(key=lambda g: g.name.lower())
			want_sep = False
			for group in groups_sorted:
				if want_sep: columns.separator()
				want_sep = False
				for object in group.objects:
					if object in validObs:
						had_groups = True
						row = columns.row()
						row.prop(group,"smd_export",icon="GROUP",emboss=True,text=group.name)
						row.prop(group,"smd_subdir",text="")

						if group.smd_export:
							num_to_export += 1
							rows = columns.column_flow(2)
							for object in group.objects:
								if object in validObs and object.type != 'ARMATURE':
									rows.prop(object,"smd_export",icon=MakeObjectIcon(object,suffix="_DATA"),emboss=False,text=object.name)
							want_sep = True
						break # we've found an object in the scene and drawn the list

			if had_groups:
				columns.separator()
			
			had_obs = False
			for object in validObs: # meshes
				in_active_group = False
				if object.type in mesh_compatible:
					for group in object.users_group:
						if group.smd_export:
							in_active_group = True
				if not in_active_group:
					if object.type == 'ARMATURE':
						continue

					row = columns.row()
					row.prop(object,"smd_export",icon=MakeObjectIcon(object,prefix="OUTLINER_OB_"),emboss=True,text=getObExportName(object))
					row.prop(object,"smd_subdir",text="")
					had_obs = True
					if object.smd_export: num_to_export += 1
				
			if had_obs:
				columns.separator()

			had_armatures = False
			want_sep = False
			for object in validObs:
				if object.type == 'ARMATURE' and object.animation_data:
					if want_sep: columns.separator()
					want_sep = False
					had_armatures = True
					row = columns.row()
					row.prop(object,"smd_export",icon=MakeObjectIcon(object,prefix="OUTLINER_OB_"),emboss=True,text=object.name)
					row.prop(object,"smd_subdir",text="")
					if object.smd_export:
						row = columns.row()
						if object.data.smd_action_selection == 'CURRENT':
							text,icon,count = SMD_MT_ExportChoice.getActionSingleTextIcon(self,context,object)
							if object.smd_export: num_to_export += 1
						elif object.data.smd_action_selection == 'FILTERED':
							text, num = SMD_MT_ExportChoice.getActionFilterText(self,context)
							if object.smd_export: num_to_export += num
							icon = "ACTION"
						row.prop(object,"smd_export",text=text,icon=icon,emboss=False)
						row.prop(object.data,"smd_action_selection",text="")
						want_sep = True

		scene_config_row.label(text=" Scene Exports ({} file{})".format(num_to_export,"" if num_to_export == 1 else "s"),icon='SCENE_DATA')
		
		r = l.row()
		r.prop(scene,"smd_use_image_names",text="Use image filenames")
		r.prop(scene,"smd_layer_filter",text="Visible layer(s) only")
		l.row()
		
		# QCs
		global qc_path
		global qc_paths
		global qc_path_last_update
		qc_label_row = l.row()
		r = l.row()
		r.prop(scene,"smd_qc_path",text="")
		if scene.smd_qc_path != qc_path or not qc_paths or time.time() > qc_path_last_update + 2:
			qc_paths = getQCs()
			qc_path = scene.smd_qc_path	
		qc_path_last_update = time.time()
		have_qcs = len(qc_paths) > 0
	
		if have_qcs or isWild(qc_path):
			c = l.column_flow(2)
			for path in qc_paths:
				c.operator(SMD_OT_Compile.bl_idname,text=getFilename(path)).filepath = path

		qc_label_row.label(text=" QC Compiles ({} file{})".format(len(qc_paths),"" if len(qc_paths) == 1 else "s"),icon='FILE_SCRIPT')
		compile_row = l.row()
		compile_row.prop(scene,"smd_qc_compile")
		compile_row.operator(SMD_OT_Compile.bl_idname,text="Compile all now",icon='SCRIPT')
		if not have_qcs:
			if scene.smd_qc_path:
				qc_label_row.label(text=" Invalid path",icon='ERROR')
			compile_row.enabled = False
		l.separator()
		l.operator(SmdClean.bl_idname,text="Clean all SMD data from scene and objects",icon='RADIO')
		l.operator(SmdToolsUpdate.bl_idname,icon='URL')

class SMD_PT_Data(bpy.types.Panel):
	bl_label = "SMD Export"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "data"

	@classmethod
	def poll(self,context):
		return context.active_object.type in ['ARMATURE','CURVE'] # the panel isn't displayed unless there is an active object

	def draw(self, context):
		if context.active_object.type == 'ARMATURE':
			self.draw_Armature(context)
		elif context.active_object.type == 'CURVE':
			self.draw_Curve(context)

	def draw_Curve(self, context):
		c = context.active_object

		self.layout.label(text="Generate polygons on:")

		row = self.layout.row()
		row.prop(c.data,"smd_faces",expand=True)

	def draw_Armature(self, context):
		l = self.layout
		arm = context.active_object
		anim_data = arm.animation_data

		l.prop(arm,"smd_subdir",text="Export Subfolder")

		l.prop(arm.data,"smd_action_selection")
		l.prop(arm,"smd_action_filter",text="Action Filter")

		l.prop(arm.data,"smd_implicit_zero_bone")

		self.embed_arm = l.row()
		SMD_MT_ExportChoice.draw(self,context)

		if anim_data:
			l.template_ID(anim_data, "action", new="action.new")

		l.separator()
		l.operator(SmdClean.bl_idname,text="Clean SMD names/IDs from bones",icon='BONE_DATA').mode = 'ARMATURE'

class SmdExporter(bpy.types.Operator):
	'''Export Studiomdl Data files and compile them with QC scripts'''
	bl_idname = "export_scene.smd"
	bl_label = "Export SMD/VTA"
	bl_options = { 'UNDO', 'REGISTER' }

	# This should really be a directory select, but there is no way to explain to the user that a dir is needed except through the default filename!
	directory = StringProperty(name="Export root", description="The root folder into which SMDs from this scene are written", subtype='FILE_PATH')	
	filename = StringProperty(default="", options={'HIDDEN'})

	exportMode_enum = (
		('NONE','No mode','The user will be prompted to choose a mode'),
		('SINGLE','Active','Only the active object'),
		('SINGLE_ANIM','Current action',"Exports the active Armature's current Action"),
		('MULTI','Selection','All selected objects'),
		('SCENE','Scene','Export the objects and animations selected in Scene Properties'),
		#('FILE','Whole .blend file','Export absolutely everything, from all scenes'),
		)
	exportMode = EnumProperty(items=exportMode_enum,options={'HIDDEN'})
	groupIndex = IntProperty(default=-1,options={'HIDDEN'})

	def execute(self, context):
		if not ValidateBlenderVersion(self):
			return 'CANCELLED'

		props = self.properties

		if props.exportMode == 'NONE':
			self.report('ERROR',"Programmer error: bpy.ops.{} called without exportMode".format(SmdExporter.bl_idname))
			return 'CANCELLED'
	
		prev_arm_mode = None
		if props.exportMode == 'SINGLE_ANIM': # really hacky, hopefully this will stay a one-off!
			ob = context.active_object
			if ob.type == 'ARMATURE':
				prev_arm_mode = ob.data.smd_action_selection
				ob.data.smd_action_selection = 'CURRENT'
			props.exportMode = 'SINGLE'

		# Handle export root path
		if len(props.directory):
			# We've got a file path from the file selector (or direct invocation)
			context.scene['smd_path'] = props.directory
		else:
			# Get a path from the scene object
			export_root = context.scene.get("smd_path")

			# No root defined, pop up a file select
			if not export_root:
				props.filename = "*** [Please choose a root folder for exports from this scene] ***"
				context.window_manager.fileselect_add(self)
				return 'RUNNING_MODAL'
			

			if export_root.startswith("//") and not bpy.context.blend_data.filepath:
				self.report('ERROR',"Relative scene output path, but .blend not saved")
				return 'CANCELLED'

			if export_root[-1] not in ['\\','/']: # append trailing slash
				export_root += getDirSep()			

			props.directory = export_root

		global log
		log = logger()

		print("\nSMD EXPORTER RUNNING")
		prev_active_ob = context.active_object
		if prev_active_ob and prev_active_ob.type == 'ARMATURE':
			prev_bone_selection = bpy.context.selected_pose_bones
			prev_active_bone = context.active_bone
		prev_selection = context.selected_objects
		prev_visible = [] # visible_objects isn't useful due to layers
		for ob in context.scene.objects:
			if not ob.hide: prev_visible.append(ob)
		prev_frame = context.scene.frame_current

		# store Blender mode user was in before export
		prev_mode = bpy.context.mode
		if prev_mode.startswith("EDIT"):
			prev_mode = "EDIT" # remove any suffixes
		if prev_active_ob:
			prev_active_ob.hide = False
			ops.object.mode_set(mode='OBJECT')

		pose_backups = {}
		for object in bpy.context.scene.objects:
			object.hide = False # lots of operators only work on visible objects
			if object.type == 'ARMATURE' and object.animation_data:
				context.scene.objects.active = object
				ops.object.mode_set(mode='POSE')
				context.scene.objects.active = object
				# Back up any unkeyed pose. I'd use the pose library, but it can't be deleted if empty!
				pb_act = bpy.data.actions.new(name=object.name+" pose backup")
				pb_act.user_clear()
				pose_backups[object.name] = [ object.animation_data.action, pb_act ]
				bpy.ops.pose.copy()
				object.animation_data.action = pose_backups[object.name][1]
				bpy.ops.pose.paste()
				bpy.ops.pose.select_all(action='SELECT')
				bpy.ops.anim.keyframe_insert(type='LocRotScale')
				object.animation_data.action = pose_backups[object.name][0]
				ops.object.mode_set(mode='OBJECT')
		context.scene.objects.active = prev_active_ob

		# check export mode and perform appropriate jobs
		self.countSMDs = 0
		if props.exportMode == 'SINGLE':
			ob = context.active_object
			group_name = None
			if props.groupIndex != -1:
				# handle the selected object being in a group, but disabled
				group_name = ob.users_group[props.groupIndex].name
				for g_ob in ob.users_group[props.groupIndex].objects:
					if g_ob.smd_export:
						ob = g_ob
						break
					else:
						ob = None

			if ob:
				self.exportObject(context,context.active_object,groupIndex=props.groupIndex)
			else:
				log.error("The group \"" + group_name + "\" has no active objects")
				return 'CANCELLED'


		elif props.exportMode == 'MULTI':
			exported_groups = []
			for object in context.selected_objects:
				if object.type in mesh_compatible:
					if object.users_group:
						for i in range(len(object.users_group)):
							if object.smd_export and object.users_group[i] not in exported_groups:
								self.exportObject(context,object,groupIndex=i)
								exported_groups.append(object.users_group[i])
					else:
						self.exportObject(context,object)
				elif object.type == 'ARMATURE':
					self.exportObject(context,object)

		elif props.exportMode == 'SCENE':
			for group in bpy.data.groups:
				if group.smd_export:
					for object in group.objects:
						if object.smd_export and object.type in exportable_types and object.type != 'ARMATURE' and bpy.context.scene in object.users_scene:
							g_index = -1
							for i in range(len(object.users_group)):
								if object.users_group[i] == group:
									g_index = i
									break
							self.exportObject(context,object,groupIndex=g_index)
							break
			for object in bpy.context.scene.objects:
				if object.smd_export:
					should_export = True
					if object.users_group and object.type != 'ARMATURE':
						for group in object.users_group:
							if group.smd_export:
								should_export = False
								break
					if should_export:
						self.exportObject(context,object)

		elif props.exportMode == 'FILE': # can't be done until Blender scripts become able to change the scene
			for scene in bpy.data.scenes:
				scene_root = scene.get("smd_path")
				if not scene_root:
					log.warning("Skipped unconfigured scene",scene.name)
					continue
				else:
					props.directory = scene_root

				for object in bpy.data.objects:
					if object.type in ['MESH', 'ARMATURE']:
						self.exportObject(context,object)

		# Export jobs complete! Clean up...
		context.scene.objects.active = prev_active_ob
		if prev_active_ob and context.scene.objects.active:
			ops.object.mode_set(mode=prev_mode)
			if prev_active_ob.type == 'ARMATURE' and prev_active_bone:
				prev_active_ob.data.bones.active = prev_active_ob.data.bones[ prev_active_bone.name ]
				for i in range( len(prev_active_ob.pose.bones) ):
					prev_active_ob.data.bones[i].select = True if prev_bone_selection and prev_active_ob.pose.bones[i] in prev_bone_selection else False

		for object in context.scene.objects:
			object.select = object in prev_selection
			object.hide = object not in prev_visible
			if object.type == 'ARMATURE' and object.animation_data:
				object.animation_data.action = pose_backups[object.name][1] # backed up pose

		context.scene.frame_set(prev_frame) # apply backup pose
		for object in context.scene.objects:
			if object.type == 'ARMATURE' and object.animation_data:
				object.animation_data.action = pose_backups[object.name][0] # switch to original action, don't apply
				pose_backups[object.name][1].use_fake_user = False
				pose_backups[object.name][1].user_clear()
				bpy.data.actions.remove(pose_backups[object.name][1]) # remove backup
			
		if prev_arm_mode:
			prev_active_ob.data.smd_action_selection = prev_arm_mode

		jobMessage = "exported"

		if self.countSMDs == 0:
			log.error("Found no valid objects for export")
		elif context.scene.smd_qc_compile and context.scene.smd_qc_path:
			# ...and compile the QC
			num_good_compiles = compileQCs()
			jobMessage += " and {} {} QC{} compiled".format(num_good_compiles, getEngineBranchName(), "" if num_good_compiles == 1 else "s")
			print("\n")

		log.errorReport(jobMessage,"file",self,self.countSMDs)
		return 'FINISHED'

	# indirection to support batch exporting
	def exportObject(self,context,object,flex=False,groupIndex=-1):
		props = self.properties
	
		validObs = getValidObs()
		if groupIndex == -1:
			if not object in validObs:
				return
		else:
			if len(set(validObs).intersection( set(object.users_group[groupIndex].objects) )) == 0:
				return
	
		# handle subfolder
		if len(object.smd_subdir) == 0 and object.type == 'ARMATURE':
			object.smd_subdir = "anims"
		object.smd_subdir = object.smd_subdir.lstrip("/") # don't want //s here!

		if object.type == 'ARMATURE' and not object.animation_data:
			return; # otherwise we create a folder but put nothing in it

		# assemble filename
		path = bpy.path.abspath(getFileDir(props.directory) + object.smd_subdir)
		if path and path[-1] not in ['/','\\']:
			path += getDirSep()
		if not os.path.exists(path):
			os.makedirs(path)

		if object.type in mesh_compatible:
			if groupIndex == -1:
				path += getObExportName(object)
			else:
				path += object.users_group[groupIndex].name

			if writeSMD(context, object, groupIndex, path + getFileExt()):
				self.countSMDs += 1
			if bpy.context.scene.smd_format == 'SMD' and hasShapes(object,groupIndex): # DMX will export mesh and shapes to the same file
				if writeSMD(context, object, groupIndex, path + getFileExt(flex=True), FLEX):
					self.countSMDs += 1
		elif object.type == 'ARMATURE':
			ad = object.animation_data
			prev_action = None
			if ad.action: prev_action = ad.action

			if object.data.smd_action_selection == 'FILTERED':
				for action in bpy.data.actions:
					if action.users and (not object.smd_action_filter or action.name.lower().find(object.smd_action_filter.lower()) != -1):
						ad.action = action
						if writeSMD(context,object, -1, path + action.name + getFileExt(), ANIM):
							self.countSMDs += 1
			elif object.animation_data:
				if ad.action:
					if writeSMD(context,object,-1,path + ad.action.name + getFileExt(), ANIM):
						self.countSMDs += 1
				elif len(ad.nla_tracks):
					nla_actions = []
					for track in ad.nla_tracks:
						if not track.mute:
							for strip in track.strips:
								if not strip.mute and strip.action not in nla_actions:
									nla_actions.append(strip.action)
									ad.action = strip.action
									if writeSMD(context,object,-1,path + ad.action.name + getFileExt(), ANIM):
										self.countSMDs += 1
			ad.action = prev_action

	def invoke(self, context, event):
		if not ValidateBlenderVersion(self):
			return 'CANCELLED'
	
		if self.properties.exportMode == 'NONE':
			bpy.ops.wm.call_menu(name="SMD_MT_ExportChoice")
			return 'PASS_THROUGH'
		else: # a UI element has chosen a mode for us
			return self.execute(context)

class SmdClean(bpy.types.Operator):
	bl_idname = "smd.clean"
	bl_label = "Clean SMD data"
	bl_description = "Deletes SMD-related properties"
	bl_options = {'REGISTER', 'UNDO'}

	mode = EnumProperty(items=( ('OBJECT','Object','Active object'), ('ARMATURE','Armature','Armature bones and actions'), ('SCENE','Scene','Scene and all contents') ),default='SCENE')

	def execute(self,context):
		self.numPropsRemoved = 0
		def removeProps(object,bones=False):
			if not bones:
				for prop in object.items():
					if prop[0].startswith("smd_"):
						del object[prop[0]]
						self.numPropsRemoved += 1

			if bones and object.type == 'ARMATURE':
				# For some reason deleting custom properties from bones doesn't work well in Edit Mode
				bpy.context.scene.objects.active = object
				object_mode = object.mode
				bpy.ops.object.mode_set(mode='OBJECT')
				for bone in object.data.bones:
					removeProps(bone)
				bpy.ops.object.mode_set(mode=object_mode)
			
			if type(object) == bpy.types.Object and object.type == 'ARMATURE': # clean from actions too
				if object.data.smd_action_selection == 'CURRENT':
					if object.animation_data.action:
						removeProps(object.animation_data.action)
				else:
					for action in bpy.data.actions:
						if action.name.lower().contains( object.data.smd_action_filter.lower() ):
							removeProps(action)

		active_obj = bpy.context.active_object
		active_mode = active_obj.mode if active_obj else None

		if self.properties.mode == 'SCENE':
			for object in context.scene.objects:
				removeProps(object)
					
			for group in bpy.data.groups:
				for g_ob in group.objects:
					if context.scene in g_ob.users_scene:
						removeProps(group)
			removeProps(context.scene)

		elif self.properties.mode == 'OBJECT':
			removeProps(active_obj)

		elif self.properties.mode == 'ARMATURE':
			assert(active_obj.type == 'ARMATURE')
			removeProps(active_obj,bones=True)			

		bpy.context.scene.objects.active = active_obj
		if active_obj:
			bpy.ops.object.mode_set(mode=active_mode)

		self.report('INFO',"Deleted {} SMD properties".format(self.numPropsRemoved))
		return 'FINISHED'

########################
#        Update        #
########################
# DISABLE THIS if you make third-party changes to the script!

class SMD_MT_Updated(bpy.types.Menu):
	bl_label = "SMD Tools update"
	def draw(self,context):
		self.layout.operator("wm.url_open",text="View changes?",icon='TEXT').url = "http://code.google.com/p/blender-smd/wiki/Changelog"

import xml.parsers.expat, zipfile
class SmdToolsUpdate(bpy.types.Operator):
	bl_idname = "script.update_smd"
	bl_label = "Check for SMD Tools updates"
	bl_description = "Connects to http://code.google.com/p/blender-smd/"

	def execute(self,context):
		print("SMD Tools update...")
		self.cur_entry = \
		self.result = \
		self.url_err = \
		self.io_err = None
		self.rss_entries = []

		def startElem(name,attrs):
			if name == "entry":
				self.cur_entry = {'version': 0, 'bpy': 0 }
				self.rss_entries.append(self.cur_entry)
			if not self.cur_entry: return

			if name == "content":
				magic_words = [ "Blender SMD Tools ", " bpy-" ]

				def readContent(data):
					for i in range( len(magic_words) ):
						if data[: len(magic_words[i]) ] == magic_words[i]:
							self.cur_entry['version' if i == 0 else 'bpy'] = data[ len(magic_words[i]) :].split()[0].split(".")

					if self.cur_entry['version'] and self.cur_entry['bpy']:
						for val in self.cur_entry.values():
							while len(val) < 3:
								val.append('0')

				parser.CharacterDataHandler = readContent

		def endElem(name):
			if name == "entry": self.cur_entry = None
			if name == "feed":
				if len(self.rss_entries):
					self.update()
				else:
					self.result = 'FAIL_PARSE'
			elif name == "content":
				if not (self.cur_entry['version'] and self.cur_entry['bpy']):
					self.rss_entries.pop()
				parser.CharacterDataHandler = None # don't read chars until the next content elem

		try:
			# parse RSS
			feed = urllib.request.urlopen("http://code.google.com/feeds/p/blender-smd/downloads/basic")
			parser = xml.parsers.expat.ParserCreate()
			parser.StartElementHandler = startElem
			parser.EndElementHandler = endElem

			parser.Parse(feed.read())
		except urllib.error.URLError as err:
			self.url_err = str(err)
		except xml.parsers.expat.ExpatError as err:
			print(err)
			self.result = 'FAIL_PARSE'
		except zipfile.BadZipfile:
			self.result == 'FAIL_UNZIP'
		except IOError as err:
			self.io_err = str(err)
		
		if self.url_err:
			self.report('ERROR',"Could not complete download: " + self.url_err)
			print(self.url_err)
			return 'CANCELLED'
		elif self.result == 'FAIL_PARSE':
			self.report('ERROR',"Version information was downloaded, but could not be parsed.")
			print(feed.read())
			return 'CANCELLED'
		elif self.result == 'FAIL_UNZIP':
			self.report('ERROR',"Update was downloaded, but was corrupt")
			return 'CANCELLED'
		elif self.io_err:
			self.report('ERROR',"Could not install update: " + self.io_err)
			return 'CANCELLED'

		elif self.result == 'INCOMPATIBLE':
			self.report('ERROR',"The latest SMD Tools require Blender {}. Please upgrade.".format( PrintVer(self.cur_entry['bpy']) ))
			return 'FINISHED'
		elif self.result == 'LATEST':
			self.report('INFO',"The latest SMD Tools ({}) are already installed.".format( PrintVer(bl_info['version']) ))
			return 'FINISHED'

		elif self.result == 'SUCCESS':
			bpy.ops.script.reload()
			self.report('INFO',"Upgraded to SMD Tools {}!".format(self.remote_ver_str))
			bpy.ops.wm.call_menu(name="SMD_MT_Updated")
			return 'FINISHED'

		else:
			print("Unhandled error!")
			print(self.result)
			print(self.cur_entry)
			assert(0) # unhandled error!
			return 'CANCELLED'

	def update(self):
		cur_ver = bl_info['version']
		self.cur_entry = None

		for entry in self.rss_entries:
			remote_ver = entry['version']
			remote_bpy = entry['bpy']
			stable_api = (2,56,5)
			for i in range(min( len(remote_bpy), len(bpy.app.version) )):
				if int(remote_bpy[i]) > stable_api[i] and int(remote_bpy[i]) > bpy.app.version[i]:
					remote_ver = None

			if not remote_ver:
				if not self.cur_entry:
					self.result = 'INCOMPATIBLE'
			else:
				for i in range(min( len(remote_ver), len(cur_ver) )):
					try:
						diff = int(remote_ver[i]) - int(cur_ver[i])
					except ValueError:
						continue
					if diff > 0:
						self.cur_entry = entry
						self.remote_ver_str = PrintVer(remote_ver)
						break
					elif diff < 0:
						break

		if not self.cur_entry:
			self.result = 'LATEST'
			return

		url = "https://blender-smd.googlecode.com/files/io_smd_tools-{}.zip".format( PrintVer(self.cur_entry['version'],sep="") )
		print("Found new version {}, downloading from {}...".format(self.remote_ver_str, url))

		# we are already in a try/except block, any failures will be caught
		zip = urllib.request.urlopen(url)
		zip = zipfile.ZipFile( io.BytesIO(zip.read()) )
		zip.extractall(path=getFileDir( os.path.abspath( __file__ ) ))
		self.result = 'SUCCESS'
		return


#####################################
#        Shared registration        #
#####################################

def menu_func_import(self, context):
	self.layout.operator(SmdImporter.bl_idname, text="Source Engine (.smd, .vta, .dmx, .qc)")

def menu_func_export(self, context):
	self.layout.operator(SmdExporter.bl_idname, text="Source Engine (.smd, .vta)")

def register():
	bpy.utils.register_module(__name__)
	bpy.types.INFO_MT_file_import.append(menu_func_import)
	bpy.types.INFO_MT_file_export.append(menu_func_export)

	global cached_action_filter_list
	cached_action_filter_list = 0

	bpy.types.Scene.smd_path = StringProperty(name="SMD Export Root",description="The root folder into which SMDs from this scene are written", subtype='DIR_PATH')
	bpy.types.Scene.smd_qc_compile = BoolProperty(name="Compile all on export",description="Compile all QC files whenever anything is exported",default=False)
	bpy.types.Scene.smd_qc_path = StringProperty(name="QC Path",description="Location of this scene's QC file(s). Unix wildcards supported.", subtype="FILE_PATH")
	bpy.types.Scene.smd_studiomdl_branch = EnumProperty(name="SMD Target Engine Branch",items=src_branches,description="Defines toolchain used for compiles",default='orangebox')
	bpy.types.Scene.smd_studiomdl_custom_path = StringProperty(name="SMD Studiomdl Path",description="Location of studiomdl.exe for a custom compile", subtype="FILE_PATH")
	bpy.types.Scene.smd_up_axis = EnumProperty(name="SMD Target Up Axis",items=axes,default='Z',description="Use for compatibility with existing SMDs")
	formats = (
	('SMD', "SMD", "Studiomdl Data" ),
	('DMX', "DMX", "Data Model Exchange" )
	)
	bpy.types.Scene.smd_format = EnumProperty(name="SMD Export Format",items=formats,default='SMD',description="todo")
	bpy.types.Scene.smd_use_image_names = BoolProperty(name="SMD Images Override Materials",description="Causes face preview images to override materials during export",default=False)
	bpy.types.Scene.smd_layer_filter = BoolProperty(name="SMD Export visible layers only",description="Only consider objects in active viewport layers for export",default=False)

	bpy.types.Object.smd_export = BoolProperty(name="SMD Scene Export",description="Export this object with the scene",default=True)
	bpy.types.Object.smd_subdir = StringProperty(name="SMD Subfolder",description="Location, relative to scene root, for SMDs from this object")
	bpy.types.Object.smd_action_filter = StringProperty(name="SMD Action Filter",description="Only actions with names matching this filter will be exported")

	bpy.types.Armature.smd_implicit_zero_bone = BoolProperty(name="Implicit motionless bone",default=True,description="Start bone IDs at one, allowing Studiomdl to put any unweighted vertices on bone zero. Emulates Blender's behaviour, but may break compatibility with existing SMDs.")
	arm_modes = (
	('CURRENT',"Current / NLA","The armature's assigned action, or everything in an NLA track"),
	('FILTERED',"Action Filter","All actions that match the armature's filter term")
	)
	bpy.types.Armature.smd_action_selection = EnumProperty(name="Action Selection", items=arm_modes,description="How actions are selected for export",default='CURRENT')

	bpy.types.Group.smd_export = BoolProperty(name="SMD Export Combined",description="Export the members of this group to a single SMD",default=True)
	bpy.types.Group.smd_subdir = StringProperty(name="SMD Subfolder",description="Location, relative to scene root, for SMDs from this group")

	bpy.types.Curve.smd_faces = EnumProperty(name="SMD export which faces",items=(
	('LEFT', 'Left side', 'Generate polygons on the left side'),
	('RIGHT', 'Right side', 'Generate polygons on the right side'),
	('BOTH', 'Both  sides', 'Generate polygons on both sides'),
	), description="Determines which sides of the mesh resulting from this curve will have polygons",default='LEFT')

def unregister():
	bpy.utils.unregister_module(__name__)
	bpy.types.INFO_MT_file_import.remove(menu_func_import)
	bpy.types.INFO_MT_file_export.remove(menu_func_export)

	Scene = bpy.types.Scene
	del Scene.smd_path
	del Scene.smd_qc_compile
	del Scene.smd_qc_path
	del Scene.smd_studiomdl_branch
	del Scene.smd_studiomdl_custom_path
	del Scene.smd_up_axis
	del Scene.smd_format
	del Scene.smd_use_image_names
	del Scene.smd_layer_filter

	Object = bpy.types.Object
	del Object.smd_export
	del Object.smd_subdir
	del Object.smd_action_filter

	del bpy.types.Armature.smd_implicit_zero_bone
	del bpy.types.Armature.smd_action_selection

	del bpy.types.Group.smd_export
	del bpy.types.Group.smd_subdir

	del bpy.types.Curve.smd_faces

if __name__ == "__main__":
	register()
