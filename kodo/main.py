#!/usr/bin/env python3
"""
KODO 2.0 CLI Entry Point

Main interface for autonomous development system
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from kodo.orchestrator import Kodo2Orchestrator


async def main():
    """Main CLI entry point"""
    
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "process":
        await handle_process(sys.argv[2:])
    elif command == "verify":
        await handle_verify(sys.argv[2:])
    elif command == "report":
        handle_report(sys.argv[2:])
    elif command == "--help" or command == "-h":
        print_help()
    else:
        print(f"Unknown command: {command}")
        print_help()
        sys.exit(1)


async def handle_process(args):
    """Handle code processing through full pipeline"""
    if not args:
        print("Usage: kodo process <code_file> [--test <test_file>] [--spec <spec_file>]")
        sys.exit(1)
    
    code_file = Path(args[0])
    if not code_file.exists():
        print(f"Error: Code file not found: {code_file}")
        sys.exit(1)
    
    code = code_file.read_text()
    test_code = None
    specification = None
    
    # Parse optional arguments
    i = 1
    while i < len(args):
        if args[i] == "--test" and i + 1 < len(args):
            test_file = Path(args[i + 1])
            if test_file.exists():
                test_code = test_file.read_text()
            i += 2
        elif args[i] == "--spec" and i + 1 < len(args):
            spec_file = Path(args[i + 1])
            if spec_file.exists():
                specification = spec_file.read_text()
            i += 2
        else:
            i += 1
    
    code_id = code_file.stem
    
    # Process through orchestrator
    print(f"\n📋 Processing {code_id}...\n")
    
    orchestrator = Kodo2Orchestrator()
    result = await orchestrator.process_code(
        code=code,
        code_id=code_id,
        test_code=test_code,
        specification=specification,
    )
    
    # Print results
    print_result(result)
    
    # Save report
    report_file = Path(f"{code_id}_report.json")
    report = orchestrator.get_full_report(code_id)
    report_file.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n📊 Report saved to {report_file}")


async def handle_verify(args):
    """Handle code verification only"""
    if not args:
        print("Usage: kodo verify <code_file> [--test <test_file>]")
        sys.exit(1)
    
    code_file = Path(args[0])
    if not code_file.exists():
        print(f"Error: Code file not found: {code_file}")
        sys.exit(1)
    
    code = code_file.read_text()
    test_code = None
    
    if len(args) > 2 and args[1] == "--test":
        test_file = Path(args[2])
        if test_file.exists():
            test_code = test_file.read_text()
    
    from kodo.verification import VerificationEngine
    
    print(f"\n✓ Verifying {code_file.stem}...\n")
    
    engine = VerificationEngine()
    result = await engine.verify(
        code=code,
        code_id=code_file.stem,
        test_code=test_code or "",
    )
    
    print(f"Score: {result.correctness_score:.1f}%")
    print(f"Status: {result.status.value}")
    print(f"Confidence: {result.confidence_level:.1f}%")
    print(f"Decision: {result.decision}")


def handle_report(args):
    """Handle report generation"""
    if not args:
        print("Usage: kodo report <code_id>")
        sys.exit(1)
    
    code_id = args[0]
    
    orchestrator = Kodo2Orchestrator()
    report = orchestrator.get_full_report(code_id)
    
    print(json.dumps(report, indent=2, default=str))


def print_result(result):
    """Print orchestration result"""
    
    # Color codes
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Determine color based on action
    if result.auto_action == "deploy":
        action_color = GREEN
        action_emoji = "🚀"
    elif result.auto_action == "review":
        action_color = YELLOW
        action_emoji = "👀"
    else:
        action_color = RED
        action_emoji = "❌"
    
    print(f"{BOLD}═══ KODO 2.0 Autonomous Decision ═══{RESET}\n")
    
    print(f"Code ID: {result.code_id}")
    print(f"Timestamp: {result.timestamp}\n")
    
    print(f"{BOLD}Results:{RESET}")
    print(f"  Verified: {result.verified} ({result.verification_score:.1f}%)")
    print(f"  Quality: {result.quality_passed} ({result.quality_score:.1f}%)")
    print(f"  Compliance: {result.specification_compliance:.1f}%")
    print(f"  Production Ready: {result.production_ready} ({result.production_score:.1f}%)")
    print(f"  Trust Level: {result.trust_level} ({result.trust_score:.1f}%)")
    
    if result.healed:
        print(f"  Errors Fixed: {result.errors_fixed}\n")
    
    print(f"{BOLD}Decision:{RESET}")
    print(f"  {action_emoji} {action_color}{result.auto_action.upper()}{RESET}")
    print(f"  Confidence: {result.confidence*100:.1f}%")
    print(f"  Reason: {result.reason}\n")


def print_help():
    """Print help message"""
    print("""
╔═══════════════════════════════════════════════════════════════╗
║                   KODO 2.0 Autonomous Development            ║
║                                                               ║
║  Transform code generation into fully autonomous decisions   ║
╚═══════════════════════════════════════════════════════════════╝

Usage: kodo <command> [arguments]

Commands:
  process <file>          Process code through full pipeline
                          Options:
                            --test <file>      Test code file
                            --spec <file>      Specification file
  
  verify <file>           Run verification only
                          Options:
                            --test <file>      Test code file
  
  report <code_id>        Generate report for code
  
  --help                  Show this help message

Examples:
  kodo process mycode.py --test test_mycode.py
  kodo verify module.py
  kodo report feature_123

The Orchestrator:
  1. Verifies code with tests (90%+ pass required)
  2. Runs 7-point quality gate checklist
  3. Validates specification compliance
  4. Scores production readiness
  5. Calculates trust score (0-100%)
  6. Makes autonomous decision: DEPLOY/REVIEW/REJECT
  7. Logs all decisions to audit trail
  8. Tracks costs and suggests optimizations
  9. Collects feedback for improvement
  10. Extracts patterns for learning

Output:
  - Console report with decision and confidence
  - JSON report file with detailed metrics
  - Audit trail for all decisions
  - Cost analysis and recommendations

Exit Codes:
  0  Success
  1  Error or validation failure
""")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
