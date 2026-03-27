# ui/renderers/renderer_2d.py
import numpy as np
import pyqtgraph as pg
import matplotlib
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt

class Renderer2D:
    @staticmethod
    def draw(mw, packages, show_legend):
        """
        Renders standard 2D curves, scatter plots, and error bars.
        mw: Reference to the BadgerLoopQtGraph main window instance.
        """
        mw.current_legend_entries = []
        
        # --- Route Histogram data to its dedicated renderer ---
        if getattr(mw, 'plot_mode', '2D') == "Histogram":
            mw._draw_histogram(packages, show_legend)
            return
        # -----------------------------------------------------------
        
        try:
            if hasattr(mw, 'progress_dialog'): mw.progress_dialog.accept()
            dummy_arr = np.array([0,0], dtype=np.float64)
            
            # 1. Clean up standard curves
            for c in mw.curve_pool:
                if type(c).__name__ == "PlotCurveItem":
                    c.setData(x=dummy_arr, y=dummy_arr)
                c.setVisible(False)
                try: mw.plot_widget.removeItem(c)
                except: pass
                try: mw.vb_right.removeItem(c)
                except: pass
                
            # 2. Clean up scatter points
            for s in mw.scatter_pool: 
                s.setData(x=dummy_arr, y=dummy_arr)
                s.setVisible(False)
                try: mw.plot_widget.removeItem(s)
                except: pass
                try: mw.vb_right.removeItem(s)
                except: pass
                
            # 3. Clean up error bars
            for eb in mw.errorbar_pool + mw.avg_error_pool: 
                eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
                try: mw.plot_widget.removeItem(eb)
                except: pass
                try: mw.vb_right.removeItem(eb)
                except: pass
                
            # 4. Safely wipe histogram bars if switching modes
            if hasattr(mw, 'bar_pool'):
                for b in mw.bar_pool:
                    try: mw.plot_widget.removeItem(b)
                    except: pass
                mw.bar_pool.clear()
                
            mw.legend.clear()
            mw.fit_legend.clear()
            mw.heatmap_image_item.setVisible(False)
            mw.heatmap_item.setVisible(False)
            
            mw.plot_widget.getViewBox().setLimits(xMin=-np.inf, xMax=np.inf, yMin=-np.inf, yMax=np.inf)
            if hasattr(mw, 'func_details_btn'): mw.func_details_btn.setVisible(False)
    
            mw.last_plotted_data = {'mode': '2D', 'packages': packages}
    
            xlog, ylog = mw.xscale.currentText() == "Log", mw.yscale.currentText() == "Log"
            xbase = getattr(mw, '_parse_log_base', lambda x: 10.0)(mw.xbase.text())
            ybase = getattr(mw, '_parse_log_base', lambda x: 10.0)(mw.ybase.text())
            
            mw.plot_widget.getAxis('bottom').set_custom_log(xlog, xbase)
            mw.plot_widget.getAxis('top').set_custom_log(xlog, xbase)
            mw.plot_widget.getAxis('left').set_custom_log(ylog, ybase)
            mw.plot_widget.getAxis('right').set_custom_log(ylog, ybase)
    
            try: pt_size = int(mw.point_size_edit.text())
            except ValueError: pt_size = 5

            left_pkgs = [p for p in packages if p.get("axis", "L") == "L"]
            right_pkgs = [p for p in packages if p.get("axis", "L") == "R"]
            has_right_axis = len(right_pkgs) > 0

            x_shared = False
            y_shared = False

            if has_right_axis and left_pkgs:
                if left_pkgs[0].get("x_name", "X") == right_pkgs[0].get("x_name", "X"): x_shared = True
                if left_pkgs[0].get("y_name", "Y") == right_pkgs[0].get("y_name", "Y"): y_shared = True
                    
            # --- Smart Axis & Text Coloring ---
            bg_val = mw.bg_color_combo.currentText()
            if bg_val == "Black":
                vis_color = '#ffffff'
                hid_color = '#000000'
            elif bg_val == "Transparent":
                vis_color = '#000000'
                hid_color = (0, 0, 0, 0)
            else: # White
                vis_color = '#000000'
                hid_color = '#ffffff'
            # ---------------------------------------

            main_vb = mw.plot_widget.getViewBox()
            mw.vb_right.setXLink(main_vb if x_shared else None)
            mw.vb_right.setYLink(main_vb if y_shared else None)
            
            bottom_axis = mw.plot_widget.getAxis('bottom')
            left_axis = mw.plot_widget.getAxis('left')
            right_axis = mw.plot_widget.getAxis('right')
            top_axis = mw.plot_widget.getAxis('top')
            
            mw.plot_widget.showAxis('right', show=True)
            mw.plot_widget.showAxis('top', show=True)
            
            # Lock the visible text colors for the primary axes
            bottom_axis.setTextPen(pg.mkPen(vis_color))
            left_axis.setTextPen(pg.mkPen(vis_color))
            
            if has_right_axis:
                if x_shared:
                    top_axis.linkToView(main_vb)
                    top_axis.setStyle(showValues=True)
                    top_axis.setTextPen(pg.mkPen(hid_color)) 
                else:
                    top_axis.linkToView(mw.vb_right)
                    top_axis.setStyle(showValues=True)
                    top_axis.setTextPen(pg.mkPen('#d90000')) 
                
                if y_shared:
                    right_axis.linkToView(main_vb)
                    right_axis.setStyle(showValues=True)
                    right_axis.setTextPen(pg.mkPen(hid_color)) 
                else:
                    right_axis.linkToView(mw.vb_right)
                    right_axis.setStyle(showValues=True)
                    right_axis.setTextPen(pg.mkPen('#d90000')) 
                    
                right_axis.setGrid(0)
                top_axis.setGrid(0)
            else:
                right_axis.linkToView(main_vb)
                top_axis.linkToView(main_vb)
                right_axis.setStyle(showValues=True) 
                top_axis.setStyle(showValues=True)
                # Blend the text into the background for a clean bounding box
                right_axis.setTextPen(pg.mkPen(hid_color)) 
                top_axis.setTextPen(pg.mkPen(hid_color))
                right_axis.setGrid(0)
                top_axis.setGrid(0)

            if packages:
                is_fft = getattr(mw, 'fft_mode_active', False)
                
                # Helper to safely extract HTML or fallback text
                def get_lbl(orient, default):
                    if is_fft: return default
                    saved = mw.custom_axis_labels.get(orient)
                    if isinstance(saved, dict): return saved.get("html", default)
                    return saved or default
                
                # Setup Bottom/Left Labels with correct main text color
                if left_pkgs:
                    default_x_l = left_pkgs[0].get("x_name", "X Axis") if len(set([p.get("x_name") for p in left_pkgs])) == 1 else "Bottom X"
                    mw.plot_widget.setLabel("bottom", get_lbl("bottom", default_x_l), color=vis_color)
                    
                    default_y_l = left_pkgs[0].get("y_name", "Y Axis") if len(set([p.get("y_name") for p in left_pkgs])) == 1 else "Left Values"
                    mw.plot_widget.setLabel("left", get_lbl("left", default_y_l), color=vis_color)
                else:
                    mw.plot_widget.setLabel("bottom", "")
                    mw.plot_widget.setLabel("left", "")
                    
                # Setup Top/Right Labels
                if right_pkgs:
                    if not x_shared:
                        default_x_r = right_pkgs[0].get("x_name", "X Axis") if len(set([p.get("x_name") for p in right_pkgs])) == 1 else "Top X"
                        mw.plot_widget.setLabel("top", get_lbl("top", default_x_r), color='#d90000')
                    else:
                        mw.plot_widget.setLabel("top", "") 
                        
                    if not y_shared:
                        default_y_r = right_pkgs[0].get("y_name", "Y Axis") if len(set([p.get("y_name") for p in right_pkgs])) == 1 else "Right Values"
                        mw.plot_widget.setLabel("right", get_lbl("right", default_y_r), color='#d90000')
                    else:
                        mw.plot_widget.setLabel("right", "") 
                else:
                    mw.plot_widget.setLabel("top", "")
                    mw.plot_widget.setLabel("right", "")

            total_plotted_sw = len(set(p.get("sw", 0) for p in packages))
            
            graphtype = mw.graphtype.currentText()
            
            try: line_thick = float(mw.line_thickness_edit.text())
            except: line_thick = 2.0
            
            sym_map = {"Circle (o)": "o", "Square (s)": "s", "Triangle (t)": "t", "Star (star)": "star", "Cross (+)": "+", "X (x)": "x"}
            sym = sym_map.get(mw.symbol_combo.currentText(), "o")
            
            curve_idx, scatter_idx, err_idx = 0, 0, 0
            
            active_pairs = [p for p in mw.series_data.get("2D", []) if p.get('visible', True)]
            num_active_pairs = len(active_pairs)
            added_to_legend = set()
            
            for pkg in packages:
                i = pkg.get("i", 0)
                sw = pkg.get("sw", "All")
                pair_idx = pkg.get("pair_idx", 0)
                
                y_name = pkg.get("y_name", "Y")
                cmap_name = pkg.get("cmap_name", "Blues")
                cmap = matplotlib.colormaps.get_cmap(cmap_name)
                axis_side = pkg.get("axis", "L")
                pkg_type = pkg.get("type", "standard")
                
                intensity = 0.8 if total_plotted_sw <= 1 else 0.4 + 0.6 * (i / max(1, total_plotted_sw - 1))
                rgba = cmap(intensity)
                line_color = (int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255), 255)
                
                original_pair = mw.series_data.get("2D", [])[pair_idx] if pair_idx < len(mw.series_data.get("2D", [])) else {}
                style = original_pair.get("style", {})
                
                trace_type = style.get("type", graphtype)
                
                try: line_thick = float(style.get("line_width", mw.line_thickness_edit.text() if mw.line_thickness_edit.text() else 2.0))
                except: line_thick = 2.0
                
                try: pt_size = int(style.get("symbol_size", mw.point_size_edit.text() if mw.point_size_edit.text().isdigit() else 5))
                except: pt_size = 5
                
                sym_raw = style.get("symbol", mw.symbol_combo.currentText())
                sym = sym_map.get(sym_raw, "o")
                
                pen_styles = {"Solid": Qt.PenStyle.SolidLine, "Dashed": Qt.PenStyle.DashLine, "Dotted": Qt.PenStyle.DotLine, "Dash-Dot": Qt.PenStyle.DashDotLine}
                pen_style = pen_styles.get(style.get("line_style", "Solid"), Qt.PenStyle.SolidLine)
                
                if style.get("color"):
                    from PyQt6.QtGui import QColor
                    c = QColor(style["color"])
                    line_color = (c.red(), c.green(), c.blue(), 255)
                    
                trace_pen = pg.mkPen(line_color, width=line_thick, style=pen_style)
                
                # --- SMART AUTO-NAMING ENGINE ---
                base_name = y_name
                
                if num_active_pairs > 1:
                    base_name = f"[P{pair_idx+1}] {base_name}"
                    
                if pkg_type == "average":
                    base_name += " (Average)"
                elif total_plotted_sw > 1 and not getattr(mw, 'group_sweeps_legend', False):
                    base_name += f" (Sweep {sw})"
                    
                if axis_side == "R":
                    base_name += " [R]"
                    
                if getattr(mw, 'group_sweeps_legend', False):
                    sig_key = f"{pair_idx}_GROUPED_{pkg_type}_{axis_side}"
                else:
                    sig_key = f"{pair_idx}_{sw}_{pkg_type}_{axis_side}"
                
                legend_name = mw.legend_aliases.get(sig_key, base_name)
                
                import re
                html_name = re.sub(r'\^([\w\.\-]+)', r'<sup>\1</sup>', legend_name)
                html_name = re.sub(r'_([\w\.\-]+)', r'<sub>\1</sub>', html_name)

                if not hasattr(mw, 'current_legend_entries'): mw.current_legend_entries = []
                if not any(e["sig_key"] == sig_key for e in mw.current_legend_entries):
                    mw.current_legend_entries.append({
                        "sig_key": sig_key, "base_name": base_name, 
                        "pen": trace_pen, 
                        "brush": pg.mkBrush(line_color), "symbol": sym
                    })
                
                target_vb = mw.vb_right if axis_side == "R" else mw.plot_widget
                
                def bind_double_click(label_item, key, current):
                    def on_click(ev):
                        if ev.double():
                            mw._prompt_legend_rename(key, current)
                            ev.accept()
                    label_item.mouseClickEvent = on_click
                
                if pkg["type"] == "average":
                    if scatter_idx >= len(mw.scatter_pool):
                        s = pg.ScatterPlotItem(pxMode=True)
                        mw.scatter_pool.append(s)
                        
                    scatter = mw.scatter_pool[scatter_idx]
                    target_vb.addItem(scatter)
                    
                    scatter.setData(x=np.array([pkg["x_mean"]], dtype=np.float64), 
                                    y=np.array([pkg["y_mean"]], dtype=np.float64), 
                                    size=pt_size + 3, pen=pg.mkPen(None), brush=pg.mkBrush(line_color), symbol=sym)
                    scatter.setVisible(True)
                    
                    if show_legend:
                        if sig_key not in added_to_legend:
                            mw.legend.addItem(scatter, html_name)
                            added_to_legend.add(sig_key)
                            sample, label_item = mw.legend.items[-1]
                            bind_double_click(label_item, sig_key, legend_name)
                        
                    scatter_idx += 1
                    
                    if "dx" in pkg and "dy" in pkg:
                        if err_idx >= len(mw.avg_error_pool):
                            eb = pg.ErrorBarItem()
                            mw.avg_error_pool.append(eb)
                            
                        err_item = mw.avg_error_pool[err_idx]
                        target_vb.addItem(err_item)
                        err_item.setData(x=np.array([pkg["x_mean"]]), y=np.array([pkg["y_mean"]]), 
                                         width=np.array([2*pkg["dx"]]), height=np.array([2*pkg["dy"]]), 
                                         pen=pg.mkPen(line_color, width=2))
                        err_item.setVisible(True)
                        err_idx += 1
                    
                elif pkg["type"] == "standard":
                    if "Line" in trace_type or trace_type == "FFT (Spectrum)":
                        if curve_idx >= len(mw.curve_pool):
                            c = pg.PlotCurveItem(connect="finite", autoDownsample=True)
                            mw.curve_pool.append(c)
                            
                        curve = mw.curve_pool[curve_idx]
                        target_vb.addItem(curve)
                        curve.setData(pkg["x"], pkg["y"], pen=trace_pen) 
                        curve.setVisible(True)
                        
                        if show_legend and "Scatter" not in trace_type:
                            if sig_key not in added_to_legend:
                                if getattr(mw, 'group_sweeps_legend', False) or len(added_to_legend) < 50:
                                    mw.legend.addItem(curve, html_name)
                                    added_to_legend.add(sig_key)
                                    sample, label_item = mw.legend.items[-1]
                                    bind_double_click(label_item, sig_key, legend_name)
                                
                        curve_idx += 1
                        
                    if "Scatter" in trace_type:
                        if scatter_idx >= len(mw.scatter_pool):
                            s = pg.ScatterPlotItem(pxMode=True)
                            mw.scatter_pool.append(s)
                            
                        scatter = mw.scatter_pool[scatter_idx]
                        target_vb.addItem(scatter)
                        
                        x_pts, y_pts = np.asarray(pkg["x"]), np.asarray(pkg["y"])
                        valid = np.isfinite(x_pts) & np.isfinite(y_pts)
                        scatter.setData(x=x_pts[valid], y=y_pts[valid], size=pt_size, pen=pg.mkPen(None), brush=pg.mkBrush(line_color), symbol=sym)
                        scatter.setVisible(True) 
                        
                        if show_legend:
                            if sig_key not in added_to_legend:
                                if getattr(mw, 'group_sweeps_legend', False) or len(added_to_legend) < 50:
                                    if "Line" in trace_type:
                                        proxy = pg.PlotDataItem(pen=trace_pen, symbol=sym, symbolBrush=pg.mkBrush(line_color), symbolSize=pt_size)
                                        mw.legend.addItem(proxy, html_name)
                                    else:
                                        mw.legend.addItem(scatter, html_name)
                                        
                                    added_to_legend.add(sig_key)
                                    sample, label_item = mw.legend.items[-1]
                                    bind_double_click(label_item, sig_key, legend_name)
                                
                        scatter_idx += 1

            if hasattr(mw, 'active_fits') and mw.active_fits:
                for fit in mw.active_fits:
                    if "x_raw" in fit and "y_raw" in fit:
                        x_raw, y_raw = fit["x_raw"], fit["y_raw"]
                        with np.errstate(divide='ignore', invalid='ignore'):
                            x_vis_new = np.log(x_raw) / np.log(xbase) if xlog else x_raw
                            y_vis_new = np.log(y_raw) / np.log(ybase) if ylog else y_raw
                            
                        valid = np.isfinite(x_vis_new) & np.isfinite(y_vis_new)
                        if xlog: valid &= (x_raw > 0)
                        if ylog: valid &= (y_raw > 0)
                        
                        mw.plot_widget.addItem(fit["plot_item"]) 
                        fit["plot_item"].setData(x_vis_new[valid], y_vis_new[valid])
                    
                    mw.fit_legend.addItem(fit["plot_item"], fit["name"])
                
                if hasattr(mw, 'func_details_btn'): mw.func_details_btn.setVisible(True)
                if hasattr(mw, 'save_function_btn'): mw.save_function_btn.setVisible(True)
                if hasattr(mw, 'clear_fit_btn'): mw.clear_fit_btn.setVisible(True)
                if hasattr(mw, 'edit_fit_btn'): mw.edit_fit_btn.setVisible(True)
             
            mw._apply_canvas_settings()
            mw._apply_axis_fonts()
            mw.plot_widget.getViewBox().autoRange()
            mw.vb_right.autoRange()

            try:
                mw.plot_widget.removeItem(mw.selection_curve)
                mw.plot_widget.removeItem(mw.highlight_scatter)
            except: pass
            
            mw.plot_widget.addItem(mw.selection_curve, ignoreBounds=True)
            mw.plot_widget.addItem(mw.highlight_scatter)
            mw.selection_curve.setZValue(1000)
            mw.highlight_scatter.setZValue(1001)
            
            if getattr(mw, 'selected_indices', set()):
                x_vis, y_vis, _, _ = mw._get_all_plotted_xy(apply_selection=False)
                idx_array = [i for i in list(mw.selected_indices) if i < len(x_vis)]
                if idx_array:
                    mw.highlight_scatter.setData(x_vis[idx_array], y_vis[idx_array])
                    mw.highlight_scatter.show()
                else:
                    mw.clear_selection()

            mw._apply_legend_live()

        except Exception as e:
            import traceback
            QMessageBox.critical(mw, "Rendering Error", f"A fatal error occurred while drawing the 2D plot.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            mw._is_plotting = False
