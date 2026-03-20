# ui/main_window.py
import os
import sys
import json
import numpy as np
import pyqtgraph as pg
import pyqtgraph.exporters as pgexp
from PyQt5.QtCore import Qt, QSettings, QTimer, QEvent
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QFileDialog, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QComboBox, QStackedLayout, 
    QMessageBox, QProgressDialog, QListWidget, QAction, QGridLayout, 
    QButtonGroup, QApplication, QDialog, QFormLayout, QTextEdit,
    QCheckBox, QTabWidget, QFontComboBox, QSlider, QTableWidget, QTableWidgetItem,
    QHeaderView, QSpinBox
)

# Core imports
from core.data_loader import DataLoaderThread, CSVDataset, Dataset, BADGERLOOP_AVAILABLE
from core.plot_worker import PlotWorkerThread
from core.constants import PHYSICS_CONSTANTS, GREEK_MAP
from core.theme import theme

# UI Component imports
from ui.custom_widgets import CustomAxisItem, DraggableLabel, CustomLegendItem, TraceSettingsDialog
from ui.dialogs.data_mgmt import (
    FileImportDialog, SweepTableDialog, ManageColumnsDialog, 
    MetadataDialog, CreateColumnDialog, CopyableErrorDialog
    
    
)
from ui.dialogs.analysis import (SignalProcessingDialog, PhaseSpaceDialog, PeakFinderTool,
                                 LoopAreaDialog, BaselineSubtractionDialog, AreaUnderCurveDialog,
                                 SpectrogramDialog, DataSlicerDialog
)
from ui.dialogs.fitting import (
    FitFunctionDialog, CustomFitDialog, MultiFitManagerDialog, FitDataToFunctionWindow
)
from ui.dialogs.help import HelpDialog

from ui.dialogs.settings import PreferencesDialog

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

class TemplateSelectionDialog(QDialog):
    def __init__(self, signatures, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EggPlot - Select Data Template")
        self.setMinimumWidth(550)
        layout = QVBoxLayout(self)
        
        layout.addWidget(QLabel("Multiple file formats were detected in this folder.\nSelect which group of files you want to load as sweeps:"))
        
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)
        
        self.sig_mapping = []
        
        sorted_sigs = sorted(signatures.items(), key=lambda x: len(x[1]), reverse=True)
        
        for i, (sig, files) in enumerate(sorted_sigs):
            if isinstance(sig, tuple):
                sig_str = ", ".join(sig)
            else:
                sig_str = f"{sig} columns (No Headers)"
                
            if len(sig_str) > 75: 
                sig_str = sig_str[:72] + "..."
                
            item_text = f"Group {i+1}: {len(files)} files -> Headers: [{sig_str}]"
            if i == 0: 
                item_text += " ⭐ (Auto / Recommended)"
                
            self.list_widget.addItem(item_text)
            self.sig_mapping.append(sig)
            
        self.list_widget.setCurrentRow(0)
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Load Selected Group")
        ok_btn.setStyleSheet("font-weight: bold; color: #0055ff; padding: 6px;")
        ok_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)
        
    def get_selected_signature(self):
        return self.sig_mapping[self.list_widget.currentRow()]
    
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

class BadgerLoopQtGraph(QMainWindow):
    def __init__(self):
        super().__init__()
        self.series_data = {"2D": [], "3D": [], "Heatmap": [], "Histogram": []}
        
        # --- NEW: PORTABLE MODE CHECK ---
        local_ini = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "settings.ini")
        if os.path.exists(local_ini):
            self.settings = QSettings(local_ini, QSettings.IniFormat)
        else:
            self.settings = QSettings("BadgerLoop", "QtPlotter")
            
        # --- NEW: DISABLE OPENGL OVERRIDE ---
        if self.settings.value("disable_opengl", False, bool):
            global OPENGL_AVAILABLE
            OPENGL_AVAILABLE = False
        # --------------------------------
        
        # --- FIX: INITIALISE THE THEME ENGINE BEFORE BUILDING THE UI ---
        is_dark = self.settings.value("dark_mode", False, bool)
        theme.update(is_dark)
        # ---------------------------------------------------------------
        
        self.dataset = None
        self.last_file = None
        self.legend_visible = True
        self.plot_mode = "2D"  
        self.fft_mode_active = False 
        
        axis_dict = {
            'bottom': CustomAxisItem('bottom'),
            'left': CustomAxisItem('left'),
            'top': CustomAxisItem('top'),
            'right': CustomAxisItem('right')
        }
        
        self.custom_axis_labels = {"bottom": None, "left": None, "top": None, "right": None}
        self.legend_aliases = {}
        for ax_name, ax_obj in axis_dict.items():
            ax_obj.labelDoubleClicked.connect(self._prompt_custom_axis_label)
        
        self.plot_widget = pg.PlotWidget(axisItems=axis_dict)
        self.plot_widget.getViewBox().installEventFilter(self)
        
        self.vb_right = pg.ViewBox()
        self.vb_right.installEventFilter(self)
        self.plot_widget.scene().addItem(self.vb_right)
        
        def updateViews():
            self.vb_right.setGeometry(self.plot_widget.getViewBox().sceneBoundingRect())
            
        self.plot_widget.getViewBox().sigResized.connect(updateViews)
        
        self.plot_wrapper = QWidget()
        wrapper_layout = QVBoxLayout(self.plot_wrapper)
        wrapper_layout.setAlignment(Qt.AlignCenter)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.plot_widget)
        
        if OPENGL_AVAILABLE:
            try:
                import pyqtgraph.opengl.shaders as gl_shaders
                gl_shaders.ShaderProgram.compiled.clear()
            except Exception: pass
            
            self.gl_widget = gl.GLViewWidget()
            self.gl_widget.setBackgroundColor('k')
        else:
            self.gl_widget = None
            
        self.plot_stack = QWidget()
        
        self.original_plot_stack_resize = self.plot_stack.resizeEvent
        self.plot_stack.resizeEvent = self._on_plot_stack_resize
        
        self.plot_layout = QStackedLayout(self.plot_stack)
        self.plot_layout.addWidget(self.plot_wrapper) 
        
        if self.gl_widget:
            self.plot_layout.addWidget(self.gl_widget)
            
        self.zcol = None
    
        self.setWindowTitle("EggPlot Data Plotter")
        self.resize(1200, 800)
        self.errorbars_enabled = False
        self.file_type = "BadgerLoop"
        self.csv_uncerts_enabled = False
        self.errorbar_nsigma = 1.0
        self.current_fit = None
        self.save_function_btn = None
        self.clear_fit_btn = None
    
        self._build_menu()
        
        if OPENGL_AVAILABLE:
            self.plot_3d_action.setEnabled(True)
            
        self._build_ui()
        self._apply_styles()
        self._fix_graphics_view()
        self._patch_pyqtgraph_menu()
        self.restore_state()
        
        if not BADGERLOOP_AVAILABLE:
            QTimer.singleShot(100, self.show_missing_library_warning)
    
        self._update_xscale_ui()
        self._update_yscale_ui()
        
    def show_missing_library_warning(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("Missing BadgerLoop Library")
        msg.setIcon(QMessageBox.Warning)
        msg.setText("The 'badger_loop_py3_2.py' library was not found in the same directory as this script.")
        msg.setInformativeText(
            "The program will run in CSV-only mode. All BadgerLoop-specific file formats and metadata features have been disabled.\n\n"
            "To enable full functionality, please place 'badger_loop_py3_2.py' in the same folder and restart the program."
        )
        
        btn_continue = msg.addButton("Run in CSV Mode", QMessageBox.AcceptRole)
        btn_close = msg.addButton("Close Program", QMessageBox.RejectRole)
        msg.exec()
        
        if msg.clickedButton() == btn_close:
            self.close()

    def update_active_layer(self):
        if getattr(self, 'plot_mode', '2D') != "2D": return
        if hasattr(self, 'clear_selection'): self.clear_selection()
        
        row = self.series_list.currentRow()
        if row < 0: return
        
        try:
            pair = self.series_data["2D"][row]
            if pair.get("axis", "L") == "R":
                self.vb_right.setZValue(100)
                self.plot_widget.getViewBox().setZValue(0)
            else:
                self.vb_right.setZValue(0)
                self.plot_widget.getViewBox().setZValue(100)
        except IndexError: pass

    def _post_init_plot(self):
        if self.dataset: self.plot()
            
    def update_file_mode_ui(self):
        is_multi = self.file_type == "MultiCSV"
        is_concat = self.file_type == "ConcatenatedCSV"
        is_bl = self.file_type == "BadgerLoop"
        is_csv = self.file_type == "CSV"
        is_hdf5 = self.file_type == "HDF5" # --- NEW: Register HDF5 ---
        
        # HDF5 naturally supports groups/sweeps!
        has_sweeps = is_bl or is_multi or is_concat or is_hdf5 or (is_csv and getattr(self.dataset, 'num_sweeps', 0) > 1)
        can_have_uncerts = is_csv or is_multi or is_concat
        
        self.show_metadata_btn.setVisible(True)
        self.sweeps_label.setVisible(has_sweeps)
        self.sweeps_edit.setVisible(has_sweeps)
        
        if hasattr(self, 'inspect_table_action'):
            self.inspect_table_action.setText("Sweep table" if has_sweeps else "Inspect data table")
            
        if not has_sweeps:
            self.errorbar_btn.setVisible(False)
            self.errorbar_sigma_edit.setVisible(False)
            self.average_enabled = False 
            self.errorbars_enabled = False
            
        avg_on = getattr(self, 'average_enabled', False)
        uncerts_on = getattr(self, 'csv_uncerts_enabled', False)
        
        if avg_on:
            self.toggle_avg_btn.setVisible(has_sweeps)
            self.toggle_uncert_btn.setVisible(False)
        elif uncerts_on:
            self.toggle_avg_btn.setVisible(False)
            self.toggle_uncert_btn.setVisible(can_have_uncerts)
        else:
            self.toggle_avg_btn.setVisible(has_sweeps)
            self.toggle_uncert_btn.setVisible(can_have_uncerts)
            
        self._update_uncert_visibility()
        
        if hasattr(self, 'concat_folder_action'):
            self.concat_folder_action.setEnabled(is_multi)
        
    def toggle_csv_uncertainties(self):
        self.csv_uncerts_enabled = not getattr(self, 'csv_uncerts_enabled', False)
        
        # Update styling
        if self.csv_uncerts_enabled:
            self.toggle_uncert_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
        else:
            self.toggle_uncert_btn.setStyleSheet(f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg};")
            
        self._update_uncert_visibility()
        self.update_file_mode_ui()
        self.plot()
        
    def _update_uncert_visibility(self):
        show = (self.file_type in ["CSV", "MultiCSV", "ConcatenatedCSV"] and getattr(self, 'csv_uncerts_enabled', False))
        
        is_hist = getattr(self, 'plot_mode', '2D') == "Histogram"
        
        self.xuncert_label.setVisible(show and not is_hist)
        self.xuncert.setVisible(show and not is_hist)
        self.yuncert_label.setVisible(show)
        self.yuncert.setVisible(show)
        
        show_z = show and (getattr(self, 'plot_mode', '2D') in ["3D", "Heatmap"])
        self.zuncert_label.setVisible(show_z)
        self.zuncert.setVisible(show_z)
        
    def _create_series_list_item(self, row_idx):
        pair = self.series_data[self.plot_mode][row_idx]
        text = f"{pair['y_name']} vs {pair['x_name']}"
        is_visible = pair.get('visible', True)
        axis_side = pair.get('axis', 'L')
        
        from PyQt5.QtWidgets import QListWidgetItem
        item = QListWidgetItem(self.series_list)
        self.series_list.addItem(item)
        
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(5, 2, 5, 2)
        
        label = QLabel(text)
        
        if self.plot_mode == "2D":
            btn_eye = QPushButton("👁")
            btn_eye.setFixedSize(26, 26)
            btn_eye.setCursor(Qt.PointingHandCursor)
            
            # --- NEW: Settings Button ---
            btn_settings = QPushButton("⚙️")
            btn_settings.setFixedSize(26, 26)
            btn_settings.setCursor(Qt.PointingHandCursor)
            btn_settings.setToolTip("Customize Trace Style")
            btn_settings.setStyleSheet("border: none; font-size: 16px; color: #555;")
            # ----------------------------
            
            btn_axis = QPushButton(axis_side)
            btn_axis.setFixedSize(26, 26)
            btn_axis.setCursor(Qt.PointingHandCursor)
            btn_axis.setToolTip("Toggle Left / Right Y-Axis")
            
            if is_visible:
                btn_eye.setStyleSheet(f"border: none; font-size: 16px; color: {theme.fg}; text-decoration: none;")
                label.setStyleSheet(f"color: {theme.fg}; text-decoration: none;")
            else:
                btn_eye.setStyleSheet("border: none; font-size: 16px; color: #aaa; text-decoration: line-through;")
                label.setStyleSheet("color: #aaa; text-decoration: line-through;")
                
            if axis_side == 'L':
                btn_axis.setStyleSheet(f"border: 1px solid {theme.border}; font-weight: bold; color: {theme.primary_text}; background: {theme.primary_bg};")
            else:
                btn_axis.setStyleSheet(f"border: 1px solid {theme.border}; font-weight: bold; color: {theme.danger_text}; background: {theme.danger_bg};")
                
            layout.addWidget(btn_eye)
            layout.addWidget(btn_settings)
            layout.addWidget(btn_axis)
            
            btn_eye.clicked.connect(lambda checked, r=item: self._toggle_series_visibility(r))
            btn_settings.clicked.connect(lambda checked, r=item: self._open_trace_settings(r))
            btn_axis.clicked.connect(lambda checked, r=item: self._toggle_series_axis(r))
        else:
            label.setStyleSheet("color: black; text-decoration: none;")
            
        layout.addWidget(label)
        layout.addStretch()
        
        item.setSizeHint(widget.sizeHint())
        self.series_list.setItemWidget(item, widget)

    def _toggle_series_axis(self, item):
        row = self.series_list.row(item)
        if row < 0: return
        pair = self.series_data[self.plot_mode][row]
        
        pair['axis'] = 'R' if pair.get('axis', 'L') == 'L' else 'L'
        
        widget = self.series_list.itemWidget(item)
        btns = widget.findChildren(QPushButton)
        
        if len(btns) > 2:
            btn_axis = btns[2] 
            btn_axis.setText(pair['axis'])
            if pair['axis'] == 'L':
                # --- FIX: USE THEME ENGINE VARIABLES ---
                btn_axis.setStyleSheet(f"border: 1px solid {theme.border}; font-weight: bold; color: {theme.primary_text}; background: {theme.primary_bg};")
            else:
                btn_axis.setStyleSheet(f"border: 1px solid {theme.border}; font-weight: bold; color: {theme.danger_text}; background: {theme.danger_bg};")
                # ---------------------------------------
                
        self.plot()
        self.update_active_layer()

    def _toggle_series_visibility(self, item):
        row = self.series_list.row(item)
        if row < 0: return
        pair = self.series_data[self.plot_mode][row]
        
        pair['visible'] = not pair.get('visible', True)
        is_visible = pair['visible']
        
        widget = self.series_list.itemWidget(item)
        btn = widget.findChild(QPushButton)
        label = widget.findChild(QLabel)
        
        if is_visible:
            btn.setStyleSheet(f"border: none; font-size: 16px; color: {theme.fg}; text-decoration: none;")
            label.setStyleSheet(f"color: {theme.fg}; text-decoration: none;")
        else:
            btn.setStyleSheet("border: none; font-size: 16px; color: #aaa; text-decoration: line-through;")
            label.setStyleSheet("color: #aaa; text-decoration: line-through;")
            
        self.plot()
        
    def _open_trace_settings(self, item):
        row = self.series_list.row(item)
        if row < 0: return
        pair = self.series_data[self.plot_mode][row]
        
        # Build default style if it doesn't exist yet
        if "style" not in pair:
            try: line_thick = float(self.line_thickness_edit.text())
            except: line_thick = 2.0
            try: pt_size = int(self.point_size_edit.text())
            except: pt_size = 5
            
            pair["style"] = {
                "type": self.graphtype.currentText(),
                "color": None,
                "line_style": "Solid",
                "line_width": line_thick,
                "symbol": self.symbol_combo.currentText(),
                "symbol_size": pt_size
            }
            
        pair_name = f"{pair.get('y_name', 'Y')} vs {pair.get('x_name', 'X')}"
        dlg = TraceSettingsDialog(pair["style"], pair_name, self)
        if dlg.exec() == QDialog.Accepted:
            pair["style"] = dlg.get_result()
            self.plot() # Instantly redraw
        
    def _set_interaction_mode(self, btn):
        text = btn.text()
        if "Pan" in text:
            self.interaction_mode = "pan"
            self.plot_widget.getViewBox().setMouseEnabled(x=True, y=True)
        else:
            self.interaction_mode = "box" if "Box" in text else "lasso"
            self.plot_widget.getViewBox().setMouseEnabled(x=False, y=False)

        active_style = f"background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; font-weight: bold; border-radius: 4px; padding: 6px; color: {theme.primary_text};"
        inactive_style = f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg};"

        for b in [self.btn_pan, self.btn_box, self.btn_lasso]:
            if b.isChecked(): b.setStyleSheet(active_style)
            else: b.setStyleSheet(inactive_style)

    def eventFilter(self, source, event):
        # --- NEW SAFETY SHIELD: Ignore events if the UI isn't fully built yet ---
        if not hasattr(self, 'plot_widget') or self.plot_widget is None:
            return super().eventFilter(source, event)
            
        if source == self.plot_widget.getViewBox() or source == getattr(self, 'vb_right', None):
            if getattr(self, 'interaction_mode', 'pan') != "pan" and getattr(self, 'plot_mode', '2D') == "2D":
                if event.type() == QEvent.GraphicsSceneMousePress and event.button() == Qt.LeftButton:
                    self._start_selection(event)
                    return True 
                elif event.type() == QEvent.GraphicsSceneMouseMove and getattr(self, '_is_selecting', False):
                    self._drag_selection(event)
                    return True
                elif event.type() == QEvent.GraphicsSceneMouseRelease and event.button() == Qt.LeftButton and getattr(self, '_is_selecting', False):
                    self._end_selection(event)
                    return True
        return super().eventFilter(source, event)

    def _start_selection(self, event):
        self._is_selecting = True
        pos = self.plot_widget.getViewBox().mapSceneToView(event.scenePos())
        self._sel_start_pt = (pos.x(), pos.y())
        self._sel_path = [self._sel_start_pt]
        self.selection_curve.setData([], [])
        self.selection_curve.show()
        
    def _drag_selection(self, event):
        pos = self.plot_widget.getViewBox().mapSceneToView(event.scenePos())
        curr_pt = (pos.x(), pos.y())
        
        if self.interaction_mode == "lasso":
            self._sel_path.append(curr_pt)
            xs = [p[0] for p in self._sel_path]
            ys = [p[1] for p in self._sel_path]
            self.selection_curve.setData(xs, ys)
        elif self.interaction_mode == "box":
            self._sel_path = [self._sel_start_pt, curr_pt] 
            x0, y0 = self._sel_start_pt
            x1, y1 = curr_pt
            xs = [x0, x1, x1, x0, x0]
            ys = [y0, y0, y1, y1, y0]
            self.selection_curve.setData(xs, ys)
            
    def _end_selection(self, event):
        self._is_selecting = False
        self.selection_curve.hide() 
        
        x_vis, y_vis, _, _ = self._get_all_plotted_xy(apply_selection=False)
        if len(x_vis) == 0: return
        
        row = self.series_list.currentRow()
        is_right_active = False
        if row >= 0 and self.series_data.get("2D"):
            if self.series_data["2D"][row].get("axis", "L") == "R":
                is_right_active = True

        math_path = []
        for px, py in self._sel_path:
            if is_right_active:
                scene_pt = self.plot_widget.getViewBox().mapViewToScene(pg.Point(px, py))
                right_pt = self.vb_right.mapSceneToView(scene_pt)
                math_path.append((right_pt.x(), right_pt.y()))
            else:
                math_path.append((px, py))

        pts = np.column_stack((x_vis, y_vis))
        
        if self.interaction_mode == "box":
            x0, y0 = math_path[0]
            x1, y1 = math_path[-1] if len(math_path) > 1 else math_path[0]
            x_min, x_max = min(x0, x1), max(x0, x1)
            y_min, y_max = min(y0, y1), max(y0, y1)
            
            mask = (x_vis >= x_min) & (x_vis <= x_max) & (y_vis >= y_min) & (y_vis <= y_max)
            new_indices = np.where(mask)[0]
            
        elif self.interaction_mode == "lasso":
            if len(math_path) < 3: return
            import matplotlib.path as mpath
            path = mpath.Path(math_path)
            mask = path.contains_points(pts)
            new_indices = np.where(mask)[0]
            
        ctrl_pressed = (event.modifiers() == Qt.ControlModifier)
        if ctrl_pressed: self.selected_indices.update(new_indices) 
        else: self.selected_indices = set(new_indices) 
            
        if self.selected_indices:
            idx_array = list(self.selected_indices)
            try: self.plot_widget.removeItem(self.highlight_scatter)
            except: pass
            try: self.vb_right.removeItem(self.highlight_scatter)
            except: pass
            
            if is_right_active: self.vb_right.addItem(self.highlight_scatter)
            else: self.plot_widget.addItem(self.highlight_scatter)
            
            self.highlight_scatter.setData(x_vis[idx_array], y_vis[idx_array])
            self.highlight_scatter.setZValue(100) 
            self.highlight_scatter.show()
            self._update_selection_stats()
        else:
            self.highlight_scatter.hide()
            self.stats_label.hide()
            
        # --- ADD THIS TO THE VERY END OF THE FUNCTION ---
        if hasattr(self, '_on_selection_finished_cb') and self._on_selection_finished_cb:
            cb = self._on_selection_finished_cb
            self._on_selection_finished_cb = None
            cb()
        # ------------------------------------------------
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
        super().keyPressEvent(event)
        
    def clear_selection(self):
        self.selected_indices.clear()
        self.highlight_scatter.hide()
        self.selection_curve.hide()
        self.stats_label.hide()
        
    def open_loop_area_calculator(self):
        if not self.dataset: return
        res = self._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Data", "Please plot a 2D curve first.")
            return

        dlg = LoopAreaDialog(self)
        if dlg.exec() == QDialog.Accepted:
            loops = dlg.get_selected_loops()
            self._apply_final_loops(loops)
        else:
            self._clear_temp_loops()

    def _clear_temp_loops(self):
        if not hasattr(self, 'temp_loop_items'): self.temp_loop_items = []
        for item in self.temp_loop_items:
            try: self.plot_widget.removeItem(item)
            except: pass
        self.temp_loop_items.clear()

    def _draw_temp_loops(self, checked_loops, highlighted_loops):
        self._clear_temp_loops()
        
        from PyQt5.QtWidgets import QGraphicsPolygonItem
        from PyQt5.QtGui import QPolygonF
        from PyQt5.QtCore import QPointF
        import pyqtgraph as pg
        
        # Draw standard checked loops (Faint Gray)
        for loop in checked_loops:
            if loop in highlighted_loops: continue 
            
            # Build native Qt Polygon
            polygon = QPolygonF([QPointF(x, y) for x, y in zip(loop['x'], loop['y'])])
            item = QGraphicsPolygonItem(polygon)
            item.setPen(pg.mkPen((150, 150, 150, 200), width=2))
            item.setBrush(pg.mkBrush((150, 150, 150, 80)))
            
            self.plot_widget.addItem(item)
            self.temp_loop_items.append(item)
            
        # Draw currently selected loop in the list (Bright Green)
        for loop in highlighted_loops:
            # Build native Qt Polygon with explicit floats
            polygon = QPolygonF([QPointF(float(x), float(y)) for x, y in zip(loop['x'], loop['y'])])
            item = QGraphicsPolygonItem(polygon)
            item.setFillRule(Qt.WindingFill) # <--- NEW: Forces Qt to shade intersecting/CW lobes
            
            item.setPen(pg.mkPen((150, 150, 150, 200), width=2))
            item.setBrush(pg.mkBrush((150, 150, 150, 80)))
            
            self.plot_widget.addItem(item)
            self.temp_loop_items.append(item)

    def _apply_final_loops(self, loops):
        self._clear_temp_loops()
        self._clear_final_loops() # Wipe old final loops
        if not hasattr(self, 'final_loop_items'): self.final_loop_items = []
        
        if not loops: return
            
        from PyQt5.QtWidgets import QGraphicsPolygonItem
        from PyQt5.QtGui import QPolygonF
        from PyQt5.QtCore import QPointF
        import pyqtgraph as pg
            
        total_abs_area = 0.0
        total_net_area = 0.0
        
        for loop in loops:
            total_abs_area += loop['abs_area']
            total_net_area += loop['area']
            
            # Physics specific coloring: Blue for Counter-Clockwise (+), Red for Clockwise (-)
            color = (0, 85, 255, 100) if loop['area'] >= 0 else (217, 0, 0, 100) 
            border = (0, 85, 255, 200) if loop['area'] >= 0 else (217, 0, 0, 200)
            
            polygon = QPolygonF([QPointF(float(x), float(y)) for x, y in zip(loop['x'], loop['y'])])
            item = QGraphicsPolygonItem(polygon)
            item.setFillRule(Qt.WindingFill) # <--- NEW
            
            item.setPen(pg.mkPen(border, width=2))
            item.setBrush(pg.mkBrush(color))
            item.setZValue(-10)
            
            self.plot_widget.addItem(item)
            self.final_loop_items.append(item)
            
        # Build the green HUD
        html = f"<b style='color: #2ca02c; font-size: 14px;'>Loop Area Analysis</b><br><hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
        html += f"<b>Loops Selected:</b>&nbsp;&nbsp;{len(loops)}<br>"
        html += f"<b>Total Abs Area:</b>&nbsp;&nbsp;{total_abs_area:.6g}<br>"
        html += f"<b>Net Area:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{total_net_area:.6g}<br>"
        html += f"<i style='font-size: 11px;'>(Blue = CCW, Red = CW)</i>"
        
        self.loop_stats_label.setText(html)
        self.loop_stats_label.adjustSize()
        
        if not self.loop_stats_label.isVisible():
            w = self.plot_wrapper.width()
            self.loop_stats_label.move(w - self.loop_stats_label.width() - 20, 20)
            
        self.loop_stats_label.show()
        self.loop_stats_label.raise_()
        
        self.toggle_loop_btn.setVisible(True)
        self.toggle_loop_btn.setChecked(True)
        self.toggle_loop_btn.setStyleSheet("font-weight: bold; background-color: #d0e8ff; border: 2px solid #0055ff; border-radius: 4px; padding: 6px; color: #0055ff;")

    def _clear_final_loops(self):
        if hasattr(self, 'final_loop_items'):
            for item in self.final_loop_items:
                try: self.plot_widget.removeItem(item)
                except: pass
            self.final_loop_items.clear()
        if hasattr(self, 'loop_stats_label'): self.loop_stats_label.hide()
        if hasattr(self, 'toggle_loop_btn'): self.toggle_loop_btn.setVisible(False)

    def _toggle_loop_areas(self):
        is_checked = self.toggle_loop_btn.isChecked()
        if is_checked:
            self.toggle_loop_btn.setStyleSheet("font-weight: bold; background-color: #d0e8ff; border: 2px solid #0055ff; border-radius: 4px; padding: 6px; color: #0055ff;")
            self.loop_stats_label.show()
            self.loop_stats_label.raise_()
        else:
            self.toggle_loop_btn.setStyleSheet("background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 6px; color: black;")
            self.loop_stats_label.hide()
            
        for item in getattr(self, 'final_loop_items', []):
            item.setVisible(is_checked)

    def open_signal_processing(self):
        if not self.dataset: return
        res = self._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0: 
            QMessageBox.warning(self, "No Data", "Please plot a 2D curve first.")
            return
            
        x_full, y_full, _, pair = res
        sel_idx = sorted(list(self.selected_indices)) if getattr(self, 'selected_indices', set()) else []
        
        dlg = SignalProcessingDialog(x_full, y_full, sel_idx, pair.get('y_name', 'Data'), self)
        
        if not hasattr(self, 'phantom_curve'):
            self.phantom_curve = pg.PlotCurveItem(pen=pg.mkPen("m", width=3, style=Qt.DashLine))
            self.plot_widget.addItem(self.phantom_curve)
        
        dlg.preview_updated.connect(lambda x_prev, y_prev: self._update_signal_preview(x_prev, y_prev))
        dlg.calculate_preview() 
        
        if dlg.exec() == QDialog.Accepted:
            self.phantom_curve.setVisible(False)
            config = dlg.get_result()
            
            # --- NEW FOLDER INTERCEPT ---
            if self.file_type == "MultiCSV":
                def continue_sp(): self._create_processed_column(config, pair)
                self._intercept_folder_edit(continue_sp)
                return
            # ----------------------------
            
            fname = self.dataset.filename
            orig_name = os.path.basename(fname)
            directory = os.path.dirname(fname)

            if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
                name_only, ext = os.path.splitext(orig_name)
                import glob
                search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
                existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

                if not existing_mirrors:
                    target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                    try: 
                        if self.file_type == "CSV": self._write_csv_mirror(target_file)
                        else:
                            import shutil
                            shutil.copy2(fname, target_file)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                        return
                    QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
                else:
                    dlg_mirror = QDialog(self)
                    dlg_mirror.setWindowTitle("Mirror File Exists")
                    dlg_mirror.setFixedSize(450, 150)
                    l = QVBoxLayout(dlg_mirror)
                    l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                    combo = QComboBox()
                    combo.addItem("--- Create New Mirror ---")
                    combo.addItems(existing_mirrors)
                    l.addWidget(combo)
                    
                    btn_box = QHBoxLayout()
                    ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                    btn_box.addWidget(ok); btn_box.addWidget(cancel)
                    l.addLayout(btn_box)
                    
                    ok.clicked.connect(dlg_mirror.accept); cancel.clicked.connect(dlg_mirror.reject)
                    if dlg_mirror.exec() != QDialog.Accepted: return
                    
                    choice = combo.currentText()
                    if choice == "--- Create New Mirror ---":
                        import re
                        max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                        new_mirror_name = f"MIRROR_{name_only} ({max_num + 1}){ext}"
                        target_file = os.path.join(directory, new_mirror_name)
                        
                        if self.file_type == "CSV": self._write_csv_mirror(target_file)
                        else:
                            import shutil
                            shutil.copy2(fname, target_file)
                    else:
                        target_file = os.path.join(directory, choice)

                opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
                if self.file_type == "CSV": opts["delimiter"] = ","
                    
                self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
                self.progress_dialog.setWindowModality(Qt.WindowModal)
                self.progress_dialog.setCancelButton(None)
                self.progress_dialog.setMinimumDuration(0)
                self.progress_dialog.show()

                def on_mirror_loaded(dataset):
                    self._on_load_finished(dataset, target_file, opts)
                    self._create_processed_column(config, pair) 

                self.loader_thread = DataLoaderThread(target_file, opts)
                self.loader_thread.progress.connect(self._update_progress_ui)
                self.loader_thread.finished.connect(on_mirror_loaded)
                self.loader_thread.error.connect(self._on_load_error)
                self.loader_thread.start()
                return

            self._create_processed_column(config, pair)
        else:
            self.phantom_curve.setVisible(False)
            
    def open_baseline_subtraction(self):
        if not self.dataset: return
        
        # --- NEW FOLDER INTERCEPT ---
        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(self._show_actual_baseline_dialog)
            return
        # ----------------------------
        
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type in ["CSV", "ConcatenatedCSV"]: self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    from PyQt5.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QHBoxLayout, QPushButton
                dlg_mirror = QDialog(self)
                dlg_mirror.setWindowTitle("Mirror File Exists")
                dlg_mirror.setFixedSize(450, 150)
                l = QVBoxLayout(dlg_mirror)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                
                ok.clicked.connect(dlg_mirror.accept); cancel.clicked.connect(dlg_mirror.reject)
                if dlg_mirror.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    new_mirror_name = f"MIRROR_{name_only} ({max_num + 1}){ext}"
                    target_file = os.path.join(directory, new_mirror_name)
                    
                    if self.file_type in ["CSV", "ConcatenatedCSV"]: self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
                
            from PyQt5.QtWidgets import QProgressDialog
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_baseline_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_baseline_dialog()
        
    def open_data_slicer(self):
        if not self.dataset: return
        
        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(self._show_actual_data_slicer)
            return
            
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type in ["CSV", "ConcatenatedCSV"]: self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    from PyQt5.QtWidgets import QMessageBox
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
            else:
                from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QHBoxLayout, QPushButton
                dlg_mirror = QDialog(self)
                dlg_mirror.setWindowTitle("Mirror File Exists")
                dlg_mirror.setFixedSize(450, 150)
                l = QVBoxLayout(dlg_mirror)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                
                ok.clicked.connect(dlg_mirror.accept); cancel.clicked.connect(dlg_mirror.reject)
                if dlg_mirror.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    target_file = os.path.join(directory, f"MIRROR_{name_only} ({max_num + 1}){ext}")
                    
                    if self.file_type in ["CSV", "ConcatenatedCSV"]: self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
                
            from PyQt5.QtWidgets import QProgressDialog
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_data_slicer() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_data_slicer()

    def _show_actual_data_slicer(self):
        dlg = DataSlicerDialog(self)
        if dlg.exec() != QDialog.Accepted: return
        
        target_idx, cond_idx, thresh, target_name = dlg.get_result()
        
        is_csv = (self.file_type == "CSV")
        sweeps = range(self.dataset.num_sweeps) if not is_csv else [0]
        
        blocks_below = []
        blocks_above = []
        
        for sw in sweeps:
            arr = self.dataset.data if is_csv else self.dataset.sweeps[sw].data
            cond_data = np.asarray(arr[:, cond_idx], dtype=np.float64)
            target_data = np.asarray(arr[:, target_idx], dtype=np.float64)
            
            with np.errstate(invalid='ignore'):
                mask_below = cond_data <= thresh
                mask_above = cond_data > thresh
            
            data_below = target_data.copy()
            data_below[~mask_below] = np.nan
            
            data_above = target_data.copy()
            data_above[~mask_above] = np.nan
            
            blocks_below.append(data_below)
            blocks_above.append(data_above)
            
        name_below = f"{target_name} (<= {thresh:g})"
        name_above = f"{target_name} (> {thresh:g})"
        
        try:
            self._append_column_to_file(self.dataset.filename, name_below, blocks_below)
            self._append_column_to_file(self.dataset.filename, name_above, blocks_above)
            
            from PyQt5.QtWidgets import QMessageBox, QProgressDialog, QApplication
            QMessageBox.information(self, "Success", f"Successfully sliced data at {thresh:g}.\n\nCreated:\n1. {name_below}\n2. {name_above}")
            
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Execution Error", f"Failed to slice data:\n\n{e}\n\n{traceback.format_exc()}")

    def _show_actual_baseline_dialog(self):
        from PyQt5.QtWidgets import QMessageBox, QDialog, QApplication, QProgressDialog
        res = self._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0: 
            QMessageBox.warning(self, "No Data", "Please plot a 2D curve first.")
            return
            
        # 1. Create the dialog as a floating, non-blocking palette
        self.baseline_dlg = BaselineSubtractionDialog(self)
        self.baseline_dlg.setWindowModality(Qt.NonModal) 
        
        # 2. Lock the data columns so the user doesn't break the background arrays while drawing
        self.xcol.setEnabled(False)
        self.ycol.setEnabled(False)
        self.series_list.setEnabled(False)
        
        def restore_ui():
            self.xcol.setEnabled(True)
            self.ycol.setEnabled(True)
            self.series_list.setEnabled(True)
            if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
            if hasattr(self, 'phantom_baseline_flattened'): self.phantom_baseline_flattened.setVisible(False)
            
        def on_accept():
            restore_ui()
            baseline_array = self.baseline_dlg.get_result()
            x_full, y_full, _, pair = self._get_all_plotted_xy(apply_selection=False)
            subtracted_data = y_full - baseline_array
            
            # --- Capture exact names ---
            orig_x_name = pair.get('x_name', 'X')
            new_y_name = f"{pair.get('y_name', 'Y')} (Baseline Subtracted)"
            
            try:
                self._append_column_to_file(self.dataset.filename, new_y_name, [subtracted_data])
                
                opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
                self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
                self.progress_dialog.setWindowModality(Qt.WindowModal)
                self.progress_dialog.setCancelButton(None)
                self.progress_dialog.setMinimumDuration(0)
                self.progress_dialog.show()
                QApplication.processEvents()
                
                def on_baseline_loaded(ds):
                    # 1. Mute the default plot trigger!
                    self._is_plotting = True 
                    
                    self._on_load_finished(ds, self.dataset.filename, opts)
                    
                    # 2. Release the mute
                    self._is_plotting = False
                    
                    target_x_idx, target_y_idx = 0, 0
                    
                    # Search the dropdowns by exact name
                    for i in range(self.xcol.count()):
                        combo_text = self.xcol.itemText(i)
                        actual_name = combo_text.split(": ", 1)[-1] if ": " in combo_text else combo_text
                        
                        if actual_name == orig_x_name: target_x_idx = i
                        if actual_name == new_y_name: target_y_idx = i
                            
                    self.xcol.blockSignals(True)
                    self.ycol.blockSignals(True)
                    self.xcol.setCurrentIndex(target_x_idx)
                    self.ycol.setCurrentIndex(target_y_idx)
                    self.xcol.blockSignals(False)
                    self.ycol.blockSignals(False)
                    
                    # 3. Fire the final, correct plot
                    if self.series_data["2D"]: self.update_current_series()
                    else: self.add_series_to_list()
                
                self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
                self.loader_thread.progress.connect(self._update_progress_ui)
                self.loader_thread.finished.connect(on_baseline_loaded)
                self.loader_thread.error.connect(self._on_load_error)
                self.loader_thread.start()
            except Exception as e:
                QMessageBox.critical(self, "Write Error", f"Failed to save the baseline data:\n{e}")
                
        def on_reject():
            restore_ui()
            
        # 3. Connect signals instead of halting execution
        self.baseline_dlg.accepted.connect(on_accept)
        self.baseline_dlg.rejected.connect(on_reject)
        self.baseline_dlg.show()

    def _create_processed_column(self, config, pair):
        import scipy.signal as sig
        import scipy.integrate as intg
        
        name, method = config['name'], config['method']
        win, poly = config['win'], config['poly']
        use_mask, sel_idx = config['use_mask'], config['sel_idx']
        
        x_idx, y_idx = pair['x'], pair['y']
        is_csv = (self.file_type == "CSV")
        sweeps = range(self.dataset.num_sweeps) if not is_csv else [0]
        calculated_data_blocks = []
            
        for sw in sweeps:
            arr = self.dataset.data if is_csv else self.dataset.sweeps[sw].data
            x_raw = np.asarray(arr[:, x_idx], dtype=np.float64)
            y_raw = np.asarray(arr[:, y_idx], dtype=np.float64)
            
            with np.errstate(all='ignore'):
                if "Savitzky" in method: y_calc = sig.savgol_filter(y_raw, win, poly)
                elif "Moving Average" in method: y_calc = np.convolve(y_raw, np.ones(win)/win, mode='same')
                elif "Median" in method: y_calc = sig.medfilt(y_raw, kernel_size=win)
                elif "Derivative" in method:
                    if len(x_raw) < 2: y_calc = np.zeros_like(y_raw)
                    else:
                        dx = np.gradient(x_raw)
                        if np.all(dx == 0): y_calc = np.zeros_like(y_raw)
                        else:
                            dx[np.abs(dx) < 1e-10] = 1e-10 * np.sign(dx[np.abs(dx) < 1e-10] + 1e-15)
                            y_calc = np.gradient(y_raw) / dx
                            y_calc = np.clip(np.nan_to_num(y_calc, nan=0.0, posinf=1e6, neginf=-1e6), -1e6, 1e6)
                elif "Integral" in method:
                    y_calc = np.nan_to_num(intg.cumulative_trapezoid(y_raw, x=x_raw + (np.arange(len(x_raw)) * 1e-12), initial=0), nan=0.0)
                else: y_calc = y_raw.copy()

            if use_mask and sel_idx:
                final_y = y_raw.copy()
                valid_indices = [i for i in sel_idx if i < len(final_y)]
                final_y[valid_indices] = y_calc[valid_indices]
            else:
                final_y = y_calc
                
            calculated_data_blocks.append(final_y)

        try:
            self._append_column_to_file(self.dataset.filename, name, calculated_data_blocks)
            QMessageBox.information(self, "Success", f"Column '{name}' created and saved successfully.")
            
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()

        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Fatal Execution Error", f"The file writer encountered a critical error:\n\n{e}\n\nTraceback:\n{traceback.format_exc()}")

    def open_phase_space_dialog(self):
        if not self.dataset: return
        
        # --- NEW FOLDER INTERCEPT ---
        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(self._show_actual_phase_space_dialog)
            return
        # ----------------------------
        
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    new_mirror_name = f"MIRROR_{name_only} ({max_num + 1}){ext}"
                    target_file = os.path.join(directory, new_mirror_name)
                    
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
                
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_phase_space_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_phase_space_dialog()

    def _show_actual_phase_space_dialog(self):
        dlg = PhaseSpaceDialog(self.dataset, self)
        if dlg.exec() != QDialog.Accepted: return
        state_idx, time_idx, new_name = dlg.get_result()
        if not new_name: return

        is_csv = (self.file_type == "CSV")
        sweeps = range(self.dataset.num_sweeps) if not is_csv else [0]
        calculated_data_blocks = []

        for sw in sweeps:
            arr = self.dataset.data if is_csv else self.dataset.sweeps[sw].data
            x_raw = np.asarray(arr[:, state_idx], dtype=np.float64)

            if time_idx == -1: t_raw = np.arange(len(x_raw), dtype=np.float64)
            else: t_raw = np.asarray(arr[:, time_idx], dtype=np.float64)

            with np.errstate(all='ignore'):
                if len(x_raw) < 2: y_calc = np.zeros_like(x_raw)
                else:
                    dx = np.gradient(x_raw)
                    dt = np.gradient(t_raw)
                    dt[np.abs(dt) < 1e-10] = 1e-10 * np.sign(dt[np.abs(dt) < 1e-10] + 1e-15)
                    y_calc = np.clip(np.nan_to_num(dx / dt, nan=0.0, posinf=1e6, neginf=-1e6), -1e6, 1e6)
            calculated_data_blocks.append(y_calc)

        try:
            self._append_column_to_file(self.dataset.filename, new_name, calculated_data_blocks)
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data & Plotting Phase Space...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            def on_phase_space_loaded(ds):
                self._on_load_finished(ds, self.dataset.filename, opts)
                new_col_idx = len(self.dataset.column_names) - 1
                
                self.xcol.blockSignals(True); self.ycol.blockSignals(True)
                self.xcol.setCurrentIndex(state_idx)
                self.ycol.setCurrentIndex(new_col_idx)
                self.xcol.blockSignals(False); self.ycol.blockSignals(False)
                
                self.set_plot_mode("2D")
                self.graphtype.setCurrentText("Line")
                
                if self.series_data["2D"]: self.update_current_series()
                else: self.add_series_to_list()
                    
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_phase_space_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()

        except Exception as e:
            QMessageBox.critical(self, "Fatal Error", f"Failed to generate phase space:\n\n{e}")

    def _update_signal_preview(self, x_prev, y_prev):
        valid = np.isfinite(x_prev) & np.isfinite(y_prev)
        if not np.any(valid):
            self.phantom_curve.setVisible(False)
            return
        self.phantom_curve.setData(x_prev[valid], y_prev[valid])
        self.phantom_curve.setVisible(True)
        
    def show_metadata(self):
        if self.dataset:
            MetadataDialog(self.dataset, self).exec()
        
    def open_peak_finder(self):
        if not self.dataset: return
        
        # --- NEW FOLDER INTERCEPT ---
        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(self._show_actual_peak_finder)
            return
        # ----------------------------
        
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type in ["CSV", "ConcatenatedCSV"]:
                        self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    new_mirror_name = f"MIRROR_{name_only} ({max_num + 1}){ext}"
                    target_file = os.path.join(directory, new_mirror_name)
                    
                    if self.file_type in ["CSV", "ConcatenatedCSV"]:
                        self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
                
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_peak_finder() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_peak_finder()

    def _show_actual_peak_finder(self):
        """ Actually launches the UI after ensuring we are on a safe mirror. """
        if not hasattr(self, 'peak_finder_tool') or self.peak_finder_tool is None:
            self.peak_finder_tool = PeakFinderTool(self)
            
        self.peak_finder_tool.show()
        self.peak_finder_tool.raise_()
        self.peak_finder_tool.activateWindow()

    def draw_peak_markers(self, peaks_x, peaks_y, left_x, right_x, width_heights, axis_side):
        self.clear_peak_markers()
        self.peak_markers = []
        
        target_vb = self.vb_right if axis_side == "R" else self.plot_widget
        
        import pyqtgraph as pg
        from PyQt5.QtCore import Qt
        
        # 1. Draw the Green Stars at the very tip of the peaks
        scatter = pg.ScatterPlotItem(x=peaks_x, y=peaks_y, size=14, pen=pg.mkPen('k', width=1.5), brush=pg.mkBrush('#00ff00'), symbol='star')
        target_vb.addItem(scatter)
        self.peak_markers.append((scatter, target_vb))
        
        # 2. Draw the horizontal FWHM lines (Red)
        for lx, rx, h in zip(left_x, right_x, width_heights):
            line = pg.PlotCurveItem(x=[lx, rx], y=[h, h], pen=pg.mkPen('r', width=2.5))
            target_vb.addItem(line)
            self.peak_markers.append((line, target_vb))
            
        # 3. Draw vertical dashed lines dropping down from the peak
        for px in peaks_x:
            vline = pg.InfiniteLine(pos=px, angle=90, pen=pg.mkPen((150, 150, 150, 150), style=Qt.DashLine))
            target_vb.addItem(vline)
            self.peak_markers.append((vline, target_vb))

    def clear_peak_markers(self):
        if hasattr(self, 'peak_markers'):
            for item, vb in self.peak_markers:
                try: vb.removeItem(item)
                except: pass
            self.peak_markers.clear()

    def _build_menu(self):
        menubar = self.menuBar()
        
        # --- NEW FILE MENU ---
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open File...", self)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)
        
        open_folder_action = QAction("Open Folder (Batch CSVs)...", self)
        open_folder_action.triggered.connect(self.open_folder)
        file_menu.addAction(open_folder_action)
        
        file_menu.addSeparator()
        
        self.concat_folder_action = QAction("Concatenate Loaded Folder into Single CSV...", self)
        self.concat_folder_action.triggered.connect(self.concatenate_folder)
        self.concat_folder_action.setEnabled(False) # Disabled by default
        file_menu.addAction(self.concat_folder_action)
        # ---------------------
        
        # --- NEW: EDIT MENU ---
        edit_menu = menubar.addMenu("Edit")
        prefs_action = QAction("Preferences...", self)
        prefs_action.triggered.connect(self.open_preferences)
        edit_menu.addAction(prefs_action)
        # ----------------------
    
        # Inspect Menu
        inspect_menu = menubar.addMenu("Inspect")
        self.inspect_table_action = inspect_menu.addAction("Sweep table")
        self.inspect_table_action.triggered.connect(self.prompt_sweep_table)
        inspect_menu.addAction("Rename / Delete columns").triggered.connect(self.manage_columns_dialog)
        inspect_menu.addAction("Create custom column").triggered.connect(self.prompt_create_column)
        inspect_menu.addSeparator()
        
        crosshair_action = QAction("Toggle crosshairs", self)
        crosshair_action.setShortcut("Ctrl+H") 
        crosshair_action.triggered.connect(self.toggle_crosshairs)
        inspect_menu.addAction(crosshair_action)
        
        # Analysis Menu
        analysis_menu = menubar.addMenu("Analysis")
        
        # Top-level items
        analysis_menu.addAction("Data Slicer (Split Non-Monotonic)").triggered.connect(self.open_data_slicer)
        analysis_menu.addAction("Signal Processing (Smooth / Calculus)").triggered.connect(self.open_signal_processing)
        analysis_menu.addAction("Baseline Subtraction Tool").triggered.connect(self.open_baseline_subtraction)
        analysis_menu.addAction("Phase Space Generator (x vs dx/dt)").triggered.connect(self.open_phase_space_dialog)
        
        analysis_menu.addSeparator()
        
        # Sub-menu 1: Fourier Analysis
        fourier_menu = analysis_menu.addMenu("Fourier Analysis")
        fourier_menu.addAction("Automated Peak Finder & iFFT Surgeon").triggered.connect(self.open_peak_finder)
        fourier_menu.addAction("Spectrogram / STFT (Time-Frequency)").triggered.connect(self.open_spectrogram)
        
        # Sub-menu 2: Area Calculators
        area_menu = analysis_menu.addMenu("Area Calculators")
        area_menu.addAction("Area Under Curve (Definite Integral)").triggered.connect(self.open_area_under_curve)
        area_menu.addAction("Enclosed Loop Area Calculator").triggered.connect(self.open_loop_area_calculator)
        
        # Layout Menu
        layout_menu = menubar.addMenu("Layout")
        layout_action = QAction("Plot Settings & Slicing...", self)
        layout_action.setShortcut("Ctrl+L")
        layout_action.triggered.connect(self.open_layout_dialog)
        layout_menu.addAction(layout_action)
    
        # Fitting Menu
        self.fitting_menu = menubar.addMenu("Fitting")
        self.fitting_menu.addAction("Fit common function to data").triggered.connect(self.open_fit_function_dialog)
        self.fitting_menu.addAction("Fit custom function to data").triggered.connect(self.open_custom_fit_dialog)
        self.fitting_menu.addAction("Fit data to function").triggered.connect(self.open_fit_data_to_function)

        # Plot Mode Menu
        plot_mode_menu = menubar.addMenu("Plot Mode")
        plot_mode_menu.addAction("2D Plot").triggered.connect(lambda: self.set_plot_mode("2D"))
        self.plot_3d_action = plot_mode_menu.addAction("3D Plot")
        self.plot_3d_action.triggered.connect(lambda: self.set_plot_mode("3D"))
        plot_mode_menu.addAction("Heat Map").triggered.connect(lambda: self.set_plot_mode("Heatmap"))
        plot_mode_menu.addAction("Histogram").triggered.connect(lambda: self.set_plot_mode("Histogram"))
        
        # Help Menu
        help_menu = menubar.addMenu("Help")
        help_action = QAction("How to use", self)
        help_action.triggered.connect(self.show_help)
        help_menu.addAction(help_action)

    def _update_selection_stats(self):
        if not getattr(self, 'selected_indices', set()):
            self.stats_label.hide()
            return
            
        x_sel, y_sel, _, pair = self._get_all_plotted_xy(apply_selection=True)
        if len(x_sel) < 2:
            self.stats_label.hide()
            return
            
        n_pts = len(y_sel)
        mean_y, std_y, min_y, max_y = np.mean(y_sel), np.std(y_sel), np.min(y_sel), np.max(y_sel)
        
        sort_idx = np.argsort(x_sel)
        try: area = np.trapezoid(y_sel[sort_idx], x=x_sel[sort_idx])
        except AttributeError: area = np.trapz(y_sel[sort_idx], x=x_sel[sort_idx])
        
        y_name = pair.get('y_name', 'Y Axis')
        html = f"<b style='color: #0055ff; font-size: 14px;'>{y_name} Region Stats</b><br><hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
        html += f"<b>Count (N):</b>&nbsp;&nbsp;&nbsp;&nbsp;{n_pts}<br><b>Mean (&mu;):</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{mean_y:.5g}<br>"
        html += f"<b>Std Dev (&sigma;):</b>&nbsp;&nbsp;{std_y:.5g}<br><b>Minimum:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{min_y:.5g}<br>"
        html += f"<b>Maximum:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{max_y:.5g}<br><b>Peak-to-Peak:</b> {max_y - min_y:.5g}<br>"
        html += f"<b>Integral (&int;):</b>&nbsp;{area:.5g}"
        
        self.stats_label.setText(html)
        self.stats_label.adjustSize()
        if not self.stats_label.isVisible(): self.stats_label.move(15, 15)
        self.stats_label.show()
        self.stats_label.raise_()

    def prompt_sweep_table(self):
        if not self.dataset: return
        if self.file_type == "CSV":
            SweepTableDialog(self.dataset, sweep=0, parent=self, is_csv=True).exec()
            return
    
        dialog = QDialog(self)
        dialog.setWindowTitle("Inspect sweep")
        dialog.setFixedSize(250, 120)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        sweep_edit = QLineEdit("0")
        form.addRow("Sweep number:", sweep_edit)
        layout.addLayout(form)
    
        buttons = QHBoxLayout()
        ok, cancel = QPushButton("OK"), QPushButton("Cancel")
        buttons.addStretch(); buttons.addWidget(ok); buttons.addWidget(cancel)
        layout.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)
    
        def accept():
            try: sw = int(sweep_edit.text())
            except ValueError: return
            if 0 <= sw < self.dataset.num_sweeps:
                dialog.accept()
                SweepTableDialog(self.dataset, sw, self, is_csv=False).exec()
        ok.clicked.connect(accept)
        dialog.exec()

    def confirm_permanent_change(self, message):
        if self.settings.value("suppress_rename_warning", False, bool): return True
        dialog = QDialog(self)
        dialog.setWindowTitle("Confirm change")
        dialog.setFixedSize(380, 150)
        layout = QVBoxLayout(dialog)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        checkbox = QPushButton("✓ Do not show this again")
        checkbox.setCheckable(True)
        checkbox.setChecked(False)
        layout.addWidget(checkbox, alignment=Qt.AlignLeft)
        buttons = QHBoxLayout()
        yes, no = QPushButton("Yes"), QPushButton("No")
        buttons.addStretch(); buttons.addWidget(yes); buttons.addWidget(no)
        layout.addLayout(buttons)
    
        def accept():
            if checkbox.isChecked(): self.settings.setValue("suppress_rename_warning", True)
            dialog.accept()
        yes.clicked.connect(accept)
        no.clicked.connect(dialog.reject)
        return dialog.exec() == QDialog.Accepted

    def show_help(self):
        HelpDialog(self).exec()
        
    def open_preferences(self):
        from ui.dialogs.settings import PreferencesDialog
        dlg = PreferencesDialog(self)
        
        was_portable = self.settings.value("portable_mode", False, bool)
        was_dark = self.settings.value("dark_mode", False, bool)
        
        if dlg.exec() == QDialog.Accepted:
            new_settings = dlg.get_results()
            
            # --- HANDLE PORTABLE MODE MIGRATION ---
            is_portable = new_settings["portable_mode"]
            local_ini = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "settings.ini")
            
            if is_portable and not was_portable:
                # Migrate System Registry -> Local INI
                new_settings_obj = QSettings(local_ini, QSettings.IniFormat)
                for key in self.settings.allKeys():
                    new_settings_obj.setValue(key, self.settings.value(key))
                self.settings = new_settings_obj
            elif not is_portable and was_portable:
                # Migrate Local INI -> System Registry
                new_settings_obj = QSettings("BadgerLoop", "QtPlotter")
                for key in self.settings.allKeys():
                    new_settings_obj.setValue(key, self.settings.value(key))
                self.settings = new_settings_obj
                if os.path.exists(local_ini):
                    try: os.remove(local_ini)
                    except: pass
            # --------------------------------------
            
            # Save the new values
            for key, val in new_settings.items():
                self.settings.setValue(key, val)
                
            # Apply live updates
            if hasattr(self, 'proxy'):
                self.proxy.disconnect() # Kill the old proxy
                # Rebuild it from scratch with the new rate limit
                self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved, rateLimit=new_settings["crosshair_poll_rate"], slot=self.mouse_moved)
                
            if new_settings["dark_mode"] != was_dark:
                QMessageBox.information(self, "Restart Required", "Theme changes will fully take effect after you restart the application.")
        
    def manage_columns_dialog(self):
        if not self.dataset: return
        
        # --- NEW FOLDER INTERCEPT ---
        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(self._show_actual_manage_columns_dialog)
            return
        # ----------------------------
            
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]
            target_file = None

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try:
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror file:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been automatically created.\n\nIt will now be loaded so you can safely modify columns.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("To protect original data, column changes must be made to a Mirror file.\nSelect an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    target_file = os.path.join(directory, f"MIRROR_{name_only} ({max_num + 1}){ext}")
                    try:
                        if self.file_type == "CSV": self._write_csv_mirror(target_file)
                        else:
                            import shutil
                            shutil.copy2(fname, target_file)
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to create mirror file:\n{e}")
                        return
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
            
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_manage_columns_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_manage_columns_dialog()

    def _show_actual_manage_columns_dialog(self):
        """ The standard dialog logic that actually applies the change to the safe file. """
        dlg = ManageColumnsDialog(self.dataset, self)
        if dlg.exec() != QDialog.Accepted: return
    
        action, col_idx, new_name = dlg.get_result()
        
        if action == "rename":
            if not new_name: return
            if not self.confirm_permanent_change(f"This will permanently change the column name in the mirror file:\n{os.path.basename(self.dataset.filename)}\n\nAre you sure?"): return
            self._rewrite_column_name_in_file(self.dataset.filename, col_idx, new_name)
            
        elif action == "delete":
            col_name = self.dataset.column_names.get(col_idx, "Unknown")
            ans = QMessageBox.warning(
                self, "Confirm Deletion", 
                f"Are you sure you want to permanently delete the column '{col_name}' from the mirror file?\n\nThis action is irreversible.", 
                QMessageBox.Yes | QMessageBox.No
            )
            if ans != QMessageBox.Yes: return
            self._delete_column_in_file(self.dataset.filename, col_idx)

        # Trigger full dataset reload to sync memory, arrays, and UI instantly
        opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
        self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setCancelButton(None)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        QApplication.processEvents()
        
        self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
        self.loader_thread.progress.connect(self._update_progress_ui)
        self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
        self.loader_thread.error.connect(self._on_load_error)
        self.loader_thread.start()

    def prompt_create_column(self):
        if not self.dataset: return
        
        # --- NEW FOLDER INTERCEPT ---
        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(self._show_actual_create_column_dialog)
            return
        # ----------------------------
        
        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                btn_box = QHBoxLayout()
                ok, cancel = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok); btn_box.addWidget(cancel)
                l.addLayout(btn_box)
                ok.clicked.connect(dlg.accept); cancel.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    target_file = os.path.join(directory, f"MIRROR_{name_only} ({max_num + 1}){ext}")
                    
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
            
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._show_actual_create_column_dialog() 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._show_actual_create_column_dialog()
        
    def _intercept_folder_edit(self, continue_callback):
        """ Checks if a folder is loaded and prompts the user for safety preferences. """
        orig_name = os.path.basename(self.dataset.filename)
        if orig_name.startswith("MIRROR_"):
            continue_callback()
            return
            
        from ui.dialogs.data_mgmt import FolderEditChoiceDialog
        choice = FolderEditChoiceDialog(self).exec()
        if choice == 0: return 
        
        if choice == 2:
            self.concatenate_folder()
            QMessageBox.information(self, "Concatenation Complete", "The folder has been stitched into a single file.\n\nPlease re-open the tool to apply your modifications.")
            return
            
        if choice == 1:
            self._create_mirror_folder(continue_callback)

    def _create_mirror_folder(self, callback):
        orig_folder = self.dataset.filename
        parent_dir = os.path.dirname(orig_folder)
        folder_name = os.path.basename(orig_folder)
        
        mirror_folder_name = f"MIRROR_{folder_name}"
        mirror_folder_path = os.path.join(parent_dir, mirror_folder_name)
        
        counter = 1
        while os.path.exists(mirror_folder_path):
            mirror_folder_name = f"MIRROR_{folder_name} ({counter})"
            mirror_folder_path = os.path.join(parent_dir, mirror_folder_name)
            counter += 1
            
        try:
            os.makedirs(mirror_folder_path)
            new_file_list = []
            for fpath in self.dataset.file_list:
                fname = os.path.basename(fpath)
                new_fpath = os.path.join(mirror_folder_path, f"MIRROR_{fname}")
                self._write_csv_mirror_from_existing(fpath, new_fpath)
                new_file_list.append(new_fpath)
                
            opts = getattr(self, 'last_load_opts', {"type": "MultiCSV", "delimiter": ",", "has_header": True})
            opts["file_list"] = new_file_list
            
            self.progress_dialog = QProgressDialog("Building Mirror Folder...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            def on_mirror_loaded(ds):
                self._on_load_finished(ds, mirror_folder_path, opts)
                callback() # Automatically continue to the math tool!
                
            self.loader_thread = DataLoaderThread(mirror_folder_path, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create mirror folder:\n{e}")

    def _write_csv_mirror_from_existing(self, src, dest):
        with open(src, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = f.readlines()
        import re
        has_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
        with open(dest, 'w', encoding='utf-8-sig', newline='') as f:
            if not has_flag: f.write("# Is Mirror File: Yes\n")
            f.writelines(lines)
        
    def _write_csv_mirror(self, filepath):
        import csv
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            if hasattr(self.dataset, 'notes') and self.dataset.notes:
                for line in self.dataset.notes.split('\n'):
                    clean_line = line.lstrip('#').strip()
                    if clean_line: f.write(f"#{clean_line}\n")
            
            if not hasattr(self.dataset, 'notes') or "Is Mirror File: Yes" not in getattr(self.dataset, 'notes', ''):
                f.write("# Is Mirror File: Yes\n")
                
            writer = csv.writer(f, delimiter=',')
            headers = [self.dataset.column_names.get(i, f"Column {i}") for i in range(self.dataset.num_inputs)]
            writer.writerow(headers)
            
            if hasattr(self.dataset, 'data') and self.dataset.data is not None:
                for row in self.dataset.data:
                    clean_row = ["" if np.isnan(val) else f"{val:.6g}" for val in row]
                    writer.writerow(clean_row)

    def _show_actual_create_column_dialog(self):
        dlg = CreateColumnDialog(self.dataset, self)
        if dlg.exec() != QDialog.Accepted: return
        new_col_name, raw_equation = dlg.get_equation_data()
        if not new_col_name or not raw_equation: return

        try:
            import re
            py_equation = raw_equation
            col_map = {v: k for k, v in self.dataset.column_names.items()}
            used_indices = []
            
            def replace_col(match):
                name = match.group(1)
                if name not in col_map: raise ValueError(f"Unknown column: [{name}]")
                idx = col_map[name]
                used_indices.append(idx)
                return f"data_dict[{idx}]"
                
            py_equation = re.sub(r'\[(.*?)\]', replace_col, py_equation)
    
            def replace_const_actual(match):
                c_key = match.group(1)
                if c_key not in PHYSICS_CONSTANTS: raise ValueError(f"Unknown constant: {{{c_key}}}")
                return f"({PHYSICS_CONSTANTS[c_key]['value']})"
                
            py_equation = re.sub(r'\{(.*?)\}', replace_const_actual, py_equation)
    
            py_equation = py_equation.replace('^', '**')
            py_equation = re.sub(r'\barcsinh\s*\(', 'np.arcsinh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barccosh\s*\(', 'np.arccosh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barctanh\s*\(', 'np.arctanh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barcsin\s*\(', 'np.arcsin(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barccos\s*\(', 'np.arccos(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\barctan\s*\(', 'np.arctan(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bsinh\s*\(', 'np.sinh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bcosh\s*\(', 'np.cosh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\btanh\s*\(', 'np.tanh(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bsin\s*\(', 'np.sin(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bcos\s*\(', 'np.cos(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\btan\s*\(', 'np.tan(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\blog_?2\s*\(', 'np.log2(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\blog\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
            py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)
            # --- NEW: ABSOLUTE VALUE ---
            py_equation = re.sub(r'\babs\s*\(', 'np.abs(', py_equation, flags=re.IGNORECASE)
    
            is_csv = (self.file_type == "CSV")
            calculated_data_blocks = []
            
            # --- NEW: NORMALIZATION ENGINE ---
            def norm_func(v):
                arr = np.asarray(v, dtype=np.float64)
                m = np.max(arr)
                return arr / m if m != 0 else arr
            # ---------------------------------
            
            with np.errstate(divide='ignore', invalid='ignore'):
                for sw in range(self.dataset.num_sweeps):
                    if is_csv: arr = self.dataset.data
                    else: arr = self.dataset.sweeps[sw].data
                        
                    data_dict = {idx: arr[:, idx] for idx in set(used_indices)}
                    index_arr = np.arange(arr.shape[0])
                    
                    # Inject norm_func into the math environment!
                    env = {"np": np, "data_dict": data_dict, "e": np.e, "pi": np.pi, "index": index_arr, "norm": norm_func}
                    result = eval(py_equation, {"__builtins__": {}}, env)
                    
                    if not isinstance(result, np.ndarray):
                        result = np.full(arr.shape[0], result)
                        
                    result = np.asarray(result, dtype=np.float64)
                    result[~np.isfinite(result)] = np.nan
                    calculated_data_blocks.append(result)
    
            self._append_column_to_file(self.dataset.filename, new_col_name, calculated_data_blocks)
            QMessageBox.information(self, "Success", f"Column '{new_col_name}' created and saved successfully.")
            
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
        except ValueError as ve:
            QMessageBox.critical(self, "Syntax Error", str(ve))
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Fatal Execution Error", f"The math engine or file writer encountered a critical error:\n\n{e}\n\nTraceback:\n{traceback.format_exc()}")

    def _append_column_to_file(self, target_file, new_name, calculated_blocks):
        # --- NEW: NATIVE HDF5 INTERCEPT ---
        if self.file_type == "HDF5":
            import h5py
            if hasattr(self.dataset, 'file') and self.dataset.file:
                try: self.dataset.file.close() # Free the Windows file lock
                except: pass
            with h5py.File(target_file, 'a') as f:
                if new_name in f: del f[new_name]
                data_to_write = np.concatenate(calculated_blocks) if len(calculated_blocks) > 1 else calculated_blocks[0]
                f.create_dataset(new_name, data=data_to_write)
            return
        # ----------------------------------

        if self.file_type == "MultiCSV":
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            for sw_idx, filepath in enumerate(self.dataset.file_list):
                with open(filepath, "r", encoding='utf-8-sig', errors='ignore') as f:
                    lines = f.readlines()
                    
                out = []
                data_row_idx = 0
                flat_calc = calculated_blocks[sw_idx]
                
                import re
                has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
                if not has_mirror_flag:
                    out.append("# Is Mirror File: Yes\n")
                    
                header_done = False
                for line in lines:
                    clean_line = line.rstrip('\r\n') 
                    if not clean_line or clean_line.startswith('#'): 
                        out.append(line)
                        continue
                        
                    if not header_done: 
                        out.append(f"{clean_line}{delim}{new_name}\n")
                        header_done = True
                    else: 
                        val = flat_calc[data_row_idx] if data_row_idx < len(flat_calc) else np.nan 
                        data_row_idx += 1
                        
                        # --- FIX ---
                        val_str = "" if np.isnan(val) else f"{val:.6g}"
                        out.append(f"{clean_line}{delim}{val_str}\n")
                        
                with open(filepath, "w", encoding='utf-8-sig') as f:
                    f.writelines(out)
                    
        elif self.file_type in ["CSV", "ConcatenatedCSV"]:
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = f.readlines()
                
            out = []
            import re
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                out.append("# Is Mirror File: Yes\n")
                
            header_done = False
            
            # Setup tracker for concatenated blocks
            sweep_idx = 0
            data_row_idx = 0
            flat_calc = calculated_blocks[0] if calculated_blocks else []
            
            for line in lines:
                clean_line = line.rstrip('\r\n') 
                if not clean_line or clean_line.startswith('#'): 
                    out.append(line)
                    # --- NEW: Shift blocks when passing a sweep divider ---
                    if "--- Sweep" in clean_line and self.file_type == "ConcatenatedCSV":
                        match = re.search(r'--- Sweep (\d+)', clean_line)
                        if match:
                            sweep_idx = int(match.group(1))
                            if sweep_idx < len(calculated_blocks):
                                flat_calc = calculated_blocks[sweep_idx]
                                data_row_idx = 0
                    # ------------------------------------------------------
                    continue
                    
                if not header_done: 
                    out.append(f"{clean_line}{delim}{new_name}\n")
                    header_done = True
                else: 
                    val = flat_calc[data_row_idx] if data_row_idx < len(flat_calc) else np.nan 
                    data_row_idx += 1
                    
                    # --- FIX ---
                    val_str = "" if np.isnan(val) else f"{val:.6g}"
                    out.append(f"{clean_line}{delim}{val_str}\n")
                    
            with open(target_file, "w", encoding='utf-8-sig') as f:
                f.writelines(out)
                
        else:
            with open(target_file, "r", encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            import re
            has_outputs = False
            for i in range(len(lines)):
                if lines[i].startswith("###"): break 
                match = re.search(r'(?i)^\s*outputs?[\s:=]+(\d+)', lines[i])
                if match:
                    num = int(match.group(1))
                    prefix = lines[i][:match.start(1)]
                    suffix = lines[i][match.end(1):]
                    lines[i] = f"{prefix}{num + 1}{suffix}"
                    has_outputs = True
                    break

            if not has_outputs:
                lines.insert(1, "Outputs: 1\n")
            
            out = []
            sweep_idx = 0
            point_idx = 0
            in_data = False
            has_outputs_section = False
            in_outputs_block = False
            
            target_col_idx = getattr(self.dataset, 'num_outputs', 0)
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False
            
            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}\n")
                    continue
                    
                if line.startswith("###NOTES"):
                    out.append(line)
                    if not has_mirror_flag:
                        out.append("Is Mirror File: Yes\n")
                        flag_injected = True
                    continue
                    
                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###\nIs Mirror File: Yes\n\n")
                        flag_injected = True

                if in_outputs_block and line.startswith("###"):
                    out.append(f"{new_name}\tBadgerLoop.CalculatedColumn\n")
                    in_outputs_block = False

                if line.startswith("###OUTPUTS"):
                    has_outputs_section = True
                    in_outputs_block = True
                    out.append(line)
                    continue
                    
                if line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_outputs_section:
                        out.append("###OUTPUTS###\n")
                        out.append(f"{new_name}\tBadgerLoop.CalculatedColumn\n")
                        has_outputs_section = True
                        
                    if line.startswith("###DATA") and not line.startswith("###DATA SET"):
                        in_data = True
                        out.append(line)
                        continue

                if in_outputs_block and not line.strip(): continue

                if in_data:
                    clean_line = line.rstrip('\r\n')
                    if '\t' in clean_line:
                        if sweep_idx < len(calculated_blocks) and point_idx >= len(calculated_blocks[sweep_idx]):
                            sweep_idx += 1
                            point_idx = 0
                            
                        if sweep_idx < len(calculated_blocks) and point_idx < len(calculated_blocks[sweep_idx]):
                            val = calculated_blocks[sweep_idx][point_idx]
                            point_idx += 1
                        else:
                            val = np.nan 
                            
                        parts = clean_line.split('\t')
                        
                        # --- FIX ---
                        val_str = "" if np.isnan(val) else f"{val:.6g}"
                        parts.insert(target_col_idx, val_str) 
                        out.append("\t".join(parts) + "\n")
                    else:
                        out.append(line) 
                else:
                    out.append(line)
                    
            with open(target_file, "w", encoding='utf-8') as f:
                f.writelines(out)

    def _rewrite_column_name_in_file(self, target_file, col_idx, new_name):
        # --- NEW: NATIVE HDF5 INTERCEPT ---
        if self.file_type == "HDF5":
            import h5py
            if hasattr(self.dataset, 'file') and self.dataset.file:
                try: self.dataset.file.close()
                except: pass
            with h5py.File(target_file, 'a') as f:
                old_name = self.dataset.column_names.get(col_idx)
                if old_name and old_name in f:
                    f[new_name] = f[old_name] # Copy to new name
                    del f[old_name]           # Delete old name
            return
        # ----------------------------------

        if self.file_type == "MultiCSV":
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            import csv, io, re
            
            for filepath in self.dataset.file_list:
                with open(filepath, "r", encoding='utf-8-sig', errors='ignore') as f:
                    lines = [l.rstrip('\r\n') for l in f.readlines()]
                if not lines: continue
                
                has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
                if not has_mirror_flag:
                    lines.insert(0, "# Is Mirror File: Yes")
                    
                header_idx = 0
                for i, line in enumerate(lines):
                    if line.strip() and not line.strip().startswith('#'):
                        header_idx = i
                        break
                        
                reader = csv.reader([lines[header_idx]], delimiter=delim)
                try: headers = next(reader)
                except StopIteration: continue
                    
                if col_idx < len(headers):
                    headers[col_idx] = new_name
                    
                out_buf = io.StringIO()
                csv.writer(out_buf, delimiter=delim).writerow(headers)
                lines[header_idx] = out_buf.getvalue().strip()
                
                with open(filepath, "w", encoding='utf-8') as f:
                    f.write("\n".join(lines) + "\n")
                    
        elif self.file_type in ["CSV", "ConcatenatedCSV"]:
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            import csv
            import io
            import re
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
            if not lines: return
            
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                lines.insert(0, "# Is Mirror File: Yes")
            
            header_idx = 0
            for i, line in enumerate(lines):
                if line.strip() and not line.strip().startswith('#'):
                    header_idx = i
                    break
                    
            reader = csv.reader([lines[header_idx]], delimiter=delim)
            try: headers = next(reader)
            except StopIteration: return
                
            if col_idx < len(headers):
                headers[col_idx] = new_name
            
            out_buf = io.StringIO()
            csv.writer(out_buf, delimiter=delim).writerow(headers)
            lines[header_idx] = out_buf.getvalue().strip()
            
            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(lines) + "\n")
                
        else:
            num_out = getattr(self.dataset, 'num_outputs', 0)
            num_inp = getattr(self.dataset, 'num_inputs', 0)
            has_time = (len(self.dataset.column_names) > num_out + num_inp)
            
            inst_idx = col_idx - 1 if has_time else col_idx
            enabled_names = [inst["name"] for inst in self.dataset.outputs] + [inst["name"] for inst in self.dataset.inputs]
            target_old_name = enabled_names[inst_idx] if 0 <= inst_idx < len(enabled_names) else None
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]

            out = []
            in_outputs = False
            in_inputs = False
            
            import re
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False
            
            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}")
                    continue
                    
                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###")
                        out.append("Is Mirror File: Yes")
                        out.append("")
                        flag_injected = True
                        
                if line.startswith("###OUTPUTS"):
                    in_outputs = True; in_inputs = False
                    out.append(line); continue
                if line.startswith("###INPUTS"):
                    in_inputs = True; in_outputs = False
                    out.append(line); continue
                if line.startswith("###DATA"):
                    in_outputs = False; in_inputs = False
                    out.append(line); continue
                    
                if (in_outputs or in_inputs) and line.strip():
                    parts = line.split("\t", 1)
                    if target_old_name and parts[0].strip() == target_old_name.strip():
                        parts[0] = new_name
                        line = parts[0] + ("\t" + parts[1] if len(parts) > 1 else "")
                        
                out.append(line)
                
            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(out) + "\n")

    def _delete_column_in_file(self, target_file, col_idx):
        # --- NEW: NATIVE HDF5 INTERCEPT ---
        if self.file_type == "HDF5":
            import h5py
            if hasattr(self.dataset, 'file') and self.dataset.file:
                try: self.dataset.file.close()
                except: pass
            with h5py.File(target_file, 'a') as f:
                col_name = self.dataset.column_names.get(col_idx)
                if col_name and col_name in f:
                    del f[col_name]
            return
        # ----------------------------------

        if self.file_type == "MultiCSV":
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            import csv, io, re
            
            for filepath in self.dataset.file_list:
                with open(filepath, "r", encoding='utf-8-sig', errors='ignore') as f:
                    lines = [l.rstrip('\r\n') for l in f.readlines()]
                if not lines: continue

                out = []
                has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
                if not has_mirror_flag:
                    out.append("# Is Mirror File: Yes")

                for line in lines:
                    if line.startswith('#') or not line.strip():
                        out.append(line)
                        continue
                    
                    parts = next(csv.reader([line], delimiter=delim))
                    if col_idx < len(parts):
                        parts.pop(col_idx)
                    
                    temp = io.StringIO()
                    csv.writer(temp, delimiter=delim).writerow(parts)
                    out.append(temp.getvalue().strip())
                    
                with open(filepath, "w", encoding='utf-8-sig') as f:
                    f.write("\n".join(out) + "\n")
                    
        elif self.file_type in ["CSV", "ConcatenatedCSV"]:
            delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
            if delim == "auto": delim = ","
            
            import csv
            import io
            import re
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
            if not lines: return

            out = []
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines[:15])
            if not has_mirror_flag:
                out.append("# Is Mirror File: Yes")

            for line in lines:
                if line.startswith('#') or not line.strip():
                    out.append(line)
                    continue
                
                parts = next(csv.reader([line], delimiter=delim))
                if col_idx < len(parts):
                    parts.pop(col_idx)
                
                temp = io.StringIO()
                csv.writer(temp, delimiter=delim).writerow(parts)
                out.append(temp.getvalue().strip())
                
            with open(target_file, "w", encoding='utf-8-sig') as f:
                f.write("\n".join(out) + "\n")
                
        else:
            num_out = getattr(self.dataset, 'num_outputs', 0)
            num_inp = getattr(self.dataset, 'num_inputs', 0)
            has_time = (len(self.dataset.column_names) > num_out + num_inp)
            
            inst_idx = col_idx - 1 if has_time else col_idx
            is_time = (inst_idx < 0)
            is_output = (0 <= inst_idx < num_out)
            
            enabled_names = [inst["name"] for inst in self.dataset.outputs] + [inst["name"] for inst in self.dataset.inputs]
            
            target_name = None
            if not is_time and 0 <= inst_idx < len(enabled_names):
                target_name = enabled_names[inst_idx]
            
            outputs_left = max(0, num_out - 1) if (not is_time and is_output) else num_out
            inputs_left = max(0, num_inp - 1) if (not is_time and not is_output) else num_inp
            
            with open(target_file, "r", encoding='utf-8-sig', errors='ignore') as f:
                lines = [l.rstrip('\r\n') for l in f.readlines()]
                
            out = []
            in_outputs = False
            in_inputs = False
            in_data = False
            
            import re
            target_base_name = os.path.splitext(os.path.basename(target_file))[0]
            has_mirror_flag = any(re.search(r'(?i)Is\s+Mirror\s+File\s*:\s*Yes', l) for l in lines)
            flag_injected = False
            
            for line in lines:
                if re.match(r'(?i)^Name\s*:', line):
                    out.append(f"Name: {target_base_name}")
                    continue
                    
                if line.startswith("###DISABLED") or line.startswith("###OUTPUTS") or line.startswith("###INPUTS") or (line.startswith("###DATA") and not line.startswith("###DATA SET")):
                    if not has_mirror_flag and not flag_injected:
                        out.append("###NOTES###")
                        out.append("Is Mirror File: Yes")
                        out.append("")
                        flag_injected = True
                        
                if not is_time:
                    if is_output and re.match(r'(?i)^\s*outputs?[\s:=]+(\d+)', line):
                        out.append(re.sub(r'(\d+)', str(outputs_left), line, count=1))
                        continue
                    if not is_output and re.match(r'(?i)^\s*inputs?[\s:=]+(\d+)', line):
                        out.append(re.sub(r'(\d+)', str(inputs_left), line, count=1))
                        continue
                        
                if line.startswith("###OUTPUTS"):
                    in_outputs = True; in_inputs = False; in_data = False
                    out.append(line); continue
                if line.startswith("###INPUTS"):
                    in_inputs = True; in_outputs = False; in_data = False
                    out.append(line); continue
                if line.startswith("###DATA") and not line.startswith("###DATA SET"):
                    in_data = True; in_outputs = False; in_inputs = False
                    out.append(line); continue
                    
                if (in_outputs or in_inputs) and line.strip() and target_name:
                    parts = line.split("\t", 1)
                    if parts[0].strip() == target_name.strip():
                        continue 
                        
                if in_data and line.strip() and not line.startswith("###"):
                    if ':' in line and '\t' not in line:
                        out.append(line)
                        continue
                        
                    parts = line.split('\t')
                    if col_idx < len(parts):
                        parts.pop(col_idx)
                    out.append("\t".join(parts))
                    continue
                    
                out.append(line)
                
            with open(target_file, "w", encoding='utf-8') as f:
                f.write("\n".join(out) + "\n")

    def _execute_universal_fit(self, base_model, param_names, param_config, x, y):
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
            return [param_config[p]["value"] for p in param_names]
            
        def dynamic_wrapper(x_val, *args):
            kwargs = dict(fixed_params)
            for name, val in zip(free_params, args):
                kwargs[name] = val
            full_args = [kwargs[p] for p in param_names]
            return base_model(x_val, *full_args)
            
        from scipy.optimize import curve_fit
        import warnings
        
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Naked SciPy execution exactly as the monolith did. No artificial traps!
            popt, _ = curve_fit(dynamic_wrapper, x, y, p0=p0, maxfev=20000)
            
        final_params = []
        popt_idx = 0
        for p in param_names:
            if p in free_params:
                final_params.append(popt[popt_idx])
                popt_idx += 1
            else:
                final_params.append(fixed_params[p])
                
        return final_params

    def open_fit_function_dialog(self):
        if not self.dataset: return
        dlg = FitFunctionDialog(self)
        if dlg.exec() != QDialog.Accepted: return
        func_type, degree_text, log_base_text, param_config = dlg.get_result()

        if func_type == "Polynomial":
            try:
                degree = int(degree_text)
                if degree < 0: raise ValueError
            except ValueError: return
            self.fit_polynomial(degree, param_config)
        elif func_type == "Logarithmic": self.fit_logarithmic(log_base_text, param_config)
        elif func_type == "Exponential": self.fit_exponential(param_config)
        elif func_type == "Gaussian": self.fit_gaussian(param_config)
        elif func_type == "Lorentzian": self.fit_lorentzian(param_config)
            
    def open_custom_fit_dialog(self):
        from PyQt5.QtWidgets import QDialog
        if not self.dataset: return
        dlg = CustomFitDialog(self.dataset, self)
        
        if dlg.exec() != QDialog.Accepted: 
            if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
            return
            
        if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
        
        raw_eq, py_eq, html_eq, used_cols, param_names, param_config = dlg.get_result()
        
        res_full = self._get_all_plotted_xy(aux_cols=used_cols, apply_selection=False)
        if len(res_full) < 4 or len(res_full[0]) == 0: return
        x_full, y_full, aux_full, pair = res_full
        
        import numpy as np
        
        # --- SAFE DICT ---
        safe_dict = aux_full if aux_full is not None else {}
        safe_aux_full = {}
        for c in used_cols:
            safe_aux_full[c] = safe_dict.get(c, np.zeros_like(x_full))
        # -----------------
        
        if getattr(self, 'selected_indices', set()):
            idx = sorted(list(self.selected_indices))
            valid_idx = [i for i in idx if i < len(x_full)]
            x_calc = x_full[valid_idx]
            y_calc = y_full[valid_idx]
            aux_calc = {c: safe_aux_full[c][valid_idx] for c in used_cols}
        else:
            x_calc = x_full
            y_calc = y_full
            aux_calc = safe_aux_full
        
        def custom_model_calc(x_val, *args):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "data_dict": aux_calc}
            for i, p in enumerate(param_names): env[p] = args[i]
            res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
            return res_arr

        try:
            final_params = self._execute_universal_fit(custom_model_calc, param_names, param_config, x_calc, y_calc)
        except Exception as e:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", f"{e}", self).exec()
            return

        sort_idx = np.argsort(x_full)
        x_sorted = x_full[sort_idx]
        sorted_aux = {c: safe_aux_full[c][sort_idx] for c in used_cols}
        
        def plot_model(x_arr, aux_arrs, *args):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x_arr, "data_dict": aux_arrs}
            for i, p in enumerate(param_names): env[p] = args[i]
            res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
            if res_arr.ndim == 0: res_arr = np.full_like(x_arr, float(res_arr))
            return res_arr
            
        yfit = plot_model(x_sorted, sorted_aux, *final_params)

        import pyqtgraph as pg
        from PyQt5.QtCore import Qt
        plot_item = self.plot_widget.plot(x_sorted, yfit, pen=pg.mkPen("r", width=2, style=Qt.DashLine))
        fit_name = f"Custom Fit ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(x_sorted, yfit) 
        self.active_fits.append({
            "name": fit_name, "type": "custom", 
            "params": final_params, "param_names": param_names,
            "plot_item": plot_item, "equation": raw_eq,
            "html_equation": html_eq, "raw_equation": raw_eq, 
            "param_config": param_config,
            "x_raw": x_raw, "y_raw": y_raw,
            # --- ADD THESE THREE LINES ---
            "x_idx": pair['x'], "aux_cols": used_cols,
            "callable": lambda x_arr, aux_arrs: plot_model(x_arr, aux_arrs, *final_params)
            # -----------------------------
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(True) # <--- AND THIS
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)

    def _get_all_plotted_xy(self, apply_selection=False, aux_cols=None):
        import numpy as np
        if not self.dataset: return np.array([]), np.array([]), {}, None
        row = max(0, self.series_list.currentRow())
        if row >= len(self.series_data["2D"]): return np.array([]), np.array([]), {}, None
        pair = self.series_data["2D"][row]
        
        if aux_cols is None: aux_cols = []
        
        # --- INTERCEPT FFT & HISTOGRAM MODES ---
        is_fft = getattr(self, 'fft_mode_active', False)
        is_hist = getattr(self, 'plot_mode', '2D') == "Histogram"

        if (is_fft or is_hist) and hasattr(self, 'last_plotted_data'):
            pkgs = [p for p in self.last_plotted_data.get('packages', []) if p.get("pair_idx", 0) == row and p.get("type") == "standard"]
            if pkgs:
                x_calc = pkgs[0]['x']
                y_calc = pkgs[0]['y']
                # Failsafe aux dict (aux cols aren't naturally FFT'd/Binned, so we return zeros to prevent NoneType)
                aux_dict = {c: np.zeros_like(x_calc) for c in aux_cols}
                if apply_selection and getattr(self, 'selected_indices', set()):
                    idx = np.array(list(self.selected_indices))
                    valid_idx = idx[idx < len(x_calc)]
                    return x_calc[valid_idx], y_calc[valid_idx], {c: v[valid_idx] for c, v in aux_dict.items()}, pair
                return x_calc, y_calc, aux_dict, pair

        xidx, yidx = pair['x'], pair['y']
        aux_dict = {}
        
        is_csv = (self.file_type in ["CSV", "ConcatenatedCSV"])
        is_averaged = (not is_csv) and getattr(self, 'average_enabled', False)
        
        xlog = self.xscale.currentText() == "Log"
        ylog = self.yscale.currentText() == "Log"
        xbase = getattr(self, '_parse_log_base', lambda val: 10.0)(self.xbase.text())
        ybase = getattr(self, '_parse_log_base', lambda val: 10.0)(self.ybase.text())
        
        if is_csv:
            x_raw = np.asarray(self.dataset.data[:, xidx], dtype=np.float64)
            y_raw = np.asarray(self.dataset.data[:, yidx], dtype=np.float64)
            c_raw_dict = {c: np.asarray(self.dataset.data[:, c], dtype=np.float64) for c in aux_cols}
            
            with np.errstate(divide='ignore', invalid='ignore'):
                if xlog: 
                    mask = x_raw > 0; x_raw = np.log(x_raw[mask]) / np.log(xbase); y_raw = y_raw[mask]
                    for c in aux_cols: c_raw_dict[c] = c_raw_dict[c][mask]
                if ylog: 
                    mask = y_raw > 0; x_raw = x_raw[mask]; y_raw = np.log(y_raw[mask]) / np.log(ybase)
                    for c in aux_cols: c_raw_dict[c] = c_raw_dict[c][mask]
                    
            valid = np.isfinite(x_raw) & np.isfinite(y_raw)
            x = x_raw[valid]
            y = y_raw[valid]
            for c in aux_cols: aux_dict[c] = c_raw_dict[c][valid]
        else:
            sweeps = self.parse_list(self.sweeps_edit.text())
            if sweeps == -1: sweeps = list(range(self.dataset.num_sweeps))
            
            x_list, y_list = [], []
            for c in aux_cols: aux_dict[c] = []

            for sw_idx in sweeps:
                if sw_idx >= len(self.dataset.sweeps): continue
                sw = self.dataset.sweeps[sw_idx].data
                x_raw = np.asarray(sw[:, xidx], dtype=np.float64)
                y_raw = np.asarray(sw[:, yidx], dtype=np.float64)
                
                c_raw_dict = {c: np.asarray(sw[:, c], dtype=np.float64) for c in aux_cols}
                    
                with np.errstate(divide='ignore', invalid='ignore'):
                    if xlog: 
                        mask = x_raw > 0; x_raw = np.log(x_raw[mask]) / np.log(xbase); y_raw = y_raw[mask]
                        for c in aux_cols: c_raw_dict[c] = c_raw_dict[c][mask]
                    if ylog: 
                        mask = y_raw > 0; x_raw = x_raw[mask]; y_raw = np.log(y_raw[mask]) / np.log(ybase)
                        for c in aux_cols: c_raw_dict[c] = c_raw_dict[c][mask]
                        
                valid = np.isfinite(x_raw) & np.isfinite(y_raw)
                x_valid = x_raw[valid]
                y_valid = y_raw[valid]
                
                if len(x_valid) == 0: continue
                
                # --- CRITICAL FIX: AVERAGE THE AUXILIARY COLUMNS TOO! ---
                if is_averaged:
                    x_list.append(np.array([np.mean(x_valid)]))
                    y_list.append(np.array([np.mean(y_valid)]))
                    for c in aux_cols:
                        aux_dict[c].append(np.array([np.mean(c_raw_dict[c][valid])]))
                else:
                    x_list.append(x_valid)
                    y_list.append(y_valid)
                    for c in aux_cols:
                        aux_dict[c].append(c_raw_dict[c][valid])
                    
            if x_list:
                x = np.concatenate(x_list)
                y = np.concatenate(y_list)
                for c in aux_cols: aux_dict[c] = np.concatenate(aux_dict[c])
            else:
                x, y = np.array([]), np.array([])
                for c in aux_cols: aux_dict[c] = np.array([])

        if apply_selection and getattr(self, 'selected_indices', set()):
            idx = np.array(list(self.selected_indices))
            valid_idx = idx[idx < len(x)]
            return x[valid_idx], y[valid_idx], {c: v[valid_idx] for c, v in aux_dict.items()}, pair
            
        return x, y, aux_dict, pair

    def edit_fit(self):
        if not getattr(self, 'active_fits', []): return
        if len(self.active_fits) == 1:
            idx = 0
            fit = self.active_fits[0]
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "Edit", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        if fit["type"] == "custom":
            from PyQt5.QtWidgets import QDialog
            dlg = CustomFitDialog(self.dataset, self)
            dlg.load_state(fit)
            
            if dlg.exec() == QDialog.Accepted:
                self.plot_widget.removeItem(fit["plot_item"])
                self.fit_legend.removeItem(fit["plot_item"])
                self.active_fits.pop(idx)
                
                if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
                
                raw_eq, py_eq, html_eq, used_cols, param_names, param_config = dlg.get_result()
                
                res_full = self._get_all_plotted_xy(aux_cols=used_cols, apply_selection=False)
                if len(res_full) < 4 or len(res_full[0]) == 0: return
                x_full, y_full, aux_full, pair = res_full
                
                import numpy as np
                
                # --- THE SAFETY NET ---
                if aux_full is None: aux_full = {}
                safe_aux_full = {}
                for c in used_cols:
                    if c in aux_full and aux_full[c] is not None:
                        safe_aux_full[c] = aux_full[c]
                    else:
                        safe_aux_full[c] = np.zeros_like(x_full)
                # ----------------------
                
                if getattr(self, 'selected_indices', set()):
                    idx = sorted(list(self.selected_indices))
                    x_calc = x_full[idx]
                    y_calc = y_full[idx]
                    aux_calc = {c: safe_aux_full[c][idx] for c in used_cols}
                else:
                    x_calc = x_full
                    y_calc = y_full
                    aux_calc = safe_aux_full
                
                def custom_model_calc(x_val, *args):
                    env = {"np": np, "e": np.e, "pi": np.pi, "x": x_val, "data_dict": aux_calc}
                    for i, p in enumerate(param_names): env[p] = args[i]
                    res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
                    if res_arr.ndim == 0: res_arr = np.full_like(x_val, float(res_arr))
                    return res_arr

                try:
                    final_params = self._execute_universal_fit(custom_model_calc, param_names, param_config, x_calc, y_calc)
                except Exception as e:
                    CopyableErrorDialog("Fitting Error", "Optimization failed.", f"{e}", self).exec()
                    return

                sort_idx = np.argsort(x_full)
                x_sorted = x_full[sort_idx]
                sorted_aux = {c: safe_aux_full[c][sort_idx] for c in used_cols}
                
                def plot_model(x_arr, aux_arrs, *args):
                    env = {"np": np, "e": np.e, "pi": np.pi, "x": x_arr, "data_dict": aux_arrs}
                    for i, p in enumerate(param_names): env[p] = args[i]
                    res_arr = np.asarray(eval(py_eq, {"__builtins__": {}}, env), dtype=np.float64)
                    if res_arr.ndim == 0: res_arr = np.full_like(x_arr, float(res_arr))
                    return res_arr

                yfit = plot_model(x_sorted, sorted_aux, *final_params)

                import pyqtgraph as pg
                from PyQt5.QtCore import Qt
                plot_item = self.plot_widget.plot(x_sorted, yfit, pen=pg.mkPen("r", width=2, style=Qt.DashLine))
                fit_name = f"Custom Fit ➔ {pair['y_name']}"
                self.fit_legend.addItem(plot_item, fit_name)

                x_raw, y_raw = self._get_raw_fit_coords(x_sorted, yfit) 
                self.active_fits.append({
                    "name": fit_name, "type": "custom", 
                    "params": final_params, "param_names": param_names,
                    "plot_item": plot_item, "equation": raw_eq,
                    "html_equation": html_eq, "raw_equation": raw_eq, 
                    "param_config": param_config,
                    "x_raw": x_raw, "y_raw": y_raw
                })
            else:
                if hasattr(self, 'phantom_curve'): self.phantom_curve.setVisible(False)
                
        else:
            dlg = FitFunctionDialog(self)
            dlg.load_state(fit)
            if dlg.exec() == QDialog.Accepted:
                self.plot_widget.removeItem(fit["plot_item"])
                self.fit_legend.removeItem(fit["plot_item"])
                self.active_fits.pop(idx)
                
                func_type, degree_text, log_base_text, param_config = dlg.get_result()
                if func_type == "Polynomial":
                    try:
                        degree = int(degree_text)
                        if degree >= 0: self.fit_polynomial(degree, param_config)
                    except ValueError: pass
                elif func_type == "Logarithmic": self.fit_logarithmic(log_base_text, param_config)
                elif func_type == "Exponential": self.fit_exponential(param_config)
                elif func_type == "Gaussian": self.fit_gaussian(param_config)
                elif func_type == "Lorentzian": self.fit_lorentzian(param_config)

    def _get_raw_fit_coords(self, x_vis, y_vis):
        xlog = self.xscale.currentText() == "Log"
        ylog = self.yscale.currentText() == "Log"
        xbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.xbase.text())
        ybase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.ybase.text())

        with np.errstate(over='ignore', invalid='ignore'):
            x_raw = np.power(xbase, x_vis) if xlog else np.array(x_vis, copy=True)
            y_raw = np.power(ybase, y_vis) if ylog else np.array(y_vis, copy=True)
        return x_raw, y_raw

    def fit_polynomial(self, degree, param_config):
        res = self._get_all_plotted_xy(apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        param_names = [f"c{i}" for i in range(degree + 1)]
        if all(param_config[p]["mode"] == "Auto" and param_config[p]["value"] == 1.0 for p in param_names):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                smart_p0 = np.polyfit(x, y, degree)
            for i, p in enumerate(param_names):
                param_config[p]["value"] = smart_p0[i]

        def model(x_val, *args):
            return sum(c * (x_val**(degree-i)) for i, c in enumerate(args))

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return
            
        poly = np.poly1d(final_params)
        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = poly(xfit)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Poly (deg {degree}) ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit) 
        self.active_fits.append({
            "name": fit_name, "type": "polynomial", "degree": degree,
            "coeffs": final_params, "callable": poly, "plot_item": plot_item,
            "equation": "y = " + " + ".join(f"{c:.3g}x^{i}" for i, c in enumerate(final_params[::-1])),
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw,
            "x_idx": pair['x']
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
        if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(True)

    def fit_logarithmic(self, base_text, param_config):
        res = self._get_all_plotted_xy(apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        if base_text.lower() == "e": base = np.e
        else:
            try:
                base = float(base_text)
                if base <= 0: raise ValueError
            except ValueError: return

        def model(x_val, a, c): return a * np.log(x_val) / np.log(base) + c
        param_names = ["a", "c"]

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(max(1e-15, x_full.min()), x_full.max(), 500) 
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Logarithmic ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "logarithmic", "base": base_text, "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw,
            "x_idx": pair['x']
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
        if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(True)

    def fit_exponential(self, param_config):
        res = self._get_all_plotted_xy(apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        def model(x_val, a, b, c): return a * np.exp(b * x_val) + c
        param_names = ["a", "b", "c"]

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Exponential ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "exponential", "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw,
            "x_idx": pair['x']
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
        if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(True)

    def fit_gaussian(self, param_config):
        res = self._get_all_plotted_xy(apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        def model(x_val, A, mu, sigma): return A * np.exp(-(x_val - mu)**2 / (2 * sigma**2))
        param_names = ["A", "mu", "sigma"]

        if param_config["A"]["mode"] == "Auto" and param_config["A"]["value"] == 1.0: param_config["A"]["value"] = y.max()
        if param_config["mu"]["mode"] == "Auto" and param_config["mu"]["value"] == 1.0: param_config["mu"]["value"] = x.mean()
        if param_config["sigma"]["mode"] == "Auto" and param_config["sigma"]["value"] == 1.0: param_config["sigma"]["value"] = np.std(x)

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Gaussian ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "gaussian", "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw,
            "x_idx": pair['x']
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
        if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(True)

    def fit_lorentzian(self, param_config):
        res = self._get_all_plotted_xy(apply_selection=True)
        if len(res) < 4 or len(res[0]) == 0: return
        x, y, _, pair = res

        def model(x_val, A, x0, gamma): return A / (1 + ((x_val - x0) / gamma)**2)
        param_names = ["A", "x0", "gamma"]

        if param_config["A"]["mode"] == "Auto" and param_config["A"]["value"] == 1.0: param_config["A"]["value"] = y.max()
        if param_config["x0"]["mode"] == "Auto" and param_config["x0"]["value"] == 1.0: param_config["x0"]["value"] = x.mean()
        if param_config["gamma"]["mode"] == "Auto" and param_config["gamma"]["value"] == 1.0: param_config["gamma"]["value"] = np.std(x)

        try: final_params = self._execute_universal_fit(model, param_names, param_config, x, y)
        except Exception:
            CopyableErrorDialog("Fitting Error", "Optimization failed.", "The parameters failed to converge. Try adjusting your Initial Guesses.", self).exec()
            return

        full_res = self._get_all_plotted_xy(apply_selection=False)
        x_full = full_res[0]
        xfit = np.linspace(x_full.min(), x_full.max(), 500)
        yfit = model(xfit, *final_params)

        plot_item = self.plot_widget.plot(xfit, yfit, pen=pg.mkPen("k", width=2, style=Qt.DashLine))
        fit_name = f"Lorentzian ➔ {pair['y_name']}"
        self.fit_legend.addItem(plot_item, fit_name)

        if not hasattr(self, 'active_fits'): self.active_fits = []
        x_raw, y_raw = self._get_raw_fit_coords(xfit, yfit)
        self.active_fits.append({
            "name": fit_name, "type": "lorentzian", "params": final_params,
            "callable": lambda v: model(v, *final_params), "plot_item": plot_item,
            "param_config": param_config, "x_raw": x_raw, "y_raw": y_raw,
            "x_idx": pair['x']
        })
        self.save_function_btn.setVisible(True); self.clear_fit_btn.setVisible(True); self.func_details_btn.setVisible(True)
        if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
        if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(True)

    def clear_fit(self):
        if not getattr(self, 'active_fits', []): return
        if len(self.active_fits) == 1:
            fit = self.active_fits.pop()
            self.plot_widget.removeItem(fit["plot_item"])
            self.fit_legend.removeItem(fit["plot_item"])
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "Delete", self)
            if dlg.exec() == QDialog.Accepted:
                res_type, idx = dlg.get_selection()
                if res_type == "all":
                    for fit in self.active_fits:
                        self.plot_widget.removeItem(fit["plot_item"])
                        self.fit_legend.removeItem(fit["plot_item"])
                    self.active_fits.clear()
                else:
                    fit = self.active_fits.pop(idx)
                    self.plot_widget.removeItem(fit["plot_item"])
                    self.fit_legend.removeItem(fit["plot_item"])
                    
        if not self.active_fits:
            self.save_function_btn.setVisible(False)
            if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(False)
            self.clear_fit_btn.setVisible(False)
            if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(False)
            if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(False)

    def save_function(self):
        if not getattr(self, 'active_fits', []): return
        if len(self.active_fits) == 1:
            fit = self.active_fits[0]
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "Save", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        fname, _ = QFileDialog.getSaveFileName(self, "Save Function", "", "Text files (*.txt)")
        if not fname: return
        if not fname.endswith(".txt"): fname += ".txt"

        with open(fname, "w") as f:
            f.write(f"{fit['type']}\n")
            if fit["type"] == "polynomial":
                f.write(f"degree: {fit['degree']}\n")
                for c in fit["coeffs"]: f.write(f"{c}\n")
            elif fit["type"] == "logarithmic":
                f.write(f"base: {fit['base']}\n")
                for p in fit["params"]: f.write(f"{p}\n")
            elif fit["type"] == "custom":
                f.write(f"{fit['raw_equation']}\n")
                f.write(",".join(fit['param_names']) + "\n")
                for p in fit["params"]: f.write(f"{p}\n")
            else:
                for p in fit["params"]: f.write(f"{p}\n")
                
    def export_fit_to_column(self):
        if not getattr(self, 'active_fits', []): return
        
        if len(self.active_fits) == 1:
            fit = self.active_fits[0]
        else:
            from ui.dialogs.fitting import MultiFitManagerDialog
            dlg = MultiFitManagerDialog(self.active_fits, "Export", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        from PyQt5.QtWidgets import QInputDialog, QLineEdit, QDialog, QVBoxLayout, QLabel, QComboBox, QHBoxLayout, QPushButton
        default_name = f"Fit_{fit['type'].capitalize()}"
        new_name, ok = QInputDialog.getText(self, "Export Fit", "Enter a name for the new column:", QLineEdit.Normal, default_name)
        if not ok or not new_name.strip(): return
        new_name = new_name.strip()

        if self.file_type == "MultiCSV":
            self._intercept_folder_edit(lambda: self._execute_export_fit_to_column(fit, new_name))
            return

        fname = self.dataset.filename
        orig_name = os.path.basename(fname)
        directory = os.path.dirname(fname)

        if not orig_name.startswith("MIRROR_") and self.file_type != "ConcatenatedCSV":
            name_only, ext = os.path.splitext(orig_name)
            import glob
            search_pattern = os.path.join(directory, f"MIRROR_{name_only}*{ext}")
            existing_mirrors = [os.path.basename(p) for p in glob.glob(search_pattern)]

            if not existing_mirrors:
                target_file = os.path.join(directory, f"MIRROR_{orig_name}")
                try: 
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to create mirror:\n{e}")
                    return
                QMessageBox.information(self, "Mirror Created", "To protect original data, a Mirror file has been created and loaded.")
            else:
                dlg = QDialog(self)
                dlg.setWindowTitle("Mirror File Exists")
                dlg.setFixedSize(450, 150)
                l = QVBoxLayout(dlg)
                l.addWidget(QLabel("Select an existing mirror to load, or create a new one:"))
                combo = QComboBox()
                combo.addItem("--- Create New Mirror ---")
                combo.addItems(existing_mirrors)
                l.addWidget(combo)
                btn_box = QHBoxLayout()
                ok_btn, cancel_btn = QPushButton("OK"), QPushButton("Cancel")
                btn_box.addWidget(ok_btn); btn_box.addWidget(cancel_btn)
                l.addLayout(btn_box)
                ok_btn.clicked.connect(dlg.accept); cancel_btn.clicked.connect(dlg.reject)
                if dlg.exec() != QDialog.Accepted: return
                
                choice = combo.currentText()
                if choice == "--- Create New Mirror ---":
                    import re
                    max_num = max([int(m.group(1)) for m in [re.search(r'\((\d+)\)', x) for x in existing_mirrors] if m] + [1 if f"MIRROR_{orig_name}" in existing_mirrors else 0])
                    target_file = os.path.join(directory, f"MIRROR_{name_only} ({max_num + 1}){ext}")
                    if self.file_type == "CSV": self._write_csv_mirror(target_file)
                    else:
                        import shutil
                        shutil.copy2(fname, target_file)
                else:
                    target_file = os.path.join(directory, choice)

            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            if self.file_type == "CSV": opts["delimiter"] = ","
            
            self.progress_dialog = QProgressDialog("Loading Mirror File...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()

            def on_mirror_loaded(dataset):
                self._on_load_finished(dataset, target_file, opts)
                self._execute_export_fit_to_column(fit, new_name) 

            self.loader_thread = DataLoaderThread(target_file, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(on_mirror_loaded)
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            return

        self._execute_export_fit_to_column(fit, new_name)

    def _execute_export_fit_to_column(self, fit, new_name):
        is_csv = (self.file_type == "CSV")
        sweeps = range(self.dataset.num_sweeps) if not is_csv else [0]
        
        calculated_data_blocks = []
        x_idx = fit.get("x_idx", 0)
        
        for sw in sweeps:
            arr = self.dataset.data if is_csv else self.dataset.sweeps[sw].data
            x_raw = np.asarray(arr[:, x_idx], dtype=np.float64)
            
            # Evaluate the function directly on the exact physical X-coordinates
            with np.errstate(all='ignore'):
                if fit["type"] == "custom":
                    aux_cols = fit.get("aux_cols", [])
                    aux_dict = {c: np.asarray(arr[:, c], dtype=np.float64) for c in aux_cols}
                    y_calc = fit["callable"](x_raw, aux_dict)
                else:
                    y_calc = fit["callable"](x_raw)
                    
            if not isinstance(y_calc, np.ndarray):
                y_calc = np.full(len(x_raw), y_calc)
                
            y_calc = np.asarray(y_calc, dtype=np.float64)
            y_calc[~np.isfinite(y_calc)] = np.nan
            
            calculated_data_blocks.append(y_calc)
            
        try:
            self._append_column_to_file(self.dataset.filename, new_name, calculated_data_blocks)
            
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(self, "Success", f"Fit exported to column '{new_name}' successfully.")
            
            opts = getattr(self, 'last_load_opts', {"type": self.file_type, "delimiter": ",", "has_header": True})
            self.progress_dialog = QProgressDialog("Refreshing Data...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None)
            self.progress_dialog.setMinimumDuration(0)
            self.progress_dialog.show()
            QApplication.processEvents()
            
            self.loader_thread = DataLoaderThread(self.dataset.filename, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, self.dataset.filename, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Execution Error", f"Failed to export fit:\n\n{e}\n\n{traceback.format_exc()}")

    def open_fit_data_to_function(self):
        if not self.dataset: return
        win = FitDataToFunctionWindow(self.dataset, self)
        win.show()

    def open_layout_dialog(self):
        self.layout_dialog.show()
        self.layout_dialog.raise_()
        self.layout_dialog.activateWindow()
        
    def _update_graphtype_dropdown(self):
        """ Dynamically updates the available Graph Types based on the current Plot Mode """
        current_selection = self.graphtype.currentText()
        
        self.graphtype.blockSignals(True)
        self.graphtype.clear()
        
        if self.plot_mode == "2D":
            self.graphtype.addItems(["Line", "Scatter"]) # FFT removed! Handled globally now.
        elif self.plot_mode == "3D":
            self.graphtype.addItems(["Line", "Scatter"])
        elif self.plot_mode == "Heatmap":
            self.graphtype.addItems(["Heatmap Default"])
            
        index = self.graphtype.findText(current_selection)
        if index >= 0:
            self.graphtype.setCurrentIndex(index)
        else:
            self.graphtype.setCurrentIndex(0)
            
        self.graphtype.blockSignals(False)
        self._update_graphtype_ui()
        
    def _update_graphtype_ui(self):
        is_heatmap = (self.plot_mode == "Heatmap")
        is_surface = (self.plot_mode == "3D" and hasattr(self, 'gl_surface_cb') and self.gl_surface_cb.isChecked())
        self.heatmap_cmap.setVisible(is_heatmap or is_surface)
        self.heatmap_cmap_label.setVisible(is_heatmap or is_surface)
        
    def _build_settings_dialog(self):
        self.layout_dialog = QDialog(self)
        self.layout_dialog.setWindowTitle("Plot Settings & Formatting")
        self.layout_dialog.setMinimumWidth(450)
        ld_layout = QVBoxLayout(self.layout_dialog)

        tabs = QTabWidget()
        ld_layout.addWidget(tabs)

        # -- TAB 1: Canvas --
        tab1 = QWidget()
        l1 = QFormLayout(tab1)
        
        self.axis_thick_slider = QSlider(Qt.Horizontal)
        self.axis_thick_slider.setRange(1, 10)
        self.axis_thick_slider.setValue(1)
        self.axis_thick_slider.setTickPosition(QSlider.TicksBelow)
        self.axis_thick_slider.setTickInterval(1)
        
        self.axis_thick_label = QLabel("1 px")
        
        thick_lay = QHBoxLayout()
        thick_lay.addWidget(self.axis_thick_slider)
        thick_lay.addWidget(self.axis_thick_label)
        
        self.axis_thick_slider.valueChanged.connect(self._on_axis_thick_changed)
        l1.addRow("Axis Line Thickness:", thick_lay)

        # --- RESTORED GRID LINES ---
        grid_lay = QHBoxLayout()
        self.grid_x_cb = QCheckBox("X Grid"); self.grid_x_cb.setChecked(True)
        self.grid_y_cb = QCheckBox("Y Grid"); self.grid_y_cb.setChecked(True)
        self.grid_alpha_edit = QLineEdit("0.35")
        self.grid_alpha_edit.setFixedWidth(50)
        grid_lay.addWidget(self.grid_x_cb); grid_lay.addWidget(self.grid_y_cb)
        grid_lay.addWidget(QLabel("Opacity:")); grid_lay.addWidget(self.grid_alpha_edit)
        l1.addRow("Grid Lines:", grid_lay)
        # ---------------------------

        self.bg_color_combo = QComboBox()
        self.bg_color_combo.addItems(["White", "Black", "Transparent"])
        l1.addRow("Background Color:", self.bg_color_combo)

        self.aspect_combo = QComboBox(); self.aspect_combo.addItems(["Free", "1:1", "4:3", "16:9", "Custom"])
        self.aspect_w_edit = QLineEdit("16"); self.aspect_h_edit = QLineEdit("9")
        self.aspect_colon = QLabel(":")
        cust_asp = QHBoxLayout()
        cust_asp.addWidget(self.aspect_combo); cust_asp.addWidget(self.aspect_w_edit)
        cust_asp.addWidget(self.aspect_colon); cust_asp.addWidget(self.aspect_h_edit)
        self.aspect_w_edit.setVisible(False); self.aspect_h_edit.setVisible(False); self.aspect_colon.setVisible(False)
        self.aspect_combo.currentTextChanged.connect(self._update_aspect_ui)
        self.aspect_w_edit.textChanged.connect(self._resize_plot_widget)
        self.aspect_h_edit.textChanged.connect(self._resize_plot_widget)
        l1.addRow("Aspect Ratio:", cust_asp)
        tabs.addTab(tab1, "Canvas")

        # -- TAB 2: Fonts --
        tab2 = QWidget()
        l2 = QFormLayout(tab2)
        self.font_family_combo = QFontComboBox()
        l2.addRow("Font Family:", self.font_family_combo)
        self.label_fontsize_edit = QLineEdit("14")
        l2.addRow("Axis Label Size:", self.label_fontsize_edit)
        self.tick_fontsize_edit = QLineEdit("11")
        l2.addRow("Tick Number Size:", self.tick_fontsize_edit)
        self.legend_fontsize_edit = QLineEdit("11")
        l2.addRow("Legend Text Size:", self.legend_fontsize_edit)
        tabs.addTab(tab2, "Typography")

        # -- TAB 3: Traces --
        tab3 = QWidget()
        l3 = QFormLayout(tab3)
        
        # --- NEW: Explanation Label ---
        info_lbl = QLabel("<i>Settings here act as defaults for newly added traces.<br>Use the ⚙️ icon in the Active Series list to override them individually.</i>")
        info_lbl.setWordWrap(True)
        l3.addRow(info_lbl)
        # ------------------------------

        self.graphtype = QComboBox()
        self.graphtype.addItems(["Line", "Scatter", "Line + Scatter", "Surface"]) 
        self.graphtype.currentTextChanged.connect(self._update_graphtype_ui)
        l3.addRow("Default Graph Type:", self.graphtype)
        # ... (keep the rest of Tab 3 the same) ...
        tabs.addTab(tab3, "Default Trace Styles") # <--- Renamed Tab

        self.line_thickness_edit = QLineEdit("2")
        l3.addRow("Line Thickness:", self.line_thickness_edit)

        self.point_size_edit = QLineEdit("5")
        l3.addRow("Scatter Point Size:", self.point_size_edit)

        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(["Circle (o)", "Square (s)", "Triangle (t)", "Star (star)", "Cross (+)", "X (x)"])
        l3.addRow("Scatter Symbol:", self.symbol_combo)

        self.heatmap_cmap = QComboBox()
        self.heatmap_cmap.addItems(["viridis", "plasma", "inferno", "magma", "cividis", "jet", "gray"])
        self.heatmap_cmap.currentTextChanged.connect(self.plot)
        self.heatmap_cmap_label = QLabel("Heatmap Colormap:")
        l3.addRow(self.heatmap_cmap_label, self.heatmap_cmap)
        tabs.addTab(tab3, "Traces")

        # -- TAB 4: Slicing & Scales --
        tab4 = QWidget()
        l4 = QFormLayout(tab4)
        
        self.xscale = QComboBox(); self.xscale.addItems(["Linear", "Log"]); self.xscale.currentTextChanged.connect(self._update_xscale_ui)
        self.xbase = QLineEdit("10")
        x_lay = QHBoxLayout(); x_lay.addWidget(self.xscale); x_lay.addWidget(self.xbase)
        l4.addRow("X Axis Scale:", x_lay)

        self.yscale = QComboBox(); self.yscale.addItems(["Linear", "Log"]); self.yscale.currentTextChanged.connect(self._update_yscale_ui)
        self.ybase = QLineEdit("10")
        y_lay = QHBoxLayout(); y_lay.addWidget(self.yscale); y_lay.addWidget(self.ybase)
        l4.addRow("Y Axis Scale:", y_lay)

        self.zscale = QComboBox(); self.zscale.addItems(["Linear", "Log"]); self.zscale.currentTextChanged.connect(self._update_zscale_ui)
        self.zbase = QLineEdit("10")
        self.zscale_label = QLabel("Z Axis Scale:")
        z_lay = QHBoxLayout(); z_lay.addWidget(self.zscale); z_lay.addWidget(self.zbase)
        l4.addRow(self.zscale_label, z_lay)

        self.sweeps_edit = QLineEdit("-1")
        self.sweeps_label = QLabel("Sweeps (e.g. 0,2,4 or 0:5):")
        l4.addRow(self.sweeps_label, self.sweeps_edit)
        self.points_edit = QLineEdit("-1")
        l4.addRow("Points (e.g. 100:500):", self.points_edit)
        self.bins_edit = QLineEdit("auto")
        self.bins_label = QLabel("Histogram Bins:")
        l4.addRow(self.bins_label, self.bins_edit)
        tabs.addTab(tab4, "Data & Scales")
        
        # -- TAB 5: 3D Options --
        tab5 = QWidget()
        l5 = QFormLayout(tab5)
        
        # --- NEW: SURFACE CHECKBOX ---
        self.gl_surface_cb = QCheckBox("Draw as 3D Surface (Mesh)")
        self.gl_surface_cb.stateChanged.connect(self._update_graphtype_ui)
        self.gl_surface_cb.stateChanged.connect(self.plot)
        l5.addRow("Plot Style:", self.gl_surface_cb)
        
        self.gl_surface_snap_cb = QCheckBox("Snap to raw data points (Surface Mode)")
        l5.addRow("", self.gl_surface_snap_cb)
        # -----------------------------
        
        from PyQt5.QtWidgets import QDoubleSpinBox
        self.gl_scale_x = QDoubleSpinBox(); self.gl_scale_x.setRange(0.01, 100); self.gl_scale_x.setValue(1.0); self.gl_scale_x.setSingleStep(0.1)
        self.gl_scale_y = QDoubleSpinBox(); self.gl_scale_y.setRange(0.01, 100); self.gl_scale_y.setValue(1.0); self.gl_scale_y.setSingleStep(0.1)
        self.gl_scale_z = QDoubleSpinBox(); self.gl_scale_z.setRange(0.01, 100); self.gl_scale_z.setValue(1.0); self.gl_scale_z.setSingleStep(0.1)
        
        scale_lay = QHBoxLayout()
        scale_lay.addWidget(QLabel("X:")); scale_lay.addWidget(self.gl_scale_x)
        scale_lay.addWidget(QLabel("Y:")); scale_lay.addWidget(self.gl_scale_y)
        scale_lay.addWidget(QLabel("Z:")); scale_lay.addWidget(self.gl_scale_z)
        l5.addRow("Independent Axis Scale:", scale_lay)

        self.gl_lighting_cb = QCheckBox("Enable Directional Lighting (Surface Plots)")
        self.gl_lighting_cb.setChecked(True)
        l5.addRow("Shading:", self.gl_lighting_cb)

        self.gl_stem_cb = QCheckBox("Draw Drop Lines to Floor (Scatter/Line Plots)")
        l5.addRow("Depth Cues:", self.gl_stem_cb)

        # --- NEW: HTML LABEL BUTTONS ---
        lbl_lay = QHBoxLayout()
        btn_x_lbl = QPushButton("Edit X Label")
        btn_y_lbl = QPushButton("Edit Y Label")
        btn_z_lbl = QPushButton("Edit Z Label")
        
        btn_x_lbl.clicked.connect(lambda: self._edit_3d_axis_label("x_3d"))
        btn_y_lbl.clicked.connect(lambda: self._edit_3d_axis_label("y_3d"))
        btn_z_lbl.clicked.connect(lambda: self._edit_3d_axis_label("z_3d"))
        
        lbl_lay.addWidget(btn_x_lbl)
        lbl_lay.addWidget(btn_y_lbl)
        lbl_lay.addWidget(btn_z_lbl)
        l5.addRow("HTML Axis Labels:", lbl_lay)
        # -------------------------------

        tabs.addTab(tab5, "3D Options")

        # -- Action Buttons --
        btn_lay = QHBoxLayout()
        save_def_btn = QPushButton("Save Defaults")
        save_def_btn.clicked.connect(self._save_formatting_defaults)
        apply_btn = QPushButton("Apply Settings")
        apply_btn.setStyleSheet("font-weight: bold; background-color: #0055ff; color: white; padding: 6px;")
        apply_btn.clicked.connect(self.plot)
        
        btn_lay.addWidget(save_def_btn)
        btn_lay.addStretch()
        btn_lay.addWidget(apply_btn)
        ld_layout.addLayout(btn_lay)
        
        # -- TAB 6: Legend Cosmetics --
        tab6 = QWidget()
        l6 = QFormLayout(tab6)
        
        self.leg_cols = QSpinBox()
        self.leg_cols.setRange(1, 10)
        self.leg_cols.setValue(1)
        
        self.leg_opacity = QSlider(Qt.Horizontal)
        self.leg_opacity.setRange(0, 255)
        self.leg_opacity.setValue(230)
        
        self.leg_border = QDoubleSpinBox()
        self.leg_border.setRange(0, 10)
        self.leg_border.setSingleStep(0.5)
        self.leg_border.setValue(1.5)
        
        self.leg_spacing = QSpinBox()
        self.leg_spacing.setRange(0, 50)
        self.leg_spacing.setValue(0)
        
        l6.addRow("Column Count:", self.leg_cols)
        l6.addRow("Background Opacity (0-255):", self.leg_opacity)
        l6.addRow("Border Thickness:", self.leg_border)
        l6.addRow("Item Spacing:", self.leg_spacing)
        
        # --- NEW: Connect for real-time live updates ---
        self.leg_cols.valueChanged.connect(self._apply_legend_live)
        self.leg_opacity.valueChanged.connect(self._apply_legend_live)
        self.leg_border.valueChanged.connect(self._apply_legend_live)
        self.leg_spacing.valueChanged.connect(self._apply_legend_live)
        self.bg_color_combo.currentTextChanged.connect(self._apply_legend_live)
        # -----------------------------------------------
        
        tabs.addTab(tab6, "Legend Cosmetics")
        
    def _edit_3d_axis_label(self, axis_key):
        # Determine fallback name based on current selected columns
        if axis_key == "x_3d": default = self.dataset.column_names.get(max(0, self.xcol.currentIndex()), "X")
        elif axis_key == "y_3d": default = self.dataset.column_names.get(max(0, self.ycol.currentIndex()), "Y")
        else: default = self.dataset.column_names.get(max(0, self.zcol.currentIndex()), "Z")

        current_data = self.custom_axis_labels.get(axis_key)
        if isinstance(current_data, dict): current_raw = current_data.get("raw", "")
        else: current_raw = current_data or "" 
            
        dlg = RichTextAxisLabelDialog(axis_key.replace('_3d', ''), current_raw, self)
        if dlg.exec() == QDialog.Accepted:
            raw_text, html_text = dlg.get_result()
            if raw_text: self.custom_axis_labels[axis_key] = {"raw": raw_text, "html": html_text}
            else: self.custom_axis_labels[axis_key] = None
            
            if self.plot_mode == "3D": 
                self.plot() # Instantly apply it!
        
    def _on_axis_thick_changed(self, val):
        self.axis_thick_label.setText(f"{val} px")
        self._apply_axis_fonts() # Instantly applies it without a full replot!

    def _save_formatting_defaults(self):
        self.settings.setValue("axis_thickness", self.axis_thick_slider.value())
        self.settings.setValue("grid_x", self.grid_x_cb.isChecked())
        self.settings.setValue("grid_y", self.grid_y_cb.isChecked())
        self.settings.setValue("grid_alpha", self.grid_alpha_edit.text())
        self.settings.setValue("bg_color", self.bg_color_combo.currentText())
        self.settings.setValue("font_family", self.font_family_combo.currentFont().family())
        self.settings.setValue("legend_fontsize", self.legend_fontsize_edit.text())
        self.settings.setValue("line_thickness", self.line_thickness_edit.text())
        self.settings.setValue("symbol", self.symbol_combo.currentText())
        self.settings.setValue("gl_scale_x", self.gl_scale_x.value())
        self.settings.setValue("gl_scale_y", self.gl_scale_y.value())
        self.settings.setValue("gl_scale_z", self.gl_scale_z.value())
        self.settings.setValue("gl_lighting", self.gl_lighting_cb.isChecked())
        self.settings.setValue("gl_stem", self.gl_stem_cb.isChecked())
        self.settings.setValue("leg_cols", self.leg_cols.value())
        self.settings.setValue("leg_opacity", self.leg_opacity.value())
        self.settings.setValue("leg_border", self.leg_border.value())
        self.settings.setValue("leg_spacing", self.leg_spacing.value())
        QMessageBox.information(self, "Saved", "Plot formatting defaults saved successfully.\nThey will automatically load next time you launch EggPlot.")

    def _apply_canvas_settings(self):
        # 1. Background
        bg = self.bg_color_combo.currentText()
        if bg == "White": 
            self.plot_widget.setBackground("w")
            if getattr(self, 'gl_widget', None): self.gl_widget.setBackgroundColor('w')
        elif bg == "Black": 
            self.plot_widget.setBackground("k")
            if getattr(self, 'gl_widget', None): self.gl_widget.setBackgroundColor('k')
        else: 
            self.plot_widget.setBackground(None) 
            # GLViewWidget doesn't handle pure transparency well over UI elements, so fallback to theme background
            if getattr(self, 'gl_widget', None): 
                theme_bg = '#353535' if self.settings.value("dark_mode", False, bool) else '#f5f5f5'
                self.gl_widget.setBackgroundColor(theme_bg)
        
        # 2. Grid
        try: alpha = float(self.grid_alpha_edit.text())
        except: alpha = 0.35
        self.plot_widget.showGrid(x=self.grid_x_cb.isChecked(), y=self.grid_y_cb.isChecked(), alpha=alpha)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main = QHBoxLayout(central)
        
        self._build_settings_dialog()

        controls = QVBoxLayout()
        main.addLayout(controls, 0)
        
        def button(text, slot):
            b = QPushButton(text)
            b.clicked.connect(slot)
            return b
                     
        self.show_metadata_btn = button("Show Metadata", self.show_metadata)
        controls.addWidget(self.show_metadata_btn)
        
        self.toggle_legend_btn = QPushButton("Toggle Legend")
        self.toggle_legend_btn.setCheckable(True)
        self.toggle_legend_btn.setChecked(True) # Legend is visible by default
        self.toggle_legend_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
        self.toggle_legend_btn.clicked.connect(self.toggle_legend)
        controls.addWidget(self.toggle_legend_btn)
        
        # --- NEW: HISTOGRAM STATS TOGGLE ---
        self.toggle_stats_btn = QPushButton("Toggle Histogram Stats")
        self.toggle_stats_btn.setCheckable(True)
        self.toggle_stats_btn.setChecked(True)
        self.toggle_stats_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
        self.toggle_stats_btn.setVisible(False) 
        self.toggle_stats_btn.clicked.connect(self._toggle_hist_stats)
        controls.addWidget(self.toggle_stats_btn)
        # -----------------------------------
        
        # --- NEW: LOOP AREAS TOGGLE ---
        self.toggle_loop_btn = QPushButton("Toggle Loop Areas")
        self.toggle_loop_btn.setCheckable(True)
        self.toggle_loop_btn.setChecked(True)
        self.toggle_loop_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
        self.toggle_loop_btn.setVisible(False) 
        self.toggle_loop_btn.clicked.connect(self._toggle_loop_areas)
        controls.addWidget(self.toggle_loop_btn)
        # ------------------------------
        
        self.toggle_avg_btn = button("Toggle Averaging", self.toggle_averaging)
        controls.addWidget(self.toggle_avg_btn)
        
        self.toggle_uncert_btn = button("Toggle Uncertainties", self.toggle_csv_uncertainties)
        self.toggle_uncert_btn.setVisible(False)
        controls.addWidget(self.toggle_uncert_btn)
        
        self.errorbar_btn = QPushButton("Toggle Error Bars")
        self.errorbar_btn.setCheckable(True)
        self.errorbar_btn.clicked.connect(self.toggle_errorbars)
        self.errorbar_btn.setVisible(False)
        controls.addWidget(self.errorbar_btn)
        
        controls.addWidget(QLabel("Error bar sigma multiplier"))
        self.errorbar_sigma_edit = QLineEdit("1.0")
        self.errorbar_sigma_edit.setVisible(False)
        controls.addWidget(self.errorbar_sigma_edit)
    
        controls.addSpacing(10)
        self.xcol_label = QLabel("X column")
        controls.addWidget(self.xcol_label)
        self.xcol = QComboBox()
        controls.addWidget(self.xcol)
        self.xuncert_label = QLabel(" ↳ X Uncertainty")
        self.xuncert = QComboBox()
        controls.addWidget(self.xuncert_label)
        controls.addWidget(self.xuncert)
    
        self.ycol_label = QLabel("Y column")
        controls.addWidget(self.ycol_label)
        self.ycol = QComboBox()
        controls.addWidget(self.ycol)
        self.yuncert_label = QLabel(" ↳ Y Uncertainty")
        self.yuncert = QComboBox()
        controls.addWidget(self.yuncert_label)
        controls.addWidget(self.yuncert)
    
        self.zcol_label = QLabel("Z column")
        self.zcol = QComboBox()
        controls.addWidget(self.zcol_label)
        controls.addWidget(self.zcol)
        self.zuncert_label = QLabel(" ↳ Z Uncertainty")
        self.zuncert = QComboBox()
        controls.addWidget(self.zuncert_label)
        controls.addWidget(self.zuncert)
        
        self.zcol_label.setVisible(False)
        self.zcol.setVisible(False)
        self._update_uncert_visibility()
        
        controls.addSpacing(15)
        controls.addWidget(QLabel("<b>Interaction Mode:</b>"))
        mode_layout = QHBoxLayout()
        
        self.btn_pan = QPushButton("✋ Pan/Zoom")
        self.btn_pan.setCheckable(True)
        self.btn_pan.setChecked(True)
        
        self.btn_box = QPushButton("⬛ Box")
        self.btn_box.setCheckable(True)
        
        self.btn_lasso = QPushButton("➰ Lasso")
        self.btn_lasso.setCheckable(True)
        
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.btn_pan)
        self.mode_group.addButton(self.btn_box)
        self.mode_group.addButton(self.btn_lasso)
        self.mode_group.buttonClicked.connect(self._set_interaction_mode)
        self._set_interaction_mode(self.btn_pan)
        
        mode_layout.addWidget(self.btn_pan)
        mode_layout.addWidget(self.btn_box)
        mode_layout.addWidget(self.btn_lasso)
        controls.addLayout(mode_layout)
        
        self.selection_curve = pg.PlotCurveItem(pen=pg.mkPen('#0055ff', width=2, style=Qt.DashLine))
        self.plot_widget.addItem(self.selection_curve, ignoreBounds=True)
        self.selection_curve.hide()
        
        self.highlight_scatter = pg.ScatterPlotItem(size=10, pen=pg.mkPen('k', width=1), brush=pg.mkBrush(255, 255, 0, 200))
        self.plot_widget.addItem(self.highlight_scatter)
        self.highlight_scatter.hide()
        
        self.selected_indices = set()
        self._is_selecting = False
        self._sel_path = []
        
        controls.addSpacing(10)
        controls.addWidget(QLabel("<b>Active Plot Series:</b>"))
        
        self.series_list = QListWidget()
        self.series_list.setMaximumHeight(100)
        self.series_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.series_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.series_list.setTextElideMode(Qt.ElideNone)
        self.series_list.itemSelectionChanged.connect(self.update_active_layer)
        
        controls.addWidget(self.series_list)
        
        btn_h = QHBoxLayout()
        self.add_series_btn = QPushButton("Add Pair")
        self.add_series_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text};")
        self.add_series_btn.clicked.connect(self.add_series_to_list)
        self.remove_series_btn = QPushButton("Remove")
        self.remove_series_btn.clicked.connect(self.remove_series_from_list)
        
        btn_h.addWidget(self.add_series_btn)
        btn_h.addWidget(self.remove_series_btn)
        controls.addLayout(btn_h)
        
        self.active_series_data = []
        self.series_list.itemSelectionChanged.connect(self.load_series_to_ui)
        self.xcol.currentIndexChanged.connect(self.update_current_series)
        self.ycol.currentIndexChanged.connect(self.update_current_series)
        self.zcol.currentIndexChanged.connect(self.update_current_series)

        self.heatmap_cmap_label = QLabel("Heatmap Colormap")
        self.heatmap_cmap_label.setVisible(False)
        controls.addWidget(self.heatmap_cmap_label)

        self.heatmap_cmap = QComboBox()
        self.heatmap_cmap.addItems(["viridis", "plasma", "inferno", "magma", "cividis", "jet", "gray"])
        self.heatmap_cmap.setVisible(False)
        self.heatmap_cmap.currentTextChanged.connect(self.plot)
        controls.addWidget(self.heatmap_cmap)
        
        # --- NEW: MAIN UI SURFACE TOGGLE ---
        self.gl_surface_main_btn = QPushButton("○ Surface View (Off)")
        self.gl_surface_main_btn.setCheckable(True)
        self.gl_surface_main_btn.setVisible(False) # Hidden by default
        self.gl_surface_main_btn.clicked.connect(lambda checked: self._toggle_surface_mode(checked))
        controls.addWidget(self.gl_surface_main_btn)
        # -----------------------------------
        
        self.snap_toggle_btn = QPushButton("✔ Snap Crosshair to Point")
        self.snap_toggle_btn.setCheckable(True)
        self.snap_toggle_btn.setChecked(True)
        self.snap_toggle_btn.setVisible(False)
        self.snap_toggle_btn.clicked.connect(self._update_snap_btn_ui)
        controls.addWidget(self.snap_toggle_btn)
        
        controls.addSpacing(10)
        controls.addWidget(button("Plot", self.plot))
        controls.addWidget(button("Save Plot", self.save_plot))
        controls.addWidget(button("Export Plotted Data", self.export_plotted_data))
        controls.addStretch()
        
        self.func_details_btn = QPushButton("Function Details")
        self.func_details_btn.setVisible(False)
        self.func_details_btn.clicked.connect(self.show_function_details)
        controls.addWidget(self.func_details_btn)

        self.edit_fit_btn = QPushButton("Edit Fit")
        self.edit_fit_btn.clicked.connect(self.edit_fit)
        self.edit_fit_btn.setVisible(False)
        controls.addWidget(self.edit_fit_btn)
    
        self.save_function_btn = QPushButton("Save Function")
        self.save_function_btn.clicked.connect(self.save_function)
        self.save_function_btn.setVisible(False)
        controls.addWidget(self.save_function_btn)
        
        # --- NEW: EXPORT FIT TO COLUMN BUTTON ---
        self.save_fit_col_btn = QPushButton("Export Fit to Column")
        self.save_fit_col_btn.clicked.connect(self.export_fit_to_column)
        self.save_fit_col_btn.setVisible(False)
        controls.addWidget(self.save_fit_col_btn)
        # ----------------------------------------
        
        self.clear_fit_btn = QPushButton("Clear Plot")
        self.clear_fit_btn.clicked.connect(self.clear_fit)
        self.clear_fit_btn.setVisible(False)
        controls.addWidget(self.clear_fit_btn)
    
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.35)
        
        self.legend = CustomLegendItem(offset=(10, 10))
        self.legend.setParentItem(self.plot_widget.getViewBox())
        self.legend.sigDoubleClicked.connect(self.open_legend_customizer)
        
        self.fit_legend = CustomLegendItem(offset=(-10, 10))
        self.fit_legend.setParentItem(self.plot_widget.getViewBox())
        self.fit_legend.sigDoubleClicked.connect(self.open_legend_customizer)
        
        for ax in ("left", "bottom", "right", "top"):
            self.plot_widget.showAxis(ax)
            a = self.plot_widget.getAxis(ax)
            a.setPen(pg.mkPen("k")) 
            
            if ax in ("top", "right"):
                a.linkToView(self.plot_widget.getViewBox())
                a.setStyle(showValues=True)
                a.setTextPen(pg.mkPen("w")) 
            else:
                a.setStyle(showValues=True)
                a.setTextPen(pg.mkPen("k"))
        
        main.addWidget(self.plot_stack, 1)

        self.heatmap_item = pg.HistogramLUTItem()
        self.plot_widget.plotItem.layout.addItem(self.heatmap_item, 2, 3)
        self.heatmap_item.setVisible(False) 
        
        self.heatmap_item.layout.removeItem(self.heatmap_item.axis)
        self.heatmap_item.layout.removeItem(self.heatmap_item.vb)
        self.heatmap_item.layout.removeItem(self.heatmap_item.gradient)
        
        new_axis = CustomAxisItem('left', linkView=self.heatmap_item.vb, maxTickLength=-5, parent=self.heatmap_item)
        self.heatmap_item.axis.deleteLater()
        self.heatmap_item.axis = new_axis   
        
        self.heatmap_item.layout.addItem(self.heatmap_item.axis, 0, 0)
        self.heatmap_item.layout.addItem(self.heatmap_item.gradient, 0, 1)
        self.heatmap_item.layout.addItem(self.heatmap_item.vb, 0, 2)
        
        self.heatmap_item.axis.setPen(pg.mkPen("k"))
        self.heatmap_item.axis.setTextPen(pg.mkPen("k"))
        self.heatmap_item.vb.setMinimumWidth(50)
                
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.vLine.setPen(pg.mkPen(color='k', style=Qt.DashLine))
        self.hLine.setPen(pg.mkPen(color='k', style=Qt.DashLine))
        
        self.plot_widget.addItem(self.vLine, ignoreBounds=True)
        self.plot_widget.addItem(self.hLine, ignoreBounds=True)
        self.vLine.hide()
        self.hLine.hide()
        
        self.crosshairs_enabled = False
        
        self.crosshair_label = QLabel(self.plot_wrapper)
        self.crosshair_label.setStyleSheet(f"""
            background-color: {theme.panel_bg}; 
            border: 1px solid {theme.border}; border-radius: 4px; 
            padding: 5px; font-weight: bold; font-family: Consolas;
            font-size: 14px; color: {theme.fg};
        """)
        self.crosshair_label.hide()

        self.stats_label = DraggableLabel(self.plot_wrapper)
        self.stats_label.setStyleSheet(f"""
            background-color: {theme.primary_bg}; 
            border: 2px solid {theme.primary_border}; 
            border-radius: 6px; padding: 8px; 
            font-family: Consolas, monospace; font-size: 13px; 
            color: {theme.primary_text};
        """)
        self.stats_label.hide()

        # --- NEW: LOOP STATS HUD ---
        self.loop_stats_label = DraggableLabel(self.plot_wrapper)
        self.loop_stats_label.setStyleSheet(f"""
            background-color: {theme.success_bg}; 
            border: 2px solid {theme.success_border}; 
            border-radius: 6px; padding: 8px; 
            font-family: Consolas, monospace; font-size: 13px; 
            color: {theme.success_text};
        """)
        self.loop_stats_label.hide()
        # ---------------------------
        # --- NEW: AREA UNDER CURVE HUD ---
        self.auc_stats_label = DraggableLabel(self.plot_wrapper)
        self.auc_stats_label.setStyleSheet(f"""
            background-color: {theme.warning_bg}; 
            border: 2px solid {theme.warning_border}; 
            border-radius: 6px; padding: 8px; 
            font-family: Consolas, monospace; font-size: 13px; 
            color: {theme.warning_text};
        """)
        self.auc_stats_label.hide()
        
        self.toggle_auc_btn = QPushButton("Toggle Peak Areas")
        self.toggle_auc_btn.setCheckable(True)
        self.toggle_auc_btn.setChecked(True)
        self.toggle_auc_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.warning_bg}; border: 2px solid {theme.warning_border}; border-radius: 4px; padding: 6px; color: {theme.warning_text};")
        self.toggle_auc_btn.setVisible(False) 
        self.toggle_auc_btn.clicked.connect(self._toggle_auc_areas)
        controls.addWidget(self.toggle_auc_btn)
        
        self.auc_data_records = []
        # ---------------------------------
        
        self.proxy = pg.SignalProxy(self.plot_widget.scene().sigMouseMoved, rateLimit=60, slot=self.mouse_moved)

    def open_legend_customizer(self, legend_item):
        if not hasattr(self, 'current_legend_entries') or not self.current_legend_entries: return
        dlg = LegendCustomizationDialog(self, self.current_legend_entries, self.legend_aliases, getattr(self, 'group_sweeps_legend', False))
        if dlg.exec() == QDialog.Accepted:
            new_aliases, group_sweeps = dlg.get_result()
            self.legend_aliases = new_aliases
            self.group_sweeps_legend = group_sweeps
            self.settings.setValue("group_sweeps_legend", group_sweeps)
            self.plot()

    def toggle_crosshairs(self):
        self.crosshairs_enabled = not getattr(self, 'crosshairs_enabled', False)
        
        if self.plot_mode == "3D":
            if not hasattr(self, 'crosshair_3d'):
                from core.analysis_3d import Crosshair3DManager
                self.crosshair_3d = Crosshair3DManager(self)
            self.crosshair_3d.toggle()
            
            # Hide 2D items
            self.vLine.hide()
            self.hLine.hide()
            self.crosshair_label.hide()
            
            # Sync the UI button using the 3D manager
            self.snap_toggle_btn.setVisible(self.crosshairs_enabled)
            if self.crosshairs_enabled:
                self.crosshair_3d.sync_button_ui()
                
        else:
            # Disable 3D if it was active
            if hasattr(self, 'crosshair_3d') and self.crosshair_3d.active:
                self.crosshair_3d.disable()
                
            # Enable 2D
            if not self.crosshairs_enabled:
                self.vLine.hide()
                self.hLine.hide()
                self.crosshair_label.hide()
                self.snap_toggle_btn.setVisible(False)
            else:
                self.snap_toggle_btn.setVisible(True)
                self._update_snap_btn_ui()
            
    def _update_snap_btn_ui(self):
        # Route 3D logic
        if getattr(self, 'plot_mode', '2D') == "3D":
            if hasattr(self, 'crosshair_3d') and self.crosshair_3d.active:
                is_locked = not self.snap_toggle_btn.isChecked()
                self.crosshair_3d.set_locked(is_locked)
            return

        # Standard 2D logic
        if self.snap_toggle_btn.isChecked():
            self.snap_toggle_btn.setText("✔ Snap Crosshair to Point")
            self.snap_toggle_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; border: 2px solid {theme.success_border}; padding: 6px; background-color: {theme.bg};")
        else:
            self.snap_toggle_btn.setText("✖ Free Crosshair")
            self.snap_toggle_btn.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; border: 2px solid {theme.danger_border}; padding: 6px; background-color: {theme.bg};")

    def mouse_moved(self, evt):
        if not getattr(self, 'crosshairs_enabled', False) or self.plot_mode != "2D":
            return
            
        pos = evt[0]
        if self.plot_widget.sceneBoundingRect().contains(pos):
            pos_left = self.plot_widget.plotItem.vb.mapSceneToView(pos)
            pos_right = self.vb_right.mapSceneToView(pos)
            
            row = self.series_list.currentRow()
            is_right_active = False
            if row >= 0 and self.series_data.get("2D"):
                if self.series_data["2D"][row].get("axis", "L") == "R":
                    is_right_active = True
            
            if not self.snap_toggle_btn.isChecked():
                if is_right_active:
                    mx, my = pos_right.x(), pos_right.y()
                    draw_x, draw_y = pos_left.x(), pos_left.y() 
                else:
                    mx, my = pos_left.x(), pos_left.y()
                    draw_x, draw_y = mx, my
                    
                self.vLine.setPos(draw_x)
                self.hLine.setPos(draw_y)
                self.crosshair_label.setText(f"X: {mx:.6g}\nY: {my:.6g}")
                
            else:
                min_dist = float('inf')
                closest_p = None
                
                xr_l = self.plot_widget.plotItem.vb.viewRange()[0]
                yr_l = self.plot_widget.plotItem.vb.viewRange()[1]
                x_span_l = max(1e-15, xr_l[1] - xr_l[0])
                y_span_l = max(1e-15, yr_l[1] - yr_l[0])
                
                xr_r = self.vb_right.viewRange()[0]
                yr_r = self.vb_right.viewRange()[1]
                x_span_r = max(1e-15, xr_r[1] - xr_r[0])
                y_span_r = max(1e-15, yr_r[1] - yr_r[0])
                
                if hasattr(self, 'last_plotted_data') and isinstance(self.last_plotted_data, dict):
                    for pkg in self.last_plotted_data.get('packages', []):
                        if pkg['type'] == 'standard': x, y = pkg['x'], pkg['y']
                        elif pkg['type'] == 'average': x, y = np.array([pkg['x_mean']]), np.array([pkg['y_mean']])
                        else: continue
                            
                        if len(x) == 0: continue
                        
                        axis_side = pkg.get("axis", "L")
                        if axis_side == "R":
                            mx, my = pos_right.x(), pos_right.y()
                            x_span, y_span = x_span_r, y_span_r
                        else:
                            mx, my = pos_left.x(), pos_left.y()
                            x_span, y_span = x_span_l, y_span_l
                        
                        dist = ((x - mx) / x_span)**2 + ((y - my) / y_span)**2
                        idx = dist.argmin()
                        if dist[idx] < min_dist:
                            min_dist = dist[idx]
                            closest_p = (x[idx], y[idx], axis_side)
            
                if hasattr(self, 'active_fits') and self.active_fits:
                    for fit in self.active_fits:
                        if "x_raw" in fit and "y_raw" in fit:
                            x, y = fit["x_raw"], fit["y_raw"]
                            if len(x) == 0: continue
                            
                            mx, my = pos_left.x(), pos_left.y()
                            dist = ((x - mx) / x_span_l)**2 + ((y - my) / y_span_l)**2
                            idx = dist.argmin()
                            if dist[idx] < min_dist:
                                min_dist = dist[idx]
                                closest_p = (x[idx], y[idx], "L")

                if closest_p:
                    cx, cy, side = closest_p
                    if side == "R":
                        import pyqtgraph as pg
                        pt_right = pg.Point(cx, cy)
                        pixel_pos = self.vb_right.mapViewToScene(pt_right)
                        pt_left = self.plot_widget.plotItem.vb.mapSceneToView(pixel_pos)
                        draw_x, draw_y = pt_left.x(), pt_left.y()
                    else:
                        draw_x, draw_y = cx, cy
                        
                    self.vLine.setPos(draw_x)
                    self.hLine.setPos(draw_y)
                    self.crosshair_label.setText(f"X: {cx:.6g}\nY: {cy:.6g}")

            self.crosshair_label.adjustSize()
            w = self.plot_wrapper.width()
            h = self.plot_wrapper.height()
            lw = self.crosshair_label.width()
            lh = self.crosshair_label.height()
            self.crosshair_label.move(w - lw - 10, h - lh - 10)
            
            if not self.crosshair_label.isVisible():
                self.vLine.show()
                self.hLine.show()
                self.crosshair_label.show()
        else:
            self.vLine.hide()
            self.hLine.hide()
            self.crosshair_label.hide()

    def show_function_details(self):
        if not getattr(self, 'active_fits', []): return
        
        if len(self.active_fits) == 1:
            fit = self.active_fits[0]
        else:
            dlg = MultiFitManagerDialog(self.active_fits, "View", self)
            if dlg.exec() == QDialog.Accepted:
                _, idx = dlg.get_selection()
                fit = self.active_fits[idx]
            else:
                return

        ftype = fit["type"].capitalize()
        eq_str = fit.get("equation", "")
        coeff_str = ""
        math_style = "font-size: 20px; font-family: Cambria, serif; font-style: italic;"

        if ftype == "Polynomial":
            coeff_str = "<br>".join([f"c<sub>{i}</sub> = {c:.6e}" for i, c in enumerate(fit["coeffs"])])
        elif ftype == "Logarithmic":
            base = fit["base"]
            eq_str = f"<span style='{math_style}'>y = a &middot; ln(x) + c</span>" if str(base).lower() == "e" else f"<span style='{math_style}'>y = a &middot; log<sub>{base}</sub>(x) + c</span>"
            coeff_str = f"a = {fit['params'][0]:.6e}<br>c = {fit['params'][1]:.6e}"
        elif ftype == "Exponential":
            eq_str = f"<span style='{math_style}'>y = a &middot; e<sup>bx</sup> + c</span>"
            coeff_str = f"a = {fit['params'][0]:.6e}<br>b = {fit['params'][1]:.6e}<br>c = {fit['params'][2]:.6e}"
        elif ftype == "Gaussian":
            eq_str = f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2'><tr><td rowspan='2' valign='middle'>y = A &middot; exp&nbsp;&nbsp;[ &minus;</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;(x &minus; &mu;)<sup>2</sup>&nbsp;</td><td rowspan='2' valign='middle'>]</td></tr><tr><td align='center'>2&sigma;<sup>2</sup></td></tr></table>"
            coeff_str = f"A = {fit['params'][0]:.6e}<br>&mu; = {fit['params'][1]:.6e}<br>&sigma; = {fit['params'][2]:.6e}"
        elif ftype == "Lorentzian":
            eq_str = f"<table style='{math_style}' border='0' cellspacing='0' cellpadding='2'><tr><td rowspan='2' valign='middle'>y = </td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;A&nbsp;</td></tr><tr><td align='center'><table style='{math_style}' border='0' cellspacing='0' cellpadding='0'><tr><td rowspan='2' valign='middle'>1 + &nbsp;[</td><td align='center' style='border-bottom: 1px solid black;'>&nbsp;x &minus; x<sub>0</sub>&nbsp;</td><td rowspan='2' valign='middle'>]<sup>2</sup></td></tr><tr><td align='center'>&gamma;</td></tr></table></td></tr></table>"
            coeff_str = f"A = {fit['params'][0]:.6e}<br>x<sub>0</sub> = {fit['params'][1]:.6e}<br>&gamma; = {fit['params'][2]:.6e}"
        elif ftype == "Custom":
            display_eq = fit.get('html_equation', fit.get('equation', ''))
            eq_str = f"<span style='{math_style}'>y = {display_eq}</span>"
            coeff_str = "<br>".join([f"{GREEK_MAP.get(p, p)} = {v:.6e}" for p, v in zip(fit['param_names'], fit['params'])])

        msg = QMessageBox(self)
        msg.setWindowTitle(f"Function Details: {fit['name']}")
        msg.setText(f"<b style='font-size: 16px;'>Fit Type:</b> <span style='font-size: 16px;'>{ftype}</span>")
        msg.setStyleSheet("QLabel { font-size: 14px; }")
        msg.setInformativeText(f"<b>Equation Form:</b><br><br>{eq_str}<br><b>Calculated Coefficients:</b><br><span style='font-family: Consolas, monospace; font-size: 15px;'>{coeff_str}</span>")
        msg.exec()

    def set_plot_mode(self, mode):
        # --- NEW: UI CLEAN SLATE ON MODE SWITCH ---
        # 1. Forcefully disable 3D Anchor if it exists
        if hasattr(self, 'crosshair_3d') and self.crosshair_3d.active:
            self.crosshair_3d.disable()
            
        # 2. Forcefully disable 2D Crosshairs
        self.crosshairs_enabled = False
        if hasattr(self, 'vLine'): self.vLine.hide()
        if hasattr(self, 'hLine'): self.hLine.hide()
        if hasattr(self, 'crosshair_label'): self.crosshair_label.hide()
        
        # 3. Reset the shared toggle button to a neutral state
        if hasattr(self, 'snap_toggle_btn'):
            self.snap_toggle_btn.blockSignals(True)
            self.snap_toggle_btn.setChecked(False)
            self.snap_toggle_btn.setVisible(False)
            self.snap_toggle_btn.setText("✔ Snap Crosshair to Point") # Reset 2D text
            self.snap_toggle_btn.setStyleSheet(f"color: {theme.fg}; padding: 6px; background-color: {theme.bg};")
            self.snap_toggle_btn.blockSignals(False)
        # ------------------------------------------
        
        # Protect the STFT flag
        if not getattr(self, '_ignore_mode_clear', False):
            self.stft_mode_active = False
        self._is_plotting = False
        if mode == "3D" and not OPENGL_AVAILABLE:
            QMessageBox.warning(self, "3D Not Available", "3D plotting requires OpenGL support.\n\nInstall pyqtgraph with OpenGL enabled.\n\nThis can be done with: pip install PyOpenGL PyOpenGL_accelerate")
            return
    
        self.plot_mode = mode
        self._update_graphtype_dropdown()
        
        is_heatmap = (mode == "Heatmap")
        self.heatmap_cmap.setVisible(is_heatmap)
        self.heatmap_cmap_label.setVisible(is_heatmap)
        self.heatmap_item.setVisible(is_heatmap)
        
        # --- NEW: SHOW SURFACE BUTTON IN 3D MODE ---
        if hasattr(self, 'gl_surface_main_btn'):
            self.gl_surface_main_btn.setVisible(mode == "3D")
            if mode == "3D":
                self._toggle_surface_mode(self.gl_surface_cb.isChecked()) # Sync styling on load
        # -------------------------------------------
        
        # --- NEW: UI TOGGLES FOR HISTOGRAM ---
        is_hist = (mode == "Histogram")
        
        # Show/Hide the Stats Button
        if hasattr(self, 'toggle_stats_btn'): 
            self.toggle_stats_btn.setVisible(is_hist)
            if not is_hist and hasattr(self, 'stats_label'):
                self.stats_label.hide() # Auto-hide the HUD when leaving Histogram mode
                
        # Hide X Column
        if hasattr(self, 'xcol_label'): self.xcol_label.setVisible(not is_hist)
        self.xcol.setVisible(not is_hist)
        
        # Rename Y Column dynamically
        if hasattr(self, 'ycol_label'):
            self.ycol_label.setText("Data column" if is_hist else "Y column")
        # --------------------------------------------
        
        # --- NEW: Hide Z-tools during STFT ---
        show_z = (mode in ["3D", "Heatmap"])
        if getattr(self, 'stft_mode_active', False): 
            show_z = False 
            
        self.zcol.setVisible(show_z)
        self.zcol_label.setVisible(show_z)
        self.zscale_label.setVisible(show_z)
        self.zscale.setVisible(show_z)
        self.zbase.setVisible(show_z and self.zscale.currentText() == "Log")
        # -------------------------------------
        
        if hasattr(self, 'series_data'):
            self._refresh_series_list_ui()
    
        if mode in ["2D", "Histogram", "Heatmap"]: 
            self.plot_layout.setCurrentWidget(self.plot_wrapper)
        elif mode == "3D" and OPENGL_AVAILABLE: 
            self.plot_layout.setCurrentWidget(self.gl_widget)
        
        if hasattr(self, '_update_uncert_visibility'):
            self._update_uncert_visibility()
    
        if self.dataset:
            self.plot()

    def _update_aspect_ui(self, text):
        is_custom = (text == "Custom")
        self.aspect_w_edit.setVisible(is_custom)
        self.aspect_h_edit.setVisible(is_custom)
        self.aspect_colon.setVisible(is_custom)
        self._resize_plot_widget()

    def get_aspect_ratio(self):
        text = self.aspect_combo.currentText()
        if text == "Free": return None
        if text == "1:1": return 1.0
        if text == "4:3": return 4.0 / 3.0
        if text == "16:9": return 16.0 / 9.0
        if text == "Custom":
            try:
                w = float(self.aspect_w_edit.text())
                h = float(self.aspect_h_edit.text())
                if h <= 0 or w <= 0: return None
                return w / h
            except ValueError:
                return None
        return None

    def _on_plot_stack_resize(self, event):
        self.original_plot_stack_resize(event)
        self._resize_plot_widget()
        
    def _resize_plot_widget(self):
        ratio = self.get_aspect_ratio()
        if ratio is None:
            self.plot_widget.setMinimumSize(0, 0)
            self.plot_widget.setMaximumSize(16777215, 16777215)
            return
            
        aw = self.plot_wrapper.width()
        ah = self.plot_wrapper.height()
        if aw <= 0 or ah <= 0: return
        
        if aw / ah > ratio:
            th, tw = ah, ah * ratio
        else:
            tw, th = aw, aw / ratio
            
        self.plot_widget.setFixedSize(int(tw), int(th))

    def _update_xscale_ui(self):
        self.xbase.setVisible(self.xscale.currentText() == "Log")

    def _update_yscale_ui(self):
        self.ybase.setVisible(self.yscale.currentText() == "Log")
        
    def _update_zscale_ui(self):
        is_log = self.zscale.currentText() == "Log"
        is_3d_or_heat = self.plot_mode != "2D"
        self.zbase.setVisible(is_log and is_3d_or_heat)
    
    def toggle_averaging(self):
        self.average_enabled = not getattr(self, 'average_enabled', False)
        self.errorbar_btn.setVisible(self.average_enabled)
        self.errorbar_sigma_edit.setVisible(self.average_enabled)
        if not self.average_enabled:
            self.errorbars_enabled = False
            
        # Update styling
        if self.average_enabled:
            self.toggle_avg_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
        else:
            self.toggle_avg_btn.setStyleSheet(f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg};")
        
        self.update_file_mode_ui()
        self.plot()
        
    def toggle_errorbars(self):
        self.errorbars_enabled = self.errorbar_btn.isChecked()
        if self.errorbars_enabled:
            self.errorbar_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
        else:
            self.errorbar_btn.setStyleSheet(f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg};")
        self.plot()

    def _fix_graphics_view(self):
        view = self.plot_widget.getViewBox().scene().views()[0]
        view.setViewportUpdateMode(view.FullViewportUpdate)
        view.setCacheMode(view.CacheNone)

    def _patch_pyqtgraph_menu(self):
        menu = self.plot_widget.getViewBox().menu
        def fix_palette():
            for w in menu.findChildren(QLineEdit):
                pal = w.palette()
                pal.setColor(QPalette.Base, QColor("white"))
                pal.setColor(QPalette.Text, QColor("black"))
                w.setPalette(pal)
        menu.aboutToShow.connect(fix_palette)

    def _apply_styles(self):
        app = QApplication.instance()
        is_dark = self.settings.value("dark_mode", False, bool)
        theme.update(is_dark)
        
        # --- NEW: WINDOWS 10/11 TITLE BAR HACK ---
        try:
            import ctypes
            # 20 is DWMWA_USE_IMMERSIVE_DARK_MODE for Windows 11 and newer 10
            # 19 is for older builds of Windows 10
            rendering_policy = ctypes.c_int(1 if is_dark else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 20, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(int(self.winId()), 19, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
        except Exception:
            pass
        # -----------------------------------------
        
        # --- DARK MODE ENGINE ---
        if is_dark:
            if app:
                app.setStyle("Fusion")
                dark_palette = QPalette()
                dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
                dark_palette.setColor(QPalette.WindowText, Qt.white)
                dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
                dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
                dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
                dark_palette.setColor(QPalette.ToolTipText, Qt.white)
                dark_palette.setColor(QPalette.Text, Qt.white)
                dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
                dark_palette.setColor(QPalette.ButtonText, Qt.white)
                dark_palette.setColor(QPalette.BrightText, Qt.red)
                dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
                dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
                dark_palette.setColor(QPalette.HighlightedText, Qt.black)
                app.setPalette(dark_palette)
                
            self.setStyleSheet("""
                QPushButton { background-color: #444; border: 1px solid #666; border-radius: 4px; padding: 6px; color: white; }
                QPushButton:hover { background-color: #555; }
                QPushButton:pressed { background-color: #333; }
                QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background-color: #222; color: white; border: 1px solid #555; padding: 4px; }
                
                /* DARK MODE TAB STYLES */
                QTabWidget::pane { border: 1px solid #555; background-color: #353535; }
                QTabBar::tab { background-color: #2a2a2a; color: #888; padding: 8px 16px; border: 1px solid #555; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
                QTabBar::tab:selected { background-color: #444; color: white; border: 1px solid #0055ff; border-bottom: none; font-weight: bold; }
                QTabBar::tab:hover:!selected { background-color: #3a3a3a; color: white; }
            """)
            return
        # -----------------------------

        # --- LIGHT MODE ENGINE ---
        if app: 
            app.setStyle("Fusion")
            app.setPalette(app.style().standardPalette()) # CRITICAL FIX: Restores default OS colors!
            
        self.setStyleSheet("""
            QPushButton { background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 6px; color: black; }
            QPushButton:hover { background-color: #e6e6e6; }
            QPushButton:pressed { background-color: #d0d0d0; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background-color: white; color: black; border: 1px solid #8a8a8a; padding: 4px; }
        """)

    def _init_3d_scene(self, data_bounds=None, scales=(1.0, 1.0, 1.0)):
        sx, sy, sz = scales
        
        gz = gl.GLGridItem()
        gz.setSize(x=10*sx, y=10*sy, z=0)
        gz.setSpacing(x=1*sx, y=1*sy, z=0)
        gz.setColor((150, 150, 150, 255)) 
        gz.translate(5*sx, 5*sy, -0.1) 
        self.gl_widget.addItem(gz)
    
        x_axis = gl.GLLinePlotItem(pos=np.array([[0, 0, -0.1], [11*sx, 0, -0.1]]), color=(1, 0.2, 0.2, 1), width=4, antialias=True)
        y_axis = gl.GLLinePlotItem(pos=np.array([[0, 0, -0.1], [0, 11*sy, -0.1]]), color=(0.2, 1, 0.2, 1), width=4, antialias=True)
        z_axis = gl.GLLinePlotItem(pos=np.array([[0, 0, -0.1], [0, 0, 11*sz]]), color=(0.2, 0.5, 1, 1), width=4, antialias=True)
    
        self.gl_widget.addItem(x_axis)
        self.gl_widget.addItem(y_axis)
        self.gl_widget.addItem(z_axis)

        if data_bounds is None: return
        try: from pyqtgraph.opengl import GLTextItem
        except ImportError: return

        mins, maxs = data_bounds
        spans = maxs - mins
        spans[spans == 0] = 1.0 

        x_name_def = self.xcol.currentText().split(": ")[-1] if ":" in self.xcol.currentText() else "X"
        y_name_def = self.ycol.currentText().split(": ")[-1] if ":" in self.ycol.currentText() else "Y"
        z_name_def = self.zcol.currentText().split(": ")[-1] if ":" in self.zcol.currentText() else "Z"

        # --- NEW: EXTRACT HTML LABELS ---
        def get_lbl(key, default):
            saved = self.custom_axis_labels.get(key)
            if isinstance(saved, dict): return saved.get("html", default)
            return saved or default

        x_name = get_lbl("x_3d", x_name_def)
        y_name = get_lbl("y_3d", y_name_def)
        z_name = get_lbl("z_3d", z_name_def)
        # --------------------------------

        xlog, ylog, zlog = self.xscale.currentText() == "Log", self.yscale.currentText() == "Log", self.zscale.currentText() == "Log"
        xbase = self._parse_log_base(self.xbase.text())
        ybase = self._parse_log_base(self.ybase.text())
        zbase = self._parse_log_base(self.zbase.text())
        
        superscripts = {'0':'⁰', '1':'¹', '2':'²', '3':'³', '4':'⁴', '5':'⁵', '6':'⁶', '7':'⁷', '8':'⁸', '9':'⁹', '-':'⁻', '.':'⋅'}
        def format_val_3d(v, is_log, base):
            if is_log:
                if abs(v - round(v)) < 1e-4:
                    exp_str = "".join(superscripts.get(c, c) for c in str(int(round(v))))
                    b_str = "e" if abs(base - np.e) < 1e-4 else f"{base:g}"
                    return f"{b_str}{exp_str}"
                else:
                    with np.errstate(over='ignore', invalid='ignore'):
                        orig = np.power(base, float(v))
                    if np.isinf(orig) or np.isnan(orig): return ""
                    if abs(orig) < 1e-3 or abs(orig) > 1e4: return f"{orig:.1e}"
                    return f"{orig:.2g}"
            else:
                if v == 0: return "0"
                if abs(v) < 1e-3 or abs(v) > 1e4: return f"{v:.2e}"
                return f"{v:.3g}"

        font_family = self.font_family_combo.currentFont().family()
        try: tick_size = int(self.tick_fontsize_edit.text())
        except ValueError: tick_size = 10
        try: label_size = int(self.label_fontsize_edit.text())
        except ValueError: label_size = 12

        font = pg.QtGui.QFont(font_family, tick_size)
        label_font = pg.QtGui.QFont(font_family, label_size, pg.QtGui.QFont.Bold)
        
        # --- NEW: DYNAMIC 3D TEXT COLOURS ---
        bg_val = self.bg_color_combo.currentText()
        is_dark_theme = self.settings.value("dark_mode", False, bool)
        
        if bg_val == "White" or (bg_val == "Transparent" and not is_dark_theme):
            text_color = (50, 50, 50, 255)
            label_color = (0, 0, 0, 255)
            gz.setColor((150, 150, 150, 100)) # Darker, more transparent grid for white background
        else:
            text_color = (200, 200, 200, 255)
            label_color = (255, 255, 255, 255)
            gz.setColor((150, 150, 150, 255))
        # ------------------------------------

        def add_tick_line(p1, p2):
            self.gl_widget.addItem(gl.GLLinePlotItem(pos=np.array([p1, p2]), color=(0.7, 0.7, 0.7, 1), width=2))

        tick_positions = np.linspace(0, 10, 5)

        for pos in tick_positions:
            val = mins[0] + (pos / 10.0) * spans[0]
            add_tick_line([pos*sx, 0, -0.1], [pos*sx, -0.3, -0.1])
            self.gl_widget.addItem(GLRichTextItem(pos=[pos*sx, -0.5, -0.1], text=format_val_3d(val, xlog, xbase), font=font, color=text_color))
        self.gl_widget.addItem(GLRichTextItem(pos=[5*sx, -1.8, -0.1], text=x_name, font=label_font, color=label_color))

        for pos in tick_positions:
            val = mins[1] + (pos / 10.0) * spans[1]
            add_tick_line([0, pos*sy, -0.1], [-0.3, pos*sy, -0.1])
            self.gl_widget.addItem(GLRichTextItem(pos=[-0.5, pos*sy, -0.1], text=format_val_3d(val, ylog, ybase), font=font, color=text_color))
        self.gl_widget.addItem(GLRichTextItem(pos=[-2.2, 5*sy, -0.1], text=y_name, font=label_font, color=label_color))

        for pos in tick_positions[1:]: 
            val = mins[2] + (pos / 10.0) * spans[2]
            add_tick_line([0, 0, pos*sz], [-0.3, 0, pos*sz])
            self.gl_widget.addItem(GLRichTextItem(pos=[-0.5, 0, pos*sz], text=format_val_3d(val, zlog, zbase), font=font, color=text_color))
        self.gl_widget.addItem(GLRichTextItem(pos=[-1.5, 0, 5*sz], text=z_name, font=label_font, color=label_color))

    def toggle_legend(self):
        self.legend_visible = not getattr(self, 'legend_visible', True)
        
        # Safely hide/show the legends if they exist
        if hasattr(self, 'legend'): self.legend.setVisible(self.legend_visible)
        if hasattr(self, 'fit_legend'): self.fit_legend.setVisible(self.legend_visible)
        
        # Update the button styling
        if hasattr(self, 'toggle_legend_btn'):
            self.toggle_legend_btn.setChecked(self.legend_visible)
            if self.legend_visible:
                self.toggle_legend_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
            else:
                self.toggle_legend_btn.setStyleSheet(f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg};")
                
    def _toggle_hist_stats(self):
        if self.toggle_stats_btn.isChecked():
            self.toggle_stats_btn.setStyleSheet("font-weight: bold; background-color: #d0e8ff; border: 2px solid #0055ff; border-radius: 4px; padding: 6px; color: #0055ff;")
            if self.plot_mode == "Histogram" and hasattr(self, '_last_hist_html'):
                self.stats_label.setText(self._last_hist_html)
                self.stats_label.adjustSize()
                self.stats_label.show()
                self.stats_label.raise_()
        else:
            self.toggle_stats_btn.setStyleSheet("background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 6px; color: black;")
            if self.plot_mode == "Histogram":
                self.stats_label.hide()

    def restore_state(self):
        if geo := self.settings.value("geometry"): self.restoreGeometry(geo)
        
        self.legend_visible = self.settings.value("legend", True, bool)
        self.fit_legend.setVisible(self.legend_visible)
        
        # --- FIX: SYNC THE LEGEND BUTTON STATE & COLOUR ON BOOT ---
        if hasattr(self, 'toggle_legend_btn'):
            self.toggle_legend_btn.setChecked(self.legend_visible)
            if self.legend_visible:
                self.toggle_legend_btn.setStyleSheet(f"font-weight: bold; background-color: {theme.primary_bg}; border: 2px solid {theme.primary_border}; border-radius: 4px; padding: 6px; color: {theme.primary_text};")
            else:
                self.toggle_legend_btn.setStyleSheet(f"background-color: {theme.bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg};")
        # ----------------------------------------------------------
        saved_aliases_str = self.settings.value("legend_aliases", "")
        if saved_aliases_str:
            try: self.legend_aliases = json.loads(saved_aliases_str)
            except Exception: self.legend_aliases = {}
        self.average_enabled = self.settings.value("average", False, bool)
        self.last_file = self.settings.value("last_file", "")
        self.file_type = self.settings.value("file_type", "BadgerLoop")
        
        if not BADGERLOOP_AVAILABLE and self.file_type == "BadgerLoop":
            self.file_type = "CSV"
            self.last_file = "" 
    
        self.xscale.setCurrentText(self.settings.value("xscale", "Linear"))
        self.yscale.setCurrentText(self.settings.value("yscale", "Linear"))
        self.zscale.setCurrentText(self.settings.value("zscale", "Linear")) 
        self.xbase.setText(self.settings.value("xbase", "10"))
        self.ybase.setText(self.settings.value("ybase", "10"))
        self.zbase.setText(self.settings.value("zbase", "10")) 
        
        self.sweeps_edit.setText(self.settings.value("sweeps", "-1"))
        self.points_edit.setText(self.settings.value("points", "-1"))
        self.label_fontsize_edit.setText(self.settings.value("label_fontsize", "12"))
        self.tick_fontsize_edit.setText(self.settings.value("tick_fontsize", "10"))
        try: saved_thick = int(self.settings.value("axis_thickness", 1))
        except: saved_thick = 1
        self.axis_thick_slider.setValue(saved_thick)
        self.axis_thick_label.setText(f"{saved_thick} px")
        self.grid_x_cb.setChecked(self.settings.value("grid_x", True, bool))
        self.grid_y_cb.setChecked(self.settings.value("grid_y", True, bool))
        self.grid_alpha_edit.setText(self.settings.value("grid_alpha", "0.35"))
        self.bg_color_combo.setCurrentText(self.settings.value("bg_color", "White"))
        if font_str := self.settings.value("font_family", ""):
            self.font_family_combo.setCurrentFont(pg.QtGui.QFont(font_str))
        self.legend_fontsize_edit.setText(self.settings.value("legend_fontsize", "11"))
        self.line_thickness_edit.setText(self.settings.value("line_thickness", "2"))
        self.symbol_combo.setCurrentText(self.settings.value("symbol", "Circle (o)"))
        self.errorbar_sigma_edit.setText(self.settings.value("errorbar_sigma", "1.0"))
        
        self.errorbars_enabled = self.settings.value("errorbars", False, bool)
        # --- ADD THESE 5 LINES ---
        self.errorbar_btn.setChecked(self.errorbars_enabled)
        if self.errorbars_enabled:
            self.errorbar_btn.setStyleSheet("font-weight: bold; background-color: #d0e8ff; border: 2px solid #0055ff; border-radius: 4px; padding: 6px; color: #0055ff;")
        else:
            self.errorbar_btn.setStyleSheet("background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 6px; color: black;")
        # -------------------------
        self.errorbar_btn.setVisible(self.average_enabled)
        self.errorbar_sigma_edit.setVisible(self.average_enabled)
        self.graphtype.setCurrentText(self.settings.value("graphtype", "Line"))
        self.heatmap_cmap.setCurrentText(self.settings.value("heatmap_cmap", "viridis"))
        self.plot_mode = self.settings.value("plot_mode", "2D")
        self.set_plot_mode(self.plot_mode)
        self.aspect_w_edit.setText(self.settings.value("aspect_w", "16"))
        self.aspect_h_edit.setText(self.settings.value("aspect_h", "9"))
        self.aspect_combo.setCurrentText(self.settings.value("aspect_mode", "Free"))
        self._update_aspect_ui(self.aspect_combo.currentText())
        self.gl_surface_snap_cb.setChecked(self.settings.value("gl_surface_snap", False, bool))
        
        show_z = (self.plot_mode in ["3D", "Heatmap"])
        self.zcol.setVisible(show_z)
        self.zcol_label.setVisible(show_z)
        self.zscale_label.setVisible(show_z)
        self.zscale.setVisible(show_z)
        self.zbase.setVisible(show_z and self.zscale.currentText() == "Log")
        
        snap_on = self.settings.value("crosshair_snap", True, bool)
        if hasattr(self, 'snap_toggle_btn'):
            self.snap_toggle_btn.setChecked(snap_on)
            self._update_snap_btn_ui()
        
        is_heatmap = (self.plot_mode == "Heatmap")
        self.heatmap_cmap.setVisible(is_heatmap)
        self.heatmap_cmap_label.setVisible(is_heatmap)
        
        if self.plot_mode == "2D": self.plot_layout.setCurrentWidget(self.plot_wrapper)
        elif self.plot_mode == "3D" and OPENGL_AVAILABLE: self.plot_layout.setCurrentWidget(self.gl_widget)
        elif self.plot_mode == "Heatmap": self.plot_layout.setCurrentWidget(self.plot_wrapper) # <--- FIXED
    
        if self.last_file and os.path.exists(self.last_file):
            try:
                self.leg_cols.setValue(int(self.settings.value("leg_cols", 1)))
                self.leg_opacity.setValue(int(self.settings.value("leg_opacity", 230)))
                self.leg_border.setValue(float(self.settings.value("leg_border", 1.5)))
                self.leg_spacing.setValue(int(self.settings.value("leg_spacing", 0)))
                # Retrieve saved load options
                opts_str = self.settings.value("last_load_opts", "")
                try: self.last_load_opts = json.loads(opts_str) if opts_str else {}
                except Exception: self.last_load_opts = {}

                if self.file_type == "MultiCSV":
                    if "file_list" not in self.last_load_opts:
                        raise ValueError("Missing file list for MultiCSV")
                    from core.data_loader import MultiCSVDataset
                    self.dataset = MultiCSVDataset(
                        self.last_file, 
                        self.last_load_opts["file_list"], 
                        self.last_load_opts.get("delimiter", ","), 
                        self.last_load_opts.get("has_header", True)
                    )
                elif self.file_type in ["CSV", "ConcatenatedCSV"]:
                    from core.data_loader import CSVDataset
                    self.dataset = CSVDataset(
                        self.last_file,
                        self.last_load_opts.get("delimiter", ","),
                        self.last_load_opts.get("has_header", True)
                    )
                # --- NEW: ROUTE HDF5 FILES PROPERLY ON STARTUP ---
                elif self.file_type == "HDF5":
                    from core.data_loader import HDF5Dataset
                    self.dataset = HDF5Dataset(self.last_file)
                # -------------------------------------------------
                else: 
                    if os.path.isdir(self.last_file):
                        raise IsADirectoryError("Expected a BadgerLoop file but got a directory.")
                    self.dataset = Dataset(self.last_file)
                    
                self.populate_columns()
                
                saved_series_str = self.settings.value("series_data", "")
                max_idx = len(self.dataset.column_names) - 1
                
                default_pair = {
                    "x": 0, "y": min(1, max_idx), "z": min(2, max_idx),
                    "x_name": self.dataset.column_names.get(0, "X"),
                    "y_name": self.dataset.column_names.get(min(1, max_idx), "Y"),
                    "z_name": self.dataset.column_names.get(min(2, max_idx), "Z")
                }
                
                if saved_series_str:
                    try:
                        restored_data = json.loads(saved_series_str)
                        for mode in ["2D", "3D", "Heatmap", "Histogram"]:  # <-- Added Histogram
                            if mode in restored_data and restored_data[mode]:
                                for pair in restored_data[mode]:
                                    pair['x'] = min(pair.get('x', 0), max_idx)
                                    pair['y'] = min(pair.get('y', 0), max_idx)
                                    pair['z'] = min(pair.get('z', 0), max_idx)
                                    pair['x_name'] = self.dataset.column_names.get(pair['x'], "X")
                                    pair['y_name'] = self.dataset.column_names.get(pair['y'], "Y")
                                    pair['z_name'] = self.dataset.column_names.get(pair['z'], "Z")
                            else:
                                restored_data[mode] = [dict(default_pair)]
                        self.series_data = restored_data
                    except Exception:
                        self.series_data = {"2D": [dict(default_pair)], "3D": [dict(default_pair)], "Heatmap": [dict(default_pair)], "Histogram": [dict(default_pair)]}
                else:
                    self.series_data = {"2D": [dict(default_pair)], "3D": [dict(default_pair)], "Heatmap": [dict(default_pair)], "Histogram": [dict(default_pair)]}
                
                self.update_file_mode_ui()
                self.point_size_edit.setText(self.settings.value("point_size", "5"))
                try:
                    self.gl_scale_x.setValue(float(self.settings.value("gl_scale_x", 1.0)))
                    self.gl_scale_y.setValue(float(self.settings.value("gl_scale_y", 1.0)))
                    self.gl_scale_z.setValue(float(self.settings.value("gl_scale_z", 1.0)))
                    self.gl_lighting_cb.setChecked(self.settings.value("gl_lighting", True, bool))
                    self.gl_stem_cb.setChecked(self.settings.value("gl_stem", False, bool))
                except Exception: pass
        
                saved_labels_str = self.settings.value("custom_axis_labels", "")
                if saved_labels_str:
                    try: self.custom_axis_labels = json.loads(saved_labels_str)
                    except Exception: self.custom_axis_labels = {"bottom": None, "left": None, "top": None, "right": None}
                
                if self.plot_mode == "2D": self.plot_layout.setCurrentWidget(self.plot_wrapper)
                elif self.plot_mode == "3D" and OPENGL_AVAILABLE: self.plot_layout.setCurrentWidget(self.gl_widget)
                elif self.plot_mode == "Heatmap": self.plot_layout.setCurrentWidget(self.plot_wrapper)
                
                current_pair = self.series_data[self.plot_mode][0]
                self.xcol.blockSignals(True); self.ycol.blockSignals(True); self.zcol.blockSignals(True)
                self.xcol.setCurrentIndex(current_pair['x'])
                self.ycol.setCurrentIndex(current_pair['y'])
                if self.zcol.count() > current_pair.get('z', 0):
                    self.zcol.setCurrentIndex(current_pair.get('z', 0))
                self.xcol.blockSignals(False); self.ycol.blockSignals(False); self.zcol.blockSignals(False)
                
                self._refresh_series_list_ui()
                self.plot()
            except Exception as e:
                import traceback
                print(f"Startup safety triggered. Abandoned last file due to: {e}\n{traceback.format_exc()}")
                self.dataset = None
                self.last_file = ""
                self.file_type = "BadgerLoop"

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("legend", self.legend_visible)
        self.settings.setValue("legend_aliases", json.dumps(self.legend_aliases))
        self.settings.setValue("last_file", self.last_file)
        self.settings.setValue("file_type", self.file_type)
        # --- NEW: Save the load options (delimiter, file list, etc) ---
        if hasattr(self, 'last_load_opts'):
            try: self.settings.setValue("last_load_opts", json.dumps(self.last_load_opts))
            except Exception: pass
        # -------------------------------------------------------------
        self.settings.setValue("xscale", self.xscale.currentText())
        self.settings.setValue("yscale", self.yscale.currentText())
        self.settings.setValue("zscale", self.zscale.currentText()) 
        self.settings.setValue("xbase", self.xbase.text())
        self.settings.setValue("ybase", self.ybase.text())
        self.settings.setValue("zbase", self.zbase.text()) 
        self.settings.setValue("sweeps", self.sweeps_edit.text())
        self.settings.setValue("points", self.points_edit.text())
        self.settings.setValue("label_fontsize", self.label_fontsize_edit.text())
        self.settings.setValue("tick_fontsize", self.tick_fontsize_edit.text())
        self.settings.setValue("xcol", self.xcol.currentIndex())
        self.settings.setValue("ycol", self.ycol.currentIndex())
        self.settings.setValue("average", self.average_enabled)
        self.settings.setValue("errorbars", self.errorbars_enabled)
        self.settings.setValue("errorbar_sigma", self.errorbar_sigma_edit.text())
        self.settings.setValue("aspect_mode", self.aspect_combo.currentText())
        self.settings.setValue("aspect_w", self.aspect_w_edit.text())
        self.settings.setValue("aspect_h", self.aspect_h_edit.text())
        self.settings.setValue("gl_surface_snap", self.gl_surface_snap_cb.isChecked())
        
        if hasattr(self, 'snap_toggle_btn'):
            self.settings.setValue("crosshair_snap", self.snap_toggle_btn.isChecked())
        
        self.settings.setValue("series_data", json.dumps(self.series_data))
        self.settings.setValue("point_size", self.point_size_edit.text())
        self.settings.setValue("custom_axis_labels", json.dumps(self.custom_axis_labels))
        
        if self.gl_widget is not None:
            try:
                self.gl_widget.makeCurrent()
                import OpenGL.contextdata
                OpenGL.contextdata.cleanupContext()
                self.gl_widget.doneCurrent()
            except Exception: pass
            self.gl_widget.setParent(None)
            self.gl_widget.deleteLater()
            self.gl_widget = None
                
        self.settings.setValue("graphtype", self.graphtype.currentText())
        self.settings.setValue("plot_mode", self.plot_mode)
        self.settings.setValue("heatmap_cmap", self.heatmap_cmap.currentText())
        self.settings.setValue("bg_color", self.bg_color_combo.currentText())
        self.settings.setValue("grid_alpha", self.grid_alpha_edit.text())
    
        super().closeEvent(e)

    def open_file(self):
        self._is_plotting = False # --- EMERGENCY UNLOCK ---
        if hasattr(self, 'plot_thread') and self.plot_thread.isRunning():
            try: self.plot_thread.terminate()
            except: pass
        if hasattr(self, 'loader_thread') and self.loader_thread.isRunning():
            try: self.loader_thread.terminate()
            except: pass
            
        fname, _ = QFileDialog.getOpenFileName(self, "Open Data File", "", "All supported files (*.txt *.csv *.h5 *.hdf5);;Text files (*.txt);;CSV files (*.csv);;HDF5 files (*.h5 *.hdf5);;All files (*)")
        if not fname: return

        # ==========================================
        # PRE-SCAN THE FILE TO AUTO-DETECT TYPE
        # ==========================================
        is_badgerloop_actual = False
        is_hdf5_actual = False
        detected_type = "CSV" # Default fallback
        
        try:
            with open(fname, 'rb') as f:
                header_bytes = f.read(2000)
                
                if header_bytes.startswith(b'\x89HDF\r\n\x1a\n'):
                    is_hdf5_actual = True
                    detected_type = "HDF5"
                else:
                    text_chunk = header_bytes.decode('utf-8', errors='ignore')
                    if "###OUTPUTS" in text_chunk or "###INPUTS" in text_chunk or "###DATA" in text_chunk:
                        is_badgerloop_actual = True
                        detected_type = "BadgerLoop"
        except Exception: pass
        # ==========================================

        # Pass the auto-detected type into the dialog!
        dlg = FileImportDialog(self, detected_type=detected_type)
        
        if dlg.exec() == QDialog.Accepted:
            opts = dlg.get_options()
            
            # --- The Mismatch Shields remain exactly the same! ---
            if opts["type"] == "HDF5" and not is_hdf5_actual:
                QMessageBox.critical(self, "Format Mismatch", "You selected 'HDF5', but this file does not appear to be a valid HDF5 binary.\n\nPlease select the correct File Type.")
                return
                
            if opts["type"] != "HDF5" and is_hdf5_actual:
                QMessageBox.critical(self, "Format Mismatch", "This appears to be an HDF5 binary file, but you selected another format.\n\nPlease open the file again and select 'HDF5' as the File Type.")
                return

            if opts["type"] == "CSV" and is_badgerloop_actual:
                QMessageBox.critical(self, "Format Mismatch", "You selected 'CSV', but this appears to be a native BadgerLoop file.\n\nPlease open the file again and select 'BadgerLoop' as the File Type.")
                return
                
            if opts["type"] == "BadgerLoop" and not is_badgerloop_actual:
                QMessageBox.critical(self, "Format Mismatch", "You selected 'BadgerLoop', but this file is missing standard BadgerLoop headers (e.g., ###INPUTS, ###DATA). It is likely a standard CSV or text file.\n\nPlease open the file again and select 'CSV' as the File Type.")
                return
                
            if opts["type"] == "CSV":
                import csv
                detected_delim = "," 
                sniff_success = False
                try:
                    with open(fname, 'r', encoding='utf-8', errors='ignore') as f:
                        sample_lines = []
                        chars_read = 0
                        for line in f:
                            if not line.lstrip().startswith('#') and line.strip():
                                sample_lines.append(line)
                                chars_read += len(line)
                            if chars_read > 4096: break
                        sample = "".join(sample_lines)
                        
                        if sample.strip():
                            sniffer = csv.Sniffer()
                            possible_delims = ',\t; |'
                            if opts["delimiter"] not in ["auto", ""] and len(opts["delimiter"]) == 1:
                                possible_delims += opts["delimiter"]
                            detected_delim = sniffer.sniff(sample, delimiters=possible_delims).delimiter
                            sniff_success = True
                except Exception: pass
                    
                if opts["delimiter"] == "auto":
                    opts["delimiter"] = detected_delim
                elif sniff_success and detected_delim != opts["delimiter"]:
                    delim_names = {',': 'Comma', '\t': 'Tab', ';': 'Semicolon', ' ': 'Space', '|': 'Pipe'}
                    det_name = delim_names.get(detected_delim, f"'{detected_delim}'")
                    sel_name = delim_names.get(opts["delimiter"], f"'{opts['delimiter']}'")
                    
                    msg = QMessageBox(self)
                    msg.setWindowTitle("Delimiter Mismatch")
                    msg.setText(f"{sel_name} delimiter selected, but {det_name} delimiter detected.")
                    msg.setInformativeText("How would you like to proceed?")
                    
                    btn_detected = msg.addButton(f"Use {det_name}", QMessageBox.AcceptRole)
                    btn_anyway = msg.addButton("Try Anyway", QMessageBox.DestructiveRole)
                    btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
                    msg.exec()
                    
                    if msg.clickedButton() == btn_cancel: return 
                    elif msg.clickedButton() == btn_detected: opts["delimiter"] = detected_delim 

            if hasattr(self, 'progress_dialog'): self.progress_dialog.deleteLater()
            self.progress_dialog = QProgressDialog("Initializing...", "Cancel", 0, 100, self)
            self.progress_dialog.setWindowTitle("Loading Data")
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.setCancelButton(None) 
            self.progress_dialog.setAutoClose(False)
            self.progress_dialog.setMinimumDuration(0) 
            self.progress_dialog.show()
            QApplication.processEvents() 

            self.loader_thread = DataLoaderThread(fname, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, fname, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
    def open_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder with CSVs")
        if not folder_path: return

        all_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.csv')]
        if not all_files:
            QMessageBox.warning(self, "No CSVs Found", "No CSV files were found in the selected folder.")
            return
        all_files.sort()

        dlg = FileImportDialog(self)
        dlg.file_type.setCurrentText("CSV")
        dlg.file_type.setEnabled(False) 
        
        if dlg.exec() != QDialog.Accepted: return
        opts = dlg.get_options()
        
        import csv
        delim = opts["delimiter"]
        if delim == "auto": delim = "," 
        
        signatures = {}
        errors = []
        
        self.progress_dialog = QProgressDialog("Scanning folder signatures...", "Cancel", 0, len(all_files), self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.show()
        
        # --- PHASE 1: SCAN ALL FILES ---
        for i, fname in enumerate(all_files):
            if self.progress_dialog.wasCanceled(): return
            self.progress_dialog.setValue(i)
            
            full_path = os.path.join(folder_path, fname)
            try:
                with open(full_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
                    first_line = ""
                    for line in f:
                        if line.strip() and not line.strip().startswith('#'):
                            first_line = line.strip()
                            break
                    
                    if not first_line:
                        errors.append((fname, "Empty or comments only"))
                        continue
                        
                    row = next(csv.reader([first_line], delimiter=delim))
                    sig = tuple(row) if opts["has_header"] else len(row)
                    
                    if sig not in signatures:
                        signatures[sig] = []
                    signatures[sig].append(full_path)
            except Exception as e:
                errors.append((fname, str(e)))

        self.progress_dialog.setValue(len(all_files))
        
        if not signatures:
            QMessageBox.critical(self, "Validation Failed", "No valid data found in the CSV files.")
            return

        # --- PHASE 2: TEMPLATE SELECTION ---
        target_sig = None
        if len(signatures) == 1:
            target_sig = list(signatures.keys())[0] 
        else:
            sel_dlg = TemplateSelectionDialog(signatures, self)
            if sel_dlg.exec() != QDialog.Accepted: return
            target_sig = sel_dlg.get_selected_signature()
            
        valid_files = signatures[target_sig]
        rejected_count = len(all_files) - len(valid_files)
        
        if rejected_count > 0:
            msg = f"Loaded {len(valid_files)} files matching the selected template.\nIgnored {rejected_count} mismatched files.\n\n"
            if errors:
                msg += "Some files had read errors:\n"
                for r in errors[:5]: msg += f"- {r[0]}: {r[1]}\n"
                if len(errors) > 5: msg += "..."
            QMessageBox.information(self, "Validation Summary", msg)

        # --- PHASE 3: FIRE UP MULTI-LOADER ---
        opts["type"] = "MultiCSV"
        opts["file_list"] = valid_files
        
        self.progress_dialog.setLabelText("Stitching files in memory...")
        self.progress_dialog.setValue(0)
        
        self.loader_thread = DataLoaderThread(folder_path, opts)
        self.loader_thread.progress.connect(self._update_progress_ui)
        self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, folder_path, opts))
        self.loader_thread.error.connect(self._on_load_error)
        self.loader_thread.start()

    def concatenate_folder(self):
        if self.file_type != "MultiCSV" or not self.dataset: return
        
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Concatenated CSV", os.path.dirname(self.dataset.filename), "CSV files (*.csv)")
        if not save_path: return
        if not save_path.lower().endswith('.csv'): save_path += '.csv'
        
        delim = getattr(self, 'last_load_opts', {}).get("delimiter", ",")
        if delim == "auto": delim = ","
        
        try:
            self.progress_dialog = QProgressDialog("Concatenating files...", "Cancel", 0, len(self.dataset.file_list), self)
            self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.progress_dialog.show()
            
            with open(save_path, 'w', encoding='utf-8-sig', newline='') as out_f:
                # Write Master Metadata
                out_f.write("# Format: ConcatenatedCSV\n")
                out_f.write("# Is Mirror File: Yes\n")
                out_f.write(f"# Concatenated from folder: {os.path.basename(self.dataset.filename)}\n")
                
                header_line = delim.join([self.dataset.column_names[i] for i in range(self.dataset.num_inputs)])
                out_f.write(header_line + "\n")
                
                for i, filepath in enumerate(self.dataset.file_list):
                    if self.progress_dialog.wasCanceled():
                        out_f.close()
                        os.remove(save_path)
                        return
                    self.progress_dialog.setValue(i)
                    
                    # INJECT THE SWEEP MARKER
                    out_f.write(f"# --- Sweep {i} (File: {os.path.basename(filepath)}) ---\n")
                    
                    with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as in_f:
                        lines = in_f.readlines()
                        
                    header_skipped = not getattr(self, 'last_load_opts', {}).get("has_header", True) 
                    
                    for line in lines:
                        clean_line = line.strip()
                        if not clean_line or clean_line.startswith("#"): continue
                        if not header_skipped:
                            header_skipped = True
                            continue
                        out_f.write(clean_line + "\n")
            
            self.progress_dialog.setValue(len(self.dataset.file_list))
            
            # Instantly load the brand-new concatenated file!
            opts = {"type": "CSV", "delimiter": delim, "has_header": True}
            self.loader_thread = DataLoaderThread(save_path, opts)
            self.loader_thread.progress.connect(self._update_progress_ui)
            self.loader_thread.finished.connect(lambda ds: self._on_load_finished(ds, save_path, opts))
            self.loader_thread.error.connect(self._on_load_error)
            self.loader_thread.start()
            
        except Exception as e:
            QMessageBox.critical(self, "Concatenation Error", f"Failed to concatenate files:\n{e}")

    def _update_progress_ui(self, percent, text):
        if hasattr(self, 'progress_dialog') and self.progress_dialog is not None:
            self.progress_dialog.setLabelText(text)
            self.progress_dialog.setValue(percent)

    def _on_load_finished(self, dataset, fname, opts):
        try:
            self.progress_dialog.setLabelText("File loaded. Preparing plot...")
            self.file_type = opts["type"]
            if getattr(dataset, 'is_concatenated', False):
                self.file_type = "ConcatenatedCSV"
                opts["type"] = "ConcatenatedCSV"
                
            self.last_file = fname
            self.dataset = dataset
            self.last_load_opts = opts 
            
            if hasattr(self, 'active_fits') and self.active_fits:
                for fit in self.active_fits:
                    self.plot_widget.removeItem(fit["plot_item"])
                self.active_fits.clear()
                self.fit_legend.clear()
                self.save_function_btn.setVisible(False)
                if hasattr(self, 'save_fit_col_btn'): self.save_fit_col_btn.setVisible(False)
                self.clear_fit_btn.setVisible(False)
                if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(False)
                if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(False)
            
            self.legend_aliases.clear()
            self.populate_columns()
            max_idx = len(dataset.column_names) - 1
            default_pair = {
                "x": 0, "y": min(1, max_idx), "z": min(2, max_idx),
                "x_name": dataset.column_names.get(0, "X"),
                "y_name": dataset.column_names.get(min(1, max_idx), "Y"),
                "z_name": dataset.column_names.get(min(2, max_idx), "Z")
            }
            
            for mode in ["2D", "3D", "Heatmap", "Histogram"]:  
                if getattr(self, 'series_data', None) and self.series_data.get(mode):
                    for pair in self.series_data[mode]:
                        pair['x'] = min(pair.get('x', 0), max_idx)
                        pair['y'] = min(pair.get('y', 0), max_idx)
                        pair['z'] = min(pair.get('z', 0), max_idx)
                        pair['x_name'] = dataset.column_names.get(pair['x'], "X")
                        pair['y_name'] = dataset.column_names.get(pair['y'], "Y")
                        pair['z_name'] = dataset.column_names.get(pair['z'], "Z")
                else:
                    if not hasattr(self, 'series_data'): self.series_data = {}
                    self.series_data[mode] = [dict(default_pair)]

            self.update_file_mode_ui()
            current_pair = self.series_data[self.plot_mode][0]
            self.xcol.blockSignals(True); self.ycol.blockSignals(True); self.zcol.blockSignals(True)
            self.xcol.setCurrentIndex(current_pair['x'])
            self.ycol.setCurrentIndex(current_pair['y'])
            if self.zcol.count() > current_pair.get('z', 0):
                self.zcol.setCurrentIndex(current_pair.get('z', 0))
            self.xcol.blockSignals(False); self.ycol.blockSignals(False); self.zcol.blockSignals(False)
            
            self._refresh_series_list_ui()
            self.custom_axis_labels = {"bottom": None, "left": None, "top": None, "right": None}
            self.plot()
            
        except Exception as e:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Load Error", f"Failed to process loaded file:\n\n{e}\n\n{traceback.format_exc()}")

    def _on_load_error(self, err_msg):
        if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
        CopyableErrorDialog("Loading Error", "An error occurred while loading the data.", err_msg, self).exec()

    def populate_columns(self):
        # --- BLOCK SIGNALS SO CLEARING DOES NOT WIPE MEMORY ---
        self.xcol.blockSignals(True)
        self.ycol.blockSignals(True)
        self.zcol.blockSignals(True)
        
        self.xcol.clear()
        self.ycol.clear()
        self.zcol.clear()
        self.xuncert.clear()
        self.yuncert.clear()
        self.zuncert.clear()

        self.xuncert.addItem("None")
        self.yuncert.addItem("None")
        self.zuncert.addItem("None")
    
        for i, name in self.dataset.column_names.items():
            label = f"{i}: {name}"
            self.xcol.addItem(label)
            self.ycol.addItem(label)
            self.zcol.addItem(label)
            self.xuncert.addItem(label)
            self.yuncert.addItem(label)
            self.zuncert.addItem(label)
            
        # --- UNBLOCK SIGNALS ---
        self.xcol.blockSignals(False)
        self.ycol.blockSignals(False)
        self.zcol.blockSignals(False)

    def _prompt_custom_axis_label(self, orientation):
        current_data = self.custom_axis_labels.get(orientation)
        if isinstance(current_data, dict):
            current_raw = current_data.get("raw", "")
        else:
            current_raw = current_data or "" # Backwards compatibility for old saved strings
            
        dlg = RichTextAxisLabelDialog(orientation, current_raw, self)
        if dlg.exec() == QDialog.Accepted:
            raw_text, html_text = dlg.get_result()
            if raw_text:
                self.custom_axis_labels[orientation] = {"raw": raw_text, "html": html_text}
            else:
                self.custom_axis_labels[orientation] = None
            self.plot()
            
    def _prompt_legend_rename(self, sig_key, current_name):
        from PyQt5.QtWidgets import QInputDialog, QLineEdit
        new_name, ok = QInputDialog.getText(
            self, 
            "Rename Legend Entry", 
            "Enter custom name for this trace:\n(Leave blank to revert to auto-generated name)", 
            QLineEdit.Normal, 
            current_name
        )
        if ok:
            if new_name.strip():
                self.legend_aliases[sig_key] = new_name.strip()
            else:
                self.legend_aliases.pop(sig_key, None)
            self.plot() # Instantly redraw to apply the new name

    def _apply_axis_fonts(self):
        try: label_size = int(self.label_fontsize_edit.text())
        except ValueError: label_size = 14
        try: tick_size = int(self.tick_fontsize_edit.text())
        except ValueError: tick_size = 11

        # Pull thickness directly from the new slider
        axis_thick = self.axis_thick_slider.value()

        font_family = self.font_family_combo.currentFont().family()
        label_font = pg.QtGui.QFont(font_family, label_size)
        tick_font = pg.QtGui.QFont(font_family, tick_size)
        
        try: leg_size = int(self.legend_fontsize_edit.text())
        except: leg_size = 11
        leg_font = pg.QtGui.QFont(font_family, leg_size)

        axes_to_update = [self.plot_widget.getAxis(ax) for ax in ("bottom", "left", "top", "right")]
        if hasattr(self, 'heatmap_item') and self.heatmap_item.isVisible():
            axes_to_update.append(self.heatmap_item.axis)

        # Dynamic color inversion for dark mode
        axis_color = 'w' if self.bg_color_combo.currentText() == "Black" else 'k'

        for axis in axes_to_update:
            axis.label.setFont(label_font)
            axis.setStyle(tickFont=tick_font)
            axis.setPen(pg.mkPen(axis_color, width=axis_thick))
            
            # CRITICAL FIX: Force PyQtGraph to delete its old pixel cache so the line can shrink!
            axis.picture = None 
            axis.update()

        # Apply Legend Typography
        if hasattr(self, 'legend') and self.legend is not None:
            for sample, label in self.legend.items:
                label.setFont(leg_font)
                label.setText(label.text, color=axis_color) 
                
        if hasattr(self, 'fit_legend') and self.fit_legend is not None:
            for sample, label in self.fit_legend.items:
                label.setFont(leg_font)
                label.setText(label.text, color=axis_color)
                
    def _apply_legend_live(self, *args):
        bg = self.bg_color_combo.currentText()
        fg = 'w' if bg == "Black" else 'k'  # Dynamically set border/text color
        op = self.leg_opacity.value()
        bw = self.leg_border.value()
        cols = self.leg_cols.value()
        sp = self.leg_spacing.value()
        
        if hasattr(self, 'legend') and self.legend:
            self.legend.update_style(bg, fg, op, bw, cols, sp)
        if hasattr(self, 'fit_legend') and self.fit_legend:
            self.fit_legend.update_style(bg, fg, op, bw, cols, sp)

    def parse_list(self, text):
        try:
            if not text or text.strip() in ["", "-1"]: return -1
            if ":" in text: return list(range(*map(int, text.split(":"))))
            return [int(x) for x in text.split(",") if x.strip()]
        except Exception:
            return -1
        
    def _parse_log_base(self, text):
        t = text.strip().lower()
        if t == 'e': return np.e
        try: 
            v = float(t)
            return v if v > 0 else 10.0
        except ValueError: return 10.0

    def _refresh_series_list_ui(self):
        self.series_list.blockSignals(True)
        self.series_list.clear()
        for i in range(len(self.series_data[self.plot_mode])):
            self._create_series_list_item(i)
        if self.series_list.count() > 0:
            self.series_list.setCurrentRow(0)
            self._load_series_to_ui_internal(0)
        self.series_list.blockSignals(False)

    def _load_series_to_ui_internal(self, row):
        if row >= len(self.series_data[self.plot_mode]): return
        pair = self.series_data[self.plot_mode][row]
        self._is_updating_ui = True
        self.xcol.blockSignals(True); self.ycol.blockSignals(True); self.zcol.blockSignals(True)
        self.xcol.setCurrentIndex(pair['x'])
        self.ycol.setCurrentIndex(pair['y'])
        if 'z' in pair and self.zcol.count() > pair['z']: self.zcol.setCurrentIndex(pair['z'])
        self.xcol.blockSignals(False); self.ycol.blockSignals(False); self.zcol.blockSignals(False)
        self._is_updating_ui = False

    def load_series_to_ui(self):
        if getattr(self, '_is_updating_ui', False): return
        if hasattr(self, 'clear_selection'): self.clear_selection()
        row = self.series_list.currentRow()
        if row < 0: return
        self._load_series_to_ui_internal(row)
        if self.plot_mode in ["3D", "Heatmap"]: self.plot()

    def update_current_series(self):
        self.stft_mode_active = False
        if getattr(self, '_is_updating_ui', False) or not self.dataset: return
        if hasattr(self, 'clear_selection'): self.clear_selection()
        row = self.series_list.currentRow()
        if row < 0: return

        try:
            xidx = max(0, self.xcol.currentIndex())
            yidx = max(0, self.ycol.currentIndex())
            zidx = max(0, self.zcol.currentIndex()) if self.zcol.isVisible() else 0

            x_name = self.dataset.column_names.get(xidx, "X")
            y_name = self.dataset.column_names.get(yidx, "Y")
            z_name = self.dataset.column_names.get(zidx, "Z")

            is_visible = self.series_data[self.plot_mode][row].get('visible', True)
            current_axis = self.series_data[self.plot_mode][row].get('axis', 'L')
            
            self.series_data[self.plot_mode][row] = {
                "x": xidx, "y": yidx, "z": zidx,
                "x_name": x_name, "y_name": y_name, "z_name": z_name,
                "visible": is_visible, "axis": current_axis
            }
            
            self.series_list.blockSignals(True)
            item = self.series_list.item(row)
            widget = self.series_list.itemWidget(item)
            label = widget.findChild(QLabel)
            if label: label.setText(f"{y_name} vs {x_name}")
            self.series_list.blockSignals(False)
            
            self.plot()
        except Exception: pass

    def add_series_to_list(self):
        if not self.dataset: return
        xidx = max(0, self.xcol.currentIndex())
        yidx = max(0, self.ycol.currentIndex())
        zidx = max(0, self.zcol.currentIndex()) if self.zcol.isVisible() else 0

        x_name = self.dataset.column_names.get(xidx, "X")
        y_name = self.dataset.column_names.get(yidx, "Y")
        z_name = self.dataset.column_names.get(zidx, "Z")
        
        self.series_data[self.plot_mode].append({
            "x": xidx, "y": yidx, "z": zidx,
            "x_name": x_name, "y_name": y_name, "z_name": z_name,
            "visible": True, "axis": "L"
        })
        
        self.series_list.blockSignals(True)
        self._create_series_list_item(len(self.series_data[self.plot_mode]) - 1)
        self.series_list.setCurrentRow(len(self.series_data[self.plot_mode]) - 1)
        self.series_list.blockSignals(False)
        
        if not getattr(self, '_is_updating_ui', False):
            self.plot()

    def remove_series_from_list(self):
        row = self.series_list.currentRow()
        if row >= 0:
            self.series_list.takeItem(row)
            self.series_data[self.plot_mode].pop(row)
            
            if not self.series_data[self.plot_mode]:
                self.add_series_to_list() 
            else:
                new_row = max(0, row - 1)
                self.series_list.blockSignals(True)
                self.series_list.setCurrentRow(new_row)
                self.series_list.blockSignals(False)
                self._load_series_to_ui_internal(new_row)
                self.plot()

    def plot(self):
        if not self.dataset: return
        if getattr(self, '_is_plotting', False) or (hasattr(self, 'plot_thread') and self.plot_thread.isRunning()): return 
        self._is_plotting = True
        
        # --- NEW: CONTEXT SENSITIVITY ---
        # Turn off the 3D crosshair anytime the plot is refreshed/redrawn
        if hasattr(self, 'crosshair_3d'):
            self.crosshair_3d.disable()
        # --------------------------------
        
        self._clear_final_loops()
        # --- NEW ---
        if hasattr(self, 'auc_data_records'): self.auc_data_records.clear()
        if hasattr(self, '_clear_auc_visuals'): self._clear_auc_visuals()
        if hasattr(self, 'auc_stats_label'): self.auc_stats_label.hide()
        if hasattr(self, 'toggle_auc_btn'): self.toggle_auc_btn.setVisible(False)
        # -----------
        
        if hasattr(self, 'clear_selection'): self.clear_selection()
        
        if not hasattr(self, '_pools_initialized'):
            self.curve_pool, self.scatter_pool, self.errorbar_pool, self.avg_error_pool = [], [], [], []
            self.heatmap_image_item = pg.ImageItem()
            self.plot_widget.addItem(self.heatmap_image_item)
            self.heatmap_item.setImageItem(self.heatmap_image_item)
            self._pools_initialized = True

        # --- NEW: STFT INTERCEPT ENGINE ---
        if getattr(self, 'stft_mode_active', False) and self.plot_mode == "Heatmap":
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            self._draw_heatmap(getattr(self, 'stft_res_dict', None))
            
            # Override labels explicitly to represent the STFT
            row = max(0, self.series_list.currentRow())
            if row < len(self.series_data.get("2D", [])):
                pair = self.series_data["2D"][row]
                self.plot_widget.setLabel("bottom", pair.get('x_name', 'Time'))
                self.plot_widget.setLabel("left", "Frequency (Hz)")
                
            self._is_plotting = False
            return
        # ----------------------------------

        import copy
        current_mode_series = self.series_data.get(self.plot_mode, [])
        if not current_mode_series:
            self._is_plotting = False
            return
            
        if self.plot_mode == "2D": series_to_plot = copy.deepcopy(current_mode_series)
        else:
            row = max(0, self.series_list.currentRow())
            if row < len(current_mode_series): series_to_plot = [copy.deepcopy(current_mode_series[row])]
            else: series_to_plot = [copy.deepcopy(current_mode_series[0])]

        xidx = series_to_plot[0]['x']
        yidx = series_to_plot[0]['y']
        zidx = series_to_plot[0].get('z', 0)
        
        # --- SECRET INJECTION ---
        actual_gtype = self.graphtype.currentText()
        if self.plot_mode == "3D" and getattr(self, 'gl_surface_cb', None) and self.gl_surface_cb.isChecked():
            actual_gtype = "Surface"
            
        params = {
            "plot_mode": self.plot_mode,
            "active_series": series_to_plot,
            "xidx": xidx, "yidx": yidx, "zidx": zidx,
            "sweeps": self.parse_list(self.sweeps_edit.text()),
            "points": self.parse_list(self.points_edit.text()),
            "xlog": self.xscale.currentText() == "Log", 
            "ylog": self.yscale.currentText() == "Log",
            "zlog": getattr(self, 'zscale', None) and self.zscale.currentText() == "Log",
            "xbase": self._parse_log_base(self.xbase.text()),
            "ybase": self._parse_log_base(self.ybase.text()),
            "zbase": self._parse_log_base(self.zbase.text()) if getattr(self, 'zbase', None) else 10.0,
            "average_enabled": getattr(self, 'average_enabled', False) if getattr(self.dataset, 'num_sweeps', 0) > 1 else False,
            "errorbars_enabled": getattr(self, 'errorbars_enabled', False) if getattr(self.dataset, 'num_sweeps', 0) > 1 else False,
            "nsigma": float(self.errorbar_sigma_edit.text()) if self.errorbar_sigma_edit.text().replace('.','',1).isdigit() else 1.0,
            "csv_uncerts_enabled": getattr(self, 'csv_uncerts_enabled', False),
            "file_type": self.file_type, 
            "graphtype": actual_gtype, # <--- INJECTED HERE
            "fft_mode_active": getattr(self, 'fft_mode_active', False)
        }
        
        if params["sweeps"] == -1: params["sweeps"] = list(range(self.dataset.num_sweeps))

        if hasattr(self, 'progress_dialog'): self.progress_dialog.deleteLater()
        self.progress_dialog = QProgressDialog("Processing Data...", None, 0, 100, self)
        self.progress_dialog.setWindowTitle("Plotting")
        self.progress_dialog.setWindowModality(Qt.WindowModal) 
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.show()
        QApplication.processEvents()
            
        try:
            self.plot_thread = PlotWorkerThread(self.dataset, params)
            self.plot_thread.progress.connect(self._update_progress_ui)
            self.plot_thread.finished_2d.connect(self._draw_2d)
            self.plot_thread.finished_3d.connect(self._draw_3d)
            self.plot_thread.finished_heatmap.connect(self._draw_heatmap)
            self.plot_thread.error.connect(self._on_plot_error)
            self.plot_thread.start()
        except Exception as e:
            self._is_plotting = False
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Plotting Error", f"Failed to initialize the plot engine:\n\n{e}\n\n{traceback.format_exc()}")
        
    def _on_plot_error(self, err_msg):
        self._is_plotting = False
        if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
        if "Data is 1-Dimensional" in err_msg: QMessageBox.information(self, "Heatmap Requirement", err_msg)
        else: CopyableErrorDialog("Plotting Error", "An error occurred while mathematically processing the data:", err_msg, self).exec()

    def _draw_2d(self, packages, show_legend):
        self.current_legend_entries = []
        # --- NEW: Route Histogram data to its dedicated renderer ---
        if getattr(self, 'plot_mode', '2D') == "Histogram":
            self._draw_histogram(packages, show_legend)
            return
        # -----------------------------------------------------------
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            dummy_arr = np.array([0,0], dtype=np.float64)
            
            # 1. Clean up standard curves
            for c in self.curve_pool:
                if type(c).__name__ == "PlotCurveItem":
                    c.setData(x=dummy_arr, y=dummy_arr)
                c.setVisible(False)
                try: self.plot_widget.removeItem(c)
                except: pass
                try: self.vb_right.removeItem(c)
                except: pass
                
            # 2. Clean up scatter points
            for s in self.scatter_pool: 
                s.setData(x=dummy_arr, y=dummy_arr)
                s.setVisible(False)
                try: self.plot_widget.removeItem(s)
                except: pass
                try: self.vb_right.removeItem(s)
                except: pass
                
            # 3. Clean up error bars
            for eb in self.errorbar_pool + self.avg_error_pool: 
                eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
                try: self.plot_widget.removeItem(eb)
                except: pass
                try: self.vb_right.removeItem(eb)
                except: pass
                
            # 4. NEW: Safely wipe histogram bars if switching modes
            if hasattr(self, 'bar_pool'):
                for b in self.bar_pool:
                    try: self.plot_widget.removeItem(b)
                    except: pass
                self.bar_pool.clear()
                
            self.legend.clear()
            self.fit_legend.clear()
            self.heatmap_image_item.setVisible(False)
            self.heatmap_item.setVisible(False)
            
            self.plot_widget.getViewBox().setLimits(xMin=-np.inf, xMax=np.inf, yMin=-np.inf, yMax=np.inf)
            if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(False)
    
            self.last_plotted_data = {'mode': '2D', 'packages': packages}
    
            xlog, ylog = self.xscale.currentText() == "Log", self.yscale.currentText() == "Log"
            xbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.xbase.text())
            ybase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.ybase.text())
            
            self.plot_widget.getAxis('bottom').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('top').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('left').set_custom_log(ylog, ybase)
            self.plot_widget.getAxis('right').set_custom_log(ylog, ybase)
    
            try: pt_size = int(self.point_size_edit.text())
            except ValueError: pt_size = 5

            left_pkgs = [p for p in packages if p.get("axis", "L") == "L"]
            right_pkgs = [p for p in packages if p.get("axis", "L") == "R"]
            has_right_axis = len(right_pkgs) > 0

            x_shared = False
            y_shared = False

            if has_right_axis and left_pkgs:
                if left_pkgs[0].get("x_name", "X") == right_pkgs[0].get("x_name", "X"): x_shared = True
                if left_pkgs[0].get("y_name", "Y") == right_pkgs[0].get("y_name", "Y"): y_shared = True
                    
            # --- NEW: Smart Axis & Text Coloring ---
            bg_val = self.bg_color_combo.currentText()
            if bg_val == "Black":
                vis_color = '#ffffff'
                hid_color = '#000000'
            elif bg_val == "Transparent":
                vis_color = '#000000'
                hid_color = (0, 0, 0, 0)
            else: # White
                vis_color = '#000000'
                hid_color = '#ffffff'
            # ---------------------------------------

            main_vb = self.plot_widget.getViewBox()
            self.vb_right.setXLink(main_vb if x_shared else None)
            self.vb_right.setYLink(main_vb if y_shared else None)
            
            bottom_axis = self.plot_widget.getAxis('bottom')
            left_axis = self.plot_widget.getAxis('left')
            right_axis = self.plot_widget.getAxis('right')
            top_axis = self.plot_widget.getAxis('top')
            
            self.plot_widget.showAxis('right', show=True)
            self.plot_widget.showAxis('top', show=True)
            
            # Lock the visible text colors for the primary axes
            bottom_axis.setTextPen(pg.mkPen(vis_color))
            left_axis.setTextPen(pg.mkPen(vis_color))
            
            if has_right_axis:
                if x_shared:
                    top_axis.linkToView(main_vb)
                    top_axis.setStyle(showValues=True)
                    top_axis.setTextPen(pg.mkPen(hid_color)) 
                else:
                    top_axis.linkToView(self.vb_right)
                    top_axis.setStyle(showValues=True)
                    top_axis.setTextPen(pg.mkPen('#d90000')) 
                
                if y_shared:
                    right_axis.linkToView(main_vb)
                    right_axis.setStyle(showValues=True)
                    right_axis.setTextPen(pg.mkPen(hid_color)) 
                else:
                    right_axis.linkToView(self.vb_right)
                    right_axis.setStyle(showValues=True)
                    right_axis.setTextPen(pg.mkPen('#d90000')) 
                    
                right_axis.setGrid(0)
                top_axis.setGrid(0)
            else:
                right_axis.linkToView(main_vb)
                top_axis.linkToView(main_vb)
                right_axis.setStyle(showValues=True) 
                top_axis.setStyle(showValues=True)
                # Blend the text into the background for a clean bounding box
                right_axis.setTextPen(pg.mkPen(hid_color)) 
                top_axis.setTextPen(pg.mkPen(hid_color))
                right_axis.setGrid(0)
                top_axis.setGrid(0)

            if packages:
                is_fft = getattr(self, 'fft_mode_active', False)
                
                # Helper to safely extract HTML or fallback text
                def get_lbl(orient, default):
                    if is_fft: return default
                    saved = self.custom_axis_labels.get(orient)
                    if isinstance(saved, dict): return saved.get("html", default)
                    return saved or default
                
                # Setup Bottom/Left Labels with correct main text color
                if left_pkgs:
                    default_x_l = left_pkgs[0].get("x_name", "X Axis") if len(set([p.get("x_name") for p in left_pkgs])) == 1 else "Bottom X"
                    self.plot_widget.setLabel("bottom", get_lbl("bottom", default_x_l), color=vis_color)
                    
                    default_y_l = left_pkgs[0].get("y_name", "Y Axis") if len(set([p.get("y_name") for p in left_pkgs])) == 1 else "Left Values"
                    self.plot_widget.setLabel("left", get_lbl("left", default_y_l), color=vis_color)
                else:
                    self.plot_widget.setLabel("bottom", "")
                    self.plot_widget.setLabel("left", "")
                    
                # Setup Top/Right Labels
                if right_pkgs:
                    if not x_shared:
                        default_x_r = right_pkgs[0].get("x_name", "X Axis") if len(set([p.get("x_name") for p in right_pkgs])) == 1 else "Top X"
                        self.plot_widget.setLabel("top", get_lbl("top", default_x_r), color='#d90000')
                    else:
                        self.plot_widget.setLabel("top", "") 
                        
                    if not y_shared:
                        default_y_r = right_pkgs[0].get("y_name", "Y Axis") if len(set([p.get("y_name") for p in right_pkgs])) == 1 else "Right Values"
                        self.plot_widget.setLabel("right", get_lbl("right", default_y_r), color='#d90000')
                    else:
                        self.plot_widget.setLabel("right", "") 
                else:
                    self.plot_widget.setLabel("top", "")
                    self.plot_widget.setLabel("right", "")

            import matplotlib
            total_plotted_sw = len(set(p.get("sw", 0) for p in packages))
            
            graphtype = self.graphtype.currentText()
            # --- NEW: EXTRACT TRACE SETTINGS ---
            try: line_thick = float(self.line_thickness_edit.text())
            except: line_thick = 2.0
            
            sym_map = {"Circle (o)": "o", "Square (s)": "s", "Triangle (t)": "t", "Star (star)": "star", "Cross (+)": "+", "X (x)": "x"}
            sym = sym_map.get(self.symbol_combo.currentText(), "o")
            # -----------------------------------
            curve_idx, scatter_idx, err_idx = 0, 0, 0
            
            # Context checks for smart naming
            active_pairs = [p for p in self.series_data.get("2D", []) if p.get('visible', True)]
            num_active_pairs = len(active_pairs)
            added_to_legend = set()
            
            for pkg in packages:
                i = pkg.get("i", 0)
                sw = pkg.get("sw", "All")
                pair_idx = pkg.get("pair_idx", 0)
                
                y_name = pkg.get("y_name", "Y")
                cmap_name = pkg.get("cmap_name", "Blues")
                cmap = matplotlib.colormaps.get_cmap(cmap_name)
                axis_side = pkg.get("axis", "L")
                pkg_type = pkg.get("type", "standard")
                
                intensity = 0.8 if total_plotted_sw <= 1 else 0.4 + 0.6 * (i / max(1, total_plotted_sw - 1))
                rgba = cmap(intensity)
                line_color = (int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255), 255)
                
                # --- NEW: GRAB STYLE FROM THE UI SOURCE OF TRUTH ---
                original_pair = self.series_data.get("2D", [])[pair_idx] if pair_idx < len(self.series_data.get("2D", [])) else {}
                style = original_pair.get("style", {})
                
                trace_type = style.get("type", graphtype)
                
                try: line_thick = float(style.get("line_width", self.line_thickness_edit.text() if self.line_thickness_edit.text() else 2.0))
                except: line_thick = 2.0
                
                try: pt_size = int(style.get("symbol_size", self.point_size_edit.text() if self.point_size_edit.text().isdigit() else 5))
                except: pt_size = 5
                
                sym_raw = style.get("symbol", self.symbol_combo.currentText())
                sym = sym_map.get(sym_raw, "o")
                
                pen_styles = {"Solid": Qt.SolidLine, "Dashed": Qt.DashLine, "Dotted": Qt.DotLine, "Dash-Dot": Qt.DashDotLine}
                pen_style = pen_styles.get(style.get("line_style", "Solid"), Qt.SolidLine)
                
                if style.get("color"):
                    from PyQt5.QtGui import QColor
                    c = QColor(style["color"])
                    line_color = (c.red(), c.green(), c.blue(), 255)
                    
                trace_pen = pg.mkPen(line_color, width=line_thick, style=pen_style)
                # ---------------------------------------------------
                
                # --- SMART AUTO-NAMING ENGINE ---
                base_name = y_name
                
                if num_active_pairs > 1:
                    base_name = f"[P{pair_idx+1}] {base_name}"
                    
                if pkg_type == "average":
                    base_name += " (Average)"
                elif total_plotted_sw > 1 and not getattr(self, 'group_sweeps_legend', False):
                    base_name += f" (Sweep {sw})"
                    
                if axis_side == "R":
                    base_name += " [R]"
                    
                # Generate a unique mathematical signature
                if getattr(self, 'group_sweeps_legend', False):
                    sig_key = f"{pair_idx}_GROUPED_{pkg_type}_{axis_side}"
                else:
                    sig_key = f"{pair_idx}_{sw}_{pkg_type}_{axis_side}"
                
                # Pull from the memory bank if the user overrode it
                legend_name = self.legend_aliases.get(sig_key, base_name)
                
                # Mini HTML parse for the final legend output!
                import re
                html_name = re.sub(r'\^([\w\.\-]+)', r'<sup>\1</sup>', legend_name)
                html_name = re.sub(r'_([\w\.\-]+)', r'<sub>\1</sub>', html_name)

                # Store for the customizer dialog
                if not hasattr(self, 'current_legend_entries'): self.current_legend_entries = []
                if not any(e["sig_key"] == sig_key for e in self.current_legend_entries):
                    self.current_legend_entries.append({
                        "sig_key": sig_key, "base_name": base_name, 
                        "pen": trace_pen, 
                        "brush": pg.mkBrush(line_color), "symbol": sym
                    })
                # --------------------------------
                
                target_vb = self.vb_right if axis_side == "R" else self.plot_widget
                
                # Helper to bind the double click to the specific pyqtgraph label
                def bind_double_click(label_item, key, current):
                    def on_click(ev):
                        if ev.double():
                            self._prompt_legend_rename(key, current)
                            ev.accept()
                    label_item.mouseClickEvent = on_click
                
                if pkg["type"] == "average":
                    if scatter_idx >= len(self.scatter_pool):
                        s = pg.ScatterPlotItem(pxMode=True)
                        self.scatter_pool.append(s)
                        
                    scatter = self.scatter_pool[scatter_idx]
                    target_vb.addItem(scatter)
                    
                    scatter.setData(x=np.array([pkg["x_mean"]], dtype=np.float64), 
                                    y=np.array([pkg["y_mean"]], dtype=np.float64), 
                                    size=pt_size + 3, pen=pg.mkPen(None), brush=pg.mkBrush(line_color), symbol=sym)
                    scatter.setVisible(True)
                    
                    if show_legend:
                        if sig_key not in added_to_legend:
                            self.legend.addItem(scatter, html_name)
                            added_to_legend.add(sig_key)
                            sample, label_item = self.legend.items[-1]
                            bind_double_click(label_item, sig_key, legend_name)
                        
                    scatter_idx += 1
                    
                    if "dx" in pkg and "dy" in pkg:
                        if err_idx >= len(self.avg_error_pool):
                            eb = pg.ErrorBarItem()
                            self.avg_error_pool.append(eb)
                            
                        err_item = self.avg_error_pool[err_idx]
                        target_vb.addItem(err_item)
                        err_item.setData(x=np.array([pkg["x_mean"]]), y=np.array([pkg["y_mean"]]), 
                                         width=np.array([2*pkg["dx"]]), height=np.array([2*pkg["dy"]]), 
                                         pen=pg.mkPen(line_color, width=2))
                        err_item.setVisible(True)
                        err_idx += 1
                    
                elif pkg["type"] == "standard":
                    if "Line" in trace_type or trace_type == "FFT (Spectrum)":
                        if curve_idx >= len(self.curve_pool):
                            c = pg.PlotCurveItem(connect="finite", autoDownsample=True)
                            self.curve_pool.append(c)
                            
                        curve = self.curve_pool[curve_idx]
                        target_vb.addItem(curve)
                        curve.setData(pkg["x"], pkg["y"], pen=trace_pen) 
                        curve.setVisible(True)
                        
                        if show_legend and "Scatter" not in trace_type:
                            if sig_key not in added_to_legend:
                                if getattr(self, 'group_sweeps_legend', False) or len(added_to_legend) < 50:
                                    self.legend.addItem(curve, html_name)
                                    added_to_legend.add(sig_key)
                                    sample, label_item = self.legend.items[-1]
                                    bind_double_click(label_item, sig_key, legend_name)
                                
                        curve_idx += 1
                        
                    if "Scatter" in trace_type:
                        if scatter_idx >= len(self.scatter_pool):
                            s = pg.ScatterPlotItem(pxMode=True)
                            self.scatter_pool.append(s)
                            
                        scatter = self.scatter_pool[scatter_idx]
                        target_vb.addItem(scatter)
                        
                        x_pts, y_pts = np.asarray(pkg["x"]), np.asarray(pkg["y"])
                        valid = np.isfinite(x_pts) & np.isfinite(y_pts)
                        scatter.setData(x=x_pts[valid], y=y_pts[valid], size=pt_size, pen=pg.mkPen(None), brush=pg.mkBrush(line_color), symbol=sym)
                        scatter.setVisible(True) 
                        
                        if show_legend:
                            if sig_key not in added_to_legend:
                                if getattr(self, 'group_sweeps_legend', False) or len(added_to_legend) < 50:
                                    if "Line" in trace_type:
                                        proxy = pg.PlotDataItem(pen=trace_pen, symbol=sym, symbolBrush=pg.mkBrush(line_color), symbolSize=pt_size)
                                        self.legend.addItem(proxy, html_name)
                                    else:
                                        self.legend.addItem(scatter, html_name)
                                        
                                    added_to_legend.add(sig_key)
                                    sample, label_item = self.legend.items[-1]
                                    bind_double_click(label_item, sig_key, legend_name)
                                
                        scatter_idx += 1

            if hasattr(self, 'active_fits') and self.active_fits:
                for fit in self.active_fits:
                    if "x_raw" in fit and "y_raw" in fit:
                        x_raw, y_raw = fit["x_raw"], fit["y_raw"]
                        with np.errstate(divide='ignore', invalid='ignore'):
                            x_vis_new = np.log(x_raw) / np.log(xbase) if xlog else x_raw
                            y_vis_new = np.log(y_raw) / np.log(ybase) if ylog else y_raw
                            
                        valid = np.isfinite(x_vis_new) & np.isfinite(y_vis_new)
                        if xlog: valid &= (x_raw > 0)
                        if ylog: valid &= (y_raw > 0)
                        
                        self.plot_widget.addItem(fit["plot_item"]) 
                        fit["plot_item"].setData(x_vis_new[valid], y_vis_new[valid])
                    
                    self.fit_legend.addItem(fit["plot_item"], fit["name"])
                
                if hasattr(self, 'func_details_btn'): self.func_details_btn.setVisible(True)
                if hasattr(self, 'save_function_btn'): self.save_function_btn.setVisible(True)
                if hasattr(self, 'clear_fit_btn'): self.clear_fit_btn.setVisible(True)
                if hasattr(self, 'edit_fit_btn'): self.edit_fit_btn.setVisible(True)
             
            self._apply_canvas_settings()
            self._apply_axis_fonts()
            self.plot_widget.getViewBox().autoRange()
            self.vb_right.autoRange()

            # =========================================================================
            # FIX: ALWAYS RESTORE SELECTION TOOLS TO THE TOP LAYER AFTER REDRAWING
            # =========================================================================
            try:
                self.plot_widget.removeItem(self.selection_curve)
                self.plot_widget.removeItem(self.highlight_scatter)
            except: pass
            
            self.plot_widget.addItem(self.selection_curve, ignoreBounds=True)
            self.plot_widget.addItem(self.highlight_scatter)
            self.selection_curve.setZValue(1000)
            self.highlight_scatter.setZValue(1001)
            
            # If there was a pre-existing selection, keep it highlighted!
            if getattr(self, 'selected_indices', set()):
                x_vis, y_vis, _, _ = self._get_all_plotted_xy(apply_selection=False)
                idx_array = [i for i in list(self.selected_indices) if i < len(x_vis)]
                if idx_array:
                    self.highlight_scatter.setData(x_vis[idx_array], y_vis[idx_array])
                    self.highlight_scatter.show()
                else:
                    self.clear_selection()
            # =========================================================================

            # --- APPLY LEGEND COSMETICS ---
            self._apply_legend_live()
            # ------------------------------

        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the 2D plot.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False
            
    def _draw_histogram(self, packages, show_legend=True):
        import pyqtgraph as pg
        import numpy as np
        import matplotlib
        
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            
            # 1. Safely clear old lines, scatters, error bars
            dummy_arr = np.array([], dtype=np.float64)
            for pool_name in ['curve_pool', 'scatter_pool']:
                for item in getattr(self, pool_name, []):
                    if hasattr(item, 'setData'): item.setData(x=dummy_arr, y=dummy_arr)
                    item.setVisible(False)
                    try: self.plot_widget.removeItem(item)
                    except: pass
                    
            for eb in getattr(self, 'errorbar_pool', []) + getattr(self, 'avg_error_pool', []):
                if hasattr(eb, 'setData'): eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
                try: self.plot_widget.removeItem(eb)
                except: pass
                
            # 2. Clear previous histogram bars
            if not hasattr(self, 'bar_pool'): self.bar_pool = []
            for b in self.bar_pool:
                try: self.plot_widget.removeItem(b)
                except: pass
            self.bar_pool.clear()
            # ---> NEW: UNLOCK THE VIEWBOX (Fixes cropping) <---
            self.plot_widget.getViewBox().setLimits(xMin=-np.inf, xMax=np.inf, yMin=-np.inf, yMax=np.inf)
            self.plot_widget.enableAutoRange(axis='xy', enable=True)
            # --------------------------------------------------
            
            self.legend.clear()
            self.fit_legend.clear()
            self.heatmap_image_item.setVisible(False)
            self.heatmap_item.setVisible(False)
            
            added_to_legend = set()
            
            # Configure Axes
            self.plot_widget.getAxis('bottom').setLabel("Bins")
            self.plot_widget.getAxis('left').setLabel("Counts")
            self.plot_widget.getAxis('right').hide()
            self.plot_widget.getAxis('top').hide()
            self.plot_widget.getAxis('bottom').set_custom_log(False, 10.0)
            self.plot_widget.getAxis('left').set_custom_log(False, 10.0)
            
            # ---> NEW: FORCE DISABLE LOG MODE TO PREVENT BARGRAPHITEM CRASHES <---
            self.plot_widget.setLogMode(x=False, y=False)
            # ---------------------------------------------------------------------
            
            self.last_plotted_data = {'mode': 'Histogram', 'packages': []}
    
            # 3. Draw the Distributions
            for pkg in packages:
                i = pkg.get("i", 0)
                sw = pkg.get("sw", "All")
                pair_idx = pkg.get("pair_idx", 0)
                y_name = pkg.get("y_name", "Y")
                axis_side = pkg.get("axis", "L")
                
                counts = pkg.get("counts", [])
                edges = pkg.get("bin_edges", [])
                if len(counts) == 0: continue
                
                # --- REVERT BACK TO CENTERS AND WIDTHS ---
                centers = (edges[:-1] + edges[1:]) / 2.0
                widths = edges[1:] - edges[:-1]
                # -----------------------------------------
                
                # Colors
                cmap_name = pkg.get("cmap_name", "Blues")
                cmap = matplotlib.colormaps.get_cmap(cmap_name)
                rgba = cmap(0.5) 
                border_rgba = cmap(0.9) 
                
                fill_color = (int(rgba[0]*255), int(rgba[1]*255), int(rgba[2]*255), int(rgba[3]*255))
                border_color = (int(border_rgba[0]*255), int(border_rgba[1]*255), int(border_rgba[2]*255), 255)
                
                # Draw the bars
                bg = pg.BarGraphItem(x=centers, height=counts, width=widths, brush=pg.mkBrush(fill_color), pen=pg.mkPen(border_color, width=1.5))
                self.plot_widget.addItem(bg)
                self.bar_pool.append(bg)
                
                # 4. Smart Legend Logic
                sig_key = f"{pair_idx}_{sw}_histogram_{axis_side}"
                base_name = f"{y_name} Distribution"
                if sw != "All": base_name += f" (Sw {sw})"
                
                legend_name = self.legend_aliases.get(sig_key, base_name)
                
                if show_legend and legend_name not in added_to_legend:
                    proxy_scatter = pg.ScatterPlotItem(pen=pg.mkPen(border_color, width=2), brush=pg.mkBrush(fill_color), size=12, symbol='s')
                    self.legend.addItem(proxy_scatter, legend_name)
                    added_to_legend.add(legend_name)
                    
                    sample, label_item = self.legend.items[-1]
                    def bind_double_click(label, key, current):
                        def on_click(ev):
                            if ev.double():
                                self._prompt_legend_rename(key, current)
                                ev.accept()
                        label.mouseClickEvent = on_click
                    bind_double_click(label_item, sig_key, legend_name)
                    
                # 5. Connect to Gaussian Fitter
                self.last_plotted_data['packages'].append({
                    "type": "standard", 
                    "pair_idx": pair_idx,
                    "x": centers,
                    "y": counts,
                    "x_name": f"Binned {y_name}",
                    "y_name": "Counts",
                    "axis": axis_side
                })
                
                # --- NEW: RENDER THE STATS HUD ---
                stats = pkg.get("stats", {})
                if stats and hasattr(self, 'toggle_stats_btn') and self.toggle_stats_btn.isChecked():
                    # Calculate the mode visually from the highest bin
                    mode_idx = np.argmax(counts)
                    mode_val = centers[mode_idx]
                    
                    html = f"<b style='color: #0055ff; font-size: 14px;'>{y_name} Distribution</b><br><hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
                    html += f"<b>Count (N):</b>&nbsp;&nbsp;&nbsp;&nbsp;{stats['n']}<br>"
                    html += f"<b>Mean (&mu;):</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['mean']:.5g}<br>"
                    html += f"<b>Median:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['median']:.5g}<br>"
                    html += f"<b>Mode (Bin):</b>&nbsp;&nbsp;&nbsp;{mode_val:.5g}<br>"
                    html += f"<b>Std Dev (&sigma;):</b>&nbsp;&nbsp;{stats['std']:.5g}<br>"
                    html += f"<b>Range:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['min']:.5g} to {stats['max']:.5g}<br>"
                    html += f"<b>Skewness:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['skew']:.5g}<br>"
                    html += f"<b>Kurtosis:</b>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{stats['kurt']:.5g}"
                    
                    self._last_hist_html = html
                    self.stats_label.setText(html)
                    self.stats_label.adjustSize()
                    if not self.stats_label.isVisible():
                        self.stats_label.move(15, 15)
                    self.stats_label.show()
                    self.stats_label.raise_()
                # ---------------------------------
                
            self.plot_widget.getViewBox().autoRange(padding=0.1)
            
        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the Histogram.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False

    def _draw_3d(self, all_pts_raw, bounds):
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            if not OPENGL_AVAILABLE: return
            self.gl_widget.clear() 
            self._apply_canvas_settings()
            
            if not all_pts_raw: return
            
            # --- FIX: Save the bounds into the dict so the Crosshair Manager can read them! ---
            self.last_plotted_data = {'mode': '3D', 'data': all_pts_raw, 'bounds': bounds}
            # ----------------------------------------------------------------------------------
                
            mins, maxs = bounds
            spans = maxs - mins
            spans[spans == 0] = 1.0 
            
            # --- NEW: APPLY INDEPENDENT AXIS SCALES ---
            sx = self.gl_scale_x.value()
            sy = self.gl_scale_y.value()
            sz = self.gl_scale_z.value()
            scale_factors = (10.0 / spans) * np.array([sx, sy, sz])
            # ------------------------------------------
            
            import matplotlib
            
            if all_pts_raw[0][0] == "SURFACE":
                surface_dict = all_pts_raw[0][2]
                x_1d = surface_dict["x_1d"]
                y_1d = surface_dict["y_1d"]
                z_2d = surface_dict["z_2d"]
                
                x_scaled = (x_1d - mins[0]) * scale_factors[0]
                y_scaled = (y_1d - mins[1]) * scale_factors[1]
                z_scaled = (z_2d - mins[2]) * scale_factors[2]
                
                x_scaled = np.ascontiguousarray(x_scaled, dtype=np.float32)
                y_scaled = np.ascontiguousarray(y_scaled, dtype=np.float32)
                z_scaled = np.ascontiguousarray(z_scaled, dtype=np.float32)
                
                cmap = matplotlib.colormaps.get_cmap(self.heatmap_cmap.currentText())
                z_norm = (z_2d - mins[2]) / spans[2] 
                
                colors = cmap(z_norm).astype(np.float32) 
                colors_flat = colors.reshape(-1, 4) 
                
                surface_item = gl.GLSurfacePlotItem(
                    x=x_scaled, y=y_scaled, z=z_scaled, 
                    colors=colors_flat, smooth=False, computeNormals=False
                )
                self.gl_widget.addItem(surface_item)

            else:
                cmap = matplotlib.colormaps.get_cmap('jet') 
                num_sweeps_plotted = len(all_pts_raw)
                
                for idx, (i, sw, pts) in enumerate(all_pts_raw):
                    
                    # --- CRITICAL FIX: STRIP NANS FOR OPENGL ---
                    valid = np.isfinite(pts[:, 0]) & np.isfinite(pts[:, 1]) & np.isfinite(pts[:, 2])
                    pts = pts[valid]
                    if len(pts) == 0: continue
                    # -------------------------------------------
                    
                    norm_pts = np.zeros_like(pts, dtype=np.float32)
                    norm_pts[:, 0] = (pts[:, 0] - mins[0]) * scale_factors[0]
                    norm_pts[:, 1] = (pts[:, 1] - mins[1]) * scale_factors[1]
                    norm_pts[:, 2] = (pts[:, 2] - mins[2]) * scale_factors[2]
                    norm_pts = np.ascontiguousarray(norm_pts)
                    
                    rgba = cmap(idx / max(1, num_sweeps_plotted - 1)) 
                    c_tuple = (float(rgba[0]), float(rgba[1]), float(rgba[2]), 1.0)
                    
                    if self.graphtype.currentText() == "Line":
                        item = gl.GLLinePlotItem(pos=norm_pts, color=c_tuple, width=2, antialias=True)
                    else:
                        d = 0.08
                        cross_pts = np.empty((len(norm_pts) * 6, 3), dtype=np.float32)
                        cross_pts[0::6] = norm_pts + np.array([-d, 0, 0], dtype=np.float32)
                        cross_pts[1::6] = norm_pts + np.array([ d, 0, 0], dtype=np.float32)
                        cross_pts[2::6] = norm_pts + np.array([0, -d, 0], dtype=np.float32)
                        cross_pts[3::6] = norm_pts + np.array([0,  d, 0], dtype=np.float32)
                        cross_pts[4::6] = norm_pts + np.array([0, 0, -d], dtype=np.float32)
                        cross_pts[5::6] = norm_pts + np.array([0, 0,  d], dtype=np.float32)
                        item = gl.GLLinePlotItem(pos=cross_pts, color=c_tuple, width=3, antialias=True, mode='lines')
                        
                    self.gl_widget.addItem(item)
                    
                    # --- NEW: STEM PLOTTING (DROP LINES) ---
                    if self.gl_stem_cb.isChecked():
                        stem_pts = np.empty((len(norm_pts) * 2, 3), dtype=np.float32)
                        stem_pts[0::2] = norm_pts
                        floor_pts = norm_pts.copy()
                        floor_pts[:, 2] = 0.0 # Drop straight down to the physical floor
                        stem_pts[1::2] = floor_pts
                        
                        stem_item = gl.GLLinePlotItem(pos=stem_pts, color=(1, 1, 1, 0.4), width=1, antialias=True, mode='lines')
                        self.gl_widget.addItem(stem_item)
                    # ---------------------------------------
        
            self.gl_widget.opts['center'] = pg.Vector(5*sx, 5*sy, 5*sz) # Center camera on scaled data
            self.gl_widget.setCameraPosition(distance=25*max(sx, sy, sz), elevation=25, azimuth=45)
            self._init_3d_scene(bounds, (sx, sy, sz)) # Pass scales to the scene builder
            
        except Exception as e:
            import traceback
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the 3D plot.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False

    def _draw_heatmap(self, res_dict):
        try:
            if hasattr(self, 'progress_dialog'): self.progress_dialog.accept()
            if not res_dict: return
                
            dummy_arr = np.array([0.0], dtype=np.float32)
            for c in self.curve_pool: 
                c.setData(x=dummy_arr, y=dummy_arr)
                c.setVisible(False)
            for s in self.scatter_pool: 
                s.setData(x=dummy_arr, y=dummy_arr)
                s.setVisible(False)
            for eb in self.errorbar_pool: 
                eb.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                eb.setVisible(False)
            for ac in self.avg_error_pool: 
                ac.setData(x=dummy_arr, y=dummy_arr, height=dummy_arr, width=dummy_arr)
                ac.setVisible(False)
    
            self.legend.hide()
            self.heatmap_item.setVisible(True) 
            self.heatmap_image_item.setVisible(True)
            
            pair = self.series_data[self.plot_mode][0] if self.series_data.get(self.plot_mode) else {}
            self.plot_widget.setLabel("bottom", pair.get("x_name", "X"))
            self.plot_widget.setLabel("left", pair.get("y_name", "Y"))
            
            xlog, ylog, zlog = self.xscale.currentText() == "Log", self.yscale.currentText() == "Log", self.zscale.currentText() == "Log"
            xbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.xbase.text())
            ybase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.ybase.text())
            zbase = getattr(self, '_parse_log_base', lambda x: 10.0)(self.zbase.text())
            
            self.plot_widget.getAxis('bottom').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('top').set_custom_log(xlog, xbase)
            self.plot_widget.getAxis('left').set_custom_log(ylog, ybase)
            self.plot_widget.getAxis('right').set_custom_log(ylog, ybase)
            
            self.heatmap_item.axis.setLabel(res_dict.get("z_axis_name", "Z"), color='k')
            self.heatmap_item.axis.set_custom_log(zlog, zbase)
            self._apply_axis_fonts()
            
            img_data = res_dict["img_data"]
            x_min, x_max = res_dict["x_min"], res_dict["x_max"]
            y_min, y_max = res_dict["y_min"], res_dict["y_max"]
            z_min, z_max = res_dict["z_min"], res_dict["z_max"]
            
            self.heatmap_image_item.setImage(img_data)
            try: self.heatmap_item.gradient.setColorMap(pg.colormap.get(self.heatmap_cmap.currentText(), source='matplotlib'))
            except: self.heatmap_item.gradient.loadPreset('viridis')
            
            rect_w = x_max - x_min if x_max > x_min else 1.0
            rect_h = y_max - y_min if y_max > y_min else 1.0
            self.heatmap_image_item.setRect(pg.QtCore.QRectF(x_min, y_min, rect_w, rect_h))
            
            self.heatmap_item.setLevels(z_min, z_max)
            self.plot_widget.autoRange(padding=0)
            self.plot_widget.getViewBox().setLimits(xMin=x_min, xMax=x_max, yMin=y_min, yMax=y_max)
            self.plot_widget.getViewBox().setRange(xRange=[x_min, x_max], yRange=[y_min, y_max], padding=0)
        except Exception as e:
            import traceback
            QMessageBox.critical(self, "Rendering Error", f"A fatal error occurred while drawing the Heatmap.\n\n{e}\n\n{traceback.format_exc()}")
        finally:
            self._is_plotting = False
            
    def save_plot(self):
        # Limit export formats for 3D since OpenGL renders as a pixel buffer (no SVG support)
        if self.plot_mode == "3D":
            file_filter = "PNG (*.png);;JPEG (*.jpg)"
        else:
            file_filter = "PNG (*.png);;JPEG (*.jpg);;SVG (*.svg)"

        fname, _ = QFileDialog.getSaveFileName(
            self, "Save Plot", "", file_filter
        )
        if not fname:
            return

        # Apply default extension if the user didn't type one
        if not os.path.splitext(fname)[1]:
            fname += ".png"

        # ==========================================
        # 3D SAVE LOGIC
        # ==========================================
        if self.plot_mode == "3D":
            # Grab the current frame buffer from the OpenGL widget
            img = self.gl_widget.readQImage()
            img.save(fname)
            return

        # ==========================================
        # 2D / HEATMAP SAVE LOGIC
        # ==========================================
        # Hide the interactive scaler temporarily if we're in Heatmap mode
        if self.plot_mode == "Heatmap":
            self.heatmap_item.vb.hide()
            QApplication.processEvents() # Force UI to update before exporting

        exporter = (
            pgexp.SVGExporter(self.plot_widget.plotItem)
            if fname.lower().endswith(".svg")
            else pgexp.ImageExporter(self.plot_widget.plotItem)
        )
        exporter.export(fname)

        # Restore the interactive scaler
        if self.plot_mode == "Heatmap":
            self.heatmap_item.vb.show()
            
    def export_plotted_data(self):
        if not getattr(self, 'last_plotted_data', None):
            QMessageBox.warning(self, "No Data", "No plot data available to export.\nPlease draw a plot first.")
            return

        fname, _ = QFileDialog.getSaveFileName(self, "Export Plotted Data to CSV", "", "CSV files (*.csv)", options=QFileDialog.DontConfirmOverwrite)
        if not fname: return
        if not fname.lower().endswith('.csv'): fname += '.csv'

        append_mode = False
        if os.path.exists(fname):
            msg = QMessageBox(self)
            msg.setWindowTitle("File Exists")
            msg.setText("This file already exists.\n\nWould you like to Append the new columns to it, or Overwrite it entirely?")
            btn_append = msg.addButton("Append", QMessageBox.AcceptRole)
            btn_overwrite = msg.addButton("Overwrite", QMessageBox.DestructiveRole)
            btn_cancel = msg.addButton("Cancel", QMessageBox.RejectRole)
            msg.exec()
            
            if msg.clickedButton() == btn_cancel: return
            append_mode = (msg.clickedButton() == btn_append)

        new_cols = {}
        def add_to_cols(name, data_list):
            data_arr = np.array(data_list, dtype=np.float64)
            col_name = name
            if col_name in new_cols:
                existing = np.array(new_cols[col_name], dtype=np.float64)
                if len(existing) == len(data_arr):
                    try:
                        if np.allclose(existing, data_arr, equal_nan=True): return
                    except Exception: pass
                base = col_name
                counter = 1
                while col_name in new_cols:
                    col_name = f"{base} [{counter}]"
                    counter += 1
            new_cols[col_name] = data_arr.tolist()

        data = self.last_plotted_data
        
        if data['mode'] == '2D':
            is_average = any(pkg['type'] == 'average' for pkg in data['packages'])
            pairs = {}
            for pkg in data['packages']:
                pidx = pkg.get('pair_idx', 0)
                if pidx not in pairs: pairs[pidx] = []
                pairs[pidx].append(pkg)
                
            for pidx, pkgs in pairs.items():
                x_name = pkgs[0].get('x_name', 'X')
                y_name = pkgs[0].get('y_name', 'Y')
                
                agg_x, agg_y, agg_xstd, agg_ystd = [], [], [], []
                for pkg in pkgs:
                    if pkg['type'] == 'standard':
                        agg_x.extend(pkg['x'])
                        agg_y.extend(pkg['y'])
                    elif pkg['type'] == 'average':
                        agg_x.append(pkg['x_mean'])
                        agg_y.append(pkg['y_mean'])
                        agg_xstd.append(pkg.get('x_std', 0.0))
                        agg_ystd.append(pkg.get('y_std', 0.0))
                        
                if is_average:
                    add_to_cols(f"{x_name} (Avg)", agg_x)
                    add_to_cols(f"{y_name} (Avg)", agg_y)
                    add_to_cols(f"{x_name} (Std)", agg_xstd)
                    add_to_cols(f"{y_name} (Std)", agg_ystd)
                else:
                    add_to_cols(x_name, agg_x)
                    add_to_cols(y_name, agg_y)
                    
        elif data['mode'] == '3D':
            pair = self.series_data["3D"][0]
            x_name = pair.get('x_name', 'X')
            y_name = pair.get('y_name', 'Y')
            z_name = pair.get('z_name', 'Z')
            
            agg_x, agg_y, agg_z = [], [], []
            for i, sw, pts in data['data']:
                if isinstance(pts, dict) and 'SURFACE' in str(data['data'][0][0]):
                    grid_x, grid_y = np.meshgrid(pts['x_1d'], pts['y_1d'], indexing='ij')
                    agg_x.extend(grid_x.flatten())
                    agg_y.extend(grid_y.flatten())
                    agg_z.extend(pts['z_2d'].flatten())
                else:
                    agg_x.extend(pts[:,0])
                    agg_y.extend(pts[:,1])
                    agg_z.extend(pts[:,2])
                    
            add_to_cols(x_name, agg_x)
            add_to_cols(y_name, agg_y)
            add_to_cols(z_name, agg_z)

        existing_cols = {}
        if append_mode:
            import csv
            try:
                with open(fname, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    headers = next(reader, [])
                    cols_data = {h: [] for h in headers}
                    for row in reader:
                        for i, h in enumerate(headers):
                            val = row[i] if i < len(row) else ''
                            try: cols_data[h].append(float(val) if val.strip() else np.nan)
                            except: cols_data[h].append(np.nan)
                    existing_cols = cols_data
            except Exception: pass

        final_cols = dict(existing_cols)
        for k, v in new_cols.items():
            new_k = k
            counter = 1
            while new_k in final_cols:
                new_k = f"{k} [{counter}]"
                counter += 1
            final_cols[new_k] = v

        max_len = max([len(v) for v in final_cols.values()] + [0])
        import csv
        try:
            with open(fname, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = list(final_cols.keys())
                writer.writerow(headers)
                
                for i in range(max_len):
                    row = []
                    for h in headers:
                        col_data = final_cols[h]
                        if i < len(col_data):
                            val = col_data[i]
                            if isinstance(val, (float, np.floating)) and np.isnan(val):
                                row.append("")
                            else:
                                row.append(f"{val:.6g}")
                        else:
                            row.append("")
                    writer.writerow(row)
                    
            QMessageBox.information(self, "Export Complete", "Data successfully exported to CSV!")
        except PermissionError:
            QMessageBox.critical(self, "Export Failed", "Permission denied.\nPlease close the CSV file if it is open in Excel and try again.")

    def open_area_under_curve(self):
        if not self.dataset: return
        
        res = self._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) == 0: 
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "No Data", "Please plot a 2D curve first.")
            return

        # 1. Create as non-modal floating palette
        if hasattr(self, 'auc_dlg') and self.auc_dlg is not None:
            try: self.auc_dlg.close()
            except: pass
            
        self.auc_dlg = AreaUnderCurveDialog(self)
        self.auc_dlg.setWindowModality(Qt.NonModal)
        
        def on_accept():
            method = self.auc_dlg.get_result()
            x_sel, y_sel, _, pair = self._get_all_plotted_xy(apply_selection=True)
            if len(x_sel) < 3:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Not Enough Data", "Select a larger region of data to integrate.")
                self.auc_dlg.show() # Pop it back up so they can try again
                return
            
            self._calculate_and_shade_auc(x_sel, y_sel, method, pair)
            self.clear_selection()
            
        def on_reject():
            self.clear_selection()
            
        self.auc_dlg.accepted.connect(on_accept)
        self.auc_dlg.rejected.connect(on_reject)
        self.auc_dlg.show()
    
    def open_spectrogram(self):
        res = self._get_all_plotted_xy(apply_selection=False)
        if len(res) < 4 or len(res[0]) < 100:
            QMessageBox.warning(self, "Not Enough Data", "You need a standard 2D plot with at least 100 points to generate a Spectrogram.")
            return
            
        x_full, y_full, _, pair = res
        
        # Close old dialog if it's open
        if hasattr(self, 'spec_dlg') and self.spec_dlg is not None:
            try: self.spec_dlg.close()
            except: pass
            
        self.spec_dlg = SpectrogramDialog(self, len(x_full))
        self.spec_dlg.setWindowModality(Qt.NonModal) # Let user click around the main UI
        
        def run_stft():
            import scipy.signal as sig
            
            # 1. Get Params
            p = self.spec_dlg.get_params()
            
            # 2. Sort chronologically just in case
            sort_idx = np.argsort(x_full)
            x, y = x_full[sort_idx], y_full[sort_idx]
            
            # 3. Calculate sampling frequency (fs) from the X-axis time steps
            dt = np.median(np.diff(x))
            fs = 1.0 / dt if dt > 0 else 1.0
            
            # 4. Generate the Spectrogram!
            f, t, Sxx = sig.spectrogram(y, fs=fs, window=p["window"], nperseg=p["nperseg"], noverlap=p["noverlap"])
            
            # 5. Format the Z-axis Data
            if p["log"]:
                with np.errstate(divide='ignore'):
                    Sxx = 10 * np.log10(Sxx + 1e-12) # Add tiny offset to prevent log(0)
                z_name = "Power (dB)"
            else:
                z_name = "Power"
                
            img_data = Sxx.T # Transpose so Time is X, Freq is Y
            
            # 6. Package it into our Heatmap system's specific format
            res_dict = {
                "img_data": img_data,
                "x_min": x[0] + t[0], "x_max": x[0] + t[-1],
                "y_min": f[0], "y_max": f[-1],
                "z_min": np.min(img_data), "z_max": np.max(img_data),
                "z_axis_name": z_name
            }
            
            # 7. Hijack the main UI safely
            self.stft_res_dict = res_dict
            self.stft_mode_active = True
            self._ignore_mode_clear = True
            
            # This natively calls self.plot() at the end, which triggers our new intercept!
            self.set_plot_mode("Heatmap") 
            self._ignore_mode_clear = False
            
            
            # 8. Override the axis labels to represent Time and Freq
            self.plot_widget.setLabel("bottom", pair.get('x_name', 'Time'))
            self.plot_widget.setLabel("left", "Frequency (Hz)")
            
        self.spec_dlg.apply_btn.clicked.connect(run_stft)
        self.spec_dlg.show()
    
    def _activate_auc_line_tool(self, dialog_ref):
        import pyqtgraph as pg
        import numpy as np
        from PyQt5.QtWidgets import QPushButton
        
        x_full, y_full, _, _ = self._get_all_plotted_xy(apply_selection=False)
        if len(x_full) == 0: return
        
        x_min, x_max = np.min(x_full), np.max(x_full)
        y_min = np.min(y_full)
        
        # Place a line spanning the middle 50% of the data
        pts = [[x_min + (x_max-x_min)*0.25, y_min], [x_max - (x_max-x_min)*0.25, y_min]]
        self.auc_manual_roi = pg.LineSegmentROI(pts, pen=pg.mkPen('g', width=3))
        self.plot_widget.addItem(self.auc_manual_roi)
        
        self.auc_done_btn = QPushButton("✅ Apply Line", self.plot_wrapper)
        self.auc_done_btn.setStyleSheet("font-weight: bold; background-color: #d0e8ff; border: 2px solid #0055ff; padding: 8px; border-radius: 4px;")
        self.auc_done_btn.move(20, 20)
        self.auc_done_btn.show()
        
        def on_done():
            self.auc_done_btn.hide()
            self.auc_done_btn.deleteLater()
            
            # 1. Extract endpoints from the ROI handles
            handles = self.auc_manual_roi.getSceneHandlePositions()
            pt0 = self.plot_widget.getViewBox().mapSceneToView(handles[0][1])
            pt1 = self.plot_widget.getViewBox().mapSceneToView(handles[1][1])
            x0, y0 = pt0.x(), pt0.y()
            x1, y1 = pt1.x(), pt1.y()
            
            self.plot_widget.removeItem(self.auc_manual_roi)
            
            # 2. Sort the line endpoints left-to-right
            lx = np.array([x0, x1])
            ly = np.array([y0, y1])
            sort_idx = np.argsort(lx)
            lx, ly = lx[sort_idx], ly[sort_idx]
            
            # 3. Find all data points between X bounds, whose Y is ABOVE the line
            mask = (x_full >= lx[0]) & (x_full <= lx[1])
            interp_y = np.interp(x_full[mask], lx, ly)
            above_mask = y_full[mask] >= interp_y
            
            # 4. Save global indices and highlight
            global_indices = np.where(mask)[0][above_mask]
            self.selected_indices = set(global_indices)
            
            if self.selected_indices:
                idx_array = list(self.selected_indices)
                self.highlight_scatter.setData(x_full[idx_array], y_full[idx_array])
                self.highlight_scatter.show()
                self._update_selection_stats()
            else:
                self.clear_selection()
            
            dialog_ref._finish_selection()
            
        self.auc_done_btn.clicked.connect(on_done)

    def _calculate_and_shade_auc(self, x_sel, y_sel, method, pair):
        # 1. Sort the data chronologically (left to right)
        sort_idx = np.argsort(x_sel)
        x = x_sel[sort_idx]
        y = y_sel[sort_idx]
        
        # 2. Generate the Baseline Array
        if method == "zero":
            y_base = np.zeros_like(y)
        elif method == "min":
            y_base = np.full_like(y, np.min(y))
        elif method == "endpoints":
            # Draw a straight line between the first and last point
            y_base = np.interp(x, [x[0], x[-1]], [y[0], y[-1]])
            
        # 3. Calculate Area (Integral of Data minus Integral of Baseline)
        try: area = np.trapezoid(y - y_base, x=x)
        except AttributeError: area = np.trapz(y - y_base, x=x)
        
        # 4. Generate Polygon Coordinates (Loop up the curve, then back down the baseline)
        poly_x = np.concatenate([x, x[::-1]])
        poly_y = np.concatenate([y, y_base[::-1]])
        
        # 5. Save the data to memory
        self.auc_data_records.append({
            "poly_x": poly_x, "poly_y": poly_y, 
            "area": area, "method": method, 
            "axis_side": pair.get("axis", "L")
        })
        
        self._redraw_auc_shades()

    def _redraw_auc_shades(self):
        self._clear_auc_visuals()
        if not hasattr(self, 'auc_items'): self.auc_items = []
        if not self.auc_data_records: return
        
        from PyQt5.QtWidgets import QGraphicsPolygonItem
        from PyQt5.QtGui import QPolygonF
        from PyQt5.QtCore import QPointF
        import pyqtgraph as pg
        
        total_area = 0.0
        html = f"<b style='color: #ffaa00; font-size: 14px;'>Integrals (Area Under Curve)</b><br><hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
        
        for i, rec in enumerate(self.auc_data_records):
            area = rec['area']
            total_area += area
            method_str = "Local Slant" if rec['method'] == 'endpoints' else "Min-Y" if rec['method'] == 'min' else "y=0"
            html += f"<b>Peak {i+1} ({method_str}):</b> {area:.5g}<br>"
            
            # Use distinct orange/yellow shading
            color = (255, 170, 0, 80) 
            border = (255, 170, 0, 200)
            
            polygon = QPolygonF([QPointF(float(px), float(py)) for px, py in zip(rec['poly_x'], rec['poly_y'])])
            item = QGraphicsPolygonItem(polygon)
            item.setPen(pg.mkPen(border, width=2))
            item.setBrush(pg.mkBrush(color))
            item.setZValue(-5) # Sit perfectly behind the data line
            
            target_vb = self.vb_right if rec['axis_side'] == "R" else self.plot_widget
            target_vb.addItem(item)
            self.auc_items.append((item, target_vb))
            
        html += f"<hr style='border: 0; border-top: 1px solid #ccc; margin: 4px 0;'>"
        html += f"<b>Total Area:</b>&nbsp;&nbsp;{total_area:.5g}"
        
        self.auc_stats_label.setText(html)
        self.auc_stats_label.adjustSize()
        if not self.auc_stats_label.isVisible():
            self.auc_stats_label.move(20, 100) # Move slightly lower so it doesn't overlap the Region Stats
            self.auc_stats_label.show()
            self.auc_stats_label.raise_()
            
        self.toggle_auc_btn.setVisible(True)
        self.toggle_auc_btn.setChecked(True)
        self.toggle_auc_btn.setStyleSheet("font-weight: bold; background-color: #fff0d0; border: 2px solid #ffaa00; border-radius: 4px; padding: 6px; color: #ff8800;")

    def _clear_auc_visuals(self):
        if hasattr(self, 'auc_items'):
            for item, vb in self.auc_items:
                try: vb.removeItem(item)
                except: pass
            self.auc_items.clear()

    def _toggle_auc_areas(self):
        is_checked = self.toggle_auc_btn.isChecked()
        if is_checked:
            self.toggle_auc_btn.setStyleSheet("font-weight: bold; background-color: #fff0d0; border: 2px solid #ffaa00; border-radius: 4px; padding: 6px; color: #ff8800;")
            if self.auc_data_records: self.auc_stats_label.show()
        else:
            self.toggle_auc_btn.setStyleSheet("background-color: #f5f5f5; border: 1px solid #8a8a8a; border-radius: 4px; padding: 6px; color: black;")
            self.auc_stats_label.hide()
            
        for item, _ in getattr(self, 'auc_items', []):
            item.setVisible(is_checked)
    
    def _toggle_surface_mode(self, checked):
        # Sync the hidden settings checkbox so preferences still save correctly
        if hasattr(self, 'gl_surface_cb'):
            self.gl_surface_cb.blockSignals(True)
            self.gl_surface_cb.setChecked(checked)
            self.gl_surface_cb.blockSignals(False)

        # Update the UI button styling
        if checked:
            self.gl_surface_main_btn.setText("✔ Surface View (Linear Mesh)")
            self.gl_surface_main_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; border: 2px solid {theme.success_border}; padding: 6px; background-color: {theme.bg};")
        else:
            self.gl_surface_main_btn.setText("○ Surface View (Off)")
            # --- FIX: Changed theme.text to theme.fg ---
            self.gl_surface_main_btn.setStyleSheet(f"color: {theme.fg}; border: 1px solid {theme.border}; padding: 6px; background-color: {theme.bg};")

        # Context requirement: Turn off crosshair when surface mode changes
        if hasattr(self, 'crosshair_3d'):
            self.crosshair_3d.disable()

        self.plot()
