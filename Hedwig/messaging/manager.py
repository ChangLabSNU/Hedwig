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

"""Message manager for sending content through configured consumers"""

from typing import Optional

from .base import MessageContent, MessageResult
from .factory import MessageConsumerFactory
from ..utils.config import Config
from ..utils.logging import setup_logger


class MessageManager:
    """Manage sending messages through configured consumers"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize message manager

        Args:
            config_path: Path to configuration file
        """
        self.config = Config(config_path)
        self.consumer = MessageConsumerFactory.create_from_config(self.config)
        self.logger = setup_logger('Hedwig.messaging.manager')

        if not self.consumer:
            self.logger.warning("No message consumer configured")

    def post_summary(self, markdown_file: str, message_file: str, title: str,
                    channel_override: Optional[str] = None) -> MessageResult:
        """Post a summary with notification

        Args:
            markdown_file: Path to markdown file for summary content
            message_file: Path to file with notification message
            title: Summary title
            channel_override: Optional channel/destination override

        Returns:
            MessageResult

        Raises:
            FileNotFoundError: If input files not found
            RuntimeError: If no consumer configured
        """
        return self.upload_document(markdown_file, message_file, title, channel_override)

    def upload_document(self, markdown_file: str, message_file: str, title: str,
                       channel_override: Optional[str] = None) -> MessageResult:
        """Upload a document with notification (deprecated, use post_summary)

        Args:
            markdown_file: Path to markdown file for document content
            message_file: Path to file with notification message
            title: Document title
            channel_override: Optional channel/destination override

        Returns:
            MessageResult

        Raises:
            FileNotFoundError: If input files not found
            RuntimeError: If no consumer configured
        """
        if not self.consumer:
            raise RuntimeError("No message consumer configured")

        # Read markdown content
        try:
            with open(markdown_file, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            self.logger.info(f"Read markdown file: {markdown_file}")
        except FileNotFoundError:
            self.logger.error(f"Markdown file not found: {markdown_file}")
            raise

        # Read notification message
        try:
            with open(message_file, 'r', encoding='utf-8') as f:
                notification_text = f.read().strip()
            self.logger.info(f"Read message file: {message_file}")
        except FileNotFoundError:
            self.logger.error(f"Message file not found: {message_file}")
            raise

        # Process title from notification if needed
        if notification_text:
            first_line = notification_text.splitlines()[0]
            if not first_line.startswith('* '):
                title += ': ' + first_line.strip('*').strip('#').strip()
                notification_text = '\n'.join(notification_text.splitlines()[1:]).strip()

        # Create message content
        content = MessageContent(
            title=title,
            markdown_content=markdown_content,
            notification_text=notification_text
        )

        # Send through consumer
        self.logger.info(f"Posting summary through {self.consumer.name} consumer")
        result = self.consumer.send_with_document(content, channel_override)

        if result.success:
            self.logger.info(f"Successfully posted summary: {result.message_id}")
            if result.url:
                self.logger.info(f"Summary URL: {result.url}")
        else:
            self.logger.error(f"Failed to post summary: {result.error}")

        return result

    def send_message(self, title: str, message: str, channel_override: Optional[str] = None) -> MessageResult:
        """Send a simple message

        Args:
            title: Message title
            message: Message content
            channel_override: Optional channel/destination override

        Returns:
            MessageResult

        Raises:
            RuntimeError: If no consumer configured
        """
        if not self.consumer:
            raise RuntimeError("No message consumer configured")

        content = MessageContent(
            title=title,
            markdown_content=message,
            notification_text=message
        )

        self.logger.info(f"Sending message through {self.consumer.name} consumer")
        result = self.consumer.send_message(content, channel_override)

        if result.success:
            self.logger.info(f"Successfully sent message: {result.message_id}")
        else:
            self.logger.error(f"Failed to send message: {result.error}")

        return result

    @property
    def consumer_name(self) -> Optional[str]:
        """Get the name of the active consumer"""
        return self.consumer.name if self.consumer else None

    @property
    def supports_documents(self) -> bool:
        """Check if the active consumer supports documents"""
        return self.consumer.supports_documents if self.consumer else False
