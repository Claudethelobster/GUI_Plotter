# core/constants.py

PHYSICS_CONSTANTS = {
    "c": {"name": "Speed of light in vacuum", "value": 299792458.0, "units": "m/s", "html": "c"},
    "h": {"name": "Planck constant", "value": 6.62607015e-34, "units": "J·s", "html": "h"},
    "hbar": {"name": "Reduced Planck constant", "value": 1.054571817e-34, "units": "J·s", "html": "&#8463;"},
    "G": {"name": "Newtonian constant of gravitation", "value": 6.67430e-11, "units": "m^3/kg·s^2", "html": "G"},
    "N_A": {"name": "Avogadro constant", "value": 6.02214076e23, "units": "mol^-1", "html": "N<sub>A</sub>"},
    "k_B": {"name": "Boltzmann constant", "value": 1.380649e-23, "units": "J/K", "html": "k<sub>B</sub>"},
    "q_e": {"name": "Elementary charge", "value": 1.602176634e-19, "units": "C", "html": "e"},
    "m_e": {"name": "Electron mass", "value": 9.1093837015e-31, "units": "kg", "html": "m<sub>e</sub>"},
    "m_p": {"name": "Proton mass", "value": 1.67262192369e-27, "units": "kg", "html": "m<sub>p</sub>"},
    "m_n": {"name": "Neutron mass", "value": 1.67492749804e-27, "units": "kg", "html": "m<sub>n</sub>"},
    "mu_0": {"name": "Vacuum magnetic permeability", "value": 1.25663706212e-6, "units": "N/A^2", "html": "&mu;<sub>0</sub>"},
    "eps_0": {"name": "Vacuum electric permittivity", "value": 8.8541878128e-12, "units": "F/m", "html": "&epsilon;<sub>0</sub>"},
    "R": {"name": "Molar gas constant", "value": 8.314462618, "units": "J/mol·K", "html": "R"},
    "F": {"name": "Faraday constant", "value": 96485.33212, "units": "C/mol", "html": "F"},
    "sigma_sb": {"name": "Stefan-Boltzmann constant", "value": 5.670374419e-8, "units": "W/m^2·K^4", "html": "&sigma;"},
    "R_inf": {"name": "Rydberg constant", "value": 10973731.568160, "units": "m^-1", "html": "R<sub>&infin;</sub>"},
    "a_0": {"name": "Bohr radius", "value": 5.29177210903e-11, "units": "m", "html": "a<sub>0</sub>"},
    "mu_B": {"name": "Bohr magneton", "value": 9.2740100783e-24, "units": "J/T", "html": "&mu;<sub>B</sub>"},
    "mu_N": {"name": "Nuclear magneton", "value": 5.0507837461e-27, "units": "J/T", "html": "&mu;<sub>N</sub>"},
    "g": {"name": "Standard gravity", "value": 9.80665, "units": "m/s^2", "html": "g"},
    "atm": {"name": "Standard atmosphere", "value": 101325.0, "units": "Pa", "html": "atm"},
    "eV": {"name": "Electron volt (in Joules)", "value": 1.602176634e-19, "units": "J", "html": "e<sub>V</sub>"},
    "u": {"name": "Atomic mass unit", "value": 1.66053906660e-27, "units": "kg", "html": "u"}
}

GREEK_MAP = {
    'alpha': 'α', 'Alpha': 'Α', 'beta': 'β', 'Beta': 'Β', 'gamma': 'γ', 'Gamma': 'Γ',
    'delta': 'δ', 'Delta': 'Δ', 'epsilon': 'ε', 'Epsilon': 'Ε', 'zeta': 'ζ', 'Zeta': 'Ζ',
    'eta': 'η', 'Eta': 'Η', 'theta': 'θ', 'Theta': 'Θ', 'iota': 'ι', 'Iota': 'Ι',
    'kappa': 'κ', 'Kappa': 'Κ', 'lambda': 'λ', 'Lambda': 'Λ', 'mu': 'μ', 'Mu': 'Μ',
    'nu': 'ν', 'Nu': 'Ν', 'xi': 'ξ', 'Xi': 'Ξ', 'omicron': 'ο', 'Omicron': 'Ο',
    'pi': 'π', 'Pi': 'Π', 'rho': 'ρ', 'Rho': 'Ρ', 'sigma': 'σ', 'Sigma': 'Σ',
    'tau': 'τ', 'Tau': 'Τ', 'upsilon': 'υ', 'Upsilon': 'Υ', 'phi': 'φ', 'Phi': 'Φ',
    'chi': 'χ', 'Chi': 'Χ', 'psi': 'ψ', 'Psi': 'Ψ', 'omega': 'ω', 'Omega': 'Ω'
}
