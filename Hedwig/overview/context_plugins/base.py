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

"""Base class for context plugins"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging


class ContextPlugin(ABC):
    """Abstract base class for context provider plugins

    Context plugins generate additional contextual information that gets
    inserted into the overview prompt before the language instruction.
    """

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """Initialize the context plugin

        Args:
            config: Plugin-specific configuration from config.yml
            logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.enabled = config.get('enabled', True)

    @abstractmethod
    def get_context(self) -> Optional[str]:
        """Generate context information to be included in the prompt

        Returns:
            Context string to be inserted into the prompt, or None if no context
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name identifier

        Returns:
            Unique name for this plugin
        """
        pass

    def is_enabled(self) -> bool:
        """Check if the plugin is enabled

        Returns:
            True if the plugin is enabled, False otherwise
        """
        return self.enabled