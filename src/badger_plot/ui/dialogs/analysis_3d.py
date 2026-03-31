# core/analysis_3d.py
import numpy as np
from scipy.spatial import Delaunay
import scipy.integrate as integrate
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from PyQt6.QtCore import QObject, QEvent, Qt

from PyQt6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel, QPushButton

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
                if event.type() in [QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.Wheel]:
                    if event.type() == QEvent.Type.MouseMove and event.buttons() == Qt.MouseButton.NoButton:
                        self._handle_mouse_move(event.pos())
                    elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                        self.set_locked(True) 
                    return True 
            else:
                if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
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
        
class VolumeIntegrator3D(QObject):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.mw = main_window

    def calculate_volume(self):
        """Main entry point to grab the current 3D data and route it to the correct solver."""
        data_cache = getattr(self.mw, 'last_plotted_data', {})
        if data_cache.get('mode') != '3D' or not data_cache.get('data'):
            self._show_error("No 3D Data", "Please plot some 3D data before calculating volume.")
            return

        # Grab the first active 3D series for the calculation
        # (Assuming the user highlighted the one they want to integrate)
        active_item = data_cache['data'][0]
        series_name = active_item[0]
        raw_data = active_item[2]

        try:
            if series_name == "SURFACE":
                vol, area, mean_z, base_z = self._integrate_grid(raw_data)
                method_used = "Double-Trapezoidal Matrix Integration (Uniform Grid)"
            else:
                vol, area, mean_z, base_z = self._integrate_scatter(raw_data)
                method_used = "Delaunay Triangular Prism Summation (Scattered/Line Data)"
                
            self._show_results_dialog(vol, area, mean_z, base_z, method_used)
            
        except Exception as e:
            self._show_error("Integration Failed", f"The math engine encountered an error:\n\n{str(e)}")

    def _integrate_grid(self, data_dict):
        """Calculates volume for perfectly gridded Surface Mesh data."""
        x_1d = data_dict['x_1d']
        y_1d = data_dict['y_1d']
        z_2d = data_dict['z_2d']
        
        # Calculate the baseline (we integrate down to the lowest point of the terrain)
        base_z = np.nanmin(z_2d)
        z_shifted = z_2d - base_z
        
        # Integrate along the Y axis first, then the X axis
        # (Using numpy's trapz or trapezoid depending on version, scipy is safer)
        vol_y = integrate.trapezoid(z_shifted, x=y_1d, axis=1)
        total_vol = integrate.trapezoid(vol_y, x=x_1d)
        
        # Calculate bounding area and mean height
        area = abs(x_1d[-1] - x_1d[0]) * abs(y_1d[-1] - y_1d[0])
        mean_z = np.nanmean(z_2d)
        
        return total_vol, area, mean_z, base_z

    def _integrate_scatter(self, pts):
        """Calculates volume for scattered points by building a Delaunay mesh of triangular prisms."""
        # Clean the data of NaNs
        valid_pts = pts[np.isfinite(pts).all(axis=1)]
        if len(valid_pts) < 3:
            raise ValueError("Not enough valid points to form a 3D volume mesh.")

        x = valid_pts[:, 0]
        y = valid_pts[:, 1]
        z = valid_pts[:, 2]

        base_z = np.min(z)
        z_shifted = z - base_z

        # Create a 2D mesh flat on the ground
        points_2d = np.column_stack((x, y))
        tri = Delaunay(points_2d)

        total_vol = 0.0
        total_area = 0.0

        # Loop through every triangle generated by the web
        for simplex in tri.simplices:
            # Get the (X, Y) coordinates for the 3 corners of this specific triangle
            p1, p2, p3 = points_2d[simplex[0]], points_2d[simplex[1]], points_2d[simplex[2]]
            
            # Calculate the 2D area of the triangle base using the determinant method
            area = 0.5 * np.abs(p1[0]*(p2[1] - p3[1]) + p2[0]*(p3[1] - p1[1]) + p3[0]*(p1[1] - p2[1]))
            
            # Calculate the average Z-height of the 3 corners to form the prism "roof"
            avg_height = (z_shifted[simplex[0]] + z_shifted[simplex[1]] + z_shifted[simplex[2]]) / 3.0
            
            total_vol += area * avg_height
            total_area += area

        mean_z = np.mean(z)
        
        return total_vol, total_area, mean_z, base_z

    def _show_results_dialog(self, vol, area, mean_z, base_z, method):
        """Spawns a styled floating HUD to display the physics results."""
        dialog = QDialog(self.mw)
        dialog.setWindowTitle("3D Volume Analysis")
        dialog.setStyleSheet(f"background-color: {theme.bg}; color: {theme.fg};")
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        html = f"""
        <div style="font-family: 'Segoe UI', sans-serif;">
            <h2 style="color: {theme.primary_text}; border-bottom: 1px solid {theme.border}; padding-bottom: 5px;">Topological Volume Report</h2>
            <p style="color: {theme.success_text}; font-size: 16px;"><b>Net Volume:</b> {vol:.6g} units³</p>
            <ul style="margin-top: 5px; line-height: 1.6;">
                <li><b>Calculated Base (Floor Z):</b> {base_z:.6g}</li>
                <li><b>Bounding Area (X-Y Footprint):</b> {area:.6g} units²</li>
                <li><b>Mean Z-Height:</b> {mean_z:.6g}</li>
            </ul>
            <p style="font-size: 11px; color: {theme.danger_text}; font-style: italic;">
                *Volume is calculated relative to the absolute lowest Z-coordinate in the dataset to prevent negative cancellation.
            </p>
            <hr style="border: 1px solid {theme.border};">
            <p style="font-size: 11px; color: #888;"><b>Engine:</b> {method}</p>
        </div>
        """
        
        label = QLabel(html)
        label.setWordWrap(True)
        layout.addWidget(label)
        
        close_btn = QPushButton("Close Report")
        close_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {theme.panel_bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {theme.primary_bg}; }}
        """)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
        dialog.exec()

    def _show_error(self, title, message):
        QMessageBox.warning(self.mw, title, message)
