# ui/dialogs/fitting.py
import os
import re
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pgexp
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QMainWindow, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QLabel, QPushButton, QTableWidget, QHeaderView,
    QScrollArea, QWidget, QFileDialog, QMessageBox, QApplication, QTextEdit
)

from badger_plot.core.constants import PHYSICS_CONSTANTS, GREEK_MAP
from core.theme import theme
from badger_plot.ui.dialogs.data_mgmt import ConstantsDialog, CopyableErrorDialog
from badger_plot.utils.function_io import load_function_from_file

class FitFunctionDialog(QDialog):
    def __init__(self, parent_gui):
        super().__init__(parent_gui) 
        
        self.setWindowTitle("Fit function to data")
        self.setMinimumWidth(450)
        self.setMinimumHeight(450)
        self.parent_gui = parent_gui 

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.func_combo = QComboBox()
        self.func_combo.addItems([
            "Polynomial", "Logarithmic", "Exponential", "Gaussian", "Lorentzian"
        ])
        form.addRow("Function type:", self.func_combo)

        self.degree_edit = QLineEdit("1")
        form.addRow("Polynomial degree:", self.degree_edit)

        self.log_base_edit = QLineEdit("e")
        form.addRow("Log base:", self.log_base_edit)
        
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
        self.log_base_edit.textChanged.connect(self._update_ui)

        self.param_edits = {} 
        self._update_ui()

    def _update_ui(self):
        f = self.func_combo.currentText()
        self.degree_edit.setVisible(f == "Polynomial")
        self.log_base_edit.setVisible(f == "Logarithmic")
        self.auto_guess_btn.setVisible(True)
        
        math_style = "font-size: 18px; font-family: Cambria, serif; font-style: italic;"
        eq_str = ""
        self.param_names = []
        param_labels = []
        
        if f == "Polynomial":
            try: deg = max(0, int(self.degree_edit.text()))
            except Exception: deg = 1
            terms = []
            for i in range(deg + 1):
                self.param_names.append(f"c{i}")
                param_labels.append(f"c<sub>{i}</sub>")
                power = deg - i
                if power == 0: terms.append(f"c<sub>{i}</sub>")
                elif power == 1: terms.append(f"c<sub>{i}</sub>x")
                else: terms.append(f"c<sub>{i}</sub>x<sup>{power}</sup>")
            eq_str = f"<span style='{math_style}'>y = " + " + ".join(terms) + "</span>"
            
        elif f == "Logarithmic":
            base = self.log_base_edit.text()
            if base.lower() == 'e': eq_str = f"<span style='{math_style}'>y = a &middot; ln(x) + c</span>"
            else: eq_str = f"<span style='{math_style}'>y = a &middot; log<sub>{base}</sub>(x) + c</span>"
            self.param_names, param_labels = ["a", "c"], ["a", "c"]
            
        elif f == "Exponential":
            eq_str = f"<span style='{math_style}'>y = a &middot; e<sup>bx</sup> + c</span>"
            self.param_names, param_labels = ["a", "b", "c"], ["a", "b", "c"]
            
        elif f == "Gaussian":
            eq_str = (f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2' align='center'>"
                      f"<tr><td rowspan='2' valign='middle'>y = A &middot; exp&nbsp;&nbsp;[ &minus;</td>"
                      f"<td align='center' style='border-bottom: 1px solid black;'>&nbsp;(x &minus; &mu;)<sup>2</sup>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>]</td></tr><tr><td align='center'>2&sigma;<sup>2</sup></td></tr></table>")
            self.param_names, param_labels = ["A", "mu", "sigma"], ["A", "&mu;", "&sigma;"]
            
        elif f == "Lorentzian":
            eq_str = (f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2' align='center'>"
                      f"<tr><td rowspan='2' valign='middle'>y = </td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;A&nbsp;</td></tr>"
                      f"<tr><td align='center'><table style='{math_style}' border='0' cellspacing='0' cellpadding='0'>"
                      f"<tr><td rowspan='2' valign='middle'>1 + &nbsp;[</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;x &minus; x<sub>0</sub>&nbsp;</td>"
                      f"<td rowspan='2' valign='middle'>]<sup>2</sup></td></tr><tr><td align='center'>&gamma;</td></tr></table></td></tr></table>")
            self.param_names, param_labels = ["A", "x0", "gamma"], ["A", "x<sub>0</sub>", "&gamma;"]
            
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
            
            val_edit = QLineEdit("")
            self.param_table.setCellWidget(i, 2, val_edit)
            
            self.param_edits[name] = {"mode": mode_cb, "val": val_edit}
            
    def run_auto_guess(self):
        res = self.parent_gui._get_all_plotted_xy()
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, _ = res
        
        f = self.func_combo.currentText()
        if f == "Gaussian" or f == "Lorentzian":
            self.param_edits["A"]["val"].setText(f"{y.max():.4g}")
            self.param_edits[self.param_names[1]]["val"].setText(f"{x.mean():.4g}")
            self.param_edits[self.param_names[2]]["val"].setText(f"{np.std(x):.4g}")
        elif f == "Polynomial":
            try: deg = int(self.degree_edit.text())
            except: return
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                smart_p0 = np.polyfit(x, y, deg)
            for i, p in enumerate(self.param_names):
                self.param_edits[p]["val"].setText(f"{smart_p0[i]:.4g}")
                
        elif f == "Logarithmic":
            try:
                base_str = self.log_base_edit.text()
                b = np.e if base_str.lower() == 'e' else float(base_str)
                # Failsafe: Only use strictly positive X values
                valid = x > 0
                if np.any(valid):
                    x_val, y_val = x[valid], y[valid]
                    # Transform X and run a linear regression
                    x_trans = np.log(x_val) / np.log(b)
                    slope, intercept = np.polyfit(x_trans, y_val, 1)
                    self.param_edits["a"]["val"].setText(f"{slope:.4g}")
                    self.param_edits["c"]["val"].setText(f"{intercept:.4g}")
            except Exception: pass
            
        elif f == "Exponential":
            try:
                # Failsafe: Guess the baseline slightly below the minimum Y to avoid log(0)
                c_guess = np.min(y) - 0.01 * abs(np.min(y))
                y_shifted = y - c_guess
                valid = y_shifted > 0
                if np.any(valid):
                    x_val, y_val = x[valid], y_shifted[valid]
                    # Linearise the exponential and fit
                    b_guess, ln_a_guess = np.polyfit(x_val, np.log(y_val), 1)
                    a_guess = np.exp(ln_a_guess)
                    
                    self.param_edits["a"]["val"].setText(f"{a_guess:.4g}")
                    self.param_edits["b"]["val"].setText(f"{b_guess:.4g}")
                    self.param_edits["c"]["val"].setText(f"{c_guess:.4g}")
            except Exception: pass

    def get_result(self):
        param_config = {}
        for p, controls in self.param_edits.items():
            try: val = float(controls["val"].text())
            except Exception: val = 1.0
            param_config[p] = {"mode": controls["mode"].currentText(), "value": val}
            
        return (
            self.func_combo.currentText(),
            self.degree_edit.text(),
            self.log_base_edit.text(),
            param_config
        )

    def load_state(self, state):
        type_map = {
            "polynomial": "Polynomial", 
            "logarithmic": "Logarithmic", 
            "exponential": "Exponential", 
            "gaussian": "Gaussian", 
            "lorentzian": "Lorentzian"
        }
        
        self.func_combo.setCurrentText(type_map.get(state["type"], "Polynomial"))
        
        if state["type"] == "polynomial":
            self.degree_edit.setText(str(state.get("degree", 1)))
        elif state["type"] == "logarithmic":
            self.log_base_edit.setText(str(state.get("base", "e")))
            
        param_config = state.get("param_config", {})
        for p, config in param_config.items():
            if p in self.param_edits:
                self.param_edits[p]["mode"].setCurrentText(config["mode"])
                self.param_edits[p]["val"].setText(f"{config['value']:.6g}")

class LocalWorker(QThread):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(int) # <--- NEW: Add progress signal

    def __init__(self, func, *args):
        super().__init__()
        self.func = func
        self.args = args

    def run(self):
        try:
            res = self.func(*self.args)
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))
            
def calculate_fit_statistics(y_data, y_calc, pcov, param_count, y_err=None):
    """Generates standard goodness-of-fit metrics for any model."""
    import numpy as np
    
    N = len(y_data)
    dof = max(1, N - param_count)
    residuals = y_data - y_calc
    rmse = np.sqrt(np.mean(residuals**2))

    # Calculate Chi-Squared
    if y_err is not None and np.any(y_err > 0):
        # Weighted by explicit experimental uncertainties
        safe_err = np.where(y_err > 0, y_err, np.inf)
        chi_sq = np.sum((residuals / safe_err)**2)
    else:
        # Unweighted (Sum of Squared Errors)
        chi_sq = np.sum(residuals**2)

    red_chi_sq = chi_sq / dof

    # Calculate parameter uncertainties from the covariance matrix
    param_errs = []
    if pcov is not None and not np.isinf(pcov).all() and not np.isnan(pcov).all():
        try:
            param_errs = np.sqrt(np.diag(pcov)).tolist()
        except Exception:
            param_errs = [float('nan')] * param_count
    else:
        param_errs = [float('nan')] * param_count

    return {
        "dof": dof,
        "chi_sq": chi_sq,
        "red_chi_sq": red_chi_sq,
        "rmse": rmse,
        "param_errs": param_errs
    }

class CommonFitWorker(QThread):
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int, str)
    error = pyqtSignal(str)

    def __init__(self, func_type, degree_text, log_base_text, param_config, x, y):
        super().__init__()
        self.func_type = func_type
        self.degree_text = degree_text
        self.log_base_text = log_base_text
        self.param_config = param_config
        self.x = x
        self.y = y

    def run(self):
        try:
            import numpy as np
            from scipy.optimize import curve_fit
            import warnings
            
            self.progress.emit(10, f"Initialising {self.func_type} model...")
            
            # 1. Internal Universal Fitter
            def execute_fit(base_model, param_names):
                free_params = []
                fixed_params = {}
                p0 = []
                for p in param_names:
                    if self.param_config[p]["mode"] == "Auto":
                        free_params.append(p)
                        p0.append(float(self.param_config[p]["value"]))
                    else:
                        fixed_params[p] = float(self.param_config[p]["value"])
                
                if not free_params:
                    # If all parameters are fixed, return empty stats and zero errors
                    res["stats"] = None
                    res["param_errs"] = [0.0] * len(param_names)
                    res["pcov"] = None # <--- ADD THIS
                    return [self.param_config[p]["value"] for p in param_names]
                    
                def dynamic_wrapper(x_val, *args):
                    kwargs = dict(fixed_params)
                    for name, val in zip(free_params, args):
                        kwargs[name] = val
                    full_args = [kwargs[p] for p in param_names]
                    return base_model(x_val, *full_args)
                    
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    # --- FIX: Capture pcov ---
                    popt, pcov = curve_fit(dynamic_wrapper, self.x, self.y, p0=p0, maxfev=20000)
                    
                final_params = []
                full_param_errs = []
                popt_idx = 0
                
                # Extract the uncertainties for the free parameters
                free_errs = []
                if pcov is not None and not np.isinf(pcov).all() and not np.isnan(pcov).all():
                    try: free_errs = np.sqrt(np.diag(pcov)).tolist()
                    except: free_errs = [float('nan')] * len(free_params)
                else:
                    free_errs = [float('nan')] * len(free_params)

                for p in param_names:
                    if p in free_params:
                        final_params.append(popt[popt_idx])
                        full_param_errs.append(free_errs[popt_idx])
                        popt_idx += 1
                    else:
                        final_params.append(fixed_params[p])
                        full_param_errs.append(0.0) # Fixed parameters have 0 uncertainty
                
                # Defer the heavy stats, but keep the covariance errors
                res["stats"] = None
                res["param_errs"] = full_param_errs 
                res["pcov"] = pcov # <--- ADD THIS
                
                return final_params

            self.progress.emit(25, "Setting up mathematical equations...")

            # 2. Define the requested model
            res = {"type_key": self.func_type.lower()}
            
            if self.func_type == "Polynomial":
                degree = int(self.degree_text)
                param_names = [f"c{i}" for i in range(degree + 1)]
                
                if all(self.param_config[p]["mode"] == "Auto" and self.param_config[p]["value"] == 1.0 for p in param_names):
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore')
                        smart_p0 = np.polyfit(self.x, self.y, degree)
                    for i, p in enumerate(param_names): self.param_config[p]["value"] = smart_p0[i]
                        
                def model(x_val, *args):
                    return sum(c * (x_val**(degree-i)) for i, c in enumerate(args))
                
                self.progress.emit(40, "Running non-linear optimiser...")
                final_params = execute_fit(model, param_names)
                
                poly = np.poly1d(final_params)
                res["callable"] = poly
                res["equation"] = "y = " + " + ".join(f"{c:.3g}x^{i}" for i, c in enumerate(final_params[::-1]))
                res["display_name"] = f"Poly (deg {degree})"
                res["degree"] = degree
                res["coeffs"] = final_params

            elif self.func_type == "Logarithmic":
                base = np.e if self.log_base_text.lower() == "e" else float(self.log_base_text)
                def model(x_val, a, c): return a * np.log(x_val) / np.log(base) + c
                param_names = ["a", "c"]
                
                self.progress.emit(40, "Running non-linear optimiser...")
                final_params = execute_fit(model, param_names)
                res["callable"] = lambda v: model(v, *final_params)
                res["display_name"] = "Logarithmic"
                res["base"] = self.log_base_text
                
            elif self.func_type == "Exponential":
                def model(x_val, a, b, c): return a * np.exp(b * x_val) + c
                param_names = ["a", "b", "c"]
                self.progress.emit(40, "Running non-linear optimiser...")
                final_params = execute_fit(model, param_names)
                res["callable"] = lambda v: model(v, *final_params)
                res["display_name"] = "Exponential"
                
            elif self.func_type == "Gaussian":
                def model(x_val, A, mu, sigma): return A * np.exp(-(x_val - mu)**2 / (2 * sigma**2))
                param_names = ["A", "mu", "sigma"]
                
                target_idx = np.argmax(self.y) if abs(self.y.max() - self.y.mean()) > abs(self.y.min() - self.y.mean()) else np.argmin(self.y)
                peak_x = self.x[target_idx]
                
                if self.param_config["A"]["mode"] == "Auto" and self.param_config["A"]["value"] == 1.0: self.param_config["A"]["value"] = self.y.max()
                if self.param_config["mu"]["mode"] == "Auto" and self.param_config["mu"]["value"] == 1.0: self.param_config["mu"]["value"] = peak_x
                if self.param_config["sigma"]["mode"] == "Auto" and self.param_config["sigma"]["value"] == 1.0: self.param_config["sigma"]["value"] = np.std(self.x)

                self.progress.emit(40, "Running non-linear optimiser...")
                final_params = execute_fit(model, param_names)
                res["callable"] = lambda v: model(v, *final_params)
                res["display_name"] = "Gaussian"
                
            elif self.func_type == "Lorentzian":
                def model(x_val, A, x0, gamma): return A / (1 + ((x_val - x0) / gamma)**2)
                param_names = ["A", "x0", "gamma"]
                
                target_idx = np.argmax(self.y) if abs(self.y.max() - self.y.mean()) > abs(self.y.min() - self.y.mean()) else np.argmin(self.y)
                peak_x = self.x[target_idx]
                
                if self.param_config["A"]["mode"] == "Auto" and self.param_config["A"]["value"] == 1.0: self.param_config["A"]["value"] = self.y.max()
                if self.param_config["x0"]["mode"] == "Auto" and self.param_config["x0"]["value"] == 1.0: self.param_config["x0"]["value"] = peak_x
                if self.param_config["gamma"]["mode"] == "Auto" and self.param_config["gamma"]["value"] == 1.0: self.param_config["gamma"]["value"] = np.std(self.x)

            # 3. Generate High-Res Curve
            self.progress.emit(80, "Generating high-resolution plot curve...")
            x_min = max(1e-15, self.x.min()) if self.func_type == "Logarithmic" else self.x.min()
            xfit = np.linspace(x_min, self.x.max(), 500)
            
            # Use the generated callable
            yfit = res["callable"](xfit)
            
            # Sanitize to prevent OpenGL/PyQtGraph crashes
            y_max, y_min = np.nanmax(self.y), np.nanmin(self.y)
            y_span = abs(y_max - y_min) or 1.0
            safe_max = y_max + (y_span * 50)
            safe_min = y_min - (y_span * 50)
            
            yfit = np.nan_to_num(yfit, nan=0.0, posinf=safe_max, neginf=safe_min)
            yfit = np.clip(yfit, safe_min, safe_max)

            self.progress.emit(95, "Snapping to canvas...")
            res["xfit"] = xfit
            res["yfit"] = yfit
            res["params"] = final_params
            res["param_names"] = param_names
            
            self.finished.emit(res)
            
        except Exception as e:
            self.error.emit(str(e))

class CustomFitDialog(QDialog):
    def __init__(self, dataset, parent_gui):
        super().__init__(parent_gui)
        self.setWindowTitle("Fit Custom Function")
        self.resize(750, 650)
        self.dataset = dataset
        self.parent_gui = parent_gui 
        self.available_columns = dataset.column_names
        self.parameters = []
        self.is_valid = False
        self.used_cols = []
        self.parsed_equation = ""
        self.html_equation = ""

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>1. Insert Variables & Columns:</b>"))
        btn_layout = QHBoxLayout()
        
        btn_x = QPushButton("x (Independent Variable)")
        btn_x.setStyleSheet(f"color: {theme.danger_text}; font-weight: bold; border: 1px solid {theme.danger_border}; padding: 4px;")
        btn_x.clicked.connect(lambda: self.equation_input.textCursor().insertText("x"))
        btn_layout.addWidget(btn_x)
        
        self.const_btn = QPushButton("✨ Physics Constants")
        self.const_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; border: 1px solid {theme.success_border}; padding: 4px;")
        self.const_btn.clicked.connect(self.open_constants)
        btn_layout.addWidget(self.const_btn)
        layout.addLayout(btn_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(100)
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
        scroll.setWidget(col_container)
        layout.addWidget(scroll)

        layout.addWidget(QLabel("<b>2. Create Parameters to Optimize:</b>"))
        param_creator_layout = QHBoxLayout()
        self.new_param_edit = QLineEdit()
        self.new_param_edit.setPlaceholderText("e.g. A, tau, omega, alpha")
        add_param_btn = QPushButton("Add Parameter")
        add_param_btn.clicked.connect(self.add_parameter)
        param_creator_layout.addWidget(self.new_param_edit)
        param_creator_layout.addWidget(add_param_btn)
        layout.addLayout(param_creator_layout)

        # --- NEW: Vertical Scroll Area for Parameters ---
        self.param_scroll = QScrollArea()
        self.param_scroll.setWidgetResizable(True)
        self.param_scroll.setMinimumHeight(120) 
        self.param_scroll.setMaximumHeight(200) # Stop it from taking over the screen
        
        self.param_scroll_widget = QWidget()
        self.param_btn_layout = QVBoxLayout(self.param_scroll_widget)
        self.param_btn_layout.setAlignment(Qt.AlignTop) 
        
        self.param_scroll.setWidget(self.param_scroll_widget)
        layout.addWidget(self.param_scroll)
        # ------------------------------------------------

        math_lbl_layout = QHBoxLayout()
        math_lbl_layout.addWidget(QLabel("<b>3. Equation:</b> <i>(+, -, *, /, ^, sin(), exp()...)</i>"))
        math_lbl_layout.addStretch()
        
        # --- NEW: Template Injector Dropdown ---
        self.template_combo = QComboBox()
        self.template_combo.addItems(["Template...", "Gaussian", "Lorentzian", "Sine Wave", "Nth Order Polynomial"])
        self.template_combo.activated.connect(self.apply_template)
        math_lbl_layout.addWidget(self.template_combo)
        # ---------------------------------------
        
        self.load_func_btn = QPushButton("📂 Load Saved Function")
        self.load_func_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 4px 10px;")
        self.load_func_btn.clicked.connect(self.load_custom_function)
        math_lbl_layout.addWidget(self.load_func_btn)
        
        layout.addLayout(math_lbl_layout)
        
        self.equation_input = QTextEdit()
        # --- NEW: Horizontal scrolling for long equations ---
        self.equation_input.setLineWrapMode(QTextEdit.NoWrap) 
        self.equation_input.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # ----------------------------------------------------
        self.equation_input.setMaximumHeight(80)
        self.equation_input.setFont(pg.QtGui.QFont("Consolas", 11))
        self.equation_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.equation_input)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"background-color: {theme.panel_bg}; color: {theme.fg}; border: 1px solid {theme.border}; font-size: 22px; font-family: Cambria, serif; font-style: italic; padding: 10px;")
        
        # --- NEW: Scroll Area for the Live Preview ---
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setWidget(self.preview_label) # <-- Fixed variable name
        self.preview_scroll.setMinimumHeight(100)
        self.preview_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(self.preview_scroll)
        # ---------------------------------------------

        layout.addWidget(QLabel("<b>4. Parameter Settings:</b>"))
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(3)
        self.param_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Value / Guess"])
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.param_table.verticalHeader().setVisible(False)
        layout.addWidget(self.param_table)

        # --- NEW INTERACTIVE BUTTONS ---
        btn_box = QHBoxLayout()
        
        # --- NEW INTERACTIVE BUTTONS ---
        btn_box = QHBoxLayout()
        
        self.auto_guess_btn = QPushButton("✨ Auto-Guess Values")
        self.auto_guess_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; padding: 6px;")
        self.auto_guess_btn.clicked.connect(self.run_auto_guess)
        self.auto_guess_btn.setEnabled(False) 
        
        self.optimize_btn = QPushButton("Optimize Parameters")
        self.optimize_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.optimize_btn.clicked.connect(self.run_optimization)
        self.optimize_btn.setEnabled(False)
        
        # --- FIX 2: ADD STOP BUTTON ---
        self.stop_opt_btn = QPushButton("⏹ Stop Optimization")
        self.stop_opt_btn.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; padding: 6px;")
        self.stop_opt_btn.clicked.connect(self.stop_optimization)
        self.stop_opt_btn.setVisible(False)
        # ------------------------------
        
        self.done_btn = QPushButton("Done")
        self.done_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        self.done_btn.clicked.connect(self.handle_done)
        self.done_btn.setEnabled(False) 
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addWidget(self.auto_guess_btn)
        btn_box.addWidget(self.optimize_btn)
        btn_box.addWidget(self.stop_opt_btn) # Inserted into layout
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.done_btn)
        layout.addLayout(btn_box)
        
        self.param_configs = {}
        self._swarm_count = 0 # Tracks if we should use Global or Targeted bounds
        
    def apply_template(self):
        template_name = self.template_combo.currentText()
        if template_name == "Template...": return

        if template_name == "Nth Order Polynomial":
            from PyQt5.QtWidgets import QInputDialog
            # Pop up a dialog asking for the degree (default 2, min 1, max 100)
            deg, ok = QInputDialog.getInt(self, "Polynomial Degree", "Enter polynomial degree (n):", 2, 1, 100)
            if not ok:
                self.template_combo.setCurrentIndex(0)
                return
                
            # Generator for Excel-style parameter names (A, B... Z, AA, AB...)
            def get_excel_col(index):
                name = ""
                while index >= 0:
                    name = chr((index % 26) + 65) + name
                    index = (index // 26) - 1
                return name

            params = ["X_norm"] # <--- NEW: Inject the normalisation constant
            terms = []
            for i in range(deg + 1):
                p_name = get_excel_col(i)
                params.append(p_name)
                power = deg - i
                
                if power == 0:
                    terms.append(f"{{{p_name}}}")
                elif power == 1:
                    terms.append(f"{{{p_name}}} * (x / {{X_norm}})")
                else:
                    terms.append(f"{{{p_name}}} * (x / {{X_norm}})^{power}")
                    
            data = {
                "eq": " + ".join(terms),
                "params": params
            }
            
        else:
            # Standard templates
            templates = {
                "Gaussian": {
                    "eq": "{A} * exp(-(((x - {mu})^2) / (2 * {sigma}^2))) + {C}",
                    "params": ["A", "mu", "sigma", "C"]
                },
                "Lorentzian": {
                    "eq": "{A} / (1 + ((x - {x0})/{gamma})^2) + {C}",
                    "params": ["A", "x0", "gamma", "C"]
                },
                "Sine Wave": {
                    "eq": "{A} * sin({omega} * x + {phi}) + {C}",
                    "params": ["A", "omega", "phi", "C"]
                }
            }
            if template_name not in templates: return
            data = templates[template_name]

        self.suspend_updates = True 

        # 1. Deep clean the UI and memory
        self.parameters.clear()
        self.param_table.setRowCount(0)
        self.param_configs.clear()
        
        while self.param_btn_layout.count():
            child = self.param_btn_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.equation_input.blockSignals(True)
        self.equation_input.clear()

        # 2. Inject new parameters
        for p_name in data["params"]:
            self.new_param_edit.setText(p_name)
            self.add_parameter()
            # --- NEW: Lock the normalisation constant so the optimiser ignores it ---
            if p_name == "X_norm":
                self.param_configs[p_name]["mode"].setCurrentText("Manual")
            # ------------------------------------------------------------------------

        # 3. Inject equation
        self.equation_input.setPlainText(data["eq"])
        self.template_combo.setCurrentIndex(0)
        
        self.suspend_updates = False
        self.equation_input.blockSignals(False)
        self.update_preview()

    def load_custom_function(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        fname, _ = QFileDialog.getOpenFileName(self, "Load Saved Function", "", "Text files (*.txt)")
        if not fname: return
        
        with open(fname, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
            
        if not lines: return

        # --- FIX: Parse the stats block into memory before truncating! ---
        parsed_stats = None
        stats_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("### STATS ###"):
                stats_idx = i
                break
                
        if stats_idx != -1:
            stats_lines = lines[stats_idx+1:]
            lines = lines[:stats_idx]
            parsed_stats = {}
            for sl in stats_lines:
                if ":" in sl:
                    k, v = sl.split(":", 1)
                    k, v = k.strip(), v.strip()
                    if k == "param_errs":
                        parsed_stats[k] = [float(x) if x != "NaN" else float('nan') for x in v.split(",")]
                    else:
                        try: parsed_stats[k] = float(v)
                        except: pass
            
        self.latest_stats = parsed_stats
        # -----------------------------------------------------------------

        type_line = lines[0].lower()
        
        # 1. 3D Gatekeeper
        if type_line.startswith("3d:"):
            QMessageBox.warning(self, "Format Mismatch", "This is a 3D surface function and cannot be loaded into the 2D custom fitter.")
            return

        # 2. Deep clean the UI
        self.parameters.clear()
        self.param_table.setRowCount(0)
        self.param_configs.clear()
        
        while self.param_btn_layout.count():
            child = self.param_btn_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.equation_input.blockSignals(True)
        self.equation_input.clear()

        try:
            # 3. Universal Translator Engine
            if type_line == "custom":
                raw_eq = lines[1]
                param_names = [p.strip() for p in lines[2].split(",") if p.strip()] if len(lines) > 2 else []
                param_vals = [float(v) for v in lines[3:]] if len(lines) > 3 else []
                
            elif type_line == "polynomial":
                deg = int(lines[1].split(":")[1].strip())
                param_vals = [float(x) for x in lines[2:]]
                param_names = [f"c{i}" for i in range(deg + 1)]
                terms = []
                for i in range(deg + 1):
                    power = deg - i
                    if power == 0: terms.append(f"{{c{i}}}")
                    elif power == 1: terms.append(f"{{c{i}}}*x")
                    else: terms.append(f"{{c{i}}}*x^{power}")
                raw_eq = " + ".join(terms)

            elif type_line == "logarithmic":
                base = lines[1].split(":")[1].strip()
                param_vals = [float(x) for x in lines[2:]]
                param_names = ["a", "c"]
                if base.lower() == 'e': raw_eq = "{a} * ln(x) + {c}"
                else: raw_eq = f"{{a}} * log_{base}(x) + {{c}}"

            elif type_line == "exponential":
                param_vals = [float(x) for x in lines[1:]]
                param_names = ["a", "b", "c"]
                raw_eq = "{a} * exp({b}*x) + {c}"

            elif type_line == "gaussian":
                param_vals = [float(x) for x in lines[1:]]
                param_names = ["A", "mu", "sigma"]
                if len(param_vals) > 3: 
                    param_names.append("C")
                    raw_eq = "{A} * exp(-(((x - {mu})^2) / (2 * {sigma}^2))) + {C}"
                else:
                    raw_eq = "{A} * exp(-(((x - {mu})^2) / (2 * {sigma}^2)))"

            elif type_line == "lorentzian":
                param_vals = [float(x) for x in lines[1:]]
                param_names = ["A", "x0", "gamma"]
                if len(param_vals) > 3:
                    param_names.append("C")
                    raw_eq = "{A} / (1 + ((x - {x0})/{gamma})^2) + {C}"
                else:
                    raw_eq = "{A} / (1 + ((x - {x0})/{gamma})^2)"
                    
            elif type_line == "harmonic" or type_line == "sine wave":
                param_vals = [float(x) for x in lines[1:]]
                param_names = ["A", "omega", "phi", "C"]
                raw_eq = "{A} * sin({omega} * x + {phi}) + {C}"

            else:
                QMessageBox.warning(self, "Invalid File", f"Unrecognised function format: {type_line}")
                self.equation_input.blockSignals(False)
                return

            self.equation_input.setPlainText(raw_eq)
            
            # 4. Inject the translated components into the UI
            for i, p_name in enumerate(param_names):
                self.new_param_edit.setText(p_name)
                self.add_parameter()
                if i < len(param_vals) and p_name in self.param_configs:
                    self.param_configs[p_name]["mode"].setCurrentText("Manual") 
                    self.param_configs[p_name]["val"].setText(f"{param_vals[i]:.6g}")
                    
            self.equation_input.blockSignals(False)
            self.update_preview()
            self._check_boxes_filled()
            
        except Exception as e:
            self.equation_input.blockSignals(False)
            QMessageBox.critical(self, "Load Error", f"Failed to parse function file:\n{e}")

    def load_state(self, state):
        self.equation_input.setPlainText(state.get("raw_equation", ""))
        param_config = state.get("param_config", {})
        
        for p in state.get("param_names", []):
            self.new_param_edit.setText(p)
            self.add_parameter() 
            if p in self.param_configs and p in param_config:
                self.param_configs[p]["mode"].setCurrentText(param_config[p]["mode"])
                self.param_configs[p]["val"].setText(f"{param_config[p]['value']:.6g}")
                
        self.update_preview()

    def _check_boxes_filled(self):
        if getattr(self, 'suspend_updates', False): return
        if not getattr(self, 'is_valid', False) or not self.parameters:
            self.optimize_btn.setEnabled(False)
            self.auto_guess_btn.setEnabled(False)
            self.done_btn.setEnabled(False) # Lock if invalid
            return
            
        self.auto_guess_btn.setEnabled(True)
        
        all_filled = True
        for controls in self.param_configs.values():
            if not controls["val"].text().strip():
                all_filled = False
                break
                
        self.optimize_btn.setEnabled(all_filled)
        if all_filled:
            self._draw_live_preview()
        else:
            self.done_btn.setEnabled(False)
            
    def run_auto_guess(self):
        # --- NEW: Router Logic ---
        if getattr(self, '_swarm_count', 0) > 0:
            self.run_global_search()
            return
        # -------------------------
        
        import numpy as np
        if not self.is_valid or not self.parameters: return
        
        res = self.parent_gui._get_all_plotted_xy(aux_cols=self.used_cols, apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, _ = res

        # 1. Calculate the physical scale of the data
        y_max, y_min = np.max(y), np.min(y)
        y_ptp = y_max - y_min
        y_mean = np.mean(y)
        
        # --- FIX: Find the actual X coordinate of the peak ---
        target_idx = np.argmax(y) if abs(y_max - y_mean) > abs(y_min - y_mean) else np.argmin(y)
        x_peak = x[target_idx]
        x_std = np.std(x) if np.std(x) != 0 else 1.0
        # -----------------------------------------------------

        # --- FIX 1: Suspend live updates while we fill the boxes! ---
        self.suspend_updates = True

        # 2. Smart Heuristic Mapping
        for p in self.parameters:
            is_auto = self.param_configs[p]["mode"].currentText() == "Auto"
            p_lower = p.lower()
            
            # --- FIX: Allow X_norm to be populated even if it is locked to Manual ---
            if not is_auto and p_lower != 'x_norm':
                continue
            
            # Amplitude / Scaling parameters
            if p_lower in ['a', 'amp', 'amplitude']: guess = y_max if y_min >= 0 else y_ptp / 2.0
            # Offset / Baseline parameters
            elif p_lower in ['c', 'y0', 'offset', 'base', 'baseline']: guess = y_min if y_min > 0 else y_mean
            # X-Shift / Center parameters
            elif p_lower in ['x0', 'mu', 'center', 'xc', 'shift']: guess = x_peak
            # Width / Time-constant parameters
            elif p_lower in ['w', 'width', 'sigma', 'tau', 'gamma']: guess = x_std
            # Frequency parameters
            elif p_lower in ['b', 'freq', 'frequency', 'omega']: guess = 1.0 / x_std if x_std != 0 else 1.0
            
            # --- NEW: Catch the normalisation constant ---
            elif p_lower == 'x_norm': guess = np.max(np.abs(x)) if np.max(np.abs(x)) != 0 else 1.0
            # ---------------------------------------------
            
            elif len(p_lower) <= 2: 
                guess = 0.0 # Prevents X^100 from causing an instant mathematical overflow!
            # Absolute fallback
            else:
                guess = 1.0
                
            # Safely inject the deterministic guess into the UI box
            self.param_configs[p]["val"].blockSignals(True)
            self.param_configs[p]["val"].setText(f"{guess:.4g}")
            self.param_configs[p]["val"].blockSignals(False)

        # --- FIX 3: Resume updates and trigger exactly ONE redraw ---
        self.suspend_updates = False
        self._draw_live_preview()
        self._check_boxes_filled()

    def _draw_live_preview(self):
        if not self.is_valid or not self.parameters: return
        
        param_vals = []
        for p in self.parameters:
            try: 
                param_vals.append(float(self.param_configs[p]["val"].text()))
            except ValueError:
                return # Abort drawing temporarily if they type a invalid character (like '-')
                
        res = self.parent_gui._get_all_plotted_xy(aux_cols=self.used_cols, apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0: return
        x_full, y_full, aux_dict, _ = res
        
        import numpy as np
        sort_idx = np.argsort(x_full)
        x_sorted = x_full[sort_idx]
        
        # --- FIX: Generate a high-resolution array for a smooth live preview ---
        from scipy.interpolate import make_interp_spline
        x_unique, unique_idx = np.unique(x_sorted, return_index=True)
        
        if len(x_unique) < 2: return
        xfit = np.linspace(x_unique[0], x_unique[-1], 500)
        
        safe_dict = aux_dict if aux_dict is not None else {}
        smooth_aux = {}
        for c in self.used_cols:
            arr = safe_dict.get(c, np.zeros_like(x_full))
            y_unq = arr[sort_idx][unique_idx]
            if len(x_unique) > 3:
                spline = make_interp_spline(x_unique, y_unq, k=3)
                smooth_aux[c] = spline(xfit)
            else:
                smooth_aux[c] = np.interp(xfit, x_unique, y_unq)
        # -----------------------------------------------------------------------
        
        def norm_func(v):
            arr = np.asarray(v, dtype=np.float64)
            m = np.max(arr)
            return arr / m if m != 0 else arr
            
        env = {"np": np, "e": np.e, "pi": np.pi, "x": xfit, "data_dict": smooth_aux, "norm": norm_func}
        for i, p in enumerate(self.parameters): env[p] = param_vals[i]
        
        try:
            yfit = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
            if yfit.ndim == 0:
                yfit = np.full_like(xfit, float(yfit))
            
            # --- SMART CLIP: Keep numbers relative to screen size ---
            y_max, y_min = np.nanmax(y_full), np.nanmin(y_full)
            y_span = abs(y_max - y_min) or 1.0
            safe_max = y_max + (y_span * 50)
            safe_min = y_min - (y_span * 50)
            
            yfit = np.nan_to_num(yfit, nan=0.0, posinf=safe_max, neginf=safe_min)
            yfit = np.clip(yfit, safe_min, safe_max)
            # -------------------------------------------------------
            
            import pyqtgraph as pg
            from PyQt5.QtCore import Qt
            
            if not hasattr(self.parent_gui, 'phantom_curve'):
                # --- FIX: Enable hardware clipping to stop dashed line lag ---
                self.parent_gui.phantom_curve = pg.PlotCurveItem(
                    pen=pg.mkPen("m", width=3, style=Qt.DotLine),
                    clipToView=True, autoDownsample=True
                )
                self.parent_gui.plot_widget.addItem(self.parent_gui.phantom_curve)
                # -------------------------------------------------------------
            
            self.parent_gui.phantom_curve.setData(xfit, yfit)
            self.parent_gui.phantom_curve.setVisible(True)
            self.done_btn.setEnabled(True) 
            
        except Exception as e:
            self.done_btn.setEnabled(False)
            pass

    def run_optimization(self):
        if not self.is_valid or not self.parameters: return
        self._is_optimizing = True
        self._opt_cycles = 0 # <--- Set counter to 0
        
        self.optimize_btn.setVisible(False)
        self.stop_opt_btn.setVisible(True)
        self.done_btn.setEnabled(False)
        self.auto_guess_btn.setEnabled(False)
        
        self._run_opt_step()

    def stop_optimization(self):
        self._is_optimizing = False
        self.optimize_btn.setVisible(True)
        self.stop_opt_btn.setVisible(False)
        self.done_btn.setEnabled(True)
        self.auto_guess_btn.setEnabled(True)

    def _run_opt_step(self):
        if not getattr(self, '_is_optimizing', False): return
            
        import numpy as np
        res = self.parent_gui._get_all_plotted_xy(aux_cols=self.used_cols, apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: 
            self.stop_optimization()
            return
            
        x, y, aux_dict, _ = res
        safe_dict = aux_dict if aux_dict is not None else {}
        aux_calc = {c: np.asarray(safe_dict.get(c, np.zeros_like(x))) for c in self.used_cols}

        param_config = {}
        old_vals = []
        for p, controls in self.param_configs.items():
            try: val = float(controls["val"].text())
            except: val = 1.0
            param_config[p] = {"mode": controls["mode"].currentText(), "value": val}
            if controls["mode"].currentText() == "Auto":
                old_vals.append(val)

        def norm_func(v):
            arr = np.asarray(v, dtype=np.float64)
            m = np.max(arr)
            return arr / m if m != 0 else arr

        def custom_model(x_val, *args):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "data_dict": aux_calc, "norm": norm_func}
            for i, p in enumerate(self.parameters): env[p] = args[i]
            with np.errstate(all='ignore'):
                res_arr = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
            res_arr[~np.isfinite(res_arr)] = 1e12 
            return res_arr
            
        # Spawn the thread
        self.opt_worker = LocalWorker(self.parent_gui._execute_universal_fit, custom_model, self.parameters, param_config, x, y)
        
        def on_success(result):
            final_params, pcov = result
            self.latest_pcov = pcov  # Save the raw matrix
            self._opt_cycles += 1
            
            new_vals = []
            for i, p in enumerate(self.parameters):
                if self.param_configs[p]["mode"].currentText() == "Auto":
                    new_vals.append(final_params[i])
                    self.param_configs[p]["val"].blockSignals(True)
                    self.param_configs[p]["val"].setText(f"{final_params[i]:.6g}")
                    self.param_configs[p]["val"].blockSignals(False)
            
            self._draw_live_preview()
            
            # 1. Check for mathematical convergence
            if old_vals and np.allclose(old_vals, new_vals, rtol=1e-5):
                self.stop_optimization()
                QMessageBox.information(self, "Optimization Complete", "The parameters have converged on the optimal fit.")
                
            # 2. Check if we hit the patience limit
            elif self._opt_cycles >= 30:
                self.stop_optimization()
                self._swarm_count = 1 # Force the next swarm to be Localised
                self.auto_guess_btn.setText("✨ Targeted Swarm (Local)")
                QMessageBox.warning(self, "Optimization Halted", "The local solver has reached its maximum iteration limit without fully converging.\n\nTry clicking 'Targeted Swarm (Local)' to dynamically bump the parameters out of this local trap!")
                
            # 3. Otherwise, keep looping
            elif getattr(self, '_is_optimizing', False):
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(10, self._run_opt_step)
                
        def on_err(err_str):
            self.stop_optimization()
            QMessageBox.critical(self, "Failed", f"Math Error or Failed Convergence.\n\nDetails: {err_str}")

        self.opt_worker.finished.connect(on_success)
        self.opt_worker.error.connect(on_err)
        self.opt_worker.start()

    def open_constants(self):
        dlg = ConstantsDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_key:
            self.equation_input.textCursor().insertText(f"{{\\{dlg.selected_key}}}")

    def add_parameter(self):
        p = self.new_param_edit.text().strip()
        if not p or not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', p): return
        if p in ["x", "e", "pi", "np", "sin", "cos", "tan", "exp", "log", "ln"]: return
        if p in self.parameters: return
        
        self.parameters.append(p)
        self.new_param_edit.clear()
        
        display_name = GREEK_MAP.get(p, p)
        btn = QPushButton(f"{{{display_name}}}")
        btn.setStyleSheet(f"color: {theme.warning_text}; font-weight: bold; border: 1px solid {theme.warning_border}; padding: 4px;")
        btn.clicked.connect(lambda checked, n=p: self.equation_input.textCursor().insertText(f"{{{n}}}"))
        self.param_btn_layout.addWidget(btn)
        
        row = self.param_table.rowCount()
        self.param_table.insertRow(row)
        
        lbl = QLabel(display_name)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"font-weight: bold; color: {theme.warning_text}; font-size: 16px;")
        self.param_table.setCellWidget(row, 0, lbl)
        
        mode_cb = QComboBox()
        mode_cb.addItems(["Auto", "Manual"])
        self.param_table.setCellWidget(row, 1, mode_cb)
        
        val_edit = QLineEdit("") 
        val_edit.textChanged.connect(self._check_boxes_filled)
        self.param_table.setCellWidget(row, 2, val_edit)
        
        self.param_configs[p] = {"mode": mode_cb, "val": val_edit}
        self.update_preview()
        self._check_boxes_filled()

    def validate_equation(self, raw_text):
        import re
        import numpy as np
        py_equation = raw_text
        self.used_cols = []
        col_map = {v: k for k, v in self.available_columns.items()}
        dummy_dict = {}
        
        def replace_col(match):
            name = match.group(1)
            if name not in col_map: raise ValueError()
            idx = col_map[name]
            if idx not in self.used_cols: self.used_cols.append(idx)
            dummy_dict[idx] = np.ones(1)
            return f"data_dict[{idx}]"
            
        try: py_equation = re.sub(r'\[(.*?)\]', replace_col, py_equation)
        except ValueError: return False, ""

        def replace_const_silent(match):
            c_key = match.group(1)
            if c_key in PHYSICS_CONSTANTS: return f"({PHYSICS_CONSTANTS[c_key]['value']})"
            else: raise ValueError()
            
        try: py_equation = re.sub(r'\{\\(.*?)\}', replace_const_silent, py_equation)
        except ValueError: return False, ""

        def replace_param_silent(match):
            p_key = match.group(1)
            if p_key in self.parameters: 
                # --- CRITICAL FIX: Leave it as a dynamic string keyword! ---
                return p_key 
            else: raise ValueError()
            
        try: py_equation = re.sub(r'\{(.*?)\}', replace_param_silent, py_equation)
        except ValueError: return False, ""

        py_equation = py_equation.replace('^', '**')
        # Add 'abs' to the end of this list:
        math_funcs = ['arcsinh','arccosh','arctanh','arcsin','arccos','arctan','sinh','cosh','tanh','sin','cos','tan', 'abs']
        for f in math_funcs:
            py_equation = re.sub(r'\b' + f + r'\s*\(', 'np.'+f+'(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?2\s*\(', 'np.log2(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bexp\s*\(', 'np.exp(', py_equation, flags=re.IGNORECASE)

        def norm_func(v):
            arr = np.asarray(v, dtype=np.float64)
            m = np.max(arr)
            return arr / m if m != 0 else arr

        try:
            env = {"np": np, "data_dict": dummy_dict, "e": np.e, "pi": np.pi, "x": np.ones(1), "norm": norm_func}
            for p in self.parameters: env[p] = 1.0 # Feed dummy values for validation only
            with np.errstate(all='ignore'):
                eval(py_equation, {"__builtins__": {}}, env)
            return True, py_equation
        except Exception: return False, py_equation

    def update_preview(self):
        if getattr(self, 'suspend_updates', False): return
        
        # --- NEW: Reset swarm tracker when equation changes ---
        self._swarm_count = 0
        if hasattr(self, 'auto_guess_btn'):
            self.auto_guess_btn.setText("✨ Auto-Guess (Global Search)")
        # ----------------------------------------------------
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
                c_html = PHYSICS_CONSTANTS[c_key]["html"]
                span = f"<span style='color: {theme.success_text}; font-weight: bold; font-style: normal;'>{c_html}</span>"
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

        xvars = []
        def x_repl(m):
            xvars.append(f"<span style='color: {theme.danger_text}; font-weight: bold; font-style: italic;'>x</span>")
            return f"__XVAR{len(xvars)-1}__"
        html_text = re.sub(r'\bx\b', x_repl, html_text)
        
        html_text = html_text.replace('*', '&middot;').replace('-', '&minus;')
        html_text = re.sub(r'\bpi\b', 'π', html_text) 
        
        funcs = []
        def func_repl(m):
            func = m.group(1).lower()
            func = re.sub(r'_?([0-9]+)', r"<sub style='font-size:12px;'>\1</sub>", func)
            funcs.append(f"<span style='font-style: normal; font-weight: bold; color: {theme.fg};'>{func}</span>")
            return f"__FUNC{len(funcs)-1}__"

        def tokenize_to_horizontal(text, f_size):
            parts = re.split(r'(__COL\d+__|__FUNC\d+__|__PAREN\d+__|__EXP\d+__|__CONST\d+__|__PARAM\d+__|__XVAR\d+__)', text)
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
                match = re.search(r'([a-zA-Zπ]+|[0-9\.]+|__COL\d+__|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__PARAM\d+__|__XVAR\d+__)\s*\^\s*(-?[a-zA-Zπ]+|-?[0-9\.]+|__COL\d+__|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__PARAM\d+__|__XVAR\d+__)', text)
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
            if not re.search(r'__(EXP|PAREN|FUNC|COL|CONST|PARAM|XVAR)\d+__', html_text): break
            for i in range(len(exps)): html_text = html_text.replace(f"__EXP{i}__", exps[i])
            for i in range(len(parens)): html_text = html_text.replace(f"__PAREN{i}__", parens[i])
            for i in range(len(funcs)): html_text = html_text.replace(f"__FUNC{i}__", funcs[i])
            for i in range(len(consts)): html_text = html_text.replace(f"__CONST{i}__", consts[i])
            for i in range(len(params_html)): html_text = html_text.replace(f"__PARAM{i}__", params_html[i])
            for i in range(len(xvars)): html_text = html_text.replace(f"__XVAR{i}__", xvars[i])
            for i in range(len(cols)): html_text = html_text.replace(f"__COL{i}__", f"<span style='color: {theme.primary_text}; font-weight: bold;'>{cols[i]}</span>")
            
        self.html_equation = html_text
        self.preview_label.setText(html_text)
        self._check_boxes_filled()

    def run_global_search(self):
        import numpy as np
        from PyQt5.QtWidgets import QProgressDialog, QMessageBox
        
        if not self.is_valid or not self.parameters: return
        
        res = self.parent_gui._get_all_plotted_xy(aux_cols=self.used_cols, apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, aux_dict, _ = res

        if aux_dict is None: aux_dict = {}
        safe_aux = {}
        for c in self.used_cols:
            if c in aux_dict and aux_dict[c] is not None:
                safe_aux[c] = np.asarray(aux_dict[c], dtype=np.float64)
            else:
                safe_aux[c] = np.zeros_like(x)

        # 1. Setup the UI Percentage Bar
        self.swarm_progress = QProgressDialog("Running Swarm Search... This may take a while.", "Cancel", 0, 100, self)
        self.swarm_progress.setWindowTitle("Swarming")
        self.swarm_progress.setModal(True)
        self.swarm_progress.setMinimumDuration(0)
        self.swarm_progress.setValue(0)

        def norm_func(v):
            arr = np.asarray(v, dtype=np.float64)
            m = np.max(np.abs(arr)) # Absolute max to bound between -1 and 1
            return arr / m if m != 0 else arr

        # 2. Package the Swarm into a background function
        def run_swarm():
            from scipy.optimize import differential_evolution
            import warnings
            
            def objective(params):
                env = {"np": np, "e": np.e, "pi": np.pi, "x": x, "data_dict": safe_aux, "norm": norm_func}
                for i, p in enumerate(self.parameters): env[p] = params[i]
                try:
                    with np.errstate(all='ignore'):
                        y_pred = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
                    if y_pred.ndim == 0: y_pred = np.full_like(x, float(y_pred))
                    return np.sum((y - y_pred)**2)
                except:
                    return np.inf

            max_iterations = 500
            current_iter = [0]

            def swarm_callback(xk, convergence=0.0):
                current_iter[0] += 1
                pct = int((current_iter[0] / max_iterations) * 100)
                
                if hasattr(self, 'swarm_worker'):
                    self.swarm_worker.progress.emit(pct)
                
                if self.swarm_progress.wasCanceled():
                    return True 

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

        # 3. CRITICAL: Initialize the Worker Thread
        self.swarm_worker = LocalWorker(run_swarm)

        # 4. Define Callbacks
        def on_success(best_params):
            self.swarm_progress.accept()
            
            # Update the UI state
            self._swarm_count += 1
            self.auto_guess_btn.setText("✨ Targeted Swarm (Local)")
            
            for i, p in enumerate(self.parameters):
                if self.param_configs[p]["mode"].currentText() == "Auto":
                    self.param_configs[p]["val"].blockSignals(True)
                    self.param_configs[p]["val"].setText(f"{best_params[i]:.6g}")
                    self.param_configs[p]["val"].blockSignals(False)
                    
            self._draw_live_preview()
            QMessageBox.information(self, "Swarm Complete", "Global search finished! Check the preview.")

        def on_err(err_str):
            self.swarm_progress.accept()
            QMessageBox.warning(self, "Swarm Failed", f"The search could not find a reasonable fit:\n{err_str}")

        # 5. Wire Everything Together
        self.swarm_worker.finished.connect(on_success)
        self.swarm_worker.error.connect(on_err)
        self.swarm_worker.progress.connect(self.swarm_progress.setValue)
        self.swarm_progress.canceled.connect(self.swarm_worker.terminate)
        
        self.swarm_worker.start()

    def handle_done(self):
        if not self.is_valid:
            QMessageBox.warning(self, "Invalid Equation", "Please enter a valid mathematical equation.")
            return
        if not self.parameters:
            QMessageBox.warning(self, "No Parameters", "You must create at least one parameter to optimize!")
            return
        self.accept()

    def get_result(self):
        final_config = {}
        for p, controls in self.param_configs.items():
            try: val = float(controls["val"].text())
            except: val = 1.0
            final_config[p] = {"mode": controls["mode"].currentText(), "value": val}
            
        # Pass the raw covariance matrix out instead of calculated stats
        pcov = getattr(self, 'latest_pcov', None)
        return self.equation_input.toPlainText().strip(), self.parsed_equation, self.html_equation, self.used_cols, self.parameters, final_config, pcov


class MultiFitManagerDialog(QDialog):
    def __init__(self, fits, action_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{action_name} Function")
        self.setFixedSize(380, 140)
        self.layout = QVBoxLayout(self)
        
        self.layout.addWidget(QLabel(f"<b>Select which function to {action_name.lower()}:</b>"))
        self.combo = QComboBox()
        for i, f in enumerate(fits):
            self.combo.addItem(f["name"], i)
        self.layout.addWidget(self.combo)
        
        btn_box = QHBoxLayout()
        self.btn_action = QPushButton(action_name)
        self.btn_action.setStyleSheet(f"font-weight: bold; color: {theme.primary_text};")
        self.btn_cancel = QPushButton("Cancel")
        
        if action_name == "Delete":
            self.btn_action.setStyleSheet(f"font-weight: bold; color: {theme.danger_text};")
            self.btn_all = QPushButton("Delete All")
            self.btn_all.setStyleSheet(f"font-weight: bold; color: {theme.danger_text};")
            btn_box.addWidget(self.btn_all)
            self.btn_all.clicked.connect(self.accept_all)
        
        btn_box.addStretch()
        btn_box.addWidget(self.btn_action)
        btn_box.addWidget(self.btn_cancel)
        self.layout.addLayout(btn_box)
        
        self.btn_action.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.result_type = "single"
        
    def accept_all(self):
        self.result_type = "all"
        super().accept()
        
    def get_selection(self):
        return self.result_type, self.combo.currentData()


class FitDataToFunctionWindow(QMainWindow):
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.dataset = dataset
        self.func = None

        self.setWindowTitle("Fit data to function")
        self.resize(900, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        self.last_x = None
        self.last_y = None

        controls = QVBoxLayout()
        layout.addLayout(controls, 0)

        load_btn = QPushButton("Load Function")
        load_btn.clicked.connect(self.load_function)
        controls.addWidget(load_btn)

        controls.addWidget(QLabel("Data column"))
        self.col_combo = QComboBox()
        for i, name in dataset.column_names.items():
            self.col_combo.addItem(f"{i}: {name}")
        controls.addWidget(self.col_combo)

        plot_btn = QPushButton("Plot")
        plot_btn.clicked.connect(self.plot)
        controls.addWidget(plot_btn)

        save_btn = QPushButton("Save Plot")
        save_btn.clicked.connect(self.save_plot)
        controls.addWidget(save_btn)
        
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self.export_csv)
        controls.addWidget(export_btn)
        
        self.export_btn = export_btn
        self.export_btn.setEnabled(False)

        calc_btn = QPushButton("Function Calculator")
        calc_btn.clicked.connect(self.open_calculator)
        controls.addWidget(calc_btn)

        controls.addStretch()

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.35)
        layout.addWidget(self.plot_widget, 1)

    def load_function(self):
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        import numpy as np
        import re

        fname, _ = QFileDialog.getOpenFileName(
            self, "Load Function", "",
            "Text files (*.txt)"
        )
        if not fname: return

        try:
            with open(fname, 'r') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]

            if not lines: return

            # 1. The Metadata Gatekeeper
            type_line = lines[0]
            if type_line.startswith("3D:"):
                QMessageBox.warning(self, "Format Mismatch", "This is a 3D surface function and cannot be loaded into the 2D data fitter.")
                return

            func_type = type_line.lower()

            # 2. Compile Common Functions into Callables
            if func_type == "polynomial":
                coeffs = [float(x) for x in lines[2:]]
                self.func = np.poly1d(coeffs)

            elif func_type == "logarithmic":
                base_str = lines[1].split(":")[1].strip()
                base = np.e if base_str.lower() == 'e' else float(base_str)
                params = [float(x) for x in lines[2:]]
                self.func = lambda x, a=params[0], c=params[1], b=base: a * np.log(x) / np.log(b) + c

            elif func_type == "exponential":
                params = [float(x) for x in lines[1:]]
                self.func = lambda x, a=params[0], b=params[1], c=params[2]: a * np.exp(b * x) + c

            elif func_type == "gaussian":
                params = [float(x) for x in lines[1:]]
                self.func = lambda x, A=params[0], mu=params[1], sig=params[2]: A * np.exp(-(x - mu)**2 / (2 * sig**2))

            elif func_type == "lorentzian":
                params = [float(x) for x in lines[1:]]
                self.func = lambda x, A=params[0], x0=params[1], gam=params[2]: A / (1 + ((x - x0) / gam)**2)

            # 3. Compile Custom Functions Safely
            elif func_type == "custom":
                raw_eq = lines[1]
                p_names = [p.strip() for p in lines[2].split(",") if p.strip()]
                p_vals = [float(x) for x in lines[3:]]
                
                # Convert the raw equation into a numpy-safe Python string
                py_eq = raw_eq.replace('^', '**')
                math_funcs = ['arcsinh','arccosh','arctanh','arcsin','arccos','arctan','sinh','cosh','tanh','sin','cos','tan', 'exp', 'log10', 'log2', 'log', 'abs']
                for mf in math_funcs:
                    py_eq = re.sub(r'\b' + mf + r'\s*\(', f'np.{mf}(', py_eq, flags=re.IGNORECASE)
                py_eq = re.sub(r'\bln\s*\(', 'np.log(', py_eq, flags=re.IGNORECASE)
                
                # Replace Physics Constants natively
                def replace_const(m):
                    c_key = m.group(1)
                    return f"({PHYSICS_CONSTANTS[c_key]['value']})" if c_key in PHYSICS_CONSTANTS else m.group(0)
                py_eq = re.sub(r'\{\\(.*?)\}', replace_const, py_eq)
                
                # Strip curly brackets from parameters if they exist
                for p in p_names: py_eq = py_eq.replace(f"{{{p}}}", p)

                # Create the isolated evaluation environment
                def custom_callable(x_val):
                    env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val}
                    for i, name in enumerate(p_names): env[name] = p_vals[i]
                    res = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
                    if res.ndim == 0: res = np.full_like(x_val, float(res))
                    return res
                    
                self.func = custom_callable

            else:
                QMessageBox.warning(self, "Unknown Format", f"Unrecognised function type: {type_line}")
                return

            QMessageBox.information(self, "Success", f"Successfully loaded {type_line.capitalize()} function.")

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Load Error", f"Failed to parse function file:\n{e}\n\n{traceback.format_exc()}")
            self.func = None

    def plot(self):
        self.last_x = None
        self.last_y = None
        self.export_btn.setEnabled(False)
    
        if self.func is None: return
    
        try: col = int(self.col_combo.currentText().split(":")[0])
        except (ValueError, IndexError): return
    
        xs = []
        is_csv = type(self.dataset).__name__ == 'CSVDataset'
        
        for sw in range(self.dataset.num_sweeps):
            try:
                if is_csv: arr = self.dataset.data
                else: arr = self.dataset.sweeps[sw].data
                data = np.asarray(arr[:, col], dtype=np.float64)
                xs.append(data)
            except Exception:
                continue
    
        if not xs: return
            
        x = np.concatenate(xs)
        x = x[np.isfinite(x)]
        if x.size == 0: return
    
        x = x[x > 0]
        if x.size == 0: return
    
        try:
            y = self.func(x)
        except Exception:
            QMessageBox.warning(self, "Math Error", "The function failed to evaluate on this data. (E.g. log of negative number)")
            return
    
        mask = np.isfinite(y)
        x = x[mask]
        y = y[mask]
    
        if x.size == 0: return
    
        self.plot_widget.clear()
        self.plot_widget.plot(
            x, y,
            pen=pg.mkPen("k", width=1.5),
            symbol="o",
            symbolSize=5
        )
        self.plot_widget.autoRange()
    
        self.last_x = x
        self.last_y = y
        self.export_btn.setEnabled(True)

    def save_plot(self):
        fname, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "",
            "PNG (*.png);;JPEG (*.jpg);;SVG (*.svg)"
        )
        if not fname: return
        if not os.path.splitext(fname)[1]: fname += ".png"

        exporter = (
            pgexp.SVGExporter(self.plot_widget.plotItem)
            if fname.lower().endswith(".svg")
            else pgexp.ImageExporter(self.plot_widget.plotItem)
        )
        exporter.export(fname)

    def export_csv(self):
        if self.last_x is None or self.last_y is None: return
    
        fname, _ = QFileDialog.getSaveFileName(
            self, "Export evaluated data", "", "CSV files (*.csv)"
        )
        if not fname: return
        if not fname.lower().endswith(".csv"): fname += ".csv"
    
        try:
            with open(fname, "w") as f:
                f.write("x,f(x)\n")
                for xi, yi in zip(self.last_x, self.last_y):
                    f.write(f"{xi},{yi}\n")
        except Exception:
            pass

    def open_calculator(self):
        if self.func is None: return
        dlg = QDialog(self)
        dlg.setWindowTitle("Function Calculator")
        dlg.setFixedSize(280, 160)
    
        layout = QVBoxLayout(dlg)
        form = QFormLayout()
    
        x_edit = QLineEdit()
        y_label = QLabel("")
    
        form.addRow("Input value:", x_edit)
        form.addRow("Output value:", y_label)
        layout.addLayout(form)
    
        def calculate():
            try:
                x = float(x_edit.text())
                y = self.func(x)
                y_label.setText(str(y))
            except Exception as e:
                y_label.setText("Error")
    
        calc_btn = QPushButton("Calculate")
        calc_btn.clicked.connect(calculate)
        layout.addWidget(calc_btn)
    
        dlg.exec()
