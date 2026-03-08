# ui/dialogs/help.py
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout

class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EggPlot - Help & Instructions")
        self.resize(850, 800)

        layout = QVBoxLayout(self)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        
        html_content = """
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 14px; color: #222; line-height: 1.5; }
            h1 { color: #0055ff; margin-bottom: 5px; }
            h2 { color: #d90000; border-bottom: 1px solid #ccc; padding-bottom: 3px; margin-top: 20px; font-size: 18px;}
            h3 { color: #333; margin-bottom: 2px; }
            ul { margin-top: 5px; }
            li { margin-bottom: 6px; }
            code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 3px; font-family: Consolas, monospace; color: #0055ff; font-weight: bold; }
            .about { background-color: #fff9e6; border-left: 4px solid #ffcc00; padding: 10px; margin-bottom: 20px; font-style: italic; }
            .safety { background-color: #e6f7ff; border-left: 4px solid #0055ff; padding: 10px; margin-top: 20px; }
        </style>
        
        <h1>Welcome to EggPlot</h1>
        
        <div class="about">
            <b>About EggPlot:</b> EggPlot earned its namesake during development when the smart validation engine accidentally loaded a developer's grocery list containing "Eggs" instead of actual experimental data, attempting to plot the eggs against a time axis. Today, it stands as a highly advanced, multi-format analysis tool for physicists!
        </div>

        <div class="safety">
            <b>Data Protection (MIRROR Files)</b><br>
            To prevent accidental data loss, this software uses a <b>Mirror File System</b>. When modifying a file (e.g., renaming columns, applying an iFFT filter, or generating custom math), the program creates a safe copy prefixed with <code>MIRROR_</code> and applies the changes there. Your original raw data is never altered.<br><br>
            <i>Note: If you are working on a Concatenated CSV, the software assumes it is already a derived working file, so it skips the mirror creation and applies the changes directly.</i>
        </div>

        <h2>1. Opening & Inspecting Data</h2>
        <ul>
            <li><b>Open File:</b> Loads a standard CSV (with auto-delimiter detection) or a native BadgerLoop (.blp) file.</li>
            <li><b>Open Folder (Batch CSVs):</b> Loads a directory of CSV files. The Smart Validation Engine will group matching files together and load them sequentially as "Sweeps" of the same experiment.</li>
            <li><b>Concatenate Folder:</b> Stitches a loaded folder of CSVs into a single <code>ConcatenatedCSV</code> file. The software injects inline metadata so it remembers exactly where each sweep begins and ends when reloaded.</li>
            <li><b>Metadata:</b> Click <i>Show Metadata</i> to view file details, folder sizes, and acquisition settings.</li>
            <li><b>Sweep Table:</b> Use the <i>Inspect &rarr; Sweep table</i> menu to view the raw numerical data in a spreadsheet format.</li>
            <li><b>Crosshairs:</b> Go to <i>Inspect &rarr; Toggle crosshairs</i> (or press <b>Ctrl+H</b>) to bring up coordinate tracking. Use the toggle button on the left panel to switch between free-roaming mode and snapping directly to the nearest data point.</li>
        </ul>

        <h2>2. Plotting & The Series Manager</h2>
        <p>Use the <b>Active Plot Series</b> box to plot multiple datasets simultaneously. Select your X, Y, and optional Z columns from the dropdowns, then click <b>Add Pair</b>.</p>
        <ul>
            <li><b>Editing Series:</b> Click a series in the list to highlight it; changing the dropdowns will update that specific series.</li>
            <li><b>Visibility (👁 Icon):</b> Click the eye icon next to a series to temporarily hide it from the plot without deleting it.</li>
            <li><b>Dual Axis (L/R Button):</b> Click the L/R button to assign a series to the Left or Right Y-Axis. This allows for dual X-Y plotting, perfect for comparing datasets with vastly different scales.</li>
            <li><b>Plot Modes:</b> 
                <ul>
                    <li><i>2D Plot:</i> Overlays all active series in the list using standard Lines or Scatters.</li>
                    <li><i>3D Plot:</i> Requires X, Y, and Z columns. Displays the currently highlighted series. Supports 3D Line, 3D Scatter, and <b>Surface</b> plotting (which renders a color-mapped topological 3D grid).</li>
                    <li><i>Heat Map:</i> Requires X, Y, and Z columns. Generates a 2D flat color-mapped grid where color intensity represents the Z value.</li>
                </ul>
            </li>
            <li><b>Data Slicing (Ctrl+L):</b> Filter sweeps or points using standard syntax:
                <ul>
                    <li><code>-1</code> : Plots all available data.</li>
                    <li><code>0,2,4</code> : Plots specific indices or sweeps.</li>
                    <li><code>0:10</code> : Plots a range (e.g., Sweeps 0 through 9).</li>
                    <li><code>0:50:5</code> : Plots sweeps 0 through 50, taking every 5th sweep (e.g., 0, 5, 10, 15...).</li>
                </ul>
            </li>
        </ul>

        <h2>3. Interaction & Point Selection</h2>
        <p>Using the Interaction Mode buttons on the left panel, you can switch from standard Pan/Zoom to <b>Box</b> or <b>Lasso</b> selection.</p>
        <ul>
            <li><b>Region Statistics:</b> Selecting a group of points on the graph will highlight them in yellow and spawn a floating statistics box detailing the selection's Count, Mean, Std Dev, Min/Max, and Integral.</li>
            <li><b>Math Masking:</b> Selections act as a powerful mask. If you have points selected, tools like <i>Signal Processing</i>, <i>Curve Fitting</i>, and the <i>iFFT Surgeon</i> will <b>only</b> apply to those specific highlighted points. Press <code>Escape</code> to clear your selection.</li>
        </ul>

        <h2>4. Data Analysis & Math</h2>
        <ul>
            <li><b>Custom Columns:</b> Navigate to <i>Inspect &rarr; Create Custom Column</i> to mathematically derive new data using standard NumPy equations (e.g., <code>[Voltage] * sin([Angle])</code>). Use the <b>Generate Time Axis</b> button for BadgerLoop data, or insert <b>Physics Constants</b> (formatted like <code>{\\c}</code>).</li>
            <li><b>Signal Processing:</b> Applies mathematical filters (Savitzky-Golay smoothing, moving averages, standard derivatives, cumulative integrals). Check the "Apply only to Selected Points" box to restrict the math to a highlighted region.</li>
            <li><b>Phase Space Generator:</b> Automatically calculates the velocity (dx/dt) of a selected state variable and configures the plot for phase space visualization.</li>
            <li><b>Peak Finder & iFFT Surgeon:</b> Automatically locates signal peaks based on prominence. Click <b>Toggle FFT Mode</b> to view the frequency spectrum. You can highlight specific noise frequencies in the table (or by drawing a box on the graph) and permanently cut them out of your waveform using an Inverse Fast Fourier Transform.</li>
            <li><b>Averaging & Uncertainties:</b> Use the toggle buttons on the left panel to calculate the mean of all selected sweeps, or to assign specific columns as X/Y/Z error bounds.</li>
        </ul>

        <h2>5. Curve Fitting & Exporting</h2>
        <ul>
            <li><b>Fitting:</b> Access fitting tools via the <b>Fitting</b> menu. You can fit common functions (Polynomial, Gaussian, Exponential) or define your own custom equation with starting guesses. The solver will automatically optimize the parameters.</li>
            <li><b>Editing Fits:</b> If a fit needs adjustment, click <b>Edit Fit</b> on the left panel to reopen the dialog with your equation and parameters intact.</li>
            <li><b>Save Plot:</b> Exports the current visualization as a PNG, JPG, or SVG file.</li>
            <li><b>Export Plotted Data:</b> Exports the calculated arrays for the current plot (including averages, subsets, and transformations). You can overwrite an existing CSV or append the plotted data as new columns.</li>
            <li><b>Function Calculator:</b> Found under <i>Fitting &rarr; Fit Data to Function</i>, this tool loads a saved function text file and evaluates it against an entire column of data.</li>
        </ul>
        <br>
        <p><i>Note: Window size, layout configurations, font sizes, and crosshair preferences are saved automatically when closing the program.</i></p>
        """
        
        self.browser.setHtml(html_content)
        layout.addWidget(self.browser)

        close_btn = QPushButton("Close Guide")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
