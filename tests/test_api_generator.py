"""Tests for ApiGenerator."""

import json
import tempfile
from pathlib import Path

import pytest

from kodo.api_generator import ApiGenerator, ApiRoute, generate_api
from kodo.requirements_parser import (
    Spec,
    Feature,
    DatabaseConfig,
    AuthConfig,
    TechStackChoice,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def basic_spec():
    """Create a basic test specification."""
    return Spec(
        project_name="TestAPI",
        description="A test API",
        features=[
            Feature("User Authentication", "Login and user accounts", requires_api=True),
            Feature("Dashboard", "Main dashboard view", requires_api=True),
        ],
        tech_stack=[
            TechStackChoice("backend", "express"),
        ],
        database=DatabaseConfig(db_type="postgresql"),
        auth=AuthConfig(auth_type="jwt"),
        frontend_framework=None,
        backend_framework="express",
        deployment_target="docker",
    )


class TestApiGenerator:
    """Test suite for ApiGenerator."""

    def test_generator_initialization(self):
        """Test ApiGenerator can be initialized."""
        gen = ApiGenerator("express")
        assert gen.framework == "express"

    def test_generate_routes_health_check(self, basic_spec):
        """Test that health check route is always generated."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)

        health_routes = [r for r in routes if r.path == "/health"]
        assert len(health_routes) == 1
        assert health_routes[0].method == "GET"
        assert health_routes[0].authentication_required is False

    def test_generate_routes_with_jwt_auth(self, basic_spec):
        """Test that JWT routes are generated."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)

        paths = {r.path for r in routes}
        assert "/auth/register" in paths
        assert "/auth/login" in paths
        assert "/auth/profile" in paths

    def test_generate_routes_with_oauth_providers(self):
        """Test that OAuth provider routes are generated."""
        spec = Spec(
            project_name="OAuthApp",
            description="OAuth test app",
            features=[],
            tech_stack=[],
            database=None,
            auth=AuthConfig(auth_type="oauth2", providers=["google", "github"]),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(spec)

        paths = {r.path for r in routes}
        assert "/auth/google/callback" in paths
        assert "/auth/github/callback" in paths

    def test_generate_routes_for_features(self, basic_spec):
        """Test that CRUD routes are generated for features."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)

        # Should have routes for the features
        paths = {r.path for r in routes}

        # Should have multiple routes (health, auth, features)
        assert len(routes) > 5

    def test_api_route_dataclass(self):
        """Test ApiRoute dataclass creation."""
        route = ApiRoute(
            path="/users",
            method="GET",
            name="list_users",
            description="List all users",
        )

        assert route.path == "/users"
        assert route.method == "GET"
        assert route.authentication_required is True

    def test_api_route_with_request_body(self):
        """Test ApiRoute with request body schema."""
        route = ApiRoute(
            path="/users",
            method="POST",
            name="create_user",
            description="Create user",
            request_body={"name": "string", "email": "string"},
        )

        assert route.request_body is not None
        assert "name" in route.request_body

    def test_generate_express_code(self, temp_dir, basic_spec):
        """Test Express code generation."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)
        code = gen.generate_code(routes, temp_dir / "routes.ts")

        assert code is not None
        assert "express" in code
        assert "Router" in code
        assert "router.get" in code or "router.post" in code

    def test_generate_express_code_writes_file(self, temp_dir, basic_spec):
        """Test that Express code is written to file."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)
        gen.generate_code(routes, temp_dir / "routes.ts")

        route_file = temp_dir / "routes.ts"
        assert route_file.exists()
        content = route_file.read_text()
        assert len(content) > 0

    def test_generate_fastapi_code(self, temp_dir, basic_spec):
        """Test FastAPI code generation."""
        gen = ApiGenerator("fastapi")
        routes = gen.generate_routes_from_spec(basic_spec)
        code = gen.generate_code(routes, temp_dir / "routes.py")

        assert code is not None
        assert "fastapi" in code or "APIRouter" in code
        assert "@router" in code

    def test_generate_django_code(self, temp_dir, basic_spec):
        """Test Django code generation."""
        gen = ApiGenerator("django")
        routes = gen.generate_routes_from_spec(basic_spec)
        code = gen.generate_code(routes, temp_dir / "views.py")

        assert code is not None
        assert "JsonResponse" in code
        assert "@require_http_methods" in code

    def test_generate_schema_json(self, temp_dir, basic_spec):
        """Test OpenAPI schema generation."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)
        schema = gen.generate_schema_json(routes, temp_dir / "openapi.json")

        # Verify it's valid JSON
        schema_data = json.loads(schema)
        assert "openapi" in schema_data
        assert schema_data["openapi"] == "3.0.0"
        assert "paths" in schema_data

    def test_schema_includes_all_routes(self, temp_dir, basic_spec):
        """Test that schema includes all routes."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(basic_spec)
        schema = gen.generate_schema_json(routes, temp_dir / "openapi.json")

        schema_data = json.loads(schema)
        paths = schema_data["paths"]

        # Should have /health
        assert "/health" in paths

        # Should have /auth routes
        assert any("/auth" in path for path in paths)

    def test_schema_includes_descriptions(self, temp_dir, basic_spec):
        """Test that schema includes descriptions."""
        gen = ApiGenerator("express")
        routes = [
            ApiRoute(
                path="/test",
                method="GET",
                name="test_route",
                description="This is a test route",
            )
        ]

        schema = gen.generate_schema_json(routes, temp_dir / "openapi.json")
        schema_data = json.loads(schema)

        assert schema_data["paths"]["/test"]["get"]["description"] == "This is a test route"

    def test_unsupported_framework_raises_error(self, temp_dir):
        """Test that unsupported framework raises error."""
        gen = ApiGenerator("unsupported")
        routes = [
            ApiRoute(
                path="/test",
                method="GET",
                name="test",
                description="test",
            )
        ]

        with pytest.raises(ValueError):
            gen.generate_code(routes, temp_dir / "test.ts")

    def test_generate_api_convenience_function(self, temp_dir):
        """Test generate_api convenience function."""
        spec = Spec(
            project_name="ConvApp",
            description="Convenience test",
            features=[Feature("Users", "User management")],
            tech_stack=[],
            database=None,
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        output_dir = temp_dir / "src" / "api"
        output_dir.mkdir(parents=True)

        generate_api(spec, output_dir)

        assert (output_dir / "routes.ts").exists()
        assert (output_dir / "openapi.json").exists()

    def test_routes_without_auth_marked_correctly(self):
        """Test that health check doesn't require auth."""
        gen = ApiGenerator("express")
        routes = gen.generate_routes_from_spec(
            Spec(
                project_name="App",
                description="Test",
                features=[],
                tech_stack=[],
                database=None,
                auth=None,
                frontend_framework=None,
                backend_framework="express",
                deployment_target=None,
            )
        )

        health = [r for r in routes if r.path == "/health"][0]
        assert health.authentication_required is False

    def test_express_route_with_authentication(self, temp_dir):
        """Test that Express route includes auth middleware."""
        gen = ApiGenerator("express")
        route = ApiRoute(
            path="/protected",
            method="GET",
            name="protected_route",
            description="Protected route",
            authentication_required=True,
        )

        code = gen._generate_express_route(route)
        assert "authenticate" in code

    def test_express_route_without_authentication(self, temp_dir):
        """Test that Express route without auth doesn't include middleware."""
        gen = ApiGenerator("express")
        route = ApiRoute(
            path="/public",
            method="GET",
            name="public_route",
            description="Public route",
            authentication_required=False,
        )

        code = gen._generate_express_route(route)
        assert "authenticate" not in code

    def test_fastapi_route_generation(self, temp_dir):
        """Test FastAPI route code generation."""
        gen = ApiGenerator("fastapi")
        route = ApiRoute(
            path="/items",
            method="GET",
            name="list_items",
            description="List all items",
        )

        code = gen._generate_fastapi_route(route)
        assert "@router.get" in code
        assert "list_items" in code

    def test_django_view_generation(self, temp_dir):
        """Test Django view code generation."""
        gen = ApiGenerator("django")
        route = ApiRoute(
            path="/items",
            method="GET",
            name="list_items",
            description="List all items",
        )

        code = gen._generate_django_view(route)
        assert "def list_items" in code
        assert "@require_http_methods" in code

    def test_schema_includes_request_body(self, temp_dir):
        """Test that schema includes request body when specified."""
        gen = ApiGenerator("express")
        route = ApiRoute(
            path="/users",
            method="POST",
            name="create_user",
            description="Create user",
            request_body={"email": "string", "name": "string"},
        )

        schema = gen.generate_schema_json([route], temp_dir / "schema.json")
        schema_data = json.loads(schema)

        # Check that request body is in schema
        assert "requestBody" in schema_data["paths"]["/users"]["post"]

    def test_multiple_routes_in_schema(self, temp_dir):
        """Test schema with multiple routes."""
        gen = ApiGenerator("express")
        routes = [
            ApiRoute("/users", "GET", "list_users", "List users"),
            ApiRoute("/users", "POST", "create_user", "Create user"),
            ApiRoute("/users/{id}", "GET", "get_user", "Get user"),
            ApiRoute("/items", "GET", "list_items", "List items"),
        ]

        schema = gen.generate_schema_json(routes, temp_dir / "schema.json")
        schema_data = json.loads(schema)

        assert "/users" in schema_data["paths"]
        assert "/users/{id}" in schema_data["paths"]
        assert "/items" in schema_data["paths"]

        # Check that different methods are under same path
        assert "get" in schema_data["paths"]["/users"]
        assert "post" in schema_data["paths"]["/users"]


class TestApiGeneratorIntegration:
    """Integration tests for ApiGenerator."""

    def test_full_api_generation_workflow(self, temp_dir):
        """Test full API generation workflow."""
        spec = Spec(
            project_name="FullAPI",
            description="Complete API generation test",
            features=[
                Feature("Users", "User management", requires_api=True),
                Feature("Products", "Product catalog", requires_api=True),
                Feature("Orders", "Order management", requires_api=True),
            ],
            tech_stack=[
                TechStackChoice("backend", "express"),
            ],
            database=DatabaseConfig(db_type="postgresql"),
            auth=AuthConfig(auth_type="jwt", providers=["google"]),
            frontend_framework=None,
            backend_framework="express",
            deployment_target="docker",
        )

        api_dir = temp_dir / "src" / "api"
        api_dir.mkdir(parents=True)

        # Generate API
        generate_api(spec, api_dir, "express")

        # Verify files created
        assert (api_dir / "routes.ts").exists()
        assert (api_dir / "openapi.json").exists()

        # Verify code quality
        routes_code = (api_dir / "routes.ts").read_text()
        assert "express" in routes_code
        assert "router" in routes_code

        # Verify schema quality
        schema_data = json.loads((api_dir / "openapi.json").read_text())
        assert schema_data["info"]["title"] == "Generated API"
        assert len(schema_data["paths"]) > 5

    def test_api_generation_for_multiple_frameworks(self, temp_dir):
        """Test generating API for different frameworks."""
        spec = Spec(
            project_name="MultiFramework",
            description="Multi-framework test",
            features=[Feature("Items", "Item management", requires_api=True)],
            tech_stack=[],
            database=None,
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        for framework in ["express", "fastapi", "django"]:
            gen = ApiGenerator(framework)
            routes = gen.generate_routes_from_spec(spec)
            assert len(routes) > 0
