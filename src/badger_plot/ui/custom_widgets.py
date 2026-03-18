# ui/custom_widgets.py
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, 
    QPushButton, QHBoxLayout, QSpinBox, QDoubleSpinBox, QColorDialog,
    QLabel
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
        if not self.custom_log_mode:
            return super().tickStrings(values, scale, spacing)
        
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
