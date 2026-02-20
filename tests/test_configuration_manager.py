"""Tests for ConfigurationManager."""

import json
import tempfile
from pathlib import Path

import pytest

from kodo.configuration_manager import (
    ConfigurationManager,
    ConfigValue,
    generate_project_config,
)
from kodo.requirements_parser import Spec, Feature, AuthConfig, DatabaseConfig


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def basic_config():
    """Create a basic configuration manager."""
    return ConfigurationManager("TestApp")


class TestConfigurationManager:
    """Test suite for ConfigurationManager."""

    def test_initialization(self):
        """Test ConfigurationManager initialization."""
        config = ConfigurationManager("MyApp")
        assert config.project_name == "MyApp"
        assert len(config.configs) > 0

    def test_default_sections(self):
        """Test that default sections are created."""
        config = ConfigurationManager("App")
        
        expected_sections = {"app", "database", "auth", "server", "features"}
        assert set(config.configs.keys()) == expected_sections

    def test_add_config_value(self, basic_config):
        """Test adding a configuration value."""
        basic_config.add_config("app", "debug", True)
        
        assert "debug" in basic_config.configs["app"]
        assert basic_config.configs["app"]["debug"].value is True

    def test_sensitive_key_auto_detection(self, basic_config):
        """Test automatic detection of sensitive keys."""
        basic_config.add_config("auth", "password", "secret123")
        basic_config.add_config("auth", "api_key", "key123")
        basic_config.add_config("auth", "jwt_secret", "secret")
        
        assert basic_config.configs["auth"]["password"].sensitive is True
        assert basic_config.configs["auth"]["api_key"].sensitive is True
        assert basic_config.configs["auth"]["jwt_secret"].sensitive is True

    def test_sensitive_key_override(self, basic_config):
        """Test explicit sensitive flag overrides auto-detection."""
        basic_config.add_config("app", "name", "MyApp", sensitive=True)
        
        assert basic_config.configs["app"]["name"].sensitive is True

    def test_config_value_dataclass(self):
        """Test ConfigValue dataclass."""
        val = ConfigValue(
            key="test_key",
            value="test_value",
            required=True,
            sensitive=False,
            description="Test configuration",
            default="default_value",
        )
        
        assert val.key == "test_key"
        assert val.sensitive is False

    def test_generate_env_file(self, temp_dir, basic_config):
        """Test .env file generation."""
        basic_config.add_config("database", "url", "postgresql://localhost/db")
        
        env_content = basic_config.generate_env_file(temp_dir / ".env")
        
        assert "NODE_ENV" in env_content
        assert "APP_ENV" in env_content
        assert "postgresql://localhost/db" in env_content

    def test_env_file_written_to_disk(self, temp_dir, basic_config):
        """Test that .env file is written to disk."""
        basic_config.generate_env_file(temp_dir / ".env")
        
        assert (temp_dir / ".env").exists()
        content = (temp_dir / ".env").read_text()
        assert len(content) > 0

    def test_generate_env_example(self, temp_dir, basic_config):
        """Test .env.example generation."""
        basic_config.add_config(
            "database",
            "url",
            "postgresql://localhost/db",
            sensitive=True,
            description="Database connection string",
        )
        
        example = basic_config.generate_env_example(temp_dir / ".env.example")
        
        assert "Database connection string" in example
        assert ".env.example" or "copy to .env" in example.lower()

    def test_env_example_excludes_sensitive(self, temp_dir, basic_config):
        """Test that .env.example masks sensitive values."""
        basic_config.add_config("auth", "jwt_secret", "my-secret")
        
        example = basic_config.generate_env_example(temp_dir / ".env.example")
        
        assert "my-secret" not in example

    def test_generate_config_json(self, temp_dir, basic_config):
        """Test config.json generation."""
        basic_config.add_config("app", "port", 3000)
        
        json_content = basic_config.generate_config_json(temp_dir / "config.json")
        data = json.loads(json_content)
        
        assert "app" in data
        assert "port" in data["app"]

    def test_config_json_file_written(self, temp_dir, basic_config):
        """Test that config.json is written to disk."""
        basic_config.generate_config_json(temp_dir / "config.json")
        
        assert (temp_dir / "config.json").exists()

    def test_generate_config_ts(self, temp_dir, basic_config):
        """Test TypeScript config generation."""
        ts_code = basic_config.generate_config_ts(temp_dir / "config.ts")
        
        assert "import dotenv" in ts_code
        assert "interface Config" in ts_code
        assert "export default" in ts_code

    def test_generate_config_py(self, temp_dir, basic_config):
        """Test Python config generation."""
        py_code = basic_config.generate_config_py(temp_dir / "config.py")
        
        assert "class Config:" in py_code
        assert "os.getenv" in py_code
        assert "class ProductionConfig" in py_code

    def test_validate_config_success(self, basic_config):
        """Test config validation with valid config."""
        basic_config.add_config("app", "required_field", "value")
        
        errors = basic_config.validate_config()
        
        assert len(errors) == 0

    def test_validate_config_failure(self, basic_config):
        """Test config validation with missing required values."""
        basic_config.add_config("auth", "secret", None, required=True)
        
        errors = basic_config.validate_config()
        
        assert len(errors) > 0

    def test_load_from_env(self, basic_config):
        """Test loading config from environment."""
        import os
        
        os.environ["TEST_KEY"] = "test_value"
        basic_config.add_config("test", "test_key", None)
        basic_config.load_from_env()
        
        assert basic_config.configs["test"]["test_key"].value == "test_value"

    def test_to_dict(self, basic_config):
        """Test converting config to dictionary."""
        basic_config.add_config("app", "name", "MyApp")
        basic_config.add_config("auth", "secret", "value", sensitive=True)
        
        config_dict = basic_config.to_dict()
        
        assert config_dict["app"]["name"] == "MyApp"
        assert config_dict["auth"]["secret"] == "***SENSITIVE***"

    def test_to_json(self, basic_config):
        """Test converting config to JSON."""
        basic_config.add_config("app", "name", "MyApp")
        
        json_str = basic_config.to_json()
        data = json.loads(json_str)
        
        assert "app" in data
        assert data["app"]["name"] == "MyApp"

    def test_to_json_includes_sensitive_flag(self, basic_config):
        """Test JSON conversion with sensitive flag."""
        basic_config.add_config("auth", "secret", "value", sensitive=True)
        
        json_str = basic_config.to_json(include_sensitive=False)
        data = json.loads(json_str)
        
        assert data["auth"]["secret"] == "***SENSITIVE***"

    def test_config_with_description(self, basic_config):
        """Test config with description."""
        basic_config.add_config(
            "database",
            "url",
            "postgresql://localhost",
            description="Database URL",
        )
        
        assert basic_config.configs["database"]["url"].description == "Database URL"

    def test_config_with_default(self, basic_config):
        """Test config with default value."""
        basic_config.add_config("app", "port", 3000, default=8080)
        
        assert basic_config.configs["app"]["port"].default == 8080

    def test_multiple_sections(self, basic_config):
        """Test configuration across multiple sections."""
        basic_config.add_config("app", "name", "MyApp")
        basic_config.add_config("database", "url", "postgresql://localhost")
        basic_config.add_config("auth", "jwt_secret", "secret")
        
        config_dict = basic_config.to_dict()
        
        assert len(config_dict) >= 3
        assert "app" in config_dict
        assert "database" in config_dict
        assert "auth" in config_dict

    def test_convenience_function_basic(self, temp_dir):
        """Test generate_project_config convenience function."""
        spec = Spec(
            project_name="TestApp",
            description="Test",
            features=[Feature("Users", "Users", requires_api=True)],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )
        
        config = generate_project_config(spec, temp_dir)
        
        assert config.project_name == "TestApp"
        assert (temp_dir / ".env").exists()
        assert (temp_dir / ".env.example").exists()

    def test_convenience_function_generates_files(self, temp_dir):
        """Test that convenience function generates all files."""
        spec = Spec(
            project_name="App",
            description="App",
            features=[],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )
        
        generate_project_config(spec, temp_dir)
        
        assert (temp_dir / ".env").exists()
        assert (temp_dir / ".env.example").exists()
        assert (temp_dir / "config.json").exists()
        assert (temp_dir / "config.ts").exists()

    def test_auth_providers_in_config(self, temp_dir):
        """Test that auth providers create config values."""
        spec = Spec(
            project_name="OAuthApp",
            description="OAuth app",
            features=[],
            tech_stack=[],
            database=None,
            auth=AuthConfig(auth_type="oauth2", providers=["google", "github"]),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )
        
        config = generate_project_config(spec, temp_dir)
        
        assert "google_client_id" in config.configs["auth"]
        assert "github_client_secret" in config.configs["auth"]

    def test_feature_config_generation(self, temp_dir):
        """Test that features are added to config."""
        spec = Spec(
            project_name="App",
            description="Test",
            features=[
                Feature("Users", "Users"),
                Feature("Products", "Products"),
            ],
            tech_stack=[],
            database=None,
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )
        
        config = generate_project_config(spec, temp_dir)
        
        assert "users" in config.configs["features"]
        assert "products" in config.configs["features"]


class TestConfigurationManagerIntegration:
    """Integration tests for ConfigurationManager."""

    def test_full_configuration_workflow(self, temp_dir):
        """Test complete configuration workflow."""
        spec = Spec(
            project_name="CompleteApp",
            description="Complete app",
            features=[
                Feature("Users", "User management"),
                Feature("Products", "Product catalog"),
            ],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=AuthConfig(auth_type="jwt", providers=["google"]),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )
        
        config = generate_project_config(spec, temp_dir)
        
        # Verify all files are created
        assert (temp_dir / ".env").exists()
        assert (temp_dir / ".env.example").exists()
        assert (temp_dir / "config.json").exists()
        assert (temp_dir / "config.ts").exists()
        
        # Verify configuration content
        env_content = (temp_dir / ".env").read_text()
        assert "NODE_ENV" in env_content
        assert "URL" in env_content  # DATABASE.URL becomes URL in env
        assert "JWT_SECRET" in env_content

    def test_config_validation_workflow(self, temp_dir):
        """Test config validation in complete workflow."""
        config = ConfigurationManager("App")
        config.add_config("database", "url", None, required=True)
        
        errors = config.validate_config()
        
        # Should have error for missing URL
        assert any("url" in err.lower() for err in errors)
