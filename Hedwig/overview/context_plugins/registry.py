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

"""Registry for context plugins"""

from typing import Dict, Type, List, Optional
import logging

from .base import ContextPlugin


class ContextPluginRegistry:
    """Registry for managing context plugins"""

    # Registry of available plugins
    _plugins: Dict[str, Type[ContextPlugin]] = {}

    @classmethod
    def register(cls, name: str, plugin_class: Type[ContextPlugin]):
        """Register a context plugin

        Args:
            name: Unique name for the plugin
            plugin_class: The plugin class to register
        """
        if name in cls._plugins:
            raise ValueError(f"Plugin '{name}' is already registered")

        if not issubclass(plugin_class, ContextPlugin):
            raise TypeError("Plugin class must inherit from ContextPlugin")

        cls._plugins[name] = plugin_class

    @classmethod
    def get_plugin(cls, name: str) -> Type[ContextPlugin]:
        """Get a registered plugin by name

        Args:
            name: Plugin name

        Returns:
            Plugin class

        Raises:
            KeyError: If plugin is not registered
        """
        if name not in cls._plugins:
            raise KeyError(f"Plugin '{name}' is not registered")
        return cls._plugins[name]

    @classmethod
    def list_plugins(cls) -> List[str]:
        """List all registered plugin names

        Returns:
            List of plugin names
        """
        return list(cls._plugins.keys())

    @classmethod
    def create_plugins(cls, configs: Dict[str, Dict], logger: Optional[logging.Logger] = None) -> List[ContextPlugin]:
        """Create plugin instances from configuration

        Args:
            configs: Dictionary of plugin configurations keyed by plugin name
            logger: Optional logger instance

        Returns:
            List of initialized plugin instances
        """
        plugins = []

        for plugin_name, plugin_config in configs.items():
            if not plugin_config.get('enabled', True):
                continue

            try:
                plugin_class = cls.get_plugin(plugin_name)
                plugin_instance = plugin_class(plugin_config, logger)
                plugins.append(plugin_instance)
            except KeyError:
                if logger:
                    logger.warning(f"Unknown context plugin: {plugin_name}")
            except Exception as e:
                if logger:
                    logger.error(f"Failed to initialize plugin '{plugin_name}': {e}")

        return plugins