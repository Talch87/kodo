"""Tests for AppScaffolder."""

import json
import tempfile
from pathlib import Path

import pytest

from kodo.app_scaffolder import AppScaffolder, scaffold_project
from kodo.requirements_parser import Spec, Feature, DatabaseConfig, AuthConfig, TechStackChoice


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
        description="A test application",
        features=[
            Feature("User Authentication", "Login and user accounts"),
            Feature("Dashboard", "Main dashboard view"),
        ],
        tech_stack=[
            TechStackChoice("frontend", "react"),
            TechStackChoice("backend", "express"),
        ],
        database=DatabaseConfig(db_type="postgresql"),
        auth=AuthConfig(auth_type="jwt"),
        frontend_framework="react",
        backend_framework="express",
        deployment_target="docker",
    )


class TestAppScaffolder:
    """Test suite for AppScaffolder."""

    def test_scaffolder_initialization(self, temp_dir):
        """Test scaffolder can be initialized."""
        scaffolder = AppScaffolder(temp_dir)
        assert scaffolder.base_path == temp_dir

    def test_scaffold_creates_project_directory(self, temp_dir, basic_spec):
        """Test that scaffolding creates the project directory."""
        scaffolder = AppScaffolder(temp_dir)
        result_path = scaffolder.scaffold(basic_spec)

        assert result_path.exists()
        assert result_path.is_dir()

    def test_scaffold_creates_src_directory(self, temp_dir, basic_spec):
        """Test that src directory is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        assert (project_path / "src").exists()

    def test_scaffold_creates_tests_directory(self, temp_dir, basic_spec):
        """Test that tests directory is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        assert (project_path / "tests").exists()

    def test_scaffold_creates_docs_directory(self, temp_dir, basic_spec):
        """Test that docs directory is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        assert (project_path / "docs").exists()

    def test_scaffold_creates_package_json(self, temp_dir, basic_spec):
        """Test that package.json is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        package_json = project_path / "package.json"
        assert package_json.exists()

        with open(package_json) as f:
            data = json.load(f)
            assert data["name"] == "testapp"
            assert data["version"] == "0.1.0"

    def test_package_json_has_dependencies(self, temp_dir, basic_spec):
        """Test that package.json includes dependencies."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        with open(project_path / "package.json") as f:
            data = json.load(f)
            assert "express" in data["dependencies"]

    def test_package_json_has_dev_dependencies(self, temp_dir, basic_spec):
        """Test that package.json includes dev dependencies."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        with open(project_path / "package.json") as f:
            data = json.load(f)
            assert "typescript" in data["devDependencies"]
            assert "jest" in data["devDependencies"]

    def test_scaffold_creates_gitignore(self, temp_dir, basic_spec):
        """Test that .gitignore is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        gitignore = project_path / ".gitignore"
        assert gitignore.exists()

        content = gitignore.read_text()
        assert "node_modules/" in content

    def test_scaffold_creates_env_example(self, temp_dir, basic_spec):
        """Test that .env.example is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        env_file = project_path / ".env.example"
        assert env_file.exists()

    def test_env_file_includes_jwt_secret_for_jwt_auth(self, temp_dir, basic_spec):
        """Test that .env.example includes JWT_SECRET for JWT auth."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        env_file = project_path / ".env.example"
        content = env_file.read_text()
        assert "JWT_SECRET" in content

    def test_scaffold_creates_readme(self, temp_dir, basic_spec):
        """Test that README.md is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        readme = project_path / "README.md"
        assert readme.exists()

        content = readme.read_text()
        assert "TestApp" in content
        assert basic_spec.description in content

    def test_scaffold_creates_tsconfig(self, temp_dir, basic_spec):
        """Test that tsconfig.json is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        tsconfig = project_path / "tsconfig.json"
        assert tsconfig.exists()

        with open(tsconfig) as f:
            data = json.load(f)
            assert data["compilerOptions"]["strict"] is True

    def test_scaffold_creates_dockerfile(self, temp_dir, basic_spec):
        """Test that Dockerfile is created for backend projects."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        dockerfile = project_path / "Dockerfile"
        assert dockerfile.exists()

        content = dockerfile.read_text()
        assert "node:18-alpine" in content

    def test_scaffold_creates_docker_compose(self, temp_dir, basic_spec):
        """Test that docker-compose.yml is created for database projects."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        docker_compose = project_path / "docker-compose.yml"
        assert docker_compose.exists()

    def test_scaffold_creates_backend_index(self, temp_dir, basic_spec):
        """Test that backend index.ts is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        index = project_path / "src" / "index.ts"
        assert index.exists()

        content = index.read_text()
        assert "express" in content

    def test_scaffold_creates_api_routes(self, temp_dir, basic_spec):
        """Test that API routes file is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        routes = project_path / "src" / "api" / "routes.ts"
        assert routes.exists()

    def test_scaffold_creates_react_components(self, temp_dir, basic_spec):
        """Test that React components are created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        app_component = project_path / "src" / "components" / "App.tsx"
        assert app_component.exists()

        content = app_component.read_text()
        assert "TestApp" in content

    def test_scaffold_creates_spec_file(self, temp_dir, basic_spec):
        """Test that .kodo/spec.json is created."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        spec_file = project_path / ".kodo" / "spec.json"
        assert spec_file.exists()

        with open(spec_file) as f:
            data = json.load(f)
            assert data["project_name"] == "TestApp"

    def test_scaffold_custom_output_dir(self, temp_dir):
        """Test scaffolding with custom output directory."""
        spec = Spec(
            project_name="TestApp",
            description="Test",
            features=[],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        result_path = scaffolder.scaffold(spec, "custom-output")

        assert result_path.name == "custom-output"
        assert (result_path / "src").exists()

    def test_scaffold_project_convenience_function(self, temp_dir):
        """Test convenience function scaffold_project."""
        spec = Spec(
            project_name="QuickApp",
            description="Quick test",
            features=[],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework=None,
            deployment_target=None,
        )

        # Need to change working directory for convenience function
        import os
        old_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result_path = scaffold_project(spec)
            assert result_path.exists()
        finally:
            os.chdir(old_cwd)

    def test_scaffold_without_backend(self, temp_dir):
        """Test scaffolding without backend framework."""
        spec = Spec(
            project_name="FrontendOnly",
            description="Frontend only app",
            features=[],
            tech_stack=[TechStackChoice("frontend", "react")],
            database=None,
            auth=None,
            frontend_framework="react",
            backend_framework=None,
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(spec)

        # Should not create backend index
        assert not (project_path / "src" / "index.ts").exists()
        # But should create components
        assert (project_path / "src" / "components").exists()

    def test_scaffold_without_frontend(self, temp_dir):
        """Test scaffolding without frontend framework."""
        spec = Spec(
            project_name="BackendOnly",
            description="Backend only app",
            features=[],
            tech_stack=[TechStackChoice("backend", "express")],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(spec)

        # Should create backend
        assert (project_path / "src" / "index.ts").exists()

    def test_scaffold_without_database(self, temp_dir):
        """Test scaffolding without database."""
        spec = Spec(
            project_name="NoDbApp",
            description="App without database",
            features=[],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework=None,
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(spec)

        # Should still create migration directory but no docker-compose
        assert (project_path / "src").exists()

    def test_get_dependencies_express(self, temp_dir):
        """Test dependency detection for Express."""
        spec = Spec(
            project_name="ExpressApp",
            description="Express app",
            features=[],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        deps = scaffolder._get_dependencies(spec)

        assert "express" in deps
        assert "dotenv" in deps

    def test_get_dependencies_with_auth(self, temp_dir):
        """Test dependency detection with JWT auth."""
        spec = Spec(
            project_name="AuthApp",
            description="Auth app",
            features=[],
            tech_stack=[],
            database=None,
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        deps = scaffolder._get_dependencies(spec)

        assert "jsonwebtoken" in deps

    def test_project_name_with_spaces(self, temp_dir):
        """Test that project names with spaces are handled."""
        spec = Spec(
            project_name="My Awesome App",
            description="App with spaces in name",
            features=[],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework=None,
            deployment_target=None,
        )

        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(spec)

        # Directory name should replace spaces with hyphens
        assert "my-awesome-app" in str(project_path)

    def test_gitkeep_files_created(self, temp_dir, basic_spec):
        """Test that .gitkeep files are created in directories."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        # Check some key directories have .gitkeep
        assert (project_path / "src" / ".gitkeep").exists()
        assert (project_path / "tests" / ".gitkeep").exists()

    def test_database_migrations_directory_created(self, temp_dir, basic_spec):
        """Test that migrations directory is created for database projects."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        assert (project_path / "migrations").exists()

    def test_env_includes_database_url(self, temp_dir, basic_spec):
        """Test that DATABASE_URL is in .env.example for database projects."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        env_file = project_path / ".env.example"
        content = env_file.read_text()
        assert "DATABASE_URL" in content

    def test_package_json_scripts(self, temp_dir, basic_spec):
        """Test that package.json includes useful scripts."""
        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(basic_spec)

        with open(project_path / "package.json") as f:
            data = json.load(f)
            scripts = data["scripts"]
            assert "dev" in scripts
            assert "build" in scripts
            assert "test" in scripts
            assert "lint" in scripts


class TestAppScaffolderIntegration:
    """Integration tests for AppScaffolder."""

    def test_complete_scaffold_workflow(self, temp_dir):
        """Test complete scaffolding workflow."""
        spec = Spec(
            project_name="FullApp",
            description="A complete test application",
            features=[
                Feature("API", "REST API endpoints"),
                Feature("Dashboard", "User dashboard"),
                Feature("User Authentication", "Login system"),
            ],
            tech_stack=[
                TechStackChoice("frontend", "react"),
                TechStackChoice("backend", "express"),
                TechStackChoice("database", "postgresql"),
            ],
            database=DatabaseConfig(
                db_type="postgresql",
                needs_migrations=True,
                needs_orm=True,
            ),
            auth=AuthConfig(
                auth_type="jwt",
                providers=["google"],
            ),
            frontend_framework="react",
            backend_framework="express",
            deployment_target="docker",
            estimated_effort_hours=40,
        )

        scaffolder = AppScaffolder(temp_dir)
        project_path = scaffolder.scaffold(spec)

        # Verify complete structure
        assert (project_path / "src").exists()
        assert (project_path / "tests").exists()
        assert (project_path / "migrations").exists()
        assert (project_path / "docs").exists()

        # Verify configuration files
        assert (project_path / "package.json").exists()
        assert (project_path / ".gitignore").exists()
        assert (project_path / ".env.example").exists()
        assert (project_path / "README.md").exists()
        assert (project_path / "tsconfig.json").exists()
        assert (project_path / "Dockerfile").exists()
        assert (project_path / "docker-compose.yml").exists()

        # Verify backend structure
        assert (project_path / "src" / "index.ts").exists()
        assert (project_path / "src" / "api").exists()

        # Verify frontend structure
        assert (project_path / "src" / "components").exists()
        assert (project_path / "src" / "pages").exists()

        # Verify spec is saved
        assert (project_path / ".kodo" / "spec.json").exists()
