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
	"author": "Tom Edwards, EasyPickins",
	"version": "0.7.1b",
	"blender": (2, 5, 4),
	"category": "Import/Export",
	"location": "File > Import/Export; Properties > Scene/Armature",
	"wiki_url": "http://developer.valvesoftware.com/wiki/Blender_SMD_Tools",
	"tracker_url": "http://developer.valvesoftware.com/wiki/Talk:Blender_SMD_Tools",
	"description": "Importer and exporter for Valve Software's Studiomdl Data format."}

try:
	init_data
	reload(smd_utils)
	reload(smd_import)
	reload(smd_export)
	reload(smd_test_suite)
except:
	from io_smd_tools import smd_utils
	from io_smd_tools import smd_import
	from io_smd_tools import smd_export
	from io_smd_tools import smd_test_suite

init_data = True

def register():
	smd_import.register()
	smd_export.register()
	smd_test_suite.register()

def unregister():
	smd_import.unregister()
	smd_export.unregister()
	smd_test_suite.unregister()

if __name__ == "__main__":
    register()
