# ui/renderers/heatmap_renderer.py
import numpy as np
import pyqtgraph as pg
import matplotlib
from PyQt6.QtWidgets import QMessageBox

class HeatmapRenderer:
    @staticmethod
    def draw(mw, res_dict):
        """
        Renders 2D array data as a colour-mapped heatmap.
        mw: Reference to the BadgerLoopQtGraph main window instance.
        """
        try:
            if hasattr(mw, 'progress_dialog'): mw.progress_dialog.accept()
            if not res_dict: return
                
            # 1. Safely wipe other plot types off the canvas
            dummy_arr = np.array([0.0], dtype=np.float32)
            for c in mw.curve_pool: 
                c.setData(x=dummy_arr, y=dummy_arr)
                c.setVisible(False)
            for s in mw.scatter_pool: 
                s.setData(x=dummy_arr, y=dummy_arr)
                s.setVisible(False)
            for eb in mw.errorbar_pool: 
                eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
            for ac in mw.avg_error_pool: 
                ac.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                ac.setVisible(False)

            mw.legend.hide()
            mw.heatmap_item.setVisible(True) 
            mw.heatmap_image_item.setVisible(True)
            
            # Force the canvas to update its background colour
            mw._apply_canvas_settings()
            
            # 2. Configure axes and labels
            pair = mw.series_data[mw.plot_mode][0] if mw.series_data.get(mw.plot_mode) else {}
            mw.plot_widget.setLabel("bottom", pair.get("x_name", "X"))
            mw.plot_widget.setLabel("left", pair.get("y_name", "Y"))
            
            xlog = mw.xscale.currentText() == "Log"
            ylog = mw.yscale.currentText() == "Log"
            zlog = mw.zscale.currentText() == "Log"
            
            xbase = getattr(mw, '_parse_log_base', lambda x: 10.0)(mw.xbase.text())
            ybase = getattr(mw, '_parse_log_base', lambda x: 10.0)(mw.ybase.text())
            zbase = getattr(mw, '_parse_log_base', lambda x: 10.0)(mw.zbase.text())
            
            mw.plot_widget.getAxis('bottom').set_custom_log(xlog, xbase)
            mw.plot_widget.getAxis('top').set_custom_log(xlog, xbase)
            mw.plot_widget.getAxis('left').set_custom_log(ylog, ybase)
            mw.plot_widget.getAxis('right').set_custom_log(ylog, ybase)
            
            # --- FIX: Dynamic text and bounding box colours ---
            bg_val = mw.bg_color_combo.currentText()
            is_dark = mw.settings.value("dark_mode", False, bool)
            
            if bg_val == "Black":
                vis_colour = 'w'
                hid_colour = 'k'
            elif bg_val == "Transparent":
                vis_colour = 'w' if is_dark else 'k'
                hid_colour = (0, 0, 0, 0)
            else: # White
                vis_colour = 'k'
                hid_colour = 'w'
                
            mw.heatmap_item.axis.setLabel(res_dict.get("z_axis_name", "Z"), color=vis_colour)
            mw.heatmap_item.axis.set_custom_log(zlog, zbase)
            
            # Let the main window do its general font updates first...
            mw._apply_axis_fonts()
            
            # ... then explicitly override the pens to blend the top/right axes away,
            # and strictly enforce the visible text colour on the tick numbers!
            try: axis_thick = mw.axis_thick_slider.value()
            except: axis_thick = 1
            
            # 1. Set the physical line colours
            mw.plot_widget.getAxis('bottom').setPen(pg.mkPen(vis_colour, width=axis_thick))
            mw.plot_widget.getAxis('left').setPen(pg.mkPen(vis_colour, width=axis_thick))
            mw.plot_widget.getAxis('top').setPen(pg.mkPen(vis_colour, width=axis_thick))
            mw.plot_widget.getAxis('right').setPen(pg.mkPen(vis_colour, width=axis_thick))
            
            # 2. Set the tick number colours (This fixes the numbers!)
            mw.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(vis_colour))
            mw.plot_widget.getAxis('left').setTextPen(pg.mkPen(vis_colour))
            mw.heatmap_item.axis.setTextPen(pg.mkPen(vis_colour)) # Z-axis numbers
            
            mw.plot_widget.getAxis('top').setTextPen(pg.mkPen(hid_colour))
            mw.plot_widget.getAxis('right').setTextPen(pg.mkPen(hid_colour))
            # ----------------------------------------------------
            
            # 3. Inject the Data
            img_data = res_dict["img_data"]
            x_min, x_max = res_dict["x_min"], res_dict["x_max"]
            y_min, y_max = res_dict["y_min"], res_dict["y_max"]
            z_min, z_max = res_dict["z_min"], res_dict["z_max"]
            
            mw.heatmap_image_item.setImage(img_data)
            
            # 4. Apply Colormap
            try: mw.heatmap_item.gradient.setColorMap(pg.colormap.get(mw.heatmap_cmap.currentText(), source='matplotlib'))
            except: mw.heatmap_item.gradient.loadPreset('viridis')
            
            rect_w = x_max - x_min if x_max > x_min else 1.0
            rect_h = y_max - y_min if y_max > y_min else 1.0
            mw.heatmap_image_item.setRect(pg.QtCore.QRectF(x_min, y_min, rect_w, rect_h))
            
            mw.heatmap_item.setLevels(z_min, z_max)
            mw.plot_widget.autoRange(padding=0)
            mw.plot_widget.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)
            mw.plot_widget.getViewBox().setRange(xRange=[x_min, x_max], yRange=[y_min, y_max], padding=0)
            
        except Exception as e:
            import traceback
            QMessageBox.critical(mw, "Rendering Error", f"A fatal error occurred while drawing the Heatmap.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            mw._is_plotting = False
