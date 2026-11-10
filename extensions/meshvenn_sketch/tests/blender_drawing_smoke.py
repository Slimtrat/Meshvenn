"""Actual Image Editor event-loop acceptance, run on Linux CI under Xvfb.

blender --factory-startup --enable-event-simulate --python this.py -- ...
Only Blender's own test-event API is used; no desktop or user preferences change.
"""
import argparse
import importlib
import os
from pathlib import Path
import sys
import traceback

import bpy

parser=argparse.ArgumentParser()
parser.add_argument('--package-root',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
sys.path.insert(0,str(args.package_root.resolve().parent))
extension=importlib.import_module(args.package_root.name)
extension.register()
from meshvenn_sketch import drawing

state={}
points=((.2,.25),(.7,.25),(.8,.65),(.5,.85),(.2,.65))


def area_context(area):
    return bpy.context.temp_override(area=area,region=next(r for r in area.regions if r.type=='WINDOW'))


def setup():
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    bpy.ops.object.armature_add()
    rig=bpy.context.object;rig.data.bones[0].name='attachment'
    bpy.ops.mesh.primitive_cube_add(size=2)
    source=bpy.context.object;source.name='Drawing test source'
    source.modifiers.new('Skin','ARMATURE').object=rig
    source.vertex_groups.new(name='attachment').add(range(8),1.,'REPLACE')
    image=bpy.data.images.new('Drawing test reference',width=256,height=128)
    settings=bpy.context.scene.mvsketch
    settings.source=source;settings.image=image;settings.bone='attachment'
    state.update(source=source,image=image,pixels=tuple(image.pixels))
    assert bpy.ops.mvsketch.calibrate()=={'FINISHED'}
    view=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
    with area_context(view):assert bpy.ops.mvsketch.open_view()=={'FINISHED'}
    area=next(a for a in bpy.context.screen.areas if a.type=='IMAGE_EDITOR')
    area.spaces.active.show_region_ui=False
    state['area']=area


def start():
    area=state['area']
    with area_context(area):
        bpy.ops.image.view_all(fit_view=True)
    area.tag_redraw()


def begin():
    with area_context(state['area']):
        assert bpy.ops.mvsketch.draw_outline('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
    assert len(drawing.SESSIONS)==1


def click(uv):
    area=state['area'];region=next(r for r in area.regions if r.type=='WINDOW')
    x,y=region.view2d.view_to_region(*uv,clip=False)
    actual=region.view2d.region_to_view(x,y)
    assert max(abs(a-b) for a,b in zip(actual,uv))<.01,actual
    x+=region.x;y+=region.y
    window=bpy.context.window
    window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
    window.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
    window.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)


def key(name):
    bpy.context.window.event_simulate(type=name,value='PRESS')
    bpy.context.window.event_simulate(type=name,value='RELEASE')


def stroke():
    area=state['area'];region=next(r for r in area.regions if r.type=='WINDOW')
    window=bpy.context.window
    for i,uv in enumerate(points):
        x,y=region.view2d.view_to_region(*uv,clip=False);x+=region.x;y+=region.y
        window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
        if i==0:window.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
    window.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)


def accepted():
    settings=bpy.context.scene.mvsketch
    assert not drawing.SESSIONS,'Enter did not finish the drawing operator'
    actual=[tuple(p.uv) for p in settings.contour]
    assert len(actual)==len(points),actual
    assert max(min(max(abs(a-b) for a,b in zip(uv,p)) for p in actual) for uv in points)<.01
    assert tuple(state['image'].pixels)==state['pixels'],'Drawing changed reference pixels'
    assert bpy.ops.mvsketch.create_piece()=={'FINISHED'}
    assert len(settings.piece.data.vertices)==2*len(points)
    assert settings.piece.find_armature() is state['source'].find_armature()
    state['piece']=settings.piece
    state['contour']=actual


def cancelled():
    assert not drawing.SESSIONS
    assert [tuple(p.uv) for p in bpy.context.scene.mvsketch.contour]==state['contour']
    assert tuple(state['image'].pixels)==state['pixels']
    assert bpy.context.scene.mvsketch.piece is state['piece']
    state['area'].spaces.active.show_region_ui=True
    args.output.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output/'drawing.blend'))


def reloaded():
    # Loading another file during an active tool must remove its old overlay.
    assert drawing.SESSIONS
    bpy.ops.wm.open_mainfile(filepath=str(args.output/'drawing.blend'),use_scripts=False)
    assert not drawing.SESSIONS
    state['piece']=bpy.context.scene.mvsketch.piece


def finish():
    extension.unregister()
    assert not drawing.SESSIONS and not hasattr(bpy.types.Scene,'mvsketch')
    assert 'mvsketch_recipe' in state['piece']
    print('SKETCH DRAWING PASS: split view, non-square image UVs, clicks, freehand stroke, GPU overlay, Enter, Esc, creation, reload and clean disable.',flush=True)
    (args.output/'drawing-pass.txt').write_text('Image Editor drawing acceptance passed\n',encoding='utf-8')
    bpy.ops.wm.quit_blender()


steps=iter((setup,start,begin,*(lambda uv=uv:click(uv) for uv in points),lambda:key('RET'),accepted,
            begin,lambda:click((.3,.3)),lambda:key('ESC'),cancelled,
            begin,stroke,lambda:key('RET'),accepted,begin,reloaded,finish))


def tick():
    try:
        next(steps)()
        return .3
    except StopIteration:return None
    except BaseException:
        traceback.print_exc();sys.stdout.flush();sys.stderr.flush();os._exit(1)


# This driver deliberately reloads a file; an ordinary timer disappears on load.
bpy.app.timers.register(tick,first_interval=1.,persistent=True)
