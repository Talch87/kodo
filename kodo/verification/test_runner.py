"""
Test Runner: Execute tests and collect results
"""

import asyncio
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class TestResult:
    """Result of a single test execution"""
    name: str
    passed: bool
    duration_ms: float
    output: str
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "passed": self.passed,
            "duration_ms": self.duration_ms,
            "output": self.output[:500],
            "error": self.error,
            "return_code": self.return_code,
        }


class TestRunner:
    """Execute tests for code verification"""

    def __init__(self, timeout_seconds: int = 30):
        """
        Initialize test runner
        
        Args:
            timeout_seconds: Maximum time to run all tests
        """
        self.timeout_seconds = timeout_seconds

    async def run_tests(
        self,
        code: str,
        test_code: str,
        test_files: Optional[List[Path]] = None,
    ) -> List[TestResult]:
        """
        Run tests for given code
        
        Args:
            code: Code to test
            test_code: Test code as string
            test_files: Optional test files to run
            
        Returns:
            List of TestResult objects
        """
        results: List[TestResult] = []

        # Run inline tests from test_code
        if test_code:
            inline_results = await self._run_inline_tests(code, test_code)
            results.extend(inline_results)

        # Run test files if provided
        if test_files:
            for test_file in test_files:
                file_results = await self._run_test_file(test_file)
                results.extend(file_results)

        return results

    async def _run_inline_tests(
        self,
        code: str,
        test_code: str,
    ) -> List[TestResult]:
        """Run inline tests from test code"""
        results = []

        # Create temporary Python file with code and tests
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            # Combine code and tests
            combined = f"{code}\n\n{test_code}"
            f.write(combined)
            f.flush()
            temp_path = f.name

        try:
            start_time = time.time()
            result = await asyncio.wait_for(
                self._execute_test(temp_path),
                timeout=self.timeout_seconds,
            )
            duration_ms = (time.time() - start_time) * 1000

            # Parse pytest output
            test_result = TestResult(
                name="inline_tests",
                passed=result["return_code"] == 0,
                duration_ms=duration_ms,
                output=result["stdout"],
                error=result.get("stderr"),
                stdout=result["stdout"],
                stderr=result.get("stderr", ""),
                return_code=result["return_code"],
            )
            results.append(test_result)

        except asyncio.TimeoutError:
            results.append(
                TestResult(
                    name="inline_tests",
                    passed=False,
                    duration_ms=self.timeout_seconds * 1000,
                    output="",
                    error=f"Tests timed out after {self.timeout_seconds}s",
                )
            )
        except Exception as e:
            results.append(
                TestResult(
                    name="inline_tests",
                    passed=False,
                    duration_ms=0,
                    output="",
                    error=str(e),
                )
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

        return results

    async def _run_test_file(self, test_file: Path) -> List[TestResult]:
        """Run a test file"""
        results = []

        if not test_file.exists():
            results.append(
                TestResult(
                    name=test_file.name,
                    passed=False,
                    duration_ms=0,
                    output="",
                    error=f"Test file not found: {test_file}",
                )
            )
            return results

        try:
            start_time = time.time()
            result = await asyncio.wait_for(
                self._execute_test(str(test_file)),
                timeout=self.timeout_seconds,
            )
            duration_ms = (time.time() - start_time) * 1000

            test_result = TestResult(
                name=test_file.stem,
                passed=result["return_code"] == 0,
                duration_ms=duration_ms,
                output=result["stdout"],
                error=result.get("stderr"),
                stdout=result["stdout"],
                stderr=result.get("stderr", ""),
                return_code=result["return_code"],
            )
            results.append(test_result)

        except asyncio.TimeoutError:
            results.append(
                TestResult(
                    name=test_file.stem,
                    passed=False,
                    duration_ms=self.timeout_seconds * 1000,
                    output="",
                    error=f"Test timed out after {self.timeout_seconds}s",
                )
            )
        except Exception as e:
            results.append(
                TestResult(
                    name=test_file.stem,
                    passed=False,
                    duration_ms=0,
                    output="",
                    error=str(e),
                )
            )

        return results

    @staticmethod
    async def _execute_test(test_path: str) -> Dict[str, Any]:
        """Execute a test file and return results"""
        try:
            # Run with python -m pytest
            process = await asyncio.create_subprocess_exec(
                "python",
                "-m",
                "pytest",
                test_path,
                "-v",
                "--tb=short",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_data, stderr_data = await process.communicate()

            return {
                "return_code": process.returncode,
                "stdout": stdout_data.decode("utf-8", errors="ignore"),
                "stderr": stderr_data.decode("utf-8", errors="ignore"),
            }

        except FileNotFoundError:
            # Fallback to direct python execution
            process = await asyncio.create_subprocess_exec(
                "python",
                test_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_data, stderr_data = await process.communicate()

            return {
                "return_code": process.returncode,
                "stdout": stdout_data.decode("utf-8", errors="ignore"),
                "stderr": stderr_data.decode("utf-8", errors="ignore"),
            }

    async def verify_syntax(self, code: str) -> tuple:
        """
        Verify code syntax
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        ) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            result = await self._execute_test(temp_path)
            if result["return_code"] == 0:
                return True, ""
            else:
                return False, result.get("stderr", "Syntax error")
        finally:
            Path(temp_path).unlink(missing_ok=True)
