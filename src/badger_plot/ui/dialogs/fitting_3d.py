# ui/dialogs/fitting_3d.py
import re
import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QLabel, QPushButton, QTableWidget, QHeaderView,
    QScrollArea, QWidget, QTextEdit, QInputDialog
)
from core.theme import theme
from scipy.optimize import curve_fit
import warnings
from badger_plot.core.constants import PHYSICS_CONSTANTS, GREEK_MAP
from ui.dialogs.data_mgmt import ConstantsDialog
from ui.dialogs.fitting import LocalWorker, calculate_fit_statistics

class Fit3DSurfaceDialog(QDialog):
    def __init__(self, parent_gui):
        super().__init__(parent_gui) 
        
        self.setWindowTitle("Fit 3D Surface to Data")
        self.setMinimumWidth(550)
        self.setMinimumHeight(500)
        self.parent_gui = parent_gui 

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.func_combo = QComboBox()
        self.func_combo.addItems(["2D Polynomial", "2D Gaussian", "2D Lorentzian", "2D Harmonic (Ripple)"])
        form.addRow("Surface type:", self.func_combo)
        
        self.degree_edit = QLineEdit("1")
        form.addRow("Polynomial degree:", self.degree_edit)
        
        layout.addLayout(form)
        
        self.eq_label = QLabel()
        self.eq_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.eq_label)
        
        layout.addWidget(QLabel("<b>Parameter Controls:</b>"))
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(3)
        self.param_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Value / Guess"])
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.param_table.verticalHeader().setVisible(False)
        self.param_table.setAlternatingRowColors(True)
        layout.addWidget(self.param_table)

        btn_box = QHBoxLayout()
        self.auto_guess_btn = QPushButton("✨ Auto-Guess Values")
        self.auto_guess_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; padding: 6px;")
        self.auto_guess_btn.clicked.connect(self.run_auto_guess)
        
        self.apply_btn = QPushButton("Calculate & Apply Fit")
        self.apply_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        self.apply_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addWidget(self.auto_guess_btn)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.apply_btn)
        layout.addLayout(btn_box)

        self.func_combo.currentTextChanged.connect(self._update_ui)
        self.degree_edit.textChanged.connect(self._update_ui)
        self.param_edits = {} 
        self._update_ui()

    def _update_ui(self):
        f = self.func_combo.currentText()
        self.degree_edit.setVisible(f == "2D Polynomial")
        
        math_style = "font-size: 18px; font-family: Cambria, serif; font-style: italic;"
        eq_str = ""
        self.param_names = []
        param_labels = []
        
        if f == "2D Polynomial":
            try: deg = max(1, int(self.degree_edit.text()))
            except Exception: deg = 1
            
            terms = []
            k = 0
            for d in range(deg + 1):
                for i in range(d + 1):
                    j = d - i
                    p_name = f"C{k}"
                    self.param_names.append(p_name)
                    param_labels.append(f"C<sub>{k}</sub>")
                    
                    term = f"C<sub>{k}</sub>"
                    if i == 1: term += "&middot;X"
                    elif i > 1: term += f"&middot;X<sup>{i}</sup>"
                    
                    if j == 1: term += "&middot;Y"
                    elif j > 1: term += f"&middot;Y<sup>{j}</sup>"
                    
                    terms.append(term)
                    k += 1
            
            eq_str = f"<span style='{math_style}'>Z = " + " + ".join(terms) + "</span>"
            
        elif f == "2D Gaussian":
            eq_str = (f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2' align='center'>"
                      f"<tr><td rowspan='2' valign='middle'>Z = A &middot; exp&nbsp;&nbsp;[ &minus; (</td>"
                      f"<td align='center' style='border-bottom: 1px solid black;'>&nbsp;(X &minus; X<sub>0</sub>)<sup>2</sup>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>+</td>"
                      f"<td align='center' style='border-bottom: 1px solid black;'>&nbsp;(Y &minus; Y<sub>0</sub>)<sup>2</sup>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>) ] + D&middot;X + E&middot;Y + C</td></tr>"
                      f"<tr><td align='center'>2&sigma;<sub>x</sub><sup>2</sup></td><td align='center'>2&sigma;<sub>y</sub><sup>2</sup></td></tr></table>")
            self.param_names = ["A", "X0", "Y0", "sigma_x", "sigma_y", "D", "E", "C"]
            param_labels = ["A", "X<sub>0</sub>", "Y<sub>0</sub>", "&sigma;<sub>x</sub>", "&sigma;<sub>y</sub>", "D", "E", "C"]
        
        elif f == "2D Lorentzian":
            eq_str = (f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2' align='center'>"
                      f"<tr><td rowspan='2' valign='middle'>Z = </td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;A&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'> + D&middot;X + E&middot;Y + C</td></tr>"
                      f"<tr><td align='center'><table style='{math_style}' border='0' cellspacing='0' cellpadding='0'>"
                      f"<tr><td rowspan='2' valign='middle'>1 + &nbsp;[</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;X &minus; X<sub>0</sub>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>]<sup>2</sup> + [</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;Y &minus; Y<sub>0</sub>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>]<sup>2</sup></td></tr>"
                      f"<tr><td align='center'>&gamma;<sub>x</sub></td><td align='center'>&gamma;<sub>y</sub></td></tr></table></td></tr></table>")
            self.param_names = ["A", "X0", "Y0", "gamma_x", "gamma_y", "D", "E", "C"]
            param_labels = ["A", "X<sub>0</sub>", "Y<sub>0</sub>", "&gamma;<sub>x</sub>", "&gamma;<sub>y</sub>", "D", "E", "C"]
            
        elif f == "2D Harmonic (Ripple)":
            eq_str = f"<span style='{math_style}'>Z = A &middot; sin(&omega;<sub>x</sub>X + &phi;<sub>x</sub>) &middot; sin(&omega;<sub>y</sub>Y + &phi;<sub>y</sub>) + C</span>"
            self.param_names = ["A", "omega_x", "phi_x", "omega_y", "phi_y", "C"]
            param_labels = ["A", "&omega;<sub>x</sub>", "&phi;<sub>x</sub>", "&omega;<sub>y</sub>", "&phi;<sub>y</sub>", "C"]
        self.eq_label.setText(f"<br>{eq_str}<br>")
        
        self.param_table.setRowCount(len(self.param_names))
        self.param_edits.clear()
        
        for i, (name, label) in enumerate(zip(self.param_names, param_labels)):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 16px; font-family: Cambria, serif; font-style: italic;")
            self.param_table.setCellWidget(i, 0, lbl)
            
            mode_cb = QComboBox()
            mode_cb.addItems(["Auto", "Manual"])
            self.param_table.setCellWidget(i, 1, mode_cb)
            
            val_edit = QLineEdit("1.0")
            self.param_table.setCellWidget(i, 2, val_edit)
            
            self.param_edits[name] = {"mode": mode_cb, "val": val_edit}

    def run_auto_guess(self):
        import numpy as np
        data_cache = getattr(self.parent_gui, 'last_plotted_data', {})
        if data_cache.get('mode') != '3D' or not data_cache.get('data'): return
        
        pts_list = []
        for item in data_cache['data']:
            if str(item[0]) == "SURFACE":
                grid_z = item[2]['z_2d'].flatten()
                X, Y = np.meshgrid(item[2]['x_1d'], item[2]['y_1d'], indexing='ij')
                pts_list.append(np.column_stack((X.flatten(), Y.flatten(), grid_z)))
            else:
                pts_list.append(item[2])
                
        if not pts_list: return
        all_pts = np.vstack(pts_list)
        pts = all_pts[np.isfinite(all_pts).all(axis=1)]
        
        if len(pts) < 5: return
        x, y, z = pts[:, 0], pts[:, 1], pts[:, 2]
        
        f = self.func_combo.currentText()
        guesses = {}
        
        if f == "2D Polynomial":
            guesses = {p: 0.0 for p in self.param_names}
            guesses["C0"] = np.mean(z)
        elif f == "2D Gaussian":
            max_idx = np.argmax(z)
            guesses = {
                "A": np.max(z) - np.min(z),
                "X0": x[max_idx], 
                "Y0": y[max_idx], 
                "sigma_x": (np.max(x) - np.min(x)) / 6.0,
                "sigma_y": (np.max(y) - np.min(y)) / 6.0,
                "D": 0.0,
                "E": 0.0,
                "C": np.min(z)
            }
            
        elif f == "2D Lorentzian":
            max_idx = np.argmax(z)
            guesses = {
                "A": np.max(z) - np.min(z),
                "X0": x[max_idx], 
                "Y0": y[max_idx], 
                "gamma_x": (np.max(x) - np.min(x)) / 10.0,
                "gamma_y": (np.max(y) - np.min(y)) / 10.0,
                "D": 0.0,
                "E": 0.0,
                "C": np.min(z)
            }
        elif f == "2D Harmonic (Ripple)":
            guesses = {
                "A": (np.max(z) - np.min(z)) / 2.0,
                "omega_x": 2.0 * np.pi / ((np.max(x) - np.min(x)) / 3.0), # Assumes roughly 3 ripples across the domain
                "phi_x": 0.0,
                "omega_y": 2.0 * np.pi / ((np.max(y) - np.min(y)) / 3.0),
                "phi_y": 0.0,
                "C": np.mean(z)
            }
            
        for p, val in guesses.items():
            if self.param_edits[p]["mode"].currentText() == "Auto":
                self.param_edits[p]["val"].setText(f"{val:.4g}")

    def get_result(self):
        param_config = {}
        for p, controls in self.param_edits.items():
            try: val = float(controls["val"].text())
            except Exception: val = 1.0
            param_config[p] = {"mode": controls["mode"].currentText(), "value": val}
            
        degree = int(self.degree_edit.text()) if self.func_combo.currentText() == "2D Polynomial" else None
        eq_str = self.eq_label.text().replace('<br>', '')
        
        return self.func_combo.currentText(), param_config, degree, eq_str

    def load_state(self, state):
        type_map = {
            "tilted_plane": "Tilted Plane", 
            "2d_paraboloid": "2D Paraboloid", 
            "2d_gaussian": "2D Gaussian"
        }
        self.func_combo.setCurrentText(type_map.get(state.get("type", ""), "Tilted Plane"))
        
        param_config = state.get("param_config", {})
        for p, config in param_config.items():
            if p in self.param_edits:
                self.param_edits[p]["mode"].setCurrentText(config["mode"])
                self.param_edits[p]["val"].setText(f"{config['value']:.6g}")
                
# --- MODULAR 3D MATHS ENGINE ---

def get_3d_model(func_type, degree=None):
    import numpy as np
    
    if func_type == "2D Polynomial":
        if degree is None: degree = 1
        param_names = [f"C{k}" for k in range(int((degree+1)*(degree+2)/2))]
        
        def model(xy, *args):
            x, y = xy
            z = np.zeros_like(x)
            k = 0
            for d in range(degree + 1):
                for i in range(d + 1):
                    j = d - i
                    z += args[k] * (x**i) * (y**j)
                    k += 1
            return z
        return model, param_names
        
    elif func_type == "2D Gaussian":
        def model(xy, A, X0, Y0, sigma_x, sigma_y, D, E, C):
            x, y = xy
            return A * np.exp(-(((x - X0)**2) / (2 * sigma_x**2) + ((y - Y0)**2) / (2 * sigma_y**2))) + D*x + E*y + C
        return model, ["A", "X0", "Y0", "sigma_x", "sigma_y", "D", "E", "C"]
        
    elif func_type == "2D Lorentzian":
        def model(xy, A, X0, Y0, gamma_x, gamma_y, D, E, C):
            x, y = xy
            return (A / (1 + ((x - X0) / gamma_x)**2 + ((y - Y0) / gamma_y)**2)) + D*x + E*y + C
        return model, ["A", "X0", "Y0", "gamma_x", "gamma_y", "D", "E", "C"]
        
    elif func_type == "2D Harmonic (Ripple)":
        def model(xy, A, omega_x, phi_x, omega_y, phi_y, C):
            x, y = xy
            return A * np.sin(omega_x * x + phi_x) * np.sin(omega_y * y + phi_y) + C
        return model, ["A", "omega_x", "phi_x", "omega_y", "phi_y", "C"]
    return None, []

def execute_3d_surface_fit(pts, func_type, param_config, degree=None):
    from scipy.optimize import curve_fit
    import warnings
    
    model, param_names = get_3d_model(func_type, degree)
    if model is None: raise ValueError(f"Unknown function type: {func_type}")

    x_data, y_data, z_data = pts[:, 0], pts[:, 1], pts[:, 2]

    free_params = []
    fixed_params = {}
    p0 = []

    for p in param_names:
        if param_config[p]["mode"] == "Auto":
            free_params.append(p)
            p0.append(float(param_config[p]["value"]))
        else:
            fixed_params[p] = float(param_config[p]["value"])

    if not free_params:
        # Fallback if fully locked
        return [param_config[p]["value"] for p in param_names], param_names, model, None

    def dynamic_wrapper(xy_val, *args):
        kwargs = dict(fixed_params)
        for name, val in zip(free_params, args):
            kwargs[name] = val
        full_args = [kwargs[p] for p in param_names]
        return model(xy_val, *full_args)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # --- FIX: Capture pcov ---
        popt, pcov = curve_fit(dynamic_wrapper, (x_data, y_data), z_data, p0=p0, maxfev=20000)

    final_params = []
    popt_idx = 0
    
    for p in param_names:
        if p in free_params:
            final_params.append(popt[popt_idx])
            popt_idx += 1
        else:
            final_params.append(fixed_params[p])

    # --- FIX: Defer stats to the async UI button! ---
    return final_params, param_names, model, pcov


class CustomFit3DDialog(QDialog):
    def __init__(self, dataset, parent_gui):
        super().__init__(parent_gui)
        self.setWindowTitle("Fit Custom 3D Surface (Z = f(X, Y))")
        self.resize(800, 700)
        self.dataset = dataset
        self.parent_gui = parent_gui 
        self.available_columns = dataset.column_names
        
        self.parameters = []
        self.is_valid = False
        self.used_cols = []
        self.parsed_equation = ""
        self.html_equation = ""
        
        self.param_configs = {}
        self._swarm_count = 0
        self._is_optimising = False
        self._opt_cycles = 0

        layout = QVBoxLayout(self)

        # 1. Variables & Columns
        layout.addWidget(QLabel("<b>1. Insert Variables & Columns:</b>"))
        btn_layout = QHBoxLayout()
        
        btn_x = QPushButton("X (Axis 1)")
        btn_x.setStyleSheet(f"color: {theme.danger_text}; font-weight: bold; border: 1px solid {theme.danger_border}; padding: 4px;")
        btn_x.clicked.connect(lambda: self.equation_input.textCursor().insertText("x"))
        
        # --- NEW: Y Variable Button ---
        btn_y = QPushButton("Y (Axis 2)")
        btn_y.setStyleSheet(f"color: {theme.danger_text}; font-weight: bold; border: 1px solid {theme.danger_border}; padding: 4px;")
        # ------------------------------
        btn_y.clicked.connect(lambda: self.equation_input.textCursor().insertText("y"))
        # ------------------------------
        
        self.const_btn = QPushButton("✨ Physics Constants")
        self.const_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; border: 1px solid {theme.success_border}; padding: 4px;")
        self.const_btn.clicked.connect(self.open_constants)
        
        btn_layout.addWidget(btn_x)
        btn_layout.addWidget(btn_y)
        btn_layout.addWidget(self.const_btn)
        layout.addLayout(btn_layout)

        col_scroll = QScrollArea()
        col_scroll.setWidgetResizable(True)
        col_scroll.setMaximumHeight(100)
        col_container = QWidget()
        col_grid = QFormLayout(col_container)
        
        row_layout = QHBoxLayout()
        cols_in_row = 0
        for i, name in self.available_columns.items():
            btn = QPushButton(f"[{name}]")
            btn.setStyleSheet(f"color: {theme.primary_text}; font-weight: bold; border: 1px solid {theme.primary_border}; padding: 4px;")
            btn.clicked.connect(lambda checked, n=name: self.equation_input.textCursor().insertText(f"[{n}]"))
            row_layout.addWidget(btn)
            cols_in_row += 1
            if cols_in_row == 4:
                col_grid.addRow(row_layout)
                row_layout = QHBoxLayout()
                cols_in_row = 0
        if cols_in_row > 0: col_grid.addRow(row_layout)
        col_scroll.setWidget(col_container)
        layout.addWidget(col_scroll)

        # 2. Parameters
        layout.addWidget(QLabel("<b>2. Create Parameters to Optimise:</b>"))
        param_creator_layout = QHBoxLayout()
        self.new_param_edit = QLineEdit()
        self.new_param_edit.setPlaceholderText("e.g. A, x0, y0, sigma")
        add_param_btn = QPushButton("Add Parameter")
        add_param_btn.clicked.connect(self.add_parameter)
        param_creator_layout.addWidget(self.new_param_edit)
        param_creator_layout.addWidget(add_param_btn)
        layout.addLayout(param_creator_layout)

        self.param_scroll = QScrollArea()
        self.param_scroll.setWidgetResizable(True)
        self.param_scroll.setMinimumHeight(120)
        self.param_scroll.setMaximumHeight(200)
        self.param_scroll_widget = QWidget()
        self.param_btn_layout = QVBoxLayout(self.param_scroll_widget)
        self.param_btn_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.param_scroll.setWidget(self.param_scroll_widget)
        layout.addWidget(self.param_scroll)

        # 3. Equation
        math_lbl_layout = QHBoxLayout()
        math_lbl_layout.addWidget(QLabel("<b>3. Surface Equation:</b> <i>(Z = f(x, y))</i>"))
        math_lbl_layout.addStretch()
        
        self.template_combo = QComboBox()
        self.template_combo.addItems(["Template...", "2D Gaussian", "2D Lorentzian", "2D Harmonic", "Nth Order 3D Polynomial"])
        self.template_combo.activated.connect(self.apply_template)
        math_lbl_layout.addWidget(self.template_combo)
        
        # --- NEW: Styled Load Button next to the template drop down ---
        self.load_func_btn = QPushButton("📂 Load Saved Function")
        self.load_func_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 4px 10px;")
        self.load_func_btn.clicked.connect(self.load_function)
        math_lbl_layout.addWidget(self.load_func_btn)
        # --------------------------------------------------------------
        
        layout.addLayout(math_lbl_layout)
        
        self.equation_input = QTextEdit()
        self.equation_input.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap) 
        self.equation_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.equation_input.setMaximumHeight(80)
        self.equation_input.setFont(pg.QtGui.QFont("Consolas", 11))
        self.equation_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.equation_input)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet(f"background-color: {theme.panel_bg}; color: {theme.fg}; border: 1px solid {theme.border}; font-size: 22px; font-family: Cambria, serif; font-style: italic; padding: 10px;")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setMinimumHeight(100)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(self.preview_scroll)

        # 4. Settings
        layout.addWidget(QLabel("<b>4. Parameter Settings:</b>"))
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(3)
        self.param_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Value / Guess"])
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.param_table.verticalHeader().setVisible(False)
        layout.addWidget(self.param_table)

        # Buttons
        btn_box = QHBoxLayout()
        
        self.auto_guess_btn = QPushButton("✨ Auto-Guess Values")
        self.auto_guess_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; padding: 6px;")
        self.auto_guess_btn.clicked.connect(self.run_auto_guess)
        self.auto_guess_btn.setEnabled(False)
        
        self.optimize_btn = QPushButton("Optimise Parameters")
        self.optimize_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.optimize_btn.clicked.connect(self.run_optimization)
        self.optimize_btn.setEnabled(False)
        
        self.stop_opt_btn = QPushButton("⏹ Stop Optimisation")
        self.stop_opt_btn.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; padding: 6px;")
        self.stop_opt_btn.clicked.connect(self.stop_optimization)
        self.stop_opt_btn.setVisible(False)
        
        self.done_btn = QPushButton("Done")
        self.done_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        self.done_btn.clicked.connect(self.handle_done)
        self.done_btn.setEnabled(False)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addWidget(self.auto_guess_btn)
        btn_box.addWidget(self.optimize_btn)
        btn_box.addWidget(self.stop_opt_btn)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.done_btn)
        layout.addLayout(btn_box)
        
    def load_function(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        fname, _ = QFileDialog.getOpenFileName(self, "Load 3D Function", "", "Text files (*.txt)")
        if not fname: return

        with open(fname, 'r') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]

        if not lines: return

        # --- FIX: Truncate the file so the math parser ignores the stats block ---
        stats_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("### STATS ###"):
                stats_idx = i
                break
                
        if stats_idx != -1:
            lines = lines[:stats_idx]
        # ------------------------------------------------------------------------

        # 1. The Metadata Gatekeeper
        type_line = lines[0]
        if not type_line.startswith("3D:"):
            QMessageBox.warning(self, "Format Mismatch", "This is a 2D function and cannot be loaded into the 3D surface fitter.")
            return

        func_type = type_line.replace("3D:", "").strip().lower()

        if func_type != "custom":
            QMessageBox.warning(self, "Format Mismatch", "This window only edits Custom 3D equations.")
            return

        try:
            eq_str = lines[1]
            param_names = lines[2].split(",")

            # Detect if auxiliary columns were saved
            aux_cols = []
            val_start_idx = 3
            if lines[3].startswith("aux_cols:"):
                aux_str = lines[3].split(":", 1)[1].strip()
                if aux_str != "None":
                    aux_cols = [c for c in aux_str.split(",")]
                val_start_idx = 4

            vals = [float(x) for x in lines[val_start_idx:]]

            # 2. Wipe the existing UI
            self.template_combo.setCurrentIndex(0)
            self.parameters.clear()
            self.param_table.setRowCount(0)
            self.param_configs.clear()
            self._clear_layout(self.param_btn_layout)

            self.equation_input.blockSignals(True)
            self.equation_input.clear()

            # 3. Rebuild the UI with loaded parameters
            for i, p_name in enumerate(param_names):
                self.new_param_edit.setText(p_name)
                self.add_parameter()
                
                # --- FIX: Keep standard parameters 'Auto' so the buttons unlock ---
                if p_name in ["X_norm", "Y_norm"]:
                    self.param_configs[p_name]["mode"].setCurrentText("Manual")
                else:
                    self.param_configs[p_name]["mode"].setCurrentText("Auto")
                # ------------------------------------------------------------------
                    
                if i < len(vals):
                    self.param_configs[p_name]["val"].setText(f"{vals[i]:.6g}")

            self.equation_input.setPlainText(eq_str)
            self.equation_input.blockSignals(False)
            self.update_preview()

            if aux_cols:
                QMessageBox.information(self, "Dependencies Required", f"This equation relies on auxiliary data columns.\n\nPlease ensure your dataset has the correct columns mapped to avoid evaluation errors.")

        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to parse function file:\n{e}")
        
    def _clear_layout(self, layout):
        """Recursively and safely wipes all widgets and sub-layouts from a parent layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self._clear_layout(item.layout())
                    item.layout().deleteLater()

    def apply_template(self):
        template_name = self.template_combo.currentText()
        if template_name == "Template...": return

        if template_name == "Nth Order 3D Polynomial":
            deg, ok = QInputDialog.getInt(self, "Polynomial Degree", "Enter max polynomial degree (n):", 2, 1, 50)
            if not ok:
                self.template_combo.setCurrentIndex(0)
                return

            params = ["X_norm", "Y_norm"]
            terms = []
            idx = 0
            
            # --- FIX 1: Generate C0, C1, C2... to prevent Physics Constant collisions (like 'F') ---
            for i in range(deg + 1):
                for j in range(deg + 1 - i):
                    p_name = f"C{idx}"
                    params.append(p_name)
                    idx += 1
                    
                    term = f"{{{p_name}}}"
                    if i > 0:
                        term += " * (x / {X_norm})" if i == 1 else f" * (x / {{X_norm}})^{i}"
                    if j > 0:
                        term += " * (y / {Y_norm})" if j == 1 else f" * (y / {{Y_norm}})^{j}"
                        
                    terms.append(term)
                    
            data = {"eq": " + ".join(terms), "params": params}
            
        else:
            templates = {
                "2D Gaussian": {
                    "eq": "{A} * exp(-0.5 * (((x - {X0})/{sigma_x})^2 + ((y - {Y0})/{sigma_y})^2)) + {D}*x + {E}*y + {C}",
                    "params": ["A", "X0", "Y0", "sigma_x", "sigma_y", "D", "E", "C"]
                },
                "2D Lorentzian": {
                    "eq": "{A} / (1 + ((x - {X0})/{gamma_x})^2 + ((y - {Y0})/{gamma_y})^2) + {D}*x + {E}*y + {C}",
                    "params": ["A", "X0", "Y0", "gamma_x", "gamma_y", "D", "E", "C"]
                },
                "2D Harmonic": {
                    "eq": "{A} * sin({omega_x} * x + {phi_x}) * sin({omega_y} * y + {phi_y}) + {C}",
                    "params": ["A", "omega_x", "phi_x", "omega_y", "phi_y", "C"]
                }
            }
            if template_name not in templates: return
            data = templates[template_name]

        self.suspend_updates = True 

        self.parameters.clear()
        self.param_table.setRowCount(0)
        self.param_configs.clear()
        
        # --- FIX 2: Apply the robust layout wiper ---
        self._clear_layout(self.param_btn_layout)

        self.equation_input.blockSignals(True)
        self.equation_input.clear()

        for p_name in data["params"]:
            self.new_param_edit.setText(p_name)
            self.add_parameter()
            
            # Safely lock normalisation constants
            if p_name in ["X_norm", "Y_norm"] and p_name in self.param_configs:
                self.param_configs[p_name]["mode"].setCurrentText("Manual")

        self.equation_input.setPlainText(data["eq"])
        self.template_combo.setCurrentIndex(0)
        
        self.suspend_updates = False
        self.equation_input.blockSignals(False)
        self.update_preview()

    def update_preview(self):
        if getattr(self, 'suspend_updates', False): return
        
        self._swarm_count = 0
        if hasattr(self, 'auto_guess_btn'):
            self.auto_guess_btn.setText("✨ Auto-Guess (Global Search)")
            
        raw_text = self.equation_input.toPlainText().strip()
        if not raw_text:
            self.preview_label.setText(""); self.is_valid = False
            self.parsed_equation = ""; self.html_equation = ""
            self._check_boxes_filled(); return

        self.is_valid, self.parsed_equation = self.validate_equation(raw_text)
        if not self.is_valid:
            import html
            self.preview_label.setText(f"<span style='color: red; font-style: normal;'>{html.escape(raw_text)}</span>")
            self.html_equation = ""; self._check_boxes_filled(); return

        html_text = raw_text
        cols = []
        def col_repl(m):
            cols.append(m.group(0)); return f"__COL{len(cols)-1}__"
        html_text = re.sub(r'\[.*?\]', col_repl, html_text)
        
        consts = []
        def const_repl(m):
            c_key = m.group(1)
            if c_key in PHYSICS_CONSTANTS:
                span = f"<span style='color: {theme.success_text}; font-weight: bold; font-style: normal;'>{PHYSICS_CONSTANTS[c_key]['html']}</span>"
            else: span = f"<span style='color: {theme.danger_text};'>{{\\{c_key}}}</span>"
            consts.append(span); return f"__CONST{len(consts)-1}__"
        html_text = re.sub(r'\{\\(.*?)\}', const_repl, html_text)

        params_html = []
        def param_repl(m):
            p_key = m.group(1)
            if p_key in self.parameters:
                p_html = GREEK_MAP.get(p_key, p_key)
                span = f"<span style='color: {theme.warning_text}; font-weight: bold; font-style: normal;'>{p_html}</span>"
            else: span = f"<span style='color: {theme.danger_text};'>{{{p_key}}}</span>"
            params_html.append(span); return f"__PARAM{len(params_html)-1}__"
        html_text = re.sub(r'\{(.*?)\}', param_repl, html_text)

        # --- NEW: Colour both X and Y ---
        xvars = []
        def x_repl(m):
            xvars.append(f"<span style='color: {theme.danger_text}; font-weight: bold; font-style: italic;'>x</span>")
            return f"__XVAR{len(xvars)-1}__"
        html_text = re.sub(r'\bx\b', x_repl, html_text)
        
        yvars = []
        def y_repl(m):
            yvars.append(f"<span style='color: {theme.danger_text}; font-weight: bold; font-style: italic;'>y</span>")
            return f"__YVAR{len(yvars)-1}__"
        html_text = re.sub(r'\by\b', y_repl, html_text)
        # --------------------------------
        
        html_text = html_text.replace('*', '&middot;').replace('-', '&minus;')
        html_text = re.sub(r'\bpi\b', 'π', html_text) 
        
        funcs = []
        def func_repl(m):
            func = m.group(1).lower()
            func = re.sub(r'_?([0-9]+)', r"<sub style='font-size:12px;'>\1</sub>", func)
            funcs.append(f"<span style='font-style: normal; font-weight: bold; color: {theme.fg};'>{func}</span>")
            return f"__FUNC{len(funcs)-1}__"

        def tokenize_to_horizontal(text, f_size):
            parts = re.split(r'(__COL\d+__|__FUNC\d+__|__PAREN\d+__|__EXP\d+__|__CONST\d+__|__PARAM\d+__|__XVAR\d+__|__YVAR\d+__)', text)
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
                match = re.search(r'([a-zA-Zπ]+|[0-9\.]+|__COL\d+__|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__PARAM\d+__|__XVAR\d+__|__YVAR\d+__)\s*\^\s*(-?[a-zA-Zπ]+|-?[0-9\.]+|__COL\d+__|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__PARAM\d+__|__XVAR\d+__|__YVAR\d+__)', text)
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
                return f"<table style='display:inline-table; border-collapse:collapse; margin:0;'><tr><td style='vertical-align:middle; font-size:{f_size}; padding:0; color:{theme.fg};'>(</td><td style='vertical-align:middle; padding:0;'>{res}</td><td style='vertical-align:middle; font-size:{f_size}; padding:0; color:{theme.fg};'>)</td></tr></table>" if has_parens else res
            parts = text.split('/')
            res = tokenize_to_horizontal(parts[0].strip() or "&nbsp;", f_size)
            for p in parts[1:]:
                den = tokenize_to_horizontal(p.strip() or "&nbsp;", f_size)
                res = f"<table style='display:inline-table; vertical-align:middle; border-collapse:collapse; margin: 0 1px;'><tr><td rowspan='2' style='vertical-align:middle; font-size:{p_size}; padding: 0; color:{theme.fg};'>{'(' if has_parens else ''}</td><td style='border-bottom:1px solid {theme.fg}; padding: 0 2px; text-align:center; vertical-align:bottom; font-size:{f_size};'>{res}</td><td rowspan='2' style='vertical-align:middle; font-size:{p_size}; padding: 0; color:{theme.fg};'>{')' if has_parens else ''}</td></tr><tr><td style='padding: 0 2px; text-align:center; vertical-align:top; font-size:{f_size};'>{den}</td></tr></table>"
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
            if not re.search(r'__(EXP|PAREN|FUNC|COL|CONST|PARAM|XVAR|YVAR)\d+__', html_text): break
            for i in range(len(exps)): html_text = html_text.replace(f"__EXP{i}__", exps[i])
            for i in range(len(parens)): html_text = html_text.replace(f"__PAREN{i}__", parens[i])
            for i in range(len(funcs)): html_text = html_text.replace(f"__FUNC{i}__", funcs[i])
            for i in range(len(consts)): html_text = html_text.replace(f"__CONST{i}__", consts[i])
            for i in range(len(params_html)): html_text = html_text.replace(f"__PARAM{i}__", params_html[i])
            for i in range(len(xvars)): html_text = html_text.replace(f"__XVAR{i}__", xvars[i])
            for i in range(len(yvars)): html_text = html_text.replace(f"__YVAR{i}__", yvars[i])
            for i in range(len(cols)): html_text = html_text.replace(f"__COL{i}__", f"<span style='color: {theme.primary_text}; font-weight: bold;'>{cols[i]}</span>")
            
        self.html_equation = html_text
        self.preview_label.setText(html_text)
        self._check_boxes_filled()

    # ==========================================
    # STAGE 2: THE 3D MATHS ENGINE
    # ==========================================

    def _get_3d_data(self):
        """ Safely extracts the active 3D point cloud from the main window. """
        data_cache = getattr(self.parent_gui, 'last_plotted_data', {})
        if data_cache.get('mode') != '3D' or not data_cache.get('data'): 
            return None, None, None
            
        pts_list = []
        for item in data_cache['data']:
            if str(item[0]) == "SURFACE":
                grid_z = item[2]['z_2d'].flatten()
                X, Y = np.meshgrid(item[2]['x_1d'], item[2]['y_1d'], indexing='ij')
                pts_list.append(np.column_stack((X.flatten(), Y.flatten(), grid_z)))
            else:
                pts_list.append(item[2])
                
        all_pts = np.vstack(pts_list)
        valid = np.isfinite(all_pts).all(axis=1)
        pts = all_pts[valid]
        
        if len(pts) == 0: return None, None, None
        return pts[:, 0], pts[:, 1], pts[:, 2]

    def open_constants(self):
        dlg = ConstantsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_key:
            self.equation_input.textCursor().insertText(f"{{\\{dlg.selected_key}}}")

    def add_parameter(self):
        p_name = self.new_param_edit.text().strip()
        if not p_name or p_name in self.parameters or p_name in PHYSICS_CONSTANTS or p_name in ["x", "y", "np", "e", "pi"]:
            return
            
        self.parameters.append(p_name)
        self.new_param_edit.clear()

        btn = QPushButton(f"{{{p_name}}}")
        btn.setStyleSheet(f"color: {theme.warning_text}; font-weight: bold; border: 1px solid {theme.warning_border}; padding: 4px;")
        btn.clicked.connect(lambda checked, n=p_name: self.equation_input.textCursor().insertText(f"{{{n}}}"))
        
        # --- FIX 3: Bulletproof layout targeting ---
        last_layout = None
        if self.param_btn_layout.count() > 0:
            item = self.param_btn_layout.itemAt(self.param_btn_layout.count() - 1)
            if item.layout() is not None:
                last_layout = item.layout()
                
        if last_layout is None or last_layout.count() >= 4:
            last_layout = QHBoxLayout()
            self.param_btn_layout.addLayout(last_layout)
            
        last_layout.addWidget(btn)
        # -------------------------------------------

        row = self.param_table.rowCount()
        self.param_table.insertRow(row)

        name_lbl = QLabel(p_name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(f"font-weight: bold; color: {theme.warning_text};")
        self.param_table.setCellWidget(row, 0, name_lbl)

        mode_combo = QComboBox()
        mode_combo.addItems(["Auto", "Manual"])
        self.param_table.setCellWidget(row, 1, mode_combo)

        val_edit = QLineEdit("1.0")
        val_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.param_table.setCellWidget(row, 2, val_edit)

        self.param_configs[p_name] = {"mode": mode_combo, "val": val_edit}

        mode_combo.currentTextChanged.connect(self._check_boxes_filled)
        val_edit.textChanged.connect(self._check_boxes_filled)

        self.update_preview()
        self._check_boxes_filled()

    def validate_equation(self, raw_text):
        import re
        if not raw_text: return False, ""
        
        py_eq = raw_text.replace('^', '**')
        
        self.used_cols = []
        def replace_col(match):
            col_name = match.group(1)
            if col_name not in self.available_columns.values(): raise ValueError
            col_idx = next(k for k, v in self.available_columns.items() if v == col_name)
            if col_idx not in self.used_cols: self.used_cols.append(col_idx)
            return f"data_dict[{col_idx}]"
            
        try: py_eq = re.sub(r'\[(.*?)\]', replace_col, py_eq)
        except ValueError: return False, ""

        def replace_const(match):
            c_key = match.group(1)
            if c_key not in PHYSICS_CONSTANTS: raise ValueError
            return f"({PHYSICS_CONSTANTS[c_key]['value']})"
            
        try: py_eq = re.sub(r'\{\\(.*?)\}', replace_const, py_eq)
        except ValueError: return False, ""

        def replace_param(match):
            p_key = match.group(1)
            if p_key not in self.parameters: raise ValueError
            return p_key
            
        try: py_eq = re.sub(r'\{(.*?)\}', replace_param, py_eq)
        except ValueError: return False, ""

        # Add all standard numpy maths functions
        funcs = ['sin', 'cos', 'tan', 'arcsin', 'arccos', 'arctan', 'sinh', 'cosh', 'tanh', 'arcsinh', 'arccosh', 'arctanh', 'exp', 'log10', 'log2', 'log', 'sqrt', 'abs']
        for f in funcs: py_eq = re.sub(r'\b' + f + r'\s*\(', f'np.{f}(', py_eq, flags=re.IGNORECASE)

        # Test the equation mathematically with dummy grids
        try:
            x_dummy = np.array([1.0, 2.0])
            y_dummy = np.array([1.0, 2.0])
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_dummy, "y": y_dummy, "data_dict": {c: np.ones_like(x_dummy) for c in self.used_cols}}
            for p in self.parameters: env[p] = 1.0
            
            res = eval(py_eq, {"__builtins__": {}}, env)
            return True, py_eq
        except Exception:
            return False, ""

    def _check_boxes_filled(self):
        if getattr(self, 'suspend_updates', False): return
        
        all_filled = True
        has_auto = False
        
        for p in self.parameters:
            if not self.param_configs[p]["val"].text().strip(): all_filled = False
            if self.param_configs[p]["mode"].currentText() == "Auto": has_auto = True

        self.done_btn.setEnabled(all_filled and self.is_valid)
        self.auto_guess_btn.setEnabled(has_auto and self.is_valid)
        self.optimize_btn.setEnabled(has_auto and all_filled and self.is_valid)

    def run_auto_guess(self):
        # 1. Router: If local solver got stuck, launch the targeted swarm instead
        if getattr(self, '_swarm_count', 0) > 0:
            self.run_global_search()
            return
            
        if not self.is_valid or not self.parameters: return
        x, y, z = self._get_3d_data()
        if x is None: return

        # 2. Calculate 3D Heuristics
        z_max, z_min = np.max(z), np.min(z)
        z_ptp = z_max - z_min
        z_mean = np.mean(z)
        
        # --- FIX: Find the actual coordinates of the peak (or valley) ---
        target_idx = np.argmax(z) if abs(z_max - z_mean) > abs(z_min - z_mean) else np.argmin(z)
        x_peak = x[target_idx]
        y_peak = y[target_idx]
        # ----------------------------------------------------------------
        
        x_std = np.std(x) if np.std(x) != 0 else 1.0
        y_std = np.std(y) if np.std(y) != 0 else 1.0

        self.suspend_updates = True

        # 3. Smart Parameter Population
        for p in self.parameters:
            is_auto = self.param_configs[p]["mode"].currentText() == "Auto"
            p_lower = p.lower()
            
            # Allow Norm constants to be populated even if locked to Manual
            if not is_auto and p_lower not in ['x_norm', 'y_norm']:
                continue
                
            if p_lower in ['a', 'amp', 'amplitude']: guess = z_max if z_min >= 0 else z_ptp / 2.0
            elif p_lower in ['c', 'z0', 'offset', 'base', 'baseline']: guess = z_min if z_min > 0 else z_mean
            
            # X-Axis specific parameters
            elif p_lower in ['x0', 'mu_x', 'center_x', 'cx']: guess = x_peak
            elif p_lower in ['sigma_x', 'wx', 'width_x', 'gamma_x']: guess = x_std
            elif p_lower in ['omega_x', 'freq_x']: guess = 1.0 / x_std if x_std != 0 else 1.0
            elif p_lower == 'x_norm': guess = np.max(np.abs(x)) if np.max(np.abs(x)) != 0 else 1.0
            
            # Y-Axis specific parameters
            elif p_lower in ['y0', 'mu_y', 'center_y', 'cy']: guess = y_peak
            elif p_lower in ['sigma_y', 'wy', 'width_y', 'gamma_y']: guess = y_std
            elif p_lower in ['omega_y', 'freq_y']: guess = 1.0 / y_std if y_std != 0 else 1.0
            elif p_lower == 'y_norm': guess = np.max(np.abs(y)) if np.max(np.abs(y)) != 0 else 1.0
            
            # Polynomial flatline prevention
            elif len(p_lower) <= 2: guess = 0.0 
            else: guess = 1.0
                
            self.param_configs[p]["val"].blockSignals(True)
            self.param_configs[p]["val"].setText(f"{guess:.4g}")
            self.param_configs[p]["val"].blockSignals(False)

        self.suspend_updates = False
        self._check_boxes_filled()

    def run_global_search(self):
        from PyQt6.QtWidgets import QProgressDialog, QMessageBox
        if not self.is_valid or not self.parameters: return
        x, y, z = self._get_3d_data()
        if x is None: return

        # Need dummy dict for columns, assuming 0 for Swarm if not provided
        safe_aux = {c: np.zeros_like(x) for c in self.used_cols}

        self.swarm_progress = QProgressDialog("Running 3D Swarm Search...", "Cancel", 0, 100, self)
        self.swarm_progress.setWindowTitle("Swarming")
        self.swarm_progress.setModal(True)
        self.swarm_progress.setMinimumDuration(0)
        self.swarm_progress.setValue(0)

        def run_swarm():
            from scipy.optimize import differential_evolution
            import warnings
            
            def objective(params):
                env = {"np": np, "e": np.e, "pi": np.pi, "x": x, "y": y, "data_dict": safe_aux}
                for i, p in enumerate(self.parameters): env[p] = params[i]
                try:
                    with np.errstate(all='ignore'):
                        z_pred = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
                    if z_pred.ndim == 0: z_pred = np.full_like(x, float(z_pred))
                    return np.sum((z - z_pred)**2)
                except:
                    return np.inf

            max_iterations = 300 # Slightly lower for 3D as evaluating grids is heavy
            current_iter = [0]

            def swarm_callback(xk, convergence=0.0):
                current_iter[0] += 1
                pct = int((current_iter[0] / max_iterations) * 100)
                if hasattr(self, 'swarm_worker'): self.swarm_worker.progress.emit(pct)
                if self.swarm_progress.wasCanceled(): return True 

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                bounds = []
                is_targeted = getattr(self, '_swarm_count', 0) > 0
                
                for p in self.parameters:
                    is_auto = self.param_configs[p]["mode"].currentText() == "Auto"
                    try: current_val = float(self.param_configs[p]["val"].text())
                    except: current_val = 1.0
                    
                    if not is_auto:
                        margin = 1e-8
                        bounds.append((current_val - margin, current_val + margin))
                    elif not is_targeted:
                        bounds.append((-10000.0, 10000.0))
                    else:
                        margin = max(abs(current_val) * 0.5, 2.0)
                        bounds.append((current_val - margin, current_val + margin))
                
                pop = max(5, min(15, 200 // max(1, len(self.parameters))))
                result = differential_evolution(objective, bounds, maxiter=max_iterations, popsize=pop, tol=0.01, callback=swarm_callback)
                
                if not result.success and not self.swarm_progress.wasCanceled():
                    if "Maximum number of iterations" not in result.message:
                        raise Exception("Swarm failed to converge.")
                return result.x

        self.swarm_worker = LocalWorker(run_swarm)

        def on_success(best_params):
            self.swarm_progress.accept()
            self._swarm_count += 1
            self.auto_guess_btn.setText("✨ Targeted Swarm (Local)")
            
            for i, p in enumerate(self.parameters):
                if self.param_configs[p]["mode"].currentText() == "Auto":
                    self.param_configs[p]["val"].blockSignals(True)
                    self.param_configs[p]["val"].setText(f"{best_params[i]:.6g}")
                    self.param_configs[p]["val"].blockSignals(False)
            self._check_boxes_filled()
            QMessageBox.information(self, "Swarm Complete", "Global search found the best starting parameters!")

        def on_err(err_str):
            self.swarm_progress.accept()
            QMessageBox.warning(self, "Swarm Failed", f"The search could not find a reasonable fit:\n{err_str}")

        self.swarm_worker.finished.connect(on_success)
        self.swarm_worker.error.connect(on_err)
        self.swarm_worker.progress.connect(self.swarm_progress.setValue)
        self.swarm_progress.canceled.connect(self.swarm_worker.terminate)
        self.swarm_worker.start()

    def run_optimization(self):
        if not self.is_valid or not self.parameters: return
        self._is_optimizing = True
        self._opt_cycles = 0 
        
        self.optimize_btn.setVisible(False)
        self.stop_opt_btn.setVisible(True)
        self.done_btn.setEnabled(False)
        self.auto_guess_btn.setEnabled(False)
        
        self._run_opt_step()

    def _run_opt_step(self):
        if not getattr(self, '_is_optimizing', False): return
        
        x, y, z = self._get_3d_data()
        if x is None: return
        safe_aux = {c: np.zeros_like(x) for c in self.used_cols}

        free_params = []
        fixed_params = {}
        p0 = []
        old_vals = []
        
        for p in self.parameters:
            try: val = float(self.param_configs[p]["val"].text())
            except ValueError: val = 1.0
                
            if self.param_configs[p]["mode"].currentText() == "Auto":
                free_params.append(p)
                p0.append(val)
                old_vals.append(val)
            else:
                fixed_params[p] = val

        if not free_params:
            self.stop_optimization()
            return

        # 1. 3D MATHS TRICK: SciPy only accepts one independent variable. 
        # We pack our X and Y arrays into a single tuple here.
        def dynamic_wrapper(xy_tuple, *args):
            x_val, y_val = xy_tuple
            kwargs = dict(fixed_params)
            for name, val in zip(free_params, args):
                kwargs[name] = val
                
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "y": y_val, "data_dict": safe_aux}
            for p_name in self.parameters: env[p_name] = kwargs[p_name]
            
            res_arr = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
            return res_arr

        def execute_scipy():
            from scipy.optimize import curve_fit
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                popt, pcov = curve_fit(dynamic_wrapper, (x, y), z, p0=p0, maxfev=5000)
                
            final_params = []
            popt_idx = 0
            
            for p in self.parameters:
                if p in free_params:
                    final_params.append(popt[popt_idx])
                    popt_idx += 1
                else:
                    final_params.append(fixed_params[p])
                    
            # Return raw matrix instead of eager stats
            return final_params, pcov

        self.opt_worker = LocalWorker(execute_scipy)

        def on_success(result):
            from PyQt6.QtWidgets import QMessageBox
            final_params, pcov = result
            self.latest_pcov = pcov # Save to memory for get_result()
            self._opt_cycles += 1
            
            new_vals = []
            for i, p in enumerate(self.parameters):
                if self.param_configs[p]["mode"].currentText() == "Auto":
                    new_vals.append(final_params[i])
                    self.param_configs[p]["val"].blockSignals(True)
                    self.param_configs[p]["val"].setText(f"{final_params[i]:.6g}")
                    self.param_configs[p]["val"].blockSignals(False)
            
            # Check for mathematical convergence
            if old_vals and np.allclose(old_vals, new_vals, rtol=1e-5):
                self.stop_optimization()
                QMessageBox.information(self, "Optimization Complete", "The parameters have converged on the optimal surface.")
                
            # Check if we hit the patience limit
            elif self._opt_cycles >= 30:
                self.stop_optimization()
                self._swarm_count = 1 
                self.auto_guess_btn.setText("✨ Targeted Swarm (Local)")
                QMessageBox.warning(self, "Optimization Halted", "The local solver reached its maximum iteration limit without fully converging.\n\nTry clicking 'Targeted Swarm (Local)' to dynamically bump the parameters out of this local trap!")
                
            # Otherwise, keep looping
            elif getattr(self, '_is_optimizing', False):
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(10, self._run_opt_step)

        def on_err(err_str):
            from PyQt6.QtWidgets import QMessageBox
            self.stop_optimization()
            QMessageBox.warning(self, "Optimization Error", f"Failed to optimize parameters:\n{err_str}")

        self.opt_worker.finished.connect(on_success)
        self.opt_worker.error.connect(on_err)
        self.opt_worker.start()

    def stop_optimization(self):
        self._is_optimizing = False
        self.optimize_btn.setVisible(True)
        self.stop_opt_btn.setVisible(False)
        self.done_btn.setEnabled(True)
        self.auto_guess_btn.setEnabled(True)

    def get_result(self):
        final_config = {}
        for p, controls in self.param_configs.items():
            try: val = float(controls["val"].text())
            except: val = 1.0
            final_config[p] = {"mode": controls["mode"].currentText(), "value": val}
            
        pcov = getattr(self, 'latest_pcov', None)

        return self.equation_input.toPlainText().strip(), self.parsed_equation, self.html_equation, self.used_cols, self.parameters, final_config, pcov

    def handle_done(self):
        self.accept()
