# ui/custom_widgets.py
import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel

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
