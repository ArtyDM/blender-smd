#  Copyright (c) 2013 Tom Edwards contact@steamreview.org
#
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

import bpy, io
from .utils import *

class SMD_MT_Updated(bpy.types.Menu):
	bl_label = "SMD Tools update"
	def draw(self,context):
		self.layout.operator("wm.url_open",text="View changes?",icon='TEXT').url = "http://code.google.com/p/blender-smd/wiki/Changelog"

updater_supported = True
try:
	import urllib.request, urllib.error, xml.parsers.expat, zipfile
except:
	updater_supported = False

class SmdToolsUpdate(bpy.types.Operator):
	bl_idname = "script.update_smd"
	bl_label = "Check for SMD Tools updates"
	bl_description = "Connects to https://code.google.com/p/blender-smd/"
	
	@classmethod
	def poll(self,context):
		return updater_supported

	def execute(self,context):	
		print("SMD Tools update...")
		
		import sys
		self.cur_version = sys.modules.get(__name__.split(".")[0]).bl_info['version']
		
		self.cur_entry = \
		self.result = None
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
			feed = urllib.request.urlopen("https://code.google.com/feeds/p/blender-smd/downloads/basic")
			parser = xml.parsers.expat.ParserCreate()
			parser.StartElementHandler = startElem
			parser.EndElementHandler = endElem

			parser.Parse(feed.read())
			
		except urllib.error.URLError as err:		
			self.report({'ERROR'},"Could not complete download: " + str(err))
			return {'CANCELLED'}
		except xml.parsers.expat.ExpatError as err:
			print(err)
			self.report({'ERROR'},"Version information was downloaded, but could not be parsed.")
			print(feed.read())
			return {'CANCELLED'}
		except zipfile.BadZipfile:
			self.report({'ERROR'},"Update was downloaded, but was corrupt")
			return {'CANCELLED'}
		except IOError as err:
			self.report({'ERROR'},"Could not install update: " + str(err))
			return {'CANCELLED'}
	
		if self.result == 'INCOMPATIBLE':
			self.report({'ERROR'},"The latest SMD Tools require Blender {}. Please upgrade.".format( PrintVer(self.cur_entry['bpy']) ))
			return {'FINISHED'}
		elif self.result == 'LATEST':
			self.report({'INFO'},"The latest SMD Tools ({}) are already installed.".format( PrintVer(self.cur_version) ))
			return {'FINISHED'}

		elif self.result == 'SUCCESS':
			ops.script.reload()
			self.report({'INFO'},"Upgraded to SMD Tools {}!".format(self.remote_ver_str))
			ops.wm.call_menu(name="SMD_MT_Updated")
			return {'FINISHED'}

		else:
			print("Unhandled error!")
			print(self.result)
			print(self.cur_entry)
			assert(0) # unhandled error!
			return {'CANCELLED'}

	def update(self):
		self.cur_entry = None

		for entry in self.rss_entries:
			remote_ver = entry['version']
			remote_bpy = entry['bpy']
			stable_api = (2,58,0)
			for i in range(min( len(remote_bpy), len(bpy.app.version) )):
				if int(remote_bpy[i]) > stable_api[i] and int(remote_bpy[i]) > bpy.app.version[i]:
					remote_ver = None

			if not remote_ver:
				if not self.cur_entry:
					self.result = 'INCOMPATIBLE'
			else:
				for i in range(min( len(remote_ver), len(self.cur_version) )):
					try:
						diff = int(remote_ver[i]) - int(self.cur_version[i])
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
		
		# Added dots support with 1.1 to avoid any future collisions between 1.0.1 and 10.1 etc.
		url_template = "https://blender-smd.googlecode.com/files/io_smd_tools-{}.zip"
		url_dots = url_template.format( PrintVer(self.cur_entry['version'],sep=".") )
		url = url_template.format( PrintVer(self.cur_entry['version'],sep="") )
		
		print("Found new version {}, downloading from {}...".format(self.remote_ver_str, url_dots))

		# we are already in a try/except block, any unhandled failures will be caught
		try:
			zip = urllib.request.urlopen(url_dots)
		except:
			zip = urllib.request.urlopen(url)
		zip = zipfile.ZipFile( io.BytesIO(zip.read()) )
		zip.extractall(path=os.path.dirname( os.path.abspath( __file__ ) ))
		self.result = 'SUCCESS'
		return
