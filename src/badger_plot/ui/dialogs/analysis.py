# ui/dialogs/analysis.py
import os
import numpy as np
import scipy.signal as sig
import scipy.integrate as intg
import re
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QLabel, QPushButton, QSpinBox, QTableWidget, QHeaderView,
    QAbstractItemView, QGroupBox, QButtonGroup, QMessageBox, QApplication,
    QProgressDialog, QListWidget, QListWidgetItem, QTabWidget, QScrollArea,
    QTextEdit, QWidget, QRadioButton
)
from badger_plot.core.constants import PHYSICS_CONSTANTS, GREEK_MAP
from core.data_loader import DataLoaderThread
from core.theme import theme

class AreaUnderCurveDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Area Under Curve Integration")
        self.setMinimumWidth(350)
        layout = QVBoxLayout(self)

        # --- STEP 1: SELECTION TOOLS ---
        layout.addWidget(QLabel("<b>1. Select Data to Integrate:</b>"))
        sel_layout = QHBoxLayout()
        
        self.btn_box = QPushButton("⬛ Draw Box")
        self.btn_box.clicked.connect(self._activate_box)
        
        self.btn_line = QPushButton("📏 Draw Line")
        self.btn_line.clicked.connect(self._activate_line)
        
        sel_layout.addWidget(self.btn_box)
        sel_layout.addWidget(self.btn_line)
        layout.addLayout(sel_layout)

        self.lbl_points = QLabel("Selected points: 0")
        self.lbl_points.setStyleSheet(f"color: {theme.danger_text}; font-weight: bold;")
        layout.addWidget(self.lbl_points)

        # --- STEP 2: BASELINE OPTIONS ---
        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>2. Select Baseline Method:</b><br>How should the bottom of the peak be bounded?"))

        self.btn_endpoints = QRadioButton("Connect Endpoints (Local Slant)")
        self.btn_min = QRadioButton("Minimum Y-Value in Selection (Flat)")
        self.btn_zero = QRadioButton("Absolute Zero (y = 0)")
        self.btn_endpoints.setChecked(True) 

        self.bg = QButtonGroup()
        self.bg.addButton(self.btn_endpoints, 0)
        self.bg.addButton(self.btn_min, 1)
        self.bg.addButton(self.btn_zero, 2)

        layout.addWidget(self.btn_endpoints)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_zero)
        
        layout.addSpacing(10)

        # --- STEP 3: ACTION BUTTONS ---
        btn_box_layout = QHBoxLayout()
        self.ok_btn = QPushButton("Calculate Area")
        self.ok_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        self.ok_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_box_layout.addStretch()
        btn_box_layout.addWidget(cancel_btn)
        btn_box_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_box_layout)
        
        self.update_points_label()

    def update_points_label(self):
        count = len(getattr(self.main_window, 'selected_indices', set()))
        self.lbl_points.setText(f"Selected points: {count}")
        color = theme.success_text if count > 2 else theme.danger_text
        self.lbl_points.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.ok_btn.setEnabled(count > 2)

    def _activate_box(self):
        self.hide() # Auto-hide palette
        self.main_window.btn_box.setChecked(True)
        self.main_window._set_interaction_mode(self.main_window.btn_box)
        
        # Hand the main window our callback function
        self.main_window._on_selection_finished_cb = self._finish_selection


    def _activate_line(self):
        self.hide() # Auto-hide palette
        self.main_window._activate_auc_line_tool(self)

    def _finish_selection(self):
        self.update_points_label()
        self.show()
        self.raise_()

    def get_result(self):
        idx = self.bg.checkedId()
        if idx == 0: return "endpoints"
        if idx == 1: return "min"
        if idx == 2: return "zero"

class LoopAreaDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Enclosed Loop Area Calculator")
        self.setMinimumSize(450, 500)
        
        # Grab the current plotted data
        res = main_window._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0:
            raise ValueError("No valid 2D data to analyze.")
            
        self.x, self.y, _, self.pair = res
        self.detected_loops = [] # Store dictionaries of loop data
        
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        info = QLabel("<b>Calculate Area of Enclosed Loops</b><br>"
                      "Finds the area inside a parametric loop (e.g. Hysteresis, P-V Diagrams).")
        layout.addWidget(info)
        
        btn_layout = QHBoxLayout()
        self.btn_auto = QPushButton("🔍 Auto-Detect Loops")
        self.btn_auto.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; color: {theme.primary_text};")
        self.btn_auto.clicked.connect(self._auto_detect)
        
        self.btn_manual = QPushButton("🎯 Capture Lasso/Box Selection")
        self.btn_manual.clicked.connect(self._capture_manual)
        
        self.btn_entire = QPushButton("🔄 Treat Entire Plot as 1 Loop")
        self.btn_entire.clicked.connect(self._capture_entire)
        
        btn_layout.addWidget(self.btn_auto)
        btn_layout.addWidget(self.btn_manual)
        layout.addLayout(btn_layout)
        layout.addWidget(self.btn_entire)
        
        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Detected Loops:</b> (Check boxes to include in final sum)"))
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_widget.itemChanged.connect(self._on_item_checked)
        self.list_widget.itemSelectionChanged.connect(self._preview_selected)
        layout.addWidget(self.list_widget)
        
        self.btn_clear = QPushButton("Clear List")
        self.btn_clear.clicked.connect(self._clear_list)
        layout.addWidget(self.btn_clear)
        
        buttons = QHBoxLayout()
        ok_btn = QPushButton("Apply & View Results")
        ok_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text};")
        cancel_btn = QPushButton("Cancel")
        
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        buttons.addStretch()
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

    def _calc_shoelace(self, x_arr, y_arr):
        """ Calculates the exact area of a polygon. Positive = CCW, Negative = CW. """
        if len(x_arr) < 3: return 0.0
        # Ensure the loop is closed mathematically
        x_cl = np.append(x_arr, x_arr[0])
        y_cl = np.append(y_arr, y_arr[0])
        area = 0.5 * np.sum(x_cl[:-1] * y_cl[1:] - x_cl[1:] * y_cl[:-1])
        return area

    def _add_loop_to_list(self, indices, name):
        if len(indices) < 3: return
        idx_arr = np.array(indices)
        x_loop = self.x[idx_arr]
        y_loop = self.y[idx_arr]
        
        area = self._calc_shoelace(x_loop, y_loop)
        
        loop_data = {
            "name": name,
            "indices": indices,
            "x": x_loop, "y": y_loop,
            "area": area,
            "abs_area": abs(area)
        }
        self.detected_loops.append(loop_data)
        
        # Determine rotation direction for the UI label
        direction = "CCW (+)" if area >= 0 else "CW (-)"
        
        item = QListWidgetItem(f"{name} | Area: {abs(area):.4g} [{direction}]")
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        item.setData(Qt.ItemDataRole.UserRole, len(self.detected_loops) - 1)
        self.list_widget.addItem(item)
        self._preview_selected()

    def _auto_detect(self):
        try:
            from scipy.spatial import cKDTree
        except ImportError:
            QMessageBox.warning(self, "Missing Library", "SciPy is required for auto-detection.")
            return
            
        points = np.column_stack((self.x, self.y))
        
        x_range = np.ptp(self.x)
        y_range = np.ptp(self.y)
        r = max(x_range, y_range) * 0.015 
        if r == 0: return
        
        tree = cKDTree(points)
        pairs = tree.query_pairs(r=r)
        
        used_indices = set()
        sorted_pairs = sorted(pairs, key=lambda p: p[1] - p[0], reverse=False)
        
        # --- NEW: Calculate the maximum possible area of the plot ---
        total_box_area = x_range * y_range
        
        count = 1
        for i, j in sorted_pairs:
            if j - i > 15: 
                loop_set = set(range(i, j+1))
                if len(loop_set.intersection(used_indices)) < len(loop_set) * 0.1:
                    
                    # --- NEW: Reject microscopic jitter/noise loops ---
                    test_x, test_y = self.x[list(loop_set)], self.y[list(loop_set)]
                    area = abs(self._calc_shoelace(test_x, test_y))
                    
                    if area > (total_box_area * 0.001): # Must be > 0.1% of the plot size
                        used_indices.update(loop_set)
                        self._add_loop_to_list(list(range(i, j+1)), f"Auto-Loop {count}")
                        count += 1
                        
        if count == 1:
            QMessageBox.information(self, "No Loops", "Could not automatically isolate any distinct loops. Try using the Manual Capture tools.")

    def _capture_manual(self):
        sel_indices = getattr(self.main_window, 'selected_indices', set())
        if not sel_indices:
            QMessageBox.warning(self, "No Selection", "Please draw a box or lasso around a loop on the main plot first.")
            return
            
        valid_indices = sorted([i for i in sel_indices if i < len(self.x)])
        if len(valid_indices) < 3: return
        
        count = sum("Manual" in d["name"] for d in self.detected_loops) + 1
        self._add_loop_to_list(valid_indices, f"Manual Loop {count}")
        self.main_window.clear_selection()

    def _capture_entire(self):
        try:
            from scipy.spatial import cKDTree
            points = np.column_stack((self.x, self.y))
            x_range, y_range = np.ptp(self.x), np.ptp(self.y)
            r = max(x_range, y_range) * 0.01 # 1% proximity radius
            
            if r > 0:
                tree = cKDTree(points)
                pairs = tree.query_pairs(r=r)
                
                n_pts = len(self.x)
                has_crossings = False
                
                for i, j in pairs:
                    # Check if the points are far apart in time
                    if abs(i - j) > 20:
                        # Ignore the loop closing naturally at the start and end
                        if min(i, j) < 20 and max(i, j) > n_pts - 20:
                            continue
                        
                        # An intersection in the middle of the dataset was found!
                        has_crossings = True
                        break
                        
                if has_crossings:
                    ans = QMessageBox.warning(
                        self, 
                        "Self-Intersection Detected", 
                        "It looks like this curve crosses over itself.\n\n"
                        "Because the Shoelace formula treats Counter-Clockwise area as Positive and Clockwise area as Negative, treating this entire plot as one continuous loop will compute the Net Area (opposing lobes will cancel each other out).\n\n"
                        "If you want the Absolute Total Area, use the 'Auto-Detect Loops' tool instead to split it into separate polygons.\n\n"
                        "Do you still want to treat this as 1 continuous loop?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if ans == QMessageBox.StandardButton.No:
                        return
                        
        except ImportError:
            pass # Silently skip the check if SciPy isn't loaded
            
        self._add_loop_to_list(list(range(len(self.x))), "Entire Plot Sequence")

    def _clear_list(self):
        self.list_widget.clear()
        self.detected_loops.clear()
        self._preview_selected()

    def _on_item_checked(self, item):
        self._preview_selected()

    def _preview_selected(self):
        # Gather all checked loops, and highlight currently clicked ones in the list
        checked_loops = []
        highlighted_loops = []
        
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            loop_idx = item.data(Qt.ItemDataRole.UserRole)
            loop = self.detected_loops[loop_idx]
            
            if item.checkState() == Qt.CheckState.Checked:
                checked_loops.append(loop)
            if item.isSelected():
                highlighted_loops.append(loop)
                
        # Send them to the main window to be drawn as phantom polygons
        if hasattr(self.main_window, '_draw_temp_loops'):
            self.main_window._draw_temp_loops(checked_loops, highlighted_loops)

    def get_selected_loops(self):
        checked_loops = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                checked_loops.append(self.detected_loops[item.data(Qt.ItemDataRole.UserRole)])
        return checked_loops

    def closeEvent(self, event):
        if hasattr(self.main_window, '_clear_temp_loops'):
            self.main_window._clear_temp_loops()
        super().closeEvent(event)

class SignalProcessingDialog(QDialog):
    preview_updated = pyqtSignal(object, object)
    
    def __init__(self, x_full, y_full, sel_idx, col_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Signal Processing")
        self.resize(450, 400)
        
        self.x_full = x_full
        self.y_full = y_full
        self.sel_idx = sel_idx
        self.base_name = col_name
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.new_name_edit = QLineEdit(f"{col_name}_Processed")
        form.addRow("<b>New Column Name:</b>", self.new_name_edit)
        
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Savitzky-Golay (Smooth)", "Moving Average (Smooth)", 
            "Median Filter (Despike)", "First Derivative (dy/dx)", 
            "Cumulative Integral (∫y dx)"
        ])
        form.addRow("<b>Method:</b>", self.method_combo)
        
        self.mask_checkbox = QCheckBox(f"Apply only to Selected Points ({len(sel_idx)} pts)")
        self.mask_checkbox.setChecked(bool(sel_idx))
        self.mask_checkbox.setEnabled(bool(sel_idx))
        form.addRow("", self.mask_checkbox)
        
        layout.addLayout(form)
        layout.addWidget(QLabel("<hr>"))
        
        self.param_layout = QFormLayout()
        
        self.window_lbl = QLabel("<b>Window Size:</b>")
        self.window_spin = QSpinBox()
        max_win = len(x_full) if len(x_full) % 2 != 0 else len(x_full) - 1
        self.window_spin.setRange(3, max(3, max_win))
        self.window_spin.setSingleStep(2)
        self.window_spin.setValue(11)
        self.param_layout.addRow(self.window_lbl, self.window_spin)
        
        self.poly_lbl = QLabel("<b>Polynomial Order:</b>")
        self.poly_spin = QSpinBox()
        self.poly_spin.setRange(1, 9)
        self.poly_spin.setValue(2)
        self.param_layout.addRow(self.poly_lbl, self.poly_spin)
        
        layout.addLayout(self.param_layout)
        layout.addStretch()
        
        btn_box = QHBoxLayout()
        self.save_btn = QPushButton("Save as New Column")
        self.save_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.save_btn)
        layout.addLayout(btn_box)
        
        self.method_combo.currentTextChanged.connect(self.update_ui)
        self.mask_checkbox.stateChanged.connect(self.calculate_preview)
        self.window_spin.valueChanged.connect(self.on_slider_change) 
        self.poly_spin.valueChanged.connect(self.on_slider_change)
        self.save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        self.update_ui()
        
    def accept(self):
        new_name = self.new_name_edit.text().strip()
        existing_names = list(self.parent().dataset.column_names.values())
        if new_name in existing_names:
            QMessageBox.warning(self, "Duplicate Name", f"The column '{new_name}' already exists.\nPlease choose a unique name.")
            return
        super().accept()

    def update_ui(self):
        method = self.method_combo.currentText()
        is_smoothing = "Smooth" in method or "Despike" in method
        is_savgol = "Savitzky" in method
        
        if not is_smoothing:
            self.mask_checkbox.setChecked(False)
            self.mask_checkbox.setEnabled(False)
            self.mask_checkbox.setText("Regional Mask Disabled (Global Math Only)")
        else:
            self.mask_checkbox.setEnabled(bool(self.sel_idx))
            self.mask_checkbox.setText(f"Apply only to Selected Points ({len(self.sel_idx)} pts)")
            
        self.window_spin.setVisible(is_smoothing)
        self.window_lbl.setVisible(is_smoothing)
        self.poly_spin.setVisible(is_savgol)
        self.poly_lbl.setVisible(is_savgol)
        
        names = {
            "Savitzky-Golay (Smooth)": f"{self.base_name}_SG",
            "Moving Average (Smooth)": f"{self.base_name}_MA",
            "Median Filter (Despike)": f"{self.base_name}_Med",
            "First Derivative (dy/dx)": f"d({self.base_name})/dx",
            "Cumulative Integral (∫y dx)": f"Int({self.base_name})"
        }
        self.new_name_edit.setText(names.get(method, f"{self.base_name}_Proc"))
        self.calculate_preview()

    def on_slider_change(self):
        win = self.window_spin.value()
        if win % 2 == 0: 
            win += 1
            self.window_spin.blockSignals(True)
            self.window_spin.setValue(win)
            self.window_spin.blockSignals(False)
            
        poly = self.poly_spin.value()
        if poly >= win:
            poly = win - 1
            self.poly_spin.blockSignals(True)
            self.poly_spin.setValue(poly)
            self.poly_spin.blockSignals(False)
            
        self.calculate_preview()

    def calculate_preview(self):
        method = self.method_combo.currentText()
        win = self.window_spin.value()
        poly = self.poly_spin.value()
        use_mask = self.mask_checkbox.isChecked() and self.sel_idx
        
        try:
            with np.errstate(all='ignore'):
                if "Savitzky" in method:
                    y_calc = sig.savgol_filter(self.y_full, win, poly)
                elif "Moving Average" in method:
                    box = np.ones(win)/win
                    y_calc = np.convolve(self.y_full, box, mode='same')
                elif "Median" in method:
                    y_calc = sig.medfilt(self.y_full, kernel_size=win)
                elif "Derivative" in method:
                    if len(self.x_full) < 2:
                        y_calc = np.zeros_like(self.y_full)
                    else:
                        dy = np.gradient(self.y_full)
                        dx = np.gradient(self.x_full)
                        if np.all(dx == 0):
                            y_calc = np.zeros_like(self.y_full)
                        else:
                            dx[np.abs(dx) < 1e-10] = 1e-10 * np.sign(dx[np.abs(dx) < 1e-10] + 1e-15)
                            y_calc = dy / dx
                            y_calc = np.nan_to_num(y_calc, nan=0.0, posinf=1e6, neginf=-1e6)
                            y_calc = np.clip(y_calc, -1e6, 1e6)
                elif "Integral" in method:
                    y_calc = intg.cumulative_trapezoid(self.y_full, x=self.x_full, initial=0)
                    y_calc = np.nan_to_num(y_calc, nan=0.0) 
                else:
                    y_calc = self.y_full.copy()
                
            if use_mask:
                y_preview = self.y_full.copy()
                y_preview[self.sel_idx] = y_calc[self.sel_idx]
            else:
                y_preview = y_calc
                
            self.preview_updated.emit(self.x_full, y_preview)
            
        except Exception as e:
            print(f"Math preview suppressed a transient error: {e}")

    def get_result(self):
        return {
            "name": self.new_name_edit.text(),
            "method": self.method_combo.currentText(),
            "win": self.window_spin.value(),
            "poly": self.poly_spin.value(),
            "use_mask": self.mask_checkbox.isChecked(),
            "sel_idx": self.sel_idx
        }

class PhaseSpaceDialog(QDialog):
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Generate Phase Space Plot")
        self.resize(400, 200)
        self.dataset = dataset

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.state_combo = QComboBox()
        self.time_combo = QComboBox()
        self.time_combo.addItem("None (Use Point Index)", -1)

        for i, name in dataset.column_names.items():
            self.state_combo.addItem(f"{i}: {name}", i)
            self.time_combo.addItem(f"{i}: {name}", i)

        form.addRow("State Variable (x):", self.state_combo)
        form.addRow("Time Variable (t):", self.time_combo)

        self.new_name_edit = QLineEdit()
        form.addRow("Velocity Name (dx/dt):", self.new_name_edit)

        layout.addLayout(form)

        self.state_combo.currentTextChanged.connect(self.update_name)
        self.time_combo.currentTextChanged.connect(self.update_name)
        self.update_name()

        btn_box = QHBoxLayout()
        self.calc_btn = QPushButton("Generate & Plot")
        self.calc_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.calc_btn)
        layout.addLayout(btn_box)

        self.calc_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def accept(self):
        new_name = self.new_name_edit.text().strip()
        existing_names = list(self.dataset.column_names.values())
        if new_name in existing_names:
            QMessageBox.warning(self, "Duplicate Name", f"The column '{new_name}' already exists.\nPlease choose a unique name.")
            return
        super().accept()

    def update_name(self):
        x_name = self.state_combo.currentText().split(": ")[-1]
        t_name = self.time_combo.currentText().split(": ")[-1]
        if "None" in t_name:
            self.new_name_edit.setText(f"Velocity of {x_name}")
        else:
            self.new_name_edit.setText(f"d({x_name})/d({t_name})")

    def get_result(self):
        return (
            self.state_combo.currentData(),
            self.time_combo.currentData(),
            self.new_name_edit.text().strip()
        )

class PeakFinderTool(QDialog):
    def __init__(self, parent_gui):
        super().__init__(parent_gui)
        self.parent_gui = parent_gui
        self.setWindowTitle("Analysis: Peak Finder & iFFT Surgeon")
        self.resize(700, 720)
        self.setModal(False) 

        layout = QVBoxLayout(self)
        
        self.fft_toggle_btn = QPushButton("∿ Toggle FFT Mode")
        self.fft_toggle_btn.setCheckable(True)
        self.fft_toggle_btn.setChecked(getattr(self.parent_gui, 'fft_mode_active', False))
        self.fft_toggle_btn.clicked.connect(self.toggle_fft_mode)
        self.fft_toggle_btn.setStyleSheet(self._get_toggle_style(self.fft_toggle_btn.isChecked()))
        
        font = self.fft_toggle_btn.font()
        font.setPointSize(12); font.setBold(True)
        self.fft_toggle_btn.setFont(font)
        layout.addWidget(self.fft_toggle_btn)
        
        form = QFormLayout()
        self.prom_edit = QLineEdit("Auto")
        self.prom_edit.setToolTip("Type 'Auto' to use 5% of the data's total range.")
        form.addRow("<b>Prominence (Height):</b>", self.prom_edit)
        
        self.dist_edit = QLineEdit("1")
        form.addRow("<b>Min Distance (Points):</b>", self.dist_edit)
        
        self.width_mode_combo = QComboBox()
        self.width_mode_combo.addItems([
            "Full-Width Half-Max (FWHM)", 
            "Full-Width Quarter-Max (FWQM)", 
            "Custom Absolute Offset"
        ])
        form.addRow("<b>Width Mode:</b>", self.width_mode_combo)
        
        self.custom_offset_edit = QLineEdit("-3.0")
        self.custom_offset_edit.setToolTip("Must be a negative number.")
        self.custom_offset_edit.setVisible(False)
        form.addRow("<b>Custom Offset:</b>", self.custom_offset_edit)
        
        self.width_mode_combo.currentTextChanged.connect(self._toggle_width_mode)
        layout.addLayout(form)
        
        btn_layout = QHBoxLayout()
        self.find_btn = QPushButton("🔍 Find Peaks")
        self.find_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        self.find_btn.clicked.connect(self.run_peak_finder)
        
        self.clear_btn = QPushButton("✖ Clear Markers")
        self.clear_btn.clicked.connect(self.parent_gui.clear_peak_markers)
        
        btn_layout.addWidget(self.find_btn)
        btn_layout.addWidget(self.clear_btn)
        layout.addLayout(btn_layout)
        
        layout.addWidget(QLabel("<b>Detected Peaks:</b>"))
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Peak #", "X (Center)", "Y (Height)", "Width", "Smart Diagnosis"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        
        self.peak_data_memory = []
        
        self.fft_group = QGroupBox("✂ Interactive iFFT Surgeon")
        self.fft_group.setStyleSheet(f"QGroupBox {{ font-weight: bold; border: 2px solid {theme.danger_text}; border-radius: 6px; margin-top: 10px; padding-top: 15px; }} QGroupBox::title {{ color: {theme.danger_text}; left: 10px; }}")
        fft_layout = QVBoxLayout()
        noise_layout = QHBoxLayout()
        
        flag_layout = QFormLayout()
        self.noise_flag_edit = QLineEdit("50, 60")
        self.noise_flag_edit.setPlaceholderText("e.g. 50, 60, 120")
        flag_layout.addRow("Flag Known Noise (Hz):", self.noise_flag_edit)
        noise_layout.addLayout(flag_layout)
        
        manual_group = QGroupBox("Manual Selection")
        manual_h = QHBoxLayout()
        self.btn_pan = QPushButton("✋ Pan")
        self.btn_box = QPushButton("⬛ Box")
        self.btn_lasso = QPushButton("➰ Lasso")
        
        for b in [self.btn_pan, self.btn_box, self.btn_lasso]:
            b.setCheckable(True)
            
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_pan)
        self.mode_group.addButton(self.btn_box)
        self.mode_group.addButton(self.btn_lasso)
        
        if hasattr(self.parent_gui, 'btn_box') and self.parent_gui.btn_box.isChecked(): self.btn_box.setChecked(True)
        elif hasattr(self.parent_gui, 'btn_lasso') and self.parent_gui.btn_lasso.isChecked(): self.btn_lasso.setChecked(True)
        else: self.btn_pan.setChecked(True)
        self._update_interaction_styles()
        
        self.mode_group.buttonClicked.connect(self._sync_interaction_mode)
        manual_h.addWidget(self.btn_pan)
        manual_h.addWidget(self.btn_box)
        manual_h.addWidget(self.btn_lasso)
        manual_group.setLayout(manual_h)
        noise_layout.addWidget(manual_group)
        
        fft_layout.addLayout(noise_layout)
        fft_layout.addWidget(QLabel("<i>Target noise by highlighting table rows OR drawing a yellow box over the spike.</i>"))
        
        self.selection_label = QLabel("<b>Targeted for removal:</b> None")
        self.selection_label.setStyleSheet(f"color: {theme.danger_text}; font-size: 13px; padding: 4px; border: 1px dashed {theme.danger_border}; background-color: {theme.danger_bg};")
        self.selection_label.setWordWrap(True)
        fft_layout.addWidget(self.selection_label)
        
        self.selection_timer = QTimer(self)
        self.selection_timer.timeout.connect(self.update_selection_display)
        self.selection_timer.start(200) 
        
        row_h = QHBoxLayout()
        row_h.addWidget(QLabel("<b>New Column Name:</b>"))
        self.ifft_name_edit = QLineEdit("Filtered_Signal")
        row_h.addWidget(self.ifft_name_edit)
        
        self.ifft_btn = QPushButton("✂ Remove Targeted Noise")
        self.ifft_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.danger_bg}; color: {theme.danger_text}; padding: 6px;")
        self.ifft_btn.clicked.connect(self.run_ifft_filter)
        row_h.addWidget(self.ifft_btn)
        
        fft_layout.addLayout(row_h)
        self.fft_group.setLayout(fft_layout)
        layout.addWidget(self.fft_group)
        
        self._update_ui_visibility()

    def _toggle_width_mode(self, text):
        self.custom_offset_edit.setVisible("Custom" in text)

    def update_selection_display(self):
        if not self.fft_group.isVisible(): return
        targets = []
        
        selected_rows = list(set([item.row() for item in self.table.selectedItems()]))
        for r in selected_rows:
            if r < len(self.peak_data_memory):
                hz = self.peak_data_memory[r].get("center_hz", 0)
                targets.append(f"{hz:.1f} Hz")
                
        # --- NEW SOURCE OF TRUTH: Read the math arrays, NOT the UI dots! ---
        if getattr(self.parent_gui, 'selected_indices', set()):
            try:
                x_sel, _, _, _ = self.parent_gui._get_all_plotted_xy(apply_selection=True)
                if x_sel is not None and len(x_sel) > 0:
                    min_hz, max_hz = np.min(x_sel), np.max(x_sel)
                    targets.append(f"Box: {min_hz:.1f}-{max_hz:.1f} Hz")
            except Exception:
                pass
                
        if targets:
            self.selection_label.setText(f"<b>Targeted for removal:</b> {', '.join(targets)}")
        else:
            self.selection_label.setText("<b>Targeted for removal:</b> None")

    def _get_toggle_style(self, is_on):
        if is_on: return f"background-color: {theme.primary_text}; color: {theme.panel_bg}; border-radius: 4px; padding: 8px; border: none;"
        return f"background-color: {theme.bg}; color: {theme.fg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 8px;"
        
    def toggle_fft_mode(self):
        is_on = self.fft_toggle_btn.isChecked()
        self.fft_toggle_btn.setStyleSheet(self._get_toggle_style(is_on))
        self.parent_gui.fft_mode_active = is_on
        self._update_ui_visibility()
        self.parent_gui.plot()
        
    def _update_ui_visibility(self):
        self.fft_group.setVisible(self.fft_toggle_btn.isChecked())
        
    def _update_interaction_styles(self):
        active_style = f"background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; font-weight: bold; border-radius: 4px; padding: 4px; color: {theme.primary_text};"
        inactive_style = f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 4px; color: {theme.fg};"
        for b in [self.btn_pan, self.btn_box, self.btn_lasso]:
            b.setStyleSheet(active_style if b.isChecked() else inactive_style)

    def _sync_interaction_mode(self, btn):
        if btn == self.btn_pan: self.parent_gui.btn_pan.click()
        elif btn == self.btn_box: self.parent_gui.btn_box.click()
        elif btn == self.btn_lasso: self.parent_gui.btn_lasso.click()
        self._update_interaction_styles()

    def run_peak_finder(self):
        data_cache = getattr(self.parent_gui, 'last_plotted_data', {})
        if data_cache.get('mode') != '2D' or not data_cache.get('packages'):
            QMessageBox.warning(self, "No Data", "Please plot a 2D curve first.")
            return

        row = max(0, self.parent_gui.series_list.currentRow())
        active_pkgs = [p for p in data_cache['packages'] if p.get("pair_idx", 0) == row and p.get("type") == "standard"]
        
        if not active_pkgs: return
        pkg = active_pkgs[0]
        x = pkg['x'] 
        y = pkg['y']
        axis_side = pkg.get('axis', 'L')
        
        sort_idx = np.argsort(x)
        x = x[sort_idx]
        y = y[sort_idx]
        
        is_x_log = hasattr(self.parent_gui, 'xscale') and self.parent_gui.xscale.currentText() == "Log"
        try: x_base = float(self.parent_gui.xbase.text())
        except Exception: x_base = 10.0
        
        x_raw = (x_base ** x) if is_x_log else x
        
        prom_text = self.prom_edit.text().strip().lower()
        if prom_text == "auto" or not prom_text:
            prominence = (np.max(y) - np.min(y)) * 0.05 
        else:
            try: prominence = float(prom_text)
            except: prominence = 0.0
            
        try: distance = max(1, int(self.dist_edit.text()))
        except: distance = 1

        peaks, properties = sig.find_peaks(y, prominence=prominence, distance=distance)
        if len(peaks) == 0:
            self.table.setRowCount(0)
            self.parent_gui.clear_peak_markers()
            return

        mode = self.width_mode_combo.currentText()
        custom_drop = 0.0
        
        if "Custom" in mode:
            try: custom_drop = float(self.custom_offset_edit.text())
            except ValueError: custom_drop = -3.0
                
            if custom_drop > 0:
                QMessageBox.warning(self, "Invalid Offset", "The offset must be a negative value (e.g., -3.0).")
                self.custom_offset_edit.setText(f"-{abs(custom_drop)}")
                return
                
        proms = properties['prominences']
        left_x_vis, right_x_vis, width_heights = [], [], []

        import warnings
        from PyQt6.QtWidgets import QTableWidgetItem
        
        self.table.setRowCount(len(peaks))
        self.peak_data_memory.clear()
        
        known_noise = []
        if self.fft_toggle_btn.isChecked():
            try: known_noise = [float(val.strip()) for val in self.noise_flag_edit.text().split(",") if val.strip()]
            except: pass

        peak_x_vis = []
        peak_y_vis = []

        for i, p in enumerate(peaks):
            if "FWHM" in mode: rel_h = 0.5
            elif "FWQM" in mode: rel_h = 0.75 
            else: 
                rel_h = abs(custom_drop) / proms[i] if proms[i] != 0 else 0
                rel_h = max(1e-5, min(rel_h, 1.0)) 
                
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                w, w_h, l_ips, r_ips = sig.peak_widths(y, [p], rel_height=rel_h)
                _, _, base_l_ips, base_r_ips = sig.peak_widths(y, [p], rel_height=0.98) # Wide cut bounds for the surgeon
                
            # --- MAP INDICES TO THE ACTUAL X-AXIS (Hz) ---
            # By forcing float(), we stop PyQt from choking on NumPy arrays!
            center_hz = float(x_raw[p])
            peak_height = float(y[p])
            
            # True physical boundaries for the Surgeon to cut
            cut_left = float(np.interp(base_l_ips[0], np.arange(len(x)), x_raw))
            cut_right = float(np.interp(base_r_ips[0], np.arange(len(x)), x_raw))
            
            # Physical width for the UI Table
            lx_r = float(np.interp(l_ips[0], np.arange(len(x)), x_raw))
            rx_r = float(np.interp(r_ips[0], np.arange(len(x)), x_raw))
            width_hz = rx_r - lx_r
            
            # Visual Coordinates for the red/green graph markers
            lx_v = float(np.interp(l_ips[0], np.arange(len(x)), x))
            rx_v = float(np.interp(r_ips[0], np.arange(len(x)), x))
            left_x_vis.append(lx_v)
            right_x_vis.append(rx_v)
            width_heights.append(w_h[0])
            peak_x_vis.append(float(x[p]))
            peak_y_vis.append(peak_height)
            
            # Save accurately to memory
            self.peak_data_memory.append({
                "center_hz": center_hz,
                "width_hz": width_hz,
                "cut_left_hz": cut_left,
                "cut_right_hz": cut_right,
                "height": peak_height
            })
            
            tag = ""
            bg_color = None
            
            if self.fft_toggle_btn.isChecked():
                if center_hz < 0.5: 
                    tag = "Keep (DC Offset)"
                    bg_color = QColor("#e6f7ff") 
                else:
                    for n in known_noise:
                        for harmonic in [1, 2, 3]:
                            target = n * harmonic
                            if abs(center_hz - target) < 1.5: 
                                suffix = "Harmonic" if harmonic > 1 else "Noise"
                                tag = f"⚠️ {n}Hz {suffix}?"
                                bg_color = QColor("#ffe6e6") 
                                break
                        if tag: break

            item_id = QTableWidgetItem(str(i + 1))
            item_x = QTableWidgetItem(f"{center_hz:.2f}")
            item_y = QTableWidgetItem(f"{peak_height:.4f}")
            item_width = QTableWidgetItem(f"{width_hz:.2f}")
            item_tag = QTableWidgetItem(tag)
            
            if bg_color:
                for item in (item_id, item_x, item_y, item_width, item_tag):
                    item.setBackground(bg_color)
            
            self.table.setItem(i, 0, item_id)
            self.table.setItem(i, 1, item_x)
            self.table.setItem(i, 2, item_y)
            self.table.setItem(i, 3, item_width)
            self.table.setItem(i, 4, item_tag)
            
        self.parent_gui.draw_peak_markers(peak_x_vis, peak_y_vis, left_x_vis, right_x_vis, width_heights, axis_side)

    def run_ifft_filter(self):
        selected_rows = list(set([item.row() for item in self.table.selectedItems()]))
        table_cuts = [self.peak_data_memory[r] for r in selected_rows]
        
        manual_cuts = []
        if getattr(self.parent_gui, 'selected_indices', set()):
            try:
                x_sel, _, _, _ = self.parent_gui._get_all_plotted_xy(apply_selection=True)
                if x_sel is not None and len(x_sel) > 0:
                    min_hz, max_hz = np.min(x_sel), np.max(x_sel)
                    manual_cuts.append({"cut_left_hz": float(min_hz), "cut_right_hz": float(max_hz)})
            except Exception:
                pass
                
        all_cuts = table_cuts + manual_cuts
        
        if not all_cuts:
            QMessageBox.warning(self, "No Selection", "Please highlight rows in the table OR draw a box over the noise on the graph.")
            return
            
        new_name = self.ifft_name_edit.text().strip()
        if not new_name: return
        
        existing_names = list(self.parent_gui.dataset.column_names.values())
        if new_name in existing_names:
            QMessageBox.warning(self, "Duplicate Name", f"The column '{new_name}' already exists.\nPlease choose a unique name.")
            return

        self.parent_gui.clear_peak_markers()
        if hasattr(self.parent_gui, 'clear_selection'):
            self.parent_gui.clear_selection()
        self.btn_pan.click() 

        # Because the main window safely secured a mirror before opening this tool, 
        # we can jump straight into the execution!
        self._execute_ifft_math(all_cuts, new_name)

    def _execute_ifft_math(self, all_cuts, new_name):
        row = max(0, self.parent_gui.series_list.currentRow())
        pair = self.parent_gui.series_data["2D"][row]
        xidx, yidx = pair['x'], pair['y']
        
        is_csv = (self.parent_gui.file_type == "CSV")
        sweeps = range(self.parent_gui.dataset.num_sweeps) if not is_csv else [0]
        calculated_data_blocks = []
        
        for sw in sweeps:
            arr = self.parent_gui.dataset.data if is_csv else self.parent_gui.dataset.sweeps[sw].data
            t_raw = np.asarray(arr[:, xidx], dtype=np.float64)
            y_raw = np.asarray(arr[:, yidx], dtype=np.float64)
            
            valid = np.isfinite(t_raw) & np.isfinite(y_raw)
            t_valid = t_raw[valid]
            y_valid = y_raw[valid]
            
            if len(t_valid) < 4:
                calculated_data_blocks.append(np.zeros_like(y_raw))
                continue
                
            dt = np.abs(t_valid[-1] - t_valid[0]) / max(1, len(t_valid) - 1)
            
            yf = np.fft.rfft(y_valid)
            xf = np.fft.rfftfreq(len(y_valid), d=dt)
            
            for cut in all_cuts:
                l_idx = (np.abs(xf - cut["cut_left_hz"])).argmin()
                r_idx = (np.abs(xf - cut["cut_right_hz"])).argmin()
                l_idx = max(0, l_idx - 1)
                r_idx = min(len(yf) - 1, r_idx + 1)
                
                if r_idx > l_idx:
                    yf[l_idx:r_idx] = np.linspace(yf[l_idx], yf[r_idx], r_idx - l_idx)
                    
            y_clean = np.fft.irfft(yf, n=len(y_valid))
            final_y = np.full_like(y_raw, np.nan)
            final_y[valid] = y_clean
            calculated_data_blocks.append(final_y)
            
        try:
            self.parent_gui._append_column_to_file(self.parent_gui.dataset.filename, new_name, calculated_data_blocks)
            opts = getattr(self.parent_gui, 'last_load_opts', {"type": self.parent_gui.file_type, "delimiter": ",", "has_header": True})
            
            self.parent_gui.progress_dialog = QProgressDialog("Applying iFFT Filter & Rebuilding...", "Cancel", 0, 100, self.parent_gui)
            self.parent_gui.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            self.parent_gui.progress_dialog.setCancelButton(None)
            self.parent_gui.progress_dialog.setMinimumDuration(0)
            self.parent_gui.progress_dialog.show()
            QApplication.processEvents()
            
            def on_ifft_loaded(ds):
                # 1. Let the Main Window handle the standard file load safely.
                self.parent_gui._is_plotting = True 
                self.parent_gui._on_load_finished(ds, self.parent_gui.dataset.filename, opts)
                self.parent_gui._is_plotting = False
                
                # 2. SEARCH for the newly created column by its exact name!
                new_col_idx = 0
                for idx, col_name in ds.column_names.items():
                    if col_name == new_name:
                        new_col_idx = idx
                        break
                
                # 3. Redirect the Y-Axis to the newly created filtered column
                row = max(0, self.parent_gui.series_list.currentRow())
                
                if self.parent_gui.series_data.get("2D"):
                    self.parent_gui.series_data["2D"][row]["y"] = new_col_idx
                    self.parent_gui.series_data["2D"][row]["y_name"] = new_name
                
                # 4. Update the UI Dropdowns and Series List to reflect this change
                self.parent_gui.ycol.blockSignals(True)
                self.parent_gui.ycol.setCurrentIndex(new_col_idx)
                self.parent_gui.ycol.blockSignals(False)
                self.parent_gui._refresh_series_list_ui()
                
                # 5. Clean up the Peak Finder HUD
                self.table.clearSelection()
                self.table.setRowCount(0)
                self.peak_data_memory.clear()
                if hasattr(self, 'selection_label'):
                    self.selection_label.setText("<b>Targeted for removal:</b> None")
                self.parent_gui.clear_peak_markers()
                
                # 6. Plot the beautiful filtered spectrum!
                self.parent_gui.plot()
                
            from core.data_loader import DataLoaderThread
            self.parent_gui.loader_thread = DataLoaderThread(self.parent_gui.dataset.filename, opts)
            self.parent_gui.loader_thread.progress.connect(self.parent_gui._update_progress_ui)
            self.parent_gui.loader_thread.finished.connect(on_ifft_loaded)
            self.parent_gui.loader_thread.error.connect(self.parent_gui._on_load_error)
            self.parent_gui.loader_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Filter Error", f"Failed to apply iFFT filter:\n\n{e}")

    def closeEvent(self, event):
        self.selection_timer.stop()
        self.parent_gui.clear_peak_markers()
        super().closeEvent(event)
        
# --- NEW FUNCTION: Restart the timer when the window is reopened ---
    def showEvent(self, event):
        if hasattr(self, 'selection_timer') and not self.selection_timer.isActive():
            self.selection_timer.start(200)
        super().showEvent(event)
        
class BaselineSubtractionDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Baseline Subtraction Tool")
        self.setMinimumSize(800, 650)
        
        # Grab current data
        res = main_window._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0:
            raise ValueError("No valid 2D data to analyze.")
            
        self.x, self.y, self.aux_dict, self.pair = res
        
        # Setup phantom curves for live preview
        if not hasattr(self.main_window, 'phantom_curve'):
            self.main_window.phantom_curve = pg.PlotCurveItem(pen=pg.mkPen("r", width=2, style=Qt.PenStyle.DashLine))
            self.main_window.plot_widget.addItem(self.main_window.phantom_curve)
            
        if not hasattr(self.main_window, 'phantom_baseline_flattened'):
            self.main_window.phantom_baseline_flattened = pg.PlotCurveItem(pen=pg.mkPen("m", width=2))
            self.main_window.plot_widget.addItem(self.main_window.phantom_baseline_flattened)
            self.main_window.phantom_baseline_flattened.hide()

        self.current_baseline = np.zeros_like(self.y)
        
        self._build_ui()
        self._update_preview()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # --- TAB 1: Asymmetric Least Squares (ALS) ---
        tab_als = QWidget()
        als_layout = QVBoxLayout(tab_als)
        als_layout.addWidget(QLabel("<b>Asymmetric Least Squares (ALS)</b><br>"
                                    "Automatically wraps a stiff curve underneath peaks. Great for spectroscopy and chromatography."))
        
        form_als = QFormLayout()
        self.als_lam_edit = QLineEdit("100000")
        self.als_lam_edit.setToolTip("Smoothness (λ): Usually between 10^2 to 10^9")
        self.als_p_edit = QLineEdit("0.01")
        self.als_p_edit.setToolTip("Asymmetry (p): Usually between 0.001 and 0.1")
        
        form_als.addRow("Smoothness (λ):", self.als_lam_edit)
        form_als.addRow("Asymmetry (p):", self.als_p_edit)
        als_layout.addLayout(form_als)
        
        btn_calc_als = QPushButton("Calculate ALS Baseline")
        btn_calc_als.clicked.connect(self._update_preview)
        als_layout.addWidget(btn_calc_als)
        als_layout.addStretch()
        self.tabs.addTab(tab_als, "Auto (ALS)")
        
        # --- TAB 2: Spline / Anchor Points ---
        tab_spline = QWidget()
        spline_layout = QVBoxLayout(tab_spline)
        spline_layout.addWidget(QLabel("<b>Spline Interpolation & Manual Lines</b><br>"
                                       "Select background points with the Lasso, or draw an interactive bendable line."))
                                       
        lasso_layout = QHBoxLayout()
        btn_activate_lasso = QPushButton("🖌️ Select Data (Lasso)")
        btn_activate_lasso.clicked.connect(self._activate_lasso)
        
        btn_manual_line = QPushButton("📏 Draw Manual Line")
        btn_manual_line.clicked.connect(self._activate_manual_polyline)
        
        lasso_layout.addWidget(btn_activate_lasso)
        lasso_layout.addWidget(btn_manual_line)
        spline_layout.addLayout(lasso_layout)
        
        self.anchor_lbl = QLabel("Active Anchors: 0 points")
        spline_layout.addWidget(self.anchor_lbl)
        
        btn_calc_spline = QPushButton("Calculate Spline Baseline")
        btn_calc_spline.clicked.connect(self._update_preview)
        spline_layout.addWidget(btn_calc_spline)
        
        self.spline_x, self.spline_y = np.array([]), np.array([])
        spline_layout.addStretch()
        self.tabs.addTab(tab_spline, "Spline / Manual Line")
        
        # --- TAB 3: Custom Equation ---
        tab_eq = QWidget()
        eq_layout = QVBoxLayout(tab_eq)
        eq_layout.addWidget(QLabel("<b>Custom Mathematical Background</b><br>"
                                   "Type a function (e.g., linear drift or exponential decay) to subtract."))
        
        self._build_custom_equation_ui(eq_layout)
        self.tabs.addTab(tab_eq, "Custom Equation")
        
        # --- GLOBAL PREVIEW CONTROLS ---
        layout.addSpacing(10)
        preview_layout = QHBoxLayout()
        self.preview_btn = QPushButton("Toggle Flattened Preview")
        self.preview_btn.setCheckable(True)
        self.preview_btn.clicked.connect(self._toggle_flattened_preview)
        preview_layout.addWidget(self.preview_btn)
        layout.addLayout(preview_layout)
        
        # --- BOTTOM BUTTONS ---
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Subtract & Create Column")
        ok_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; padding: 6px;")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)
        
        self.tabs.currentChanged.connect(self._update_preview)

    def _build_custom_equation_ui(self, layout):
        btn_layout = QHBoxLayout()
        btn_x = QPushButton("x (Independent Variable)")
        btn_x.setStyleSheet("color: #d90000; font-weight: bold; border: 1px solid #d90000; padding: 4px;")
        btn_x.clicked.connect(lambda: self.equation_input.textCursor().insertText("x"))
        btn_layout.addWidget(btn_x)
        layout.addLayout(btn_layout)

        self.equation_input = QTextEdit()
        self.equation_input.setMaximumHeight(60)
        self.equation_input.setFont(QFont("Consolas", 11))
        self.equation_input.setPlaceholderText("e.g. 0.05 * x + 1.2")
        self.equation_input.textChanged.connect(self._validate_custom_equation)
        layout.addWidget(self.equation_input)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("background-color: white; border: 1px solid #ccc; font-size: 18px; font-family: Cambria, serif; font-style: italic; padding: 10px;")
        self.preview_label.setMinimumHeight(60)
        layout.addWidget(self.preview_label)

        self.parsed_equation = ""
        self.is_valid = False
        layout.addStretch()

    def _validate_custom_equation(self):
        raw_text = self.equation_input.toPlainText().strip()
        if not raw_text:
            self.preview_label.setText("")
            self.is_valid = False
            self.parsed_equation = ""
            self._update_preview()
            return

        # 1. Parse and Validate Math
        py_equation = raw_text
        try: py_equation = re.sub(r'\{\\(.*?)\}', lambda m: f"({PHYSICS_CONSTANTS[m.group(1)]['value']})", py_equation)
        except: pass

        py_equation = py_equation.replace('^', '**')
        # --- NEW: ADDED 'abs' TO LIST ---
        math_funcs = ['arcsinh','arccosh','arctanh','arcsin','arccos','arctan','sinh','cosh','tanh','sin','cos','tan','exp', 'abs']
        for f in math_funcs:
            py_equation = re.sub(r'\b' + f + r'\s*\(', 'np.'+f+'(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)

        # --- NEW: NORM ENGINE ---
        def norm_func(v):
            arr = np.asarray(v, dtype=np.float64)
            m = np.max(arr)
            return arr / m if m != 0 else arr
        # ------------------------

        try:
            # Test run the math with a dummy value (inject norm_func!)
            env = {"np": np, "e": np.e, "pi": np.pi, "x": np.ones(1), "norm": norm_func}
            with np.errstate(all='ignore'): eval(py_equation, {"__builtins__": {}}, env)
            self.is_valid = True
            self.parsed_equation = py_equation
        except Exception:
            self.is_valid = False
            self.preview_label.setText("<span style='color: red;'>Invalid Syntax (or missing variables)</span>")
            self._update_preview()
            return

        # 2. Render Beautiful HTML
        html_text = raw_text
        
        consts = []
        def const_repl(m):
            c_key = m.group(1)
            if c_key in PHYSICS_CONSTANTS:
                c_html = PHYSICS_CONSTANTS[c_key]["html"]
                span = f"<span style='color: #2ca02c; font-weight: bold; font-style: normal;'>{c_html}</span>"
            else: span = f"<span style='color: red;'>{{\\{c_key}}}</span>"
            consts.append(span); return f"__CONST{len(consts)-1}__"
        html_text = re.sub(r'\{\\(.*?)\}', const_repl, html_text)

        xvars = []
        def x_repl(m):
            xvars.append("<span style='color: #d90000; font-weight: bold; font-style: italic;'>x</span>")
            return f"__XVAR{len(xvars)-1}__"
        html_text = re.sub(r'\bx\b', x_repl, html_text)
        
        html_text = html_text.replace('*', '&middot;').replace('-', '&minus;')
        html_text = re.sub(r'\bpi\b', 'π', html_text) 
        
        funcs = []
        def func_repl(m):
            func = m.group(1).lower()
            func = re.sub(r'_?([0-9]+)', r"<sub style='font-size:12px;'>\1</sub>", func)
            funcs.append(f"<span style='font-style: normal; font-weight: bold; color: #222;'>{func}</span>")
            return f"__FUNC{len(funcs)-1}__"
        # --- NEW: ADDED abs AND norm TO REGEX ---
        html_text = re.sub(r'\b(arcsin|arccos|arctan|arcsinh|arccosh|arctanh|sinh|cosh|tanh|sin|cos|tan|ln|log(?:_?[0-9]+)?|exp|abs|norm)\b', func_repl, html_text, flags=re.IGNORECASE)

        def tokenize_to_horizontal(text, f_size):
            parts = re.split(r'(__FUNC\d+__|__PAREN\d+__|__EXP\d+__|__CONST\d+__|__XVAR\d+__)', text)
            row_html = "<table style='display:inline-table; border-collapse: collapse; margin: 0;'><tr>"
            for p in parts:
                if not p: continue
                row_html += f"<td style='vertical-align:middle; padding:0; white-space:nowrap; font-size:{f_size};'>{p}</td>"
            return row_html + "</tr></table>"

        exps = []
        def resolve_exponents(text, is_exp=False):
            f_size_base, f_size_exp = ("15px", "10px") if is_exp else ("22px", "15px")
            spacer = "6px" if is_exp else "10px"
            while True:
                match = re.search(r'([a-zA-Zπ]+|[0-9\.]+|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__XVAR\d+__)\s*\^\s*(-?[a-zA-Zπ]+|-?[0-9\.]+|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__XVAR\d+__)', text)
                if not match: break
                base, exp = match.group(1), match.group(2)
                table = f"<table style='display:inline-table; border-collapse:collapse; margin: 0;'><tr><td style='vertical-align:bottom; padding:0; padding-right:1px; font-size:{f_size_base};'>{base}</td><td style='vertical-align:top; padding:0;'><table style='border-collapse:collapse; margin:0; padding:0;'><tr><td style='vertical-align:top; padding:0; font-size:{f_size_exp};'>{exp}</td></tr><tr><td style='font-size:{spacer}; padding:0;'>&nbsp;</td></tr></table></td></tr></table>"
                exps.append(table); text = text[:match.start()] + f"__EXP{len(exps)-1}__" + text[match.end():]
            return text

        parens = []
        def process_math_block(text, is_exp=False, has_parens=False):
            f_size, p_size = ("15px", "130%") if is_exp else ("22px", "130%")
            if '/' not in text:
                res = tokenize_to_horizontal(text, f_size)
                return f"<table style='display:inline-table; border-collapse:collapse; margin:0;'><tr><td style='vertical-align:middle; font-size:{f_size}; padding:0; color:#222;'>(</td><td style='vertical-align:middle; padding:0;'>{res}</td><td style='vertical-align:middle; font-size:{f_size}; padding:0; color:#222;'>)</td></tr></table>" if has_parens else res
            parts = text.split('/')
            res = tokenize_to_horizontal(parts[0].strip() or "&nbsp;", f_size)
            for p in parts[1:]:
                den = tokenize_to_horizontal(p.strip() or "&nbsp;", f_size)
                res = f"<table style='display:inline-table; vertical-align:middle; border-collapse:collapse; margin: 0 1px;'><tr><td rowspan='2' style='vertical-align:middle; font-size:{p_size}; padding: 0; color:#222;'>{'(' if has_parens else ''}</td><td style='border-bottom:1px solid black; padding: 0 2px; text-align:center; vertical-align:bottom; font-size:{f_size};'>{res}</td><td rowspan='2' style='vertical-align:middle; font-size:{p_size}; padding: 0; color:#222;'>{')' if has_parens else ''}</td></tr><tr><td style='padding: 0 2px; text-align:center; vertical-align:top; font-size:{f_size};'>{den}</td></tr></table>"
                has_parens = False
            return res

        while True:
            match = re.search(r'(\^?)\(([^()]*)\)', html_text)
            if not match: break
            is_e, inner = (match.group(1) == '^'), match.group(2)
            inner = resolve_exponents(inner, is_exp=is_e)
            parens.append(process_math_block(inner, is_exp=is_e, has_parens=True))
            html_text = html_text[:match.start()] + ( '^' if is_e else '' ) + f"__PAREN{len(parens)-1}__" + html_text[match.end():]
            
        html_text = resolve_exponents(html_text, is_exp=False)
        html_text = process_math_block(html_text, is_exp=False, has_parens=False)
        
        for _ in range(15):
            if not re.search(r'__(EXP|PAREN|FUNC|CONST|XVAR)\d+__', html_text): break
            for i in range(len(exps)): html_text = html_text.replace(f"__EXP{i}__", exps[i])
            for i in range(len(parens)): html_text = html_text.replace(f"__PAREN{i}__", parens[i])
            for i in range(len(funcs)): html_text = html_text.replace(f"__FUNC{i}__", funcs[i])
            for i in range(len(consts)): html_text = html_text.replace(f"__CONST{i}__", consts[i])
            for i in range(len(xvars)): html_text = html_text.replace(f"__XVAR{i}__", xvars[i])
            
        self.preview_label.setText(f"<span style='font-size: 22px; font-family: Cambria, serif; font-style: italic;'>y = {html_text}</span>")
        self._update_preview()

    def _capture_spline_anchors(self):
        sel_indices = getattr(self.main_window, 'selected_indices', set())
        if not sel_indices:
            QMessageBox.warning(self, "No Selection", "Draw a box/lasso to select baseline points first.")
            return
            
        valid_indices = sorted([i for i in sel_indices if i < len(self.x)])
        self.spline_x = self.x[valid_indices]
        self.spline_y = self.y[valid_indices]
        self.anchor_lbl.setText(f"Active Anchors: {len(self.spline_x)} points")
        self.main_window.clear_selection()
        self._update_preview()
        
    def _activate_lasso(self):
        self.hide() # Auto-hide window
        self.main_window.btn_lasso.setChecked(True)
        self.main_window._set_interaction_mode(self.main_window.btn_lasso)
        
        # Hand the main window our callback function
        self.main_window._on_selection_finished_cb = self._finish_lasso
        
        
    def _finish_lasso(self):
        self.show()
        self.raise_()
        self._capture_spline_anchors()

    def _capture_spline_anchors(self):
        sel_indices = getattr(self.main_window, 'selected_indices', set())
        if not sel_indices:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Selection", "Draw a box/lasso to select baseline points first.")
            return
            
        valid_indices = sorted([i for i in sel_indices if i < len(self.x)])
        self.spline_x = self.x[valid_indices]
        self.spline_y = self.y[valid_indices]
        self.anchor_lbl.setText(f"Active Anchors: {len(self.spline_x)} points")
        self.main_window.clear_selection()
        self._update_preview()

    def _activate_manual_polyline(self):
        self.hide() # Auto-hide window
        
        # Calculate bounds to place the initial straight line
        x_min, x_max = np.min(self.x), np.max(self.x)
        y_min = np.min(self.y)
        
        # Initialize a 3-point bendable line
        pts = [[x_min, y_min], [(x_min+x_max)/2.0, y_min], [x_max, y_min]]
        self.manual_roi = pg.PolyLineROI(pts, pen=pg.mkPen('g', width=3), closed=False, removable=True)
        self.main_window.plot_widget.addItem(self.manual_roi)
        
        # Add a floating "Done" button directly to the plot screen
        self.done_btn = QPushButton("✅ Apply Line", self.main_window.plot_wrapper)
        self.done_btn.setStyleSheet("font-weight: bold; background-color: #d0e8ff; border: 2px solid #0055ff; padding: 8px; border-radius: 4px;")
        self.done_btn.move(20, 20)
        self.done_btn.show()
        
        def on_done():
            self.done_btn.hide()
            self.done_btn.deleteLater()
            
            # Extract true coordinates from the ROI handles
            pts = self.manual_roi.saveState()['points']
            pos = self.manual_roi.pos()
            self.spline_x = np.array([p[0] + pos.x() for p in pts])
            self.spline_y = np.array([p[1] + pos.y() for p in pts])
            
            # Cleanup UI
            self.main_window.plot_widget.removeItem(self.manual_roi)
            self.anchor_lbl.setText(f"Active Anchors: {len(self.spline_x)} (Manual Line)")
            
            self.show()
            self.raise_()
            self._update_preview()
            
        self.done_btn.clicked.connect(on_done)

    def _calc_als(self, y, lam, p, niter=10):
        from scipy import sparse
        from scipy.sparse.linalg import spsolve
        L = len(y)
        D = sparse.diags([1,-2,1], [0,-1,-2], shape=(L,L-2))
        D = lam * D.dot(D.transpose())
        w = np.ones(L)
        for i in range(niter):
            W = sparse.spdiags(w, 0, L, L)
            Z = W + D
            z = spsolve(Z, w*y)
            w = p * (y > z) + (1-p) * (y < z)
        return z

    def _update_preview(self, *args):
        tab_idx = self.tabs.currentIndex()
        
        if tab_idx == 0: # ALS
            try:
                lam = float(self.als_lam_edit.text())
                p = float(self.als_p_edit.text())
                self.current_baseline = self._calc_als(self.y, lam, p)
            except Exception: return
            
        elif tab_idx == 1: # Spline
            if len(self.spline_x) < 2:
                self.current_baseline = np.zeros_like(self.y)
                return
            import scipy.interpolate
            # Sort anchors chronologically
            sort_idx = np.argsort(self.spline_x)
            sx, sy = self.spline_x[sort_idx], self.spline_y[sort_idx]
            
            # Linear interp outside bounds, cubic inside (if enough points)
            try:
                k = min(3, len(sx) - 1)
                tck = scipy.interpolate.splrep(sx, sy, k=k)
                self.current_baseline = scipy.interpolate.splev(self.x, tck)
            except Exception:
                self.current_baseline = np.interp(self.x, sx, sy)
                
        elif tab_idx == 2: # Custom Equation
            if not self.is_valid: return
            
            # --- NEW: NORM ENGINE ---
            def norm_func(v):
                arr = np.asarray(v, dtype=np.float64)
                m = np.max(arr)
                return arr / m if m != 0 else arr
            # ------------------------
            
            env = {"np": np, "e": np.e, "pi": np.pi, "x": self.x, "norm": norm_func}
            try:
                yfit = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
                if yfit.ndim == 0: yfit = np.full_like(self.x, float(yfit))
                self.current_baseline = yfit
            except Exception: return
            
        # Draw the red baseline curve
        self.main_window.phantom_curve.setData(self.x, self.current_baseline)
        self.main_window.phantom_curve.setVisible(not self.preview_btn.isChecked())
        
        # Draw the flattened preview (magenta)
        subtracted = self.y - self.current_baseline
        self.main_window.phantom_baseline_flattened.setData(self.x, subtracted)
        self.main_window.phantom_baseline_flattened.setVisible(self.preview_btn.isChecked())

    def _toggle_flattened_preview(self):
        self._update_preview()
        if self.preview_btn.isChecked():
            self.preview_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; color: {theme.primary_text};")
            self.preview_btn.setText("View Original Data + Baseline")
        else:
            self.preview_btn.setStyleSheet(f"background-color: {theme.bg}; border: 1px solid {theme.border}; color: {theme.fg};")
            self.preview_btn.setText("Toggle Flattened Preview")

    def closeEvent(self, event):
        if hasattr(self.main_window, 'phantom_curve'): self.main_window.phantom_curve.setVisible(False)
        if hasattr(self.main_window, 'phantom_baseline_flattened'): self.main_window.phantom_baseline_flattened.setVisible(False)
        super().closeEvent(event)
        
    def get_result(self):
        return self.current_baseline
    
class SpectrogramDialog(QDialog):
    def __init__(self, main_window, max_pts):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Spectrogram (STFT) Settings")
        self.setMinimumWidth(350)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Short-Time Fourier Transform</b><br>Maps the frequency spectrum as it changes over time."))
        layout.addSpacing(10)

        form = QFormLayout()
        
        self.window_spin = QSpinBox()
        self.window_spin.setRange(16, max(16, max_pts))
        self.window_spin.setSingleStep(128)
        self.window_spin.setValue(min(256, max(16, max_pts // 10)))
        self.window_spin.setToolTip("Larger windows = Better Frequency resolution, but worse Time resolution.")
        form.addRow("Window Size (pts):", self.window_spin)
        
        self.overlap_spin = QSpinBox()
        self.overlap_spin.setRange(0, self.window_spin.value() - 1)
        self.overlap_spin.setSingleStep(64)
        self.overlap_spin.setValue(self.window_spin.value() // 2)
        form.addRow("Overlap (pts):", self.overlap_spin)
        
        self.window_type = QComboBox()
        self.window_type.addItems(["hann", "hamming", "blackman", "boxcar"])
        form.addRow("Window Type:", self.window_type)
        
        layout.addLayout(form)
        
        self.log_scale_cb = QCheckBox("Logarithmic Power Scale (dB)")
        self.log_scale_cb.setChecked(True)
        layout.addWidget(self.log_scale_cb)
        
        layout.addSpacing(10)
        
        self.apply_btn = QPushButton("Generate Spectrogram")
        self.apply_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; padding: 6px; border-radius: 4px; color: {theme.primary_text};")
        layout.addWidget(self.apply_btn)
        
        # Enforce Overlap < Window Size dynamically
        self.window_spin.valueChanged.connect(self._sync_overlap_limit)

    def _sync_overlap_limit(self, val):
        self.overlap_spin.setMaximum(val - 1)

    def get_params(self):
        return {
            "nperseg": self.window_spin.value(),
            "noverlap": self.overlap_spin.value(),
            "window": self.window_type.currentText(),
            "log": self.log_scale_cb.isChecked()
        }
    
class DataSlicerDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.setWindowTitle("Data Slicer (Non-Monotonic Split)")
        self.setMinimumWidth(450)
        self.main_window = main_window
        dataset = main_window.dataset

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Split a column into two halves based on a threshold.\nPerfect for isolating non-monotonic calibration curves."))
        layout.addSpacing(10)

        form = QFormLayout()

        self.target_col = QComboBox()
        self.cond_col = QComboBox()
        for i, name in dataset.column_names.items():
            self.target_col.addItem(f"{i}: {name}", i)
            self.cond_col.addItem(f"{i}: {name}", i)

        # Pre-select based on current plot
        try:
            self.cond_col.setCurrentIndex(main_window.xcol.currentIndex())
            self.target_col.setCurrentIndex(main_window.ycol.currentIndex())
        except Exception: pass

        form.addRow("Column to Split (Y):", self.target_col)
        form.addRow("Condition Column (X):", self.cond_col)

        thresh_lay = QHBoxLayout()
        self.thresh_edit = QLineEdit("0.0")
        self.grab_btn = QPushButton("📍 Grab from Crosshair")
        self.grab_btn.clicked.connect(self.grab_crosshair)
        thresh_lay.addWidget(self.thresh_edit)
        thresh_lay.addWidget(self.grab_btn)

        form.addRow("Threshold Value:", thresh_lay)
        layout.addLayout(form)

        btn_box = QHBoxLayout()
        ok = QPushButton("Slice Data")
        ok.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        cancel = QPushButton("Cancel")
        btn_box.addStretch(); btn_box.addWidget(cancel); btn_box.addWidget(ok)
        layout.addLayout(btn_box)

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

    def grab_crosshair(self):
        if hasattr(self.main_window, 'vLine') and self.main_window.vLine.isVisible():
            # Grab the X-coordinate of the vertical crosshair line
            val = self.main_window.vLine.value()
            self.thresh_edit.setText(f"{val:.6g}")

    def get_result(self):
        target_idx = self.target_col.currentData()
        cond_idx = self.cond_col.currentData()
        try: thresh = float(self.thresh_edit.text())
        except ValueError: thresh = 0.0
        return target_idx, cond_idx, thresh, self.target_col.currentText().split(": ")[-1]
