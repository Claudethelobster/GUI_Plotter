# ui/renderers/renderer_3d.py
import numpy as np
import matplotlib
import pyqtgraph as pg
from PyQt5.QtWidgets import QMessageBox

try:
    import pyqtgraph.opengl as gl
except ImportError:
    gl = None

class Renderer3D:
    @staticmethod
    def draw(mw, all_pts_raw, bounds):
        """
        Renders 3D point clouds, lines, and fitted surfaces.
        mw: Reference to the BadgerLoopQtGraph main window instance.
        """
        try:
                # --- FIX: Safely close the progress dialog ---
            if getattr(mw, 'progress_dialog', None) is not None:
                try: mw.progress_dialog.accept()
                except: pass
            # ---------------------------------------------
            
            # Safely abort if OpenGL failed to initialise on boot
            if mw.gl_widget is None or gl is None: return
            
            mw.gl_widget.clear() 
            mw._apply_canvas_settings()
            
            if not all_pts_raw: return
            
            # --- FIX: Save the bounds into the dict so the Crosshair Manager can read them! ---
            mw.last_plotted_data = {'mode': '3D', 'data': all_pts_raw, 'bounds': bounds}
            # ----------------------------------------------------------------------------------
                
            mins, maxs = bounds
            spans = maxs - mins
            spans[spans == 0] = 1.0 
            
            # --- NEW: APPLY INDEPENDENT AXIS SCALES ---
            sx = mw.gl_scale_x.value()
            sy = mw.gl_scale_y.value()
            sz = mw.gl_scale_z.value()
            scale_factors = (10.0 / spans) * np.array([sx, sy, sz])
            # ------------------------------------------
            
            if all_pts_raw[0][0] == "SURFACE":
                surface_dict = all_pts_raw[0][2]
                x_1d = surface_dict["x_1d"]
                y_1d = surface_dict["y_1d"]
                z_2d = surface_dict["z_2d"]
                
                x_scaled = (x_1d - mins[0]) * scale_factors[0]
                y_scaled = (y_1d - mins[1]) * scale_factors[1]
                z_scaled = (z_2d - mins[2]) * scale_factors[2]
                
                x_scaled = np.ascontiguousarray(x_scaled, dtype=np.float32)
                y_scaled = np.ascontiguousarray(y_scaled, dtype=np.float32)
                z_scaled = np.ascontiguousarray(z_scaled, dtype=np.float32)
                
                cmap = matplotlib.colormaps.get_cmap(mw.heatmap_cmap.currentText())
                z_norm = (z_2d - mins[2]) / spans[2] 
                
                colors = cmap(z_norm).astype(np.float32) 
                colors_flat = colors.reshape(-1, 4) 
                
                # --- FIX: Safe Wireframe Texture (No Shaders) ---
                draw_grid = mw.gl_lighting_cb.isChecked()
                z_gl_safe = np.nan_to_num(z_scaled, nan=0.0)
                
                surface_item = gl.GLSurfacePlotItem(
                    x=x_scaled, y=y_scaled, z=z_gl_safe, 
                    colors=colors_flat, 
                    smooth=False, computeNormals=False,
                    drawEdges=draw_grid, edgeColor=(0.0, 0.0, 0.0, 0.3) # Subtle dark net
                )
                mw.gl_widget.addItem(surface_item)
                # ------------------------------------------------

            else:
                cmap = matplotlib.colormaps.get_cmap('jet') 
                num_sweeps_plotted = len(all_pts_raw)
                
                for idx, (i, sw, pts) in enumerate(all_pts_raw):
                    
                    # --- CRITICAL FIX: STRIP NANS FOR OPENGL ---
                    valid = np.isfinite(pts[:, 0]) & np.isfinite(pts[:, 1]) & np.isfinite(pts[:, 2])
                    pts = pts[valid]
                    if len(pts) == 0: continue
                    # -------------------------------------------
                    
                    norm_pts = np.zeros_like(pts, dtype=np.float32)
                    norm_pts[:, 0] = (pts[:, 0] - mins[0]) * scale_factors[0]
                    norm_pts[:, 1] = (pts[:, 1] - mins[1]) * scale_factors[1]
                    norm_pts[:, 2] = (pts[:, 2] - mins[2]) * scale_factors[2]
                    norm_pts = np.ascontiguousarray(norm_pts)
                    
                    rgba = cmap(idx / max(1, num_sweeps_plotted - 1)) 
                    c_tuple = (float(rgba[0]), float(rgba[1]), float(rgba[2]), 1.0)
                    
                    if mw.graphtype.currentText() == "Line":
                        item = gl.GLLinePlotItem(pos=norm_pts, color=c_tuple, width=2, antialias=True)
                    else:
                        d = 0.08
                        cross_pts = np.empty((len(norm_pts) * 6, 3), dtype=np.float32)
                        cross_pts[0::6] = norm_pts + np.array([-d, 0, 0], dtype=np.float32)
                        cross_pts[1::6] = norm_pts + np.array([ d, 0, 0], dtype=np.float32)
                        cross_pts[2::6] = norm_pts + np.array([0, -d, 0], dtype=np.float32)
                        cross_pts[3::6] = norm_pts + np.array([0,  d, 0], dtype=np.float32)
                        cross_pts[4::6] = norm_pts + np.array([0, 0, -d], dtype=np.float32)
                        cross_pts[5::6] = norm_pts + np.array([0, 0,  d], dtype=np.float32)
                        item = gl.GLLinePlotItem(pos=cross_pts, color=c_tuple, width=3, antialias=True, mode='lines')
                        
                    mw.gl_widget.addItem(item)
                    
                    # --- NEW: STEM PLOTTING (DROP LINES) ---
                    if mw.gl_stem_cb.isChecked():
                        stem_pts = np.empty((len(norm_pts) * 2, 3), dtype=np.float32)
                        stem_pts[0::2] = norm_pts
                        floor_pts = norm_pts.copy()
                        floor_pts[:, 2] = 0.0 # Drop straight down to the physical floor
                        stem_pts[1::2] = floor_pts
                        
                        stem_item = gl.GLLinePlotItem(pos=stem_pts, color=(1, 1, 1, 0.4), width=1, antialias=True, mode='lines')
                        mw.gl_widget.addItem(stem_item)
                    # ---------------------------------------

            # --- NEW: RENDER FITTED 3D SURFACES ---
            if hasattr(mw, 'active_3d_fits') and mw.active_3d_fits:
                x_grid = np.linspace(mins[0], maxs[0], 100)
                y_grid = np.linspace(mins[1], maxs[1], 100)
                
                x_scaled = (x_grid - mins[0]) * scale_factors[0]
                y_scaled = (y_grid - mins[1]) * scale_factors[1]
                
                X, Y = np.meshgrid(x_grid, y_grid, indexing='ij')
                
                for fit in mw.active_3d_fits:
                    Z = fit["callable"]((X, Y), *fit["params"])
                    
                    # --- FIX 1: Sanitize NaNs and Infs to prevent OpenGL crashes ---
                    Z = np.nan_to_num(Z, nan=mins[2], posinf=maxs[2]*10, neginf=mins[2]*10)
                    # ---------------------------------------------------------------
                    
                    Z_scaled = (Z - mins[2]) * scale_factors[2]
                    
                    x_gl = np.ascontiguousarray(x_scaled, dtype=np.float32)
                    y_gl = np.ascontiguousarray(y_scaled, dtype=np.float32)
                    z_gl = np.ascontiguousarray(Z_scaled, dtype=np.float32)
                    
                    # --- FIX: Bright White Grid for Fits (No Shaders) ---
                    draw_grid = mw.gl_lighting_cb.isChecked()
                    
                    fit_surface = gl.GLSurfacePlotItem(
                        x=x_gl, y=y_gl, z=z_gl,
                        color=(0.1, 0.6, 1.0, 0.45), 
                        smooth=True, computeNormals=False, 
                        drawEdges=draw_grid, edgeColor=(1.0, 1.0, 1.0, 0.8) # Bright white net
                    )
                    mw.gl_widget.addItem(fit_surface)
                    
                    # Save a reference to the mesh so the "Clear Plot" button can delete it!
                    fit["plot_item"] = fit_surface 
                    # ----------------------------------------------------

            # --- REVEAL THE UI BUTTONS IN 3D MODE ---
            if hasattr(mw, 'active_3d_fits') and mw.active_3d_fits:
                if hasattr(mw, 'func_details_btn'): mw.func_details_btn.setVisible(True)
                if hasattr(mw, 'clear_fit_btn'): mw.clear_fit_btn.setVisible(True)
            # ----------------------------------------

            mw.gl_widget.opts['center'] = pg.Vector(5*sx, 5*sy, 5*sz) # Center camera on scaled data
            mw.gl_widget.setCameraPosition(distance=25*max(sx, sy, sz), elevation=25, azimuth=45)
            mw._init_3d_scene(bounds, (sx, sy, sz)) # Pass scales to the scene builder
            
        except Exception as e:
            import traceback
            QMessageBox.critical(mw, "Rendering Error", f"A fatal error occurred while drawing the 3D plot.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            mw._is_plotting = False
