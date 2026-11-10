"""Image Editor outline tool; draws overlays without changing reference pixels."""
import math
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from .bridge import draft_frame
from .polygon import outline,simplify

SESSIONS=set()


def _redraw(session):
    try:session.area.tag_redraw()
    except ReferenceError:pass


def _cleanup(session):
    if getattr(session,'handler',None) is not None:
        bpy.types.SpaceImageEditor.draw_handler_remove(session.handler,'WINDOW');session.handler=None
    try:
        session.area.header_text_set(None)
        session.window.cursor_modal_restore()
        session.area.tag_redraw()
    except (ReferenceError,RuntimeError):pass
    SESSIONS.discard(session)


def cleanup():
    for session in tuple(SESSIONS):_cleanup(session)


class MVSK_OT_Draw(bpy.types.Operator):
    bl_idname='mvsketch.draw_outline';bl_label='Draw Piece Outline'
    bl_description='Click corners or drag an outline; Enter accepts, Esc cancels, Backspace removes points'
    bl_options={'REGISTER','UNDO','BLOCKING'}

    @classmethod
    def poll(cls,context):
        return context.area is not None and context.area.type=='IMAGE_EDITOR' and context.region.type in {'WINDOW','UI'}

    def invoke(self,context,event):
        settings=context.scene.mvsketch
        try:draft_frame(settings)
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        if context.space_data.image is not settings.image:
            self.report({'ERROR'},'Show the calibrated reference image in this Image Editor.');return {'CANCELLED'}
        self.area=context.area;self.window=context.window
        self.region=next(r for r in self.area.regions if r.type=='WINDOW')
        self.image=settings.image;self.frame=settings.frame_json
        self.points=[];self.dragging=False
        self.handler=bpy.types.SpaceImageEditor.draw_handler_add(self._draw_overlay,(),'WINDOW','POST_PIXEL')
        SESSIONS.add(self)
        self.area.header_text_set('Click corners or drag • Enter: accept • Backspace: remove point • R: redraw • Esc: cancel')
        self.window.cursor_modal_set('CROSSHAIR');context.window_manager.modal_handler_add(self)
        _redraw(self);return {'RUNNING_MODAL'}

    def _draw_overlay(self):
        if bpy.context.area is not self.area or len(self.points)<2:return
        coordinates=[self.region.view2d.view_to_region(*uv,clip=False) for uv in self.points]
        if not self.dragging:coordinates.append(coordinates[0])
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        batch=batch_for_shader(shader,'LINE_STRIP',{'pos':coordinates})
        gpu.state.blend_set('ALPHA');gpu.state.line_width_set(2.)
        try:
            shader.bind();shader.uniform_float('color',(.15,.8,1.,1.));batch.draw(shader)
        finally:gpu.state.line_width_set(1.);gpu.state.blend_set('NONE')

    def _point(self,event):
        x,y=event.mouse_x-self.region.x,event.mouse_y-self.region.y
        if not 0<=x<self.region.width or not 0<=y<self.region.height:return None
        u,v=self.region.view2d.region_to_view(x,y)
        if not 0<=u<=1 or not 0<=v<=1:return None
        return float(u),float(v)

    def modal(self,context,event):
        if self not in SESSIONS:return {'CANCELLED'}
        settings=context.scene.mvsketch
        if (settings.image is not self.image or settings.frame_json!=self.frame
                or self.area.type!='IMAGE_EDITOR' or self.area.spaces.active.image is not self.image):
            _cleanup(self);self.report({'WARNING'},'Reference changed; drawing cancelled.');return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'}:
            _cleanup(self);return {'CANCELLED'}
        if event.type=='R' and event.value=='PRESS':self.points.clear();self.dragging=False
        elif event.type in {'BACK_SPACE','DEL'} and event.value=='PRESS':
            if self.points:self.points.pop()
        elif event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS':
            try:
                points=outline(simplify(self.points,tuple(self.image.size)))
                draft_frame(settings)
            except Exception as exc:self.report({'ERROR'},str(exc));return {'RUNNING_MODAL'}
            settings.contour.clear()
            for uv in points:settings.contour.add().uv=uv
            _cleanup(self);self.report({'INFO'},f'Outline saved: {len(points)} corners. Set thickness and create the piece.');return {'FINISHED'}
        elif event.type=='LEFTMOUSE':
            if event.value=='PRESS':
                point=self._point(event)
                if point is not None and len(self.points)<2048:
                    self.points.append(point);self.dragging=True
            elif event.value=='RELEASE':self.dragging=False
        elif event.type=='MOUSEMOVE' and self.dragging:
            point=self._point(event)
            if point is not None and len(self.points)<2048:
                last=self.region.view2d.view_to_region(*self.points[-1],clip=False)
                pixel=self.region.view2d.view_to_region(*point,clip=False)
                if math.dist(last,pixel)>=3:self.points.append(point)
        elif not self.dragging and event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN','TRACKPADZOOM'}:
            return {'PASS_THROUGH'}
        _redraw(self);return {'RUNNING_MODAL'}

    def cancel(self,context):_cleanup(self)
