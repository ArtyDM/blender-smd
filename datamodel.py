import struct, array

def check_support(encoding,encoding_ver):
	if encoding == 'binary':
		if encoding_ver not in [5]:
			raise ValueError("Version {} of binary DMX is not supported".format(encoding_ver))
	else:
		raise ValueError("DMX encoding \"{}\" is not supported".format(encoding))

def _get_string(datamodel,string,use_str_dict = True):
	dict_index = -1
	if use_str_dict:
		try: dict_index = datamodel.str_dict.index(string)
		except ValueError: pass
	if dict_index != -1:
		return struct.pack("i",dict_index)
	else:
		return bytes(string,'ASCII') + bytes(1)

def _validate_array_list(list,array_type):
	if not list: return
	for item in list:
		if type(item) != array_type:
			raise TypeError("Sequence must contain only {} values".format(array_type))

class _Array(list):
	type = None
	type_str = ""
	
	def __init__(self,list=None):
		_validate_array_list(list,self.type)
		return super().__init__(list)
	
	def tobytes(self, datamodel, elem):
		return array.array(self.type_str,self).tobytes()

class _BoolArray(_Array):
	type = bool
	type_str = "b"
class _IntArray(_Array):
	type = int
	type_str = "i"
class _FloatArray(_Array):
	type = float
	type_str = "f"
class _StrArray(_Array):
	type = str	
	def tobytes(self, datamodel, elem):
		out = bytes()
		for item in self: out += _get_string(datamodel,item,use_str_dict=False)
		return out
	
class _Vector(list):
	type_str = ""
	def __init__(self,list):
		_validate_array_list(list,float)
		if len(list) != len(self.type_str):
			raise TypeError("Expected {} values".format(len(self.type_str)))
		super().__init__(list)
	
	def tobytes(self):
		out = bytes()
		for ord in self: out += struct.pack("f",ord)
		return out		
class Vector2(_Vector):
	type_str = "ff"
class Vector3(_Vector):
	type_str = "fff"
class Vector4(_Vector):
	type_str = "ffff"
class Quaternion(Vector4):
	pass
class Angle(Vector3):
	pass
class _VectorArray(_Array):
	type = list
	def __init__(self,list=None):
		_validate_array_list(self,list)
		_Array.__init__(self,list)
	def tobytes(self, datamodel, elem):
		out = bytes()
		for item in self: out += item.tobytes()
		return out
class _Vector2Array(_VectorArray):
	type = Vector2
class _Vector3Array(_VectorArray):
	type = Vector3
class _Vector4Array(_VectorArray):
	type = Vector4
class _QuaternionArray(_Vector4Array):
	type = Quaternion
class _AngleArray(_Vector3Array):
	type = Angle

class Matrix:
	pass
class _MatrixArray():
	type = Matrix

class Binary(bytes):
	pass
class _BinaryArray(_Array):
	type = Binary
	type_str = "b"
class Color(Vector4):
	pass
class _ColorArray(_Vector4Array):
	pass
	
class Time(float):
	def tobytes(self):
		return struct.pack("i",int(self * 10000))
class _TimeArray(_Array):
	type = Time
	def tobytes(self, datamodel, elem):
		out = bytes()
		for item in self:
			out += item.tobytes()
		return out

class Attribute:	
	value = None
	
	def __init__(self,name,value):
		if type(name) != str or (type(value) not in _dmxtypes and type(value) not in _dmxtypes_array):
			raise TypeError("Expected str, {}",_dmxtypes)
		self.name = name
		self.value = value
		
	def __repr__(self):
		return "<Datamodel Attribute {}[{}]>".format(type(self.value),self.name)
	
	def typeid(self,encoding,version):
		return _get_dmx_type_id(encoding,version,type(self.value))

_array_types = [list,set,tuple,array.array]
class Element:
	properties = {}
	
	def __init__(self,name,elemtype="DmElement",id=None):
		# Blender bug: importing uuid causes a runtime exception. The return value is not affected, thankfully.
		# http://projects.blender.org/tracker/index.php?func=detail&aid=28732&group_id=9&atid=498
		import uuid
		
		if type(name) != str or type(elemtype) != str or (id and type(id) != uuid.UUID):
			raise TypeError("Expected str, [str, uuid.UUID]")
			
		self.name = name
		self.type = elemtype
		self.id = id if id else uuid.uuid4()
		
		self.properties = {}
		self.attribute_order = []
		
	def __repr__(self):
		return "<Datamodel element {}[{}]>".format(self.type,self.name)
		
	def add_attribute(self,name,value,prop_type = None):
		t = type(value)
		if self.properties.get(name):
			raise ValueError("Attribute \"{}\" already exists".format(name))
		if t in _array_types and not prop_type:
			raise ValueError("A datamodel type must be specified for arrays")
		if t not in _dmxtypes and t not in _array_types:
			raise ValueError("Unsupported data type ({})".format(t))
		if t in _array_types:
			prop_type = _get_array_type(prop_type)
			value = prop_type(value)
		prop = Attribute(name,value)
		self.properties[name] = prop
		self.attribute_order.append(name)
		
		return prop
		
	def get_attribute(self,name):
		return self.properties[name]

class _ElementArray(_Array):
	type = Element
	def tobytes(self, datamodel, elem):
		out = []
		for item in self:
			out.append(datamodel.elem_chain.index(item))
		return array.array("i",out).tobytes()

_dmxtypes = [Element,int,float,bool,str,Binary,Time,Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix]
_dmxtypes_array = [_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,_TimeArray,_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray]

def _get_array_type(single_type):
	if single_type in _dmxtypes_array: raise ValueError("Argument is already an array type")
	return _dmxtypes_array[ _dmxtypes.index(single_type) ]
def _get_single_type(array_type):
	if array_type in _dmxtypes: raise ValueError("Argument is already a single type")
	return _dmxtypes[ _dmxtypes_array.index(array_type) ]

def _get_dmx_type_id(encoding,version,type):
	attr_list_v1 = [
				None,Element,int,float,bool,str,Binary,"ObjectID",Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix,
				_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,"_ObjectIDArray",_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray
			] # ObjectID is an element UUID
	attr_list_v2 = [
				None,Element,int,float,bool,str,Binary,Time,Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix,
				_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,_TimeArray,_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray
			]
	
	if encoding == "binary":
		if version in [2]:
			return attr_list_v1.index(type)
		if version in [5]:
			return attr_list_v2.index(type)
	if encoding == "keyvalues2":
		if version == 1:
			return attr_list_v1.index(type)
		if version in [2]:
			return attr_list_v2.index(type)
				
	raise ValueError("Type {} not supported in {} {}".format(type,encoding,version))

class DataModel:
	elements = []
	root = None
	
	def __init__(self,format,format_ver):
		if type(format) != str or type(format_ver) != int:
			raise TypeError("Expected str, int")
		
		self.format = format
		self.format_ver = format_ver
		
		self.elements = []
		
	def add_element(self,name,elemtype="DmElement",id=None):
		elem = Element(name,elemtype,id)
		self.elements.append(elem)
		elem.datamodel = self
		if len(self.elements) == 1: self.root = elem
		return elem
		
	def find_element(self,name):
		for elem in self.elements:
			if elem.name == name:
				return elem
		
	def remove_element(self,element):
		del self.elements[element]
	
	def _write(self,value, elem = None, use_str_dict = True):
		import uuid
		t = type(value)
		
		if t in [bytes,Binary]:
			self.out.write(value)
		
		elif t == uuid.UUID:
			self.out.write(value.bytes)
		elif t == Element:
			raise Error("Don't write elements as properties")
		elif t == str:
			self.out.write( _get_string(self,value,use_str_dict) )
				
		elif issubclass(t, _Array):
			self.out.write( struct.pack("i",len(value)) )
			self.out.write( value.tobytes(self,elem) )
		elif issubclass(t,_Vector) or t == Time:
			self.out.write(value.tobytes())
		
		elif t == bool:
			self.out.write( struct.pack("b",value) )
		elif t == int:
			self.out.write( struct.pack("i",value) )
		elif t == float:
			self.out.write( struct.pack("f",value) )
	
	def _write_element_index(self,elem):
		self._write(elem.type)
		self._write(elem.name)
		self._write(elem.id)		
		
		self.elem_chain.append(elem)
		
		for name in elem.attribute_order:
			prop = elem.properties[name]
			t = type(prop.value)
			if t == Element and prop.value not in self.elem_chain:
				self._write_element_index(prop.value)
			if t == _ElementArray:
				for i in prop.value:
					if i not in self.elem_chain:
						self._write_element_index(i)
		
	def _write_element_props(self):
		for elem in self.elem_chain:
			self._write(len(elem.properties))
			for prop_name in elem.attribute_order:
				prop = elem.properties[prop_name]
				self._write(prop_name)
				self._write(struct.pack("b", prop.typeid(self.encoding,self.encoding_ver) ))
				if type(prop.value) == Element:
					self._write(self.elem_chain.index(prop.value),elem)
				else:
					self._write(prop.value,elem)
		
	def _write_element(self,elem):
		self._write_element_index(elem)
		self._write_element_props()
		
	def _build_str_dict(self,elem):
		self.str_dict.add(elem.name)
		self.str_dict_checked.append(elem)
		self.str_dict.add(elem.type)
		for name in elem.attribute_order:
			prop = elem.properties[name]
			self.str_dict.add(name)
			if type(prop.value) == str:
				self.str_dict.add(prop.value)
			if type(prop.value) == Element:
				if prop.value not in self.str_dict_checked:
					self._build_str_dict(prop.value)
			if type(prop.value) == _ElementArray:
				for i in prop.value:
					if i not in self.str_dict_checked:
						self._build_str_dict(i)
		
	def write(self,path,encoding,encoding_ver):
		check_support(encoding, encoding_ver)
		
		self.out = open(path,'wb')
		self.encoding = encoding
		self.encoding_ver = encoding_ver
		
		# header
		self._write("<!-- dmx encoding {} {} format {} {} -->\n".format(encoding,encoding_ver,self.format,self.format_ver),use_str_dict = False)
		
		# string dictionary
		self.str_dict = set()
		self.str_dict_checked = []
		self._build_str_dict(self.root)
		self.str_dict = list(self.str_dict)
		
		self._write(len(self.str_dict))
		x=0
		for i in self.str_dict:
			self._write(i,use_str_dict = False)
			#print(x,i)
			x+=1
			
		# count elements
		out_elems = set()
		def _count_child_elems(elem):
			out_elems.add(elem)
			for name in elem.attribute_order:
				prop = elem.properties[name]
				t = type(prop.value)
				if t == Element and prop.value not in out_elems:
					_count_child_elems(prop.value)
				if t == _ElementArray:
					for i in prop.value:
						if i not in out_elems:
							_count_child_elems(i)
		_count_child_elems(self.root)
		self._write(len(out_elems))
		
		self.elem_chain = []
		self._write_element(self.root) # only write stuff referenced by the root element
				
		self.out.close()
