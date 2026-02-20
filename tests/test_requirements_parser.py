"""Tests for RequirementsParser."""

import pytest
from kodo.requirements_parser import (
    RequirementsParser,
    Spec,
    Feature,
    DatabaseConfig,
    AuthConfig,
    TechStackChoice,
    parse_goal,
)


class TestRequirementsParser:
    """Test suite for RequirementsParser."""

    def test_parse_simple_goal(self):
        """Test parsing a simple project goal."""
        goal = "Build a todo app with React and Express"
        parser = RequirementsParser()
        spec = parser.parse(goal)

        assert spec.project_name == "Build"
        assert spec.frontend_framework == "react"
        assert spec.backend_framework == "express"
        assert len(spec.features) > 0

    def test_parse_with_explicit_project_name(self):
        """Test parsing with explicit project name."""
        goal = "Build a task management system"
        parser = RequirementsParser()
        spec = parser.parse(goal, project_name="TaskMaster")

        assert spec.project_name == "TaskMaster"

    def test_extract_project_name_from_quoted_string(self):
        """Test extracting project name from quoted string."""
        goal = 'Build "MyAwesomeApp" - a blogging platform'
        parser = RequirementsParser()
        name = parser._extract_project_name(goal)

        assert name == "MyAwesomeApp"

    def test_detect_react_frontend(self):
        """Test detection of React frontend."""
        parser = RequirementsParser()
        assert parser._detect_frontend("build a nextjs app") == "react"
        assert parser._detect_frontend("create with react") == "react"
        assert parser._detect_frontend("next.js dashboard") == "react"

    def test_detect_vue_frontend(self):
        """Test detection of Vue frontend."""
        parser = RequirementsParser()
        assert parser._detect_frontend("build with vue") == "vue"
        assert parser._detect_frontend("nuxt application") == "vue"

    def test_detect_svelte_frontend(self):
        """Test detection of Svelte frontend."""
        parser = RequirementsParser()
        assert parser._detect_frontend("svelte web app") == "svelte"

    def test_detect_frontend_default(self):
        """Test frontend detection defaults to React when needed."""
        parser = RequirementsParser()
        assert parser._detect_frontend("build a dashboard") == "react"
        assert parser._detect_frontend("web interface") == "react"

    def test_detect_express_backend(self):
        """Test detection of Express backend."""
        parser = RequirementsParser()
        assert parser._detect_backend("build with express") == "express"
        assert parser._detect_backend("nodejs server") == "express"

    def test_detect_fastapi_backend(self):
        """Test detection of FastAPI backend."""
        parser = RequirementsParser()
        assert parser._detect_backend("python fastapi") == "fastapi"
        assert parser._detect_backend("build with python") == "fastapi"

    def test_detect_django_backend(self):
        """Test detection of Django backend."""
        parser = RequirementsParser()
        assert parser._detect_backend("django application") == "django"

    def test_detect_rails_backend(self):
        """Test detection of Rails backend."""
        parser = RequirementsParser()
        assert parser._detect_backend("ruby on rails") == "rails"

    def test_detect_backend_default(self):
        """Test backend detection defaults to Express when needed."""
        parser = RequirementsParser()
        assert parser._detect_backend("build a rest api") == "express"
        assert parser._detect_backend("backend server") == "express"

    def test_detect_postgresql_database(self):
        """Test detection of PostgreSQL."""
        parser = RequirementsParser()
        assert parser._detect_database("postgres database").db_type == "postgresql"
        assert parser._detect_database("postgresql store").db_type == "postgresql"

    def test_detect_mongodb_database(self):
        """Test detection of MongoDB."""
        parser = RequirementsParser()
        assert parser._detect_database("mongo database").db_type == "mongodb"
        assert parser._detect_database("nosql store").db_type == "mongodb"

    def test_detect_mysql_database(self):
        """Test detection of MySQL."""
        parser = RequirementsParser()
        assert parser._detect_database("mysql store").db_type == "mysql"
        assert parser._detect_database("mariadb database").db_type == "mysql"

    def test_detect_sqlite_database(self):
        """Test detection of SQLite."""
        parser = RequirementsParser()
        assert parser._detect_database("sqlite local").db_type == "sqlite"

    def test_database_config_includes_migrations(self):
        """Test database config detects migration needs."""
        parser = RequirementsParser()
        db = parser._detect_database("postgres with migrations and schema versioning")

        assert db is not None
        assert db.needs_migrations is True

    def test_database_config_includes_orm(self):
        """Test database config detects ORM needs."""
        parser = RequirementsParser()
        db = parser._detect_database("postgres with orm")

        assert db is not None
        assert db.needs_orm is True

    def test_database_orm_selection(self):
        """Test ORM selection based on backend."""
        parser = RequirementsParser()

        # Python → SQLAlchemy
        db = parser._detect_database("python app with database")
        assert db.orm_type == "sqlalchemy"

        # MongoDB → Mongoose
        db = parser._detect_database("mongo database")
        assert db.orm_type == "mongoose"

    def test_detect_jwt_auth(self):
        """Test detection of JWT auth."""
        parser = RequirementsParser()
        auth = parser._detect_auth("secure api with jwt")

        assert auth is not None
        assert auth.auth_type == "jwt"

    def test_detect_oauth_auth(self):
        """Test detection of OAuth auth."""
        parser = RequirementsParser()
        auth = parser._detect_auth("google oauth login")

        assert auth is not None
        assert auth.auth_type == "oauth2"
        assert "google" in auth.providers

    def test_detect_session_auth(self):
        """Test detection of session-based auth."""
        parser = RequirementsParser()
        auth = parser._detect_auth("cookie session login")

        assert auth is not None
        assert auth.auth_type == "session"

    def test_detect_auth_providers(self):
        """Test detection of auth providers."""
        parser = RequirementsParser()
        auth = parser._detect_auth("support google and github login")

        assert "google" in auth.providers
        assert "github" in auth.providers

    def test_detect_auth_default(self):
        """Test auth detection defaults to JWT when needed."""
        parser = RequirementsParser()
        auth = parser._detect_auth("app with user accounts and authentication")

        assert auth is not None
        assert auth.auth_type == "jwt"

    def test_detect_deployment_aws(self):
        """Test detection of AWS deployment."""
        parser = RequirementsParser()
        assert parser._detect_deployment("deploy on aws") == "aws"
        assert parser._detect_deployment("amazon infrastructure") == "aws"

    def test_detect_deployment_heroku(self):
        """Test detection of Heroku deployment."""
        parser = RequirementsParser()
        assert parser._detect_deployment("heroku deployment") == "heroku"

    def test_detect_deployment_docker(self):
        """Test detection of Docker deployment."""
        parser = RequirementsParser()
        assert parser._detect_deployment("docker container") == "docker"
        assert parser._detect_deployment("containerized app") == "docker"

    def test_extract_features_authentication(self):
        """Test extraction of authentication feature."""
        parser = RequirementsParser()
        features = parser._extract_features("build with user authentication")

        assert any(f.name == "User Authentication" for f in features)

    def test_extract_features_dashboard(self):
        """Test extraction of dashboard feature."""
        parser = RequirementsParser()
        features = parser._extract_features("dashboard for analytics")

        assert any(f.name == "Dashboard" for f in features)

    def test_extract_features_api(self):
        """Test extraction of API feature."""
        parser = RequirementsParser()
        features = parser._extract_features("rest api with json")

        assert any(f.name == "API" for f in features)

    def test_extract_features_payment(self):
        """Test extraction of payment feature."""
        parser = RequirementsParser()
        features = parser._extract_features("stripe payment integration")

        assert any(f.name == "Payment Processing" for f in features)

    def test_feature_priority_detection(self):
        """Test detection of feature priority."""
        parser = RequirementsParser()
        features = parser._extract_features("critical: user authentication, nice to have: analytics")

        critical = [f for f in features if "Authentication" in f.name]
        if critical:
            assert critical[0].priority == "critical"

    def test_estimate_effort_base(self):
        """Test effort estimation starts with base."""
        parser = RequirementsParser()
        spec = parser.parse("simple app")

        assert spec.estimated_effort_hours >= 8

    def test_estimate_effort_with_features(self):
        """Test effort increases with features."""
        parser = RequirementsParser()
        goal_simple = "simple app"
        goal_complex = "app with auth, dashboard, api, and payments"

        spec_simple = parser.parse(goal_simple)
        spec_complex = parser.parse(goal_complex)

        assert spec_complex.estimated_effort_hours > spec_simple.estimated_effort_hours

    def test_estimate_effort_with_frontend(self):
        """Test effort includes frontend time."""
        parser = RequirementsParser()
        spec = parser.parse("react dashboard")

        assert spec.estimated_effort_hours >= 20

    def test_estimate_effort_with_database(self):
        """Test effort includes database setup."""
        parser = RequirementsParser()
        spec = parser.parse("app with postgresql and migrations")

        assert spec.estimated_effort_hours >= 16

    def test_spec_to_dict(self):
        """Test Spec serialization to dict."""
        feature = Feature("Feature1", "Description", "high")
        tech = TechStackChoice("frontend", "react")
        spec = Spec(
            project_name="TestApp",
            description="Test",
            features=[feature],
            tech_stack=[tech],
            database=None,
            auth=None,
            frontend_framework="react",
            backend_framework="express",
            deployment_target="docker",
        )

        spec_dict = spec.to_dict()

        assert spec_dict["project_name"] == "TestApp"
        assert len(spec_dict["features"]) == 1
        assert spec_dict["frontend_framework"] == "react"

    def test_spec_to_json(self):
        """Test Spec serialization to JSON."""
        feature = Feature("Feature1", "Description")
        tech = TechStackChoice("frontend", "react")
        spec = Spec(
            project_name="TestApp",
            description="Test",
            features=[feature],
            tech_stack=[tech],
            database=None,
            auth=None,
            frontend_framework="react",
            backend_framework=None,
            deployment_target=None,
        )

        json_str = spec.to_json()

        assert "TestApp" in json_str
        assert "Feature1" in json_str
        assert "react" in json_str

    def test_convenience_parse_goal(self):
        """Test parse_goal convenience function."""
        spec = parse_goal("Build a todo app with React")

        assert spec is not None
        assert spec.frontend_framework == "react"
        assert len(spec.features) > 0

    def test_complex_goal_parsing(self):
        """Test parsing a complex real-world goal."""
        goal = """
        Build a "BlogHub" content management system with:
        - React frontend with Nextjs
        - Python FastAPI backend
        - PostgreSQL with migrations
        - JWT authentication with Google OAuth
        - File uploads to S3
        - Real-time notifications
        - Admin dashboard
        - Payment processing via Stripe
        - Deploy on AWS
        """

        parser = RequirementsParser()
        spec = parser.parse(goal)

        assert spec.project_name == "BlogHub"
        assert spec.frontend_framework == "react"
        assert spec.backend_framework == "fastapi"
        assert spec.database.db_type == "postgresql"
        assert spec.auth.auth_type == "jwt"
        assert "google" in spec.auth.providers
        assert spec.deployment_target == "aws"
        assert len(spec.features) >= 5

    def test_tech_stack_generation(self):
        """Test tech stack array generation."""
        goal = "React app with Express and MongoDB"
        parser = RequirementsParser()
        spec = parser.parse(goal)

        tech_names = {tc.choice for tc in spec.tech_stack}

        assert "react" in tech_names
        assert "express" in tech_names
        assert "mongodb" in tech_names

    def test_database_none_when_not_needed(self):
        """Test database is None when not mentioned."""
        goal = "Simple static website"
        parser = RequirementsParser()
        spec = parser.parse(goal)

        assert spec.database is None

    def test_auth_none_when_not_needed(self):
        """Test auth is None when not mentioned."""
        goal = "Public blog with static content"
        parser = RequirementsParser()
        spec = parser.parse(goal)

        assert spec.auth is None

    def test_multiple_features_extraction(self):
        """Test extraction of multiple features."""
        goal = "App with auth, search, file upload, and analytics"
        parser = RequirementsParser()
        features = parser._extract_features(goal)

        feature_names = {f.name for f in features}

        assert "User Authentication" in feature_names
        assert "Search" in feature_names
        assert "File Upload/Storage" in feature_names
        assert "Analytics" in feature_names


# Integration tests
class TestRequirementsParserIntegration:
    """Integration tests for full workflows."""

    def test_end_to_end_app_generation_spec(self):
        """Test generating a complete app spec."""
        goal = """
        Create a "TaskFlow" project management tool
        - React dashboard with real-time updates
        - Express.js REST API
        - PostgreSQL for data storage
        - JWT-based user authentication
        - Email notifications
        - File attachments
        - Deploy to Heroku
        """

        spec = parse_goal(goal)

        # Verify complete spec
        assert spec.project_name == "TaskFlow"
        assert spec.frontend_framework == "react"
        assert spec.backend_framework == "express"
        assert spec.database.db_type == "postgresql"
        assert spec.auth.auth_type == "jwt"
        assert spec.deployment_target == "heroku"

        # Check tech stack is comprehensive
        assert len(spec.tech_stack) >= 4

        # Check features are identified
        assert len(spec.features) >= 3

        # Check effort is reasonable
        assert spec.estimated_effort_hours >= 30

    def test_full_spec_serialization(self):
        """Test serializing complete spec to JSON."""
        goal = "React + Node + Postgres app with auth"
        spec = parse_goal(goal)

        json_output = spec.to_json()

        # Verify JSON is valid and contains expected keys
        import json as json_module
        data = json_module.loads(json_output)

        assert "project_name" in data
        assert "features" in data
        assert "tech_stack" in data
        assert "database" in data
        assert "auth" in data
