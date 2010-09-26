from io_smd_tools.smd_import import *
from io_smd_tools.smd_export import *

test_suite_root = os.path.normpath('/SMD_Tools_Test_Suite')

def available():
	if not os.path.exists(test_suite_root):
		return None
	return SmdTestSuite.bl_idname

def compareVectorElem(e1,e2):
	return e1 - e2 > 0.001

def compareVector(v1,v2):
	if compareVectorElem(v1.x,v2.x):
		return 1
	if compareVectorElem(v1.y,v2.y):
		return 1
	if compareVectorElem(v1.z,v2.z):
		return 1
	return 0
	
def vectorString(v):
	return "%0.06f,%0.06f,%0.06f" % (v.x,v.y,v.z)
	

class SmdTestSuite(bpy.types.Operator):
	bl_idname = "smd_test_suite"
	bl_label = "Test SMD import/export"
	bl_description = "Runs a test suite on the importer/exporter"

	def execute(self,context):

		from io_smd_tools import smd_import, smd_export
		smd_import.log = smd_export.log = logger()
		
		if not available():
			self.report('ERROR',"can't find the test suite directory")
			return {'CANCELLED'}
		
		self.logfile = open(self.ipath('log.txt'), 'w')
		
		self.context = context
		self.newestArmatureObj = None
		'''
		# sourcesdk_content\hl2\modelsrc\Antlion_Guard
		# some polygons go missing
		self.runTest('Antlion_guard_reference.smd', 'REF', connectBones='NONE', multiImport=True)
		self.runTest('bust_floor.smd', 'ANIM', connectBones='NONE', multiImport=False)

		# sourcesdk_content\hl2\modelsrc\Buggy
		# buggy_ammo_open.smd has fewer bones, is missing Gun_Parent for example, so lots of differences on export
		self.runTest('buggy_reference.smd', 'REF', connectBones='NONE', multiImport=True)
		self.runTest('buggy_ammo_open.smd', 'ANIM', connectBones='NONE', multiImport=False)

		# sourcesdk_content\hl2\modelsrc\weapons\v_rocket_launcher
		# rpg_reference.smd has a too-long material name
		# rpg_reload.smd (originally reload.smd) doesn't list every bone for each frame
		self.runTest('rpg_reference.smd', 'REF', connectBones='NONE', multiImport=True)
		self.runTest('rpg_reload.smd', 'ANIM', connectBones='NONE', multiImport=False)

		# ANIM_SOLO test
		self.runTest('bust_floor.smd', 'ANIM', connectBones='NONE', multiImport=True)

		# DOW2
		self.runTest('dreadnought_main.smd', 'REF', connectBones='NONE', multiImport=True)

		# connectBones tests
		# DOW2
		self.runTest('dreadnought_main.smd', 'REF', connectBones='COMPATIBILITY', multiImport=True)
		
		self.runTest('no-such-file.smd', 'REF', connectBones='NONE', multiImport=True)
		'''
		'''
		for length in [0.001,0.01,0.1,1]:
			io_smd_tools.min_bone_length = length
			self.runTest('dreadnought_main.smd', 'REF', connectBones='NONE', multiImport=True)

		for length in [0.001,0.01,0.1,1]:
			io_smd_tools.min_bone_length = length
			self.runTest('deff-dread.smd', 'REF', connectBones='NONE', multiImport=True)
		'''
		
		# Y-up tests
		self.runTest('heavy_model.smd', 'REF', inAxis='Y', outAxis='Y', connectBones='NONE', multiImport=True)
		self.runTest('heavy_anim2.smd', 'ANIM', inAxis='Y', outAxis='Y', connectBones='NONE', multiImport=False)

		# import Z-up, export to Y-up, import Y-up as Z-up, export Z-up and compare to original
		self.logfile.write('---------- Antlion_guard_reference.smd Z -> Y - > Z----------\n')
		self.runTestAux(self.ipath('Antlion_guard_reference.smd'), self.opath('ZY_Antlion_guard_reference.smd'), 'REF', inAxis='Z', outAxis='Y', connectBones='NONE', multiImport=True)
		self.runTestAux(self.opath('ZY_Antlion_guard_reference.smd'), self.opath('YZ_Antlion_guard_reference.smd'), 'REF', inAxis='Y', outAxis='Z', connectBones='NONE', multiImport=True)
		self.compareSMDs(self.ipath('Antlion_guard_reference.smd'),self.opath('YZ_Antlion_guard_reference.smd'))

		self.logfile.close()

		return {'FINISHED'}
	
	def runTest(self,filename,jobType,inAxis='Z',outAxis='Z',connectBones='NONE',multiImport='False'):
		self.logfile.write('---------- %s ----------\n' % filename)
		inFile = self.ipath(filename)
		outFile = self.opath(filename)
		self.runTestAux(inFile,outFile,jobType,inAxis,outAxis,connectBones,multiImport)
		self.compareSMDs(inFile,outFile)

	def runTestAux(self,inFile,outFile,jobType,inAxis='Z',outAxis='Z',connectBones='NONE',multiImport='False'):
		if not os.path.exists(inFile):
			self.fail('skipping missing test file: ' + inFile)
			return
		objects = []
		objects += self.context.scene.objects
		readSMD(self.context, filepath=inFile, upAxis=inAxis, connectBones=connectBones, cleanAnim=False, newscene=False, multiImport=multiImport)
		newObjects = []
		for object in self.context.scene.objects:
			if not object in objects:
				print('new object ', object.name, ':', object.type)
				newObjects.append(object)
				if object.type == 'ARMATURE':
					self.newestArmatureObj = object
		objWrite = None
		for object in self.context.scene.objects:
			#if object.name == 'smd_bone_vis': continue
			if object == self.newestArmatureObj and jobType == 'ANIM':
				if objWrite:
					self.fail('trying to write unexpected extra object ', object)
				else:
					objWrite = object
			elif object.type == 'MESH' and jobType == 'REF' and object in newObjects:
				if objWrite:
					self.fail('trying to write unexpected extra object ', object)
				else:
					objWrite = object
		if objWrite:
			bpy.context.scene.smd_up_axis = outAxis
			writeSMD(self.context, objWrite, filepath=outFile)

	def compareSMDs(self,inFile,outFile):
		self.filename = outFile
		data1 = self.parseSMD(inFile)
		data2 = self.parseSMD(outFile)
		self.compareData(data1,data2)
	
	def parseSMD(self,filepath):
		data = {}
		self.file = open(filepath, 'r')
		for line in self.file:
			if line == "nodes\n": self.readBones(data)
			if line == "skeleton\n": self.readFrames(data)
			if line == "triangles\n": self.readPolys(data)
			if line == "vertexanimation\n": self.readShapes(data)
		self.file.close()
		return data

	def readBones(self,data):
		data['ID_to_name'] = {}
		data['name_to_ID'] = {}
		data['name_to_parentID'] = {}
		for line in self.file:
			if line == 'end\n':
				break

			s = line.strip()
			m = re.match('([-+]?\d+)\s+"([\S ]+)"\s+([-+]?\d+)', s)
			values = list(m.groups())
			
			smd_id = int(values[0])
			name = values[1]
			parent_id = int(values[2])
			
			data['ID_to_name'][smd_id] = name
			data['name_to_ID'][name] = smd_id
			data['name_to_parentID'][name] = parent_id

	def readFrames(self,data):
		data['frames'] = {}
		frameCount = 0
		for line in self.file:
			if line == 'end\n':
				break
			values = line.split()
			if values[0] == 'time':
				data['frames'][frameCount] = []
				frameCount += 1
				continue
			smd_id = int(values[0])
			smd_pos = vector([float(values[1]), float(values[2]), float(values[3])])
			smd_rot = vector([float(values[4]), float(values[5]), float(values[6])])
			data['frames'][frameCount-1].append((smd_id,smd_pos,smd_rot))
		data['frameCount'] = frameCount

	def readPolys(self,data):
		data['materials'] = []
		data['triangles'] = 0
		for line in self.file:
			line = line.rstrip("\n")
			if line == "end" or "":
				break
			if not line in data['materials']:
				data['materials'].append(line)
			vertexCount = 0
			for line in self.file:
				values = line.split()
				vertexCount += 1
				if vertexCount == 3:
					data['triangles'] += 1
					break
		
	def compareData(self,data1,data2):
		for key in data1:
			if not key in data2:
				self.fail('missing "%s" block' % key)
		for key in data2:
			if not key in data1:
				self.fail('extra "%s" block' % key)
		if 'triangles' in data1 and data1['triangles'] != data2['triangles']:
			self.fail('triangle count mismatch got %d expected %d' % (data2['triangles'],data1['triangles']))
		if 'materials' in data1:
			for material in data1['materials']:
				if not material in data2['materials']:
					self.fail('missing material "%s"' % material)
		if 'ID_to_name' in data1:
			for boneName in data1['name_to_ID']:
				if not boneName in data2['name_to_ID']:
					self.fail('missing bone "%s"' % boneName)
				parentName1 = parentName2 = '<none>'
				if data1['name_to_parentID'][boneName] != -1:
					parentName1 = data1['ID_to_name'][data1['name_to_parentID'][boneName]]
				if data2['name_to_parentID'][boneName] != -1:
					parentName2 = data2['ID_to_name'][data2['name_to_parentID'][boneName]]
				if parentName1 != parentName2:
					self.fail('parent of bone "%s" got "%s" expected "%s"' % (boneName,parentName2,parentName1))
		if 'frameCount' in data1:
			if data1['frameCount'] != data2['frameCount']:
				self.fail('frame count mismatch got %d expected %d' % (data2['frameCount'],data1['frameCount']))
			pos1 = {}
			rot1 = {}
			pos2 = {}
			rot2 = {}
			for frame in range(data1['frameCount']):
				frameData1 = data1['frames'][frame]
				for frameBone in frameData1:
					pos1[data1['ID_to_name'][frameBone[0]]] = frameBone[1]
					rot1[data1['ID_to_name'][frameBone[0]]] = frameBone[2]
				frameData2 = data2['frames'][frame]
				for frameBone in frameData2:
					pos2[data2['ID_to_name'][frameBone[0]]] = frameBone[1]
					rot2[data2['ID_to_name'][frameBone[0]]] = frameBone[2]
				for boneName in data1['name_to_ID']:
					if compareVector(pos1[boneName],pos2[boneName]):
						self.fail('frame %d bone %s POS got %s expected %s' % (frame,boneName,vectorString(pos2[boneName]),vectorString(pos1[boneName])))
					if compareVector(rot1[boneName],rot2[boneName]):
						self.fail('frame %d bone %s ROT got %s expected %s' % (frame,boneName,vectorString(rot2[boneName]),vectorString(rot1[boneName])))

	def fail(self,msg):
		self.logfile.write('%s\n' % msg)
		print('test suite fail: %s %s' % (self.filename, msg))

	def ipath(self,filename):
		return os.path.join(test_suite_root,filename)

	def opath(self,filename):
		return os.path.join(test_suite_root,'output',filename)

def register():
	pass

def unregister():
	pass
