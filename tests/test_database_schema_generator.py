"""Tests for DatabaseSchemaGenerator."""

import json
import tempfile
from pathlib import Path

import pytest

from kodo.database_schema_generator import (
    DatabaseSchemaGenerator,
    ColumnDefinition,
    TableDefinition,
    generate_database_schema,
)
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
def spec_with_auth():
    """Create a spec with authentication."""
    return Spec(
        project_name="AuthApp",
        description="App with authentication",
        features=[Feature("Users", "User management", requires_api=True)],
        tech_stack=[],
        database=DatabaseConfig(db_type="postgresql", orm_type="prisma"),
        auth=AuthConfig(auth_type="jwt"),
        frontend_framework=None,
        backend_framework="express",
        deployment_target=None,
    )


class TestDatabaseSchemaGenerator:
    """Test suite for DatabaseSchemaGenerator."""

    def test_generator_initialization(self):
        """Test DatabaseSchemaGenerator initialization."""
        gen = DatabaseSchemaGenerator("postgresql")
        assert gen.db_type == "postgresql"

    def test_generate_schema_creates_users_table(self, spec_with_auth):
        """Test that users table is created when auth is enabled."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)

        users_table = [t for t in tables if t.name == "users"]
        assert len(users_table) >= 1

    def test_users_table_has_required_columns(self, spec_with_auth):
        """Test that users table has required columns."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)

        users_table = tables[0]
        column_names = {col.name for col in users_table.columns}

        assert "id" in column_names
        assert "email" in column_names
        assert "password_hash" in column_names

    def test_column_definition_creation(self):
        """Test ColumnDefinition dataclass."""
        col = ColumnDefinition(
            "user_id",
            "string",
            required=True,
            unique=True,
            indexed=True,
        )

        assert col.name == "user_id"
        assert col.type == "string"
        assert col.required is True
        assert col.unique is True

    def test_table_definition_creation(self):
        """Test TableDefinition dataclass."""
        cols = [
            ColumnDefinition("id", "string"),
            ColumnDefinition("name", "string"),
        ]
        table = TableDefinition("users", "User table", cols)

        assert table.name == "users"
        assert len(table.columns) == 2
        assert table.timestamps is True

    def test_generate_postgresql_sql(self, spec_with_auth):
        """Test PostgreSQL SQL generation."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        sql = gen.generate_sql(tables)

        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "users" in sql
        assert "VARCHAR" in sql
        assert "TIMESTAMP" in sql

    def test_generate_mysql_sql(self, spec_with_auth):
        """Test MySQL SQL generation."""
        gen = DatabaseSchemaGenerator("mysql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        sql = gen.generate_sql(tables)

        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "`users`" in sql
        assert "VARCHAR" in sql or "INT" in sql

    def test_generate_sqlite_sql(self, spec_with_auth):
        """Test SQLite SQL generation."""
        gen = DatabaseSchemaGenerator("sqlite")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        sql = gen.generate_sql(tables)

        assert "CREATE TABLE IF NOT EXISTS" in sql
        assert "TEXT" in sql

    def test_migration_file_generation(self, temp_dir, spec_with_auth):
        """Test migration file generation."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        
        migrations_dir = temp_dir / "migrations"
        migrations_dir.mkdir()
        
        file_path = gen.generate_migration_file(tables, migrations_dir)

        assert Path(file_path).exists()
        assert "migration" not in Path(file_path).name.lower() or "_" in Path(file_path).name

    def test_prisma_schema_generation(self, spec_with_auth):
        """Test Prisma schema generation."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        schema = gen.generate_prisma_schema(tables)

        assert "datasource db" in schema
        assert "model User" in schema or "model Users" in schema
        assert "@id" in schema

    def test_mongodb_schema_generation(self, spec_with_auth):
        """Test MongoDB schema generation."""
        gen = DatabaseSchemaGenerator("mongodb")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        schemas = gen.generate_mongodb_schema(tables)

        assert "users" in schemas
        assert "validator" in schemas["users"]
        assert "$jsonSchema" in schemas["users"]["validator"]

    def test_feature_table_generation(self):
        """Test table generation from features."""
        spec = Spec(
            project_name="App",
            description="Test",
            features=[
                Feature("Products", "Product catalog", requires_api=True),
            ],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec)

        products_table = [t for t in tables if "product" in t.name]
        assert len(products_table) > 0

    def test_product_table_has_price_column(self):
        """Test that product tables have price column."""
        spec = Spec(
            project_name="Shop",
            description="E-commerce",
            features=[Feature("Products", "Items for sale", requires_api=True)],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec)

        products_table = tables[0]
        column_names = {col.name for col in products_table.columns}

        assert "price" in column_names

    def test_order_table_has_status(self):
        """Test that order tables have status column."""
        spec = Spec(
            project_name="Orders",
            description="Order management",
            features=[Feature("Orders", "Customer orders", requires_api=True)],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec)

        orders_table = tables[0]
        column_names = {col.name for col in orders_table.columns}

        assert "status" in column_names

    def test_sql_includes_indexes(self, spec_with_auth):
        """Test that SQL includes index creation."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        sql = gen.generate_sql(tables)

        # Emails are indexed, so should see CREATE INDEX
        assert "CREATE INDEX" in sql

    def test_sql_includes_timestamps(self, spec_with_auth):
        """Test that SQL includes timestamp columns."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        sql = gen.generate_sql(tables)

        assert "created_at" in sql.lower()
        assert "updated_at" in sql.lower()

    def test_type_mapping_postgresql(self):
        """Test PostgreSQL type mapping."""
        gen = DatabaseSchemaGenerator("postgresql")

        assert gen._get_postgres_type("string") == "VARCHAR(255)"
        assert gen._get_postgres_type("integer") == "INTEGER"
        assert gen._get_postgres_type("float") == "DECIMAL(10,2)"
        assert gen._get_postgres_type("boolean") == "BOOLEAN"

    def test_type_mapping_mysql(self):
        """Test MySQL type mapping."""
        gen = DatabaseSchemaGenerator("mysql")

        assert gen._get_mysql_type("string") == "VARCHAR(255)"
        assert gen._get_mysql_type("integer") == "INT"
        assert gen._get_mysql_type("float") == "DECIMAL(10,2)"

    def test_type_mapping_sqlite(self):
        """Test SQLite type mapping."""
        gen = DatabaseSchemaGenerator("sqlite")

        assert gen._get_sqlite_type("string") == "TEXT"
        assert gen._get_sqlite_type("integer") == "INTEGER"
        assert gen._get_sqlite_type("float") == "REAL"

    def test_prisma_type_mapping(self):
        """Test Prisma type mapping."""
        gen = DatabaseSchemaGenerator("postgresql")

        assert gen._get_prisma_type("string") == "String"
        assert gen._get_prisma_type("integer") == "Int"
        assert gen._get_prisma_type("boolean") == "Boolean"

    def test_mongodb_type_mapping(self):
        """Test MongoDB type mapping."""
        gen = DatabaseSchemaGenerator("mongodb")

        assert gen._get_mongodb_type("string") == "string"
        assert gen._get_mongodb_type("integer") == "int"
        assert gen._get_mongodb_type("float") == "double"
        assert gen._get_mongodb_type("boolean") == "bool"

    def test_pascal_case_conversion(self):
        """Test snake_case to PascalCase conversion."""
        gen = DatabaseSchemaGenerator("postgresql")

        assert gen._to_pascal_case("user_account") == "UserAccount"
        assert gen._to_pascal_case("product") == "Product"
        assert gen._to_pascal_case("order_item") == "OrderItem"

    def test_unsupported_db_type_raises_error(self):
        """Test that unsupported database type raises error."""
        gen = DatabaseSchemaGenerator("mongodb")
        tables = []

        with pytest.raises(ValueError):
            gen.generate_sql(tables)

    def test_multiple_tables_in_schema(self):
        """Test schema with multiple tables."""
        spec = Spec(
            project_name="Complex",
            description="Complex schema",
            features=[
                Feature("Users", "Users", requires_api=True),
                Feature("Products", "Products", requires_api=True),
                Feature("Orders", "Orders", requires_api=True),
            ],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec)

        assert len(tables) >= 4  # users + 3 features

    def test_convenience_function(self, temp_dir):
        """Test generate_database_schema convenience function."""
        spec = Spec(
            project_name="App",
            description="Test",
            features=[],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql", orm_type="prisma"),
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        generate_database_schema(spec, temp_dir)
        
        # Should have created migration directory
        assert (temp_dir / "migrations").exists()

    def test_prisma_schema_written_to_file(self, temp_dir):
        """Test that Prisma schema is written to file."""
        spec = Spec(
            project_name="App",
            description="Test",
            features=[],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql", orm_type="prisma"),
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        generate_database_schema(spec, temp_dir)

        prisma_file = temp_dir / "prisma" / "schema.prisma"
        assert prisma_file.exists()
        content = prisma_file.read_text()
        assert "model" in content

    def test_mongodb_schema_written_to_file(self, temp_dir):
        """Test that MongoDB schema is written to file."""
        spec = Spec(
            project_name="App",
            description="Test",
            features=[],
            tech_stack=[],
            database=DatabaseConfig(db_type="mongodb", orm_type="mongoose"),
            auth=None,
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        generate_database_schema(spec, temp_dir)

        mongo_file = temp_dir / "schemas" / "mongodb.json"
        assert mongo_file.exists()
        
        with open(mongo_file) as f:
            data = json.load(f)
            assert isinstance(data, dict)

    def test_column_with_default_value(self):
        """Test column with default value."""
        col = ColumnDefinition("is_active", "boolean", default="true")
        
        assert col.default == "true"

    def test_unique_constraint_in_sql(self, spec_with_auth):
        """Test that UNIQUE constraints are in SQL."""
        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec_with_auth)
        sql = gen.generate_sql(tables)

        assert "UNIQUE" in sql


class TestDatabaseSchemaGeneratorIntegration:
    """Integration tests for DatabaseSchemaGenerator."""

    def test_full_schema_generation_workflow(self, temp_dir):
        """Test complete schema generation workflow."""
        spec = Spec(
            project_name="ECommerce",
            description="E-commerce platform",
            features=[
                Feature("Users", "User accounts", requires_api=True),
                Feature("Products", "Product catalog", requires_api=True),
                Feature("Orders", "Order management", requires_api=True),
                Feature("Payments", "Payment processing", requires_api=True),
            ],
            tech_stack=[],
            database=DatabaseConfig(
                db_type="postgresql",
                orm_type="prisma",
                needs_migrations=True,
            ),
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        gen = DatabaseSchemaGenerator("postgresql")
        tables = gen.generate_schema_from_spec(spec)

        # Generate all outputs
        migrations_dir = temp_dir / "migrations"
        migrations_dir.mkdir()
        
        gen.generate_migration_file(tables, migrations_dir)
        sql = gen.generate_sql(tables)
        prisma = gen.generate_prisma_schema(tables)

        # Verify completeness
        assert len(tables) >= 5
        assert len(sql) > 0
        assert len(prisma) > 0
        assert (migrations_dir / "*.sql").parent.glob("*.sql").__next__().exists()

    def test_multiple_db_types_generation(self, temp_dir):
        """Test generating schema for multiple database types."""
        spec = Spec(
            project_name="MultiDB",
            description="Test",
            features=[Feature("Users", "Users", requires_api=True)],
            tech_stack=[],
            database=DatabaseConfig(db_type="postgresql"),
            auth=AuthConfig(auth_type="jwt"),
            frontend_framework=None,
            backend_framework="express",
            deployment_target=None,
        )

        for db_type in ["postgresql", "mysql", "sqlite"]:
            gen = DatabaseSchemaGenerator(db_type)
            tables = gen.generate_schema_from_spec(spec)
            sql = gen.generate_sql(tables)

            assert len(sql) > 0
            assert "users" in sql.lower()
