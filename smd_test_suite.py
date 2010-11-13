bl_addon_info = {
	"name": "SMD Tools Test Suite",
	"author": "Tom Edwards, EasyPickins",
	"version": (0, 8),
	"blender": (2, 5, 4),
	"category": "Import/Export",
	"location": "Properties > Scene",
	"wiki_url": "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools",
	"tracker_url": "http://developer.valvesoftware.com/wiki/Talk:Blender_SMD_Tools",
	"description": "Run tests on SMD Tools."}

import bpy, os, io_smd_tools
from io_smd_tools import *

test_suite_root = os.path.abspath('/SMD_Tools_Test_Suite')

def available():
	return os.path.exists(test_suite_root)

def compareVectorElem(e1,e2,epsilon=0.001):
	return e1 - e2 > epsilon

def compareVector(v1,v2,epsilon=0.001):
	if compareVectorElem(v1.x,v2.x,epsilon):
		return 1
	if compareVectorElem(v1.y,v2.y,epsilon):
		return 1
	if compareVectorElem(v1.z,v2.z,epsilon):
		return 1
	return 0
	
def vectorString(v):
	return "%0.06f,%0.06f,%0.06f" % (v.x,v.y,v.z)

class SCENE_OT_SmdTestSuite(bpy.types.Operator):
	bl_idname = "smd_test_suite"
	bl_label = "Test SMD import/export"
	bl_description = "Runs a test suite on the importer/exporter"

	def execute(self,context):
		#if not getattr(io_smd_tools,'log',None): # won't exist if the importer/exporter hasn't been run yet
		#	setattr(io_smd_tools,'log',logger())
		io_smd_tools.log = logger()
		
		if not available():
			self.report('ERROR',"can't find the test suite directory")
			return {'CANCELLED'}
		
		self.context = context
		self.newestArmatureObj = None
		
		startTime = time.time()

		with open(self.ipath('log.txt'), 'w') as self.logfile:
			self.runTests()
		
		print('----- TEST SUITE FINISHED in ' + str(round(time.time() - startTime,1)) + ' seconds -----')
		
		return {'FINISHED'}

	def runTests(self):
		
		connectBones = self.context.scene.smd_test_suite.connectBones
		self.expect = []

		#return # <<<<<----------

		# sourcesdk_content\hl2\modelsrc\weapons\v_physcannon\Prongs.smd
		# A 2-frame animation.  The curve-cleaner chopped out the last frame.
		# 2 mangled rotations
		self.runTest('Prongs.smd', 'ANIM', connectBones=connectBones, multiImport=True)

		# sourcesdk_content\hl2\modelsrc\weapons\v_smg1\*
		# Alt_fire was rotated 90 degrees, has extra root bone compared to ref
		self.runTest('Smg1_reference.smd', 'REF', connectBones=connectBones, multiImport=True)
		self.expectBonesRemoved('ValveBiped','ValveBiped.cube','ValveBiped.SpineControl','ValveBiped.SpineControl1','ValveBiped.SpineControl2')
		self.expectBonesRemoved('ValveBiped.SpineControl3','ValveBiped.NeckControl','ValveBiped.HeadControl','ValveBiped.HandControlPosL','ValveBiped.ArmRollL')
		self.expectBonesRemoved('ValveBiped.HandControlPosR','ValveBiped.ArmRollR','ValveBiped.LegRollL','ValveBiped.LegRollR')
		self.runTest('Alt_fire.smd', 'ANIM', connectBones=connectBones, multiImport=False)

		# sourcesdk_content\hl2\modelsrc\Buggy
		# buggy_ammo_open.smd has fewer bones, is missing Gun_Parent for example, so lots of differences on export
		self.runTest('buggy_reference.smd', 'REF', connectBones=connectBones, multiImport=True)
		self.runTest('buggy_ammo_open.smd', 'ANIM', connectBones=connectBones, multiImport=False)

		# sourcesdk_content\hl2\modelsrc\Antlion_Guard
		# some polygons go missing
		self.runTest('Antlion_guard_reference.smd', 'REF', connectBones=connectBones, multiImport=True)
		self.runTest('bust_floor.smd', 'ANIM', connectBones=connectBones, multiImport=False)

		# sourcesdk_content\hl2\modelsrc\weapons\v_rocket_launcher
		# rpg_reference.smd has a too-long material name
		# rpg_reload.smd (originally reload.smd) doesn't list every bone for each frame
		self.runTest('rpg_reference.smd', 'REF', connectBones=connectBones, multiImport=True)
		self.runTest('rpg_reload.smd', 'ANIM', connectBones=connectBones, multiImport=False)

		# ANIM_SOLO test
		self.runTest('bust_floor.smd', 'ANIM', connectBones=connectBones, multiImport=True)

		# DOW2
		self.runTest('dreadnought_main.smd', 'REF', connectBones=connectBones, multiImport=True)

		# connectBones tests
		# DOW2
		#self.runTest('dreadnought_main.smd', 'REF', connectBones='COMPATIBILITY', multiImport=True)
		
		# missing file test
		self.runTest('no-such-file.smd', 'REF', connectBones=connectBones, multiImport=True)
		
		'''
		for length in [0.001,0.01,0.1,1]:
			io_smd_tools.min_bone_length = length
			self.runTest('dreadnought_main.smd', 'REF', connectBones=connectBones, multiImport=True)

		for length in [0.001,0.01,0.1,1]:
			io_smd_tools.min_bone_length = length
			self.runTest('deff-dread.smd', 'REF', connectBones=connectBones, multiImport=True)
		'''

		# Y-up mesh + anim
		self.runTest('heavy_model.smd', 'REF', inAxis='Y', outAxis='Y', connectBones=connectBones, multiImport=True)
		self.runTest('heavy_anim2.smd', 'ANIM', inAxis='Y', outAxis='Y', connectBones=connectBones, multiImport=False)

		# Y-up mesh
		self.runTest('demo_model.smd', 'REF', inAxis='Y', outAxis='Y', connectBones=connectBones, multiImport=True)
		self.runTest('engineer_model.smd', 'REF', inAxis='Y', outAxis='Y', connectBones=connectBones, multiImport=True)
		self.runTest('medic_model.smd', 'REF', inAxis='Y', outAxis='Y', connectBones=connectBones, multiImport=True)
		self.runTest('pyro_model.smd', 'REF', inAxis='Y', outAxis='Y', connectBones=connectBones, multiImport=True)
		
		# Z -> Y -> Z
		self.runTestZYZ('Antlion_guard_reference.smd', 'REF', connectBones=connectBones)
		self.runTestZYZ('bust_floor.smd', 'ANIM', connectBones=connectBones)

		# imp -> exp -> imp -> exp -> imp -> exp
		self.runTestInOutX3('Antlion_guard_reference.smd', 'REF', connectBones=connectBones)
		self.runTestInOutX3('rpg_reload.smd', 'ANIM', connectBones=connectBones)
	
	def runTest(self,filename,jobType,inAxis='Z',outAxis='Z',connectBones='NONE',multiImport='False',comment=''):
		comment = ' connectBones='+connectBones+comment
		self.logfile.write('---------- %s %s%s ----------\n' % (jobType,filename,comment))
		inFile = self.ipath(filename)
		outFile = self.opath(filename)
		if self.runTestAux(inFile,outFile,jobType,inAxis,outAxis,connectBones,multiImport):
			self.compareSMDs(inFile,outFile)
	
	def runTestZYZ(self,filename,jobType,connectBones='NONE',comment=''):
		comment = ' Z -> Y -> Z'
		comment = ' connectBones='+connectBones+comment
		self.logfile.write('---------- %s %s%s ----------\n' % (jobType,filename,comment))
		self.runTestAux(self.ipath(filename),       self.opath('ZY_'+filename), jobType, inAxis='Z', outAxis='Y', connectBones=connectBones, multiImport=True)
		self.runTestAux(self.opath('ZY_'+filename), self.opath('YZ_'+filename), jobType, inAxis='Y', outAxis='Z', connectBones=connectBones, multiImport=True)
		self.compareSMDs(self.ipath(filename),      self.opath('YZ_'+filename))

	def runTestInOutX3(self,filename,jobType,inAxis='Z',outAxis='Z',connectBones='NONE',comment=''):
		comment = ' imp -> exp -> imp -> exp -> imp -> exp'
		comment = ' connectBones='+connectBones+comment
		self.logfile.write('---------- %s %s%s ----------\n' % (jobType,filename,comment))
		basename = os.path.splitext(filename)[0]
		self.runTestAux(self.ipath(filename),          self.opath(basename+'-1.smd'), jobType, inAxis=inAxis,outAxis=outAxis,connectBones=connectBones, multiImport=True)
		self.runTestAux(self.opath(basename+'-1.smd'), self.opath(basename+'-2.smd'), jobType, connectBones=connectBones, multiImport=True)
		self.runTestAux(self.opath(basename+'-2.smd'), self.opath(basename+'-3.smd'), jobType, connectBones=connectBones, multiImport=True)
		self.compareSMDs(self.ipath(filename),self.opath(basename+'-3.smd'))

	def runTestAux(self,inFile,outFile,jobType,inAxis='Z',outAxis='Z',connectBones='NONE',multiImport=False):
		self.filename = outFile
		if not os.path.exists(inFile):
			self.fail('skipping missing test file: ' + inFile)
			return False
		objects = []
		objects += self.context.scene.objects
		readSMD(self.context, filepath=inFile, upAxis=inAxis, connectBones=connectBones, newscene=False, multiImport=multiImport)
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
			writeSMD(self.context, objWrite, -1, filepath=outFile)
			return True
		return False

	def compareSMDs(self,inFile,outFile):
		self.filename = outFile
		self.data1 = self.parseSMD(inFile)
		self.data2 = self.parseSMD(outFile)
		print('test suite: comparing...')
		self.compareData(self.data1,self.data2)
		self.logfile.flush()
		self.expect = [] # clear it out for next test

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
			self.fail('triangle count mismatch: got %d expected %d' % (data2['triangles'],data1['triangles']))
		if 'materials' in data1:
			for material in data1['materials']:
				if not material in data2['materials']:
					self.fail('missing material "%s"' % material)
		if 'ID_to_name' in data1:
			missingBoneNames = []
			for boneName in data1['name_to_ID']:
				if not boneName in data2['name_to_ID']:
					if not self.expectedBoneRemoved(boneName):
						missingBoneNames.append(boneName)
					continue
				parentName1 = parentName2 = '<none>'
				parentID1 = data1['name_to_parentID'][boneName]
				if parentID1 != -1:
					parentName1 = data1['ID_to_name'][parentID1]
				parentID2 = data2['name_to_parentID'][boneName]
				if parentID2 != -1:
					parentName2 = data2['ID_to_name'][parentID2]
				if self.expectedBoneRemoved(parentName1):
					if parentName1 == parentName2:
						self.fail('expected parent of bone "%s" to change: got "%s"' % (boneName,parentName1))
				elif parentName1 != parentName2:
					self.fail('parent of bone "%s" mismatch: got "%s" expected "%s"' % (boneName,parentName2,parentName1))
			for boneName in missingBoneNames:
				self.fail('output is missing bone "%s"' % boneName)
		if 'frameCount' in data1:
			if data1['frameCount'] != data2['frameCount']:
				self.fail('frame count mismatch: got %d expected %d' % (data2['frameCount'],data1['frameCount']))
			pos1 = {}
			rot1 = {}
			pos2 = {}
			rot2 = {}
			for frame in range(data1['frameCount']):
				frameData1 = data1['frames'][frame]
				# Each frameBone is (id,pos,rot)
				for frameBone in frameData1:
					pos1[data1['ID_to_name'][frameBone[0]]] = frameBone[1]
					rot1[data1['ID_to_name'][frameBone[0]]] = frameBone[2]
				frameData2 = data2['frames'][frame]
				for frameBone in frameData2:
					pos2[data2['ID_to_name'][frameBone[0]]] = frameBone[1]
					rot2[data2['ID_to_name'][frameBone[0]]] = frameBone[2]
				for boneName in data1['name_to_ID']:
					if not boneName in data2['name_to_ID']:
						continue
					if self.compareCumulativePosition(frame,boneName,pos1,rot1,pos2,rot2):
						pass
					if self.compareCumulativeRotation(frame,boneName,rot1,rot2):
						pass
					# If we expected the bone to be reparented then we can't compare the local pos/rot to the original
					if self.expectedParentChanged(boneName):
						continue
					if compareVector(pos1[boneName],pos2[boneName]):
						self.fail('frame %d bone %s POS got %s expected %s' % (frame,boneName,vectorString(pos2[boneName]),vectorString(pos1[boneName])))
					if compareVector(rot1[boneName],rot2[boneName]):
						q1 = mathutils.Euler(rot1[boneName]).to_quat()
						q2 = mathutils.Euler(rot2[boneName]).to_quat()
						q3 = q1.difference(q2)
						if q3.angle == 0.0 or round(q3.angle,6) == round(math.pi*2,6):
							if not self.context.scene.smd_test_suite.hide_quat_ok:
								self.fail('frame %d bone %s ROT got %s expected %s QUAT_OK' % (frame,boneName,vectorString(rot2[boneName]),vectorString(rot1[boneName])))
						else:
							self.fail('frame %d bone %s ROT got %s expected %s QUAT_FAIL' % (frame,boneName,vectorString(rot2[boneName]),vectorString(rot1[boneName])))
							self.fail('-->%s %s %s' % (q3,q3.angle,q3.magnitude))
	
	def compareCumulativePosition(self, frame, boneName, pos1, rot1, pos2, rot2):
		globalPos1 = self.calcGlobalPosition(boneName,self.data1,pos1,rot1)
		globalPos2 = self.calcGlobalPosition(boneName,self.data2,pos2,rot2)
		if compareVector(globalPos1,globalPos2):
			self.fail('frame %d bone %s GLOBAL-POS got %s expected %s' % (frame,boneName,vectorString(globalPos1),vectorString(globalPos2)))

	def compareCumulativeRotation(self, frame, boneName, rot1, rot2):
		rotMat1 = self.calcGlobalMatrix(boneName,self.data1,rot1)
		rotMat2 = self.calcGlobalMatrix(boneName,self.data2,rot2)
		eul1 = rotMat1.to_euler()
		eul2 = rotMat2.to_euler()
		if compareVector(eul1,eul2,0.005):
			q1 = eul1.to_quat()
			q2 = eul2.to_quat()
			q3 = q1.difference(q2)
			if q3.angle == 0.0 or round(q3.angle,6) == round(math.pi*2,6):
				if not self.context.scene.smd_test_suite.hide_quat_ok:
					self.fail('frame %d bone %s GLOBAL-ROT got %s expected %s QUAT_OK' % (frame,boneName,vectorString(eul2),vectorString(eul1)))
			else:
				self.fail('frame %d bone %s GLOBAL-ROT got %s expected %s QUAT_FAIL' % (frame,boneName,vectorString(eul2),vectorString(eul1)))
				self.fail('-->%s %s %s' % (q3,q3.angle,q3.magnitude))
	
	def calcGlobalMatrix(self,boneName,data,rots):
		smd_rot = rots[boneName]
		rotMat = rMat(-smd_rot.x, 3,'X') * rMat(-smd_rot.y, 3,'Y') * rMat(-smd_rot.z, 3,'Z')
		parentID = data['name_to_parentID'][boneName]
		if parentID != -1:
			parentName = data['ID_to_name'][parentID]
			rotMat *= self.calcGlobalMatrix(parentName,data,rots)
		return rotMat
	
	def calcGlobalPosition(self,boneName,data,poss,rots):
		parentID = data['name_to_parentID'][boneName]
		if parentID != -1:
			parentName = data['ID_to_name'][parentID]
			parentPos = self.calcGlobalPosition(parentName,data,poss,rots)
			if gVectorMathReversed:
				return parentPos + poss[boneName] * self.calcGlobalMatrix(parentName,data,rots).invert()
			return parentPos + poss[boneName] * self.calcGlobalMatrix(parentName,data,rots)
		else:
			return poss[boneName]

	def expectBonesRemoved(self,*args):
		for boneName in args:
			self.expect.append(['bone-remove',boneName])

	def expectedBoneRemoved(self,boneName):
		for sublist in self.expect:
			if sublist[0] == 'bone-remove' and sublist[1] == boneName:
				return True
		return False
	
	def expectedParentChanged(self,boneName):
		parentID = self.data1['name_to_parentID'][boneName]
		if parentID != -1:
			parentName = self.data1['ID_to_name'][parentID]
			return self.expectedBoneRemoved(parentName)
		return False

	def fail(self,msg):
		self.logfile.write('%s\n' % msg)
		print('test suite fail: %s see log.txt' % (self.filename))

	def ipath(self,filename):
		return os.path.join(test_suite_root,filename)

	def opath(self,filename):
		return os.path.join(test_suite_root,'output',filename)

class SCENE_PT_SmdTestSuite(bpy.types.Panel):
	bl_label = "SMD Test Suite"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	bl_default_closed = True

	def __init__(self, context):
		# A new instance of this class gets created for *every* draw operation!
		#print('SCENE_PT_SmdTestSuite __init__')
		pass

	def __del__(self):
		#print('SCENE_PT_SmdTestSuite __del__')
		pass

	def draw(self, context):
		l = self.layout
		l.prop(context.scene.smd_test_suite,"connectBones",text='Connect')
		l.prop(context.scene.smd_test_suite,"hide_quat_ok")
		row = l.row()
		if available():
			row.operator(SCENE_OT_SmdTestSuite.bl_idname,text="Run test suite",icon='FILE_TICK')
		else:
			row.operator(SCENE_OT_SmdTestSuite.bl_idname,text="Can't find test_suite_root",icon='ERROR')
			row.enabled = False

class SmdTestSuiteProps(bpy.types.IDPropertyGroup):
	hide_quat_ok = BoolProperty(name="Hide QUAT_OK",description="Don't report different Euler rotations that represent the same angle",default=True)
	connectionEnum = ( ('NONE','NONE','All bones will be unconnected spheres'),
	('COMPATIBILITY','COMPATIBILITY','Only connect bones that will not break compatibility with existing SMDs'),
	('ALL','ALL','All bones that can be connected will be, disregarding backwards compatibility') )
	connectBones = EnumProperty(name="Bone Connection Mode",items=connectionEnum,description="How to choose which bones to connect together",default='COMPATIBILITY')

def register():
	print('smd_test_suite register')
	bpy.types.Scene.smd_test_suite = PointerProperty(type=SmdTestSuiteProps, name='SMD Test Suite', description='SMD Test Suite Settings')

def unregister():
	print('smd_test_suite unregister')
	del bpy.types.Scene.smd_test_suite

if __name__ == "__main__":
    register()
