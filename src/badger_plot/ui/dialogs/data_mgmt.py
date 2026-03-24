# ui/dialogs/data_mgmt.py
import os
import re
import numpy as np
from datetime import datetime
from PyQt5.QtCore import Qt, QTimer, QAbstractTableModel, QModelIndex
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QFormLayout, QComboBox, QLineEdit, QWidget, QCheckBox, QTabWidget, QGroupBox,
    QTableView, QScrollArea, QMessageBox, QSpinBox, QListWidget
)

from core.constants import PHYSICS_CONSTANTS
from core.theme import theme
from core.data_loader import BADGERLOOP_AVAILABLE

class CopyableErrorDialog(QDialog):
    def __init__(self, title, header, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(650, 450)
        layout = QVBoxLayout(self)
        
        lbl = QLabel(header)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; font-size: 14px;")
        layout.addWidget(lbl)
        
        self.txt = QTextEdit()
        self.txt.setPlainText(details)
        self.txt.setReadOnly(True)
        self.txt.setStyleSheet(f"background-color: {theme.bg}; color: {theme.fg}; border: 1px solid {theme.border}; font-family: Consolas, monospace; padding: 8px;")
        layout.addWidget(self.txt)
        
        btn_box = QHBoxLayout()
        copy_btn = QPushButton("📋 Copy to Clipboard")
        copy_btn.setStyleSheet("font-weight: bold; padding: 6px;")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("padding: 6px;")
        close_btn.clicked.connect(self.accept)
        
        btn_box.addWidget(copy_btn)
        btn_box.addStretch()
        btn_box.addWidget(close_btn)
        layout.addLayout(btn_box)
        
    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.txt.toPlainText())
        btn = self.sender()
        if btn:
            btn.setText("✔ Copied!")
            QTimer.singleShot(1500, lambda b=btn: b.setText("📋 Copy to Clipboard"))


class FileImportDialog(QDialog):
    # --- NEW: Added detected_type parameter ---
    def __init__(self, parent=None, detected_type="CSV"):
        super().__init__(parent)
        self.setWindowTitle("Import Data File")
        
        layout = QVBoxLayout(self)
        
        type_form = QFormLayout()
        self.file_type = QComboBox()
        self.file_type.addItems(["BadgerLoop", "CSV", "HDF5"])
        
        if not globals().get('BADGERLOOP_AVAILABLE', True):
            self.file_type.model().item(0).setEnabled(False) 
            self.file_type.setCurrentIndex(1) 
            
        # --- NEW: Set the dropdown to the auto-detected type ---
        idx = self.file_type.findText(detected_type)
        if idx >= 0 and self.file_type.model().item(idx).isEnabled():
            self.file_type.setCurrentIndex(idx)
        # -------------------------------------------------------
            
        type_form.addRow("File Type:", self.file_type)
        layout.addLayout(type_form)
        
        self.csv_container = QWidget()
        csv_form = QFormLayout(self.csv_container)
        csv_form.setContentsMargins(0, 0, 0, 0)
        
        self.delimiter = QComboBox()
        self.delimiter.addItems(["Auto-detect", "Comma (,)", "Tab", "Semicolon (;)", "Space", "Other"])
        csv_form.addRow("Delimiter:", self.delimiter)
        
        self.custom_delimiter = QLineEdit()
        self.custom_delimiter.setMaxLength(1)
        self.custom_delim_label = QLabel("Custom Delimiter:")
        csv_form.addRow(self.custom_delim_label, self.custom_delimiter)
        self.custom_delimiter.setVisible(False)
        self.custom_delim_label.setVisible(False)
        
        self.has_header = QCheckBox()
        self.has_header.setChecked(True)
        csv_form.addRow("Has Header:", self.has_header)
        
        layout.addWidget(self.csv_container)
        
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(btn_ok)
        btn_box.addWidget(btn_cancel)
        layout.addLayout(btn_box)
        
        self.delimiter.currentTextChanged.connect(self.toggle_custom_delimiter)
        self.file_type.currentTextChanged.connect(self.toggle_csv_options)
        self.toggle_csv_options(self.file_type.currentText())

    def toggle_csv_options(self, text):
        is_csv = (text == "CSV")
        self.csv_container.setVisible(is_csv)
        self.adjustSize()

    def toggle_custom_delimiter(self, text):
        is_other = (text == "Other")
        self.custom_delimiter.setVisible(is_other)
        self.custom_delim_label.setVisible(is_other)
        self.adjustSize()

    def get_options(self):
        delim_map = {"Comma (,)": ",", "Tab": "\t", "Semicolon (;)": ";", "Space": " "}
        sel = self.delimiter.currentText()
        if sel == "Auto-detect":
            delim_char = "auto"
        elif sel == "Other":
            delim_char = self.custom_delimiter.text() or ","
        else:
            delim_char = delim_map.get(sel, ",")
            
        return {
            "type": self.file_type.currentText(),
            "delimiter": delim_char,
            "has_header": self.has_header.isChecked()
        }


class NumpyTableModel(QAbstractTableModel):
    def __init__(self, data, headers):
        super().__init__()
        self._data = data
        self._headers = headers

    def rowCount(self, parent=QModelIndex()):
        return self._data.shape[0] if self._data.size else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        if role == Qt.DisplayRole:
            val = self._data[index.row(), index.column()]
            try: return f"{val:.6g}"
            except Exception: return str(val)
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignRight | Qt.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal: return self._headers[section]
            else: return str(section)
        return None


class SweepTableDialog(QDialog):
    def __init__(self, dataset, sweep, parent=None, is_csv=False):
        super().__init__(parent)
        self.setWindowTitle("CSV Data" if is_csv else f"Sweep {sweep} data")
        self.resize(950, 550)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        if is_csv:
            form.addRow("Points:", QLabel(str(dataset.num_points)))
            form.addRow("Columns:", QLabel(str(dataset.num_inputs + dataset.num_outputs)))
            data = dataset.data
        else:
            form.addRow("Sweep:", QLabel(str(sweep)))
            form.addRow("Points:", QLabel(str(dataset.sweeps[sweep].num_points)))
            form.addRow("Columns:", QLabel(str(dataset.num_inputs + dataset.num_outputs)))
            data = dataset.sweeps[sweep].data

        layout.addLayout(form)
        layout.addSpacing(10)

        headers = [dataset.column_names[i] for i in range(dataset.num_inputs + dataset.num_outputs)]
        self.table_view = QTableView()
        self.model = NumpyTableModel(data, headers)
        self.table_view.setModel(self.model)
        
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setStyleSheet(f"alternate-background-color: {theme.bg}; background-color: {theme.panel_bg}; color: {theme.fg};")
        
        font = self.table_view.font()
        font.setFamily("Consolas, DejaVu Sans Mono, Menlo, Courier New")
        font.setPointSize(10)
        self.table_view.setFont(font)
        
        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setDefaultSectionSize(120) 

        layout.addWidget(self.table_view)

        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)


class ManageColumnsDialog(QDialog):
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Columns")
        self.setFixedSize(450, 220)
        self.dataset = dataset

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        
        # --- TAB 1: RENAME ---
        self.tab_rename = QWidget()
        form_rename = QFormLayout(self.tab_rename)
        form_rename.setLabelAlignment(Qt.AlignRight)
        
        self.rename_combo = QComboBox()
        for idx, name in dataset.column_names.items():
            self.rename_combo.addItem(f"{idx}: {name}", idx)
            
        self.current_name = QLabel("")
        self.new_name_edit = QLineEdit()
        
        form_rename.addRow("Column:", self.rename_combo)
        form_rename.addRow("Current name:", self.current_name)
        form_rename.addRow("New name:", self.new_name_edit)
        self.tab_rename.setLayout(form_rename)
        
        # --- TAB 2: DELETE ---
        self.tab_delete = QWidget()
        form_delete = QFormLayout(self.tab_delete)
        form_delete.setLabelAlignment(Qt.AlignRight)
        
        self.delete_combo = QComboBox()
        for idx, name in dataset.column_names.items():
            self.delete_combo.addItem(f"{idx}: {name}", idx)
            
        form_delete.addRow("Column to delete:", self.delete_combo)
        warning_lbl = QLabel(f"<br><b style='color: {theme.danger_text};'>Warning: Deleting a column is irreversible!</b>")
        warning_lbl.setAlignment(Qt.AlignCenter)
        form_delete.addRow("", warning_lbl)
        self.tab_delete.setLayout(form_delete)
        
        self.tabs.addTab(self.tab_rename, "Rename")
        self.tabs.addTab(self.tab_delete, "Delete")
        layout.addWidget(self.tabs)

        buttons = QHBoxLayout()
        ok = QPushButton("OK")
        cancel = QPushButton("Cancel")
        buttons.addStretch()
        buttons.addWidget(ok)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)

        self.rename_combo.currentIndexChanged.connect(self._update_current_name)
        self._update_current_name()

    def _update_current_name(self):
        idx = self.rename_combo.currentData()
        self.current_name.setText(self.dataset.column_names.get(idx, ""))
        
    def accept(self):
        # We only care about uniqueness if they are trying to Rename a column
        if self.tabs.currentIndex() == 0: 
            idx = self.rename_combo.currentData()
            old_name = self.dataset.column_names.get(idx, "")
            new_name = self.new_name_edit.text().strip()
            
            # If they didn't change the name, just close the dialog silently
            if new_name == old_name:
                super().reject() # Reject skips the file-writing logic entirely
                return
                
            # If they picked a new name, check if it already exists somewhere else
            existing_names = list(self.dataset.column_names.values())
            if new_name in existing_names:
                QMessageBox.warning(self, "Duplicate Name", f"The column '{new_name}' already exists.\nPlease choose a unique name.")
                return
                
        super().accept()

    def get_result(self):
        if self.tabs.currentIndex() == 0:
            return "rename", self.rename_combo.currentData(), self.new_name_edit.text().strip()
        else:
            return "delete", self.delete_combo.currentData(), None

class FolderEditChoiceDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Folder Modification Options")
        self.setFixedSize(450, 180)
        
        layout = QVBoxLayout(self)
        lbl = QLabel(
            "<b>You are about to modify a Multi-CSV Folder dataset.</b><br><br>"
            "To protect your original data, you must choose how to save this change:"
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        
        self.btn_mirror = QPushButton("📂 Create a MIRROR_ Folder (Keep files separate)")
        self.btn_mirror.setStyleSheet("font-weight: bold; padding: 8px;")
        
        self.btn_concat = QPushButton("📄 Concatenate into a Single CSV")
        self.btn_concat.setStyleSheet("font-weight: bold; padding: 8px;")
        
        btn_cancel = QPushButton("Cancel")
        
        self.btn_mirror.clicked.connect(lambda: self.done(1))
        self.btn_concat.clicked.connect(lambda: self.done(2))
        btn_cancel.clicked.connect(self.reject)
        
        layout.addWidget(self.btn_mirror)
        layout.addWidget(self.btn_concat)
        layout.addWidget(btn_cancel)

class MetadataDialog(QDialog):
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dataset Metadata")
        self.resize(550, 600) 
        self.dataset = dataset
        self.parent_gui = parent

        layout = QVBoxLayout(self)
        
        is_mirror_str = "No"
        try:
            with open(dataset.filename, 'r', encoding='utf-8', errors='ignore') as f:
                if re.search(r'Is\s+Mirror\s+File\s*:\s*Yes', f.read(2000), re.IGNORECASE):
                    is_mirror_str = "Yes"
        except Exception: pass
        
        ds_type = type(dataset).__name__
        
        # ==========================================
        # 1. MULTI-CSV FOLDER VIEW
        # ==========================================
        if ds_type == 'MultiCSVDataset':
            folder_size_kb = sum(os.path.getsize(f) for f in dataset.file_list) / 1024
            
            general_group = QGroupBox("Folder Information")
            general_layout = QFormLayout()
            general_layout.setLabelAlignment(Qt.AlignRight)
            
            general_layout.addRow("<b>Folder Name:</b>", QLabel(os.path.basename(dataset.filename)))
            general_layout.addRow("<b>Total CSV Files:</b>", QLabel(str(dataset.num_sweeps)))
            general_layout.addRow("<b>Total Data Points:</b>", QLabel(str(dataset.num_points)))
            general_layout.addRow("<b>Columns per file:</b>", QLabel(str(dataset.num_inputs)))
            general_layout.addRow("<b>Total Size:</b>", QLabel(f"{folder_size_kb:.2f} KB"))
            
            path_label = QLineEdit(dataset.filename)
            path_label.setReadOnly(True)
            path_label.setStyleSheet("border: none; background: transparent;")
            path_label.setCursorPosition(0)
            general_layout.addRow("<b>Location:</b>", path_label)
            
            general_group.setLayout(general_layout)
            layout.addWidget(general_group)
            
            inspect_group = QGroupBox("Inspect Specific Sweep / File")
            inspect_layout = QHBoxLayout()
            self.sweep_spin = QSpinBox()
            self.sweep_spin.setRange(0, max(0, dataset.num_sweeps - 1))
            inspect_layout.addWidget(QLabel("Sweep Number:"))
            inspect_layout.addWidget(self.sweep_spin)
            
            inspect_btn = QPushButton("View File Metadata")
            inspect_btn.clicked.connect(self.view_specific_file)
            inspect_layout.addWidget(inspect_btn)
            
            inspect_group.setLayout(inspect_layout)
            layout.addWidget(inspect_group)
            layout.addStretch()

        # ==========================================
        # 2. STANDARD CSV VIEW
        # ==========================================
        elif ds_type == 'CSVDataset':
            try:
                file_stat = os.stat(dataset.filename)
                file_size_kb = file_stat.st_size / 1024
                created_time = datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
                modified_time = datetime.fromtimestamp(file_stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                file_size_kb = 0; created_time = "Unknown"; modified_time = "Unknown"
                
            general_group = QGroupBox("File Information")
            general_layout = QFormLayout()
            general_layout.setLabelAlignment(Qt.AlignRight)
            
            general_layout.addRow("<b>File Name:</b>", QLabel(os.path.basename(dataset.filename)))
            general_layout.addRow(f"<b style='color: {theme.primary_text};'>Is this a mirror file?:</b>", QLabel(f"<span style='color: {theme.primary_text};'><b>{is_mirror_str}</b></span>"))
            
            path_label = QLineEdit(os.path.dirname(dataset.filename))
            path_label.setReadOnly(True)
            path_label.setStyleSheet("border: none; background: transparent;")
            path_label.setCursorPosition(0)
            general_layout.addRow("<b>Location:</b>", path_label)
            
            general_layout.addRow("<b>Size:</b>", QLabel(f"{file_size_kb:.2f} KB"))
            general_layout.addRow("<b>Created:</b>", QLabel(created_time))
            general_layout.addRow("<b>Modified:</b>", QLabel(modified_time))
            
            general_group.setLayout(general_layout)
            layout.addWidget(general_group)
            
            acq_group = QGroupBox("Dataset Information")
            acq_layout = QFormLayout()
            acq_layout.setLabelAlignment(Qt.AlignRight)
            
            acq_layout.addRow("<b>Total Data Points:</b>", QLabel(str(dataset.num_points)))
            acq_layout.addRow("<b>Total Columns:</b>", QLabel(str(dataset.num_inputs)))
            if dataset.num_sweeps > 1:
                acq_layout.addRow("<b>Detected Sweeps:</b>", QLabel(str(dataset.num_sweeps)))
            
            acq_group.setLayout(acq_layout)
            layout.addWidget(acq_group)
            layout.addStretch()
            
        # ==========================================
        # 3. BADGERLOOP VIEW
        # ==========================================
        else:
            version = "Unknown"
            settling_time = str(getattr(dataset, 'settling_time', 'Unknown'))
            sweep_delay = str(getattr(dataset, 'sweep_delay', 'Unknown'))
            
            try:
                with open(dataset.filename, 'r', encoding='utf-8', errors='ignore') as f:
                    header_content = f.read(2000)
                    v_match = re.search(r'version[\s:=]+([^\s\t\n]+)', header_content, re.IGNORECASE)
                    if v_match: version = v_match.group(1).strip()
            except Exception: pass
                
            general_group = QGroupBox("General Information")
            general_layout = QFormLayout()
            general_layout.setLabelAlignment(Qt.AlignRight)
            
            d_name = getattr(dataset, 'name', 'Unknown')
            general_layout.addRow("<b>Name:</b>", QLabel(str(d_name)))
            general_layout.addRow(f"<b style='color: {theme.primary_text};'>Is this a mirror file?:</b>", QLabel(f"<span style='color: {theme.primary_text};'><b>{is_mirror_str}</b></span>"))
            
            d_date = getattr(dataset, 'date', None)
            date_str = d_date.strftime("%Y-%m-%d %H:%M:%S") if d_date else "Unknown"
            general_layout.addRow("<b>Date:</b>", QLabel(date_str))
            general_layout.addRow("<b>BadgerLoop Version:</b>", QLabel(version))
            
            general_group.setLayout(general_layout)
            layout.addWidget(general_group)
            
            acq_group = QGroupBox("Acquisition Settings")
            acq_layout = QFormLayout()
            acq_layout.setLabelAlignment(Qt.AlignRight)
            
            acq_layout.addRow("<b>Settling Time:</b>", QLabel(f"{settling_time} ms"))
            acq_layout.addRow("<b>Sweep Delay:</b>", QLabel(f"{sweep_delay} ms"))
            acq_layout.addRow("<b>Sweeps:</b>", QLabel(str(getattr(dataset, 'num_sweeps', 'Unknown'))))
            acq_layout.addRow("<b>Inputs:</b>", QLabel(str(getattr(dataset, 'num_inputs', 'Unknown'))))
            acq_layout.addRow("<b>Outputs:</b>", QLabel(str(getattr(dataset, 'num_outputs', 'Unknown'))))
            
            acq_group.setLayout(acq_layout)
            layout.addWidget(acq_group)

            disabled_insts = getattr(dataset, 'disabled_outputs', []) + getattr(dataset, 'disabled_inputs', [])
            if disabled_insts:
                dis_group = QGroupBox("Disabled Instruments (Parked States)")
                dis_layout = QVBoxLayout()
                
                dis_table = QTableWidget()
                dis_table.setColumnCount(3)
                dis_table.setHorizontalHeaderLabels(["Name", "Type", "Parked Value"])
                dis_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
                dis_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
                dis_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
                dis_table.verticalHeader().setVisible(False)
                dis_table.setEditTriggers(QTableWidget.NoEditTriggers)
                dis_table.setAlternatingRowColors(True)
                dis_table.setRowCount(len(disabled_insts))
                
                for i, inst in enumerate(disabled_insts):
                    dis_table.setItem(i, 0, QTableWidgetItem(inst.get('name', 'Unknown')))
                    dis_table.setItem(i, 1, QTableWidgetItem(inst.get('type', 'Unknown').replace("BadgerLoop.", "")))
                    
                    val_str = f"{inst.get('last_value', 0.0)} {inst.get('units', '')}".strip()
                    val_item = QTableWidgetItem(val_str)
                    val_item.setForeground(QColor(theme.danger_text)) 
                    font = val_item.font()
                    font.setBold(True)
                    val_item.setFont(font)
                    dis_table.setItem(i, 2, val_item)
                
                dis_layout.addWidget(dis_table)
                dis_group.setLayout(dis_layout)
                layout.addWidget(dis_group)

        # NOTES SECTION (For all modes)
        layout.addWidget(QLabel("<b>Notes:</b>"))
        raw_notes = str(getattr(dataset, 'notes', ''))
        clean_notes = raw_notes.replace('\\n', '\n').replace('\t', '\n')
        if '\n' not in clean_notes and ';' in clean_notes:
            clean_notes = clean_notes.replace(';', ';\n')
        clean_notes = '\n'.join([line.strip() for line in clean_notes.split('\n') if line.strip()])
        
        notes_edit = QTextEdit()
        notes_edit.setPlainText(clean_notes)
        notes_edit.setReadOnly(True)
        layout.addWidget(notes_edit)

        btn = QPushButton("Close")
        btn.setFixedWidth(100)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignRight)
        
        self.setStyleSheet(f"""
            QGroupBox {{ font-weight: bold; border: 1px solid {theme.border}; border-radius: 6px; margin-top: 10px; padding-top: 15px; background-color: {theme.bg}; }}
            QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; left: 10px; color: {theme.fg}; }}
            QTextEdit, QLineEdit {{ background-color: {theme.bg}; color: {theme.fg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 4px; }}
            QLabel {{ color: {theme.fg}; }}
        """)

    def view_specific_file(self):
        idx = self.sweep_spin.value()
        filepath = self.dataset.file_list[idx]
        
        try:
            from core.data_loader import CSVDataset
            delim = getattr(self.parent_gui, 'last_load_opts', {}).get("delimiter", ",")
            has_header = getattr(self.parent_gui, 'last_load_opts', {}).get("has_header", True)
            single_ds = CSVDataset(filepath, delimiter=delim, has_header=has_header)
            MetadataDialog(single_ds, self.parent_gui).exec()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to read file metadata:\n{e}")


class ConstantsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Physics Constant")
        self.resize(650, 500)
        self.selected_key = None
        
        layout = QVBoxLayout(self)
        
        btn_layout = QHBoxLayout()
        self.insert_btn = QPushButton("Insert Selected Constant")
        self.insert_btn.setEnabled(False)
        self.insert_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; font-size: 14px; padding: 6px;")
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("padding: 6px;")
        
        btn_layout.addWidget(self.insert_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Key", "Name", "Value", "Units"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        
        self.keys = list(PHYSICS_CONSTANTS.keys())
        self.table.setRowCount(len(self.keys))
        
        for row, key in enumerate(self.keys):
            c = PHYSICS_CONSTANTS[key]
            
            key_item = QTableWidgetItem(f"{{{key}}}")
            key_item.setForeground(QColor(theme.success_text))
            font = key_item.font()
            font.setBold(True)
            key_item.setFont(font)
            
            self.table.setItem(row, 0, key_item)
            self.table.setItem(row, 1, QTableWidgetItem(c["name"]))
            self.table.setItem(row, 2, QTableWidgetItem(f"{c['value']:.6e}"))
            self.table.setItem(row, 3, QTableWidgetItem(c["units"]))
            
        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        self.table.itemSelectionChanged.connect(self.on_select)
        self.insert_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
    def on_select(self):
        selected = self.table.selectedItems()
        self.insert_btn.setEnabled(bool(selected))
        if selected:
            self.selected_key = self.keys[selected[0].row()]


class CreateColumnDialog(QDialog):
    def __init__(self, dataset, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Custom Column")
        self.resize(750, 500)
        self.dataset = dataset
        self.available_columns = dataset.column_names
        self.is_valid = False

        layout = QVBoxLayout(self)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("<b>New Column Name:</b>"))
        self.col_name_edit = QLineEdit("Calculated_Column")
        name_layout.addWidget(self.col_name_edit)
        layout.addLayout(name_layout)

        layout.addWidget(QLabel("<b>Insert Column:</b>"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(130)
        btn_container = QWidget()
        grid = QFormLayout(btn_container)
        
        row_layout = QHBoxLayout()
        cols_in_row = 0
        for i, name in self.available_columns.items():
            btn = QPushButton(name)
            btn.setStyleSheet(f"color: {theme.primary_text}; font-weight: bold; border: 1px solid {theme.primary_border}; padding: 4px;")
            btn.clicked.connect(lambda checked, n=name: self.insert_column(n))
            row_layout.addWidget(btn)
            cols_in_row += 1
            if cols_in_row == 4:
                grid.addRow(row_layout)
                row_layout = QHBoxLayout()
                cols_in_row = 0
        if cols_in_row > 0:
            grid.addRow(row_layout)
            
        scroll.setWidget(btn_container)
        layout.addWidget(scroll)

        math_lbl_layout = QHBoxLayout()
        math_lbl_layout.addWidget(QLabel("<b>Equation:</b> <i>(+, -, *, /, ^, log10(), ln(), arcsin()...)</i>"))
        math_lbl_layout.addStretch()
        
        self.time_btn = QPushButton("⏱ Generate Time Axis")
        self.time_btn.setStyleSheet(f"font-weight: bold; color: {theme.danger_text}; border: 1px solid {theme.danger_border}; padding: 4px 10px;")
        self.time_btn.clicked.connect(self.generate_time_axis)
        math_lbl_layout.addWidget(self.time_btn)
        
        self.const_btn = QPushButton("✨ Physics Constants")
        self.const_btn.setStyleSheet(f"font-weight: bold; color: {theme.success_text}; border: 1px solid {theme.success_border}; padding: 4px 10px;")
        self.const_btn.clicked.connect(self.open_constants)
        math_lbl_layout.addWidget(self.const_btn)
        layout.addLayout(math_lbl_layout)
        
        self.equation_input = QTextEdit()
        self.equation_input.setMaximumHeight(80)
        self.equation_input.textChanged.connect(self.update_preview)
        
        font = self.equation_input.font()
        font.setPointSize(11)
        self.equation_input.setFont(font)
        layout.addWidget(self.equation_input)

        layout.addWidget(QLabel("<b>Live Preview:</b>"))
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"background-color: {theme.panel_bg}; color: {theme.fg}; border: 1px solid {theme.border}; font-size: 22px; font-family: Cambria, serif; font-style: italic; padding: 10px;")
        self.preview_label.setMinimumHeight(120)
        layout.addWidget(self.preview_label)

        btn_box = QHBoxLayout()
        self.calc_btn = QPushButton("Calculate & Save")
        self.calc_btn.clicked.connect(self.handle_calculate)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(self.calc_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def generate_time_axis(self):
        if type(self.dataset).__name__ == 'CSVDataset' or not hasattr(self.dataset, 'settling_time'):
            QMessageBox.warning(self, "Not Available", "This dataset does not contain BadgerLoop timing metadata.")
            return
            
        self.col_name_edit.setText("Time (s)")
        eq = f"index * ({self.dataset.settling_time} + {self.dataset.sweep_delay}) / 1000.0"
        self.equation_input.setPlainText(eq)

    def open_constants(self):
        dlg = ConstantsDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.selected_key:
            self.equation_input.textCursor().insertText(f"{{\\{dlg.selected_key}}}")

    def handle_calculate(self):
        if not getattr(self, 'is_valid', False):
            QMessageBox.warning(self, "Invalid Equation", "Please enter a valid mathematical equation.")
            return
        # --- NEW UNIQUENESS CHECK ---
        new_name = self.col_name_edit.text().strip()
        existing_names = list(self.dataset.column_names.values())
        if new_name in existing_names:
            QMessageBox.warning(self, "Duplicate Name", f"The column '{new_name}' already exists.\nPlease choose a unique name.")
            return
        # ----------------------------
        self.accept()

    def validate_equation(self, raw_text):
        import re
        import numpy as np

        py_equation = raw_text
        col_map = {v: k for k, v in self.available_columns.items()}
        dummy_dict = {}
        
        def replace_col(match):
            name = match.group(1)
            if name not in col_map: raise ValueError()
            idx = col_map[name]
            dummy_dict[idx] = np.ones(1)
            return f"data_dict[{idx}]"
            
        try:
            py_equation = re.sub(r'\[(.*?)\]', replace_col, py_equation)
        except ValueError:
            return False

        def replace_const_silent(match):
            c_key = match.group(1)
            if c_key not in PHYSICS_CONSTANTS: raise ValueError()
            return f"({PHYSICS_CONSTANTS[c_key]['value']})"
            
        try:
            py_equation = re.sub(r'\{\\(.*?)\}', replace_const_silent, py_equation)
        except ValueError:
            return False

        py_equation = py_equation.replace('^', '**')
        
        # --- NEW: ADDED 'abs' TO LIST ---
        math_funcs = ['arcsinh','arccosh','arctanh','arcsin','arccos','arctan','sinh','cosh','tanh','sin','cos','tan', 'abs']
        for f in math_funcs:
            py_equation = re.sub(r'\b' + f + r'\s*\(', 'np.'+f+'(', py_equation, flags=re.IGNORECASE)
            
        py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?2\s*\(', 'np.log2(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)

        # --- NEW: NORM ENGINE ---
        def norm_func(v):
            arr = np.asarray(v, dtype=np.float64)
            m = np.max(arr)
            return arr / m if m != 0 else arr
        # ------------------------

        try:
            with np.errstate(all='ignore'):
                # Inject norm into the test environment!
                eval(py_equation, {"__builtins__": {}}, {"np": np, "data_dict": dummy_dict, "e": np.e, "pi": np.pi, "index": np.ones(1), "norm": norm_func})
            return True
        except Exception:
            return False

    def insert_column(self, col_name):
        self.equation_input.textCursor().insertText(f"[{col_name}]")

    def update_preview(self):
        raw_text = self.equation_input.toPlainText().strip()
        if not raw_text:
            self.preview_label.setText("")
            self.is_valid = False
            return

        self.is_valid = self.validate_equation(raw_text)

        if not self.is_valid:
            import html
            safe_text = html.escape(raw_text)
            self.preview_label.setText(f"<span style='color: {theme.danger_text}; font-style: normal;'>{safe_text}</span>")
            return

        import re
        html_text = raw_text
        
        cols = []
        def col_repl(m):
            cols.append(m.group(0))
            return f"__COL{len(cols)-1}__"
        html_text = re.sub(r'\[.*?\]', col_repl, html_text)
        
        consts = []
        def const_repl(m):
            c_key = m.group(1)
            if c_key in PHYSICS_CONSTANTS:
                c_html = PHYSICS_CONSTANTS[c_key]["html"]
                span = f"<span style='color: {theme.success_text}; font-weight: bold; font-style: normal;'>{c_html}</span>"
            else:
                span = f"<span style='color: {theme.danger_text};'>{{\\{c_key}}}</span>"
            consts.append(span)
            return f"__CONST{len(consts)-1}__"
            
        html_text = re.sub(r'\{\\(.*?)\}', const_repl, html_text)
        
        idx_vars = []
        def idx_repl(m):
            idx_vars.append(f"<span style='color: {theme.danger_text}; font-weight: bold; font-style: italic;'>index</span>")
            return f"__INDEX{len(idx_vars)-1}__"
        html_text = re.sub(r'\bindex\b', idx_repl, html_text)
        
        html_text = html_text.replace('*', '&middot;')
        html_text = html_text.replace('-', '&minus;')
        html_text = re.sub(r'\bpi\b', 'π', html_text) 
        
        funcs = []
        def func_repl(m):
            func = m.group(1).lower() 
            func = re.sub(r'_?([0-9]+)', r"<sub style='font-size:12px;'>\1</sub>", func)
            funcs.append(f"<span style='font-style: normal; font-weight: bold; color: {theme.fg};'>{func}</span>")
            return f"__FUNC{len(funcs)-1}__"
            
        # --- NEW: ADDED abs AND norm TO REGEX ---
        html_text = re.sub(r'\b(arcsin|arccos|arctan|arcsinh|arccosh|arctanh|sinh|cosh|tanh|sin|cos|tan|ln|log(?:_?[0-9]+)?|abs|norm)\b', func_repl, html_text, flags=re.IGNORECASE)

        def tokenize_to_horizontal(text, f_size):
            parts = re.split(r'(__COL\d+__|__FUNC\d+__|__PAREN\d+__|__EXP\d+__|__CONST\d+__|__INDEX\d+__)', text)
            row_html = "<table style='display:inline-table; border-collapse: collapse; margin: 0;'><tr>"
            for p in parts:
                if not p: continue
                row_html += f"<td style='vertical-align:middle; padding:0; white-space:nowrap; font-size:{f_size};'>{p}</td>"
            row_html += "</tr></table>"
            return row_html

        exps = []
        def resolve_exponents(text, is_exp=False):
            f_size_base = "15px" if is_exp else "22px"
            f_size_exp  = "10px" if is_exp else "15px"
            spacer      = "6px"  if is_exp else "10px"
            
            while True:
                match = re.search(r'([a-zA-Zπ]+|[0-9\.]+|__COL\d+__|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__INDEX\d+__)\s*\^\s*(-?[a-zA-Zπ]+|-?[0-9\.]+|__COL\d+__|__PAREN\d+__|__FUNC\d+__|__EXP\d+__|__CONST\d+__|__INDEX\d+__)', text)
                if not match: break
                base, exp = match.group(1), match.group(2)
                
                table = (
                    f"<table style='display:inline-table; border-collapse:collapse; margin: 0;'>"
                    f"<tr>"
                    f"<td style='vertical-align:bottom; padding:0; padding-right:1px; font-size:{f_size_base};'>{base}</td>"
                    f"<td style='vertical-align:top; padding:0;'>"
                    f"  <table style='border-collapse:collapse; margin:0; padding:0;'>"
                    f"    <tr><td style='vertical-align:top; padding:0; font-size:{f_size_exp};'>{exp}</td></tr>"
                    f"    <tr><td style='font-size:{spacer}; padding:0;'>&nbsp;</td></tr>"
                    f"  </table>"
                    f"</td>"
                    f"</tr></table>"
                )
                exps.append(table)
                text = text[:match.start()] + f"__EXP{len(exps)-1}__" + text[match.end():]
            return text

        parens = []
        def process_math_block(text, is_exp=False, has_parens=False):
            f_size = "15px" if is_exp else "22px"
            p_size = "130%" 
            
            if '/' not in text:
                res = tokenize_to_horizontal(text, f_size)
                if has_parens:
                    return (
                        f"<table style='display:inline-table; border-collapse:collapse; margin:0;'><tr>"
                        f"<td style='vertical-align:middle; font-size:{f_size}; padding:0; color:#222;'>(</td>"
                        f"<td style='vertical-align:middle; padding:0;'>{res}</td>"
                        f"<td style='vertical-align:middle; font-size:{f_size}; padding:0; color:#222;'>)</td>"
                        f"</tr></table>"
                    )
                return res
                
            parts = text.split('/')
            res = tokenize_to_horizontal(parts[0].strip() or "&nbsp;", f_size)
            
            for p in parts[1:]:
                den = tokenize_to_horizontal(p.strip() or "&nbsp;", f_size)
                if has_parens:
                    res = (
                        f"<table style='display:inline-table; vertical-align:middle; border-collapse:collapse; margin: 0 1px;'>"
                        f"<tr>"
                        f"<td rowspan='2' style='vertical-align:middle; font-size:{p_size}; padding: 0; color:#222;'>(</td>"
                        f"<td style='border-bottom:1px solid black; padding: 0 2px; text-align:center; vertical-align:bottom; font-size:{f_size};'>{res}</td>"
                        f"<td rowspan='2' style='vertical-align:middle; font-size:{p_size}; padding: 0; color:#222;'>)</td>"
                        f"</tr>"
                        f"<tr><td style='padding: 0 2px; text-align:center; vertical-align:top; font-size:{f_size};'>{den}</td></tr>"
                        f"</table>"
                    )
                    has_parens = False 
                else:
                    res = (
                        f"<table style='display:inline-table; vertical-align:middle; border-collapse:collapse; margin: 0 1px;'>"
                        f"<tr><td style='border-bottom:1px solid black; padding: 0 2px; text-align:center; vertical-align:bottom; font-size:{f_size};'>{res}</td></tr>"
                        f"<tr><td style='padding: 0 2px; text-align:center; vertical-align:top; font-size:{f_size};'>{den}</td></tr>"
                        f"</table>"
                    )
            return res

        while True:
            match = re.search(r'(\^?)\(([^()]*)\)', html_text)
            if not match: break
            
            is_exp = (match.group(1) == '^')
            inner = match.group(2)
            
            inner = resolve_exponents(inner, is_exp=is_exp) 
            formatted_inner = process_math_block(inner, is_exp=is_exp, has_parens=True)
            
            ph = f"__PAREN{len(parens)}__"
            parens.append(formatted_inner)
            
            if is_exp:
                html_text = html_text[:match.start()] + '^' + ph + html_text[match.end():]
            else:
                html_text = html_text[:match.start()] + ph + html_text[match.end():]
            
        html_text = resolve_exponents(html_text, is_exp=False) 
        html_text = process_math_block(html_text, is_exp=False, has_parens=False)
        
        for _ in range(15): 
            if not re.search(r'__(EXP|PAREN|FUNC|COL|CONST|INDEX)\d+__', html_text): break
            for i in range(len(exps)): html_text = html_text.replace(f"__EXP{i}__", exps[i])
            for i in range(len(parens)): html_text = html_text.replace(f"__PAREN{i}__", parens[i])
            for i in range(len(funcs)): html_text = html_text.replace(f"__FUNC{i}__", funcs[i])
            for i in range(len(consts)): html_text = html_text.replace(f"__CONST{i}__", consts[i])
            for i in range(len(idx_vars)): html_text = html_text.replace(f"__INDEX{i}__", idx_vars[i])
            for i in range(len(cols)):
                span = f"<span style='color: {theme.primary_text}; font-weight: bold;'>{cols[i]}</span>"
                html_text = html_text.replace(f"__COL{i}__", span)
            
        self.preview_label.setText(html_text)

    def get_equation_data(self):
        return self.col_name_edit.text(), self.equation_input.toPlainText()
    
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
