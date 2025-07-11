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

"""Factory for creating message consumers based on configuration"""

from typing import Dict, Any, Optional, List
import importlib

from .base import MessageConsumer
from ..utils.config import Config


class MessageConsumerFactory:
    """Factory for creating message consumers"""

    # Registry of available consumers
    CONSUMER_REGISTRY = {
        'slack': 'Hedwig.messaging.consumers.slack.SlackConsumer',
    }

    @classmethod
    def create_consumer(cls, consumer_type: str, config: Dict[str, Any], quiet: bool = False) -> MessageConsumer:
        """Create a message consumer instance

        Args:
            consumer_type: Type of consumer (e.g., 'slack')
            config: Configuration for the consumer
            quiet: Suppress informational messages

        Returns:
            MessageConsumer instance

        Raises:
            ValueError: If consumer type is not supported
            ImportError: If consumer module cannot be imported
        """
        if consumer_type not in cls.CONSUMER_REGISTRY:
            available = ', '.join(cls.CONSUMER_REGISTRY.keys())
            raise ValueError(
                f"Unsupported consumer type: {consumer_type}. "
                f"Available types: {available}"
            )

        # Get the class path
        class_path = cls.CONSUMER_REGISTRY[consumer_type]

        # Import the module and class
        module_path, class_name = class_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        consumer_class = getattr(module, class_name)

        # Add quiet flag to config
        config_with_quiet = config.copy()
        config_with_quiet['quiet'] = quiet

        # Create and return instance
        return consumer_class(config_with_quiet)

    @classmethod
    def create_from_config(cls, config: Config, quiet: bool = False) -> Optional[MessageConsumer]:
        """Create a message consumer from configuration

        Args:
            config: Configuration object
            quiet: Suppress informational messages

        Returns:
            MessageConsumer instance or None if messaging not configured
        """
        messaging_config = config.get('messaging', {})
        if not messaging_config:
            return None

        # Get the active consumer
        active_consumer = messaging_config.get('active')
        if not active_consumer:
            return None

        # Get consumer-specific config
        consumer_config = messaging_config.get(active_consumer, {})

        return cls.create_consumer(active_consumer, consumer_config, quiet=quiet)

    @classmethod
    def list_available_consumers(cls) -> List[str]:
        """List available consumer types

        Returns:
            List of consumer type names
        """
        return list(cls.CONSUMER_REGISTRY.keys())

    @classmethod
    def register_consumer(cls, consumer_type: str, class_path: str) -> None:
        """Register a new consumer type

        Args:
            consumer_type: Type identifier for the consumer
            class_path: Full module path to the consumer class
        """
        cls.CONSUMER_REGISTRY[consumer_type] = class_path
