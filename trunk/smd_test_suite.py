import bpy, os, io_smd_tools
from io_smd_tools import *

test_suite_root = os.path.normpath('/SMD_Tools_Test_Suite')

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
		#if not getattr(io_smd_tools,'log',None): # won't exist if the importer/exporter hasn't been run yet
		#	setattr(io_smd_tools,'log',logger())
		io_smd_tools.log = logger()
		
		if not os.path.exists(test_suite_root):
			os.makedirs(test_suite_root)
		
		self.logfile = open(self.ipath('log.txt'), 'w')
		
		# sourcesdk_content\hl2\modelsrc\Antlion_Guard
		readSMD(context, filepath=self.ipath('Antlion_guard_reference.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=True)
		readSMD(context, filepath=self.ipath('bust_floor.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=False)
		writeSMD(context, bpy.data.objects['Antlion_guard_ref.000'],filepath=self.opath('Antlion_guard_reference.smd'))
		writeSMD(context, bpy.data.objects['Antlion_guard_referen'],filepath=self.opath('bust_floor.smd'))
		self.compareSMDs(filename='Antlion_guard_reference.smd')
		self.compareSMDs(filename='bust_floor.smd')

		# sourcesdk_content\hl2\modelsrc\Buggy
		# buggy_ammo_open.smd has fewer bones, is missing Gun_Parent for example
		readSMD(context, filepath=self.ipath('buggy_reference.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=True)
		readSMD(context, filepath=self.ipath('buggy_ammo_open.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=False)
		writeSMD(context, bpy.data.objects['buggy_reference.001'],filepath=self.opath('buggy_reference.smd'))
		writeSMD(context, bpy.data.objects['buggy_reference'],filepath=self.opath('buggy_ammo_open.smd'))
		self.compareSMDs(filename='buggy_reference.smd')
		#self.compareSMDs(filename='buggy_ammo_open.smd')

		# sourcesdk_content\hl2\modelsrc\weapons\v_rocket_launcher
		# rpg_reference.smd has a too-long material name
		# rpg_reload.smd (originally reload.smd) doesn't list every bone for each frame
		readSMD(context, filepath=self.ipath('rpg_reference.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=True)
		readSMD(context, filepath=self.ipath('rpg_reload.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=False)
		writeSMD(context, bpy.data.objects['rpg_reference.001'],filepath=self.opath('rpg_reference.smd'))
		writeSMD(context, bpy.data.objects['rpg_reference'],filepath=self.opath('rpg_reload.smd'))
		self.compareSMDs(filename='rpg_reference.smd')
		self.compareSMDs(filename='rpg_reload.smd')

		# ANIM_SOLO test
		readSMD(context, filepath=self.ipath('bust_floor.smd'), upAxis='Z', connectBones='NONE', cleanAnim=False, newscene=False, multiImport=True)

		self.logfile.close()

		return {'FINISHED'}
	
	def compareSMDs(self,filename):
		self.filename = filename
		file1 = self.ipath(filename)
		file2 = self.opath(filename)
		data1 = self.parseSMD(file1)
		data2 = self.parseSMD(file2)
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
		self.logfile.write('test suite fail: %s %s\n' % (self.filename, msg))
		print('test suite fail: %s %s' % (self.filename, msg))

	def ipath(self,filename):
		return os.path.join(test_suite_root,filename)
	def opath(self,filename):
		return os.path.join(test_suite_root,'output',filename)

