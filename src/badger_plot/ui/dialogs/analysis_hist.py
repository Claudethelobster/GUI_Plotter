# ui/dialogs/analysis_hist.py
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QDoubleSpinBox, QSpinBox
)
from PyQt5.QtCore import Qt
from core.theme import theme

class SmartBinningDialog(QDialog):
    def __init__(self, data, current_bins, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Smart Binning Optimiser")
        self.setMinimumWidth(350)
        self.data = data[np.isfinite(data)]
        self.current_bins = current_bins
        
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("<b>Select Binning Algorithm:</b>"))
        
        self.method_combo = QComboBox()
        self.method_combo.addItems([
            "Freedman-Diaconis (Robust to outliers)", 
            "Sturges' Formula (Best for normal data)", 
            "Scott's Normal Reference (Minimises variance)", 
            "Square Root (Standard Excel/Simple method)"
        ])
        layout.addWidget(self.method_combo)
        
        self.result_label = QLabel()
        self.result_label.setStyleSheet(f"font-size: 14px; color: {theme.primary_text}; font-weight: bold; margin-top: 10px;")
        layout.addWidget(self.result_label)
        
        btn_box = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Bins")
        self.apply_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; background-color: {theme.primary_bg}; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.apply_btn)
        layout.addLayout(btn_box)
        
        self.method_combo.currentIndexChanged.connect(self._calculate_bins)
        self.apply_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        self.suggested_bins = 10
        self._calculate_bins()

    def _calculate_bins(self):
        n = len(self.data)
        if n < 2:
            self.suggested_bins = 10
            self.result_label.setText("Not enough data to optimise.")
            return
            
        method = self.method_combo.currentText()
        
        try:
            if "Sturges" in method:
                self.suggested_bins = int(np.ceil(np.log2(n) + 1))
            elif "Square Root" in method:
                self.suggested_bins = int(np.ceil(np.sqrt(n)))
            elif "Freedman" in method:
                iqr = np.subtract(*np.percentile(self.data, [75, 25]))
                bin_width = 2 * iqr / (n ** (1/3))
                if bin_width > 0:
                    self.suggested_bins = int(np.ceil((np.max(self.data) - np.min(self.data)) / bin_width))
                else:
                    self.suggested_bins = 10
            elif "Scott" in method:
                bin_width = 3.49 * np.std(self.data) / (n ** (1/3))
                if bin_width > 0:
                    self.suggested_bins = int(np.ceil((np.max(self.data) - np.min(self.data)) / bin_width))
                else:
                    self.suggested_bins = 10
                    
            # Cap the bins at a reasonable rendering limit so we don't crash the UI
            self.suggested_bins = max(5, min(self.suggested_bins, 10000))
            
            diff = self.suggested_bins - (int(self.current_bins) if str(self.current_bins).isdigit() else 0)
            diff_str = f"(+{diff})" if diff >= 0 else f"({diff})"
            self.result_label.setText(f"Suggested Bins: {self.suggested_bins} {diff_str}")
            
        except Exception:
            self.suggested_bins = 10
            self.result_label.setText("Calculation failed. Defaulting to 10.")

    def get_result(self):
        return str(self.suggested_bins)

class CDFOverlayDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("CDF Overlay Settings")
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("<b>Cumulative Distribution Function (CDF)</b>"))
        layout.addWidget(QLabel("This will plot the normalised cumulative sum on the right-hand Y-axis."))
        
        col_lay = QHBoxLayout()
        col_lay.addWidget(QLabel("Line Colour:"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(["Red", "Blue", "Green", "Magenta", "Cyan", "Yellow", "White"])
        col_lay.addWidget(self.color_combo)
        layout.addLayout(col_lay)
        
        thick_lay = QHBoxLayout()
        thick_lay.addWidget(QLabel("Line Thickness:"))
        self.thick_spin = QSpinBox()
        self.thick_spin.setRange(1, 10)
        self.thick_spin.setValue(2)
        thick_lay.addWidget(self.thick_spin)
        layout.addLayout(thick_lay)
        
        btn_box = QHBoxLayout()
        apply_btn = QPushButton("Generate CDF")
        apply_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; background-color: {theme.primary_bg};")
        cancel_btn = QPushButton("Cancel")
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(apply_btn)
        layout.addLayout(btn_box)
        
        apply_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def get_result(self):
        colour_map = {"Red": 'r', "Blue": 'b', "Green": 'g', "Magenta": 'm', "Cyan": 'c', "Yellow": 'y', "White": 'w'}
        return colour_map.get(self.color_combo.currentText(), 'r'), self.thick_spin.value()

class SigmaClippingDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sigma Clipping (Outlier Removal)")
        self.setMinimumSize(500, 450)
        
        self.data = data[np.isfinite(data)]
        self.mean = np.mean(self.data)
        self.std = np.std(self.data)
        
        layout = QVBoxLayout(self)
        
        # Mini Plot Preview
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground(theme.bg)
        self.plot_widget.setLabel('bottom', "Data Values")
        self.plot_widget.setLabel('left', "Counts")
        layout.addWidget(self.plot_widget)
        
        # Calculate a quick histogram for the preview
        y, x = np.histogram(self.data, bins='auto')
        centers = (x[:-1] + x[1:]) / 2
        widths = x[1:] - x[:-1]
        self.bg = pg.BarGraphItem(x=centers, height=y, width=widths, brush=pg.mkBrush((100, 150, 255, 150)))
        self.plot_widget.addItem(self.bg)
        
        self.lower_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
        self.upper_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
        self.plot_widget.addItem(self.lower_line)
        self.plot_widget.addItem(self.upper_line)
        
        controls = QHBoxLayout()
        controls.addWidget(QLabel("<b>Sigma Threshold (\u00b1 &sigma;):</b>"))
        self.sigma_spin = QDoubleSpinBox()
        self.sigma_spin.setRange(0.1, 10.0)
        self.sigma_spin.setValue(3.0)
        self.sigma_spin.setSingleStep(0.1)
        controls.addWidget(self.sigma_spin)
        layout.addLayout(controls)
        
        self.stats_lbl = QLabel()
        layout.addWidget(self.stats_lbl)
        
        btn_box = QHBoxLayout()
        self.apply_btn = QPushButton("Clip Data & Create Column")
        self.apply_btn.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; background-color: {theme.danger_bg}; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(self.apply_btn)
        layout.addLayout(btn_box)
        
        self.sigma_spin.valueChanged.connect(self._update_preview)
        self.apply_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        self._update_preview()

    def _update_preview(self):
        sigma = self.sigma_spin.value()
        lower_bound = self.mean - (sigma * self.std)
        upper_bound = self.mean + (sigma * self.std)
        
        self.lower_line.setPos(lower_bound)
        self.upper_line.setPos(upper_bound)
        
        mask = (self.data >= lower_bound) & (self.data <= upper_bound)
        kept = np.sum(mask)
        removed = len(self.data) - kept
        pct = (kept / len(self.data)) * 100
        
        self.stats_lbl.setText(f"Keeping values between <b>{lower_bound:.4g}</b> and <b>{upper_bound:.4g}</b><br>"
                               f"Data Retained: {kept} ({pct:.1f}%) | Outliers Removed: {removed}")

    def get_result(self):
        sigma = self.sigma_spin.value()
        return self.mean - (sigma * self.std), self.mean + (sigma * self.std)
