# utils/function_io.py
import re
import numpy as np
from core.constants import PHYSICS_CONSTANTS

def load_function_from_file(fname):
    with open(fname, "r") as f:
        lines = [l.strip() for l in f if l.strip()]

    ftype = lines[0].lower()

    if ftype == "polynomial":
        degree = int(lines[1].split(":")[1])
        coeffs = [float(c) for c in lines[2:]]
        poly = np.poly1d(coeffs)
        return lambda x: poly(x)

    if ftype == "logarithmic":
        base_str = lines[1].split(":")[1]
        base = np.e if base_str == "e" else float(base_str)
        a, c = map(float, lines[2:])
        return lambda x: a * np.log(x) / np.log(base) + c

    if ftype == "exponential":
        a, b, c = map(float, lines[1:])
        return lambda x: a * np.exp(b * x) + c

    if ftype == "gaussian":
        A, mu, sigma = map(float, lines[1:])
        return lambda x: A * np.exp(-(x - mu)**2 / (2 * sigma**2))

    if ftype == "lorentzian":
        A, x0, gamma = map(float, lines[1:])
        return lambda x: A / (1 + ((x - x0) / gamma)**2)

    # --- GLOBAL CUSTOM FUNCTION PARSER ---
    if ftype == "custom":
        raw_eq = lines[1]
        param_names = [p.strip() for p in lines[2].split(",") if p.strip()]
        param_vals = [float(v) for v in lines[3:]]
        
        py_equation = raw_eq
        # Replace parameters with their hardcoded values
        for p, v in zip(param_names, param_vals):
            py_equation = re.sub(r'\{' + p + r'\}', f"({v})", py_equation)
            
        # Replace physics constants
        def replace_const_silent(match):
            c_key = match.group(1)
            if c_key in PHYSICS_CONSTANTS: return str(PHYSICS_CONSTANTS[c_key]['value'])
            return match.group(0)
        py_equation = re.sub(r'\{\\(.*?)\}', replace_const_silent, py_equation)
        
        py_equation = py_equation.replace('^', '**')
        math_funcs = ['arcsinh','arccosh','arctanh','arcsin','arccos','arctan','sinh','cosh','tanh','sin','cos','tan']
        for fn in math_funcs:
            py_equation = re.sub(r'\b' + fn + r'\s*\(', 'np.'+fn+'(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?10\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog_?2\s*\(', 'np.log2(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\blog\s*\(', 'np.log10(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bln\s*\(', 'np.log(', py_equation, flags=re.IGNORECASE)
        py_equation = re.sub(r'\bexp\s*\(', 'np.exp(', py_equation, flags=re.IGNORECASE)
        
        def model(x):
            env = {"np": np, "e": np.e, "pi": np.pi, "x": x}
            try:
                res = eval(py_equation, {"__builtins__": {}}, env)
                if np.isscalar(res): return np.full_like(x, float(res))
                return np.asarray(res, dtype=np.float64)
            except Exception as e:
                raise ValueError(f"Cannot evaluate this custom function in the Calculator.\n(It likely contains specific [Column Data] which is only available in the main plot window)\nError: {e}")
        return model

    raise ValueError(f"Unknown function type: {ftype}")
