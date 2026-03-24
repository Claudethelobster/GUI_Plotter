# ui/custom_widgets.py
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, 
    QPushButton, QHBoxLayout, QSpinBox, QDoubleSpinBox, QColorDialog,
    QLabel, QCheckBox, QTableWidget, QHeaderView, QTableWidgetItem, QLineEdit
)
from PyQt5.QtGui import QColor
from core.theme import theme

class CustomAxisItem(pg.AxisItem):
    """ Intercepts the tick drawing engine to display true logarithmic bunching and superscripts """
    
    labelDoubleClicked = pyqtSignal(str) 
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.custom_log_mode = False
        self.custom_log_base = 10.0

    def mouseClickEvent(self, ev):
        if ev.double() and ev.button() == Qt.LeftButton:
            self.labelDoubleClicked.emit(self.orientation)
            ev.accept()
        else:
            super().mouseClickEvent(ev)

    def set_custom_log(self, is_log, base=10.0):
        self.custom_log_mode = is_log
        self.custom_log_base = base
        self.picture = None 
        self.update()

    def tickValues(self, minVal, maxVal, size):
        if not self.custom_log_mode:
            return super().tickValues(minVal, maxVal, size)
        
        if np.isinf(minVal) or np.isinf(maxVal) or np.isnan(minVal) or np.isnan(maxVal):
            return []

        if maxVal - minVal > 0.5:
            min_i = int(np.floor(max(-300, minVal)))
            max_i = int(np.ceil(min(300, maxVal)))
            
            major_ticks = np.arange(min_i, max_i + 1)
            minor_ticks = []
            
            base_int = int(round(self.custom_log_base))
            if base_int > 1:
                for i in range(min_i - 1, max_i + 1):
                    for k in range(2, base_int):
                        minor_val = i + np.log(k) / np.log(self.custom_log_base)
                        if minVal <= minor_val <= maxVal:
                            minor_ticks.append(minor_val)
                            
            return [(1.0, major_ticks), (0.1, minor_ticks)]
        else:
            return super().tickValues(minVal, maxVal, size)

    def tickStrings(self, values, scale, spacing):
        # 1. Linear Mode: Hardcoded formatter to prevent cross-device DPI scaling issues
        if not getattr(self, 'custom_log_mode', False):
            strings = []
            for v in values:
                if v == 0:
                    strings.append("0")
                elif abs(v) < 1e-4 or abs(v) >= 1e4:
                    # Scientific notation for very large/small numbers
                    strings.append(f"{v:.2e}")
                else:
                    # Standard decimals (e.g., 0.001) up to 4 significant figures
                    strings.append(f"{v:.4g}")
            return strings
        
        # 2. Log Mode: Your existing custom superscript formatting
        superscripts = {'0':'⁰', '1':'¹', '2':'²', '3':'³', '4':'⁴', '5':'⁵', '6':'⁶', '7':'⁷', '8':'⁸', '9':'⁹', '-':'⁻', '.':'⋅'}
        
        strings = []
        for v in values:
            if abs(v - round(v)) < 1e-4:
                exp_val = int(round(v))
                exp_str = "".join(superscripts.get(c, c) for c in str(exp_val))
                base_str = "e" if abs(self.custom_log_base - np.e) < 1e-4 else f"{self.custom_log_base:g}"
                strings.append(f"{base_str}{exp_str}")
            else:
                if spacing < 0.5: 
                    with np.errstate(over='ignore', invalid='ignore'):
                        orig = np.power(self.custom_log_base, float(v))
                        
                    if np.isinf(orig) or np.isnan(orig): strings.append("")
                    elif orig == 0: strings.append("0")
                    elif abs(orig) < 1e-3 or abs(orig) >= 1e4: strings.append(f"{orig:.2e}")
                    else: strings.append(f"{orig:.3g}")
                else:
                    strings.append("") 
        return strings

class DraggableLabel(QLabel):
    """ A custom QLabel that allows the user to click and drag it around its parent widget. """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dragging = False
        self._drag_start_pos = None
        self.setCursor(Qt.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            self.raise_()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            new_pos = self.mapToParent(event.pos() - self._drag_start_pos)
            if self.parent():
                parent_rect = self.parent().rect()
                x = max(0, min(new_pos.x(), parent_rect.width() - self.width()))
                y = max(0, min(new_pos.y(), parent_rect.height() - self.height()))
                self.move(x, y)
            else:
                self.move(new_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = False
            self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
        
class CustomLegendItem(pg.LegendItem):
    sigDoubleClicked = pyqtSignal(object)

    def __init__(self, size=None, offset=None):
        super().__init__(size, offset)
        self.setBrush(pg.mkBrush(255, 255, 255, 230)) 
        self.setPen(pg.mkPen('k', width=1.5)) 
        self.layout.setContentsMargins(8, 8, 8, 8) 
        
        # FIX 1: Push the legend to the absolute top layer, above all grid lines
        self.setZValue(10000) 

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.sigDoubleClicked.emit(self)
            ev.accept()
        else:
            super().mouseDoubleClickEvent(ev)

    def update_style(self, bg_col, fg_col, opacity, border_width, columns, spacing):
        # Background
        base_color = pg.mkColor('w') if bg_col == "Transparent" else pg.mkColor(bg_col)
        base_color.setAlpha(opacity)
        self.setBrush(pg.mkBrush(base_color))
        
        # Border
        if border_width > 0:
            self.setPen(pg.mkPen(fg_col, width=border_width))
        else:
            self.setPen(None)
            
        self.columnCount = max(1, columns)
        
        # FIX 2 & 3: Custom Layout Engine (Column-Major Sorting + Anti-Overlap Spacing)
        # 1. Strip all items out of the current layout manager safely
        for i in range(self.layout.count() - 1, -1, -1):
            self.layout.removeAt(i)
            
        # 2. Re-insert them using Top-to-Bottom, Left-to-Right math
        if len(self.items) > 0:
            rowCount = int(np.ceil(len(self.items) / self.columnCount))
            for i, (sample, label) in enumerate(self.items):
                row = i % rowCount
                col = i // rowCount
                
                self.layout.addItem(sample, row, col * 2)
                self.layout.addItem(label, row, col * 2 + 1)
                
                # Force strict alignments to keep everything anchored
                self.layout.setAlignment(sample, Qt.AlignRight | Qt.AlignVCenter)
                self.layout.setAlignment(label, Qt.AlignLeft | Qt.AlignVCenter)

        self.layout.setVerticalSpacing(spacing)
        self.layout.setHorizontalSpacing(15) # Force a hard gap between the symbol and the text
        self.updateSize()
        
class TraceSettingsDialog(QDialog):
    def __init__(self, style_data, pair_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Trace Settings: {pair_name}")
        self.setMinimumWidth(350)
        self.style_data = style_data.copy() if style_data else {}
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Line", "Scatter", "Line + Scatter"])
        self.type_combo.setCurrentText(self.style_data.get("type", "Line"))
        form.addRow("Plot Type:", self.type_combo)
        
        # Color Picker
        self.color_btn = QPushButton("Auto (Colormap)")
        self.custom_color = self.style_data.get("color")
        self._update_color_btn()
        self.color_btn.clicked.connect(self._pick_color)
        
        btn_clear_color = QPushButton("↺ Revert to Auto")
        btn_clear_color.clicked.connect(self._clear_color)
        
        color_lay = QHBoxLayout()
        color_lay.addWidget(self.color_btn)
        color_lay.addWidget(btn_clear_color)
        form.addRow("Trace Color:", color_lay)
        
        # Line Settings
        self.line_style_combo = QComboBox()
        self.line_style_combo.addItems(["Solid", "Dashed", "Dotted", "Dash-Dot"])
        self.line_style_combo.setCurrentText(self.style_data.get("line_style", "Solid"))
        form.addRow("Line Style:", self.line_style_combo)
        
        self.line_width_spin = QDoubleSpinBox()
        self.line_width_spin.setRange(0.5, 10.0)
        self.line_width_spin.setSingleStep(0.5)
        self.line_width_spin.setValue(self.style_data.get("line_width", 2.0))
        form.addRow("Line Width:", self.line_width_spin)
        
        # Scatter Settings
        self.sym_combo = QComboBox()
        self.sym_combo.addItems(["Circle (o)", "Square (s)", "Triangle (t)", "Star (star)", "Cross (+)", "X (x)"])
        self.sym_combo.setCurrentText(self.style_data.get("symbol", "Circle (o)"))
        form.addRow("Symbol:", self.sym_combo)
        
        self.sym_size_spin = QSpinBox()
        self.sym_size_spin.setRange(1, 30)
        self.sym_size_spin.setValue(self.style_data.get("symbol_size", 5))
        form.addRow("Symbol Size:", self.sym_size_spin)
        
        layout.addLayout(form)
        
        btn_box = QHBoxLayout()
        ok, cancel = QPushButton("Apply"), QPushButton("Cancel")
        
        # --- THEME UPDATE ---
        ok.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        
        btn_box.addStretch(); btn_box.addWidget(cancel); btn_box.addWidget(ok)
        layout.addLayout(btn_box)
        
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        
        self.type_combo.currentTextChanged.connect(self._toggle_fields)
        self._toggle_fields()
        
    def _toggle_fields(self):
        t = self.type_combo.currentText()
        show_line = "Line" in t
        show_scat = "Scatter" in t
        self.line_style_combo.setEnabled(show_line)
        self.line_width_spin.setEnabled(show_line)
        self.sym_combo.setEnabled(show_scat)
        self.sym_size_spin.setEnabled(show_scat)
        
    def _pick_color(self):
        color = QColorDialog.getColor(QColor(self.custom_color) if self.custom_color else Qt.white, self)
        if color.isValid():
            self.custom_color = color.name()
            self._update_color_btn()
            
    def _clear_color(self):
        self.custom_color = None
        self._update_color_btn()
        
    def _update_color_btn(self):
        if self.custom_color:
            self.color_btn.setText(self.custom_color)
            text_col = 'black' if QColor(self.custom_color).lightness() > 128 else 'white'
            self.color_btn.setStyleSheet(f"background-color: {self.custom_color}; color: {text_col}; font-weight: bold;")
        else:
            self.color_btn.setText("Auto (Colormap)")
            self.color_btn.setStyleSheet("")
            
    def get_result(self):
        self.style_data.update({
            "type": self.type_combo.currentText(),
            "color": self.custom_color,
            "line_style": self.line_style_combo.currentText(),
            "line_width": self.line_width_spin.value(),
            "symbol": self.sym_combo.currentText(),
            "symbol_size": self.sym_size_spin.value()
        })
        return self.style_data

try:
    import pyqtgraph.opengl as gl
    from PyQt5.QtGui import QPainter, QTextDocument, QColor, QVector3D
    OPENGL_AVAILABLE = True
    
    # --- NEW: CUSTOM 3D HTML RENDERER ---
    class GLRichTextItem(gl.GLGraphicsItem.GLGraphicsItem):
        def __init__(self, pos=(0,0,0), text='', font=None, color=(255,255,255,255)):
            super().__init__()
            self.pos = pos
            self.text = text
            self.font = font
            self.color = color

        def paint(self):
            self.setupGLState()
            view = self.view()
            painter = QPainter(view)
            painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
            
            # --- CRITICAL FIX: PyQtGraph 0.13+ Compatibility ---
            try:
                # Extract the raw integers from the QRect object into a tuple
                v_rect = view.rect()
                rect_tuple = (v_rect.x(), v_rect.y(), v_rect.width(), v_rect.height())
                
                # Pass the tuple to the newer pyqtgraph engine
                proj = view.projectionMatrix(region=rect_tuple, viewport=rect_tuple)
            except TypeError:
                # Fallback for older versions
                proj = view.projectionMatrix()
                
            pr = proj * view.viewMatrix() * self.transform()
            # ---------------------------------------------------
            
            p = pr.map(QVector3D(*self.pos))
            
            # Hide text if it rotates behind the camera
            if p.z() > 1.0 or p.z() < -1.0:
                painter.end()
                return
            
            x = (p.x() + 1.0) * view.width() * 0.5
            y = (1.0 - p.y()) * view.height() * 0.5
            
            # Render HTML using the UI's internal web-engine
            doc = QTextDocument()
            if self.font: doc.setDefaultFont(self.font)
            
            c = QColor(*self.color) if isinstance(self.color, (tuple, list)) else self.color
            doc.setHtml(f"<div style='color: {c.name()}; white-space: nowrap;'>{self.text}</div>")
            
            # Center the text exactly on the point
            size = doc.size()
            painter.translate(x - size.width() / 2, y - size.height() / 2)
            doc.drawContents(painter)
            painter.end()
    # ------------------------------------
except Exception:
    OPENGL_AVAILABLE = False
    
class LegendCustomizationDialog(QDialog):
    def __init__(self, main_window, entries, current_aliases, group_sweeps):
        super().__init__(main_window)
        self.setWindowTitle("Customize Legend")
        self.setMinimumSize(650, 500)
        self.main_window = main_window
        self.entries = entries 
        self.aliases = current_aliases.copy()
        
        layout = QVBoxLayout(self)
        
        self.group_cb = QCheckBox("Group multiple sweeps into a single legend entry")
        self.group_cb.setChecked(group_sweeps)
        self.group_cb.setStyleSheet("font-weight: bold; color: #0055ff;")
        layout.addWidget(self.group_cb)
        
        layout.addWidget(QLabel("<b>Customize Labels:</b> <i>(Leave blank to use default. Use ^ for superscripts and _ for subscripts.)</i>"))
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Original Smart Name", "Custom Override"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        
        layout.addWidget(QLabel("<b>Live Preview:</b>"))
        self.preview_widget = pg.GraphicsLayoutWidget()
        self.preview_widget.setFixedHeight(150)
        
        bg_col = main_window.bg_color_combo.currentText()
        self.preview_widget.setBackground(bg_col if bg_col != "Transparent" else "w")
        
        # Import the new custom legend locally to avoid circular dependencies
        from ui.custom_widgets import CustomLegendItem
        self.preview_legend = CustomLegendItem(offset=(10, 10))
        self.preview_legend.setParentItem(self.preview_widget.ci)
        layout.addWidget(self.preview_widget)
        
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Apply")
        btn_ok.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)
        
        self._populate_table()
        self.table.itemChanged.connect(self._on_table_changed)
        self.group_cb.stateChanged.connect(self._update_preview)
        self._update_preview()

    def _populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.entries))
        for i, entry in enumerate(self.entries):
            def_item = QTableWidgetItem(entry["base_name"])
            def_item.setFlags(def_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, def_item)
            
            custom_text = self.aliases.get(entry["sig_key"], "")
            cust_item = QTableWidgetItem(custom_text)
            self.table.setItem(i, 1, cust_item)
        self.table.blockSignals(False)

    def _on_table_changed(self, item):
        if item.column() == 1:
            row = item.row()
            sig_key = self.entries[row]["sig_key"]
            text = item.text().strip()
            if text: self.aliases[sig_key] = text
            else: self.aliases.pop(sig_key, None)
            self._update_preview()

    def _update_preview(self):
        self.preview_legend.clear()
        import re
        is_grouped = self.group_cb.isChecked()
        seen_groups = set()

        for entry in self.entries:
            if is_grouped:
                parts = entry["sig_key"].split("_")
                group_key = f"{parts[0]}_GROUPED_{parts[2]}_{parts[3]}" if len(parts) >= 4 else entry["sig_key"]
                if group_key in seen_groups: continue
                seen_groups.add(group_key)
                
                base_name = re.sub(r" \(Sweep \w+\)", "", entry["base_name"])
                display_text = self.aliases.get(group_key, base_name)
            else:
                display_text = self.aliases.get(entry["sig_key"], entry["base_name"])
            
            # Mini HTML parser for preview
            html_text = re.sub(r'\^([\w\.\-]+)', r'<sup>\1</sup>', display_text)
            html_text = re.sub(r'_([\w\.\-]+)', r'<sub>\1</sub>', html_text)
            
            dummy_plot = pg.PlotDataItem(pen=entry.get("pen", 'k'), symbol=entry.get("symbol", None), symbolBrush=entry.get("brush", None))
            self.preview_legend.addItem(dummy_plot, html_text)
            
    def get_result(self):
        return self.aliases, self.group_cb.isChecked()
    
class RichTextAxisLabelDialog(QDialog):
    def __init__(self, orientation, current_raw_text, main_window):
        super().__init__(main_window)
        self.setWindowTitle(f"Edit {orientation.capitalize()} Axis Label")
        self.setMinimumWidth(450)
        self.main_window = main_window
        self.parsed_html = current_raw_text

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Enter Custom Axis Label:</b>"))
        layout.addWidget(QLabel("<i>Tip: Use ^ for superscripts (m/s^2), _ for subscripts (x_0), and {alpha} for Greek.</i>"))

        input_lay = QHBoxLayout()
        self.input_edit = QLineEdit(current_raw_text)
        self.input_edit.textChanged.connect(self.update_preview)
        input_lay.addWidget(self.input_edit)

        self.const_btn = QPushButton("✨ Insert Constant")
        self.const_btn.clicked.connect(self.open_constants)
        input_lay.addWidget(self.const_btn)
        layout.addLayout(input_lay)

        layout.addSpacing(10)
        layout.addWidget(QLabel("<b>Live Preview:</b>"))

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)

        # --- Pull exact font & color from layout settings ---
        font_family = main_window.font_family_combo.currentFont().family()
        try: label_size = int(main_window.label_fontsize_edit.text())
        except ValueError: label_size = 14
        
        bg_color = main_window.bg_color_combo.currentText()
        if bg_color == "Black":
            box_bg, text_color = "#222", "white"
        else:
            box_bg, text_color = "white", "black"

        self.preview_label.setStyleSheet(f"background-color: {box_bg}; color: {text_color}; border: 1px solid #aaa; padding: 15px;")
        self.preview_label.setFont(pg.QtGui.QFont(font_family, label_size))
        layout.addWidget(self.preview_label)

        btn_box = QHBoxLayout()
        
        clear_btn = QPushButton("Revert to Default")
        clear_btn.setStyleSheet("color: #d90000;")
        clear_btn.clicked.connect(self._clear_and_accept)
        
        ok_btn = QPushButton("Apply")
        ok_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
        ok_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(clear_btn)
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)

        self.update_preview(current_raw_text)

    def _clear_and_accept(self):
        self.input_edit.setText("")
        self.accept()

    def open_constants(self):
        from ui.dialogs.data_mgmt import ConstantsDialog
        dlg = ConstantsDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_key:
            self.input_edit.insert(f"{{\\{dlg.selected_key}}}")

    def update_preview(self, text):
        html_text = text
        import re
        
        # 1. Physics Constants
        def const_repl(m):
            c_key = m.group(1)
            return PHYSICS_CONSTANTS[c_key]["html"] if c_key in PHYSICS_CONSTANTS else f"\\{{{c_key}}}"
        html_text = re.sub(r'\{\\(.*?)\}', const_repl, html_text)

        # 2. Greek Letters
        def param_repl(m):
            p_key = m.group(1)
            return GREEK_MAP.get(p_key, p_key)
        html_text = re.sub(r'\{(.*?)\}', param_repl, html_text)

        # 3. Superscripts (e.g., ^2, ^-1)
        html_text = re.sub(r'\^([\w\.\-]+)', r'<sup>\1</sup>', html_text)
        
        # 4. Subscripts (e.g., _0, _max)
        html_text = re.sub(r'_([\w\.\-]+)', r'<sub>\1</sub>', html_text)

        self.preview_label.setText(html_text)
        self.parsed_html = html_text

    def get_result(self):
        return self.input_edit.text().strip(), self.parsed_html
