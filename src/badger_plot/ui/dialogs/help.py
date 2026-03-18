from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton

from core.theme import theme

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EggPlot - Help & Instructions")
        self.resize(850, 800)
        
        # Apply the base dialog theme
        self.setStyleSheet(f"background-color: {theme.bg}; color: {theme.fg};")

        layout = QVBoxLayout(self)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(f"background-color: {theme.panel_bg}; border: 1px solid {theme.border};")
        
        # We use an f-string to inject the dynamic theme colors into the HTML CSS
        # Notice that standard CSS curly braces are doubled ({{ and }})
        html_content = f"""
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 14px; color: {theme.fg}; line-height: 1.5; }}
            h1 {{ color: {theme.primary_text}; margin-bottom: 5px; }}
            h2 {{ color: {theme.danger_text}; border-bottom: 1px solid {theme.border}; padding-bottom: 3px; margin-top: 20px; font-size: 18px;}}
            h3 {{ color: {theme.fg}; margin-bottom: 2px; }}
            ul {{ margin-top: 5px; }}
            li {{ margin-bottom: 6px; }}
            code {{ background-color: {theme.bg}; padding: 2px 4px; border-radius: 3px; font-family: Consolas, monospace; color: {theme.primary_text}; font-weight: bold; border: 1px solid {theme.border}; }}
            .about {{ background-color: {theme.warning_bg}; border-left: 4px solid {theme.warning_border}; padding: 10px; margin-bottom: 20px; font-style: italic; color: {theme.fg}; }}
            .safety {{ background-color: {theme.primary_bg}; border-left: 4px solid {theme.primary_border}; padding: 10px; margin-top: 20px; color: {theme.fg}; }}
        </style>
        
        <h1>Welcome to EggPlot</h1>
        
        <div class="about">
            <b>About EggPlot:</b> EggPlot earned its namesake during development when the smart validation engine accidentally loaded a developer's grocery list containing "Eggs" instead of actual experimental data, attempting to plot the eggs against a time axis. Today, it stands as a highly advanced, multi-format analysis tool for physicists!
        </div>

        <div class="safety">
            <b>Data Protection (MIRROR Files)</b><br>
            To prevent accidental data loss, this software uses a <b>Mirror File System</b>. When modifying a file (e.g., renaming columns, slicing data, applying an iFFT filter, or generating custom math), the program creates a safe copy prefixed with <code>MIRROR_</code> and applies the changes there. Your original raw data is never altered.<br><br>
            <i>Note: If you are working on a Concatenated CSV, the software assumes it is already a derived working file, so it skips the mirror creation and applies the changes directly.</i>
        </div>

        <h2>1. Opening & Inspecting Data</h2>
        <ul>
            <li><b>Open File:</b> Loads a standard CSV (with auto-delimiter detection), an HDF5 binary (.h5), or a native BadgerLoop (.blp) file.</li>
            <li><b>Open Folder (Batch CSVs):</b> Loads a directory of CSV files. The Smart Validation Engine will group matching files together and load them sequentially as "Sweeps" of the same experiment.</li>
            <li><b>Concatenate Folder:</b> Stitches a loaded folder of CSVs into a single <code>ConcatenatedCSV</code> file. The software injects inline metadata so it remembers exactly where each sweep begins and ends when reloaded.</li>
            <li><b>Metadata:</b> Click <i>Show Metadata</i> to view file details, folder sizes, and acquisition settings.</li>
            <li><b>Sweep Table:</b> Use the <i>Inspect &rarr; Sweep table</i> menu to view the raw numerical data in a spreadsheet format.</li>
            <li><b>Crosshairs (Ctrl+H):</b> Go to <i>Inspect &rarr; Toggle crosshairs</i> to bring up coordinate tracking. Use the toggle button on the left panel to switch between free-roaming mode and snapping directly to the nearest data point.</li>
        </ul>

        <h2>2. Plotting & The Series Manager</h2>
        <p>Use the <b>Active Plot Series</b> box to plot multiple datasets simultaneously. Select your X, Y, and optional Z columns from the dropdowns, then click <b>Add Pair</b>.</p>
        <ul>
            <li><b>Editing Series:</b> Click a series in the list to highlight it; changing the dropdowns will update that specific series.</li>
            <li><b>Visibility (👁 Icon):</b> Click the eye icon next to a series to temporarily hide it from the plot without deleting it.</li>
            <li><b>Per-Trace Customization (⚙️ Icon):</b> Click the gear icon to customize the exact line style (solid, dashed, dotted), thickness, color, and scatter symbol for that specific trace. This overrides the global defaults.</li>
            <li><b>Dual Axis (L/R Button):</b> Click the L/R button to assign a series to the Left or Right Y-Axis. This allows for dual X-Y plotting, perfect for comparing datasets with vastly different scales.</li>
            <li><b>Plot Modes:</b> 
                <ul>
                    <li><i>2D Plot:</i> Overlays all active series in the list using standard Lines or Scatters.</li>
                    <li><i>3D Plot:</i> Requires X, Y, and Z columns. Displays the currently highlighted series. Supports 3D Line, 3D Scatter, and <b>Surface</b> plotting (which renders a color-mapped topological 3D grid).</li>
                    <li><i>Heat Map:</i> Requires X, Y, and Z columns. Generates a 2D flat color-mapped grid where color intensity represents the Z value.</li>
                    <li><i>Histogram:</i> Bins your Y-column data to show its statistical distribution. Click <b>Toggle Histogram Stats</b> to view a HUD containing the Count, Mean, Median, Mode, Std Dev, Skewness, and Kurtosis.</li>
                </ul>
            </li>
            <li><b>Layout & Slicing (Ctrl+L):</b> Filter sweeps or points using standard syntax (e.g., <code>0:10</code> or <code>0,2,4</code>). This menu also controls global trace defaults, grid lines, background colors, and <b>Legend Cosmetics</b> (which update live as you drag the opacity/column sliders).</li>
        </ul>

        <h2>3. Interaction & Point Selection</h2>
        <p>Using the Interaction Mode buttons on the left panel, you can switch from standard Pan/Zoom to <b>Box</b> or <b>Lasso</b> selection.</p>
        <ul>
            <li><b>Region Statistics:</b> Selecting a group of points on the graph will highlight them in yellow and spawn a floating statistics box detailing the selection's Count, Mean, Std Dev, Min/Max, and Integral.</li>
            <li><b>Math Masking:</b> Selections act as a powerful mask. If you have points selected, tools like <i>Signal Processing</i>, <i>Curve Fitting</i>, and the <i>iFFT Surgeon</i> will <b>only</b> apply to those specific highlighted points. Press <code>Escape</code> to clear your selection.</li>
        </ul>

        <h2>4. Data Analysis & Math</h2>
        <ul>
            <li><b>Custom Columns:</b> Navigate to <i>Inspect &rarr; Create Custom Column</i> to mathematically derive new data using standard NumPy equations (e.g., <code>[Voltage] * sin([Angle])</code>). Use the <b>Generate Time Axis</b> button for BadgerLoop data, or insert <b>Physics Constants</b>.</li>
            <li><b>Data Slicer (Non-Monotonic Split):</b> Easily isolate specific slopes of a non-monotonic calibration curve. Place your crosshair at the inflection point, click "Grab from Crosshair", and the tool will split the data into two isolated columns (Above/Below the threshold) padded with NaNs to ensure clean curve fitting.</li>
            <li><b>Area Calculators:</b> Found under the Analysis menu.
                <ul>
                    <li><i>Area Under Curve:</i> Calculate definite integrals using Box/Lasso selections or custom bendable lines. Supports multiple baseline methods (y=0, Min-Y, or Local Slant).</li>
                    <li><i>Enclosed Loop Area:</i> Calculates the area inside parametric loops (like Hysteresis or P-V diagrams) using the exact Shoelace formula. Supports auto-detection of multiple intersecting lobes.</li>
                </ul>
            </li>
            <li><b>Signal Processing:</b> Applies mathematical filters (Savitzky-Golay smoothing, moving averages, standard derivatives, cumulative integrals).</li>
            <li><b>Phase Space Generator:</b> Automatically calculates the velocity (dx/dt) of a selected state variable and configures the plot for phase space visualization.</li>
            <li><b>Fourier Analysis:</b>
                <ul>
                    <li><i>Spectrogram (STFT):</i> Generates a Time-Frequency heatmap of your signal to visualize how frequency components shift over time.</li>
                    <li><i>Peak Finder & iFFT Surgeon:</i> Automatically locates signal peaks. Click <b>Toggle FFT Mode</b> to view the frequency spectrum. You can highlight specific noise frequencies in the table (or by drawing a box on the graph) and permanently cut them out of your waveform using an Inverse Fast Fourier Transform.</li>
                </ul>
            </li>
            <li><b>Averaging & Uncertainties:</b> Use the toggle buttons on the left panel to calculate the mean of all selected sweeps, or to assign specific columns as X/Y/Z error bounds.</li>
        </ul>

        <h2>5. Curve Fitting & Exporting</h2>
        <ul>
            <li><b>Fitting:</b> Access fitting tools via the <b>Fitting</b> menu. You can fit common functions (Polynomial, Gaussian, Exponential, Lorentzian, Logarithmic) or define your own custom equation with starting guesses.</li>
            <li><b>Editing Fits:</b> If a fit needs adjustment, click <b>Edit Fit</b> on the left panel to reopen the dialog with your equation and parameters intact.</li>
            <li><b>Export Fit to Column:</b> Instantly turns your mathematical fit into hard data! Generates a perfectly spaced, high-resolution X-array spanning your data's min/max bounds, evaluates the Y-values, and appends both as new columns to your dataset.</li>
            <li><b>Save Plot:</b> Exports the current visualization as a PNG, JPG, or SVG file.</li>
            <li><b>Export Plotted Data:</b> Exports the calculated arrays for the current plot (including averages, subsets, and transformations). You can overwrite an existing CSV or append the plotted data as new columns.</li>
        </ul>
        <br>
        <p><i>Note: Window size, layout configurations, font sizes, and crosshair preferences are saved automatically when closing the program.</i></p>
        """
        
        self.browser.setHtml(html_content)
        layout.addWidget(self.browser)

        close_btn = QPushButton("Close Guide")
        close_btn.setFixedWidth(100)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {theme.panel_bg}; border: 1px solid {theme.border}; border-radius: 4px; padding: 6px; color: {theme.fg}; font-weight: bold; }}
            QPushButton:hover {{ background-color: {theme.bg}; }}
        """)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
