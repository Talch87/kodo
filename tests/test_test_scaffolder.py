"""Tests for TestScaffolder."""

import tempfile
from pathlib import Path

import pytest

from kodo.test_scaffolder import TestScaffolder, generate_tests
from kodo.requirements_parser import Spec, Feature, AuthConfig, TechStackChoice


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def basic_spec():
    """Create a basic test specification."""
    return Spec(
        project_name="TestApp",
        description="App for testing",
        features=[
            Feature("Users", "User management", requires_api=True),
            Feature("Products", "Product catalog", requires_api=True),
        ],
        tech_stack=[TechStackChoice("backend", "express")],
        database=None,
        auth=AuthConfig(auth_type="jwt"),
        frontend_framework=None,
        backend_framework="express",
        deployment_target=None,
    )


class TestTestScaffolder:
    """Test suite for TestScaffolder."""

    def test_scaffolder_initialization_jest(self):
        """Test TestScaffolder initialization with Jest."""
        scaffolder = TestScaffolder("jest")
        assert scaffolder.framework == "jest"

    def test_scaffolder_initialization_pytest(self):
        """Test TestScaffolder initialization with Pytest."""
        scaffolder = TestScaffolder("pytest")
        assert scaffolder.framework == "pytest"

    def test_scaffolder_initialization_mocha(self):
        """Test TestScaffolder initialization with Mocha."""
        scaffolder = TestScaffolder("mocha")
        assert scaffolder.framework == "mocha"

    def test_generate_jest_tests(self, basic_spec):
        """Test Jest test generation."""
        scaffolder = TestScaffolder("jest")
        tests = scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

        assert "describe" in tests
        assert "jest" not in tests.lower()  # Should be TypeScript/JavaScript syntax
        assert "request" in tests
        assert "/health" in tests

    def test_generate_jest_auth_tests(self, basic_spec):
        """Test that Jest includes auth tests."""
        scaffolder = TestScaffolder("jest")
        tests = scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

        assert "Authentication" in tests
        assert "/auth/register" in tests
        assert "/auth/login" in tests

    def test_generate_jest_feature_tests(self, basic_spec):
        """Test that Jest includes feature tests."""
        scaffolder = TestScaffolder("jest")
        tests = scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

        assert "Users" in tests or "users" in tests
        assert "Products" in tests or "products" in tests

    def test_generate_pytest_tests(self, basic_spec):
        """Test Pytest test generation."""
        scaffolder = TestScaffolder("pytest")
        tests = scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

        assert "def test_" in tests
        assert "client" in tests
        assert "fixture" in tests

    def test_generate_pytest_health_test(self, basic_spec):
        """Test that Pytest includes health check."""
        scaffolder = TestScaffolder("pytest")
        tests = scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

        assert "test_health_check" in tests
        assert "/health" in tests

    def test_generate_mocha_tests(self, basic_spec):
        """Test Mocha test generation."""
        scaffolder = TestScaffolder("mocha")
        tests = scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

        assert "describe" in tests
        assert "it(" in tests

    def test_generate_unit_tests_jest(self):
        """Test Jest unit test template."""
        scaffolder = TestScaffolder("jest")
        tests = scaffolder.generate_unit_tests(Path("/tmp"))

        assert "describe" in tests
        assert "it(" in tests

    def test_generate_unit_tests_pytest(self):
        """Test Pytest unit test template."""
        scaffolder = TestScaffolder("pytest")
        tests = scaffolder.generate_unit_tests(Path("/tmp"))

        assert "def test_" in tests
        assert "assert" in tests

    def test_generate_unit_tests_mocha(self):
        """Test Mocha unit test template."""
        scaffolder = TestScaffolder("mocha")
        tests = scaffolder.generate_unit_tests(Path("/tmp"))

        assert "describe" in tests
        assert "it(" in tests

    def test_unsupported_framework_raises_error(self, basic_spec):
        """Test that unsupported framework raises error."""
        scaffolder = TestScaffolder("unsupported")
        
        with pytest.raises(ValueError):
            scaffolder.generate_api_tests(basic_spec, Path("/tmp"))

    def test_tests_without_auth(self):
        """Test generation without auth."""
        spec = Spec(
            project_name="NoAuth",
            description="App without auth",
            features=[Feature("Items", "Items", requires_api=True)],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        scaffolder = TestScaffolder("jest")
        tests = scaffolder.generate_api_tests(spec, Path("/tmp"))

        # Should still have health check
        assert "/health" in tests
        # Should have features
        assert "items" in tests.lower()

    def test_convenience_function_jest(self, temp_dir, basic_spec):
        """Test generate_tests convenience function with Jest."""
        generate_tests(basic_spec, temp_dir, "jest")

        assert (temp_dir / "api.test.ts").exists()
        assert (temp_dir / "unit.test.ts").exists()

    def test_convenience_function_pytest(self, temp_dir, basic_spec):
        """Test generate_tests convenience function with Pytest."""
        generate_tests(basic_spec, temp_dir, "pytest")

        assert (temp_dir / "test_api.py").exists()
        assert (temp_dir / "test_unit.py").exists()

    def test_generated_files_are_valid(self, temp_dir, basic_spec):
        """Test that generated files are valid."""
        generate_tests(basic_spec, temp_dir, "jest")

        api_tests = (temp_dir / "api.test.ts").read_text()
        assert len(api_tests) > 0
        assert "describe" in api_tests

    def test_multiple_features_in_tests(self):
        """Test that multiple features are in tests."""
        spec = Spec(
            project_name="Multi",
            description="Multiple features",
            features=[
                Feature("Users", "Users", requires_api=True),
                Feature("Products", "Products", requires_api=True),
                Feature("Orders", "Orders", requires_api=True),
            ],
            tech_stack=[],
            database=None,
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        scaffolder = TestScaffolder("jest")
        tests = scaffolder.generate_api_tests(spec, Path("/tmp"))

        assert "Users" in tests or "users" in tests
        assert "Products" in tests or "products" in tests
        assert "Orders" in tests or "orders" in tests


class TestTestScaffolderIntegration:
    """Integration tests for TestScaffolder."""

    def test_full_test_generation_workflow(self, temp_dir):
        """Test complete test generation workflow."""
        spec = Spec(
            project_name="FullApp",
            description="Complete test generation",
            features=[
                Feature("Users", "User management", requires_api=True),
                Feature("Products", "Product catalog", requires_api=True),
            ],
            tech_stack=[TechStackChoice("backend", "express")],
            database=None,
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        # Generate tests for different frameworks
        for framework in ["jest", "pytest", "mocha"]:
            framework_dir = temp_dir / framework
            framework_dir.mkdir()
            generate_tests(spec, framework_dir, framework)

            # Verify files exist
            test_files = list(framework_dir.glob("*.ts")) + list(framework_dir.glob("*.py"))
            assert len(test_files) > 0

    def test_test_content_completeness(self, temp_dir, basic_spec):
        """Test that generated tests have complete coverage."""
        generate_tests(basic_spec, temp_dir, "jest")

        api_tests = (temp_dir / "api.test.ts").read_text()

        # Should have health check
        assert "health" in api_tests.lower()

        # Should have auth tests
        assert "auth" in api_tests.lower()
        assert "register" in api_tests.lower() or "login" in api_tests.lower()

        # Should have feature tests
        assert "users" in api_tests.lower()
        assert "products" in api_tests.lower()
