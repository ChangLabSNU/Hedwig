#
# Copyright (c) 2025 Seoul National University
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Configuration management for Hedwig"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class Config:
    """Configuration manager for Hedwig"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration from YAML file

        Args:
            config_path: Path to configuration file. If None, looks for config.yml
                        in common locations.
        """
        self.config_path = self._find_config_file(config_path)
        self.data = self._load_config()

    def _find_config_file(self, config_path: Optional[str]) -> Path:
        """Find configuration file in various locations"""
        if config_path:
            path = Path(config_path)
            if path.exists():
                return path
            raise FileNotFoundError(f"Config file not found: {config_path}")

        # Look for config in common locations
        search_paths = [
            Path.cwd() / "config.yml",
            Path.cwd() / "qbio" / "config.yml",
            Path.home() / ".config" / "hedwig" / "config.yml",
            Path("/etc/hedwig/config.yml"),
        ]

        for path in search_paths:
            if path.exists():
                return path

        raise FileNotFoundError(
            "No config.yml found. Searched in: " +
            ", ".join(str(p) for p in search_paths)
        )

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation

        Args:
            key: Configuration key (e.g., 'notion.api_key')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def __getitem__(self, key: str) -> Any:
        """Get configuration section"""
        return self.data[key]

    @property
    def notion(self) -> Dict[str, Any]:
        """Get Notion configuration section (now under api.notion)"""
        # Support both new and old structure
        api_config = self.data.get('api', {})
        if 'notion' in api_config:
            return api_config['notion']
        # Fallback to old structure
        return self.data.get('notion', {})

    @property
    def sync(self) -> Dict[str, Any]:
        """Get sync configuration section"""
        return self.data.get('sync', {})

    @property
    def output(self) -> Dict[str, Any]:
        """Get output configuration section"""
        return self.data.get('output', {})

    @property
    def markdown(self) -> Dict[str, Any]:
        """Get markdown configuration section"""
        return self.data.get('markdown', {})

    @property
    def git(self) -> Dict[str, Any]:
        """Get git configuration section"""
        return self.data.get('git', {})
