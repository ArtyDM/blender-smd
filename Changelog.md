## SMD Tools 1.9.2 - November 6th, 2013 ##

General:

  * Added support for DMX binary 4 (L4D2)
  * Fixed DMX binary 3 animations
  * Fixed DMX model 11 animations

Importer:

  * SMD: Shape names are now imported from VTA file comments

## SMD Tools 1.9.1 - November 5th, 2013 ##

General:

  * Added DMX version information for TF2

Importer:

  * Added support for SMDs which provide blank material names

Exporter:

  * Fixed a possible DMX element ID collision

## SMD Tools 1.9.0 - September 26th, 2013 ##

General:

  * Added "Launch HLMV" operator (requires SDK Path to be set)
  * Export Path text box is now highlighted red when empty

Importer:

  * DMX: improved weightmap import performance
  * DMX: fixed importing empty animations

Exporter:

  * SMD: Worked around crash in the SMD->DMX conversion of Dota 2's model importer
  * DMX: Wrinkle maps are now auto-generated; set a non-zero wrinkle scale in your flex controller DMX to activate
  * DMX: Flex controller generator now works for objects which aren't in a Group
  * DMX: Don't generate flex controllers for corrective shapes
  * DMX: Fixed flat-shaded polygon export
  * DMX: Fixed exporting Groups with multiple texture names
  * Fixed post-export error if export was started from paint mode

## SMD Tools 1.8.6 - September 6th, 2013 ##

Exporter:

  * DMX: fixed per-face "Shade Smooth" setting not being applied to exports
  * Fixed exporting face images with relative filepaths
  * Empty Groups no longer cause the export process to cancel

## SMD Tools 1.8.5 - August 4th, 2013 ##

Exporter:

  * Display an error if the scene is unconfigured telling users about the Scene Properties panel (there are now multiple settings to configure)
  * Fixed export error if there is no active object
  * DMX: Fixed exporting Text and Curve objects
  * DMX: Fixed polygon corruption in compiled Text objects (Studiomdl does not support concave polygons)

## SMD Tools 1.8.4 - July 25rd, 2013 ##

General:

  * Fixed installing the addon in Blender 2.68

Exporter:

  * Fixed objects with Bone Parents being exported with the wrong rotations (possibly a Blender 2.68 bug)
  * Fixed exporting objects parented to other objects with Bone Parents
  * Fixed exporting armatures with parents
  * Fixed armature scale being applied twice to animation frames
  * Warn user when an armature has non-uniform scale
  * Fixed animations not being exported to the "anims" subfolder by default
  * Replace "Sdk" with "SDK" in engine branch names

## SMD Tools 1.8.3 - July 23rd, 2013 ##

Datamodel.py:

  * Fixed writing string attribute values in binary DMX 3 and below (material names)
  * Improved binary DMX array writing

Exporter:

  * Fixed exporting when the active object is hidden
  * Fixed subdirectory of the selected Object instead of selected Group being used
  * Changed the default scene QC Path to `//*.qc`
  * Error when unable to export DMX due to configuration problem

## SMD Tools 1.8.2 - July 16th, 2013 ##

Importer:

  * Fixed importing when Blender is in background mode

Exporter:

  * Fixed exporting DMX meshes without Armatures
  * Fixed console error when changing to an unrecognised SDK


## SMD Tools 1.8.1 - July 10th, 2013 ##

General:

  * Fixed possible UI error when the number of scene exportables decreased

Importer:

  * Fixed importing individual files into a scene already containing an Armature
  * Fixed importing very, very old DMX animations which don't specify a framerate
  * Fixed errors from totally invalid VTAs never being reported
  * Improved accuracy of the VTA importer in cases where VTA basis verts aren't 100% aligned with reference mesh verts
  * Fixed importing VTAs into Y-up scenes
  * If any verts weren't matched by the VTA importer, a mesh is now created showing the user where they are

Exporter:

  * Fixed VTA exports not including basis verts
  * Fixed DMX export with Blender 2.66
  * Turned OS filesystem exceptions into user-friendly error reports
  * Fixed exporting DMX meshes with bone parents
  * Fixed console spam and UI glitches if Blender doesn't make a scene update callback

## SMD Tools 1.8 - July 3rd, 2013 ##

General:

  * Refactored the addon into a Python package. 1.8 is technically a different addon from 1.7 but the upgrade process should be transparent.

Importer:

  * Fixed importing DMX animations with sub-keyframe accuracy (Source Filmmaker)
  * Fixed importing DMX animations which aren't Z-up and have sparse keyframes
  * Fixed importing DMX model 15 animations

Exporter:

  * **NEW:** Rewrote engine branch configuration to reflect the new Source SDK layout. You must now provide a path to the binaries of your target engine branch.
  * DMX is now the default export format
  * Fixed exporting DMX model v1 and v15
  * Switched DMX version override properties to be a drop-down list of valid values instead of a user-defined number
  * It is now possible to override the system VPROJECT variable on a scene-by-scene basis for QC compiles

Datamodel.py:

  * Now uses The MIT License
  * Added support for binary 3
  * Fixed writing stub Elements in binary encodings that don't support them
  * Fixed some built-in function and type shadowing (PYTHON!!)
  * Fixed using the string dictionary for element names in binary 2
  * Fixed writing binary 1
  * Fixed loading string arrays from below binary 5

## SMD Tools 1.7 - June 4th, 2013 ##

General:

  * Added the "Generate Corrective Shape Key Drivers" operator, which adds Blender animation drivers for corrective shape keys
  * Added the "Activate Dependency Shapes" operator, which activates all shapes referred to in the name of the active shape (use to view/edit a corrective shape in its proper context)

Exporter:

  * Fixed object scale not being applied

## SMD Tools 1.6.7 - May 14th, 2013 ##

Exporter:

  * Fixed DMX export when Material Path is empty

## SMD Tools 1.6.6 - May 8th, 2013 ##

Importer:

  * DMX: fixed material name import

Exporter:

  * Fixed object rotation doing crazy things
  * DMX: fixed material name export when the scene's material path does not end with a slash

## SMD Tools 1.6.5 - March 4th, 2013 ##

Importer:

  * Fixed importing DMX files with shape keys

## SMD Tools 1.6.4 - February 22nd, 2013 ##

  * Updated to Blender 2.66. Earlier versions of Blender are no longer supported.

Exporter:

  * Improved export list UI
  * Fixed exporting a group to DMX when multiple members shared the same material
  * Improved UI behaviour when an object is a member of multiple groups

## SMD Tools 1.6.3 - December 17th, 2012 ##

General:

  * Upgraded to Blender 2.65. Previous versions of Blender are no longer supported.

Importer:

  * Fixed the up axis setting on the import screen being ignored
  * Fixed importing QC files with $pushdir
  * Fixed objects being imported with file extensions
  * Improved object selection for shape key import
  * DMX: added support for Binary v1
  * DMX: use default values if an animation does not specify an offset or scale
  * SMD: fixed animations not being importing for some bones

Exporter:

  * Fixed exporting the basis shape key twice
  * Error if the user tries to export shapes from an object with a 'Collapse' or 'Planar' Decimate modifier
  * DMX: fixed various Guid collision issues
  * DMX: fixed no animation frames being exported (am I going mad?)

## SMD Tools 1.6.2 - December 10th, 2012 ##

General:

  * Fixed importing/exporting animations

## SMD Tools 1.6.1 - December 3rd, 2012 ##

General:

  * Fixed datamodel.py move on fresh Blender profiles with no modules folder

## SMD Tools 1.6 - November 29th, 2012 ##

General:

  * Added code to move datamodel.py from the "addons" folder to "modules". This should help with the tools being impossible to enable.

Importer:

  * DMX: Rewrote importer in Python. DMX-Model is no longer required.

Exporter:

  * Fixed Blender undoing too far when exporting from edit mode.
  * DMX: datamodel element IDs are now based on relevant Blender object names instead of being random. This is better for source control.
  * DMX: flex controllers can now be loaded from binary DMX files.

## SMD Tools 1.5.2 - September 29th, 2012 ##

Importer:

  * Handle implicit SMD bones (like the ones the exporter creates...)

Exporter:

  * Armature properties panel now shows up when selecting an object with an armature modifier

## SMD Tools 1.5.1 - September 5th, 2012 ##

Fixed the tools not starting on systems without the Source SDK.

## SMD Tools 1.5 - September 3rd, 2012 ##

Importer:

  * Removed code that tried to preserve long names, as Blender no longer limits them to 29 characters
  * Fixed warnings when an SMD starts with comments or blank lines (Dota 2 heroes)

Exporter:

  * Updated UI. Moved all the scattered object/data panels into Scene Properties.
  * DMX: Added advanced flex controller configuration which inserts the controllers of another DMX File
  * DMX: Added an operator to generate a template flex controller DMX
  * DMX: wrinkle map vertex groups no longer start with "wrinkle"; they are now just the name of the shape key
  * DMX: added support for flex controller stereo split


## SMD Tools 1.4.2 - August 26th, 2012 ##

Exporter:

  * SMD: fixed bone parent export when there is more than one bone

## SMD Tools 1.4.2 - August 20th, 2012 ##

Exporter

  * Fixed exporting objects without armatures
  * The exporter no longer leaves the scene in a huge mess if it fails

## SMD Tools 1.4.1 - August 18th, 2012 ##

Exporter:

  * DMX: added support for bone parents/constraints, bone envelopes, and implicit motionless bones
  * DMX: added simple wrinkle map export (make a vertex group called "wrinkle <shape name>")
  * DMX: enabled export for Source MP and Alien Swarm
  * SMD: fixed Blender crash when exporting a scene containing shapes
  * Worked around Blender remembering the "path" and "group index" properties between executions
  * Fixed exporting 2D curves
  * Fixed exporting multi-user meshes
  * SMD: fixed implicit bones
  * Fixed bone envelope export from scaled armatures
  * SMD: fixed export of objects with subsurf

## SMD Tools 1.4 - August 13th, 2012 ##

A problem with official builds of Blender leads to a "runtime error" the first time you export a DMX file. The error is harmless and can be ignored. See [issue 43](https://code.google.com/p/blender-smd/issues/detail?id=43).

Importer:

  * Fixed QC flex name import when flex frames weren't sequential (HL2 citizen SDK sample)

Exporter:

  * Added DMX export for mesh, flex, and animation
  * DMX Model is NOT required for export
  * No support for any DMX-specific features yet
  * Portal 2 and Source Filmmaker only for now
  * Due to a Blender bug, you will receive a harmless runtime error the first time you export a DMX file
  * Optimised the export process in general

## SMD Tools 1.3.1 - August 1st, 2012 ##

Exporter:

  * Fixed an error when exporting a model without any animation.

## SMD Tools 1.3 - July 28th, 2012 ##

Importer:

  * Added DMX shape key import
  * Fixed back-to-back faces being destroyed by Blender (running Remove Doubles will still destroy them, watch out)
  * DMX Model 0.3 is now required to import DMX models
  * Improved post-import 3D View camera and grid fixup
  * Fixed keyframe handles all being at (0,0,0)
  * Y-up DMX objects no longer start with unapplied rotations
  * Newly-imported objects are now always selected when the script finishes
  * Fixed QC flex names being applied to the wrong shape keys
  * Fixed importing DMX animations when the armature was not already the active object
  * Added support for Action Libraries (not supported by official Blender builds)
  * Added support for per-Action framerates (not supported by official Blender builds)

Exporter:

  * Added Source Filmmaker as a target engine
  * Fixed exporting Y-up shape keys
  * Curve object polygon generation options now work again
  * Fixed exporting non-mesh objects
  * Fixed exporting while a blank text block was open
  * Lots of code refactoring (6K smaller!) now that I can undo from within the script
  * The export operator no longer shows up in the Tool Shelf after it runs

## SMD Tools 1.2.6 - June 12th, 2012 ##

Importer:

  * No longer chokes on SMD comments
  * Re-enabled QC flex name import

## SMD Tools 1.2.5 - May 31st, 2012 ##

Exporter:

  * Fixed a bug when exporting objects with Armature modifiers. The error was handled incorrectly by Blender, leading to intermittent crashes.

## SMD Tools 1.2.4 - May 28th, 2012 ##

Exporter:

  * Fixed exporting shapes from objects with shape key pinning disabled
  * Promoted the skipping of muted shape keys to a warning
  * Fixed the object name written in VTA file comments

## SMD Tools 1.2.3 - May 13th, 2012 ##

General:

  * Fixed updater (a debug test had been left in)
  * Fixed Scene Properties display when an Armature action filter is in use

## SMD Tools 1.2.2 - May 4th, 2012 ##

Exporter:

  * Fixed and greatly optimised shape key export

## SMD Tools 1.2.1 - April 29th, 2012 ##

Exporter:

  * Fixed error when exporting a UV mapped mesh

## SMD Tools 1.2 - April 28th, 2012 ##

General:

  * Upgraded to Blender 2.63 and the new BMesh system. Previous versions of Blender are no longer supported.
  * Added compatibility with debug builds of Blender, which don't have the full array of Python features

Importer:

  * DMX faces with more than four edges are no longer split up (BMesh)
  * Fixed importing DMX animations onto a hidden Armature
  * Rewrote shape key import to work with disconnected faces, and in future with DMX

Exporter:

  * The exporter now uses the UV map which is active in 3D View (had been using the one active for rendering)
  * Now displays the active vproject for QC compiles
  * Replaced "invalid path" error message with an alert highlight over the QC path box
  * No longer tries to Smart Project UV-less meshes of over 2000 vertices (too slow)
  * Verts of imported meshes no longer start out selected
  * Improved the way modifiers are applied

## SMD Tools 1.1.7 - February 3rd, 2012 ##

Exporter:

  * Now falls back on face-assigned texture filenames if no material is found
  * Now writes out the names of all materials written to an SMD

## SMD Tools 1.1.6 - January 30th, 2012 ##

General:

  * Fixed a couple of errors in the Clean SMD Data operator

Importer:

  * Fixed QCs imported into a scene with an armature latching onto it instead of creating their own, often generating errors

Exporter:

  * Now prints the location of each output file to the console

## SMD Tools 1.1.5 - October 21st, 2011 ##

General:

  * Updated to Blender 2.60. Previous versions of Blender will no longer work.

Exporter:

  * Added QC compile support for the new Source MP/2009 engine branches.

## SMD Tools 1.1.4 - September 14th, 2011 ##

General:

  * Added a help link to the Scene Properties panel

Importer:

  * Fixed an error when importing QCs with animations

## SMD Tools 1.1.3 - September 4th, 2011 ##

Exporter:

  * Fixed armature scale being applied twice to root bones

## SMD Tools 1.1.2 - September 3rd, 2011 ##

Importer:

  * Fixed rest pose being oriented incorrectly on Y-up meshes

Exporter:

  * Fixed exporting objects with negative scale

## SMD Tools 1.1.1 - August 19th, 2011 ##

Exporter:

  * Now disables auto-keyframing before messing around with bones (prevents animation destruction!)

## SMD Tools 1.1 - August 17th, 2011 ##

General:

  * Upgraded to Blender 2.59.
  * This release changes the way that bones are imported and exported. Previously the difference between Blender's Y-up and Source's Z-up bones was accounted for, but this led to compatibility problems with other modelling software and was generally confusing. Bones are now imported exactly as they are arranged in the SMD/DMX file.
  * Added a "legacy rotations" option to Armature Properties for users who run into trouble with the new bone code.
  * Avoided future problems with the updater (1.0.1 and 10.1 would have been the same file).
  * Fixed version enforcer error.

Importer:

  * Rewrote bone import. Much faster and much simpler!
  * Worked around Blender hang when importing long bone names, for real this time.
  * Added support for SMDs which don't define the position of every bone every frame.
  * You can now choose whether you want quaternion or euler bone rotations (euler is default).
  * Fixed DMX phys meshes being imported with flat shading (smooth is required for export).

Exporter:

  * Rewrote bone export, again faster and simpler.
  * When the export of a group is disabled, its objects are no longer returned to the list of individual objects. To have the SMD Tools ignore a group altogether use the new controls in Properties > Object > Groups.
  * Gave object/group names more space in UI.
  * The list of Group objects can now be expanded and collapsed.
  * Fixed objects with negative scale having inverted normals.
  * Removed some console debug spam.

## SMD Tools 1.0.2 - July 9th, 2011 ##

Exporter:

  * Fixed rotated and scaled+translated armatures being exported incorrectly

## SMD Tools 1.0.1 - July 8th, 2011 ##

General:

  * Removed pointless extended descriptions for axes and engine branches, and other minor UI tweaks

Importer:

  * Fixed importing DMX UV maps with Blender 2.58
  * No longer tries to connect bones. This was a crap feature, as animations may want to translate at any time!
  * Fixed bone names containing '.' losing earlier characters (that behaviour is intended for "ValveBiped." only)
  * Support for broken SMDs with no material names

Exporter:

  * Fixed Armature scale not being applied to exported animations
  * Fixed Armature action filter not applying during whole scene export
  * If a QC is open in Blender, it will now be saved before being run (to open one, turn the file extension filter off)
  * Fixed long object names being changed on export
  * Added smd\_name support to objects and actions
  * Tweaked the way that numbers are written to increase SMD readability

## SMD Tools 1.0 - June 24th, 2011 ##

The SMD Tools are more or less feature complete (DMX export isn't viable right now) and have proven themselves stable so, after well over 50 releases, **welcome to 1.0!**

General:

  * Updated to Blender 2.58 API. 2.57 is no longer supported.
  * Info reports are fixed in 2.58; started using them again
  * Changed the import and export operators' internal names to fit Blender's tweaked naming scheme

Importer:

  * Fixed DMX physics meshes not receiving wireframe highlight

Exporter:

  * Fixed exporting objects with vertices that have zero weight but are somehow still associated with bones (Blender bug?)

## SMD Tools 0.15.10 - May 29th, 2011 ##

Exporter:

  * Fixed exporting objects with faces assigned to empty material slots

## SMD Tools 0.15.9 - May 21st, 2011 ##

Exporter:

  * Fixed whole-scene exports when a group contains an armature or a non-exportable object
  * Fixed trying to compile on export when the QC path is blank

## SMD Tools 0.15.8 - May 11th, 2011 ##

Importer:

  * Collision meshes imported from a QC now have a wireframe overlay instead of being flat shaded (smoothing is required for concave collision meshes to compile properly)

Exporter:

  * Added Portal 2 compile support

## SMD Tools 0.15.7 - April 28th, 2011 ##

Importer:

  * Fixed DMX import with long material names

Exporter:

  * Fixed writing invalid SMDs in cases of long material names

## SMD Tools 0.15.6 - April 11th, 2011 ##

General:

  * Fixed version validation failing in some Blender builds
  * Added a console message for downloading DMX-Model if a DMX is encountered without it

## DMX-Model 0.2 - April 7th, 2011 ##

  * KeyValues2 support. All TF2 models can now be imported.
  * Fixed importing bones with "foreign objects" as children
  * Fixed not importing DmeDag bones (are they any different from DmeJoint?)
  * Fixed mesh transforms never being written out
  * Fixed handling of animations that don't define a framerate (by assuming 30fps)

## SMD Tools 0.15.5 - April 7th, 2011 ##

General:

  * Fixed large UI gaps when a group or armature was filtered from the Scene Exports list

Importer:

  * Fixed infinite recursion when a file was missing
  * Fixed not storing long bone names
  * Fixed importing DMX materials without a folder
  * Fixed importing DMX animations that don't define every bone
  * Fixed Y-up SMD meshes being in outdated positions until the user caused them to update
  * Fixed importing pure animation QCs
  * Fixed $definemacro by ignoring it (for now at least)
  * Fixed trying to import $animation names when appearing in a $sequence
  * Fixed hidden armatures becoming visible after DMX import

## 0.15.4 - April 6th, 2011 ##

General:

  * Relaxed Blender version checking, as now we are into RCs the addon API should be stable.

Importer:

  * Fixed importing DMX materials without a folder
  * Fixed importing DMX animations that don't define every bone

## 0.15.3 - April 5th, 2011 ##

Exporter:

  * Fixed exporting Y-up armatures

## 0.15.2 - April 5th, 2011 ##

Importer:

  * Fixed importing SMD skeletons
  * Fixed importing materials with long names

## 0.15.1 - April 3rd, 2011 ##

General:

  * Fixed auto updater, again

Exporter:

  * Fixed exporting objects without UV maps

## 0.15 - March 31st, 2011 ##

General:

  * Updated for Blender 2.57
  * Promoted important info reports to errors, due to presumed Blender bug that hides info and warning reports

DMX-Model:

  * Initial commit. Requires Alien Swarm Tier0.dll, but not Steam.

Importer:

  * New feature: DMX mesh, skeleton, attachment and animation import. This requires a separate download. KeyValues2 encoding is not supported, which leads to oddness with all the TF2 models except Pyro!
  * Fixed $definevariable case issues
  * Up axis now defaults to the scene's target axis

Exporter:

  * Greatly optimised shape key export (>200% faster)

## 0.14.3 - March 13th, 2011 ##

General:

  * Fixed the updater (sigh)

## 0.14.2 - March 13th, 2011 ##

Importer:

  * LODs and collision meshes are now imported to separate layers, which all start active
  * Improved recognition of QC variables (e.g. blah$var$blah)

Exporter:

  * Fixed per-face and per-object smooth/flat setting being ignored
  * Names of face textures (assigned when UV mapping) can now be set to override names of materials
  * The list of objects to export can now be restricted to active scene layers
  * The UI now shows which engine branch a QC was compiled with

## 0.14.1 - March 6th, 2011 ##

General:

  * Scene properties: groups now display their member objects in two columns

Exporter:

  * Fixed being unable to export objects in disabled groups
  * Fixed objects in inactive layers being marked hidden after export
  * Groups: shape keys with the same name are now merged together
  * If no QCs are found, try adding ".qc" to the search path

## 0.14 - March 5th, 2011 ##

General:

  * Items in Scene Configuration are now sorted by name

Exporter:

  * **New feature:** Added wildcard support to QC paths, for batch compiles
  * QCs can now be compiled at any time (individually or all at once)
  * Fixed exporting meshes with hidden vertices
  * Number of SMDs/QCs to export/compile is now shown in scene properties

## 0.13.3 - March 5th, 2011 ##

General:

  * Groups now start with combined SMD export enabled
  * Fixed errors and warnings appearing twice in the console
  * Fixed reports with warnings but not errors not being pop-ups
  * Fixed two dots appearing in action export names
  * Improved support for case-sensitive filesystems

Exporter:

  * **New feature:** support for parent bones and constraints to bones.
  * Improved warnings when multiple envelopes are found

## 0.13.2 - March 3rd, 2011 ##

General:

  * Errors and warning descriptions are now reported in the UI (as line breaks have become possible)

Exporter:

  * Handle long object names better when labelling VTAs
  * Note in the console when skipping bones with deformation disabled

## 0.13.1 - March 2nd, 2011 ##

Exporter:

  * Fixed exporting objects without armatures
  * Fixed shape key export from groups
  * Fixed all verts being exported for each shape, not just changed ones
  * VTA files are now labelled with shape key names
  * No longer generating UVs on shape exports

## 0.13 - March 1st, 2011 ##

General:

  * The updater no longer stops looking for updates the first time it finds a candidate

Exporter:

  * **New feature:** Shapes can now be exported from meshes with modifiers, and from surfaces
  * Shapes now affect vertex normals
  * The reference mesh of an object with shapes will now always be the first shape, not whatever happens to be active
  * Fixed unkeyed poses being preserved only on bones that are selected

## 0.12.4 - February 2nd, 2011 ##

General:

  * No longer displaying full action export path in scene properties (just the name)

Exporter:

  * Fixed exporting shapes from objects with no modifiers
  * Improved error handling for QC compiles
  * Added support for long SMD filenames; make a "smd\_name" custom property. There is no GUI for this!

## 0.12.3 - January 25th, 2011 ##

General:

  * Fixed UI failure when displaying an export name
  * Switched to secure HTTP for update downloads

## 0.12.2 - January 24th, 2011 ##

General:

  * Enforce Blender version (due to confusion between 2.56 and 2.56a)
  * A link to the changelog is now offered after an update
  * Improved handling of file I/O and update errors
  * Moved the update and cleaner operators within the script to improve search results for "SMD" (imp/exp are now first)
  * Fixed rogue slashes before export target names

Importer:

  * Internal changes to prepare for DMX support (which won't come until Blender 2.57 due to 2.56 bugs)

## 0.12.1 - January 23rd, 2011 ##

_(0.12 plus hotfix)_

General:

  * New feature: update checker

Exporter:

  * UI changes to prepare for DMX support
  * Armatures no longer appear in Scene Configuration unless they have associated animation data (really this time)

## 0.11.2 - January 23rd, 2011 ##

Importer:

  * Handle reference SMDs that do not define positions for all bones
  * Warn on > 128 bones when importing too
  * Renamed operator to match searches for "QC"

Exporter:

  * Fixed "vertex\_group\_multi\_modifier" exception (what's wrong with bug reports, people?)

## 0.11.1 - January 7th, 2011 ##

Importer:

  * Fixed one final animation import regression

Exporter:

  * The active rendering UV texture is now exported, not the first

## 0.11 - January 6, 2011 ##

Importer:

  * Fixed bone import

Exporter:

  * **New feature:** support for exporting actions from NLA tracks (when the armature is playing from NLA)
  * **New feature:** armatures can now be configured to export their filtered action list by default
  * Fixed deleted actions and temporary "pose backup" actions sometimes being exported
  * Moved armatures to their own Scene Configuration section and added details of what exporting them will actually do
  * Armatures no longer appear in Scene Configuration unless they have associated actions

## 0.10.3 - December 31, 2010 ##

General:

  * Upgraded to Blender 2.56; previous versions of Blender are no longer supported

Exporter:

  * Fixed another error on exporting without an armature object active
  * Fixed error on exporting with the active object hidden
  * Fixed error on exporting an armature modifier with no associated armature object
  * No longer warn of shape key / modifier issues unless there is a non-armature modifier on the object


## 0.10.2 - December 18, 2010 ##

Importer:

  * Now ignoring animations in ref meshes (fixes cstrike\urban\_ragdoll.smd)
  * Flipped "Import SMD as new model" to "SMDs extend any existing model"
  * Fixed invalid SMD import attempts not erroring correctly
  * Importing SMDs now only changes the scene name if it's "Scene"

## 0.10.1 - December 5, 2010 ##

Exporter:

  * Fixed error on exporting animations when not in pose mode
  * Actually made unkeyed poses persist after export (still won't work in 2.55, but will in 2.56)
  * Restore active bone after export, if any
  * Tidied some log messages

## 0.10 - November 12, 2010 ##

General:

  * List warning and error messages in the console at the end of the job
  * Calculate bone positions directly, instead of sampling Blender's output

Importer:

  * Fixed importing SMDs with duplicate bone names, as they are not necessarily invalid

Exporter:

  * **New Feature:** support for Text, Metaball, Surface and Curve (when extruded) objects. _Watch your polycount!_
  * **New Feature:** support for bone envelopes and vertex group filtering on Armature modifiers
  * **New Feature:** Option to create an "implicit motionless bone" (starts on). This preserves Blender's behaviour of not deforming vertices without bones attached, but can break compatibility with existing SMDs. The extra bone will be created by Studiomdl only if needed.
  * **New Feature:** Bones with deformation disabled will no longer be exported
  * Worked around Blender bug which eventually leads to actions being lost from .blend files
  * Made the exporter undoable. Though this makes no sense at first, it suppresses undo levels from the operators it calls. This doesn't work 100% yet due to a Blender 2.55 bug.
  * Back up unkeyed poses and restore them after export. This doesn't actually work yet due to a Blender 2.55 bug.
  * Fixed objects not being exported relative to their ultimate parent's origin
  * Fixed grouped objects' armature settings being stomped on
  * Dropped support for export relative to armatures referenced in modifiers, as it is ill-defined and incompatible with group export
  * Error when user tries to export something with zero polygons


## 0.9.1 - November 8, 2010 ##

Exporter:

  * Fixed not being able to export objects that are in disabled groups
  * Now running Blender's smart project on objects without UVs

## 0.9 - November 4, 2010 ##

General:

  * Now requires Blender 2.55
  * UI error/warning message now includes how many SMDs were handled

Importer:

  * Filtered the file chooser to compatible files only (new feature in 2.55)

Exporter:

  * **New feature: Group export.** Grouped meshes can be exported to a single SMD, enabling advanced use of modifiers and datablock linking. Armatures cannot be group exported.
  * Avoided Blender's inability to apply modifiers to meshes with shape keys. The keys are now exported, just without modifiers applied.
  * Fixed exception when a vertex group on a mesh does not have a corresponding bone
  * Added a new Armature properties button to clean SMD data from its bones without also nuking everything in the scene
  * Console now specifies that shape keys are being exported, rather than a mesh

## 0.8.3 - October 29, 2010 ##

Importer:

  * Fixed issues when importing animations that leave root bones implicit
  * Fixed two-frame animations not importing correctly
  * Fixed $sequences that define both an SMD file and advanced options not being imported
  * Now importing $origin location as either a camera, for viewmodel editing, or a simple empty object, for reference. The frame is offset to account for Blender's FOV not being locked to frame resolution - _this is a hack that only works for the default FOV of 54 degrees!_
  * Give imported animations a fake user, preventing them from being removed by Blender if not active
  * Fixed DMX import attempts not generating error messages
  * Stopped warning altogether when encountering repeated SMDs

Exporter:

  * Fixed duplicate action(s) being left over after each export (Blender bug?)
  * Console now talks about the action being exported, not its armature

## 0.8.2 - October 22, 2010 ##

General:

  * Changed bug report URL to point to the Google Code issues page

Importer:

  * Fixed scene frame range being offset by +1 after importing an animation
  * Flip active frame from 1 to 0 after importing an animation

## 0.8.1 - October 9, 2010 ##

General:

  * Fixed an error when the Blender revision wasn't an integer.
  * Packaged io\_smd\_tools.py as a ZIP archive to avoid naming issues.

## 0.8 - September 30th, 2010 ##

General:

  * Cross-platform compatibility
  * Support addon unloading properly
  * Moved "Target Up Axis" property from armature to scene, as it can affect meshes too. Models targeting different up axes will have to be in different scenes from now on.

Import:

  * Optimised animation import
  * Fixed standalone animation import
  * Preserve material name if too long for Blender
  * Fixed animation import when a bone's parent wasn't in the armature
  * Fixed "smd\_bone\_vis" error when importing subsequent meshes
  * Do not resize etc. bones if there is only one in the armature (static props)
  * Scale 3D View to show imported mesh as well as armature (static props)
  * Gave up trying to reduce the number of animations keyframes imported due to bone "wobble". Like motion capture data, SMD anims will just have to be re-created before being edited.

Exporter:

  * Support all modifiers
  * Support sharp edges
  * Fixed Y-up animation export
  * Start exporting animation from the first defined keyframe, not scene frame zero (consistent with not finishing on the last scene frame)
  * Prevented errors when exporting hidden objects
  * Error when trying to export to a relative file path when the .blend hasn't been saved (otherwise it ends up somewhere weird)

## 0.7 - August 30th, 2010 ##

General:

  * Upgraded to Blender 2.54 beta. The script can no longer be used with 2.53 beta.


Importer:

  * Animation import (EasyPickins)
  * Fixed VTA import regression
  * Made bone length calculation more robust
  * Do not connect bones unless model is Z-up (temporary fix, I hope)
  * Do not generate a warning on $animation name redefinition

Exporter:

  * Mostly fixed animation export when imported bones are not Z-up. Configure target bone up axis from the Armature Properties panel.

## 0.6.5 - August 30th, 2010 ##

Importer:

  * Extend 3D View's gridlines and far clip distance to match import's size
  * Added support for absolute paths in QCs

## 0.6.4 - August 28th, 2010 ##

General:

  * Removed BigLines from the credits, at his request

Importer:

  * Improved performance by 30%
  * Fixed exception if a vertex is found weighted to a nonexistent bone
  * Fixed exception when exporting meshes without parents
  * Fixed exception at the very end of the import process if it wasn't invoked from the 3D View
  * Fixed new armatures sometimes being named after earlier QC imports

## 0.6.3 - August 28th, 2010 ##

Exporter:

  * Fixed not exporting reference bone positions (whoops)
  * Fixed subfolder creation failing when the scene root doesn't exist

## 0.6.2 - August 27th, 2010 ##

Importer:

  * Fixed bones with siblings being collapsed into each other by the bone connection routine
  * Fixed occasional errors when choosing armature for additional meshes
  * Fixed bones becoming connected to children directly below them, as well as above (hotfix)

## 0.6.1 - August 27th, 2010 ##

General:

  * Optimisations
  * More descriptive messages on fatal errors; check the console

Importer:

  * Fixed bones with siblings not always being conncted properly
  * Changed the armature search method when importing additional meshes:
    1. Active armature
    1. First armature in the selection
    1. First armature found modifying something in the selection
    1. First armature in the scene
    1. Otherwise a new armature is created
  * Bones at the end of chains are now ALWAYS spheres (fixes length issues and direction confusion)

Exporter:

  * Fixed export failing if there is no active object
  * Fixed exporter trying to write frames out even if there was no animation on an armature
  * Don't carry on trying to compile a QC if studiomdl isn't found
  * Warn when exceeding Source's bone limit of 128

## 0.6 - August 26, 2010 ##

Importer:

  * **Bones are now imported correctly to their rest positions**
  * **Meshes now import three times faster**
  * Changed the bone connection options. You can now choose to:
    * Connect all bones regardless of compatibility with other SMDs
    * Connect only bones that can be connected without breaking compatibility
    * Connect no bones at all
  * Unconnected bones become spheres without tails, to better represent SMD bones
  * Up axis is now adhered to when importing QCs, and can be configured when importing lone SMDs
  * Optimised QC line parsing


Exporter:

  * **Fixed bone export (thanks to EasyPickins)**, under all bone rotations modes
  * **Object scale and rotation is now applied** to all exports (Translation is only applied to meshes with parents or armature modifiers)
  * Copy meshes when converting between quads and tris, instead of operating on the original (EasyPickins)
  * Added option to compile a QC file automatically on export
  * Added armature configuration panel:
    * Actions for batch export can be filtered by name
    * The active action can be changed, and new ones created