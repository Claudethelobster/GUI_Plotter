import os
import json
from PyQt5.QtCore import Qt, QSettings
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, 
    QFormLayout, QCheckBox, QLineEdit, QPushButton, QLabel, 
    QSlider, QFileDialog, QMessageBox
)
from core.theme import theme

class PreferencesDialog(QDialog):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.setWindowTitle("EggPlot Preferences")
        self.setMinimumWidth(450)
        self.main_window = main_window
        self.settings = main_window.settings
        
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        self._build_general_tab()
        self._build_ui_tab()
        self._build_advanced_tab()
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("Save & Apply")
        ok_btn.setStyleSheet(f"font-weight: bold; color: {theme.primary_text}; padding: 6px;")
        cancel_btn = QPushButton("Cancel")
        
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        
        btn_box.addStretch()
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)
        
        self.load_current_settings()

    def _build_general_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        
        # Mirror File Settings
        self.mirror_subfolder = QCheckBox("Save Mirrors in /EggPlot_Output/ subfolder")
        form.addRow("File Management:", self.mirror_subfolder)
        
        form.addRow(QLabel("<hr>"))
        
        # Profile Management
        profile_lay = QHBoxLayout()
        btn_export = QPushButton("Export Profile")
        btn_import = QPushButton("Import Profile")
        btn_export.clicked.connect(self.export_profile)
        btn_import.clicked.connect(self.import_profile)
        profile_lay.addWidget(btn_export)
        profile_lay.addWidget(btn_import)
        form.addRow("Settings Profile:", profile_lay)
        
        self.portable_mode = QCheckBox("Portable Mode (Save settings to local .ini file)")
        self.portable_mode.setToolTip("Keeps settings in the app folder instead of the Windows Registry.")
        form.addRow("", self.portable_mode)
        
        form.addRow(QLabel("<hr>"))
        
        # Nuclear Option
        btn_reset = QPushButton("Reset to Factory Defaults")
        btn_reset.setStyleSheet(f"color: {theme.danger_text}; font-weight: bold;")
        btn_reset.clicked.connect(self.factory_reset)
        form.addRow("Memory Wipe:", btn_reset)
        
        self.tabs.addTab(tab, "General & Data")

    def _build_ui_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        
        self.dark_mode = QCheckBox("Enable Dark Mode Theme (Requires Restart)")
        form.addRow("Application Theme:", self.dark_mode)
        
        btn_restore_warnings = QPushButton("Restore all 'Are you sure?' warnings")
        btn_restore_warnings.clicked.connect(self.restore_warnings)
        form.addRow("Safety Nets:", btn_restore_warnings)
        
        self.tabs.addTab(tab, "UI & Experience")

    def _build_advanced_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        
        self.disable_opengl = QCheckBox("Disable Hardware Acceleration (OpenGL)")
        self.disable_opengl.setToolTip("Check this if 3D plots are crashing your graphics driver.")
        form.addRow("Graphics:", self.disable_opengl)
        
        # Polling Rate Slider
        poll_lay = QHBoxLayout()
        self.poll_slider = QSlider(Qt.Horizontal)
        self.poll_slider.setRange(10, 120)
        self.poll_slider.setTickPosition(QSlider.TicksBelow)
        self.poll_slider.setTickInterval(10)
        
        self.poll_lbl = QLabel("60 Hz")
        self.poll_lbl.setFixedWidth(45)
        
        self.poll_slider.valueChanged.connect(lambda v: self.poll_lbl.setText(f"{v} Hz"))
        
        poll_lay.addWidget(self.poll_slider)
        poll_lay.addWidget(self.poll_lbl)
        form.addRow("Crosshair Polling Rate:", poll_lay)
        
        self.tabs.addTab(tab, "Advanced / Performance")

    def load_current_settings(self):
        self.mirror_subfolder.setChecked(self.settings.value("mirror_subfolder", False, bool))
        self.portable_mode.setChecked(self.settings.value("portable_mode", False, bool))
        self.dark_mode.setChecked(self.settings.value("dark_mode", False, bool))
        self.disable_opengl.setChecked(self.settings.value("disable_opengl", False, bool))
        
        poll_rate = int(self.settings.value("crosshair_poll_rate", 60))
        self.poll_slider.setValue(poll_rate)

    def restore_warnings(self):
        self.settings.setValue("suppress_rename_warning", False)
        QMessageBox.information(self, "Restored", "All confirmation dialogs have been restored.")

    def factory_reset(self):
        ans = QMessageBox.warning(
            self, "Factory Reset", 
            "Are you sure you want to completely wipe all EggPlot settings, custom equations, and formatting defaults?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if ans == QMessageBox.Yes:
            self.settings.clear()
            QMessageBox.information(self, "Reset Complete", "Settings wiped. Please restart EggPlot.")
            self.accept()

    def export_profile(self):
        fname, _ = QFileDialog.getSaveFileName(self, "Export Profile", "EggPlot_Profile.json", "JSON Files (*.json)")
        if not fname: return
        
        # Dump all QSettings to a dictionary
        data = {key: self.settings.value(key) for key in self.settings.allKeys()}
        try:
            with open(fname, 'w') as f:
                json.dump(data, f, indent=4)
            QMessageBox.information(self, "Success", "Profile exported successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export profile:\n{e}")

    def import_profile(self):
        fname, _ = QFileDialog.getOpenFileName(self, "Import Profile", "", "JSON Files (*.json)")
        if not fname: return
        
        try:
            with open(fname, 'r') as f:
                data = json.load(f)
            for key, val in data.items():
                self.settings.setValue(key, val)
            self.load_current_settings()
            QMessageBox.information(self, "Success", "Profile imported! Some changes may require a restart.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import profile:\n{e}")

    def get_results(self):
        return {
            "mirror_subfolder": self.mirror_subfolder.isChecked(),
            "portable_mode": self.portable_mode.isChecked(),
            "dark_mode": self.dark_mode.isChecked(),
            "disable_opengl": self.disable_opengl.isChecked(),
            "crosshair_poll_rate": self.poll_slider.value()
        }
