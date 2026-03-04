"""Tests for config loading integration with validation."""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kodo.team_config import load_team_config, _load_json
from kodo.schemas import TeamConfigSchema


class TestConfigLoading:
    """Test config loading with validation."""
    
    def test_load_valid_team_config(self):
        """Load a valid team config from JSON."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test-team",
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "opus",
                        "description": "Smart worker",
                        "max_turns": 30,
                    },
                },
            }))
            
            result = _load_json(config_path)
            
            assert result["name"] == "test-team"
            assert "worker" in result["agents"]
            assert result["agents"]["worker"]["backend"] == "claude"
    
    def test_load_minimal_team_config(self):
        """Load team config with minimal required fields."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "minimal",
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "sonnet",
                    },
                },
            }))
            
            result = _load_json(config_path)
            
            assert result["name"] == "minimal"
            assert result["agents"]["worker"]["model"] == "sonnet"
            # Defaults should be filled in
            assert result["agents"]["worker"]["max_turns"] == 15
    
    def test_invalid_json_raises_error(self):
        """Invalid JSON raises clear error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text("{ invalid json }")
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid JSON" in str(exc_info.value)
    
    def test_missing_name_raises_error(self):
        """Missing name field raises validation error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "opus",
                    },
                },
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid team config" in str(exc_info.value)
    
    def test_missing_agents_raises_error(self):
        """Missing agents field raises validation error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test",
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid team config" in str(exc_info.value)
    
    def test_empty_agents_raises_error(self):
        """Empty agents dict raises validation error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test",
                "agents": {},
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid team config" in str(exc_info.value)
            assert "at least one agent" in str(exc_info.value).lower()
    
    def test_invalid_backend_raises_error(self):
        """Invalid backend raises validation error with suggestion."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test",
                "agents": {
                    "worker": {
                        "backend": "invalid-backend",
                        "model": "opus",
                    },
                },
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            error_msg = str(exc_info.value).lower()
            assert "invalid team config" in error_msg or "backend" in error_msg
    
    def test_missing_model_raises_error(self):
        """Missing model field raises validation error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test",
                "agents": {
                    "worker": {
                        "backend": "claude",
                    },
                },
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid team config" in str(exc_info.value)
    
    def test_invalid_max_turns_raises_error(self):
        """Invalid max_turns value raises validation error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test",
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "opus",
                        "max_turns": 0,  # Invalid: must be >= 1
                    },
                },
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid team config" in str(exc_info.value)
    
    def test_invalid_timeout_raises_error(self):
        """Invalid timeout_s value raises validation error."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "test",
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "opus",
                        "timeout_s": 5,  # Invalid: must be >= 10
                    },
                },
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            assert "Invalid team config" in str(exc_info.value)
    
    def test_detailed_error_messages(self):
        """Error messages include path and field info."""
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "team.json"
            config_path.write_text(json.dumps({
                "name": "",  # Empty name
                "agents": {},  # Empty agents
            }))
            
            with pytest.raises(ValueError) as exc_info:
                _load_json(config_path)
            
            error_msg = str(exc_info.value)
            assert "Invalid team config" in error_msg
            # Should mention the file path
            assert str(config_path) in error_msg or "team.json" in error_msg


class TestLoadTeamConfigLookup:
    """Test config file lookup priority."""
    
    def test_load_team_config_not_found(self):
        """load_team_config returns None if config not found."""
        with TemporaryDirectory() as tmpdir:
            result = load_team_config("nonexistent", Path(tmpdir))
            assert result is None
    
    def test_load_team_config_from_project_dir(self):
        """load_team_config finds config in project .kodo/ dir."""
        with TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)
            kodo_dir = project_dir / ".kodo"
            kodo_dir.mkdir()
            
            team_file = kodo_dir / "team.json"
            team_file.write_text(json.dumps({
                "name": "project-team",
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "opus",
                    },
                },
            }))
            
            result = load_team_config("test", project_dir)
            
            assert result is not None
            assert result["name"] == "project-team"
    
    def test_load_team_config_from_user_dir(self):
        """load_team_config finds config in ~/.kodo/teams/ dir."""
        with TemporaryDirectory() as tmpdir:
            home_dir = Path(tmpdir)
            teams_dir = home_dir / ".kodo" / "teams"
            teams_dir.mkdir(parents=True)
            
            team_file = teams_dir / "my-team.json"
            team_file.write_text(json.dumps({
                "name": "my-team",
                "agents": {
                    "worker": {
                        "backend": "claude",
                        "model": "opus",
                    },
                },
            }))
            
            # Mock Path.home() to return our temp directory
            with patch('pathlib.Path.home', return_value=home_dir):
                result = load_team_config("my-team", Path("/other"))
                
                assert result is not None
                assert result["name"] == "my-team"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
