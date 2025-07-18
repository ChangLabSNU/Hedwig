"""Static context plugin for providing fixed context information."""

from typing import Optional

from .base import ContextPlugin
from .registry import ContextPluginRegistry


class StaticContextPlugin(ContextPlugin):
    """Context plugin that provides static information from configuration."""

    @property
    def name(self) -> str:
        return "static"

    def get_context(self) -> Optional[str]:
        """Return the static context content from configuration.

        Returns:
            The configured static content string, or None if not configured
        """
        if not self.enabled:
            return None

        content = self.config.get('content', '').strip()
        if not content:
            return None

        return content


# Register the plugin
ContextPluginRegistry.register("static", StaticContextPlugin)