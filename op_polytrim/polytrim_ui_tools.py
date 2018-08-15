'''
Created on Oct 10, 2015

@author: Patrick
'''
from ..common.utils import get_matrices
from ..common.rays import get_view_ray_data, ray_cast, ray_cast_path
from .polytrim_datastructure import InputNetwork, PolyLineKnife, InputPoint, InputSegment
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.geometry import intersect_point_line



class Polytrim_UI_Tools():
    '''
    Functions helpful with user interactions in polytrim
    '''

    class SketchHandler():
        '''
        Handles sketches made by user.
        * Intermediary between polytrim_states and PolyLineKnife
        '''
        def __init__(self, polyline):
            self.sketch = []
            self.polyline = polyline
            self.stroke_smoothing = 0.75  # 0: no smoothing. 1: no change
            self.sketch_curpos = (0, 0)

        def has_locs(self): return len(self.sketch) > 0
        has_locs = property(has_locs)

        def get_locs(self): return self.sketch

        def reset(self): self.sketch = []

        def add_loc(self, x, y):
            ''' Add's a screen location to the sketch list '''
            self.sketch.append((x,y))

        def smart_add_loc(self, x, y):
            ''' Add's a screen location to the sketch list based on smart stuff '''
            (lx, ly) = self.sketch[-1]
            ss0,ss1 = self.stroke_smoothing ,1-self.stroke_smoothing  #First data manipulation
            self.sketch += [(lx*ss0+x*ss1, ly*ss0+y*ss1)]

        def is_good(self):
            ''' Returns whether the sketch attempt should/shouldn't be added to the PolyLineKnife '''
            # checking to see if sketch functionality shouldn't happen
            if len(self.sketch) < 5 and self.polyline.ui_type == 'DENSE_POLY': return False
            return True

        def finalize(self, context, start_pnt, end_pnt=None):
            ''' takes sketch data and adds it into the datastructures '''
            if not isinstance(end_pnt, InputPoint): end_pnt = None

            print("Start:",start_pnt)
            print("End:",end_pnt)

            prev_pnt = None
            for ind in range(0, len(self.sketch) , 5):
                if not prev_pnt:
                    if self.polyline.num_points == 1: new_pnt = self.polyline.input_points.get(0)
                    else: new_pnt = start_pnt
                else:
                    pt_screen_loc = self.sketch[ind]
                    view_vector, ray_origin, ray_target = get_view_ray_data(context, pt_screen_loc)
                    loc, no, face_ind =  ray_cast(self.polyline.source_ob,self.polyline.imx, ray_origin, ray_target, None)
                    if face_ind != -1:
                        new_pnt = InputPoint(self.polyline.mx * loc, loc, view_vector, face_ind)
                        self.polyline.input_points.add(p=new_pnt)
                if prev_pnt:
                    seg = InputSegment(prev_pnt,new_pnt)
                    self.polyline.input_points.segments.append(seg)
                    seg.pre_vis_cut(self.polyline.bme, self.polyline.bvh, self.polyline.mx, self.polyline.imx)
                prev_pnt = new_pnt
            if end_pnt:
                seg = InputSegment(prev_pnt,end_pnt)
                self.polyline.input_points.segments.append(seg)
                seg.pre_vis_cut(self.polyline.bme, self.polyline.bvh, self.polyline.mx, self.polyline.imx)

    def ui_text_update(self):
        '''
        updates the text at the bottom of the viewport depending on certain conditions
        '''
        context = self.context
        if self.plm.current.bad_segments:
            context.area.header_text_set("Fix Bad segments by moving control points.")
        elif self.plm.current.ed_cross_map.is_used:
            context.area.header_text_set("When cut is satisfactory, press 'S' then 'LeftMouse' in region to cut")
        elif self.plm.current.hovered[0] == 'POINT':
            if self.plm.current.hovered[1] == 0:
                context.area.header_text_set("For origin point, left click to toggle cyclic")
            else:
                context.area.header_text_set("Right click to delete point. Hold left click and drag to make a sketch")
        else:
            self.set_ui_text_main()

    def set_ui_text_main(self):
        ''' sets the viewports text during general creation of line '''
        self.info_label.set_markdown("Left click to place cut points on the mesh, then press 'C' to preview the cut")
        #self.context.area.header_text_set()

    def hover(self, select_radius = 12, snap_radius = 24): #TDOD, these radii are pixels? Shoudl they be settings?
        '''
        finds points/edges/etc that are near ,mouse
         * hovering happens in mixed 3d and screen space, 20 pixels thresh for points, 30 for edges 40 for non_man
        '''

        # TODO: update self.hover to use Accel2D?
        polyline = self.plm.current
        mouse = self.actions.mouse
        context = self.context

        mx, imx = get_matrices(polyline.source_ob)
        loc3d_reg2D = view3d_utils.location_3d_to_region_2d
        # ray tracing
        view_vector, ray_origin, ray_target = get_view_ray_data(context, mouse)
        loc, no, face_ind = ray_cast(polyline.source_ob, imx, ray_origin, ray_target, None)

        polyline.snap_element = None
        polyline.connect_element = None
        
        if polyline.input_points.is_empty:
            polyline.hovered = [None, -1]
            self.hover_non_man()
            return
        if face_ind == -1: polyline.closest_ep = None
        else: polyline.closest_ep = polyline.closest_endpoint(mx * loc)

        #find length between vertex and mouse
        def dist(v):
            if v == None:
                print('v off screen')
                return 100000000
            diff = v - Vector(mouse)
            return diff.length

        #find length between 2 3d points
        def dist3d(v3):
            if v3 == None:
                return 100000000
            delt = v3 - polyline.source_ob.matrix_world * loc
            return delt.length

        #closest_3d_loc = min(polyline.input_points.world_locs, key = dist3d)
        closest_ip = min(polyline.input_points, key = lambda x: dist3d(x.world_loc))
        pixel_dist = dist(loc3d_reg2D(context.region, context.space_data.region_3d, closest_ip.world_loc))

        if pixel_dist  < select_radius:
            print('point is hovered')
            print(pixel_dist)
            polyline.hovered = ['POINT', closest_ip]  #TODO, probably just store the actual InputPoint as the 2nd value?
            polyline.snap_element = None
            return

        elif pixel_dist >= select_radius and pixel_dist < snap_radius:
            print('point is within snap radius')
            print(pixel_dist)
            if closest_ip.is_endpoint:
                polyline.snap_element = closest_ip

                print('This is the close loop scenario')
                closest_endpoints = polyline.closest_endpoints(polyline.snap_element.world_loc, 2)

                print('these are the 2 closest endpoints, one should be snap element itself')
                print(closest_endpoints)
                if closest_endpoints == None:
                    #we are not quite hovered but in snap territory
                    return

                if len(closest_endpoints) != 2:
                    print('len of closest endpoints not 2')
                    return

                polyline.connect_element = closest_endpoints[1]

            return


        if polyline.num_points == 1:  #why did we do this? Oh because there are no segments.
            polyline.hovered = [None, -1]
            polyline.snap_element = None
            return

        ##Check distance between ray_cast point, and segments
        distance_map = {}
        for seg in polyline.input_points.segments:  #TODO, may need to decide some better naming and better heirarchy

            close_loc, close_d = seg.closes_point_3d_linear(polyline.source_ob.matrix_world * loc)
            if close_loc  == None:
                distance_map[seg] = 10000000
                continue

            distance_map[seg] = close_d

        if polyline.input_points.segments:
            closest_seg = min(polyline.input_points.segments, key = lambda x: distance_map[x])

            a = loc3d_reg2D(context.region, context.space_data.region_3d, closest_seg.ip0.world_loc)
            b = loc3d_reg2D(context.region, context.space_data.region_3d, closest_seg.ip1.world_loc)

            if a and b:  #if points are not on the screen, a or b will be None
                intersect = intersect_point_line(Vector(mouse).to_3d(), a.to_3d(),b.to_3d())
                dist = (intersect[0].to_2d() - Vector(mouse)).length_squared
                bound = intersect[1]
                if (dist < select_radius**2) and (bound < 1) and (bound > 0):
                    polyline.hovered = ['EDGE', closest_seg]
                    return

        ## Multiple points, but not hovering over edge or point.
        polyline.hovered = [None, -1]

        self.hover_non_man()  #todo, optimize because double ray cast per mouse move!

    def hover_non_man(self):
        '''
        finds nonman edges and verts nearby to cursor location
        '''
        polyline = self.plm.current
        mouse = self.actions.mouse
        context = self.context

        region = context.region
        rv3d = context.region_data
        mx, imx = get_matrices(polyline.source_ob)
        # ray casting
        view_vector, ray_origin, ray_target= get_view_ray_data(context, mouse)
        loc, no, face_ind = ray_cast(polyline.source_ob, imx, ray_origin, ray_target, None)

        mouse = Vector(mouse)
        loc3d_reg2D = view3d_utils.location_3d_to_region_2d
        if len(polyline.non_man_points):
            co3d, index, dist = polyline.kd.find(mx * loc)

            #get the actual non man vert from original list
            close_bmvert = polyline.bme.verts[polyline.non_man_bmverts[index]] #stupid mapping, unreadable, terrible, fix this, because can't keep a list of actual bmverts
            close_eds = [ed for ed in close_bmvert.link_edges if not ed.is_manifold]
            if len(close_eds) == 2:
                bm0 = close_eds[0].other_vert(close_bmvert)
                bm1 = close_eds[1].other_vert(close_bmvert)

                a0 = bm0.co
                b   = close_bmvert.co
                a1  = bm1.co

                inter_0, d0 = intersect_point_line(loc, a0, b)
                inter_1, d1 = intersect_point_line(loc, a1, b)

                screen_0 = loc3d_reg2D(region, rv3d, mx * inter_0)
                screen_1 = loc3d_reg2D(region, rv3d, mx * inter_1)
                screen_v = loc3d_reg2D(region, rv3d, mx * b)

                if screen_0 and screen_1 and screen_v:
                    screen_d0 = (mouse - screen_0).length
                    screen_d1 = (mouse - screen_1).length
                    screen_dv = (mouse - screen_v).length

                    #TODO, decid how to handle when very very close to vertcies
                    if 0 < d0 <= 1 and screen_d0 < 20:
                        polyline.hovered = ['NON_MAN_ED', (close_eds[0], mx*inter_0)]
                        return
                    elif 0 < d1 <= 1 and screen_d1 < 20:
                        polyline.hovered = ['NON_MAN_ED', (close_eds[1], mx*inter_1)]
                        return
                    
                    #For now, not able to split a vert on the edge of the mesh, only edges
                    #elif screen_dv < 20:
                    #    if abs(d0) < abs(d1):
                    #        polyline.hovered = ['NON_MAN_VERT', (close_eds[0], mx*b)]
                    #        return
                    #    else:
                    #        polyline.hovered = ['NON_MAN_VERT', (close_eds[1], mx*b)]
                    #        return

class PolyLineManager(object):
    '''
    Manages having multiple instances of PolyLineKnife on an object at once.
    Might not need this so much anymore
    Or perhaps we should use this to manage insertions, strokes etc since InputPointsMap seems to handle things
    
    '''
    def __init__(self):
        self.polylines = []
        self.vert_screen_locs = {}
        self.hovered = None
        self.current = None
        self.previous = None
        self.mode = 'wait' # 'wait'  : mode for editing a single polyline's datastructure
                           # 'select': mode for selecting, adding, and deleting polylines

    def num_polylines(self): return len(self.polylines)
    num_polylines = property(num_polylines)

    ######################
    ## user interaction ##

    def initiate_select_mode(self, context):
        self.mode = 'select'
        self.previous = self.current
        self.current = None
        self.update_screen_locs(context)

    def hover(self, context, coord):
        for polyline in self.vert_screen_locs:
            for loc in self.vert_screen_locs[polyline]:
                if self.dist(loc, coord) < 20:
                    self.hovered = polyline
                    return
        self.hovered = None

    def select(self, context):
        self.mode = 'wait'
        self.current = self.hovered
        self.hovered = None

    def delete(self, context):
        if self.previous == self.hovered: self.previous = self.polylines[self.polylines.index(self.hovered) - 1]
        self.polylines.remove(self.hovered)
        self.hovered = None
        self.update_screen_locs(context)

    def start_new_polyline(self, context):
        self.mode = 'wait'
        self.hovered = None
        self.previous = None
        self.current = PolyLineKnife(context, context.object)
        self.add(self.current)

    def terminate_select_mode(self):
        self.mode = 'wait'
        self.hovered = None
        self.current = self.previous

    ###########
    ## other ##

    def add(self, polyline):
        ''' add a polyline to the plm's polyline list '''
        self.polylines.append(polyline)

    def update_screen_locs(self, context):
        ''' fills dictionary: keys -> polylines, values -> vertex screen locations '''
        self.vert_screen_locs = {}
        loc3d_reg2D = view3d_utils.location_3d_to_region_2d
        for polyline in self.polylines:
            self.vert_screen_locs[polyline] = []
            for loc in polyline.input_points.world_locs:
                loc2d = loc3d_reg2D(context.region, context.space_data.region_3d, loc)
                self.vert_screen_locs[polyline].append(loc2d)

    def dist(self, v, screen_loc):
        ''' finds screen distance between mouse location and specified point '''
        if v == None:
            print('v off screen')
            return 100000000
        diff = v - Vector(screen_loc)
        return diff.length


