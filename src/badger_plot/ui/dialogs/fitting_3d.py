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
        return [param_config[p]["value"] for p in param_names], param_names, model

    def dynamic_wrapper(xy_val, *args):
        kwargs = dict(fixed_params)
        for name, val in zip(free_params, args):
            kwargs[name] = val
        full_args = [kwargs[p] for p in param_names]
        return model(xy_val, *full_args)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        popt, _ = curve_fit(dynamic_wrapper, (x_data, y_data), z_data, p0=p0, maxfev=20000)

    final_params = []
    popt_idx = 0
    for p in param_names:
        if p in free_params:
            final_params.append(popt[popt_idx])
            popt_idx += 1
        else:
            final_params.append(fixed_params[p])

    return final_params, param_names, model

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
