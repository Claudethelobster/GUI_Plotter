# core/analysis_3d.py
import numpy as np
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt5.QtCore import QObject, QEvent, Qt

from core.theme import theme
from ui.custom_widgets import DraggableLabel

class Crosshair3DManager(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window
        self.gl_widget = main_window.gl_widget
        
        self.active = False
        self.locked = False
        
        # Performance Caches
        self._last_data_ref = None
        self._cached_raw = np.array([])
        self._cached_smooth = np.array([])
        
        # 1. BUILD THE 3D MAP PIN MESH
        # The goal is to build a mesh where the pinpoint rests exactly at (0,0,0) in local space.
        # This ensures accurate snapping when translated to data points.
        
        # stem_length must correspond to the height of the cone defined in gl.MeshData.cylinder
        stem_length = 2.0 
        head_radius = 0.5
        
        # A. Create the cone stem (tip at z=0, base at z=stem_length)
        stem_md = gl.MeshData.cylinder(rows=1, cols=16, radius=[0.0, head_radius/2], length=stem_length)
        
        # B. Create the head (sphere center at (0,0,0))
        head_md = gl.MeshData.sphere(rows=16, cols=16, radius=head_radius)
        
        # C. Shift head upwards so it sits on top of the stem
        v_head = head_md.vertexes()
        v_head[:, 2] += stem_length + (head_radius * 0.7) # Lift sphere above stem
        head_md.setVertexes(v_head)
        
        # D. Combine Meshes
        combined_verts = np.vstack((stem_md.vertexes(), head_md.vertexes()))
        combined_faces = np.vstack((stem_md.faces(), head_md.faces() + stem_md.vertexes().shape[0]))
        
        combined_md = gl.MeshData(vertexes=combined_verts, faces=combined_faces)
        
        self.marker = gl.GLMeshItem(meshdata=combined_md, smooth=False, computeNormals=False, color=(1.0, 0.2, 0.2, 0.9), shader=None)
        self.marker.hide()
            
        # 2. Build the Floating HUD
        self.hud = DraggableLabel(self.mw.plot_stack)
        self.hud.setStyleSheet(f"""
            background-color: {theme.primary_bg}; 
            border: 2px solid {theme.primary_border}; 
            border-radius: 6px; padding: 8px; 
            font-family: Consolas, monospace; font-size: 13px; 
            color: {theme.primary_text};
        """)
        self.hud.hide()
        
    def toggle(self):
        if not self.gl_widget: return
        self.active = not self.active
        if self.active:
            self.enable()
        else:
            self.disable()
            
    def enable(self):
        self.locked = False
        
        if self.marker not in self.gl_widget.items:
            self.gl_widget.addItem(self.marker)
            
        self.marker.show()
        self.hud.show()
        self.hud.raise_()
        self.gl_widget.installEventFilter(self)
        self.gl_widget.setMouseTracking(True)
        self.sync_button_ui()
        
    def disable(self):
        self.active = False
        self.locked = False
        self.marker.hide()
        self.hud.hide()
        # Protect against double-removal crash if plot mode changed while active
        try:
            self.gl_widget.removeEventFilter(self)
            self.gl_widget.setMouseTracking(False)
        except Exception:
            pass
        self.sync_button_ui()
        
    def set_locked(self, locked):
        self.locked = locked
        self.sync_button_ui()

    def sync_button_ui(self):
        if not hasattr(self.mw, 'snap_toggle_btn'): return
        self.mw.snap_toggle_btn.blockSignals(True)
        if self.locked:
            self.mw.snap_toggle_btn.setChecked(False)
            self.mw.snap_toggle_btn.setText("✖ Camera Free (Anchor Locked)")
            self.mw.snap_toggle_btn.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; border: 2px solid {theme.danger_border}; padding: 6px; background-color: {theme.bg};")
        else:
            self.mw.snap_toggle_btn.setChecked(self.active)
            if self.active:
                self.mw.snap_toggle_btn.setText("✔ Camera Locked (Anchor Active)")
                self.mw.snap_toggle_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; border: 2px solid {theme.success_border}; padding: 6px; background-color: {theme.bg};")
            else:
                self.mw.snap_toggle_btn.setText("○ Activate 3D Anchor")
                # --- FIX: Changed theme.text to theme.fg ---
                self.mw.snap_toggle_btn.setStyleSheet(f"color: {theme.fg}; padding: 6px; background-color: {theme.bg};")
        self.mw.snap_toggle_btn.blockSignals(False)

    def _build_caches(self, data_cache):
        raw_list = []
        smooth_list = []
        is_line_plot = getattr(self.mw.graphtype, 'currentText', lambda: '')() == "Line"

        import scipy.ndimage

        for item in data_cache['data']:
            if str(item[0]) == "SURFACE":
                if 'raw_pts' in item[2]:
                    raw_list.append(item[2]['raw_pts'])
                    
                grid_z = item[2]['z_2d']
                target_res = 400
                current_res = max(grid_z.shape)
                
                if current_res < target_res:
                    zoom_factor = target_res / current_res
                    z_smooth = scipy.ndimage.zoom(grid_z, zoom_factor, order=1)
                else:
                    z_smooth = grid_z
                    
                x_smooth = np.linspace(item[2]['x_1d'][0], item[2]['x_1d'][-1], z_smooth.shape[0])
                y_smooth = np.linspace(item[2]['y_1d'][0], item[2]['y_1d'][-1], z_smooth.shape[1])
                X, Y = np.meshgrid(x_smooth, y_smooth, indexing='ij')
                pts = np.column_stack((X.flatten(), Y.flatten(), z_smooth.flatten()))
                smooth_list.append(pts)
            else:
                pts = item[2]
                raw_list.append(pts)
                
                # Oversample 3D lines
                if is_line_plot and len(pts) > 1:
                    num_smooth = min(len(pts) * 15, 250000) 
                    orig_idx = np.arange(len(pts))
                    smooth_idx = np.linspace(0, len(pts)-1, num_smooth)
                    
                    smooth_x = np.interp(smooth_idx, orig_idx, pts[:, 0])
                    smooth_y = np.interp(smooth_idx, orig_idx, pts[:, 1])
                    smooth_z = np.interp(smooth_idx, orig_idx, pts[:, 2])
                    smooth_list.append(np.column_stack((smooth_x, smooth_y, smooth_z)))
                else:
                    smooth_list.append(pts)

        if raw_list:
            c_raw = np.vstack(raw_list)
            self._cached_raw = c_raw[np.isfinite(c_raw).all(axis=1)]
        else:
            self._cached_raw = np.array([])

        if smooth_list:
            c_smooth = np.vstack(smooth_list)
            self._cached_smooth = c_smooth[np.isfinite(c_smooth).all(axis=1)]
        else:
            self._cached_smooth = np.array([])

    def eventFilter(self, source, event):
        if source == self.gl_widget:
            if not self.locked:
                if event.type() in [QEvent.MouseMove, QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.Wheel]:
                    if event.type() == QEvent.MouseMove and event.buttons() == Qt.NoButton:
                        self._handle_mouse_move(event.pos())
                    elif event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                        self.set_locked(True) 
                    return True 
            else:
                if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
                    self.set_locked(False)
                    return True
        return super().eventFilter(source, event)
        
    def _handle_mouse_move(self, pos):
        try:
            w, h = self.gl_widget.width(), self.gl_widget.height()
            if w == 0 or h == 0: return

            try:
                rect_tuple = (0, 0, w, h)
                proj = self.gl_widget.projectionMatrix(region=rect_tuple, viewport=rect_tuple)
            except TypeError:
                proj = self.gl_widget.projectionMatrix()
                
            view = self.gl_widget.viewMatrix()
            mvp = proj * view
            
            m = np.array([
                [mvp.row(0).x(), mvp.row(0).y(), mvp.row(0).z(), mvp.row(0).w()],
                [mvp.row(1).x(), mvp.row(1).y(), mvp.row(1).z(), mvp.row(1).w()],
                [mvp.row(2).x(), mvp.row(2).y(), mvp.row(2).z(), mvp.row(2).w()],
                [mvp.row(3).x(), mvp.row(3).y(), mvp.row(3).z(), mvp.row(3).w()]
            ])
            
            data_cache = getattr(self.mw, 'last_plotted_data', {})
            if data_cache.get('mode') != '3D' or not data_cache.get('data'): return
            
            bounds = data_cache.get('bounds')
            if not bounds: return
            mins, maxs = bounds
            
            current_data_ref = data_cache.get('data')
            if current_data_ref is not self._last_data_ref:
                self._build_caches(data_cache)
                self._last_data_ref = current_data_ref
                
            snap_to_raw = getattr(self.mw, 'gl_surface_cb', None) and not self.mw.gl_surface_cb.isChecked()
            all_pts = self._cached_raw if snap_to_raw else self._cached_smooth
            
            if len(all_pts) == 0: return
            
            sx, sy, sz = self.mw.gl_scale_x.value(), self.mw.gl_scale_y.value(), self.mw.gl_scale_z.value()
            spans = maxs - mins
            spans[spans == 0] = 1.0
            
            scale_factors = (10.0 / spans) * np.array([sx, sy, sz])
            scaled_pts = (all_pts - mins) * scale_factors
            
            pts_4d = np.hstack((scaled_pts, np.ones((len(scaled_pts), 1))))
            clip_pts = pts_4d.dot(m.T)
            
            w_clip = clip_pts[:, 3]
            front_mask = w_clip > 0.001 
            
            if not np.any(front_mask): return
            clip_pts = clip_pts[front_mask]
            valid_pts = all_pts[front_mask]
            valid_scaled = scaled_pts[front_mask]
            w_clip = w_clip[front_mask]
            
            ndc_x = clip_pts[:, 0] / w_clip
            ndc_y = clip_pts[:, 1] / w_clip
            
            screen_x = (ndc_x + 1.0) * w / 2.0
            screen_y = (1.0 - ndc_y) * h / 2.0 
            
            mouse_x, mouse_y = pos.x(), pos.y()
            pixel_dists_sq = (screen_x - mouse_x)**2 + (screen_y - mouse_y)**2
            best_idx = np.argmin(pixel_dists_sq)
            
            # Pixel threshold slightly reduced to account for the precision of the pin shape
            if pixel_dists_sq[best_idx] > 10000:
                self.marker.hide()
                self.hud.hide()
                return
            
            self.marker.show()
            self.hud.show()
            
            best_scaled = valid_scaled[best_idx]
            best_physical = valid_pts[best_idx]
            
            # RENDER PIN (The tip is at local 0,0,0, so translation handles the pinpointing)
            tr = pg.Transform3D()
            tr.translate(best_scaled[0], best_scaled[1], best_scaled[2])
            # Pin size is relative to axis scaling
            base_size = 0.20 * max(sx, sy, sz)
            tr.scale(base_size, base_size, base_size)
            self.marker.setTransform(tr)
            
            self.hud.setText(f"<b>3D Coordinate Anchor</b><hr style='border-top: 1px solid #ccc; margin: 4px 0;'>"
                             f"X: {best_physical[0]:.6g}<br>"
                             f"Y: {best_physical[1]:.6g}<br>"
                             f"Z: {best_physical[2]:.6g}")
            self.hud.adjustSize()
            
            hw, hh = self.hud.width(), self.hud.height()
            mx, my = pos.x() + 15, pos.y() + 15
            if mx + hw > w: mx = pos.x() - hw - 5
            if my + hh > h: my = pos.y() - hh - 5
            self.hud.move(mx, my)
            
        except Exception:
            pass
