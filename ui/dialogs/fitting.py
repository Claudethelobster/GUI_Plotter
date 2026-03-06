# ui/dialogs/fitting.py
import os
import re
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pgexp
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QMainWindow, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLineEdit, QLabel, QPushButton, QTableWidget, QHeaderView,
    QScrollArea, QWidget, QFileDialog, QMessageBox, QApplication
)

from core.constants import PHYSICS_CONSTANTS, GREEK_MAP
from ui.dialogs.data_mgmt import ConstantsDialog, CopyableErrorDialog
from utils.function_io import load_function_from_file

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
        self.auto_guess_btn.setStyleSheet("font-weight: bold; color: #2ca02c; padding: 6px;")
        self.auto_guess_btn.clicked.connect(self.run_auto_guess)
        
        self.apply_btn = QPushButton("Calculate & Apply Fit")
        self.apply_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
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
        self.auto_guess_btn.setVisible(f in ["Gaussian", "Lorentzian", "Polynomial"])
        
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
        btn_x.setStyleSheet("color: #d90000; font-weight: bold; border: 1px solid #d90000; padding: 4px;")
        btn_x.clicked.connect(lambda: self.equation_input.textCursor().insertText("x"))
        btn_layout.addWidget(btn_x)
        
        self.const_btn = QPushButton("✨ Physics Constants")
        self.const_btn.setStyleSheet("font-weight: bold; color: #2ca02c; border: 1px solid #2ca02c; padding: 4px;")
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
            btn.setStyleSheet("color: #0055ff; font-weight: bold; border: 1px solid #0055ff; padding: 4px;")
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

        self.param_btn_layout = QHBoxLayout()
        layout.addLayout(self.param_btn_layout)

        math_lbl_layout = QHBoxLayout()
        math_lbl_layout.addWidget(QLabel("<b>3. Equation:</b> <i>(+, -, *, /, ^, sin(), exp()...)</i>"))
        math_lbl_layout.addStretch()
        
        self.load_func_btn = QPushButton("📂 Load Saved Function")
        self.load_func_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 4px 10px;")
        self.load_func_btn.clicked.connect(self.load_custom_function)
        math_lbl_layout.addWidget(self.load_func_btn)
        
        layout.addLayout(math_lbl_layout)
        
        self.equation_input = QTextEdit()
        self.equation_input.setMaximumHeight(80)
        self.equation_input.setFont(pg.QtGui.QFont("Consolas", 11))
        self.equation_input.textChanged.connect(self.update_preview)
        layout.addWidget(self.equation_input)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: white; border: 1px solid #ccc; font-size: 22px; font-family: Cambria, serif; font-style: italic; padding: 10px;")
        self.preview_label.setMinimumHeight(100)
        layout.addWidget(self.preview_label)

        layout.addWidget(QLabel("<b>4. Parameter Settings:</b>"))
        self.param_table = QTableWidget()
        self.param_table.setColumnCount(3)
        self.param_table.setHorizontalHeaderLabels(["Parameter", "Mode", "Value / Guess"])
        self.param_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.param_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.param_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.param_table.verticalHeader().setVisible(False)
        layout.addWidget(self.param_table)

        btn_box = QHBoxLayout()
        
        self.optimize_btn = QPushButton("Optimize Parameters")
        self.optimize_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        self.optimize_btn.clicked.connect(self.run_optimization)
        self.optimize_btn.setEnabled(False)
        
        self.done_btn = QPushButton("Done")
        self.done_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
        self.done_btn.clicked.connect(self.handle_done)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addWidget(self.optimize_btn)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.done_btn)
        layout.addLayout(btn_box)
        
        self.param_configs = {}

    def load_custom_function(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Load Custom Function", "", "Text files (*.txt)")
        if not fname: return
        
        with open(fname, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
            
        if not lines or lines[0].lower() != "custom":
            QMessageBox.warning(self, "Invalid File", "This is not a saved Custom Function file.\n(It may be a standard Gaussian/Polynomial fit).")
            return
            
        if len(lines) < 2:
            QMessageBox.warning(self, "Corrupted File", "The function file appears to be empty.")
            return
            
        raw_eq = lines[1]
        param_names = [p.strip() for p in lines[2].split(",") if p.strip()] if len(lines) > 2 else []
        param_vals = [float(v) for v in lines[3:]] if len(lines) > 3 else []
        
        self.equation_input.setPlainText(raw_eq)
        
        for i, p_name in enumerate(param_names):
            if p_name not in self.parameters:
                self.new_param_edit.setText(p_name)
                self.add_parameter()
                
            if i < len(param_vals) and p_name in self.param_configs:
                self.param_configs[p_name]["mode"].setCurrentText("Manual") 
                self.param_configs[p_name]["val"].setText(f"{param_vals[i]:.6g}")
                
        self.update_preview()
        self._check_boxes_filled()

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
        if not self.is_valid or not self.parameters:
            self.optimize_btn.setEnabled(False)
            return
            
        for controls in self.param_configs.values():
            if not controls["val"].text().strip():
                self.optimize_btn.setEnabled(False)
                return
                
        self.optimize_btn.setEnabled(True)
        self._draw_live_preview()

    def _draw_live_preview(self):
        if not self.is_valid or not self.parameters: return
        
        param_vals = []
        for p in self.parameters:
            try: 
                param_vals.append(float(self.param_configs[p]["val"].text()))
            except ValueError:
                return 
                
        res = self.parent_gui._get_all_plotted_xy(aux_cols=self.used_cols, apply_selection=False)
        
        if len(res) < 4 or len(res[0]) == 0: return
        x, _, aux_dict, _ = res
        
        sort_idx = np.argsort(x)
        x_sorted = x[sort_idx]
        sorted_aux = {c: aux_dict[c][sort_idx] for c in self.used_cols}
        
        env = {"np": np, "e": np.e, "pi": np.pi, "x": x_sorted, "data_dict": sorted_aux}
        for i, p in enumerate(self.parameters): env[p] = param_vals[i]
        
        try:
            yfit = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
            if yfit.ndim == 0:
                yfit = np.full_like(x_sorted, float(yfit))
            
            if not hasattr(self.parent_gui, 'phantom_curve'):
                self.parent_gui.phantom_curve = pg.PlotCurveItem(pen=pg.mkPen("m", width=3, style=Qt.DotLine))
                self.parent_gui.plot_widget.addItem(self.parent_gui.phantom_curve)
            
            self.parent_gui.phantom_curve.setData(x_sorted, yfit)
            self.parent_gui.phantom_curve.setVisible(True)
        except Exception:
            pass

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
        btn.setStyleSheet("color: #800080; font-weight: bold; border: 1px solid #800080; padding: 4px;")
        btn.clicked.connect(lambda checked, n=p: self.equation_input.textCursor().insertText(f"{{{n}}}"))
        self.param_btn_layout.addWidget(btn)
        
        row = self.param_table.rowCount()
        self.param_table.insertRow(row)
        
        lbl = QLabel(display_name)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("font-weight: bold; color: #800080; font-size: 16px;")
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
            if p_key in self.parameters: return f"({p_key})"
            else: raise ValueError()
            
        try: py_equation = re.sub(r'\{(.*?)\}', replace_param_silent, py_equation)
        except ValueError: return False, ""

        py_equation = py_equation.replace('^', '**')
        math_funcs = ['arcsinh','arccosh','arctanh','arcsin','arccos','arctan','sinh','cosh','tanh','sin','cos','tan']
        for f in math_funcs:
            py_equation = re.sub(r'\b' + f + r'\s*\(', 'np.'+f+'(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?2\s*\(', 'np.log2(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bexp\s*\(', 'np.exp(', py_equation, flags=re.IGNORECASE)

        try:
            env = {"np": np, "data_dict": dummy_dict, "e": np.e, "pi": np.pi, "x": np.ones(1)}
            for p in self.parameters: env[p] = 1.0
            with np.errstate(all='ignore'):
                eval(py_equation, {"__builtins__": {}}, env)
            return True, py_equation
        except Exception: return False, py_equation

    def update_preview(self):
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
                span = f"<span style='color: #2ca02c; font-weight: bold; font-style: normal;'>{c_html}</span>"
            else: span = f"<span style='color: red;'>{{\\{c_key}}}</span>"
            consts.append(span); return f"__CONST{len(consts)-1}__"
        html_text = re.sub(r'\{\\(.*?)\}', const_repl, html_text)

        params_html = []
        def param_repl(m):
            p_key = m.group(1)
            if p_key in self.parameters:
                p_html = GREEK_MAP.get(p_key, p_key)
                span = f"<span style='color: #800080; font-weight: bold; font-style: normal;'>{p_html}</span>"
            else: span = f"<span style='color: red;'>{{{p_key}}}</span>"
            params_html.append(span); return f"__PARAM{len(params_html)-1}__"
        html_text = re.sub(r'\{(.*?)\}', param_repl, html_text)

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
        html_text = re.sub(r'\b(arcsin|arccos|arctan|arcsinh|arccosh|arctanh|sinh|cosh|tanh|sin|cos|tan|ln|log(?:_?[0-9]+)?|exp)\b', func_repl, html_text, flags=re.IGNORECASE)

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
            if not re.search(r'__(EXP|PAREN|FUNC|COL|CONST|PARAM|XVAR)\d+__', html_text): break
            for i in range(len(exps)): html_text = html_text.replace(f"__EXP{i}__", exps[i])
            for i in range(len(parens)): html_text = html_text.replace(f"__PAREN{i}__", parens[i])
            for i in range(len(funcs)): html_text = html_text.replace(f"__FUNC{i}__", funcs[i])
            for i in range(len(consts)): html_text = html_text.replace(f"__CONST{i}__", consts[i])
            for i in range(len(params_html)): html_text = html_text.replace(f"__PARAM{i}__", params_html[i])
            for i in range(len(xvars)): html_text = html_text.replace(f"__XVAR{i}__", xvars[i])
            for i in range(len(cols)): html_text = html_text.replace(f"__COL{i}__", f"<span style='color: #0055ff; font-weight: bold;'>{cols[i]}</span>")
            
        self.html_equation = html_text
        self.preview_label.setText(html_text)
        self._check_boxes_filled()

    def run_optimization(self):
        if not self.is_valid or not self.parameters: return
        res = self.parent_gui._get_all_plotted_xy(aux_cols=self.used_cols)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, aux_dict, _ = res

        self.optimize_btn.setText("Optimizing...")
        self.optimize_btn.setEnabled(False)
        QApplication.processEvents()

        param_config = {}
        for p, controls in self.param_configs.items():
            try: val = float(controls["val"].text())
            except: val = 1.0
            param_config[p] = {"mode": controls["mode"].currentText(), "value": val}

        def custom_model(x_val, *args):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "data_dict": aux_dict}
            for i, p in enumerate(self.parameters): env[p] = args[i]
            res_arr = np.asarray(eval(self.parsed_equation, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
            return res_arr

        try:
            final_params = self.parent_gui._execute_universal_fit(custom_model, self.parameters, param_config, x, y)
            
            for i, p in enumerate(self.parameters):
                if self.param_configs[p]["mode"].currentText() == "Auto":
                    self.param_configs[p]["val"].blockSignals(True)
                    self.param_configs[p]["val"].setText(f"{final_params[i]:.6g}")
                    self.param_configs[p]["val"].blockSignals(False)
            
            self._draw_live_preview()

        except Exception as e:
            QMessageBox.critical(self, "Failed", f"Math Error or Failed Convergence.\n\nCheck your initial guesses!\n\nDetails: {e}")

        self.optimize_btn.setText("Optimize Parameters")
        self.optimize_btn.setEnabled(True)

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
        return self.equation_input.toPlainText().strip(), self.parsed_equation, self.html_equation, self.used_cols, self.parameters, final_config


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
        self.btn_action.setStyleSheet("font-weight: bold; color: #0055ff;")
        self.btn_cancel = QPushButton("Cancel")
        
        if action_name == "Delete":
            self.btn_action.setStyleSheet("font-weight: bold; color: #d90000;")
            self.btn_all = QPushButton("Delete All")
            self.btn_all.setStyleSheet("font-weight: bold; color: #d90000;")
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
        fname, _ = QFileDialog.getOpenFileName(
            self, "Load Function", "",
            "Text files (*.txt)"
        )
        if not fname: return
        try:
            self.func = load_function_from_file(fname)
        except Exception:
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
