import os
import shutil
import dlt

# 1. Get the path from dlt's actual config
try:
    # This identifies where dlt is currently looking for data
    storage_path = dlt.config.get("runtime.storage_path")
    if storage_path and os.path.exists(storage_path):
        print(f"Cleaning DLT storage at: {storage_path}")
        shutil.rmtree(storage_path)
except:
    print("Could not resolve storage_path automatically.")

# 2. Manually kill the 3 most common 'Ghost' locations in Codespaces
paths_to_wipe = [
    os.path.expanduser("~/.dlt/pipelines"),
    os.path.expanduser("~/.dlt/schemas"),
    "/tmp/dlt",
    "./.dlt/pipelines"
]

for path in paths_to_wipe:
    if os.path.exists(path):
        print(f"Wiping ghost data at: {path}")
        shutil.rmtree(path)
    else:
        print(f"Path not found (already clean): {path}")

print("\nDone! Your DLT environment is now a blank slate.")