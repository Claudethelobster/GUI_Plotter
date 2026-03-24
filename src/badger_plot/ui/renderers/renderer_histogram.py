# ui/renderers/renderer_histogram.py
import numpy as np
import pyqtgraph as pg
import matplotlib
from PyQt5.QtWidgets import QMessageBox

class RendererHistogram:
    @staticmethod
    def draw(mw, packages, show_legend=True):
        """
        Renders 1D array data as a binned histogram with statistical overlays.
        mw: Reference to the BadgerLoopQtGraph main window instance.
        """
        try:
            if hasattr(mw, 'progress_dialog'): mw.progress_dialog.accept()
            
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
            
            # ---> NEW: UNLOCK THE VIEWBOX (Fixes cropping) <---
            mw.plot_widget.getViewBox().setLimits(xMin=-np.inf, xMax=np.inf, yMin=-np.inf, yMax=np.inf)
            mw.plot_widget.enableAutoRange(axis='xy', enable=True)
            # --------------------------------------------------
            
            mw.legend.clear()
            mw.fit_legend.clear()
            mw.heatmap_image_item.setVisible(False)
            mw.heatmap_item.setVisible(False)
            
            added_to_legend = set()
            
            # Configure Axes
            mw.plot_widget.getAxis('bottom').setLabel("Bins")
            mw.plot_widget.getAxis('left').setLabel("Counts")
            mw.plot_widget.getAxis('right').hide()
            mw.plot_widget.getAxis('top').hide()
            mw.plot_widget.getAxis('bottom').set_custom_log(False, 10.0)
            mw.plot_widget.getAxis('left').set_custom_log(False, 10.0)
            
            # ---> NEW: FORCE DISABLE LOG MODE TO PREVENT BARGRAPHITEM CRASHES <---
            mw.plot_widget.setLogMode(x=False, y=False)
            # ---------------------------------------------------------------------
            
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
                
                # --- REVERT BACK TO CENTERS AND WIDTHS ---
                centers = (edges[:-1] + edges[1:]) / 2.0
                widths = edges[1:] - edges[:-1]
                # -----------------------------------------
                
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
                
                # --- NEW: RENDER THE STATS HUD ---
                stats = pkg.get("stats", {})
                if stats and hasattr(mw, 'toggle_stats_btn') and mw.toggle_stats_btn.isChecked():
                    # Calculate the mode visually from the highest bin
                    mode_idx = np.argmax(counts)
                    mode_val = centers[mode_idx]
                    
                    html = f"<b style='color: #0055ff; font-size: 14px;'>{y_name} Distribution</b><br><hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
                    html += f"<b>Count (N):</b>&nbsp;&nbsp;&nbsp;&nbsp;{stats['n']}<br>"
                    html += f"<b>Mean (&mu;):</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['mean']:.5g}<br>"
                    html += f"<b>Median:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['median']:.5g}<br>"
                    html += f"<b>Mode (Bin):</b>&nbsp;&nbsp;&nbsp;{mode_val:.5g}<br>"
                    html += f"<b>Std Dev (&sigma;):</b>&nbsp;&nbsp;{stats['std']:.5g}<br>"
                    html += f"<b>Range:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['min']:.5g} to {stats['max']:.5g}<br>"
                    html += f"<b>Skewness:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['skew']:.5g}<br>"
                    html += f"<b>Kurtosis:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['kurt']:.5g}"
                    
                    mw._last_hist_html = html
                    mw.stats_label.setText(html)
                    mw.stats_label.adjustSize()
                    if not mw.stats_label.isVisible():
                        mw.stats_label.move(15, 15)
                    mw.stats_label.show()
                    mw.stats_label.raise_()
                # ---------------------------------
                
            mw.plot_widget.getViewBox().autoRange(padding=0.1)
            
        except Exception as e:
            import traceback
            QMessageBox.critical(mw, "Rendering Error", f"A fatal error occurred while drawing the Histogram.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            mw._is_plotting = False
