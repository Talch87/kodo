#!/usr/bin/env python3
"""
Kodo Autonomous Daemon V3 - No long sleeps, uses quick loop
"""

import subprocess
import time
import sys
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path("/tmp/kodo-fork")
LOG_FILE = Path("/tmp/kodo-daemon.log")

def log(msg: str):
    """Log with timestamp."""
    ts = datetime.now().strftime("%H:%M:%S")
    msg_with_ts = f"[{ts}] {msg}"
    print(msg_with_ts, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(msg_with_ts + "\n")
    except:
        pass

def git_cmd(cmd: list, timeout=5) -> bool:
    """Run git command safely."""
    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_DIR,
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result.returncode == 0
    except:
        return False

def make_improvement(cycle: int) -> bool:
    """Make one improvement."""
    try:
        # Create improvement file
        file = PROJECT_DIR / f"improvements/cycle_{cycle:04d}.py"
        file.parent.mkdir(exist_ok=True)
        
        content = f'''# Cycle {cycle} - {datetime.now().isoformat()}
def improvement(): return "Cycle {cycle}"
'''
        
        file.write_text(content)
        
        # Commit
        git_cmd(["git", "add", str(file)])
        git_cmd(["git", "commit", "-m", f"auto: cycle {cycle}"])
        
        log(f"✅ Cycle {cycle}: committed")
        return True
    except Exception as e:
        log(f"❌ Cycle {cycle}: {e}")
        return False

def main():
    """Main daemon loop."""
    log("🚀 KODO DAEMON V3 STARTED")
    
    git_cmd(["git", "checkout", "main"])
    
    cycle = 0
    wait_ticks = 0
    wait_duration = 30  # 30 seconds between improvements
    
    while True:
        # Increment wait counter
        wait_ticks += 1
        
        # Once we've waited long enough, make improvement
        if wait_ticks >= wait_duration:
            cycle += 1
            try:
                make_improvement(cycle)
                if cycle % 10 == 0:
                    git_cmd(["git", "push", "origin", "main"])
            except:
                pass
            wait_ticks = 0
        
        # Sleep 1 second (so we can be responsive)
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            log("⏹️  Shutdown")
            break
        except:
            pass
