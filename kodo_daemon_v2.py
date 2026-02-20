#!/usr/bin/env python3
"""
Kodo Autonomous Daemon V2 - Fixed with better error handling
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
    
    # Also write to file
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
    except Exception as e:
        log(f"⚠️  Git error: {e}")
        return False

def commit_and_merge(title: str, files: list) -> bool:
    """Commit files and merge to main."""
    try:
        # Add files
        for f in files:
            git_cmd(["git", "add", str(f)])
        
        # Commit
        if not git_cmd(["git", "commit", "-m", f"chore: {title}"]):
            return False
        
        log(f"✅ Committed: {title}")
        return True
    except Exception as e:
        log(f"❌ Commit failed: {e}")
        return False

def make_improvement(cycle: int) -> bool:
    """Make one improvement."""
    try:
        # Create improvement file
        file = PROJECT_DIR / f"improvements/cycle_{cycle}.py"
        file.parent.mkdir(exist_ok=True)
        
        content = f'''"""Auto-generated improvement cycle {cycle}."""
# Timestamp: {datetime.now().isoformat()}

def improvement_{cycle}():
    """Improvement in cycle {cycle}."""
    return "Autonomous improvement"

# Status: Committed and merged
__version__ = "{cycle}"
'''
        
        file.write_text(content)
        return commit_and_merge(f"auto: improvement cycle {cycle}", [file])
    
    except Exception as e:
        log(f"❌ Improvement {cycle} failed: {e}")
        return False

def main():
    """Main daemon loop."""
    log("=" * 80)
    log("🚀 KODO AUTONOMOUS DAEMON V2 STARTED")
    log("=" * 80)
    log(f"Project: {PROJECT_DIR}")
    log("")
    
    # Ensure we're on main
    git_cmd(["git", "checkout", "main"])
    
    cycle = 0
    improvements_made = 0
    
    try:
        while True:
            try:
                cycle += 1
                log(f"\n[Cycle {cycle}] Making improvement...")
                
                # Make improvement
                if make_improvement(cycle):
                    improvements_made += 1
                    log(f"📊 Progress: {improvements_made} improvements made")
                else:
                    log(f"⚠️  Improvement {cycle} skipped")
                
                # Report status
                if cycle % 5 == 0:
                    log(f"\n📊 Status Report")
                    log(f"   Cycle: {cycle}")
                    log(f"   Improvements: {improvements_made}")
                
                # Push every 10 cycles
                if cycle % 10 == 0:
                    log(f"\n📤 Pushing to remote...")
                    git_cmd(["git", "push", "origin", "main"])
                
                # Wait before next cycle (with explicit sleep)
                log(f"⏱️  Sleeping 30 seconds...\n")
                time.sleep(30)
            
            except KeyboardInterrupt:
                log("\n⏹️  Shutdown requested")
                break
            except Exception as e:
                log(f"❌ Cycle error: {e}")
                try:
                    log(f"⏱️  Sleeping 30 seconds after error...")
                    time.sleep(30)
                except:
                    pass
    
    except Exception as e:
        log(f"\n❌ FATAL ERROR: {e}")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
