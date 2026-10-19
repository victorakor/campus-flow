import os
import sys
import importlib.util

print("Current directory:", os.getcwd())
print("Python executable:", sys.executable)

print("\nPython import paths:")
for path in sys.path:
    print(" -", path)

print("\nChecking campusflow package:")
spec = importlib.util.find_spec("campusflow")
print("Package found:", spec is not None)

if spec:
    print("Package location:", spec.origin or spec.submodule_search_locations)

print("\nChecking campusflow.lab module:")
try:
    from campusflow.lab import run_lab
    print("SUCCESS: run_lab imported successfully.")
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
