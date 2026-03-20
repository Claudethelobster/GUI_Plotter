# ui/dialogs/fitting_3d.py
import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QLabel, QPushButton, QTableWidget, QHeaderView
)
from core.theme import theme
from scipy.optimize import curve_fit
import warnings

class Fit3DSurfaceDialog(QDialog):
    def __init__(self, parent_gui):
        super().__init__(parent_gui) 
        
        self.setWindowTitle("Fit 3D Surface to Data")
        self.setMinimumWidth(500)
        self.setMinimumHeight(450)
        self.parent_gui = parent_gui 

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.func_combo = QComboBox()
        self.func_combo.addItems([
            "Tilted Plane", "2D Paraboloid", "2D Gaussian"
        ])
        form.addRow("Surface type:", self.func_combo)
        layout.addLayout(form)
        
        self.eq_label = QLabel()
        self.eq_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.eq_label)
        
        layout.addWidget(QLabel("<b>Parameter Controls:</b>"))
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(3)
        self.param_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Value / Guess"])
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
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
        self.param_edits = {} 
        self._update_ui()

    def _update_ui(self):
        f = self.func_combo.currentText()
        math_style = "font-size: 18px; font-family: Cambria, serif; font-style: italic;"
        eq_str = ""
        self.param_names = []
        param_labels = []
        
        if f == "Tilted Plane":
            eq_str = f"<span style='{math_style}'>Z = A&middot;X + B&middot;Y + C</span>"
            self.param_names, param_labels = ["A", "B", "C"], ["A", "B", "C"]
            
        elif f == "2D Paraboloid":
            eq_str = f"<span style='{math_style}'>Z = A&middot;X<sup>2</sup> + B&middot;Y<sup>2</sup> + C&middot;X + D&middot;Y + E</span>"
            self.param_names, param_labels = ["A", "B", "C", "D", "E"], ["A", "B", "C", "D", "E"]
            
        elif f == "2D Gaussian":
            # --- UPGRADE: Added a Tilted Baseline (D*X + E*Y + C) ---
            eq_str = (f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2' align='center'>"
                      f"<tr><td rowspan='2' valign='middle'>Z = A &middot; exp&nbsp;&nbsp;[ &minus; (</td>"
                      f"<td align='center' style='border-bottom: 1px solid black;'>&nbsp;(X &minus; X<sub>0</sub>)<sup>2</sup>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>+</td>"
                      f"<td align='center' style='border-bottom: 1px solid black;'>&nbsp;(Y &minus; Y<sub>0</sub>)<sup>2</sup>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>) ] + D&middot;X + E&middot;Y + C</td></tr>"
                      f"<tr><td align='center'>2&sigma;<sub>x</sub><sup>2</sup></td><td align='center'>2&sigma;<sub>y</sub><sup>2</sup></td></tr></table>")
            self.param_names = ["A", "X0", "Y0", "sigma_x", "sigma_y", "D", "E", "C"]
            param_labels = ["A", "X<sub>0</sub>", "Y<sub>0</sub>", "&sigma;<sub>x</sub>", "&sigma;<sub>y</sub>", "D", "E", "C"]
            
        self.eq_label.setText(f"<br>{eq_str}<br>")
        
        self.param_table.setRowCount(len(self.param_names))
        self.param_edits.clear()
        
        for i, (name, label) in enumerate(zip(self.param_names, param_labels)):
            lbl = QLabel(label)
            lbl.setAlignment(Qt.AlignCenter)
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
        
        if f == "Tilted Plane":
            guesses = {"A": 0.0, "B": 0.0, "C": np.mean(z)}
        elif f == "2D Paraboloid":
            guesses = {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0, "E": np.mean(z)}
        elif f == "2D Gaussian":
            # --- UPGRADE: True Peak Hunting ---
            max_idx = np.argmax(z)
            guesses = {
                "A": np.max(z) - np.min(z),
                "X0": x[max_idx], # Hunt for the physical peak coordinates!
                "Y0": y[max_idx], 
                "sigma_x": (np.max(x) - np.min(x)) / 6.0,
                "sigma_y": (np.max(y) - np.min(y)) / 6.0,
                "D": 0.0,
                "E": 0.0,
                "C": np.min(z)
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
            
        return self.func_combo.currentText(), param_config

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

def get_3d_model(func_type):
    import numpy as np
    if func_type == "Tilted Plane":
        def model(xy, A, B, C):
            x, y = xy
            return A * x + B * y + C
        return model, ["A", "B", "C"]
        
    elif func_type == "2D Paraboloid":
        def model(xy, A, B, C, D, E):
            x, y = xy
            return A * x**2 + B * y**2 + C * x + D * y + E
        return model, ["A", "B", "C", "D", "E"]
        
    elif func_type == "2D Gaussian":
        # --- UPGRADE: Execute the new Tilted Baseline parameters ---
        def model(xy, A, X0, Y0, sigma_x, sigma_y, D, E, C):
            x, y = xy
            return A * np.exp(-(((x - X0)**2) / (2 * sigma_x**2) + ((y - Y0)**2) / (2 * sigma_y**2))) + D*x + E*y + C
        return model, ["A", "X0", "Y0", "sigma_x", "sigma_y", "D", "E", "C"]
        
    return None, []

def execute_3d_surface_fit(pts, func_type, param_config):
    """
    Universally optimises any 3D model, respecting locked (Manual) parameters.
    Expects pts as an Nx3 NumPy array: [X, Y, Z]
    """
    model, param_names = get_3d_model(func_type)
    if model is None: raise ValueError(f"Unknown function type: {func_type}")

    x_data, y_data, z_data = pts[:, 0], pts[:, 1], pts[:, 2]

    free_params = []
    fixed_params = {}
    p0 = []

    # Sort parameters into free (Auto) and fixed (Manual)
    for p in param_names:
        if param_config[p]["mode"] == "Auto":
            free_params.append(p)
            p0.append(float(param_config[p]["value"]))
        else:
            fixed_params[p] = float(param_config[p]["value"])

    # If all parameters are locked, skip the solver entirely
    if not free_params:
        return [param_config[p]["value"] for p in param_names], param_names, model

    # Dynamic wrapper to inject fixed parameters during SciPy iteration
    def dynamic_wrapper(xy_val, *args):
        kwargs = dict(fixed_params)
        for name, val in zip(free_params, args):
            kwargs[name] = val
        full_args = [kwargs[p] for p in param_names]
        return model(xy_val, *full_args)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # SciPy expects independent variables as a tuple: (X, Y)
        popt, _ = curve_fit(dynamic_wrapper, (x_data, y_data), z_data, p0=p0, maxfev=20000)

    # Reconstruct the final parameter list in the correct order
    final_params = []
    popt_idx = 0
    for p in param_names:
        if p in free_params:
            final_params.append(popt[popt_idx])
            popt_idx += 1
        else:
            final_params.append(fixed_params[p])

    return final_params, param_names, model
