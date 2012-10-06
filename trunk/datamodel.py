import struct, array, io, binascii
from struct import unpack,calcsize

global _kv2_indent
_kv2_indent = 0
global header_format
header_format = "<!-- dmx encoding {:s} {:d} format {:s} {:d} -->\n"

intsize = calcsize("i")
floatsize = calcsize("f")

def check_support(encoding,encoding_ver):
	if encoding == 'binary':
		if encoding_ver not in [5]:
			raise ValueError("Version {} of binary DMX is not supported".format(encoding_ver))
	elif encoding == 'keyvalues2':
		if encoding_ver not in [1]:
			raise ValueError("Version {} of keyvalues2 DMX is not supported".format(encoding_ver))
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

def _get_kv2_indent():
	return '\t' * _kv2_indent

def _validate_array_list(list,array_type):
	if not list: return
	for item in list:
		if type(item) != array_type:
			raise TypeError("Sequence must contain only {} values".format(array_type))
			
def _quote(str):
	return "\"{}\"".format(str)
	
def get_bool(file):
	return file.read(1) != b'\x00'
def get_byte(file):
	return int(unpack("B",file.read(1))[0])
def get_char(file):
	return unpack("c",file.read(1))[0].decode('ASCII')
def get_int(file):
	return int( unpack("i",file.read(intsize))[0] )
def get_short(file):
	return int( unpack("H",file.read(int(intsize/2)))[0] )
def get_float(file):
	return float( unpack("f",file.read(floatsize))[0] )
def get_vec(file,dim):
	return list( unpack("{}f".format(dim),file.read(floatsize*dim)) )
	
def get_str(file):
	out = ""
	while True:
		cur = file.read(1)
		if cur == b'\x00': return out
		out += cur.decode('ASCII')

def _get_kv2_repr(var):
	t = type(var)
	if t == bool:
		return "1" if var else "0"
	elif t == float:
		out = "{:.10f}".format(var)
		return out.rstrip("0").rstrip(".")
	elif t == Element:
		return str(var.id)
	elif issubclass(t, _Array):
		return var.to_kv2()
	else:
		return str(var)

class _Array(list):
	type = None
	type_str = ""	
	
	def __init__(self,list=None):
		_validate_array_list(list,self.type)
		return super().__init__(list)
		
	def to_kv2(self):
		global _kv2_indent
		
		if len(self) == 0:
			return "[ ]"
		if self.type == Element:
			out = "\n{}[\n".format(_get_kv2_indent())
			_kv2_indent += 1
		else:
			out = "[ "
		
		for i,item in enumerate(self):
			if i > 0: out += ", "
			if self.type == Element:				
				if i > 0: out += "\n"
				if item._users == 1:
					out += _get_kv2_indent() + item._get_kv2_str()
				else:
					out += "{}{} {}".format(_get_kv2_indent(),_quote("element"),_quote(item.id))				
			else:
				out += _quote(_get_kv2_repr(item))
		
		if self.type == Element:
			_kv2_indent -= 1
			return "{}\n{}]".format(out,_get_kv2_indent())
		else:
			return "{} ]".format(out)
	
	def tobytes(self, datamodel, elem):
		return array.array(self.type_str,self).tobytes()
		
	def frombytes(self,file):
		length = get_int(file)		
		self.extend( unpack( typestr*length, file.read( calcsize(typestr) * length) ) )

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
		for item in self:out += _get_string(datamodel,item,use_str_dict=False)
		return out

class _Vector(list):
	type_str = ""
	def __init__(self,list):
		_validate_array_list(list,float)
		if len(list) != len(self.type_str):
			raise TypeError("Expected {} values".format(len(self.type_str)))
		super().__init__(list)
		
	def __repr__(self):
		out = ""
		for i,ord in enumerate(self):
			if i > 0: out += " "
			out += _get_kv2_repr(ord)
			
		return out
	
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
	attributes = {}
	datamodel = None
	
	def __init__(self,datamodel,name,elemtype="DmElement",id=None):
		# Blender bug: importing uuid causes a runtime exception. The return value is not affected, thankfully.
		# http://projects.blender.org/tracker/index.php?func=detail&aid=28732&group_id=9&atid=498
		import uuid
		
		if type(name) != str or type(elemtype) != str or (id and type(id) != uuid.UUID):
			raise TypeError("Expected str, [str, uuid.UUID]")
			
		self.name = name
		self.type = elemtype
		self.id = id if id else uuid.uuid4()
		
		self.attributes = {}
		self.attribute_order = []
		
	def __repr__(self):
		return "<Datamodel element {}[{}]>".format(self.type,self.name)
		
	def add_attribute(self,name,value,prop_type = None):
		t = type(value)
		if self.attributes.get(name):
			raise ValueError("Attribute \"{}\" already exists".format(name))
		if not t in _dmxtypes_array:
			if t in _array_types and not prop_type:
				raise ValueError("A datamodel type must be specified for arrays")
			if t not in _dmxtypes:
				if t in _array_types:
					if prop_type not in _dmxtypes_array: prop_type = _get_array_type(prop_type)
					value = prop_type(value)
				else:
					raise ValueError("Unsupported data type ({})".format(t))
		prop = Attribute(name,value)
		self.attributes[name] = prop
		self.attribute_order.append(name)
		
		def _import_element(elem):
			if elem.datamodel != self.datamodel:
				elem.datamodel = self.datamodel
				self.datamodel.elements.append(elem)
				for attr in elem.attributes.values():
					t = type(attr.value)
					if t == Element:
						_import_element(attr.value)
					if t == _ElementArray:
						for arr_elem in attr.value:
							_import_element(arr_elem)
		
		if t == Element:
			_import_element(value)
		elif prop_type == Element:
			for _arr_elem in value:
				_import_element(_arr_elem)
		
		return prop
	
	def get_attribute(self,name):
		return self.attributes.get(name)
	def remove_attribute(self,name):
		del self.attributes[name]
		
	def _get_kv2_str(self):
		global _kv2_indent
		out = ""
		out += _quote(self.type)
		out += "\n" + _get_kv2_indent() + "{\n"
		_kv2_indent += 1
		
		def _make_attr_str(attr, is_array = False):
			attr_str = _get_kv2_indent()
			
			for i,item in enumerate(attr):
				if i > 0: attr_str += " "
				
				if is_array and i == 2:
					attr_str += str(item)
				else:
					attr_str += _quote(item)
			
			return attr_str + "\n"
		
		out += _make_attr_str([ "id", "elementid", self.id ])
		out += _make_attr_str([ "name", "string", self.name ])
		
		for attr_name in self.attribute_order:
			attr = self.attributes[attr_name]
			t = type(attr.value)
			
			if t == Element and attr.value._users == 1:
				out += _get_kv2_indent()
				out += _quote(attr.name)
				out += " {}".format( attr.value._get_kv2_str() )
				out += "\n"
			else:				
				if issubclass(t,_Array):
					if t == _ElementArray:
						type_str = "element_array"
					else:
						type_str = _dmxtypes_str[_dmxtypes_array.index(t)] + "_array"
				else:
					type_str = _dmxtypes_str[_dmxtypes.index(t)]
				
				out += _make_attr_str( [
					attr.name,
					type_str,
					_get_kv2_repr(attr.value)
				], issubclass(t,_Array) )
		_kv2_indent -= 1
		out += _get_kv2_indent() + "}"
		return out

class _ElementArray(_Array):
	type = Element
	def tobytes(self, datamodel, elem):
		out = []
		for item in self:
			out.append(datamodel.elem_chain.index(item))
		return array.array("i",out).tobytes()

_dmxtypes = [Element,int,float,bool,str,Binary,Time,Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix]
_dmxtypes_array = [_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,_TimeArray,_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray]
_dmxtypes_str = ["element","int","float","bool","string","binary","time","color","vector2","vector3","vector4","angle","quaternion","matrix"]

attr_list_v1 = [
	None,Element,int,float,bool,str,Binary,"ObjectID",Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix,
	_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,"_ObjectIDArray",_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray
] # ObjectID is an element UUID
attr_list_v2 = [
	None,Element,int,float,bool,str,Binary,Time,Color,Vector2,Vector3,Vector4,Angle,Quaternion,Matrix,
	_ElementArray,_IntArray,_FloatArray,_BoolArray,_StrArray,_BinaryArray,_TimeArray,_ColorArray,_Vector2Array,_Vector3Array,_Vector4Array,_AngleArray,_QuaternionArray,_MatrixArray
]

def _get_type_from_string(type_str):
	return _dmxtypes[_dmxtypes_str.index(type_str)]
def _get_array_type(single_type):
	if single_type in _dmxtypes_array: raise ValueError("Argument is already an array type")
	return _dmxtypes_array[ _dmxtypes.index(single_type) ]
def _get_single_type(array_type):
	if array_type in _dmxtypes: raise ValueError("Argument is already a single type")
	return _dmxtypes[ _dmxtypes_array.index(array_type) ]

def _get_dmx_id_type(encoding,version,id):	
	if encoding == "binary":
		if version in [2]:
			return attr_list_v1[id]
		if version in [5]:
			return attr_list_v2[id]
	if encoding == "keyvalues2":
		if version == 1:
			return attr_list_v1[id]
		if version in [2]:
			return attr_list_v2[id]
				
	raise ValueError("Type {} not supported in {} {}".format(type,encoding,version))
	
def _get_dmx_type_id(encoding,version,type):	
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
		elem = Element(self,name,elemtype,id)
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
			raise Error("Don't write elements as attributes")
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
			prop = elem.attributes[name]
			t = type(prop.value)
			if t == Element and prop.value not in self.elem_chain:
				self._write_element_index(prop.value)
			if t == _ElementArray:
				for i in prop.value:
					if i not in self.elem_chain:
						self._write_element_index(i)
		
	def _write_element_props(self):		
		for elem in self.elem_chain:
			self._write(len(elem.attributes))
			for prop_name in elem.attribute_order:
				prop = elem.attributes[prop_name]
				self._write(prop_name)
				self._write(struct.pack("b", prop.typeid(self.encoding,self.encoding_ver) ))
				if type(prop.value) == Element:
					self._write(self.elem_chain.index(prop.value),elem)
				else:
					self._write(prop.value,elem)
		
	def _build_str_dict(self,elem):
		self.str_dict.add(elem.name)
		self.str_dict_checked.append(elem)
		self.str_dict.add(elem.type)
		for name in elem.attribute_order:
			prop = elem.attributes[name]
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
	
	def echo(self,encoding,encoding_ver):
		check_support(encoding, encoding_ver)
		
		if encoding == "binary":
			self.out = io.BytesIO()
		else:
			self.out = io.StringIO()
		
		self.encoding = encoding
		self.encoding_ver = encoding_ver
		
		global header_format
		header = header_format.format(encoding,encoding_ver,self.format,self.format_ver)
		if self.encoding == 'binary':
			self.out.write( bytes(header,'ASCII') + bytes(1))
		elif self.encoding == 'keyvalues2':
			self.out.write(header)
		
		if encoding == 'binary':
			# string dictionary
			self.str_dict = set()
			self.str_dict_checked = []
			self._build_str_dict(self.root)
			self.str_dict = list(self.str_dict)
			
			self._write(len(self.str_dict))
			for i in self.str_dict:
				self._write(i,use_str_dict = False)
			
		# count elements
		out_elems = []
		for elem in self.elements:
			elem._users = 0
		def _count_child_elems(elem):
			out_elems.append(elem)
			for name in elem.attribute_order:
				prop = elem.attributes[name]
				t = type(prop.value)
				if t == Element:
					if prop.value not in out_elems:
						_count_child_elems(prop.value)
					prop.value._users += 1
				elif t == _ElementArray:
					for i in prop.value:
						if i not in out_elems:
							_count_child_elems(i)
						i._users += 1
		_count_child_elems(self.root)
		
		if self.encoding == 'binary':
			self._write(len(out_elems))
			self.elem_chain = []
			self._write_element_index(self.root)
			self._write_element_props()
		elif self.encoding == 'keyvalues2':
			self.out.write(self.root._get_kv2_str() + "\n\n")
			for elem in out_elems:
				if elem._users > 1:
					self.out.write(elem._get_kv2_str() + "\n\n")
				
		return self.out.getvalue()
		
	def write(self,path,encoding,encoding_ver):		
		file = open(path,'wb' if encoding == "binary" else 'w')
		try:		
			file.write(self.echo(encoding,encoding_ver))
		finally:
			file.close()

def parse(parse_string, element_path=None):
	return load(in_file=io.StringIO(parse_string),element_path=element_path)

def load(path = None, in_file = None, element_path = None):
	if not (path or in_file):
		raise ArgumentError("A path or a file must be provided")
	if element_path != None and type(element_path) != list:
		raise TypeError("element_path must be a list containing element names")
	if not in_file:
		in_file = open(path,'rb')
	
	try:
		import re, uuid
		global header_format
		pattern = header_format[:]
		pattern = pattern.replace("{:d}","([0-9]+)")
		pattern = pattern.replace("{:s}","(\S+)")
		
		header = ""
		while True:
			header += get_char(in_file)
			if header.endswith("\n"): break
		matches = re.findall(pattern,header)
		if len(matches) != 1 or len(matches[0]) != 4:
			raise Exception("Could not read DMX header")
		encoding,encoding_ver, format,format_ver = matches[0]
		encoding_ver = int(encoding_ver)
		format_ver = int(format_ver)
		
		check_support(encoding,encoding_ver)		
		dm = DataModel(format,format_ver)
		
		global max_elem_path
		max_elem_path = len(element_path) + 1 if element_path else 0
		
		if encoding == 'keyvalues2':
			def parse_line(line):
				return re.findall("\"(.*?)\"",line.strip("\n\t ") )
				
			def read_element(elem_type):
				id = None
				name = None
				
				def read_value(name,type_str,kv2_text, index=-1):
					if type_str == 'element':
						if not kv2_text:
							return None
						user_info = [element_chain[-1], name, index]
						if not element_users.get(kv2_text):
							element_users[kv2_text] = [user_info]
						else:
							element_users[kv2_text].append(user_info)
						return dm.add_element("Missing element",id=uuid.UUID(hex=kv2_text))
					
					if type_str == 'string': return kv2_text
					elif type_str == 'int': return int(kv2_text)
					elif type_str == 'float': return float(kv2_text)
					elif type_str == 'bool': return bool(int(kv2_text))
					elif type_str == 'time': return Time(kv2_text)
					elif type_str.startswith('vector') or type_str in ['color','quaternion','angle']:
						return _get_type_from_string(type_str)( [float(i) for i in kv2_text.split(" ")] )
				
				for line_raw in in_file:
					if line_raw.strip("\n\t, ").endswith("}"):
						#print("{}- {}".format('\t' * (len(element_chain)-1),element_chain[-1].name))
						return element_chain.pop()
					
					line = parse_line(line_raw)
					if len(line) == 0:
						continue
					
					if line[0] == 'id': id = uuid.UUID(hex=line[2])
					elif line[0] == 'name': name = line[2]
					
					# don't read elements outside the element path
					if max_elem_path and name and len(dm.elements):
						if len(element_path):
							skip = name.lower() != element_path[0].lower()
						else:
							skip = len(element_chain) < max_elem_path
						if skip:
							child_level = 0
							for line_raw in in_file:
								if "{" in line_raw: child_level += 1
								if "}" in line_raw:
									if child_level == 0: return
									else: child_level -= 1
							return
						elif len(element_path):
							del element_path[0]
					
					if id and name:
						element_chain.append(dm.add_element(name,elem_type,id))
						#print("{}+ {}".format('\t' * (len(element_chain)-1),element_chain[-1].name))
						users = element_users.get(str(id))
						if users:
							for user_info in users:
								attr = user_info[0].get_attribute(user_info[1])
								if user_info[2] == -1:
									attr.value = element_chain[-1]
								else:
									attr.value[ user_info[2] ] = element_chain[-1]
						id = name = None
						continue
					
					if len(line) >= 2:
						if line[1] == "element_array":
							arr_name = line[0]
							arr = []
							
							if "[" not in line_raw: # immediate "[" means and empty array; elements must be on separate lines
								for line in in_file:
									if "[" in line: continue
									if "]" in line: break
									line = parse_line(line)
									
									if len(line) == 1:
										arr.append( read_element(line[0]) )
									elif len(line) == 2:
										arr.append( read_value(arr_name,"element",line[1],index=len(arr)) )								
							
							element_chain[-1].add_attribute(arr_name,arr,Element)							
							continue
						
						elif line[1].endswith("_array"):
							arr_name = line[0]
							arr_type_str = line[1].split("_")[0]
							arr_type = _get_type_from_string(arr_type_str)
							arr = []
							
							if "[" in line_raw: # one-line array
								for item in line[2:]:
									arr.append(read_value(arr_name,arr_type_str,item))
								element_chain[-1].add_attribute(arr_name,arr,arr_type)
								
							else: # multi-line array
								for line in in_file:
									if "[" in line:
										continue
									if "]" in line:
										element_chain[-1].add_attribute(arr_name,arr,arr_type)
										break
										
									line = parse_line(line)									
									arr.append(read_value(arr_name,arr_type_str,line[0]))
						
						elif len(line) == 2: # inline element
							elem = read_element(line[1])
							if elem:
								element_chain[-1].add_attribute(line[0],elem)
						elif len(line) == 3: # ordinary attribute or element ID
							attr_value = read_value(line[0],line[1],line[2])
							if attr_value != None:
								element_chain[-1].add_attribute(line[0],attr_value)

				raise IOError("Unexpected EOF")
			
			
			in_file.close()
			in_file = open(path,'r')
			in_file.seek(len(header))
			
			element_chain = []
			element_users = {}
			for line in in_file:
				line = parse_line(line)
				
				if len(line) == 0: continue
				
				if len(element_chain) == 0 and len(line) == 1:
					read_element(line[0])
				
		elif encoding == 'binary':
			in_file.seek(1,1) # skip header's null terminator
			
			# string dictionary			
			string_dict = []
			def get_str_with_dict():			
				try:
					return string_dict[get_int(in_file)]
				except:
					in_file.seek(intsize,1)
					return get_str(in_file)
			
			dict_len = get_int(in_file)
			for i in range(dict_len):
				string_dict.append(get_str())
			num_elements = get_int(in_file)
			
			# element headers
			for i in range(num_elements):
				elemtype = get_str_with_dict()
				name = get_str_with_dict()
				id = uuid.UUID(binascii.hexlify(in_file.read(16)).decode('ASCII'))
				dm.add_element(name,elemtype,id)
				
			# attributes
			def get_value(attr_type):
				if attr_type in _dmxtypes_array:	attr_type = _get_single_type(attr_type)
				
				if attr_type == Element:	return dm.elements[get_int(in_file)]
					
				elif attr_type == str:		return get_str_with_dict()
				elif attr_type == int:		return get_int(in_file)
				elif attr_type == float:	return get_float(in_file)
				elif attr_type == bool:		return get_bool(in_file)
					
				elif attr_type == Vector2:		return Vector2(get_vec(in_file,2))
				elif attr_type == Vector3:		return Vector3(get_vec(in_file,3))
				elif attr_type == Angle:		return Angle(get_vec(in_file,3))
				elif attr_type == Vector4:		return Vector4(get_vec(in_file,4))
				elif attr_type == Quaternion:	return Quaternion(get_vec(in_file,4))
				elif attr_type == Color:		return Color(get_vec(in_file,4))
					
				elif attr_type == Time:		return get_int(in_file) / 10000
				
			for elem in dm.elements:
				num_attributes = get_int(in_file)
				for i in range(num_attributes):
					name = get_str_with_dict()
					attr_type = _get_dmx_id_type(encoding,encoding_ver,get_byte(in_file))
					
					if attr_type in _dmxtypes:
						elem.add_attribute(name,get_value(attr_type))
					elif attr_type in _dmxtypes_array:
						array_len = get_int(in_file)
						arr = elem.add_attribute(name,[],attr_type).value
						for x in range(array_len):
							arr.append( get_value(attr_type) )
					
		return dm
	finally:
		in_file.close()
