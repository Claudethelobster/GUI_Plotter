# ui/dialogs/analysis.py
import os
import numpy as np
import scipy.signal as sig
import scipy.integrate as intg
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QCheckBox, QLabel, QPushButton, QSpinBox, QTableWidget, QHeaderView,
    QAbstractItemView, QGroupBox, QButtonGroup, QMessageBox, QApplication, QProgressDialog
)

from core.data_loader import DataLoaderThread

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
        self.save_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
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
        self.calc_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.calc_btn)
        layout.addLayout(btn_box)

        self.calc_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

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
        self.find_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
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
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        
        self.peak_data_memory = []
        
        self.fft_group = QGroupBox("✂ Interactive iFFT Surgeon")
        self.fft_group.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #d90000; border-radius: 6px; margin-top: 10px; padding-top: 15px; } QGroupBox::title { color: #d90000; left: 10px; }")
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
        self.selection_label.setStyleSheet("color: #d90000; font-size: 13px; padding: 4px; border: 1px dashed #d90000; background-color: #fff0f0;")
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
        self.ifft_btn.setStyleSheet("font-weight: bold; background-color: #ffe6e6; color: #d90000; padding: 6px;")
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
                
        if getattr(self.parent_gui, 'selected_indices', set()):
            x_vis, _, _, _ = self.parent_gui._get_all_plotted_xy(apply_selection=True)
            if len(x_vis) > 0:
                min_hz, max_hz = np.min(x_vis), np.max(x_vis)
                targets.append(f"Box: {min_hz:.1f}-{max_hz:.1f} Hz")
                
        if targets:
            self.selection_label.setText(f"<b>Targeted for removal:</b> {', '.join(targets)}")
        else:
            self.selection_label.setText("<b>Targeted for removal:</b> None")

    def _get_toggle_style(self, is_on):
        if is_on: return "background-color: #0055ff; color: white; border-radius: 4px; padding: 8px; border: none;"
        return "background-color: #f5f5f5; color: black; border: 1px solid #aaa; border-radius: 4px; padding: 8px;"
        
    def toggle_fft_mode(self):
        is_on = self.fft_toggle_btn.isChecked()
        self.fft_toggle_btn.setStyleSheet(self._get_toggle_style(is_on))
        self.parent_gui.fft_mode_active = is_on
        self._update_ui_visibility()
        self.parent_gui.plot()
        
    def _update_ui_visibility(self):
        self.fft_group.setVisible(self.fft_toggle_btn.isChecked())
        
    def _update_interaction_styles(self):
        active_style = "background-color: #d0e8ff; border: 2px solid #0078d7; font-weight: bold; border-radius: 4px; padding: 4px;"
        inactive_style = "background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 4px;"
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
        left_x_vis, right_x_vis, width_real, width_heights = [], [], [], []

        import warnings
        for i, p in enumerate(peaks):
            if "FWHM" in mode: rel_h = 0.5
            elif "FWQM" in mode: rel_h = 0.75 
            else: 
                rel_h = abs(custom_drop) / proms[i] if proms[i] != 0 else 0
                rel_h = max(1e-5, min(rel_h, 1.0)) 
                
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                w, w_h, l_ips, r_ips = sig.peak_widths(y, [p], rel_height=rel_h)
                
            lx_v = np.interp(l_ips[0], np.arange(len(x)), x)
            rx_v = np.interp(r_ips[0], np.arange(len(x)), x)
            left_x_vis.append(lx_v)
            right_x_vis.append(rx_v)
            width_heights.append(w_h[0])
            
            lx_r = np.interp(l_ips[0], np.arange(len(x)), x_raw)
            rx_r = np.interp(r_ips[0], np.arange(len(x)), x_raw)
            width_real.append(rx_r - lx_r)
            
        _, _, base_left_ips, base_right_ips = sig.peak_widths(y, peaks, rel_height=0.98)
        base_left_x_raw = np.interp(base_left_ips, np.arange(len(x)), x_raw)
        base_right_x_raw = np.interp(base_right_ips, np.arange(len(x)), x_raw)

        peak_x_vis = x[peaks]
        peak_x_raw = x_raw[peaks]
        peak_y = y[peaks]

        self.table.setRowCount(len(peaks))
        self.peak_data_memory.clear()
        
        known_noise = []
        if self.fft_toggle_btn.isChecked():
            try: known_noise = [float(val.strip()) for val in self.noise_flag_edit.text().split(",") if val.strip()]
            except: pass

        from PyQt5.QtWidgets import QTableWidgetItem
        for i in range(len(peaks)):
            freq = peak_x_raw[i] 
            tag = ""
            bg_color = None
            
            if self.fft_toggle_btn.isChecked():
                if freq < 0.5: 
                    tag = "Keep (DC Offset)"
                    bg_color = QColor("#e6f7ff") 
                else:
                    for n in known_noise:
                        for harmonic in [1, 2, 3]:
                            target = n * harmonic
                            if abs(freq - target) < 1.5: 
                                suffix = "Harmonic" if harmonic > 1 else "Noise"
                                tag = f"⚠️ {n}Hz {suffix}?"
                                bg_color = QColor("#ffe6e6") 
                                break
                        if tag: break

            item_id = QTableWidgetItem(str(i + 1))
            item_x = QTableWidgetItem(f"{peak_x_raw[i]:.6g}")
            item_y = QTableWidgetItem(f"{peak_y[i]:.6g}")
            item_width = QTableWidgetItem(f"{width_real[i]:.6g}")
            item_tag = QTableWidgetItem(tag)
            
            if bg_color:
                for item in (item_id, item_x, item_y, item_width, item_tag):
                    item.setBackground(bg_color)
            
            self.table.setItem(i, 0, item_id)
            self.table.setItem(i, 1, item_x)
            self.table.setItem(i, 2, item_y)
            self.table.setItem(i, 3, item_width)
            self.table.setItem(i, 4, item_tag)
            
            self.peak_data_memory.append({
                "center_hz": peak_x_raw[i],
                "cut_left_hz": base_left_x_raw[i],
                "cut_right_hz": base_right_x_raw[i]
            })
            
        self.parent_gui.draw_peak_markers(peak_x_vis, peak_y, left_x_vis, right_x_vis, width_heights, axis_side)

    def run_ifft_filter(self):
        selected_rows = list(set([item.row() for item in self.table.selectedItems()]))
        table_cuts = [self.peak_data_memory[r] for r in selected_rows]
        
        manual_cuts = []
        if getattr(self.parent_gui, 'selected_indices', set()):
            x_vis, _, _, _ = self.parent_gui._get_all_plotted_xy(apply_selection=True)
            if len(x_vis) > 0:
                min_hz, max_hz = np.min(x_vis), np.max(x_vis)
                manual_cuts.append({"cut_left_hz": min_hz, "cut_right_hz": max_hz})
                
        all_cuts = table_cuts + manual_cuts
        
        if not all_cuts:
            QMessageBox.warning(self, "No Selection", "Please highlight rows in the table OR draw a box over the noise on the graph.")
            return
            
        new_name = self.ifft_name_edit.text().strip()
        if not new_name: return

        self.parent_gui.clear_peak_markers()
        if hasattr(self.parent_gui, 'clear_selection'):
            self.parent_gui.clear_selection()
        self.btn_pan.click() 
        
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
            self.parent_gui.progress_dialog.setWindowModality(Qt.WindowModal)
            self.parent_gui.progress_dialog.setCancelButton(None)
            self.parent_gui.progress_dialog.setMinimumDuration(0)
            self.parent_gui.progress_dialog.show()
            QApplication.processEvents()
            
            def on_ifft_loaded(ds):
                self.parent_gui._on_load_finished(ds, self.parent_gui.dataset.filename, opts)
                
                def apply_new_plot():
                    new_col_idx = len(self.parent_gui.dataset.column_names) - 1
                    self.parent_gui.ycol.blockSignals(False)
                    self.parent_gui.ycol.setCurrentIndex(new_col_idx)
                    self.parent_gui.update_current_series()
                    self.parent_gui.plot()
                    
                    def post_plot_cleanup():
                        self.run_peak_finder()
                        self.parent_gui.clear_peak_markers()
                        self.table.clearSelection() 
                        
                    QTimer.singleShot(600, post_plot_cleanup)
                QTimer.singleShot(150, apply_new_plot)
                
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
