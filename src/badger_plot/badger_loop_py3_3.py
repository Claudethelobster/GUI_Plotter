"""
    Utilities for loading and plotting data saved by BadgerLoop
    
    v0.1 Jonathan Prance, Aug 2014
    v0.2 JRP, Sep 2014. Bug fixes, including...
        Fixed: checking of sweep/column/point indices should _not_ resort indices
    v0.3 Matt Taylor, fixed the read_instrument staticmethod to work with the GUI plotter when altering mirror badgerloop files.
        
    27/08/2015: added parsing of alternative date format (used in newer UW data)
    07/06/2016: waveform loading implemented
    10/10/2018: allow incomplete final sweeps to be used by 'slice' if they contain sufficient points
    25/10/2018: added wrapper for 'range' (for future python3 compatibility)
"""

import datetime
import re
import string
import os
import struct
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib import ticker
from scipy import optimize

def BLrange(a, b):
    return [i for i in range(a, b)]

"""
    Plot a graph of the given sweeps and points from a dataset
"""
def plot_dataset_2D(data, xcol, ycol, sweeps=-1, points=-1, size=10, show=True):
    print('plot_dataset_2D:')
    print(' X: ' + data.column_names[xcol])
    print(' Y: ' + data.column_names[ycol])
    
    fig, ax = plt.subplots(figsize=(size,0.7*size))
    
    if not type(sweeps) == list:    # If only one sweep was passed, make sure 'sweeps' is still iterable
            sweeps = [sweeps]

    if sweeps[0] == -1:             # Select all sweeps by default
        sweeps = BLrange(0, data.num_sweeps)
    else:                           # Otherwise, make sure the given list of sweeps fits in the dataset
        sweeps = [s for s in sweeps if s in BLrange(0, data.num_sweeps)]
    
    for sw in sweeps:
        xs, ys = data.slice(sweeps=sw, points=points, cols=[xcol, ycol])
        ax.plot(xs, ys, label='sweep {}'.format(sw))

    ax.grid(True)
    ax.set_title('[' + data.date.strftime('%Y%m%d') + '/' + data.name + ']')
    ax.set_xlabel(data.column_names[xcol])
    ax.set_ylabel(data.column_names[ycol])
    ax.ticklabel_format(style='sci', axis='x', scilimits=(-2,2))
    ax.ticklabel_format(style='sci', axis='y', scilimits=(-2,2))
    plt.tight_layout()
    lgd = ax.legend(bbox_to_anchor=(1,1), loc=2)
    fig.subplots_adjust(right=1-(2.0/size))
    plt.draw()
    if show: plt.show()
    return fig
    
"""
    Plot a colormap of the given sweeps from a dataset
"""
def plot_dataset_3D(data, xcol, ycol, zcol, sweeps=-1, points=-1, size=10, show=True):
    print('plot_dataset_3D:')
    print(' X: ' + data.column_names[xcol])
    print(' Y: ' + data.column_names[ycol])
    print(' Z: ' + data.column_names[zcol])
    
    xs, ys, zs = data.slice(sweeps=sweeps, points=points, cols=[xcol, ycol, zcol])
    
    if not type(size) == tuple:
        w, h = np.shape(zs)
        size = size, min(size,size*h/w)
    
    fig, ax = plt.subplots(figsize=size)
    cax = ax.pcolormesh(xs, ys, zs, cmap=cm.jet)
    ax.axis([xs.min(), xs.max(), ys.min(), ys.max()])
    
    ax.set_title('[' + data.date.strftime('%Y%m%d') + '/' + data.name + ']\n')
    ax.set_xlabel(data.column_names[xcol])
    ax.set_ylabel(data.column_names[ycol])
    ax.ticklabel_format(style='sci', axis='x', scilimits=(-2,2))
    ax.ticklabel_format(style='sci', axis='y', scilimits=(-2,2))
    
    cbar = fig.colorbar(cax)
    ticks = ticker.ScalarFormatter()
    ticks.set_scientific(True)
    ticks.set_powerlimits((-2,2))
    cbar.formatter = ticks
    cbar.update_ticks()
    
    cbar.set_label(data.column_names[zcol])
    
    plt.tight_layout()
    plt.draw()
    if show: plt.show()
    return fig
    
    
"""
    Generic wrapper for 2D and 3D plot functions
""" 
def plot_dataset(data, xcol, ycol, zcol=-1, sweeps=-1, points=-1, scaling=-1, size=10, show=True):
    if zcol == -1:
        return plot_dataset_2D(data, xcol, ycol, sweeps=sweeps, points=points, size=size, show=show)
    else:
        return plot_dataset_3D(data, xcol, ycol, zcol, sweeps=sweeps, points=points, size=size, show=show)

"""
    Container class for a BadgerLoop data files.
    Constructor takes the full path to the data file and loads the file into memory.
"""
class Dataset:
    def __init__(self, fname):
        self.load_data(fname)
        
    """
        Return an arbitrary sub-section of the data, as specified by a BLrange of sweeps and
        points and a list of columns.
        Returns data as a list of arrays, one for each data column requested.
    """
    def slice(self, sweeps=-1, points=-1, cols=-1):
        if not type(cols) == list:
            if cols == -1: return []    # No need to continue if no columns were requested
            cols = [cols]               # If only one column was passed, make sure 'cols' is still iterable
            
        # Make sure the given list of columns fits with the available columns
        cols = [c for c in cols if c in BLrange(0, self.num_inputs+self.num_outputs)]
        
        if not type(sweeps) == list:    # If only one sweep was passed, make sure 'sweeps' is still iterable
            sweeps = [sweeps]

        if sweeps[0] == -1:             # Select all sweeps by default
            sweeps = BLrange(0, self.num_sweeps)
        else:                           # Otherwise, make sure the given list of sweeps fits in the dataset
            sweeps = [s for s in sweeps if s in BLrange(0, self.num_sweeps)]
        
        if not type(points) == list:    # If only one point was passed, make sure 'points' is still iterable
            points = [points]
        
        if points[0] == -1:             # Select all points by default
            points = BLrange(0, self.sweeps[sweeps[0]].num_points)
        else:                           # Otherwise, make sure the given list of points fits in the dataset
            points = [p for p in points if p in BLrange(0, self.sweeps[sweeps[0]].num_points)]
        
        # Up until this point we have assumed that all sweeps are the same length. This should be enforced
        # by BadgerLoop, except for a final sweep that is terminated early. Therefore, we remove any sweeps
        # that do not contain the points we have selected by this point.        
        sweeps = [s for s in sweeps if points == [p for p in points if p in BLrange(0, self.sweeps[s].num_points)]]        
        
        # Create and fill arrays
        ret = [np.zeros((len(sweeps), len(points))) for c in cols]
        for isw, sw in enumerate(sweeps):
            for ic, col in enumerate(cols):
                ret[ic][isw,:] = self.sweeps[sw].data[points,col]
        
        # All 1D vectors are returned as shape=(N,) arrays, so
        # if any arrays are Nx1 vectors, reshape them, and if
        # ny arrays are 1xN vectors, transpose them and reshape them
        for ic in BLrange(0, len(cols)):
            w, h = np.shape(ret[ic])
            if w == 1 and h != 1:
                ret[ic] = ret[ic].transpose().reshape((h,))
            elif h == 1 and w != 1:
                ret[ic] = ret[ic].reshape((w,))
        
        # If we are only returning one array, do not return it inside a list
        if len(ret) == 1:
            return ret[0]
        else:
            return ret
    
    """
        Load data from a BadgerLoop file
    """
    def load_data(self, fname):
        self.filename = fname
    
        print('Loading ' + self.filename + '...')
        f = open(self.filename, 'r')
        
        # HEADER
        s = f.readline()
        try:
            self.date = datetime.datetime.strptime(s, '%d/%m/%Y %H:%M\n')
        except ValueError:
            try:
                self.date = datetime.datetime.strptime(s, '%m/%d/%Y %H:%M %p\n')
            except:
                print('Could not interpret date string: \"' + s.rstrip() + '\"')
        
        # DATA SET
        while not f.readline().startswith('###DATA SET'): pass  # Scan ahead to 'DATA SET' section
        self.name = re.findall(r'Name: (.*)$', f.readline())[0].strip()
        s = f.readline()
        self.settling_time = int(re.findall(r'SettlingTime: ([0-9]*)', s)[0])
        self.sweep_delay = int(re.findall(r'SweepDelay: ([0-9]*)', s)[0])
        
        # NOTES
        while not f.readline().startswith('###NOTES'): pass  # Scan ahead to 'NOTES' section
        self.notes = ''
        while True:
            s = f.readline()
            if s.startswith('###DISABLED OUTPUTS'):     # 'NOTES' when 'DISABLED OUTPUTS' starts
                break
            else:
                self.notes = self.notes + s
        self.notes = self.notes.rstrip()
        
        # DISABLED OUTPUTS
        self.num_disabled_outputs = 0
        self.disabled_outputs = []
        while True:
            inst = Dataset.read_instrument(f, read_last_value=True)
            if inst:
                self.disabled_outputs.append(inst)
                self.num_disabled_outputs += 1
            else:
                break
            
        # DISABLED INPUTS
        while not f.readline().startswith('###DISABLED INPUTS'): pass
        self.num_disabled_inputs = 0
        self.disabled_inputs = []
        while True:
            inst = Dataset.read_instrument(f, read_last_value=True)
            if inst:
                self.disabled_inputs.append(inst)
                self.num_disabled_inputs += 1
            else:
                break
        
        # OUTPUTS
        while not f.readline().startswith('###OUTPUTS'): pass
        self.num_outputs = 0
        self.outputs = []
        self.column_names = {}
        num_columns = 0
        while True:
            inst = Dataset.read_instrument(f, read_last_value=False)
            if inst:
                self.outputs.append(inst)
                self.column_names[num_columns] = inst['name']
                self.num_outputs += 1
                num_columns = num_columns + 1
            else:
                break
        
        # INPUTS
        while not f.readline().startswith('###INPUTS'): pass
        self.num_inputs = 0
        self.inputs = []
        while True:
            inst = Dataset.read_instrument(f, read_last_value=False)
            if inst:
                self.inputs.append(inst)
                self.column_names[num_columns] = inst['name']
                self.num_inputs += 1
                num_columns = num_columns + 1
            else:
                break
                
        # DATA
        while not f.readline().startswith('###DATA'): pass
        self.num_sweeps = int(re.findall(r'TotalSweeps: ([0-9]*)', f.readline())[0])
        self.sweeps = []
        for i in BLrange(0, self.num_sweeps):
            s = f.readline()
            while not s.startswith('###START SWEEP'):
                s = f.readline()
            num_points = int(re.findall(r'TotalPoints: ([0-9]*)', f.readline())[0])
            self.sweeps.append(Sweep(self.num_outputs+self.num_inputs, num_points))
            
            for p in BLrange(0, self.sweeps[i].num_points):
                self.sweeps[i].data[p,:] = [float(v) for v in f.readline().split('\t')]
                
        f.close()

        # Load binary waveform data

        self.waveforms = []
        self.waveform_names = []
        self.num_waveforms = 0
        datadir = os.path.split(fname)[0]       # Get the path of the main BL data file

        for file in os.listdir(datadir):        # Search for waveform 'info' files
            if file.endswith('_info.txt'):
                # If a file looks like a waveform datafile then open it and see if it makes sense
                info_header = False
                with open(os.path.join(datadir, file), 'r') as f:
                    while True:
                        l = f.readline()
                        if l.startswith('BadgerLoop'): # Header tag found
                            info_header = True
                            break
                        if not l: break # End of file

                    if info_header:
                        instrument_name = re.findall(r'Instrument: (.*)$', f.readline())[0].strip()                
                        num_waveform_channels = int(re.findall(r'NumWaveformChannels: ([0-9]*)', f.readline())[0])
                        num_points_per_waveform = int(re.findall(r'NumPointsPerWaveform: ([0-9]*)', f.readline())[0])
                        num_data_sets = int(re.findall(r'NumDataSets: ([0-9]*)', f.readline())[0])

                # If waveform information was found then load the associated binary waveform data
                if info_header:
                    waveform_file = os.path.join(datadir, '{}.dat'.format(instrument_name))
                    print('Loading ' + waveform_file + '... (binary waveforms)')
                    raw_data = np.zeros(num_data_sets*num_waveform_channels*num_points_per_waveform)

                    with open(waveform_file, 'rb') as f:
                        for i in BLrange(0, len(raw_data)):
                            d = f.read(8)
                            if not d:
                                break
                            else:
                                raw_data[i] = struct.unpack('d', d)[0]
                                
                    # Parse waveform data into correct shape and save
                    self.waveform_names.append(instrument_name)
                    self.waveforms.append([])

                    for n in BLrange(0, num_data_sets):
                        waveform_data = Waveform(instrument_name, num_waveform_channels, num_points_per_waveform, raw_data, n)
                        self.waveforms[self.num_waveforms].append(waveform_data)

                    self.num_waveforms += 1

    """
        Parse information about an instrument from the datafile (Upgraded for Fault-Tolerance)
    """
    @staticmethod
    def read_instrument(f, read_last_value=False):
        # Save the current position in the file so we can rewind if we hit a boundary
        last_pos = f.tell()
        s = f.readline()
        
        # 1. SMART BOUNDARY DETECTION: Stop if we hit a blank line OR a new section header
        if not s.strip() or s.startswith('###'):      
            if s.startswith('###'):
                # We accidentally read the next section header! Rewind the file 
                # so the main parser loop doesn't miss it.
                f.seek(last_pos) 
            return False
            
        inst = {}
        fields = re.split(r'\t', s.rstrip('\r\n'))
        
        # 2. INDEX CRASH PROTECTION: Safely handle missing tabs
        inst['name'] = fields[0]
        if len(fields) > 1:
            inst['type'] = fields[1]
            inst['settings'] = fields[2:]
        else:
            inst['type'] = "BadgerLoop.Unknown"
            inst['settings'] = []
            
        # 3. SAFE LAST VALUE READING
        if read_last_value:
            last_pos_val = f.tell()
            s = f.readline()
            if s.startswith('LastValue:'):
                try:
                    val = re.findall(r'LastValue: (.*) (.*)', s)[0]
                    inst['last_value'] = float(val[0])
                    inst['units'] = val[1].rstrip()
                except Exception:
                    inst['last_value'] = 0.0
                    inst['units'] = ""
            else:
                # If there was no LastValue line, rewind so we don't accidentally skip the next instrument
                f.seek(last_pos_val)
            
        return inst

"""
    Container class for a single data sweep
"""

class Sweep:
    def __init__(self, num_cols, num_points):
        self.num_cols = num_cols
        self.num_points = num_points
        self.data = np.zeros((num_points, num_cols))

"""
    Container class for waveform data. Contains all of the waveforms from a single instrument
"""

class Waveform:
    def __init__(self, instrument_name, num_channels, num_points, raw_data, n):
        self.instrument_name = instrument_name
        self.num_channels = num_channels
        self.num_points = num_points
        self.waveform = np.zeros((num_points, num_channels))
        
        #print instrument_name
        #print num_channels
        #print num_points
        #print np.shape(self.waveform)
        #print np.shape(raw_data)

        for c in BLrange(0,num_channels):
            p1 = (n*num_points*num_channels)+c
            p2 = ((n+1)*num_points*num_channels)+c
            #print '{} {} {} {}'.format(c, p1, p2, n)
            self.waveform[:,c] = raw_data[BLrange(p1, p2, num_channels)]
            #print ' done'




