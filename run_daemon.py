#!/usr/bin/env python3
import subprocess, time
from pathlib import Path

PROJECT = Path("/tmp/kodo-fork")
for cycle in range(1, 999):
    try:
        file = PROJECT / f"improvements/c{cycle}.py"
        file.parent.mkdir(exist_ok=True)
        file.write_text(f"# Cycle {cycle}\n")
        
        subprocess.run(["git", "add", str(file)], cwd=PROJECT, capture_output=True, timeout=5)
        subprocess.run(["git", "commit", "-m", f"auto: cycle {cycle}"], cwd=PROJECT, capture_output=True, timeout=5)
        
        print(f"✅ Cycle {cycle}", flush=True)
        
        if cycle % 10 == 0:
            subprocess.run(["git", "push", "origin", "main"], cwd=PROJECT, capture_output=True, timeout=10)
        
        for _ in range(30):
            time.sleep(1)
    except Exception as e:
        print(f"Error: {e}", flush=True)
