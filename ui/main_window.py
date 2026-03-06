# ui/main_window.py
import os
import sys
import json
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pgexp
from PyQt5.QtCore import Qt, QSettings, QTimer, QEvent
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QComboBox, QStackedLayout, 
    QMessageBox, QProgressDialog, QListWidget, QAction, QGridLayout, 
    QButtonGroup, QApplication, QDialog, QFormLayout
)

# Core imports
from core.data_loader import DataLoaderThread, CSVDataset, Dataset, BADGERLOOP_AVAILABLE
from core.plot_worker import PlotWorkerThread
from core.constants import PHYSICS_CONSTANTS, GREEK_MAP

# UI Component imports
from ui.custom_widgets import CustomAxisItem, DraggableLabel
from ui.dialogs.data_mgmt import (
    FileImportDialog, SweepTableDialog, ManageColumnsDialog, 
    MetadataDialog, CreateColumnDialog, CopyableErrorDialog
)
from ui.dialogs.analysis import SignalProcessingDialog, PhaseSpaceDialog, PeakFinderTool
from ui.dialogs.fitting import (
    FitFunctionDialog, CustomFitDialog, MultiFitManagerDialog, FitDataToFunctionWindow
)
from ui.dialogs.help import HelpDialog

try:
    import pyqtgraph.opengl as gl
    OPENGL_AVAILABLE = True
except Exception:
    OPENGL_AVAILABLE = False


class BadgerLoopQtGraph(QMainWindow):
    def __init__(self):
        super().__init__()
        self.series_data = {"2D": [], "3D": [], "Heatmap": []}
        self.settings = QSettings("BadgerLoop", "QtPlotter")
    
        self.dataset = None
        self.last_file = None
        self.legend_visible = True
        self.plot_mode = "2D"  
        self.fft_mode_active = False 
        
        axis_dict = {
            'bottom': CustomAxisItem('bottom'),
            'left': CustomAxisItem('left'),
            'top': CustomAxisItem('top'),
            'right': CustomAxisItem('right')
        }
        
        self.custom_axis_labels = {"bottom": None, "left": None, "top": None, "right": None}
        for ax_name, ax_obj in axis_dict.items():
            ax_obj.labelDoubleClicked.connect(self._prompt_custom_axis_label)
        
        self.plot_widget = pg.PlotWidget(axisItems=axis_dict)
        self.plot_widget.getViewBox().installEventFilter(self)
        
        self.vb_right = pg.ViewBox()
        self.vb_right.installEventFilter(self)
        self.plot_widget.scene().addItem(self.vb_right)
        
        def updateViews():
            self.vb_right.setGeometry(self.plot_widget.getViewBox().sceneBoundingRect())
            
        self.plot_widget.getViewBox().sigResized.connect(updateViews)
        
        self.plot_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(self.plot_wrapper)
        wrapper_layout.setAlignment(Qt.AlignCenter)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.plot_widget)
        
        if OPENGL_AVAILABLE:
            try:
                import pyqtgraph.opengl.shaders as gl_shaders
                gl_shaders.ShaderProgram.compiled.clear()
            except Exception: pass
            
            self.gl_widget = gl.GLViewWidget()
            self.gl_widget.setBackgroundColor('k')
        else:
            self.gl_widget = None
            
        self.plot_stack = QWidget()
        
        self.original_plot_stack_resize = self.plot_stack.resizeEvent
        self.plot_stack.resizeEvent = self._on_plot_stack_resize
        
        self.plot_layout = QStackedLayout(self.plot_stack)
        self.plot_layout.addWidget(self.plot_wrapper) 
        
        if self.gl_widget:
            self.plot_layout.addWidget(self.gl_widget)
            
        self.zcol = None
    
        self.setWindowTitle("BadgerLoop Data Plotter")
        self.resize(1200, 800)
        self.errorbars_enabled = False
        self.file_type = "BadgerLoop"
        self.csv_uncerts_enabled = False
        self.errorbar_nsigma = 1.0
        self.current_fit = None
        self.save_function_btn = None
        self.clear_fit_btn = None
    
        self._build_menu()
        
        if OPENGL_AVAILABLE:
            self.plot_3d_action.setEnabled(True)
            
        self._build_ui()
        self._apply_styles()
        self._fix_graphics_view()
        self._patch_pyqtgraph_menu()
        self.restore_state()
        
        if not BADGERLOOP_AVAILABLE:
            QTimer.singleShot(100, self.show_missing_library_warning)
    
        self._update_xscale_ui()
        self._update_yscale_ui()
        
    def show_missing_library_warning(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Missing BadgerLoop Library")
        msg.setIcon(QMessageBox.Warning)
        msg.setText("The 'badger_loop_py3_2.py' library was not found in the same directory as this script.")
        msg.setInformativeText(
            "The program will run in CSV-only mode. All BadgerLoop-specific file formats and metadata features have been disabled.\n\n"
            "To enable full functionality, please place 'badger_loop_py3_2.py' in the same folder and restart the program."
        )
        
        btn_continue = msg.addButton("Run in CSV Mode", QMessageBox.AcceptRole)
        btn_close = msg.addButton("Close Program", QMessageBox.RejectRole)
        msg.exec()
        
        if msg.clickedButton() == btn_close:
            self.close()

    def update_active_layer(self):
        if getattr(self, 'plot_mode', '2D') != "2D": return
        if hasattr(self, 'clear_selection'): self.clear_selection()
        
        row = self.series_list.currentRow()
        if row < 0: return
        
        try:
            pair = self.series_data["2D"][row]
            if pair.get("axis", "L") == "R":
                self.vb_right.setZValue(100)
                self.plot_widget.getViewBox().setZValue(0)
            else:
                self.vb_right.setZValue(0)
                self.plot_widget.getViewBox().setZValue(100)
        except IndexError: pass

    def _post_init_plot(self):
        if self.dataset: self.plot()
            
    def update_file_mode_ui(self):
        is_bl = self.file_type == "BadgerLoop"
        is_csv = self.file_type == "CSV"
        
        self.show_metadata_btn.setVisible(True)
        self.toggle_avg_btn.setVisible(is_bl)
        self.sweeps_label.setVisible(is_bl)
        self.sweeps_edit.setVisible(is_bl)
        
        if hasattr(self, 'inspect_table_action'):
            self.inspect_table_action.setText("Sweep table" if is_bl else "Inspect data table")
        
        if is_csv:
            self.errorbar_btn.setVisible(False)
            self.errorbar_sigma_edit.setVisible(False)
            self.average_enabled = False 
            self.errorbars_enabled = False
            
        self.toggle_uncert_btn.setVisible(is_csv)
        self._update_uncert_visibility()
        
    def toggle_csv_uncertainties(self):
        self.csv_uncerts_enabled = not self.csv_uncerts_enabled
        self._update_uncert_visibility()
        self.plot()
        
    def _update_uncert_visibility(self):
        show = (self.file_type == "CSV" and self.csv_uncerts_enabled)
        self.xuncert_label.setVisible(show)
        self.xuncert.setVisible(show)
        self.yuncert_label.setVisible(show)
        self.yuncert.setVisible(show)
        
        show_z = show and (self.plot_mode != "2D")
        self.zuncert_label.setVisible(show_z)
        self.zuncert.setVisible(show_z)
        
    def _create_series_list_item(self, row_idx):
        pair = self.series_data[self.plot_mode][row_idx]
        text = f"{pair['y_name']} vs {pair['x_name']}"
        is_visible = pair.get('visible', True)
        axis_side = pair.get('axis', 'L')
        
        from PyQt5.QtWidgets import QListWidgetItem
        item = QListWidgetItem(self.series_list)
        self.series_list.addItem(item)
        
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        
        label = QLabel(text)
        
        if self.plot_mode == "2D":
            btn_eye = QPushButton("👁")
            btn_eye.setFixedSize(26, 26)
            btn_eye.setCursor(Qt.PointingHandCursor)
            
            btn_axis = QPushButton(axis_side)
            btn_axis.setFixedSize(26, 26)
            btn_axis.setCursor(Qt.PointingHandCursor)
            btn_axis.setToolTip("Toggle Left / Right Y-Axis")
            
            if is_visible:
                btn_eye.setStyleSheet("border: none; font-size: 16px; color: #333; text-decoration: none;")
                label.setStyleSheet("color: black; text-decoration: none;")
            else:
                btn_eye.setStyleSheet("border: none; font-size: 16px; color: #aaa; text-decoration: line-through;")
                label.setStyleSheet("color: #aaa; text-decoration: line-through;")
                
            if axis_side == 'L':
                btn_axis.setStyleSheet("border: 1px solid #aaa; font-weight: bold; color: #0055ff; background: #e6f0ff;")
            else:
                btn_axis.setStyleSheet("border: 1px solid #aaa; font-weight: bold; color: #d90000; background: #ffe6e6;")
                
            layout.addWidget(btn_eye)
            layout.addWidget(btn_axis)
            
            btn_eye.clicked.connect(lambda checked, r=item: self._toggle_series_visibility(r))
            btn_axis.clicked.connect(lambda checked, r=item: self._toggle_series_axis(r))
        else:
            label.setStyleSheet("color: black; text-decoration: none;")
            
        layout.addWidget(label)
        layout.addStretch()
        
        item.setSizeHint(widget.sizeHint())
        self.series_list.setItemWidget(item, widget)

    def _toggle_series_axis(self, item):
        row = self.series_list.row(item)
        if row < 0: return
        pair = self.series_data[self.plot_mode][row]
        
        pair['axis'] = 'R' if pair.get('axis', 'L') == 'L' else 'L'
        
        widget = self.series_list.itemWidget(item)
        btns = widget.findChildren(QPushButton)
        if len(btns) > 1:
            btn_axis = btns[1]
            btn_axis.setText(pair['axis'])
            if pair['axis'] == 'L':
                btn_axis.setStyleSheet("border: 1px solid #aaa; font-weight: bold; color: #0055ff; background: #e6f0ff;")
            else:
                btn_axis.setStyleSheet("border: 1px solid #aaa; font-weight: bold; color: #d90000; background: #ffe6e6;")
                
        self.plot()
        self.update_active_layer()

    def _toggle_series_visibility(self, item):
        row = self.series_list.row(item)
        if row < 0: return
        pair = self.series_data[self.plot_mode][row]
        
        pair['visible'] = not pair.get('visible', True)
        is_visible = pair['visible']
        
        widget = self.series_list.itemWidget(item)
        btn = widget.findChild(QPushButton)
        label = widget.findChild(QLabel)
        
        if is_visible:
            btn.setStyleSheet("border: none; font-size: 16px; color: #333; text-decoration: none;")
            label.setStyleSheet("color: black; text-decoration: none;")
        else:
            btn.setStyleSheet("border: none; font-size: 16px; color: #aaa; text-decoration: line-through;")
            label.setStyleSheet("color: #aaa; text-decoration: line-through;")
            
        self.plot()
        
    def _set_interaction_mode(self, btn):
        text = btn.text()
        if "Pan" in text:
            self.interaction_mode = "pan"
            self.plot_widget.getViewBox().setMouseEnabled(x=True, y=True)
        else:
            self.interaction_mode = "box" if "Box" in text else "lasso"
            self.plot_widget.getViewBox().setMouseEnabled(x=False, y=False)

        active_style = "background-color: #d0e8ff; border: 2px solid #0078d7; font-weight: bold; border-radius: 4px; padding: 6px; color: #003366;"
        inactive_style = "background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 6px; color: black;"

        for b in [self.btn_pan, self.btn_box, self.btn_lasso]:
            if b.isChecked(): b.setStyleSheet(active_style)
            else: b.setStyleSheet(inactive_style)

    def eventFilter(self, source, event):
        if source == self.plot_widget.getViewBox() or source == getattr(self, 'vb_right', None):
            if getattr(self, 'interaction_mode', 'pan') != "pan" and self.plot_mode == "2D":
                if event.type() == QEvent.GraphicsSceneMousePress and event.button() == Qt.LeftButton:
                    self._start_selection(event)
                    return True 
                elif event.type() == QEvent.GraphicsSceneMouseMove and getattr(self, '_is_selecting', False):
                    self._drag_selection(event)
                    return True
                elif event.type() == QEvent.GraphicsSceneMouseRelease and event.button() == Qt.LeftButton and getattr(self, '_is_selecting', False):
                    self._end_selection(event)
                    return True
        return super().eventFilter(source, event)

    def _start_selection(self, event):
        self._is_selecting = True
        pos = self.plot_widget.getViewBox().mapSceneToView(event.scenePos())
        self._sel_start_pt = (pos.x(), pos.y())
        self._sel_path = [self._sel_start_pt]
        self.selection_curve.setData([], [])
        self.selection_curve.show()
        
    def _drag_selection(self, event):
        pos = self.plot_widget.getViewBox().mapSceneToView(event.scenePos())
        curr_pt = (pos.x(), pos.y())
        
        if self.interaction_mode == "lasso":
            self._sel_path.append(curr_pt)
            xs = [p[0] for p in self._sel_path]
            ys = [p[1] for p in self._sel_path]
            self.selection_curve.setData(xs, ys)
        elif self.interaction_mode == "box":
            self._sel_path = [self._sel_start_pt, curr_pt] 
            x0, y0 = self._sel_start_pt
            x1, y1 = curr_pt
            xs = [x0, x1, x1, x0, x0]
            ys = [y0, y0, y1, y1, y0]
            self.selection_curve.setData(xs, ys)
            
    def _end_selection(self, event):
        self._is_selecting = False
        self.selection_curve.hide() 
        
        x_vis, y_vis, _, _ = self._get_all_plotted_xy(apply_selection=False)
        if len(x_vis) == 0: return
        
        row = self.series_list.currentRow()
        is_right_active = False
        if row >= 0 and self.series_data.get("2D"):
            if self.series_data["2D"][row].get("axis", "L") == "R":
                is_right_active = True

        math_path = []
        for px, py in self._sel_path:
            if is_right_active:
                scene_pt = self.plot_widget.getViewBox().mapViewToScene(pg.Point(px, py))
                right_pt = self.vb_right.mapSceneToView(scene_pt)
                math_path.append((right_pt.x(), right_pt.y()))
            else:
                math_path.append((px, py))

        pts = np.column_stack((x_vis, y_vis))
        
        if self.interaction_mode == "box":
            x0, y0 = math_path[0]
            x1, y1 = math_path[-1] if len(math_path) > 1 else math_path[0]
            x_min, x_max = min(x0, x1), max(x0, x1)
            y_min, y_max = min(y0, y1), max(y0, y1)
            
            mask = (x_vis >= x_min) & (x_vis <= x_max) & (y_vis >= y_min) & (y_vis <= y_max)
            new_indices = np.where(mask)[0]
            
        elif self.interaction_mode == "lasso":
            if len(math_path) < 3: return
            import matplotlib.path as mpath
            path = mpath.Path(math_path)
            mask = path.contains_points(pts)
            new_indices = np.where(mask)[0]
            
        ctrl_pressed = (event.modifiers() == Qt.ControlModifier)
        if ctrl_pressed: self.selected_indices.update(new_indices) 
        else: self.selected_indices = set(new_indices) 
            
        if self.selected_indices:
            idx_array = list(self.selected_indices)
            try: self.plot_widget.removeItem(self.highlight_scatter)
            except: pass
            try: self.vb_right.removeItem(self.highlight_scatter)
            except: pass
            
            if is_right_active: self.vb_right.addItem(self.highlight_scatter)
            else: self.plot_widget.addItem(self.highlight_scatter)
            
            self.highlight_scatter.setData(x_vis[idx_array], y_vis[idx_array])
            self.highlight_scatter.setZValue(100) 
            self.highlight_scatter.show()
            self._update_selection_stats()
        else:
            self.highlight_scatter.hide()
            self.stats_label.hide()
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
        super().keyPressEvent(event)
        
    def clear_selection(self):
        self.selected_indices.clear()
        self.highlight_scatter.hide()
        self.selection_curve.hide()
        self.stats_label.hide()

    def open_signal_processing(self):
        if not self.dataset: return
        res = self._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0: 
            QMessageBox.warning(self, "No Data", "Please plot a 2D curve first.")
            return
            
        x_full, y_full, _, pair = res
        sel_idx = sorted(list(self.selected_indices)) if getattr(self, 'selected_indices', set()) else []
        
        dlg = SignalProcessingDialog(x_full, y_full, sel_idx, pair.get('y_name', 'Data'), self)
        
        if not hasattr(self, 'phantom_curve'):
            self.phantom_curve = pg.PlotCurveItem(pen=pg.mkPen("m", width=3, style=Qt.DashLine))
            self.plot_widget.addItem(self.phantom_curve)
        
        dlg.preview_updated.connect(lambda x_prev, y_prev: self._update_signal_preview(x_prev, y_prev))
        dlg.calculate_preview() 
        
        if dlg.exec() == QDialog.Accepted:
            self.phantom_curve.setVisible(False)
            config = dlg.get_result()
            
            fname = self.dataset.filename
            orig_name = os.path.basename(fname)
            directory = os.path.dirname(fname)

            if not orig_name.startswith("MIRROR_"):
                name_only, ext = os.path.splitext(orig_name)
                import glob
                search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
                existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

                if not existing_mirrors:
                    target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                    try: 
                        if self.file_type == "CSV": self._write_csv_mirror(target_file)
                        else:
                            import shutil
                            shutil.copy2(fname, target_file)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                        return
                    QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
                else:
                    dlg_mirror = QDialog(self)
                    dlg_mirror.setWindowTitle("Mirror File Exists")
                    dlg_mirror.setFixedSize(450, 150)
                    l = QVBoxLayout(dlg_mirror)
                    l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                    combo = QComboBox()
                    combo.addItem("--- Create New Mirror ---")
                    combo.addItems(existing_mirrors)
                    l.addWidget(combo)
                    
                    btn_box = QHBoxLayout()
                    ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                    btn_box.addWidget(ok); btn_box.addWidget(cancel)
                    l.addLayout(btn_box)
                    
                    ok.clicked.connect(dlg_mirror.accept); cancel.clicked.connect(dlg_mirror.reject)
                    if dlg_mirror.exec() != QDialog.Accepted: return
                    
                    choice = combo.currentText()
                    if choice == "--- Create New Mirror ---":
                        import re
                        max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                        new_mirror_name = f"MIRROR_{name_only} ({max_num + 1}){ext}"
                        target_file = os.path.join(directory, new_mirror_name)
                        
                        if self.file_type == "CSV": self._write_csv_mirror(target_file)
                        else:
                            import shutil
                            shutil.copy2(fname, target_file)
                    else:
                        target_file = os.path.join(directory, choice)

                opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
                if self.file_type == "CSV": opts["delimiter"] = ","
                    
                self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
                self.progress_dialog.setWindowModality(Qt.WindowModal)
                self.progress_dialog.setCancelButton(None)
                self.progress_dialog.setMinimumDuration(0)
                self.progress_dialog.show()

                def on_mirror_loaded(dataset):
                    self._on_load_finished(dataset, target_file, opts)
                    self._create_processed_column(config, pair) 

                self.loader_thread = DataLoaderThread(target_file, opts)
                self.loader_thread.progress.connect(self._update_progress_ui)
                self.loader_thread.finished.connect(on_mirror_loaded)
                self.loader_thread.error.connect(self._on_load_error)
                self.loader_thread.start()
                return

            self._create_processed_column(config, pair)
        else:
            self.phantom_curve.setVisible(False)

    def _create_processed_column(self, config, pair):
        import scipy.signal as sig
        import scipy.integrate as intg
        
        name, method = config['name'], config['method']
        win, poly = config['win'], config['poly']
        use_mask, sel_idx = config['use_mask'], config['sel_idx']
        
        x_idx, y_idx = pair['x'], pair['y']
        is_csv = (self.file_type == "CSV")
        sweeps = range(self.dataset.num_sweeps) if not is_csv else [0]
        calculated_data_blocks = []
            
        for sw in sweeps:
            arr = self.dataset.data if is_csv else self.dataset.sweeps[sw].data
            x_raw = np.asarray(arr[:, x_idx], dtype=np.float64)
            y_raw = np.asarray(arr[:, y_idx], dtype=np.float64)
            
            with np.errstate(all='ignore'):
                if "Savitzky" in method: y_calc = sig.savgol_filter(y_raw, win, poly)
                elif "Moving Average" in method: y_calc = np.convolve(y_raw, np.ones(win)/win, mode='same')
                elif "Median" in method: y_calc = sig.medfilt(y_raw, kernel_size=win)
                elif "Derivative" in method:
                    if len(x_raw) < 2: y_calc = np.zeros_like(y_raw)
                    else:
                        dx = np.gradient(x_raw)
                        if np.all(dx == 0): y_calc = np.zeros_like(y_raw)
                        else:
                            dx[np.abs(dx) < 1e-10] = 1e-10 * np.sign(dx[np.abs(dx) < 1e-10] + 1e-15)
                            y_calc = np.gradient(y_raw) / dx
                            y_calc = np.clip(np.nan_to_num(y_calc, nan=0.0, posinf=1e6, neginf=-1e6), -1e6, 1e6)
                elif "Integral" in method:
                    y_calc = np.nan_to_num(intg.cumulative_trapezoid(y_raw, x=x_raw + (np.arange(len(x_raw)) * 1e-12), initial=0), nan=0.0)
                else: y_calc = y_raw.copy()

            if use_mask and sel_idx:
                final_y = y_raw.copy()
                valid_indices = [i for i in sel_idx if i < len(final_y)]
                final_y[valid_indices] = y_calc[valid_indices]
            else:
                final_y = y_calc
                
            calculated_data_blocks.append(final_y)

        try:
            self._append_column_to_file(self.dataset.filename, name, calculated_data_blocks)
            QMessageBox.information(self, "Success", f"Column '{name}' created and saved successfully.")
            
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Fatal Execution Error", f"The file writer encountered a critical error:\n\n{e}\n\nTraceback:\n{traceback.format_exc()}")

    def open_phase_space_dialog(self):
        if not self.dataset: return
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_"):
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    new_mirror_name = f"MIRROR_{name_only} ({max_num + 1}){ext}"
                    target_file = os.path.join(directory, new_mirror_name)
                    
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
                
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_phase_space_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_phase_space_dialog()

    def _show_actual_phase_space_dialog(self):
        dlg = PhaseSpaceDialog(self.dataset, self)
        if dlg.exec() != QDialog.Accepted: return
        state_idx, time_idx, new_name = dlg.get_result()
        if not new_name: return

        is_csv = (self.file_type == "CSV")
        sweeps = range(self.dataset.num_sweeps) if not is_csv else [0]
        calculated_data_blocks = []

        for sw in sweeps:
            arr = self.dataset.data if is_csv else self.dataset.sweeps[sw].data
            x_raw = np.asarray(arr[:, state_idx], dtype=np.float64)

            if time_idx == -1: t_raw = np.arange(len(x_raw), dtype=np.float64)
            else: t_raw = np.asarray(arr[:, time_idx], dtype=np.float64)

            with np.errstate(all='ignore'):
                if len(x_raw) < 2: y_calc = np.zeros_like(x_raw)
                else:
                    dx = np.gradient(x_raw)
                    dt = np.gradient(t_raw)
                    dt[np.abs(dt) < 1e-10] = 1e-10 * np.sign(dt[np.abs(dt) < 1e-10] + 1e-15)
                    y_calc = np.clip(np.nan_to_num(dx / dt, nan=0.0, posinf=1e6, neginf=-1e6), -1e6, 1e6)
            calculated_data_blocks.append(y_calc)

        try:
            self._append_column_to_file(self.dataset.filename, new_name, calculated_data_blocks)
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data & Plotting Phase Space...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            def on_phase_space_loaded(ds):
                self._on_load_finished(ds, self.dataset.filename, opts)
                new_col_idx = len(self.dataset.column_names) - 1
                
                self.xcol.blockSignals(True); self.ycol.blockSignals(True)
                self.xcol.setCurrentIndex(state_idx)
                self.ycol.setCurrentIndex(new_col_idx)
                self.xcol.blockSignals(False); self.ycol.blockSignals(False)
                
                self.set_plot_mode("2D")
                self.graphtype.setCurrentText("Line")
                
                if self.series_data["2D"]: self.update_current_series()
                else: self.add_series_to_list()
                    
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_phase_space_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "Fatal Error", f"Failed to generate phase space:\n\n{e}")

    def _update_signal_preview(self, x_prev, y_prev):
        valid = np.isfinite(x_prev) & np.isfinite(y_prev)
        if not np.any(valid):
            self.phantom_curve.setVisible(False)
            return
        self.phantom_curve.setData(x_prev[valid], y_prev[valid])
        self.phantom_curve.setVisible(True)
        
    def show_metadata(self):
        if self.dataset:
            MetadataDialog(self.dataset, self).exec()
        
    def open_peak_finder(self):
        if not self.dataset: return
        
        if not hasattr(self, 'peak_finder_tool') or self.peak_finder_tool is None:
            self.peak_finder_tool = PeakFinderTool(self)
            
        self.peak_finder_tool.show()
        self.peak_finder_tool.raise_()
        self.peak_finder_tool.activateWindow()

    def draw_peak_markers(self, peaks_x, peaks_y, left_x, right_x, width_heights, axis_side):
        self.clear_peak_markers()
        self.peak_markers = []
        
        target_vb = self.vb_right if axis_side == "R" else self.plot_widget
        
        import pyqtgraph as pg
        from PyQt5.QtCore import Qt
        
        # 1. Draw the Green Stars at the very tip of the peaks
        scatter = pg.ScatterPlotItem(x=peaks_x, y=peaks_y, size=14, pen=pg.mkPen('k', width=1.5), brush=pg.mkBrush('#00ff00'), symbol='star')
        target_vb.addItem(scatter)
        self.peak_markers.append((scatter, target_vb))
        
        # 2. Draw the horizontal FWHM lines (Red)
        for lx, rx, h in zip(left_x, right_x, width_heights):
            line = pg.PlotCurveItem(x=[lx, rx], y=[h, h], pen=pg.mkPen('r', width=2.5))
            target_vb.addItem(line)
            self.peak_markers.append((line, target_vb))
            
        # 3. Draw vertical dashed lines dropping down from the peak
        for px in peaks_x:
            vline = pg.InfiniteLine(pos=px, angle=90, pen=pg.mkPen((150, 150, 150, 150), style=Qt.DashLine))
            target_vb.addItem(vline)
            self.peak_markers.append((vline, target_vb))

    def clear_peak_markers(self):
        if hasattr(self, 'peak_markers'):
            for item, vb in self.peak_markers:
                try: vb.removeItem(item)
                except: pass
            self.peak_markers.clear()

    def _build_menu(self):
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("File")
        open_action = QAction("Open Data File", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
    
        # Inspect Menu
        inspect_menu = menubar.addMenu("Inspect")
        self.inspect_table_action = inspect_menu.addAction("Sweep table")
        self.inspect_table_action.triggered.connect(self.prompt_sweep_table)
        inspect_menu.addAction("Rename / Delete columns").triggered.connect(self.manage_columns_dialog)
        inspect_menu.addAction("Create custom column").triggered.connect(self.prompt_create_column)
        inspect_menu.addSeparator()
        
        crosshair_action = QAction("Toggle crosshairs", self)
        crosshair_action.setShortcut("Ctrl+H") 
        crosshair_action.triggered.connect(self.toggle_crosshairs)
        inspect_menu.addAction(crosshair_action)
        
        # Analysis Menu
        analysis_menu = menubar.addMenu("Analysis")
        analysis_menu.addAction("Signal Processing (Smooth / Calculus)").triggered.connect(self.open_signal_processing)
        analysis_menu.addAction("Phase Space Generator (x vs dx/dt)").triggered.connect(self.open_phase_space_dialog)
        analysis_menu.addAction("Automated Peak Finder & iFFT Surgeon").triggered.connect(self.open_peak_finder)
        
        # Layout Menu
        layout_menu = menubar.addMenu("Layout")
        layout_action = QAction("Plot Settings & Slicing...", self)
        layout_action.setShortcut("Ctrl+L")
        layout_action.triggered.connect(self.open_layout_dialog)
        layout_menu.addAction(layout_action)
    
        # Fitting Menu
        self.fitting_menu = menubar.addMenu("Fitting")
        self.fitting_menu.addAction("Fit common function to data").triggered.connect(self.open_fit_function_dialog)
        self.fitting_menu.addAction("Fit custom function to data").triggered.connect(self.open_custom_fit_dialog)
        self.fitting_menu.addAction("Fit data to function").triggered.connect(self.open_fit_data_to_function)

        # Plot Mode Menu
        plot_mode_menu = menubar.addMenu("Plot Mode")
        plot_mode_menu.addAction("2D Plot").triggered.connect(lambda: self.set_plot_mode("2D"))
        self.plot_3d_action = plot_mode_menu.addAction("3D Plot")
        self.plot_3d_action.triggered.connect(lambda: self.set_plot_mode("3D"))
        plot_mode_menu.addAction("Heat Map").triggered.connect(lambda: self.set_plot_mode("Heatmap"))
        
        # Help Menu
        help_menu = menubar.addMenu("Help")
        help_action = QAction("How to use", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

    def _update_selection_stats(self):
        if not getattr(self, 'selected_indices', set()):
            self.stats_label.hide()
            return
            
        x_sel, y_sel, _, pair = self._get_all_plotted_xy(apply_selection=True)
        if len(x_sel) < 2:
            self.stats_label.hide()
            return
            
        n_pts = len(y_sel)
        mean_y, std_y, min_y, max_y = np.mean(y_sel), np.std(y_sel), np.min(y_sel), np.max(y_sel)
        
        sort_idx = np.argsort(x_sel)
        try: area = np.trapezoid(y_sel[sort_idx], x=x_sel[sort_idx])
        except AttributeError: area = np.trapz(y_sel[sort_idx], x=x_sel[sort_idx])
        
        y_name = pair.get('y_name', 'Y Axis')
        html = f"<b style='color: #0055ff; font-size: 14px;'>{y_name} Region Stats</b><br><hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
        html += f"<b>Count (N):</b>&nbsp;&nbsp;&nbsp;&nbsp;{n_pts}<br><b>Mean (&mu;):</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{mean_y:.5g}<br>"
        html += f"<b>Std Dev (&sigma;):</b>&nbsp;&nbsp;{std_y:.5g}<br><b>Minimum:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{min_y:.5g}<br>"
        html += f"<b>Maximum:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{max_y:.5g}<br><b>Peak-to-Peak:</b> {max_y - min_y:.5g}<br>"
        html += f"<b>Integral (&int;):</b>&nbsp;{area:.5g}"
        
        self.stats_label.setText(html)
        self.stats_label.adjustSize()
        if not self.stats_label.isVisible(): self.stats_label.move(15, 15)
        self.stats_label.show()
        self.stats_label.raise_()

    def prompt_sweep_table(self):
        if not self.dataset: return
        if self.file_type == "CSV":
            SweepTableDialog(self.dataset, sweep=0, parent=self, is_csv=True).exec()
            return
    
        dialog = QDialog(self)
        dialog.setWindowTitle("Inspect sweep")
        dialog.setFixedSize(250, 120)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        sweep_edit = QLineEdit("0")
        form.addRow("Sweep number:", sweep_edit)
        layout.addLayout(form)
    
        buttons = QHBoxLayout()
        ok, cancel = QPushButton("OK"), QPushButton("Cancel")
        buttons.addStretch(); buttons.addWidget(ok); buttons.addWidget(cancel)
        layout.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)
    
        def accept():
            try: sw = int(sweep_edit.text())
            except ValueError: return
            if 0 <= sw < self.dataset.num_sweeps:
                dialog.accept()
                SweepTableDialog(self.dataset, sw, self, is_csv=False).exec()
        ok.clicked.connect(accept)
        dialog.exec()

    def confirm_permanent_change(self, message):
        if self.settings.value("suppress_rename_warning", False, bool): return True
        dialog = QDialog(self)
        dialog.setWindowTitle("Confirm change")
        dialog.setFixedSize(380, 150)
        layout = QVBoxLayout(dialog)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        checkbox = QPushButton("✓ Do not show this again")
        checkbox.setCheckable(True)
        checkbox.setChecked(False)
        layout.addWidget(checkbox, alignment=Qt.AlignLeft)
        buttons = QHBoxLayout()
        yes, no = QPushButton("Yes"), QPushButton("No")
        buttons.addStretch(); buttons.addWidget(yes); buttons.addWidget(no)
        layout.addLayout(buttons)
    
        def accept():
            if checkbox.isChecked(): self.settings.setValue("suppress_rename_warning", True)
            dialog.accept()
        yes.clicked.connect(accept)
        no.clicked.connect(dialog.reject)
        return dialog.exec() == QDialog.Accepted

    def show_help(self):
        HelpDialog(self).exec()
        
    def manage_columns_dialog(self):
        if not self.dataset: return
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_"):
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]
            target_file = None

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try:
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror file:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been automatically created.\n\nIt will now be loaded so you can safely modify columns.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("To protect original data, column changes must be made to a Mirror file.\nSelect an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    target_file = os.path.join(directory, f"MIRROR_{name_only} ({max_num + 1}){ext}")
                    try:
                        if self.file_type == "CSV": self._write_csv_mirror(target_file)
                        else:
                            import shutil
                            shutil.copy2(fname, target_file)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to create mirror file:\n{e}")
                        return
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
            
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_manage_columns_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_manage_columns_dialog()

    def prompt_create_column(self):
        if not self.dataset: return
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_"):
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    target_file = os.path.join(directory, f"MIRROR_{name_only} ({max_num + 1}){ext}")
                    
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
            
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_create_column_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_create_column_dialog()
        
    def _write_csv_mirror(self, filepath):
        import csv
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            if hasattr(self.dataset, 'notes') and self.dataset.notes:
                for line in self.dataset.notes.split('\n'):
                    clean_line = line.lstrip('#').strip()
                    if clean_line: f.write(f"#{clean_line}\n")
            
            if not hasattr(self.dataset, 'notes') or "Is Mirror File: Yes" not in getattr(self.dataset, 'notes', ''):
                f.write("# Is Mirror File: Yes\n")
                
            writer = csv.writer(f, delimiter=',')
            headers = [self.dataset.column_names.get(i, f"Column {i}") for i in range(self.dataset.num_inputs)]
            writer.writerow(headers)
            
            if hasattr(self.dataset, 'data') and self.dataset.data is not None:
                for row in self.dataset.data:
                    clean_row = ["" if np.isnan(val) else f"{val:.6g}" for val in row]
                    writer.writerow(clean_row)

    def _show_actual_create_column_dialog(self):
        dlg = CreateColumnDialog(self.dataset, self)
        if dlg.exec() != QDialog.Accepted: return
        new_col_name, raw_equation = dlg.get_equation_data()
        if not new_col_name or not raw_equation: return

        try:
            import re
            py_equation = raw_equation
            col_map = {v: k for k, v in self.dataset.column_names.items()}
            used_indices = []
            
            def replace_col(match):
                name = match.group(1)
                if name not in col_map: raise ValueError(f"Unknown column: [{name}]")
                idx = col_map[name]
                used_indices.append(idx)
                return f"data_dict[{idx}]"
                
            py_equation = re.sub(r'\[(.*?)\]', replace_col, py_equation)
    
            def replace_const_actual(match):
                c_key = match.group(1)
                if c_key not in PHYSICS_CONSTANTS: raise ValueError(f"Unknown constant: {{{c_key}}}")
                return f"({PHYSICS_CONSTANTS[c_key]['value']})"
                
            py_equation = re.sub(r'\{(.*?)\}', replace_const_actual, py_equation)
    
            py_equation = py_equation.replace('^', '**')
            py_equation = re.sub(r'\barcsinh\s*\(', 'np.arcsinh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barccosh\s*\(', 'np.arccosh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barctanh\s*\(', 'np.arctanh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barcsin\s*\(', 'np.arcsin(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barccos\s*\(', 'np.arccos(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barctan\s*\(', 'np.arctan(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bsinh\s*\(', 'np.sinh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bcosh\s*\(', 'np.cosh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\btanh\s*\(', 'np.tanh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bsin\s*\(', 'np.sin(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bcos\s*\(', 'np.cos(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\btan\s*\(', 'np.tan(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\blog_?2\s*\(', 'np.log2(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\blog\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)
    
            is_csv = (self.file_type == "CSV")
            calculated_data_blocks = []
            
            with np.errstate(divide='ignore', invalid='ignore'):
                for sw in range(self.dataset.num_sweeps):
                    if is_csv: arr = self.dataset.data
                    else: arr = self.dataset.sweeps[sw].data
                        
                    data_dict = {idx: arr[:, idx] for idx in set(used_indices)}
                    index_arr = np.arange(arr.shape[0])
                    result = eval(py_equation, {"np": np, "data_dict": data_dict, "e": np.e, "pi": np.pi, "index": index_arr})
                    
                    if not isinstance(result, np.ndarray):
                        result = np.full(arr.shape[0], result)
                        
                    result = np.asarray(result, dtype=np.float64)
                    result[~np.isfinite(result)] = np.nan
                    calculated_data_blocks.append(result)
    
            self._append_column_to_file(self.dataset.filename, new_col_name, calculated_data_blocks)
            QMessageBox.information(self, "Success", f"Column '{new_col_name}' created and saved successfully.")
            
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
        except ValueError as ve:
            QMessageBox.critical(self, "Syntax Error", str(ve))
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Fatal Execution Error", f"The math engine or file writer encountered a critical error:\n\n{e}\n\nTraceback:\n{traceback.format_exc()}")

    def _append_column_to_file(self, target_file, new_name, calculated_blocks):
        if self.file_type == "CSV":
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
                
            out = []
            data_row_idx = 0
            flat_calc = calculated_blocks[0] 
            
            import re
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                out.append("# Is Mirror File: Yes\n")
            
            header_done = False
            for line in lines:
                clean_line = line.rstrip('\r\n') 
                if not clean_line or clean_line.startswith('#'): 
                    out.append(line)
                    continue
                    
                if not header_done: 
                    out.append(f"{clean_line}{delim}{new_name}\n")
                    header_done = True
                else: 
                    if data_row_idx < len(flat_calc):
                        val = flat_calc[data_row_idx]
                        data_row_idx += 1
                    else:
                        val = np.nan 
                    out.append(f"{clean_line}{delim}{val:.6g}\n")
                    
            with open(target_file, "w", encoding='utf-8-sig') as f:
                f.writelines(out)
                
        else:
            with open(target_file, "r", encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            import re
            has_outputs = False
            for i in range(len(lines)):
                if lines[i].startswith("###"): break 
                match = re.search(r'(?i)^\s*outputs?[\s:=]+(\d+)', lines[i])
                if match:
                    num = int(match.group(1))
                    prefix = lines[i][:match.start(1)]
                    suffix = lines[i][match.end(1):]
                    lines[i] = f"{prefix}{num + 1}{suffix}"
                    has_outputs = True
                    break

            if not has_outputs:
                lines.insert(1, "Outputs: 1\n")
            
            out = []
            sweep_idx = 0
            point_idx = 0
            in_data = False
            has_outputs_section = False
            in_outputs_block = False
            
            target_col_idx = getattr(self.dataset, 'num_outputs', 0)
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False
            
            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}\n")
                    continue
                    
                if line.startswith("###NOTES"):
                    out.append(line)
                    if not has_mirror_flag:
                        out.append("Is Mirror File: Yes\n")
                        flag_injected = True
                    continue
                    
                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###\nIs Mirror File: Yes\n\n")
                        flag_injected = True

                if in_outputs_block and line.startswith("###"):
                    out.append(f"{new_name}\tBadgerLoop.CalculatedColumn\n")
                    in_outputs_block = False

                if line.startswith("###OUTPUTS"):
                    has_outputs_section = True
                    in_outputs_block = True
                    out.append(line)
                    continue
                    
                if line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_outputs_section:
                        out.append("###OUTPUTS###\n")
                        out.append(f"{new_name}\tBadgerLoop.CalculatedColumn\n")
                        has_outputs_section = True
                        
                    if line.startswith("###DATA") and not line.startswith("###DATA SET"):
                        in_data = True
                        out.append(line)
                        continue

                if in_outputs_block and not line.strip(): continue

                if in_data:
                    clean_line = line.rstrip('\r\n')
                    if '\t' in clean_line:
                        if sweep_idx < len(calculated_blocks) and point_idx >= len(calculated_blocks[sweep_idx]):
                            sweep_idx += 1
                            point_idx = 0
                            
                        if sweep_idx < len(calculated_blocks) and point_idx < len(calculated_blocks[sweep_idx]):
                            val = calculated_blocks[sweep_idx][point_idx]
                            point_idx += 1
                        else:
                            val = np.nan 
                            
                        parts = clean_line.split('\t')
                        parts.insert(target_col_idx, f"{val:.6g}") 
                        out.append("\t".join(parts) + "\n")
                    else:
                        out.append(line) 
                else:
                    out.append(line)
                    
            with open(target_file, "w", encoding='utf-8') as f:
                f.writelines(out)

    def _rewrite_column_name_in_file(self, target_file, col_idx, new_name):
        if self.file_type == "CSV":
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            import csv
            import io
            import re
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
            if not lines: return
            
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                lines.insert(0, "# Is Mirror File: Yes")
            
            header_idx = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('#'):
                    header_idx = i
                    break
                    
            reader = csv.reader([lines[header_idx]], delimiter=delim)
            try: headers = next(reader)
            except StopIteration: return
                
            if col_idx < len(headers):
                headers[col_idx] = new_name
            
            out_buf = io.StringIO()
            csv.writer(out_buf, delimiter=delim).writerow(headers)
            lines[header_idx] = out_buf.getvalue().strip()
            
            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(lines) + "\n")
                
        else:
            num_out = getattr(self.dataset, 'num_outputs', 0)
            num_inp = getattr(self.dataset, 'num_inputs', 0)
            has_time = (len(self.dataset.column_names) > num_out + num_inp)
            
            inst_idx = col_idx - 1 if has_time else col_idx
            enabled_names = [inst["name"] for inst in self.dataset.outputs] + [inst["name"] for inst in self.dataset.inputs]
            target_old_name = enabled_names[inst_idx] if 0 <= inst_idx < len(enabled_names) else None
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]

            out = []
            in_outputs = False
            in_inputs = False
            
            import re
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False
            
            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}")
                    continue
                    
                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###")
                        out.append("Is Mirror File: Yes")
                        out.append("")
                        flag_injected = True
                        
                if line.startswith("###OUTPUTS"):
                    in_outputs = True; in_inputs = False
                    out.append(line); continue
                if line.startswith("###INPUTS"):
                    in_inputs = True; in_outputs = False
                    out.append(line); continue
                if line.startswith("###DATA"):
                    in_outputs = False; in_inputs = False
                    out.append(line); continue
                    
                if (in_outputs or in_inputs) and line.strip():
                    parts = line.split("\t", 1)
                    if target_old_name and parts[0].strip() == target_old_name.strip():
                        parts[0] = new_name
                        line = parts[0] + ("\t" + parts[1] if len(parts) > 1 else "")
                        
                out.append(line)
                
            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(out) + "\n")

    def _delete_column_in_file(self, target_file, col_idx):
        if self.file_type == "CSV":
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            import csv
            import io
            import re
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
            if not lines: return

            out = []
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                out.append("# Is Mirror File: Yes")

            for line in lines:
                if line.startswith('#') or not line.strip():
                    out.append(line)
                    continue
                
                parts = next(csv.reader([line], delimiter=delim))
                if col_idx < len(parts):
                    parts.pop(col_idx)
                
                temp = io.StringIO()
                csv.writer(temp, delimiter=delim).writerow(parts)
                out.append(temp.getvalue().strip())
                
            with open(target_file, "w", encoding='utf-8-sig') as f:
                f.write("\n".join(out) + "\n")
                
        else:
            num_out = getattr(self.dataset, 'num_outputs', 0)
            num_inp = getattr(self.dataset, 'num_inputs', 0)
            has_time = (len(self.dataset.column_names) > num_out + num_inp)
            
            inst_idx = col_idx - 1 if has_time else col_idx
            is_time = (inst_idx < 0)
            is_output = (0 <= inst_idx < num_out)
            
            enabled_names = [inst["name"] for inst in self.dataset.outputs] + [inst["name"] for inst in self.dataset.inputs]
            
            target_name = None
            if not is_time and 0 <= inst_idx < len(enabled_names):
                target_name = enabled_names[inst_idx]
            
            outputs_left = max(0, num_out - 1) if (not is_time and is_output) else num_out
            inputs_left = max(0, num_inp - 1) if (not is_time and not is_output) else num_inp
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
                
            out = []
            in_outputs = False
            in_inputs = False
            in_data = False
            
            import re
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False
            
            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}")
                    continue
                    
                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###")
                        out.append("Is Mirror File: Yes")
                        out.append("")
                        flag_injected = True
                        
                if not is_time:
                    if is_output and re.match(r'(?i)^\s*outputs?[\s:=]+(\d+)', line):
                        out.append(re.sub(r'(\d+)', str(outputs_left), line, count=1))
                        continue
                    if not is_output and re.match(r'(?i)^\s*inputs?[\s:=]+(\d+)', line):
                        out.append(re.sub(r'(\d+)', str(inputs_left), line, count=1))
                        continue
                        
                if line.startswith("###OUTPUTS"):
                    in_outputs = True; in_inputs = False; in_data = False
                    out.append(line); continue
                if line.startswith("###INPUTS"):
                    in_inputs = True; in_outputs = False; in_data = False
                    out.append(line); continue
                if line.startswith("###DATA") and not line.startswith("###DATA SET"):
                    in_data = True; in_outputs = False; in_inputs = False
                    out.append(line); continue
                    
                if (in_outputs or in_inputs) and line.strip() and target_name:
                    parts = line.split("\t", 1)
                    if parts[0].strip() == target_name.strip():
                        continue 
                        
                if in_data and line.strip() and not line.startswith("###"):
                    if ':' in line and '\t' not in line:
                        out.append(line)
                        continue
                        
                    parts = line.split('\t')
                    if col_idx < len(parts):
                        parts.pop(col_idx)
                    out.append("\t".join(parts))
                    continue
                    
                out.append(line)
                
            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(out) + "\n")

    def _execute_universal_fit(self, base_model, param_names, param_config, x, y):
        free_params = []
        fixed_params = {}
        p0 = []
        
        for p in param_names:
            if param_config[p]["mode"] == "Auto":
                free_params.append(p)
                p0.append(param_config[p]["value"])
            else:
                fixed_params[p] = param_config[p]["value"]
        
        if not free_params:
            return [param_config[p]["value"] for p in param_names]
            
        def dynamic_wrapper(x_val, *args):
            kwargs = dict(fixed_params)
            for name, val in zip(free_params, args):
                kwargs[name] = val
            full_args = [kwargs[p] for p in param_names]
            return base_model(x_val, *full_args)
            
        from scipy.optimize import curve_fit
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            popt, _ = curve_fit(dynamic_wrapper, x, y, p0=p0, maxfev=20000)
            
        final_params = []
        popt_idx = 0
        for p in param_names:
            if p in free_params:
                final_params.append(popt[popt_idx])
                popt_idx += 1
            else:
                final_params.append(fixed_params[p])
                
        return final_params

    def open_fit_function_dialog(self):
        if not self.dataset: return
        dlg = FitFunctionDialog(self)
        if dlg.exec() != QDialog.Accepted: return
        func_type, degree_text, log_base_text, param_config = dlg.get_result()

        if func_type == "Polynomial":
            try:
                degree = int(degree_text)
                if degree < 0: raise ValueError
            except ValueError: return
            self.fit_polynomial(degree, param_config)
        elif func_type == "Logarithmic": self.fit_logarithmic(log_base_text, param_config)
        elif func_type == "Exponential": self.fit_exponential(param_config)
        elif func_type == "Gaussian": self.fit_gaussian(param_config)
        elif func_type == "Lorentzian": self.fit_lorentzian(param_config)
            
    def open_custom_fit_dialog(self):
        if not self.dataset: return
        dlg = CustomFitDialog(self.dataset, self)
        if dlg.exec() != QDialog.Accepted: 
            if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
            return
            
        if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
        raw_eq, py_eq, html_eq, used_cols, param_names, param_config = dlg.get_result()
        
        res_full = self._get_all_plotted_xy(aux_cols=used_cols, apply_selection=False)
        if len(res_full) < 4 or len(res_full[0]) == 0: return
        x_full, y_full, aux_full, pair = res_full
        
        if getattr(self, 'selected_indices', set()):
            idx = sorted(list(self.selected_indices))
            x_calc = x_full[idx]
            y_calc = y_full[idx]
            aux_calc = {c: aux_full[c][idx] for c in used_cols}
        else:
            x_calc = x_full
            y_calc = y_full
            aux_calc = aux_full
        
        def custom_model_calc(x_val, *args):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "data_dict": aux_calc}
            for i, p in enumerate(param_names): env[p] = args[i]
            res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
            return res_arr

        try:
            final_params = self._execute_universal_fit(custom_model_calc, param_names, param_config, x_calc, y_calc)
        except Exception as e:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", f"{e}", self).exec()
            return

        sort_idx = np.argsort(x_full)
        x_sorted = x_full[sort_idx]
        sorted_aux = {c: aux_full[c][sort_idx] for c in used_cols}
        
        def plot_model(x_arr, aux_arrs, *args):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_arr, "data_dict": aux_arrs}
            for i, p in enumerate(param_names): env[p] = args[i]
            res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_arr, float(res_arr))
            return res_arr
            
        yfit = plot_model(x_sorted, sorted_aux, *final_params)

        plot_item = self.plot_widget.plot(x_sorted, yfit, pen=pg.mkPen("r", width=2, style=Qt.DashLine))
        fit_name = f"Custom Fit ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(x_sorted, yfit) 
        self.active_fits.append({
            "name": fit_name, "type": "custom", 
            "params": final_params, "param_names": param_names,
            "plot_item": plot_item, "equation": raw_eq,
            "html_equation": html_eq, "raw_equation": raw_eq, 
            "param_config": param_config,
            "x_raw": x_raw, "y_raw": y_raw
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def _get_all_plotted_xy(self, apply_selection=False, aux_cols=None):
        if not self.dataset: return [], [], None, {}
        row = max(0, self.series_list.currentRow())
        if row >= len(self.series_data["2D"]): return [], [], None, {}
        pair = self.series_data["2D"][row]
        
        if getattr(self, 'fft_mode_active', False) and hasattr(self, 'last_plotted_data'):
            pkgs = [p for p in self.last_plotted_data.get('packages', []) if p.get("pair_idx", 0) == row and p.get("type") == "standard"]
            if pkgs:
                x_fft = pkgs[0]['x']
                y_fft = pkgs[0]['y']
                if apply_selection and getattr(self, 'selected_indices', set()):
                    idx = np.array(list(self.selected_indices))
                    valid_idx = idx[idx < len(x_fft)]
                    return x_fft[valid_idx], y_fft[valid_idx], None, pair
                return x_fft, y_fft, None, pair
        
        xidx, yidx = pair['x'], pair['y']
        aux_dict = {}
        
        if self.file_type == "CSV":
            x = np.asarray(self.dataset.data[:, xidx], dtype=np.float64)
            y = np.asarray(self.dataset.data[:, yidx], dtype=np.float64)
            if aux_cols:
                for c in aux_cols: aux_dict[c] = np.asarray(self.dataset.data[:, c], dtype=np.float64)
        else:
            sw = self.dataset.sweeps[0].data
            x = np.asarray(sw[:, xidx], dtype=np.float64)
            y = np.asarray(sw[:, yidx], dtype=np.float64)
            if aux_cols:
                for c in aux_cols: aux_dict[c] = np.asarray(sw[:, c], dtype=np.float64)
            
        if apply_selection and getattr(self, 'selected_indices', set()):
            idx = np.array(list(self.selected_indices))
            valid_idx = idx[idx < len(x)]
            if aux_cols:
                return x[valid_idx], y[valid_idx], {c: v[valid_idx] for c, v in aux_dict.items()}, pair
            return x[valid_idx], y[valid_idx], None, pair
            
        return x, y, aux_dict, pair

    def edit_fit(self):
        if not getattr(self, 'active_fits', []): return
        if len(self.active_fits) == 1:
            idx = 0
            fit = self.active_fits[0]
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "Edit", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        if fit["type"] == "custom":
            dlg = CustomFitDialog(self.dataset, self)
            dlg.load_state(fit)
            if dlg.exec() == QDialog.Accepted:
                self.plot_widget.removeItem(fit["plot_item"])
                self.fit_legend.removeItem(fit["plot_item"])
                self.active_fits.pop(idx)
                if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
                
                raw_eq, py_eq, html_eq, used_cols, param_names, param_config = dlg.get_result()
                
                res_full = self._get_all_plotted_xy(aux_cols=used_cols, apply_selection=False)
                if len(res_full) < 4 or len(res_full[0]) == 0: return
                x_full, y_full, aux_full, pair = res_full
                
                if getattr(self, 'selected_indices', set()):
                    idx = sorted(list(self.selected_indices))
                    x_calc = x_full[idx]
                    y_calc = y_full[idx]
                    aux_calc = {c: aux_full[c][idx] for c in used_cols}
                else:
                    x_calc = x_full
                    y_calc = y_full
                    aux_calc = aux_full
                
                def custom_model_calc(x_val, *args):
                    env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "data_dict": aux_calc}
                    for i, p in enumerate(param_names): env[p] = args[i]
                    res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
                    if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
                    return res_arr

                try:
                    final_params = self._execute_universal_fit(custom_model_calc, param_names, param_config, x_calc, y_calc)
                except Exception as e:
                    CopyableErrorDialog("Fitting Error", "Optimization failed.", f"{e}", self).exec()
                    return

                sort_idx = np.argsort(x_full)
                x_sorted = x_full[sort_idx]
                sorted_aux = {c: aux_full[c][sort_idx] for c in used_cols}
                
                def plot_model(x_arr, aux_arrs, *args):
                    env = {"np": np, "e": np.e, "pi": np.pi, "x": x_arr, "data_dict": aux_arrs}
                    for i, p in enumerate(param_names): env[p] = args[i]
                    res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
                    if res_arr.ndim == 0: res_arr = np.full_like(x_arr, float(res_arr))
                    return res_arr

                yfit = plot_model(x_sorted, sorted_aux, *final_params)
                plot_item = self.plot_widget.plot(x_sorted, yfit, pen=pg.mkPen("r", width=2, style=Qt.DashLine))
                fit_name = f"Custom Fit ➔ {pair['y_name']}"
                self.fit_legend.addItem(plot_item, fit_name)

                x_raw, y_raw = self._get_raw_fit_coords(x_sorted, yfit) 
                self.active_fits.append({
                    "name": fit_name, "type": "custom", 
                    "params": final_params, "param_names": param_names,
                    "plot_item": plot_item, "equation": raw_eq,
                    "html_equation": html_eq, "raw_equation": raw_eq, 
                    "param_config": param_config,
                    "x_raw": x_raw, "y_raw": y_raw
                })
            else:
                if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
                
        else:
            dlg = FitFunctionDialog(self)
            dlg.load_state(fit)
            if dlg.exec() == QDialog.Accepted:
                self.plot_widget.removeItem(fit["plot_item"])
                self.fit_legend.removeItem(fit["plot_item"])
                self.active_fits.pop(idx)
                
                func_type, degree_text, log_base_text, param_config = dlg.get_result()
                if func_type == "Polynomial":
                    try:
                        degree = int(degree_text)
                        if degree >= 0: self.fit_polynomial(degree, param_config)
                    except ValueError: pass
                elif func_type == "Logarithmic": self.fit_logarithmic(log_base_text, param_config)
                elif func_type == "Exponential": self.fit_exponential(param_config)
                elif func_type == "Gaussian": self.fit_gaussian(param_config)
                elif func_type == "Lorentzian": self.fit_lorentzian(param_config)

    def _get_raw_fit_coords(self, x_vis, y_vis):
        xlog = self.xscale.currentText() == "Log"
        ylog = self.yscale.currentText() == "Log"
        xbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.xbase.text())
        ybase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.ybase.text())

        with np.errstate(over='ignore', invalid='ignore'):
            x_raw = np.power(xbase, x_vis) if xlog else np.array(x_vis, copy=True)
            y_raw = np.power(ybase, y_vis) if ylog else np.array(y_vis, copy=True)
        return x_raw, y_raw

    def fit_polynomial(self, degree, param_config):
        res = self._get_all_plotted_xy()
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        param_names = [f"c{i}" for i in range(degree + 1)]
        if all(param_config[p]["mode"] == "Auto" and param_config[p]["value"] == 1.0 for p in param_names):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                smart_p0 = np.polyfit(x, y, degree)
            for i, p in enumerate(param_names):
                param_config[p]["value"] = smart_p0[i]

        def model(x_val, *args):
            return sum(c * (x_val**(degree-i)) for i, c in enumerate(args))

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return
            
        poly = np.poly1d(final_params)
        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = poly(xfit)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Poly (deg {degree}) ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit) 
        self.active_fits.append({
            "name": fit_name, "type": "polynomial", "degree": degree,
            "coeffs": final_params, "callable": poly, "plot_item": plot_item,
            "equation": "y = " + " + ".join(f"{c:.3g}x^{i}" for i, c in enumerate(final_params[::-1])),
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def fit_logarithmic(self, base_text, param_config):
        res = self._get_all_plotted_xy()
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        if base_text.lower() == "e": base = np.e
        else:
            try:
                base = float(base_text)
                if base <= 0: raise ValueError
            except ValueError: return

        def model(x_val, a, c): return a * np.log(x_val) / np.log(base) + c
        param_names = ["a", "c"]

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(max(1e-15, x_full.min()), x_full.max(), 500) 
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Logarithmic ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "logarithmic", "base": base_text, "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def fit_exponential(self, param_config):
        res = self._get_all_plotted_xy()
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        def model(x_val, a, b, c): return a * np.exp(b * x_val) + c
        param_names = ["a", "b", "c"]

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Exponential ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "exponential", "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def fit_gaussian(self, param_config):
        res = self._get_all_plotted_xy()
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        def model(x_val, A, mu, sigma): return A * np.exp(-(x_val - mu)**2 / (2 * sigma**2))
        param_names = ["A", "mu", "sigma"]

        if param_config["A"]["mode"] == "Auto" and param_config["A"]["value"] == 1.0: param_config["A"]["value"] = y.max()
        if param_config["mu"]["mode"] == "Auto" and param_config["mu"]["value"] == 1.0: param_config["mu"]["value"] = x.mean()
        if param_config["sigma"]["mode"] == "Auto" and param_config["sigma"]["value"] == 1.0: param_config["sigma"]["value"] = np.std(x)

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Gaussian ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "gaussian", "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def fit_lorentzian(self, param_config):
        res = self._get_all_plotted_xy()
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        def model(x_val, A, x0, gamma): return A / (1 + ((x_val - x0) / gamma)**2)
        param_names = ["A", "x0", "gamma"]

        if param_config["A"]["mode"] == "Auto" and param_config["A"]["value"] == 1.0: param_config["A"]["value"] = y.max()
        if param_config["x0"]["mode"] == "Auto" and param_config["x0"]["value"] == 1.0: param_config["x0"]["value"] = x.mean()
        if param_config["gamma"]["mode"] == "Auto" and param_config["gamma"]["value"] == 1.0: param_config["gamma"]["value"] = np.std(x)

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Lorentzian ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "lorentzian", "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def clear_fit(self):
        if not getattr(self, 'active_fits', []): return
        if len(self.active_fits) == 1:
            fit = self.active_fits.pop()
            self.plot_widget.removeItem(fit["plot_item"])
            self.fit_legend.removeItem(fit["plot_item"])
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "Delete", self)
            if dlg.exec() == QDialog.Accepted:
                res_type, idx = dlg.get_selection()
                if res_type == "all":
                    for fit in self.active_fits:
                        self.plot_widget.removeItem(fit["plot_item"])
                        self.fit_legend.removeItem(fit["plot_item"])
                    self.active_fits.clear()
                else:
                    fit = self.active_fits.pop(idx)
                    self.plot_widget.removeItem(fit["plot_item"])
                    self.fit_legend.removeItem(fit["plot_item"])
                    
        if not self.active_fits:
            self.save_function_btn.setVisible(False)
            self.clear_fit_btn.setVisible(False)
            if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(False)
            if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(False)

    def save_function(self):
        if not getattr(self, 'active_fits', []): return
        if len(self.active_fits) == 1:
            fit = self.active_fits[0]
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "Save", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        fname, _ = QFileDialog.getSaveFileName(self, "Save Function", "", "Text files (*.txt)")
        if not fname: return
        if not fname.endswith(".txt"): fname += ".txt"

        with open(fname, "w") as f:
            f.write(f"{fit['type']}\n")
            if fit["type"] == "polynomial":
                f.write(f"degree: {fit['degree']}\n")
                for c in fit["coeffs"]: f.write(f"{c}\n")
            elif fit["type"] == "logarithmic":
                f.write(f"base: {fit['base']}\n")
                for p in fit["params"]: f.write(f"{p}\n")
            elif fit["type"] == "custom":
                f.write(f"{fit['raw_equation']}\n")
                f.write(",".join(fit['param_names']) + "\n")
                for p in fit["params"]: f.write(f"{p}\n")
            else:
                for p in fit["params"]: f.write(f"{p}\n")

    def open_fit_data_to_function(self):
        if not self.dataset: return
        win = FitDataToFunctionWindow(self.dataset, self)
        win.show()

    def open_layout_dialog(self):
        self.layout_dialog.show()
        self.layout_dialog.raise_()
        self.layout_dialog.activateWindow()
        
    def _update_graphtype_dropdown(self):
        """ Dynamically updates the available Graph Types based on the current Plot Mode """
        current_selection = self.graphtype.currentText()
        
        self.graphtype.blockSignals(True)
        self.graphtype.clear()
        
        if self.plot_mode == "2D":
            self.graphtype.addItems(["Line", "Scatter"]) # FFT removed! Handled globally now.
        elif self.plot_mode == "3D":
            self.graphtype.addItems(["Line", "Scatter", "Surface"])
        elif self.plot_mode == "Heatmap":
            self.graphtype.addItems(["Heatmap Default"])
            
        index = self.graphtype.findText(current_selection)
        if index >= 0:
            self.graphtype.setCurrentIndex(index)
        else:
            self.graphtype.setCurrentIndex(0)
            
        self.graphtype.blockSignals(False)
        self._update_graphtype_ui()
        
    def _update_graphtype_ui(self):
        is_heatmap = (self.plot_mode == "Heatmap")
        is_surface = (self.plot_mode == "3D" and self.graphtype.currentText() == "Surface")
        self.heatmap_cmap.setVisible(is_heatmap or is_surface)
        self.heatmap_cmap_label.setVisible(is_heatmap or is_surface)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        
        self.layout_dialog = QDialog(self)
        self.layout_dialog.setWindowTitle("Plot Settings & Slicing")
        self.layout_dialog.setMinimumWidth(350)
        ld_layout = QVBoxLayout(self.layout_dialog)
        
        ld_layout.addWidget(QLabel("<b>Graph Type:</b>"))
        self.graphtype = QComboBox()
        self.graphtype.addItems(["Line", "Scatter", "FFT (Spectrum)", "Surface"]) 
        self.graphtype.currentTextChanged.connect(self._update_graphtype_ui)
        ld_layout.addWidget(self.graphtype)

        ld_layout.addSpacing(10)
        ld_layout.addWidget(QLabel("<b>Plot Aspect Ratio:</b>"))
        aspect_grid = QGridLayout()
        
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["Free", "1:1", "4:3", "16:9", "Custom"])
        aspect_grid.addWidget(self.aspect_combo, 0, 0, 1, 2)
        
        self.aspect_w_edit = QLineEdit("16")
        self.aspect_h_edit = QLineEdit("9")
        self.aspect_colon = QLabel(":")
        self.aspect_colon.setAlignment(Qt.AlignCenter)
        
        self.aspect_w_edit.setVisible(False)
        self.aspect_h_edit.setVisible(False)
        self.aspect_colon.setVisible(False)
        
        custom_aspect_layout = QHBoxLayout()
        custom_aspect_layout.addWidget(self.aspect_w_edit)
        custom_aspect_layout.addWidget(self.aspect_colon)
        custom_aspect_layout.addWidget(self.aspect_h_edit)
        
        aspect_grid.addLayout(custom_aspect_layout, 1, 0, 1, 2)
        ld_layout.addLayout(aspect_grid)
        
        self.aspect_combo.currentTextChanged.connect(self._update_aspect_ui)
        self.aspect_w_edit.textChanged.connect(self._resize_plot_widget)
        self.aspect_h_edit.textChanged.connect(self._resize_plot_widget)

        ld_layout.addSpacing(10)
        ld_layout.addWidget(QLabel("<b>Data Slicing:</b>"))
        slice_grid = QGridLayout()
        self.sweeps_label = QLabel("Sweeps (e.g. 0,2,4 or 0:5):")
        slice_grid.addWidget(self.sweeps_label, 0, 0)
        self.sweeps_edit = QLineEdit("-1")
        slice_grid.addWidget(self.sweeps_edit, 0, 1)
        slice_grid.addWidget(QLabel("Points (e.g. 100:500):"), 1, 0)
        self.points_edit = QLineEdit("-1")
        slice_grid.addWidget(self.points_edit, 1, 1)
        ld_layout.addLayout(slice_grid)

        ld_layout.addSpacing(10)
        ld_layout.addWidget(QLabel("<b>Axis Scales & Bases:</b>"))
        scale_grid = QGridLayout()
        scale_grid.addWidget(QLabel("X Axis:"), 0, 0)
        self.xscale = QComboBox()
        self.xscale.addItems(["Linear", "Log"])
        self.xscale.currentTextChanged.connect(self._update_xscale_ui)
        scale_grid.addWidget(self.xscale, 0, 1)
        self.xbase = QLineEdit("10")
        self.xbase.setPlaceholderText("Base (e.g. 10 or e)")
        scale_grid.addWidget(self.xbase, 0, 2)

        scale_grid.addWidget(QLabel("Y Axis:"), 1, 0)
        self.yscale = QComboBox()
        self.yscale.addItems(["Linear", "Log"])
        self.yscale.currentTextChanged.connect(self._update_yscale_ui)
        scale_grid.addWidget(self.yscale, 1, 1)
        self.ybase = QLineEdit("10")
        self.ybase.setPlaceholderText("Base")
        scale_grid.addWidget(self.ybase, 1, 2)

        self.zscale_label = QLabel("Z Axis:")
        scale_grid.addWidget(self.zscale_label, 2, 0)
        self.zscale = QComboBox()
        self.zscale.addItems(["Linear", "Log"])
        self.zscale.currentTextChanged.connect(self._update_zscale_ui)
        scale_grid.addWidget(self.zscale, 2, 1)
        self.zbase = QLineEdit("10")
        self.zbase.setPlaceholderText("Base")
        scale_grid.addWidget(self.zbase, 2, 2)
        ld_layout.addLayout(scale_grid)

        self.zscale_label.setVisible(False)
        self.zscale.setVisible(False)
        self.zbase.setVisible(False)

        ld_layout.addSpacing(10)
        ld_layout.addWidget(QLabel("<b>Sizes & Fonts:</b>"))
        font_grid = QGridLayout()
        font_grid.addWidget(QLabel("Label Size:"), 0, 0)
        self.label_fontsize_edit = QLineEdit("14")
        font_grid.addWidget(self.label_fontsize_edit, 0, 1)
        font_grid.addWidget(QLabel("Tick Size:"), 1, 0)
        self.tick_fontsize_edit = QLineEdit("11")
        font_grid.addWidget(self.tick_fontsize_edit, 1, 1)
        font_grid.addWidget(QLabel("Point Size (2D):"), 2, 0)
        self.point_size_edit = QLineEdit("5")
        font_grid.addWidget(self.point_size_edit, 2, 1)
        ld_layout.addLayout(font_grid)

        ld_layout.addStretch()
        apply_btn = QPushButton("Apply to Plot")
        apply_btn.setStyleSheet("font-weight: bold; background-color: #e0e0e0; padding: 6px;")
        apply_btn.clicked.connect(self.plot)
        ld_layout.addWidget(apply_btn)

        controls = QVBoxLayout()
        main.addLayout(controls, 0)
        
        def button(text, slot):
            b = QPushButton(text)
            b.clicked.connect(slot)
            return b
            
        controls.addWidget(button("Open Data File", self.open_file))           
        self.show_metadata_btn = button("Show Metadata", self.show_metadata)
        controls.addWidget(self.show_metadata_btn)
        
        controls.addWidget(button("Toggle Legend", self.toggle_legend))
        
        self.toggle_avg_btn = button("Toggle Averaging", self.toggle_averaging)
        controls.addWidget(self.toggle_avg_btn)
        
        self.toggle_uncert_btn = button("Toggle Uncertainties", self.toggle_csv_uncertainties)
        self.toggle_uncert_btn.setVisible(False)
        controls.addWidget(self.toggle_uncert_btn)
        
        self.errorbar_btn = QPushButton("Toggle Error Bars")
        self.errorbar_btn.clicked.connect(self.toggle_errorbars)
        self.errorbar_btn.setVisible(False)
        controls.addWidget(self.errorbar_btn)
        
        controls.addWidget(QLabel("Error bar sigma multiplier"))
        self.errorbar_sigma_edit = QLineEdit("1.0")
        self.errorbar_sigma_edit.setVisible(False)
        controls.addWidget(self.errorbar_sigma_edit)
    
        controls.addSpacing(10)
        controls.addWidget(QLabel("X column"))
        self.xcol = QComboBox()
        controls.addWidget(self.xcol)
        self.xuncert_label = QLabel(" ↳ X Uncertainty")
        self.xuncert = QComboBox()
        controls.addWidget(self.xuncert_label)
        controls.addWidget(self.xuncert)
    
        controls.addWidget(QLabel("Y column"))
        self.ycol = QComboBox()
        controls.addWidget(self.ycol)
        self.yuncert_label = QLabel(" ↳ Y Uncertainty")
        self.yuncert = QComboBox()
        controls.addWidget(self.yuncert_label)
        controls.addWidget(self.yuncert)
    
        self.zcol_label = QLabel("Z column")
        self.zcol = QComboBox()
        controls.addWidget(self.zcol_label)
        controls.addWidget(self.zcol)
        self.zuncert_label = QLabel(" ↳ Z Uncertainty")
        self.zuncert = QComboBox()
        controls.addWidget(self.zuncert_label)
        controls.addWidget(self.zuncert)
        
        self.zcol_label.setVisible(False)
        self.zcol.setVisible(False)
        self._update_uncert_visibility()
        
        controls.addSpacing(15)
        controls.addWidget(QLabel("<b>Interaction Mode:</b>"))
        mode_layout = QHBoxLayout()
        
        self.btn_pan = QPushButton("✋ Pan/Zoom")
        self.btn_pan.setCheckable(True)
        self.btn_pan.setChecked(True)
        
        self.btn_box = QPushButton("⬛ Box")
        self.btn_box.setCheckable(True)
        
        self.btn_lasso = QPushButton("➰ Lasso")
        self.btn_lasso.setCheckable(True)
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_pan)
        self.mode_group.addButton(self.btn_box)
        self.mode_group.addButton(self.btn_lasso)
        self.mode_group.buttonClicked.connect(self._set_interaction_mode)
        self._set_interaction_mode(self.btn_pan)
        
        mode_layout.addWidget(self.btn_pan)
        mode_layout.addWidget(self.btn_box)
        mode_layout.addWidget(self.btn_lasso)
        controls.addLayout(mode_layout)
        
        self.selection_curve = pg.PlotCurveItem(pen=pg.mkPen('#0055ff', width=2, style=Qt.DashLine))
        self.plot_widget.addItem(self.selection_curve, ignoreBounds=True)
        self.selection_curve.hide()
        
        self.highlight_scatter = pg.ScatterPlotItem(size=10, pen=pg.mkPen('k', width=1), brush=pg.mkBrush(255, 255, 0, 200))
        self.plot_widget.addItem(self.highlight_scatter)
        self.highlight_scatter.hide()
        
        self.selected_indices = set()
        self._is_selecting = False
        self._sel_path = []
        
        controls.addSpacing(10)
        controls.addWidget(QLabel("<b>Active Plot Series:</b>"))
        
        self.series_list = QListWidget()
        self.series_list.setMaximumHeight(100)
        self.series_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.series_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.series_list.setTextElideMode(Qt.ElideNone)
        self.series_list.itemSelectionChanged.connect(self.update_active_layer)
        
        controls.addWidget(self.series_list)
        
        btn_h = QHBoxLayout()
        self.add_series_btn = QPushButton("Add Pair")
        self.add_series_btn.setStyleSheet("font-weight: bold; color: #0055ff;")
        self.add_series_btn.clicked.connect(self.add_series_to_list)
        self.remove_series_btn = QPushButton("Remove")
        self.remove_series_btn.clicked.connect(self.remove_series_from_list)
        
        btn_h.addWidget(self.add_series_btn)
        btn_h.addWidget(self.remove_series_btn)
        controls.addLayout(btn_h)
        
        self.active_series_data = []
        self.series_list.itemSelectionChanged.connect(self.load_series_to_ui)
        self.xcol.currentIndexChanged.connect(self.update_current_series)
        self.ycol.currentIndexChanged.connect(self.update_current_series)
        self.zcol.currentIndexChanged.connect(self.update_current_series)

        self.heatmap_cmap_label = QLabel("Heatmap Colormap")
        self.heatmap_cmap_label.setVisible(False)
        controls.addWidget(self.heatmap_cmap_label)

        self.heatmap_cmap = QComboBox()
        self.heatmap_cmap.addItems(["viridis", "plasma", "inferno", "magma", "cividis", "jet", "gray"])
        self.heatmap_cmap.setVisible(False)
        self.heatmap_cmap.currentTextChanged.connect(self.plot)
        controls.addWidget(self.heatmap_cmap)
        
        self.snap_toggle_btn = QPushButton("✔ Snap Crosshair to Point")
        self.snap_toggle_btn.setCheckable(True)
        self.snap_toggle_btn.setChecked(True)
        self.snap_toggle_btn.setVisible(False)
        self.snap_toggle_btn.clicked.connect(self._update_snap_btn_ui)
        controls.addWidget(self.snap_toggle_btn)
        
        controls.addSpacing(10)
        controls.addWidget(button("Plot", self.plot))
        controls.addWidget(button("Save Plot", self.save_plot))
        controls.addWidget(button("Export Plotted Data", self.export_plotted_data))
        controls.addStretch()
        
        self.func_details_btn = QPushButton("Function Details")
        self.func_details_btn.setVisible(False)
        self.func_details_btn.clicked.connect(self.show_function_details)
        controls.addWidget(self.func_details_btn)

        self.edit_fit_btn = QPushButton("Edit Fit")
        self.edit_fit_btn.clicked.connect(self.edit_fit)
        self.edit_fit_btn.setVisible(False)
        controls.addWidget(self.edit_fit_btn)
    
        self.save_function_btn = QPushButton("Save Function")
        self.save_function_btn.clicked.connect(self.save_function)
        self.save_function_btn.setVisible(False)
        controls.addWidget(self.save_function_btn)
        
        self.clear_fit_btn = QPushButton("Clear Plot")
        self.clear_fit_btn.clicked.connect(self.clear_fit)
        self.clear_fit_btn.setVisible(False)
        controls.addWidget(self.clear_fit_btn)
    
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.35)
        
        self.legend = self.plot_widget.addLegend(offset=(10, 10))
        self.fit_legend = pg.LegendItem(offset=(-10, 10))
        self.fit_legend.setParentItem(self.plot_widget.getViewBox())
        
        for ax in ("left", "bottom", "right", "top"):
            self.plot_widget.showAxis(ax)
            a = self.plot_widget.getAxis(ax)
            a.setPen(pg.mkPen("k")) 
            
            if ax in ("top", "right"):
                a.linkToView(self.plot_widget.getViewBox())
                a.setStyle(showValues=True)
                a.setTextPen(pg.mkPen("w")) 
            else:
                a.setStyle(showValues=True)
                a.setTextPen(pg.mkPen("k"))
        
        main.addWidget(self.plot_stack, 1)

        self.heatmap_item = pg.HistogramLUTItem()
        self.plot_widget.plotItem.layout.addItem(self.heatmap_item, 2, 3)
        self.heatmap_item.setVisible(False) 
        
        self.heatmap_item.layout.removeItem(self.heatmap_item.axis)
        self.heatmap_item.layout.removeItem(self.heatmap_item.vb)
        self.heatmap_item.layout.removeItem(self.heatmap_item.gradient)
        
        new_axis = CustomAxisItem('left', linkView=self.heatmap_item.vb, maxTickLength=-5, parent=self.heatmap_item)
        self.heatmap_item.axis.deleteLater()
        self.heatmap_item.axis = new_axis   
        
        self.heatmap_item.layout.addItem(self.heatmap_item.axis, 0, 0)
        self.heatmap_item.layout.addItem(self.heatmap_item.gradient, 0, 1)
        self.heatmap_item.layout.addItem(self.heatmap_item.vb, 0, 2)
        
        self.heatmap_item.axis.setPen(pg.mkPen("k"))
        self.heatmap_item.axis.setTextPen(pg.mkPen("k"))
        self.heatmap_item.vb.setMinimumWidth(50)
                
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.vLine.setPen(pg.mkPen(color='k', style=Qt.DashLine))
        self.hLine.setPen(pg.mkPen(color='k', style=Qt.DashLine))
        
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        self.vLine.hide()
        self.hLine.hide()
        
        self.crosshairs_enabled = False
        
        self.crosshair_label = QLabel(self.plot_wrapper)
        self.crosshair_label.setStyleSheet("""
            background-color: rgba(255, 255, 255, 220); 
            border: 1px solid #333; border-radius: 4px; 
            padding: 5px; font-weight: bold; font-family: Consolas;
            font-size: 14px; color: black;
        """)
        self.crosshair_label.hide()
        
        self.stats_label = DraggableLabel(self.plot_wrapper)
        self.stats_label.setStyleSheet("""
            background-color: rgba(240, 248, 255, 230); 
            border: 2px solid #0055ff; 
            border-radius: 6px; 
            padding: 8px; 
            font-family: Consolas, monospace;
            font-size: 13px; 
            color: #111;
        """)
        self.stats_label.hide()
        
        self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)

    def toggle_crosshairs(self):
        self.crosshairs_enabled = not getattr(self, 'crosshairs_enabled', False)
        if not self.crosshairs_enabled:
            self.vLine.hide()
            self.hLine.hide()
            self.crosshair_label.hide()
            self.snap_toggle_btn.setVisible(False)
        else:
            self.snap_toggle_btn.setVisible(True)
            
    def _update_snap_btn_ui(self):
        if self.snap_toggle_btn.isChecked():
            self.snap_toggle_btn.setText("✔ Snap Crosshair to Point")
            self.snap_toggle_btn.setStyleSheet("font-weight: bold; color: #2ca02c; border: 2px solid #2ca02c; padding: 6px; background-color: #f5f5f5;")
        else:
            self.snap_toggle_btn.setText("✖ Free Crosshair")
            self.snap_toggle_btn.setStyleSheet("font-weight: bold; color: #d90000; border: 2px solid #d90000; padding: 6px; background-color: #f5f5f5;")

    def mouse_moved(self, evt):
        if not getattr(self, 'crosshairs_enabled', False) or self.plot_mode != "2D":
            return
            
        pos = evt[0]
        if self.plot_widget.sceneBoundingRect().contains(pos):
            pos_left = self.plot_widget.plotItem.vb.mapSceneToView(pos)
            pos_right = self.vb_right.mapSceneToView(pos)
            
            row = self.series_list.currentRow()
            is_right_active = False
            if row >= 0 and self.series_data.get("2D"):
                if self.series_data["2D"][row].get("axis", "L") == "R":
                    is_right_active = True
            
            if not self.snap_toggle_btn.isChecked():
                if is_right_active:
                    mx, my = pos_right.x(), pos_right.y()
                    draw_x, draw_y = pos_left.x(), pos_left.y() 
                else:
                    mx, my = pos_left.x(), pos_left.y()
                    draw_x, draw_y = mx, my
                    
                self.vLine.setPos(draw_x)
                self.hLine.setPos(draw_y)
                self.crosshair_label.setText(f"X: {mx:.6g}\nY: {my:.6g}")
                
            else:
                min_dist = float('inf')
                closest_p = None
                
                xr_l = self.plot_widget.plotItem.vb.viewRange()[0]
                yr_l = self.plot_widget.plotItem.vb.viewRange()[1]
                x_span_l = max(1e-15, xr_l[1] - xr_l[0])
                y_span_l = max(1e-15, yr_l[1] - yr_l[0])
                
                xr_r = self.vb_right.viewRange()[0]
                yr_r = self.vb_right.viewRange()[1]
                x_span_r = max(1e-15, xr_r[1] - xr_r[0])
                y_span_r = max(1e-15, yr_r[1] - yr_r[0])
                
                if hasattr(self, 'last_plotted_data') and isinstance(self.last_plotted_data, dict):
                    for pkg in self.last_plotted_data.get('packages', []):
                        if pkg['type'] == 'standard': x, y = pkg['x'], pkg['y']
                        elif pkg['type'] == 'average': x, y = np.array([pkg['x_mean']]), np.array([pkg['y_mean']])
                        else: continue
                            
                        if len(x) == 0: continue
                        
                        axis_side = pkg.get("axis", "L")
                        if axis_side == "R":
                            mx, my = pos_right.x(), pos_right.y()
                            x_span, y_span = x_span_r, y_span_r
                        else:
                            mx, my = pos_left.x(), pos_left.y()
                            x_span, y_span = x_span_l, y_span_l
                        
                        dist = ((x - mx) / x_span)**2 + ((y - my) / y_span)**2
                        idx = dist.argmin()
                        if dist[idx] < min_dist:
                            min_dist = dist[idx]
                            closest_p = (x[idx], y[idx], axis_side)
            
                if hasattr(self, 'active_fits') and self.active_fits:
                    for fit in self.active_fits:
                        if "x_raw" in fit and "y_raw" in fit:
                            x, y = fit["x_raw"], fit["y_raw"]
                            if len(x) == 0: continue
                            
                            mx, my = pos_left.x(), pos_left.y()
                            dist = ((x - mx) / x_span_l)**2 + ((y - my) / y_span_l)**2
                            idx = dist.argmin()
                            if dist[idx] < min_dist:
                                min_dist = dist[idx]
                                closest_p = (x[idx], y[idx], "L")

                if closest_p:
                    cx, cy, side = closest_p
                    if side == "R":
                        import pyqtgraph as pg
                        pt_right = pg.Point(cx, cy)
                        pixel_pos = self.vb_right.mapViewToScene(pt_right)
                        pt_left = self.plot_widget.plotItem.vb.mapSceneToView(pixel_pos)
                        draw_x, draw_y = pt_left.x(), pt_left.y()
                    else:
                        draw_x, draw_y = cx, cy
                        
                    self.vLine.setPos(draw_x)
                    self.hLine.setPos(draw_y)
                    self.crosshair_label.setText(f"X: {cx:.6g}\nY: {cy:.6g}")

            self.crosshair_label.adjustSize()
            w = self.plot_wrapper.width()
            h = self.plot_wrapper.height()
            lw = self.crosshair_label.width()
            lh = self.crosshair_label.height()
            self.crosshair_label.move(w - lw - 10, h - lh - 10)
            
            if not self.crosshair_label.isVisible():
                self.vLine.show()
                self.hLine.show()
                self.crosshair_label.show()
        else:
            self.vLine.hide()
            self.hLine.hide()
            self.crosshair_label.hide()

    def show_function_details(self):
        if not getattr(self, 'active_fits', []): return
        
        if len(self.active_fits) == 1:
            fit = self.active_fits[0]
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "View", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        ftype = fit["type"].capitalize()
        eq_str = fit.get("equation", "")
        coeff_str = ""
        math_style = "font-size: 20px; font-family: Cambria, serif; font-style: italic;"

        if ftype == "Polynomial":
            coeff_str = "<br>".join([f"c<sub>{i}</sub> = {c:.6e}" for i, c in enumerate(fit["coeffs"])])
        elif ftype == "Logarithmic":
            base = fit["base"]
            eq_str = f"<span style='{math_style}'>y = a &middot; ln(x) + c</span>" if str(base).lower() == "e" else f"<span style='{math_style}'>y = a &middot; log<sub>{base}</sub>(x) + c</span>"
            coeff_str = f"a = {fit['params'][0]:.6e}<br>c = {fit['params'][1]:.6e}"
        elif ftype == "Exponential":
            eq_str = f"<span style='{math_style}'>y = a &middot; e<sup>bx</sup> + c</span>"
            coeff_str = f"a = {fit['params'][0]:.6e}<br>b = {fit['params'][1]:.6e}<br>c = {fit['params'][2]:.6e}"
        elif ftype == "Gaussian":
            eq_str = f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2'><tr><td rowspan='2' valign='middle'>y = A &middot; exp&nbsp;&nbsp;[ &minus;</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;(x &minus; &mu;)<sup>2</sup>&nbsp;</td><td rowspan='2' valign='middle'>]</td></tr><tr><td align='center'>2&sigma;<sup>2</sup></td></tr></table>"
            coeff_str = f"A = {fit['params'][0]:.6e}<br>&mu; = {fit['params'][1]:.6e}<br>&sigma; = {fit['params'][2]:.6e}"
        elif ftype == "Lorentzian":
            eq_str = f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2'><tr><td rowspan='2' valign='middle'>y = </td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;A&nbsp;</td></tr><tr><td align='center'><table style='{math_style}' border='0' cellspacing='0' cellpadding='0'><tr><td rowspan='2' valign='middle'>1 + &nbsp;[</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;x &minus; x<sub>0</sub>&nbsp;</td><td rowspan='2' valign='middle'>]<sup>2</sup></td></tr><tr><td align='center'>&gamma;</td></tr></table></td></tr></table>"
            coeff_str = f"A = {fit['params'][0]:.6e}<br>x<sub>0</sub> = {fit['params'][1]:.6e}<br>&gamma; = {fit['params'][2]:.6e}"
        elif ftype == "Custom":
            display_eq = fit.get('html_equation', fit.get('equation', ''))
            eq_str = f"<span style='{math_style}'>y = {display_eq}</span>"
            coeff_str = "<br>".join([f"{GREEK_MAP.get(p, p)} = {v:.6e}" for p, v in zip(fit['param_names'], fit['params'])])

        msg = QMessageBox(self)
        msg.setWindowTitle(f"Function Details: {fit['name']}")
        msg.setText(f"<b style='font-size: 16px;'>Fit Type:</b> <span style='font-size: 16px;'>{ftype}</span>")
        msg.setStyleSheet("QLabel { font-size: 14px; }")
        msg.setInformativeText(f"<b>Equation Form:</b><br><br>{eq_str}<br><b>Calculated Coefficients:</b><br><span style='font-family: Consolas, monospace; font-size: 15px;'>{coeff_str}</span>")
        msg.exec()

    def set_plot_mode(self, mode):
        if mode == "3D" and not OPENGL_AVAILABLE:
            QMessageBox.warning(self, "3D Not Available", "3D plotting requires OpenGL support.\n\nInstall pyqtgraph with OpenGL enabled.\n\nThis can be done with: pip install PyOpenGL PyOpenGL_accelerate")
            return
    
        self.plot_mode = mode
        self._update_graphtype_dropdown()
        
        is_heatmap = (mode == "Heatmap")
        self.heatmap_cmap.setVisible(is_heatmap)
        self.heatmap_cmap_label.setVisible(is_heatmap)
        
        show_z = (mode != "2D")
        self.zcol.setVisible(show_z)
        self.zcol_label.setVisible(show_z)
        self.zscale_label.setVisible(show_z)
        self.zscale.setVisible(show_z)
        self.zbase.setVisible(show_z and self.zscale.currentText() == "Log")
        
        self.heatmap_item.setVisible(is_heatmap)
        
        if hasattr(self, 'series_data'):
            self._refresh_series_list_ui()
    
        if mode == "2D": self.plot_layout.setCurrentWidget(self.plot_wrapper)
        elif mode == "3D": self.plot_layout.setCurrentWidget(self.gl_widget)
        elif mode == "Heatmap": self.plot_layout.setCurrentWidget(self.plot_wrapper)
        
        if hasattr(self, '_update_uncert_visibility'):
            self._update_uncert_visibility()
    
        if self.dataset:
            self.plot()

    def _update_aspect_ui(self, text):
        is_custom = (text == "Custom")
        self.aspect_w_edit.setVisible(is_custom)
        self.aspect_h_edit.setVisible(is_custom)
        self.aspect_colon.setVisible(is_custom)
        self._resize_plot_widget()

    def get_aspect_ratio(self):
        text = self.aspect_combo.currentText()
        if text == "Free": return None
        if text == "1:1": return 1.0
        if text == "4:3": return 4.0 / 3.0
        if text == "16:9": return 16.0 / 9.0
        if text == "Custom":
            try:
                w = float(self.aspect_w_edit.text())
                h = float(self.aspect_h_edit.text())
                if h <= 0 or w <= 0: return None
                return w / h
            except ValueError:
                return None
        return None

    def _on_plot_stack_resize(self, event):
        self.original_plot_stack_resize(event)
        self._resize_plot_widget()
        
    def _resize_plot_widget(self):
        ratio = self.get_aspect_ratio()
        if ratio is None:
            self.plot_widget.setMinimumSize(0, 0)
            self.plot_widget.setMaximumSize(16777215, 16777215)
            return
            
        aw = self.plot_wrapper.width()
        ah = self.plot_wrapper.height()
        if aw <= 0 or ah <= 0: return
        
        if aw / ah > ratio:
            th, tw = ah, ah * ratio
        else:
            tw, th = aw, aw / ratio
            
        self.plot_widget.setFixedSize(int(tw), int(th))

    def _update_xscale_ui(self):
        self.xbase.setVisible(self.xscale.currentText() == "Log")

    def _update_yscale_ui(self):
        self.ybase.setVisible(self.yscale.currentText() == "Log")
        
    def _update_zscale_ui(self):
        is_log = self.zscale.currentText() == "Log"
        is_3d_or_heat = self.plot_mode != "2D"
        self.zbase.setVisible(is_log and is_3d_or_heat)
    
    def toggle_averaging(self):
        self.average_enabled = not self.average_enabled
        self.errorbar_btn.setVisible(self.average_enabled)
        self.errorbar_sigma_edit.setVisible(self.average_enabled)
        if not self.average_enabled:
            self.errorbars_enabled = False
        self.plot()
        
    def toggle_errorbars(self):
        self.errorbars_enabled = not self.errorbars_enabled
        self.plot()

    def _fix_graphics_view(self):
        view = self.plot_widget.getViewBox().scene().views()[0]
        view.setViewportUpdateMode(view.FullViewportUpdate)
        view.setCacheMode(view.CacheNone)

    def _patch_pyqtgraph_menu(self):
        menu = self.plot_widget.getViewBox().menu
        def fix_palette():
            for w in menu.findChildren(QLineEdit):
                pal = w.palette()
                pal.setColor(QPalette.Base, QColor("white"))
                pal.setColor(QPalette.Text, QColor("black"))
                w.setPalette(pal)
        menu.aboutToShow.connect(fix_palette)

    def _apply_styles(self):
        self.setStyleSheet("""
            QPushButton {
                background-color: #f5f5f5;
                border: 1px solid #8a8a8a;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #e6e6e6; }
            QPushButton:pressed { background-color: #d0d0d0; }
            QLineEdit, QComboBox {
                background-color: white;
                color: black;
                border: 1px solid #8a8a8a;
                padding: 4px;
            }
        """)

    def _init_3d_scene(self, data_bounds=None):
        axis_length = 11.0
        gz = gl.GLGridItem()
        gz.setSize(x=10, y=10, z=0)
        gz.setSpacing(x=1, y=1, z=0)
        gz.setColor((150, 150, 150, 255)) 
        gz.translate(5, 5, -0.1) 
        self.gl_widget.addItem(gz)
    
        x_axis = gl.GLLinePlotItem(pos=np.array([[0, 0, -0.1], [axis_length, 0, -0.1]]), color=(1, 0.2, 0.2, 1), width=4, antialias=True)
        y_axis = gl.GLLinePlotItem(pos=np.array([[0, 0, -0.1], [0, axis_length, -0.1]]), color=(0.2, 1, 0.2, 1), width=4, antialias=True)
        z_axis = gl.GLLinePlotItem(pos=np.array([[0, 0, -0.1], [0, 0, axis_length]]), color=(0.2, 0.5, 1, 1), width=4, antialias=True)
    
        self.gl_widget.addItem(x_axis)
        self.gl_widget.addItem(y_axis)
        self.gl_widget.addItem(z_axis)

        if data_bounds is None: return
        try: from pyqtgraph.opengl import GLTextItem
        except ImportError: return

        mins, maxs = data_bounds
        spans = maxs - mins
        spans[spans == 0] = 1.0 

        x_name = self.xcol.currentText().split(": ")[-1] if ":" in self.xcol.currentText() else "X"
        y_name = self.ycol.currentText().split(": ")[-1] if ":" in self.ycol.currentText() else "Y"
        z_name = self.zcol.currentText().split(": ")[-1] if ":" in self.zcol.currentText() else "Z"

        xlog, ylog, zlog = self.xscale.currentText() == "Log", self.yscale.currentText() == "Log", self.zscale.currentText() == "Log"
        xbase = self._parse_log_base(self.xbase.text())
        ybase = self._parse_log_base(self.ybase.text())
        zbase = self._parse_log_base(self.zbase.text())
        
        superscripts = {'0':'⁰', '1':'¹', '2':'²', '3':'³', '4':'⁴', '5':'⁵', '6':'⁶', '7':'⁷', '8':'⁸', '9':'⁹', '-':'⁻', '.':'⋅'}
        def format_val_3d(v, is_log, base):
            if is_log:
                if abs(v - round(v)) < 1e-4:
                    exp_str = "".join(superscripts.get(c, c) for c in str(int(round(v))))
                    b_str = "e" if abs(base - np.e) < 1e-4 else f"{base:g}"
                    return f"{b_str}{exp_str}"
                else:
                    with np.errstate(over='ignore', invalid='ignore'):
                        orig = np.power(base, float(v))
                    if np.isinf(orig) or np.isnan(orig): return ""
                    if abs(orig) < 1e-3 or abs(orig) > 1e4: return f"{orig:.1e}"
                    return f"{orig:.2g}"
            else:
                if v == 0: return "0"
                if abs(v) < 1e-3 or abs(v) > 1e4: return f"{v:.2e}"
                return f"{v:.3g}"

        num_ticks = 5
        tick_positions = np.linspace(0, 10, num_ticks)
        font = pg.QtGui.QFont("Arial", 10)
        label_font = pg.QtGui.QFont("Arial", 12, pg.QtGui.QFont.Bold)
        text_color = (200, 200, 200, 255) 

        def add_tick_line(p1, p2):
            self.gl_widget.addItem(gl.GLLinePlotItem(pos=np.array([p1, p2]), color=(0.7, 0.7, 0.7, 1), width=2))

        for pos in tick_positions:
            val = mins[0] + (pos / 10.0) * spans[0]
            add_tick_line([pos, 0, -0.1], [pos, -0.3, -0.1])
            self.gl_widget.addItem(GLTextItem(pos=[pos, -0.5, -0.1], text=format_val_3d(val, xlog, xbase), font=font, color=text_color))
        self.gl_widget.addItem(GLTextItem(pos=[5, -1.8, -0.1], text=x_name, font=label_font, color=(255, 255, 255, 255)))

        for pos in tick_positions:
            val = mins[1] + (pos / 10.0) * spans[1]
            add_tick_line([0, pos, -0.1], [-0.3, pos, -0.1])
            self.gl_widget.addItem(GLTextItem(pos=[-0.5, pos, -0.1], text=format_val_3d(val, ylog, ybase), font=font, color=text_color))
        self.gl_widget.addItem(GLTextItem(pos=[-2.2, 5, -0.1], text=y_name, font=label_font, color=(255, 255, 255, 255)))

        for pos in tick_positions[1:]: 
            val = mins[2] + (pos / 10.0) * spans[2]
            add_tick_line([0, 0, pos], [-0.3, 0, pos])
            self.gl_widget.addItem(GLTextItem(pos=[-0.5, 0, pos], text=format_val_3d(val, zlog, zbase), font=font, color=text_color))
        self.gl_widget.addItem(GLTextItem(pos=[-1.5, 0, 5], text=z_name, font=label_font, color=(255, 255, 255, 255)))

    def toggle_legend(self):
        self.legend_visible = not self.legend_visible
        self.legend.setVisible(self.legend_visible)
        self.fit_legend.setVisible(self.legend_visible)

    def restore_state(self):
        if geo := self.settings.value("geometry"): self.restoreGeometry(geo)
        
        self.legend_visible = self.settings.value("legend", True, bool)
        self.fit_legend.setVisible(self.legend_visible)
        self.average_enabled = self.settings.value("average", False, bool)
        self.last_file = self.settings.value("last_file", "")
        self.file_type = self.settings.value("file_type", "BadgerLoop")
        
        if not BADGERLOOP_AVAILABLE and self.file_type == "BadgerLoop":
            self.file_type = "CSV"
            self.last_file = "" 
    
        self.xscale.setCurrentText(self.settings.value("xscale", "Linear"))
        self.yscale.setCurrentText(self.settings.value("yscale", "Linear"))
        self.zscale.setCurrentText(self.settings.value("zscale", "Linear")) 
        self.xbase.setText(self.settings.value("xbase", "10"))
        self.ybase.setText(self.settings.value("ybase", "10"))
        self.zbase.setText(self.settings.value("zbase", "10")) 
        
        self.sweeps_edit.setText(self.settings.value("sweeps", "-1"))
        self.points_edit.setText(self.settings.value("points", "-1"))
        self.label_fontsize_edit.setText(self.settings.value("label_fontsize", "12"))
        self.tick_fontsize_edit.setText(self.settings.value("tick_fontsize", "10"))
        self.errorbar_sigma_edit.setText(self.settings.value("errorbar_sigma", "1.0"))
        
        self.errorbars_enabled = self.settings.value("errorbars", False, bool)
        self.errorbar_btn.setVisible(self.average_enabled)
        self.errorbar_sigma_edit.setVisible(self.average_enabled)
        self.graphtype.setCurrentText(self.settings.value("graphtype", "Line"))
        self.heatmap_cmap.setCurrentText(self.settings.value("heatmap_cmap", "viridis"))
        self.plot_mode = self.settings.value("plot_mode", "2D")
        self.set_plot_mode(self.plot_mode)
        self.aspect_w_edit.setText(self.settings.value("aspect_w", "16"))
        self.aspect_h_edit.setText(self.settings.value("aspect_h", "9"))
        self.aspect_combo.setCurrentText(self.settings.value("aspect_mode", "Free"))
        self._update_aspect_ui(self.aspect_combo.currentText())
        
        show_z = (self.plot_mode != "2D")
        self.zcol.setVisible(show_z)
        self.zcol_label.setVisible(show_z)
        self.zscale_label.setVisible(show_z)
        self.zscale.setVisible(show_z)
        self.zbase.setVisible(show_z and self.zscale.currentText() == "Log")
        
        snap_on = self.settings.value("crosshair_snap", True, bool)
        if hasattr(self, 'snap_toggle_btn'):
            self.snap_toggle_btn.setChecked(snap_on)
            self._update_snap_btn_ui()
        
        is_heatmap = (self.plot_mode == "Heatmap")
        self.heatmap_cmap.setVisible(is_heatmap)
        self.heatmap_cmap_label.setVisible(is_heatmap)
        
        if self.plot_mode == "2D": self.plot_layout.setCurrentWidget(self.plot_wrapper)
        elif self.plot_mode == "3D" and OPENGL_AVAILABLE: self.plot_layout.setCurrentWidget(self.gl_widget)
        elif self.plot_mode == "Heatmap": self.plot_layout.setCurrentWidget(self.plot_widget)
    
        if self.last_file and os.path.exists(self.last_file):
            try:
                if self.file_type == "CSV": self.dataset = CSVDataset(self.last_file)
                else: self.dataset = Dataset(self.last_file)
                self.populate_columns()
                
                saved_series_str = self.settings.value("series_data", "")
                max_idx = len(self.dataset.column_names) - 1
                
                default_pair = {
                    "x": 0, "y": min(1, max_idx), "z": min(2, max_idx),
                    "x_name": self.dataset.column_names.get(0, "X"),
                    "y_name": self.dataset.column_names.get(min(1, max_idx), "Y"),
                    "z_name": self.dataset.column_names.get(min(2, max_idx), "Z")
                }
                
                if saved_series_str:
                    try:
                        restored_data = json.loads(saved_series_str)
                        for mode in ["2D", "3D", "Heatmap"]:
                            if mode in restored_data and restored_data[mode]:
                                for pair in restored_data[mode]:
                                    pair['x'] = min(pair.get('x', 0), max_idx)
                                    pair['y'] = min(pair.get('y', 0), max_idx)
                                    pair['z'] = min(pair.get('z', 0), max_idx)
                                    pair['x_name'] = self.dataset.column_names.get(pair['x'], "X")
                                    pair['y_name'] = self.dataset.column_names.get(pair['y'], "Y")
                                    pair['z_name'] = self.dataset.column_names.get(pair['z'], "Z")
                            else:
                                restored_data[mode] = [dict(default_pair)]
                        self.series_data = restored_data
                    except Exception:
                        self.series_data = {"2D": [dict(default_pair)], "3D": [dict(default_pair)], "Heatmap": [dict(default_pair)]}
                else:
                    self.series_data = {"2D": [dict(default_pair)], "3D": [dict(default_pair)], "Heatmap": [dict(default_pair)]}
                
                self.update_file_mode_ui()
                self.point_size_edit.setText(self.settings.value("point_size", "5"))
        
                saved_labels_str = self.settings.value("custom_axis_labels", "")
                if saved_labels_str:
                    try: self.custom_axis_labels = json.loads(saved_labels_str)
                    except Exception: self.custom_axis_labels = {"bottom": None, "left": None, "top": None, "right": None}
                
                if self.plot_mode == "2D": self.plot_layout.setCurrentWidget(self.plot_wrapper)
                elif self.plot_mode == "3D" and OPENGL_AVAILABLE: self.plot_layout.setCurrentWidget(self.gl_widget)
                elif self.plot_mode == "Heatmap": self.plot_layout.setCurrentWidget(self.plot_wrapper)
                
                current_pair = self.series_data[self.plot_mode][0]
                self.xcol.blockSignals(True); self.ycol.blockSignals(True); self.zcol.blockSignals(True)
                self.xcol.setCurrentIndex(current_pair['x'])
                self.ycol.setCurrentIndex(current_pair['y'])
                if self.zcol.count() > current_pair.get('z', 0):
                    self.zcol.setCurrentIndex(current_pair.get('z', 0))
                self.xcol.blockSignals(False); self.ycol.blockSignals(False); self.zcol.blockSignals(False)
                
                self._refresh_series_list_ui()
                self.plot()
            except Exception as e:
                import traceback
                print(f"Startup safety triggered. Abandoned last file due to: {e}\n{traceback.format_exc()}")
                self.dataset = None
                self.last_file = ""
                self.file_type = "BadgerLoop"

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("legend", self.legend_visible)
        self.settings.setValue("last_file", self.last_file)
        self.settings.setValue("file_type", self.file_type)
        self.settings.setValue("xscale", self.xscale.currentText())
        self.settings.setValue("yscale", self.yscale.currentText())
        self.settings.setValue("zscale", self.zscale.currentText()) 
        self.settings.setValue("xbase", self.xbase.text())
        self.settings.setValue("ybase", self.ybase.text())
        self.settings.setValue("zbase", self.zbase.text()) 
        self.settings.setValue("sweeps", self.sweeps_edit.text())
        self.settings.setValue("points", self.points_edit.text())
        self.settings.setValue("label_fontsize", self.label_fontsize_edit.text())
        self.settings.setValue("tick_fontsize", self.tick_fontsize_edit.text())
        self.settings.setValue("xcol", self.xcol.currentIndex())
        self.settings.setValue("ycol", self.ycol.currentIndex())
        self.settings.setValue("average", self.average_enabled)
        self.settings.setValue("errorbars", self.errorbars_enabled)
        self.settings.setValue("errorbar_sigma", self.errorbar_sigma_edit.text())
        self.settings.setValue("aspect_mode", self.aspect_combo.currentText())
        self.settings.setValue("aspect_w", self.aspect_w_edit.text())
        self.settings.setValue("aspect_h", self.aspect_h_edit.text())
        
        if hasattr(self, 'snap_toggle_btn'):
            self.settings.setValue("crosshair_snap", self.snap_toggle_btn.isChecked())
        
        self.settings.setValue("series_data", json.dumps(self.series_data))
        self.settings.setValue("point_size", self.point_size_edit.text())
        self.settings.setValue("custom_axis_labels", json.dumps(self.custom_axis_labels))
        
        if self.gl_widget is not None:
            try:
                self.gl_widget.makeCurrent()
                import OpenGL.contextdata
                OpenGL.contextdata.cleanupContext()
                self.gl_widget.doneCurrent()
            except Exception: pass
            self.gl_widget.setParent(None)
            self.gl_widget.deleteLater()
            self.gl_widget = None
                
        self.settings.setValue("graphtype", self.graphtype.currentText())
        self.settings.setValue("plot_mode", self.plot_mode)
        self.settings.setValue("heatmap_cmap", self.heatmap_cmap.currentText())
    
        super().closeEvent(e)

    def open_file(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Open Data File", "", "All supported files (*.txt *.csv);;Text files (*.txt);;CSV files (*.csv);;All files (*)")
        if not fname: return

        dlg = FileImportDialog(self)
        if dlg.exec() == QDialog.Accepted:
            opts = dlg.get_options()
            is_badgerloop_actual = False
            try:
                with open(fname, 'r', encoding='utf-8', errors='ignore') as f:
                    for _ in range(50):
                        line = f.readline()
                        if not line: break
                        if line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or line.startswith("###DATA"):
                            is_badgerloop_actual = True
                            break
            except Exception: pass
                
            if opts["type"] == "CSV" and is_badgerloop_actual:
                QMessageBox.critical(self, "Format Mismatch", "You selected 'CSV', but this appears to be a native BadgerLoop file.\n\nPlease open the file again and select 'BadgerLoop' as the File Type.")
                return
                
            if opts["type"] == "BadgerLoop" and not is_badgerloop_actual:
                QMessageBox.critical(self, "Format Mismatch", "You selected 'BadgerLoop', but this file is missing standard BadgerLoop headers (e.g., ###INPUTS, ###DATA). It is likely a standard CSV or text file.\n\nPlease open the file again and select 'CSV' as the File Type.")
                return
                
            if opts["type"] == "CSV":
                import csv
                detected_delim = "," 
                sniff_success = False
                try:
                    with open(fname, 'r', encoding='utf-8', errors='ignore') as f:
                        sample_lines = []
                        chars_read = 0
                        for line in f:
                            if not line.lstrip().startswith('#') and line.strip():
                                sample_lines.append(line)
                                chars_read += len(line)
                            if chars_read > 4096: break
                        sample = "".join(sample_lines)
                        
                        if sample.strip():
                            sniffer = csv.Sniffer()
                            possible_delims = ',\t; |'
                            if opts["delimiter"] not in ["auto", ""] and len(opts["delimiter"]) == 1:
                                possible_delims += opts["delimiter"]
                            detected_delim = sniffer.sniff(sample, delimiters=possible_delims).delimiter
                            sniff_success = True
                except Exception: pass
                    
                if opts["delimiter"] == "auto":
                    opts["delimiter"] = detected_delim
                elif sniff_success and detected_delim != opts["delimiter"]:
                    delim_names = {',': 'Comma', '\t': 'Tab', ';': 'Semicolon', ' ': 'Space', '|': 'Pipe'}
                    det_name = delim_names.get(detected_delim, f"'{detected_delim}'")
                    sel_name = delim_names.get(opts["delimiter"], f"'{opts['delimiter']}'")
                    
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Delimiter Mismatch")
                    msg.setText(f"{sel_name} delimiter selected, but {det_name} delimiter detected.")
                    msg.setInformativeText("How would you like to proceed?")
                    
                    btn_detected = msg.addButton(f"Use {det_name}", QMessageBox.AcceptRole)
                    btn_anyway = msg.addButton("Try Anyway", QMessageBox.DestructiveRole)
                    btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
                    msg.exec()
                    
                    if msg.clickedButton() == btn_cancel: return 
                    elif msg.clickedButton() == btn_detected: opts["delimiter"] = detected_delim 

            if hasattr(self, 'progress_dialog'): self.progress_dialog.deleteLater()
            self.progress_dialog = QProgressDialog("Initializing...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("Loading Data")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setAutoClose(False)
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()
            QApplication.processEvents() 

            self.loader_thread = DataLoaderThread(fname, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, fname, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()

    def _update_progress_ui(self, percent, text):
        if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
            self.progress_dialog.setLabelText(text)
            self.progress_dialog.setValue(percent)

    def _on_load_finished(self, dataset, fname, opts):
        self.progress_dialog.setLabelText("File loaded. Preparing plot...")
        self.file_type = opts["type"]
        self.last_file = fname
        self.dataset = dataset
        self.last_load_opts = opts 
        
        if hasattr(self, 'active_fits') and self.active_fits:
            for fit in self.active_fits:
                self.plot_widget.removeItem(fit["plot_item"])
            self.active_fits.clear()
            self.fit_legend.clear()
            self.save_function_btn.setVisible(False)
            self.clear_fit_btn.setVisible(False)
            if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(False)
            if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(False)
        
        self.populate_columns()
        max_idx = len(dataset.column_names) - 1
        default_pair = {
            "x": 0, "y": min(1, max_idx), "z": min(2, max_idx),
            "x_name": dataset.column_names.get(0, "X"),
            "y_name": dataset.column_names.get(min(1, max_idx), "Y"),
            "z_name": dataset.column_names.get(min(2, max_idx), "Z")
        }
        
        for mode in ["2D", "3D", "Heatmap"]:
            if getattr(self, 'series_data', None) and self.series_data.get(mode):
                for pair in self.series_data[mode]:
                    pair['x'] = min(pair.get('x', 0), max_idx)
                    pair['y'] = min(pair.get('y', 0), max_idx)
                    pair['z'] = min(pair.get('z', 0), max_idx)
                    pair['x_name'] = dataset.column_names.get(pair['x'], "X")
                    pair['y_name'] = dataset.column_names.get(pair['y'], "Y")
                    pair['z_name'] = dataset.column_names.get(pair['z'], "Z")
            else:
                if not hasattr(self, 'series_data'): self.series_data = {}
                self.series_data[mode] = [dict(default_pair)]

        self.update_file_mode_ui()
        current_pair = self.series_data[self.plot_mode][0]
        self.xcol.blockSignals(True); self.ycol.blockSignals(True); self.zcol.blockSignals(True)
        self.xcol.setCurrentIndex(current_pair['x'])
        self.ycol.setCurrentIndex(current_pair['y'])
        if self.zcol.count() > current_pair.get('z', 0):
            self.zcol.setCurrentIndex(current_pair.get('z', 0))
        self.xcol.blockSignals(False); self.ycol.blockSignals(False); self.zcol.blockSignals(False)
        
        self._refresh_series_list_ui()
        self.custom_axis_labels = {"bottom": None, "left": None, "top": None, "right": None}
        self.plot()

    def _on_load_error(self, err_msg):
        if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
        CopyableErrorDialog("Loading Error", "An error occurred while loading the data.", err_msg, self).exec()

    def populate_columns(self):
        self.xcol.clear()
        self.ycol.clear()
        self.zcol.clear()
        self.xuncert.clear()
        self.yuncert.clear()
        self.zuncert.clear()

        self.xuncert.addItem("None")
        self.yuncert.addItem("None")
        self.zuncert.addItem("None")
    
        for i, name in self.dataset.column_names.items():
            label = f"{i}: {name}"
            self.xcol.addItem(label)
            self.ycol.addItem(label)
            self.zcol.addItem(label)
            self.xuncert.addItem(label)
            self.yuncert.addItem(label)
            self.zuncert.addItem(label)

    def _prompt_custom_axis_label(self, orientation):
        from PyQt5.QtWidgets import QInputDialog
        current_label = self.custom_axis_labels.get(orientation) or ""
        new_label, ok = QInputDialog.getText(self, "Custom Axis Label", f"Enter custom text for the '{orientation.capitalize()}' axis label:\n(Leave blank to revert to default column name)", QLineEdit.Normal, current_label)
        if ok:
            self.custom_axis_labels[orientation] = new_label.strip() if new_label.strip() else None
            self.plot() 

    def _apply_axis_fonts(self):
        try:
            label_size = int(self.label_fontsize_edit.text())
            if label_size <= 0: raise ValueError
        except ValueError: label_size = 12
        try:
            tick_size = int(self.tick_fontsize_edit.text())
            if tick_size <= 0: raise ValueError
        except ValueError: tick_size = 10
            
        axes_to_update = [self.plot_widget.getAxis(ax) for ax in ("bottom", "left", "top", "right")]
        if hasattr(self, 'heatmap_item'): axes_to_update.append(self.heatmap_item.axis)

        for axis in axes_to_update:
            axis.label.setFont(pg.QtGui.QFont(axis.label.font().family(), label_size))
            axis.setStyle(tickFont=pg.QtGui.QFont(axis.label.font().family(), tick_size))

    def parse_list(self, text):
        if text.strip() == "-1": return -1
        if ":" in text: return list(range(*map(int, text.split(":"))))
        return [int(x) for x in text.split(",")]
        
    def _parse_log_base(self, text):
        t = text.strip().lower()
        if t == 'e': return np.e
        try: 
            v = float(t)
            return v if v > 0 else 10.0
        except ValueError: return 10.0

    def _refresh_series_list_ui(self):
        self.series_list.blockSignals(True)
        self.series_list.clear()
        for i in range(len(self.series_data[self.plot_mode])):
            self._create_series_list_item(i)
        if self.series_list.count() > 0:
            self.series_list.setCurrentRow(0)
            self._load_series_to_ui_internal(0)
        self.series_list.blockSignals(False)

    def _load_series_to_ui_internal(self, row):
        if row >= len(self.series_data[self.plot_mode]): return
        pair = self.series_data[self.plot_mode][row]
        self._is_updating_ui = True
        self.xcol.blockSignals(True); self.ycol.blockSignals(True); self.zcol.blockSignals(True)
        self.xcol.setCurrentIndex(pair['x'])
        self.ycol.setCurrentIndex(pair['y'])
        if 'z' in pair and self.zcol.count() > pair['z']: self.zcol.setCurrentIndex(pair['z'])
        self.xcol.blockSignals(False); self.ycol.blockSignals(False); self.zcol.blockSignals(False)
        self._is_updating_ui = False

    def load_series_to_ui(self):
        if getattr(self, '_is_updating_ui', False): return
        if hasattr(self, 'clear_selection'): self.clear_selection()
        row = self.series_list.currentRow()
        if row < 0: return
        self._load_series_to_ui_internal(row)
        if self.plot_mode in ["3D", "Heatmap"]: self.plot()

    def update_current_series(self):
        if getattr(self, '_is_updating_ui', False) or not self.dataset: return
        if hasattr(self, 'clear_selection'): self.clear_selection()
        row = self.series_list.currentRow()
        if row < 0: return

        try:
            xidx = max(0, self.xcol.currentIndex())
            yidx = max(0, self.ycol.currentIndex())
            zidx = max(0, self.zcol.currentIndex()) if self.zcol.isVisible() else 0

            x_name = self.dataset.column_names.get(xidx, "X")
            y_name = self.dataset.column_names.get(yidx, "Y")
            z_name = self.dataset.column_names.get(zidx, "Z")

            is_visible = self.series_data[self.plot_mode][row].get('visible', True)
            current_axis = self.series_data[self.plot_mode][row].get('axis', 'L')
            
            self.series_data[self.plot_mode][row] = {
                "x": xidx, "y": yidx, "z": zidx,
                "x_name": x_name, "y_name": y_name, "z_name": z_name,
                "visible": is_visible, "axis": current_axis
            }
            
            self.series_list.blockSignals(True)
            item = self.series_list.item(row)
            widget = self.series_list.itemWidget(item)
            label = widget.findChild(QLabel)
            if label: label.setText(f"{y_name} vs {x_name}")
            self.series_list.blockSignals(False)
            
            self.plot()
        except Exception: pass

    def add_series_to_list(self):
        if not self.dataset: return
        xidx = max(0, self.xcol.currentIndex())
        yidx = max(0, self.ycol.currentIndex())
        zidx = max(0, self.zcol.currentIndex()) if self.zcol.isVisible() else 0

        x_name = self.dataset.column_names.get(xidx, "X")
        y_name = self.dataset.column_names.get(yidx, "Y")
        z_name = self.dataset.column_names.get(zidx, "Z")
        
        self.series_data[self.plot_mode].append({
            "x": xidx, "y": yidx, "z": zidx,
            "x_name": x_name, "y_name": y_name, "z_name": z_name,
            "visible": True, "axis": "L"
        })
        
        self.series_list.blockSignals(True)
        self._create_series_list_item(len(self.series_data[self.plot_mode]) - 1)
        self.series_list.setCurrentRow(len(self.series_data[self.plot_mode]) - 1)
        self.series_list.blockSignals(False)
        
        if not getattr(self, '_is_updating_ui', False):
            self.plot()

    def remove_series_from_list(self):
        row = self.series_list.currentRow()
        if row >= 0:
            self.series_list.takeItem(row)
            self.series_data[self.plot_mode].pop(row)
            
            if not self.series_data[self.plot_mode]:
                self.add_series_to_list() 
            else:
                new_row = max(0, row - 1)
                self.series_list.blockSignals(True)
                self.series_list.setCurrentRow(new_row)
                self.series_list.blockSignals(False)
                self._load_series_to_ui_internal(new_row)
                self.plot()

    def plot(self):
        if not self.dataset: return
        if getattr(self, '_is_plotting', False) or (hasattr(self, 'plot_thread') and self.plot_thread.isRunning()): return 
        self._is_plotting = True
        
        if hasattr(self, 'clear_selection'): self.clear_selection()
        
        if not hasattr(self, '_pools_initialized'):
            self.curve_pool, self.scatter_pool, self.errorbar_pool, self.avg_error_pool = [], [], [], []
            self.heatmap_image_item = pg.ImageItem()
            self.plot_widget.addItem(self.heatmap_image_item)
            self.heatmap_item.setImageItem(self.heatmap_image_item)
            self._pools_initialized = True

        import copy
        current_mode_series = self.series_data.get(self.plot_mode, [])
        if not current_mode_series:
            self._is_plotting = False
            return
            
        if self.plot_mode == "2D": series_to_plot = copy.deepcopy(current_mode_series)
        else:
            row = max(0, self.series_list.currentRow())
            if row < len(current_mode_series): series_to_plot = [copy.deepcopy(current_mode_series[row])]
            else: series_to_plot = [copy.deepcopy(current_mode_series[0])]

        xidx = series_to_plot[0]['x']
        yidx = series_to_plot[0]['y']
        zidx = series_to_plot[0].get('z', 0)
        
        params = {
            "plot_mode": self.plot_mode,
            "active_series": series_to_plot,
            "xidx": xidx, "yidx": yidx, "zidx": zidx,
            "sweeps": self.parse_list(self.sweeps_edit.text()),
            "points": self.parse_list(self.points_edit.text()),
            "xlog": self.xscale.currentText() == "Log", 
            "ylog": self.yscale.currentText() == "Log",
            "zlog": getattr(self, 'zscale', None) and self.zscale.currentText() == "Log",
            "xbase": self._parse_log_base(self.xbase.text()),
            "ybase": self._parse_log_base(self.ybase.text()),
            "zbase": self._parse_log_base(self.zbase.text()) if getattr(self, 'zbase', None) else 10.0,
            "average_enabled": getattr(self, 'average_enabled', False) if self.file_type == "BadgerLoop" else False,
            "errorbars_enabled": getattr(self, 'errorbars_enabled', False) if self.file_type == "BadgerLoop" else False,
            "nsigma": float(self.errorbar_sigma_edit.text()) if self.errorbar_sigma_edit.text().replace('.','',1).isdigit() else 1.0,
            "csv_uncerts_enabled": getattr(self, 'csv_uncerts_enabled', False),
            "file_type": self.file_type, 
            "graphtype": self.graphtype.currentText(),
            "fft_mode_active": getattr(self, 'fft_mode_active', False)
        }
        
        if params["sweeps"] == -1: params["sweeps"] = list(range(self.dataset.num_sweeps))

        if hasattr(self, 'progress_dialog'): self.progress_dialog.deleteLater()
        self.progress_dialog = QProgressDialog("Processing Data...", None, 0, 100, self)
        self.progress_dialog.setWindowTitle("Plotting")
        self.progress_dialog.setWindowModality(Qt.WindowModal) 
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        QApplication.processEvents()
            
        try:
            self.plot_thread = PlotWorkerThread(self.dataset, params)
            self.plot_thread.progress.connect(self._update_progress_ui)
            self.plot_thread.finished_2d.connect(self._draw_2d)
            self.plot_thread.finished_3d.connect(self._draw_3d)
            self.plot_thread.finished_heatmap.connect(self._draw_heatmap)
            self.plot_thread.error.connect(self._on_plot_error)
            self.plot_thread.start()
        except Exception:
            self._is_plotting = False
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
        
    def _on_plot_error(self, err_msg):
        self._is_plotting = False
        if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
        if "Data is 1-Dimensional" in err_msg: QMessageBox.information(self, "Heatmap Requirement", err_msg)
        else: CopyableErrorDialog("Plotting Error", "An error occurred while mathematically processing the data:", err_msg, self).exec()

    def _draw_2d(self, packages, show_legend):
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            dummy_arr = np.array([0.0], dtype=np.float64)
            for c in self.curve_pool: 
                c.setData(x=dummy_arr, y=dummy_arr)
                c.setVisible(False)
                try: self.plot_widget.removeItem(c)
                except: pass
                try: self.vb_right.removeItem(c)
                except: pass
                
            for s in self.scatter_pool: 
                s.setData(x=dummy_arr, y=dummy_arr)
                s.setVisible(False)
                try: self.plot_widget.removeItem(s)
                except: pass
                try: self.vb_right.removeItem(s)
                except: pass
                
            for eb in self.errorbar_pool + self.avg_error_pool: 
                eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
                try: self.plot_widget.removeItem(eb)
                except: pass
                try: self.vb_right.removeItem(eb)
                except: pass
                
            self.legend.clear()
            self.fit_legend.clear()
            self.heatmap_image_item.setVisible(False)
            self.heatmap_item.setVisible(False)
            
            self.plot_widget.getViewBox().setLimits(xMin=-np.inf, xMax=np.inf, yMin=-np.inf, yMax=np.inf)
            if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(False)
    
            self.last_plotted_data = {'mode': '2D', 'packages': packages}
    
            xlog, ylog = self.xscale.currentText() == "Log", self.yscale.currentText() == "Log"
            xbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.xbase.text())
            ybase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.ybase.text())
            
            self.plot_widget.getAxis('bottom').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('top').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('left').set_custom_log(ylog, ybase)
            self.plot_widget.getAxis('right').set_custom_log(ylog, ybase)
    
            try: pt_size = int(self.point_size_edit.text())
            except ValueError: pt_size = 5

            left_pkgs = [p for p in packages if p.get("axis", "L") == "L"]
            right_pkgs = [p for p in packages if p.get("axis", "L") == "R"]
            has_right_axis = len(right_pkgs) > 0

            x_shared = False
            y_shared = False

            if has_right_axis and left_pkgs:
                if left_pkgs[0].get("x_name", "X") == right_pkgs[0].get("x_name", "X"): x_shared = True
                if left_pkgs[0].get("y_name", "Y") == right_pkgs[0].get("y_name", "Y"): y_shared = True
                    
            main_vb = self.plot_widget.getViewBox()
            self.vb_right.setXLink(main_vb if x_shared else None)
            self.vb_right.setYLink(main_vb if y_shared else None)
            
            right_axis = self.plot_widget.getAxis('right')
            top_axis = self.plot_widget.getAxis('top')
            
            self.plot_widget.showAxis('right', show=True)
            self.plot_widget.showAxis('top', show=True)
            
            if has_right_axis:
                if x_shared:
                    top_axis.linkToView(main_vb)
                    top_axis.setStyle(showValues=True)
                    top_axis.setPen(pg.mkPen('k'))
                    top_axis.setTextPen(pg.mkPen('w')) 
                else:
                    top_axis.linkToView(self.vb_right)
                    top_axis.setStyle(showValues=True)
                    top_axis.setPen(pg.mkPen('k'))
                    top_axis.setTextPen(pg.mkPen('#d90000')) 
                
                if y_shared:
                    right_axis.linkToView(main_vb)
                    right_axis.setStyle(showValues=True)
                    right_axis.setPen(pg.mkPen('k'))
                    right_axis.setTextPen(pg.mkPen('w')) 
                else:
                    right_axis.linkToView(self.vb_right)
                    right_axis.setStyle(showValues=True)
                    right_axis.setPen(pg.mkPen('k'))
                    right_axis.setTextPen(pg.mkPen('#d90000')) 
                    
                right_axis.setGrid(0)
                top_axis.setGrid(0)
            else:
                right_axis.linkToView(main_vb)
                top_axis.linkToView(main_vb)
                right_axis.setStyle(showValues=True) 
                top_axis.setStyle(showValues=True)
                right_axis.setPen(pg.mkPen('k'))
                top_axis.setPen(pg.mkPen('k'))
                right_axis.setTextPen(pg.mkPen('w')) 
                top_axis.setTextPen(pg.mkPen('w'))
                right_axis.setGrid(0)
                top_axis.setGrid(0)

            if packages:
                if left_pkgs:
                    default_x_l = left_pkgs[0].get("x_name", "X Axis") if len(set([p.get("x_name") for p in left_pkgs])) == 1 else "Bottom X"
                    final_x_l = self.custom_axis_labels.get("bottom") or default_x_l
                    self.plot_widget.setLabel("bottom", final_x_l)
                    
                    default_y_l = left_pkgs[0].get("y_name", "Y Axis") if len(set([p.get("y_name") for p in left_pkgs])) == 1 else "Left Values"
                    final_y_l = self.custom_axis_labels.get("left") or default_y_l
                    self.plot_widget.setLabel("left", final_y_l)
                else:
                    self.plot_widget.setLabel("bottom", "")
                    self.plot_widget.setLabel("left", "")
                    
                if right_pkgs:
                    if not x_shared:
                        default_x_r = right_pkgs[0].get("x_name", "X Axis") if len(set([p.get("x_name") for p in right_pkgs])) == 1 else "Top X"
                        final_x_r = self.custom_axis_labels.get("top") or default_x_r
                        self.plot_widget.setLabel("top", final_x_r, color='#d90000')
                    else:
                        self.plot_widget.setLabel("top", "") 
                        
                    if not y_shared:
                        default_y_r = right_pkgs[0].get("y_name", "Y Axis") if len(set([p.get("y_name") for p in right_pkgs])) == 1 else "Right Values"
                        final_y_r = self.custom_axis_labels.get("right") or default_y_r
                        self.plot_widget.setLabel("right", final_y_r, color='#d90000')
                    else:
                        self.plot_widget.setLabel("right", "") 
                else:
                    self.plot_widget.setLabel("top", "")
                    self.plot_widget.setLabel("right", "")

            import matplotlib
            total_plotted_sw = len(set(p.get("sw", 0) for p in packages))
            
            graphtype = self.graphtype.currentText()
            curve_idx, scatter_idx, err_idx = 0, 0, 0
            num_active_pairs = len(self.series_data.get("2D", []))
            added_to_legend = set()
            
            for pkg in packages:
                i, sw, pair_idx = pkg["i"], pkg["sw"], pkg.get("pair_idx", 0)
                y_name = pkg.get("y_name", "Y")
                cmap_name = pkg.get("cmap_name", "Blues")
                cmap = matplotlib.colormaps.get_cmap(cmap_name)
                axis_side = pkg.get("axis", "L")
                
                intensity = 0.8 if total_plotted_sw <= 1 else 0.4 + 0.6 * (i / max(1, total_plotted_sw - 1))
                rgba = cmap(intensity)
                line_color = (int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255), 255)
                
                legend_name = f"[P{pair_idx+1}] {y_name}" if num_active_pairs > 1 else y_name
                if self.file_type == "BadgerLoop": 
                    legend_name += f" (Sweeps)" if total_plotted_sw > 15 else f" (Sw {sw})"
                if axis_side == "R":
                    legend_name += " [Top/Right]"
                
                target_vb = self.vb_right if axis_side == "R" else self.plot_widget
                
                if pkg["type"] == "average":
                    if scatter_idx >= len(self.scatter_pool):
                        s = pg.ScatterPlotItem(pxMode=True)
                        self.scatter_pool.append(s)
                        
                    scatter = self.scatter_pool[scatter_idx]
                    target_vb.addItem(scatter)
                    
                    scatter.setData(x=np.array([pkg["x_mean"]], dtype=np.float64), 
                                    y=np.array([pkg["y_mean"]], dtype=np.float64), 
                                    size=pt_size + 3, pen=pg.mkPen(None), brush=pg.mkBrush(line_color))
                    scatter.setVisible(True)
                    
                    avg_legend = legend_name + " Avg"
                    if show_legend and avg_legend not in added_to_legend:
                        self.legend.addItem(scatter, avg_legend)
                        added_to_legend.add(avg_legend)
                        
                    scatter_idx += 1
                    
                    if "dx" in pkg and "dy" in pkg:
                        if err_idx >= len(self.avg_error_pool):
                            eb = pg.ErrorBarItem()
                            self.avg_error_pool.append(eb)
                            
                        err_item = self.avg_error_pool[err_idx]
                        target_vb.addItem(err_item)
                        err_item.setData(x=np.array([pkg["x_mean"]]), y=np.array([pkg["y_mean"]]), 
                                         width=np.array([2*pkg["dx"]]), height=np.array([2*pkg["dy"]]), 
                                         pen=pg.mkPen(line_color, width=2))
                        err_item.setVisible(True)
                        err_idx += 1
                        
                elif pkg["type"] == "standard":
                    if graphtype in ["Line", "FFT (Spectrum)"]:
                        if curve_idx >= len(self.curve_pool):
                            c = pg.PlotCurveItem(skipFiniteCheck=True, autoDownsample=True)
                            self.curve_pool.append(c)
                            
                        curve = self.curve_pool[curve_idx]
                        target_vb.addItem(curve)
                        curve.setData(pkg["x"], pkg["y"], pen=pg.mkPen(line_color, width=2))
                        curve.setVisible(True)
                        
                        if show_legend:
                            if total_plotted_sw <= 15 or legend_name not in added_to_legend:
                                self.legend.addItem(curve, legend_name)
                                added_to_legend.add(legend_name)
                                
                        curve_idx += 1
                    else:
                        if scatter_idx >= len(self.scatter_pool):
                            s = pg.ScatterPlotItem(pxMode=True)
                            self.scatter_pool.append(s)
                            
                        scatter = self.scatter_pool[scatter_idx]
                        target_vb.addItem(scatter)
                        scatter.setData(x=pkg["x"], y=pkg["y"], size=pt_size, pen=pg.mkPen(None), brush=pg.mkBrush(line_color))
                        scatter.setVisible(True) 
                        
                        if show_legend:
                            if total_plotted_sw <= 15 or legend_name not in added_to_legend:
                                self.legend.addItem(scatter, legend_name)
                                added_to_legend.add(legend_name)
                                
                        scatter_idx += 1

            if hasattr(self, 'active_fits') and self.active_fits:
                for fit in self.active_fits:
                    if "x_raw" in fit and "y_raw" in fit:
                        x_raw, y_raw = fit["x_raw"], fit["y_raw"]
                        with np.errstate(divide='ignore', invalid='ignore'):
                            x_vis_new = np.log(x_raw) / np.log(xbase) if xlog else x_raw
                            y_vis_new = np.log(y_raw) / np.log(ybase) if ylog else y_raw
                            
                        valid = np.isfinite(x_vis_new) & np.isfinite(y_vis_new)
                        if xlog: valid &= (x_raw > 0)
                        if ylog: valid &= (y_raw > 0)
                        
                        self.plot_widget.addItem(fit["plot_item"]) 
                        fit["plot_item"].setData(x_vis_new[valid], y_vis_new[valid])
                    
                    self.fit_legend.addItem(fit["plot_item"], fit["name"])
                
                if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(True)
                if hasattr(self, 'save_function_btn'): self.save_function_btn.setVisible(True)
                if hasattr(self, 'clear_fit_btn'): self.clear_fit_btn.setVisible(True)
                if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
                
            self._apply_axis_fonts()
            self.plot_widget.getViewBox().autoRange()
            self.vb_right.autoRange()
            
        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the 2D plot.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False

    def _draw_3d(self, all_pts_raw, bounds):
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            if not OPENGL_AVAILABLE: return
            self.gl_widget.clear() 
            self.gl_widget.setBackgroundColor('k')
            if not all_pts_raw: return
            self.last_plotted_data = {'mode': '3D', 'data': all_pts_raw}
                
            mins, maxs = bounds
            spans = maxs - mins
            spans[spans == 0] = 1.0 
            scale_factors = 10.0 / spans
            
            import matplotlib
            
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
                
                cmap = matplotlib.colormaps.get_cmap(self.heatmap_cmap.currentText())
                z_norm = (z_2d - mins[2]) / spans[2] 
                
                colors = cmap(z_norm).astype(np.float32) 
                colors_flat = colors.reshape(-1, 4) 
                
                surface_item = gl.GLSurfacePlotItem(
                    x=x_scaled, y=y_scaled, z=z_scaled, 
                    colors=colors_flat, smooth=False, computeNormals=False
                )
                self.gl_widget.addItem(surface_item)

            else:
                cmap = matplotlib.colormaps.get_cmap('jet') 
                num_sweeps_plotted = len(all_pts_raw)
                
                for idx, (i, sw, pts) in enumerate(all_pts_raw):
                    norm_pts = np.zeros_like(pts, dtype=np.float32)
                    norm_pts[:, 0] = (pts[:, 0] - mins[0]) * scale_factors[0]
                    norm_pts[:, 1] = (pts[:, 1] - mins[1]) * scale_factors[1]
                    norm_pts[:, 2] = (pts[:, 2] - mins[2]) * scale_factors[2]
                    norm_pts = np.ascontiguousarray(norm_pts)
                    
                    rgba = cmap(idx / max(1, num_sweeps_plotted - 1)) 
                    c_tuple = (float(rgba[0]), float(rgba[1]), float(rgba[2]), 1.0)
                    
                    if self.graphtype.currentText() == "Line":
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
                        
                    self.gl_widget.addItem(item)
        
            self.gl_widget.opts['center'] = pg.Vector(5, 5, 5)
            self.gl_widget.setCameraPosition(distance=25, elevation=25, azimuth=45)
            self._init_3d_scene(bounds)
            
        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the 3D plot.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False

    def _draw_heatmap(self, res_dict):
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            if not res_dict: return
                
            dummy_arr = np.array([0.0], dtype=np.float32)
            for c in self.curve_pool: 
                c.setData(x=dummy_arr, y=dummy_arr)
                c.setVisible(False)
            for s in self.scatter_pool: 
                s.setData(x=dummy_arr, y=dummy_arr)
                s.setVisible(False)
            for eb in self.errorbar_pool: 
                eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
            for ac in self.avg_error_pool: 
                ac.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                ac.setVisible(False)
    
            self.legend.hide()
            self.heatmap_item.setVisible(True) 
            self.heatmap_image_item.setVisible(True)
            
            pair = self.series_data[self.plot_mode][0] if self.series_data.get(self.plot_mode) else {}
            self.plot_widget.setLabel("bottom", pair.get("x_name", "X"))
            self.plot_widget.setLabel("left", pair.get("y_name", "Y"))
            
            xlog, ylog, zlog = self.xscale.currentText() == "Log", self.yscale.currentText() == "Log", self.zscale.currentText() == "Log"
            xbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.xbase.text())
            ybase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.ybase.text())
            zbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.zbase.text())
            
            self.plot_widget.getAxis('bottom').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('top').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('left').set_custom_log(ylog, ybase)
            self.plot_widget.getAxis('right').set_custom_log(ylog, ybase)
            
            self.heatmap_item.axis.setLabel(res_dict.get("z_axis_name", "Z"), color='k')
            self.heatmap_item.axis.set_custom_log(zlog, zbase)
            self._apply_axis_fonts()
            
            img_data = res_dict["img_data"]
            x_min, x_max = res_dict["x_min"], res_dict["x_max"]
            y_min, y_max = res_dict["y_min"], res_dict["y_max"]
            z_min, z_max = res_dict["z_min"], res_dict["z_max"]
            
            self.heatmap_image_item.setImage(img_data)
            try: self.heatmap_item.gradient.setColorMap(pg.colormap.get(self.heatmap_cmap.currentText(), source='matplotlib'))
            except: self.heatmap_item.gradient.loadPreset('viridis')
            
            rect_w = x_max - x_min if x_max > x_min else 1.0
            rect_h = y_max - y_min if y_max > y_min else 1.0
            self.heatmap_image_item.setRect(pg.QtCore.QRectF(x_min, y_min, rect_w, rect_h))
            
            self.heatmap_item.setLevels(z_min, z_max)
            self.plot_widget.autoRange(padding=0)
            self.plot_widget.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)
            self.plot_widget.getViewBox().setRange(xRange=[x_min, x_max], yRange=[y_min, y_max], padding=0)
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the Heatmap.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False
            
    def save_plot(self):
        # Limit export formats for 3D since OpenGL renders as a pixel buffer (no SVG support)
        if self.plot_mode == "3D":
            file_filter = "PNG (*.png);;JPEG (*.jpg)"
        else:
            file_filter = "PNG (*.png);;JPEG (*.jpg);;SVG (*.svg)"

        fname, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "", file_filter
        )
        if not fname:
            return

        # Apply default extension if the user didn't type one
        if not os.path.splitext(fname)[1]:
            fname += ".png"

        # ==========================================
        # 3D SAVE LOGIC
        # ==========================================
        if self.plot_mode == "3D":
            # Grab the current frame buffer from the OpenGL widget
            img = self.gl_widget.readQImage()
            img.save(fname)
            return

        # ==========================================
        # 2D / HEATMAP SAVE LOGIC
        # ==========================================
        # Hide the interactive scaler temporarily if we're in Heatmap mode
        if self.plot_mode == "Heatmap":
            self.heatmap_item.vb.hide()
            QApplication.processEvents() # Force UI to update before exporting

        exporter = (
            pgexp.SVGExporter(self.plot_widget.plotItem)
            if fname.lower().endswith(".svg")
            else pgexp.ImageExporter(self.plot_widget.plotItem)
        )
        exporter.export(fname)

        # Restore the interactive scaler
        if self.plot_mode == "Heatmap":
            self.heatmap_item.vb.show()
            
    def export_plotted_data(self):
        if not getattr(self, 'last_plotted_data', None):
            QMessageBox.warning(self, "No Data", "No plot data available to export.\nPlease draw a plot first.")
            return

        fname, _ = QFileDialog.getSaveFileName(self, "Export Plotted Data to CSV", "", "CSV files (*.csv)", options=QFileDialog.DontConfirmOverwrite)
        if not fname: return
        if not fname.lower().endswith('.csv'): fname += '.csv'

        append_mode = False
        if os.path.exists(fname):
            msg = QMessageBox(self)
            msg.setWindowTitle("File Exists")
            msg.setText("This file already exists.\n\nWould you like to Append the new columns to it, or Overwrite it entirely?")
            btn_append = msg.addButton("Append", QMessageBox.AcceptRole)
            btn_overwrite = msg.addButton("Overwrite", QMessageBox.DestructiveRole)
            btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec()
            
            if msg.clickedButton() == btn_cancel: return
            append_mode = (msg.clickedButton() == btn_append)

        new_cols = {}
        def add_to_cols(name, data_list):
            data_arr = np.array(data_list, dtype=np.float64)
            col_name = name
            if col_name in new_cols:
                existing = np.array(new_cols[col_name], dtype=np.float64)
                if len(existing) == len(data_arr):
                    try:
                        if np.allclose(existing, data_arr, equal_nan=True): return
                    except Exception: pass
                base = col_name
                counter = 1
                while col_name in new_cols:
                    col_name = f"{base} [{counter}]"
                    counter += 1
            new_cols[col_name] = data_arr.tolist()

        data = self.last_plotted_data
        
        if data['mode'] == '2D':
            is_average = any(pkg['type'] == 'average' for pkg in data['packages'])
            pairs = {}
            for pkg in data['packages']:
                pidx = pkg.get('pair_idx', 0)
                if pidx not in pairs: pairs[pidx] = []
                pairs[pidx].append(pkg)
                
            for pidx, pkgs in pairs.items():
                x_name = pkgs[0].get('x_name', 'X')
                y_name = pkgs[0].get('y_name', 'Y')
                
                agg_x, agg_y, agg_xstd, agg_ystd = [], [], [], []
                for pkg in pkgs:
                    if pkg['type'] == 'standard':
                        agg_x.extend(pkg['x'])
                        agg_y.extend(pkg['y'])
                    elif pkg['type'] == 'average':
                        agg_x.append(pkg['x_mean'])
                        agg_y.append(pkg['y_mean'])
                        agg_xstd.append(pkg.get('x_std', 0.0))
                        agg_ystd.append(pkg.get('y_std', 0.0))
                        
                if is_average:
                    add_to_cols(f"{x_name} (Avg)", agg_x)
                    add_to_cols(f"{y_name} (Avg)", agg_y)
                    add_to_cols(f"{x_name} (Std)", agg_xstd)
                    add_to_cols(f"{y_name} (Std)", agg_ystd)
                else:
                    add_to_cols(x_name, agg_x)
                    add_to_cols(y_name, agg_y)
                    
        elif data['mode'] == '3D':
            pair = self.series_data["3D"][0]
            x_name = pair.get('x_name', 'X')
            y_name = pair.get('y_name', 'Y')
            z_name = pair.get('z_name', 'Z')
            
            agg_x, agg_y, agg_z = [], [], []
            for i, sw, pts in data['data']:
                if isinstance(pts, dict) and 'SURFACE' in str(data['data'][0][0]):
                    grid_x, grid_y = np.meshgrid(pts['x_1d'], pts['y_1d'], indexing='ij')
                    agg_x.extend(grid_x.flatten())
                    agg_y.extend(grid_y.flatten())
                    agg_z.extend(pts['z_2d'].flatten())
                else:
                    agg_x.extend(pts[:,0])
                    agg_y.extend(pts[:,1])
                    agg_z.extend(pts[:,2])
                    
            add_to_cols(x_name, agg_x)
            add_to_cols(y_name, agg_y)
            add_to_cols(z_name, agg_z)

        existing_cols = {}
        if append_mode:
            import csv
            try:
                with open(fname, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    headers = next(reader, [])
                    cols_data = {h: [] for h in headers}
                    for row in reader:
                        for i, h in enumerate(headers):
                            val = row[i] if i < len(row) else ''
                            try: cols_data[h].append(float(val) if val.strip() else np.nan)
                            except: cols_data[h].append(np.nan)
                    existing_cols = cols_data
            except Exception: pass

        final_cols = dict(existing_cols)
        for k, v in new_cols.items():
            new_k = k
            counter = 1
            while new_k in final_cols:
                new_k = f"{k} [{counter}]"
                counter += 1
            final_cols[new_k] = v

        max_len = max([len(v) for v in final_cols.values()] + [0])
        import csv
        try:
            with open(fname, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = list(final_cols.keys())
                writer.writerow(headers)
                
                for i in range(max_len):
                    row = []
                    for h in headers:
                        col_data = final_cols[h]
                        if i < len(col_data):
                            val = col_data[i]
                            if isinstance(val, (float, np.floating)) and np.isnan(val):
                                row.append("")
                            else:
                                row.append(f"{val:.6g}")
                        else:
                            row.append("")
                    writer.writerow(row)
                    
            QMessageBox.information(self, "Export Complete", "Data successfully exported to CSV!")
        except PermissionError:
            QMessageBox.critical(self, "Export Failed", "Permission denied.\nPlease close the CSV file if it is open in Excel and try again.")
