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

axes = (('X','X','X axis'),('Y','Y','Y axis'),('Z','Z','Z axis'))

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
		from io_smd_tools.smd_import import smd_manager
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
