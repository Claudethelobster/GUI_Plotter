# ui/renderers/renderer_histogram.py
import numpy as np
import pyqtgraph as pg
import matplotlib
import re
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer
from core.theme import theme

class RendererHistogram:
    @staticmethod
    def draw(mw, packages, show_legend=True):
        """
        Renders 1D array data as a binned histogram with statistical overlays.
        mw: Reference to the BadgerLoopQtGraph main window instance.
        """
        mw.current_legend_entries = [] # Required for the Legend Customiser Dialog
        
        # --- INCORPORATED THE GHOST DIALOG KILLER ---
        if getattr(mw, 'progress_dialog', None) is not None:
            try:
                mw.progress_dialog.setValue(mw.progress_dialog.maximum())
                mw.progress_dialog.hide()
                QTimer.singleShot(0, mw.progress_dialog.close)
            except: pass
        # --------------------------------------------
        
        try:
            # 1. Safely clear old lines, scatters, error bars
            dummy_arr = np.array([], dtype=np.float64)
            for pool_name in ['curve_pool', 'scatter_pool']:
                for item in getattr(mw, pool_name, []):
                    if hasattr(item, 'setData'): item.setData(x=dummy_arr, y=dummy_arr)
                    item.setVisible(False)
                    try: mw.plot_widget.removeItem(item)
                    except: pass
                    
            for eb in getattr(mw, 'errorbar_pool', []) + getattr(mw, 'avg_error_pool', []):
                if hasattr(eb, 'setData'): eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
                try: mw.plot_widget.removeItem(eb)
                except: pass
                
            # 2. Clear previous histogram bars
            if not hasattr(mw, 'bar_pool'): mw.bar_pool = []
            for b in mw.bar_pool:
                try: mw.plot_widget.removeItem(b)
                except: pass
            mw.bar_pool.clear()
            
            # UNLOCK THE VIEWBOX (Fixes cropping, keeps panning free)
            mw.plot_widget.getViewBox().setLimits(xMin=-np.inf, xMax=np.inf, yMin=-np.inf, yMax=np.inf)
            mw.plot_widget.enableAutoRange(axis='xy', enable=True)
            
            mw.legend.clear()
            mw.fit_legend.clear()
            mw.heatmap_image_item.setVisible(False)
            mw.heatmap_item.setVisible(False)
            
            mw._apply_canvas_settings()
            added_to_legend = set()
            
            # Determine dynamic colours for the neat bounding box
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
            
            # Configure Axes
            mw.plot_widget.getAxis('bottom').setLabel("Bins")
            mw.plot_widget.getAxis('left').setLabel("Counts")
            mw.plot_widget.getAxis('right').setLabel("")
            mw.plot_widget.getAxis('top').setLabel("")
            
            # Show all 4 axes to create the bounding box
            mw.plot_widget.showAxis('right', show=True)
            mw.plot_widget.showAxis('top', show=True)
            
            main_vb = mw.plot_widget.getViewBox()
            mw.plot_widget.getAxis('right').linkToView(main_vb)
            mw.plot_widget.getAxis('top').linkToView(main_vb)
            
            mw.plot_widget.getAxis('bottom').set_custom_log(False, 10.0)
            mw.plot_widget.getAxis('left').set_custom_log(False, 10.0)
            
            mw._apply_axis_fonts()
            
            try: axis_thick = mw.axis_thick_slider.value()
            except: axis_thick = 1
            
            # Apply visible colours to all lines to create the neat box
            mw.plot_widget.getAxis('bottom').setPen(pg.mkPen(vis_colour, width=axis_thick))
            mw.plot_widget.getAxis('left').setPen(pg.mkPen(vis_colour, width=axis_thick))
            mw.plot_widget.getAxis('top').setPen(pg.mkPen(vis_colour, width=axis_thick))
            mw.plot_widget.getAxis('right').setPen(pg.mkPen(vis_colour, width=axis_thick))
            
            # Hide the numbers and ticks on the top and right
            mw.plot_widget.getAxis('top').setTextPen(pg.mkPen(hid_colour))
            mw.plot_widget.getAxis('right').setTextPen(pg.mkPen(hid_colour))
            
            # Ensure bottom and left numbers remain visible
            mw.plot_widget.getAxis('bottom').setTextPen(pg.mkPen(vis_colour))
            mw.plot_widget.getAxis('left').setTextPen(pg.mkPen(vis_colour))
            
            # FORCE DISABLE LOG MODE TO PREVENT BARGRAPHITEM CRASHES
            mw.plot_widget.setLogMode(x=False, y=False)
            
            mw.last_plotted_data = {'mode': 'Histogram', 'packages': []}
    
            # 3. Draw the Distributions
            for pkg in packages:
                i = pkg.get("i", 0)
                sw = pkg.get("sw", "All")
                pair_idx = pkg.get("pair_idx", 0)
                y_name = pkg.get("y_name", "Y")
                axis_side = pkg.get("axis", "L")
                
                counts = pkg.get("counts", [])
                edges = pkg.get("bin_edges", [])
                if len(counts) == 0: continue
                
                # REVERT BACK TO CENTERS AND WIDTHS
                centers = (edges[:-1] + edges[1:]) / 2.0
                widths = edges[1:] - edges[:-1]
                
                # Colors
                cmap_name = pkg.get("cmap_name", "Blues")
                cmap = matplotlib.colormaps.get_cmap(cmap_name)
                rgba = cmap(0.5) 
                border_rgba = cmap(0.9) 
                
                fill_color = (int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255), int(rgba[3]*255))
                border_color = (int(border_rgba[0]*255), int(border_rgba[1]*255), int(border_rgba[2]*255), 255)
                
                # Draw the bars
                bg = pg.BarGraphItem(x=centers, height=counts, width=widths, brush=pg.mkBrush(fill_color), pen=pg.mkPen(border_color, width=1.5))
                mw.plot_widget.addItem(bg)
                mw.bar_pool.append(bg)
                
                # 4. Smart Legend Logic
                sig_key = f"{pair_idx}_{sw}_histogram_{axis_side}"
                base_name = f"{y_name} Distribution"
                if sw != "All": base_name += f" (Sw {sw})"
                
                legend_name = mw.legend_aliases.get(sig_key, base_name)
                
                if show_legend and legend_name not in added_to_legend:
                    proxy_scatter = pg.ScatterPlotItem(pen=pg.mkPen(border_color, width=2), brush=pg.mkBrush(fill_color), size=12, symbol='s')
                    mw.legend.addItem(proxy_scatter, legend_name)
                    added_to_legend.add(legend_name)
                    
                    # Store data for the legend customiser dialog
                    if not any(e["sig_key"] == sig_key for e in mw.current_legend_entries):
                        mw.current_legend_entries.append({
                            "sig_key": sig_key, "base_name": base_name, 
                            "pen": pg.mkPen(border_color, width=2), 
                            "brush": pg.mkBrush(fill_color), "symbol": 's'
                        })
                    
                    sample, label_item = mw.legend.items[-1]
                    def bind_double_click(label, key, current):
                        def on_click(ev):
                            if ev.double():
                                mw._prompt_legend_rename(key, current)
                                ev.accept()
                        label.mouseClickEvent = on_click
                    bind_double_click(label_item, sig_key, legend_name)
                    
                # 5. Connect to Gaussian Fitter
                mw.last_plotted_data['packages'].append({
                    "type": "standard", 
                    "pair_idx": pair_idx,
                    "x": centers,
                    "y": counts,
                    "x_name": f"Binned {y_name}",
                    "y_name": "Counts",
                    "axis": axis_side
                })
                
                # RENDER THE STATS HUD
                stats = pkg.get("stats", {})
                if stats and hasattr(mw, 'toggle_stats_btn') and mw.toggle_stats_btn.isChecked():
                    mode_idx = np.argmax(counts)
                    mode_val = centers[mode_idx]
                    
                    html = f"<b style='color: {theme.primary_text}; font-size: 14px;'>{y_name} Distribution</b><br><hr style='border: 0; border-top: 1px solid {theme.border}; margin: 4px 0;'>"
                    html += f"<span style='color: {theme.fg};'>"
                    html += f"<b>Count (N):</b>&nbsp;&nbsp;&nbsp;&nbsp;{stats['n']}<br>"
                    html += f"<b>Mean (&mu;):</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['mean']:.5g}<br>"
                    html += f"<b>Median:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['median']:.5g}<br>"
                    html += f"<b>Mode (Bin):</b>&nbsp;&nbsp;&nbsp;{mode_val:.5g}<br>"
                    html += f"<b>Std Dev (&sigma;):</b>&nbsp;&nbsp;{stats['std']:.5g}<br>"
                    html += f"<b>Range:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['min']:.5g} to {stats['max']:.5g}<br>"
                    html += f"<b>Skewness:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['skew']:.5g}<br>"
                    html += f"<b>Kurtosis:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['kurt']:.5g}"
                    html += "</span>"
                    
                    mw._last_hist_html = html
                    mw.stats_label.setText(html)
                    mw.stats_label.adjustSize()
                    if not mw.stats_label.isVisible():
                        mw.stats_label.move(15, 15)
                    mw.stats_label.show()
                    mw.stats_label.raise_()
            
            # --- INCORPORATED CDF / FITS RENDERER ---
            if hasattr(mw, 'active_fits') and mw.active_fits:
                for fit in mw.active_fits:
                    if "x_raw" in fit and "y_raw" in fit:
                        x_raw, y_raw = fit["x_raw"], fit["y_raw"]
                        target_vb = mw.vb_right if fit.get("axis") == "R" else mw.plot_widget
                        
                        if fit.get("plot_item") not in target_vb.addedItems:
                            target_vb.addItem(fit["plot_item"]) 
                            
                        fit["plot_item"].setData(x_raw, y_raw)
                    
                    mw.fit_legend.addItem(fit["plot_item"], fit["name"])
                
                if hasattr(mw, 'func_details_btn'): mw.func_details_btn.setVisible(True)
                if hasattr(mw, 'save_function_btn'): mw.save_function_btn.setVisible(True)
                if hasattr(mw, 'clear_fit_btn'): mw.clear_fit_btn.setVisible(True)
                if hasattr(mw, 'edit_fit_btn'): mw.edit_fit_btn.setVisible(True)
            # ----------------------------------------
            
            mw.plot_widget.getViewBox().autoRange(padding=0.1)
            
            # Re-apply any visual legend overrides immediately
            mw._apply_legend_live()
            
        except Exception as e:
            import traceback
            QMessageBox.critical(mw, "Rendering Error", f"A fatal error occurred while drawing the Histogram.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            mw._is_plotting = False
            # --- INCORPORATED FINAL GHOST DIALOG FALLBACK ---
            if getattr(mw, 'progress_dialog', None) is not None:
                try:
                    mw.progress_dialog.hide()
                    QTimer.singleShot(0, mw.progress_dialog.close)
                except: pass
            # ------------------------------------------------
