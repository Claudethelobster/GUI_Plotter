# ui/dialogs/help.py
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("How to use BadgerLoop Plotter")
        self.resize(850, 750)

        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml("""
        <h2 style="color: #0055ff;">BadgerLoop Data Plotter – Usage Guide</h2>
        <p>This guide outlines the core features and analytical tools available in the plotter.</p>
        <hr>
        <h3 style="color: #333;">1. Data Protection & Mirror Files</h3>
        <p>To prevent accidental data loss, this software uses a <b>Mirror File System</b>.</p>
        <ul>
            <li>When renaming a column or creating a new calculated column, the program generates a copy of the active file prefixed with <code>MIRROR_</code>.</li>
            <li>All modifications are applied only to this Mirror file. Your original raw data is never altered.</li>
            <li>You can check if you are currently working in a Mirror file by clicking <b>Show Metadata</b>.</li>
        </ul>
        <h3 style="color: #333;">2. Opening & Inspecting Data</h3>
        <ul>
            <li><b>Supported Formats:</b> Open standard CSV files (the program will try to auto-detect the delimiter) or native BadgerLoop log files.</li>
            <li><b>Metadata:</b> Click <i>Show Metadata</i> to view file details, acquisition settings, and notes. For BadgerLoop files, this also displays a list of any instruments that were disabled during the run, including the constant values they were parked at.</li>
            <li><b>Sweep Table:</b> Use the <i>Inspect -> Sweep table</i> menu to view the raw numerical data in a spreadsheet format.</li>
            <li><b>Crosshairs:</b> Go to <i>Inspect -> Toggle crosshairs</i> (or press <b>Ctrl+H</b>) to bring up coordinate tracking. Use the toggle button on the left panel to switch between free-roaming mode and snapping directly to the nearest data point.</li>
        </ul>
        <h3 style="color: #333;">3. Plotting & The Series Manager</h3>
        <p>The <b>Active Plot Series</b> box allows you to plot multiple datasets simultaneously.</p>
        <ul>
            <li><b>Adding Data:</b> Select the X and Y (and Z) columns from the dropdown menus, then click <b>Add Pair</b>.</li>
            <li><b>Editing Data:</b> Click a series in the list to highlight it. Changing the dropdown menus will update that specific series.</li>
            <li><b>Graph Types:</b> Set the plot to Line, Scatter, or <b>FFT (Spectrum)</b>. The FFT mode automatically converts time-domain data into a frequency magnitude spectrum.</li>
            <li><b>Plot Modes:</b> 
                <ul>
                    <li><i>2D Plot:</i> Overlays all active series in the list.</li>
                    <li><i>3D Plot & Heat Map:</i> Displays only the currently highlighted series in the list.</li>
                </ul>
            </li>
        </ul>
        <h3 style="color: #333;">4. Layout, Aspect Ratios & Data Slicing</h3>
        <p>Press <b>Ctrl+L</b> or go to <i>Layout &rarr; Plot Settings & Slicing</i> to adjust the plot visuals.</p>
        <ul>
            <li><b>Aspect Ratios:</b> Lock the plot window to specific dimensions (e.g., 16:9, 4:3, or custom values) to keep exported images consistent.</li>
            <li><b>Logarithmic Scales:</b> Change axes to Log mode and specify the mathematical base (e.g., 10, 2, or <i>e</i>). Both the data and any active fit lines will transform automatically.</li>
            <li><b>Data Slicing:</b> Filter which data is plotted using standard syntax:
                <ul>
                    <li><code>-1</code> &rarr; Plot all</li>
                    <li><code>0,2,4</code> &rarr; Plot specific indices or sweeps</li>
                    <li><code>0:5</code> &rarr; Plot a range from 0 to 4</li>
                </ul>
            </li>
        </ul>
        <h3 style="color: #333;">5. Averaging & Uncertainties</h3>
        <ul>
            <li><b>BadgerLoop Files:</b> Click <i>Toggle Averaging</i> to calculate and plot the mean of all selected sweeps. Click <i>Toggle Error Bars</i> to display standard deviation bounds based on your specified sigma multiplier.</li>
            <li><b>CSV Files:</b> Click <i>Toggle Uncertainties</i> to assign specific columns in your file as X/Y/Z error bounds.</li>
        </ul>
        <h3 style="color: #333;">6. Curve Fitting & Editing</h3>
        <p>Access fitting tools via the <b>Fitting</b> menu.</p>
        <ul>
            <li><b>Common Fits:</b> Generate standard regression lines (Polynomial, Logarithmic, Exponential, Gaussian, Lorentzian).</li>
            <li><b>Custom Fits:</b> Define your own mathematical model using standard operators, math functions (<code>sin()</code>, <code>exp()</code>, <code>ln()</code>), and your <code>x</code> variable.
                <ul>
                    <li>Create parameters (like <code>A</code> or <code>omega</code>) and type starting guesses. The plot will update instantly as you type.</li>
                    <li>Once the preview line roughly matches your data, click <i>Optimize Parameters</i> to run the solver.</li>
                </ul>
            </li>
            <li><b>Editing Fits:</b> If a fit needs adjustment, click <b>Edit Fit</b> on the left panel to reopen the dialog with your equation and parameters intact.</li>
            <li><b>Saving & Loading:</b> Use <b>Save Function</b> to export a fit to a text file. In the Custom Fit dialog, you can click <b>Load Saved Function</b> to import a previous model without retyping it.</li>
        </ul>
        <h3 style="color: #333;">7. Custom Column Generation</h3>
        <p>Navigate to <i>Inspect &rarr; Create Custom Column</i> to mathematically derive new data.</p>
        <ul>
            <li>Use the <b>Generate Time Axis</b> button to automatically calculate a time column based on BadgerLoop settling and sweep delay metadata.</li>
            <li>Use the <b>Physics Constants</b> button to insert predefined constants into your equations. Note that constants are formatted with a backslash (e.g., <code>{\\c}</code> or <code>{\\h}</code>) to separate them from standard variables.</li>
        </ul>
        <h3 style="color: #333;">8. Exporting</h3>
        <ul>
            <li><b>Save Plot:</b> Exports the current visualization as a PNG, JPG, or SVG file.</li>
            <li><b>Export Plotted Data:</b> Exports the calculated arrays for the current plot (including averages, subsets, and transformations). You can overwrite an existing CSV or append the plotted data as new columns.</li>
            <li><b>Function Calculator:</b> Found under <i>Fitting &rarr; Fit Data to Function</i>, this tool loads a saved function file and evaluates it against an entire column of data, allowing you to export the mathematical result.</li>
        </ul>
        <br>
        <p><i>Note: Window size, layout configurations, font sizes, and crosshair preferences are saved automatically when closing the program.</i></p>
        """)

        layout.addWidget(text)

        close_btn = QPushButton("Close Guide")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
