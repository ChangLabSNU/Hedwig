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

"""Base classes for message consumers"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class MessageContent:
    """Content to be sent through message consumer"""
    title: str
    markdown_content: str
    notification_text: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class MessageResult:
    """Result of sending a message"""
    success: bool
    message_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MessageConsumer(ABC):
    """Abstract base class for message consumers"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize message consumer with configuration

        Args:
            config: Configuration dictionary for this consumer
        """
        self.config = config
        self._validate_config()

    @abstractmethod
    def _validate_config(self) -> None:
        """Validate configuration for this consumer

        Raises:
            ValueError: If configuration is invalid
        """
        pass

    @abstractmethod
    def send_message(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Send a message through this consumer

        Args:
            content: Message content to send
            channel: Optional channel/destination override

        Returns:
            MessageResult indicating success/failure and any metadata
        """
        pass

    @abstractmethod
    def send_document(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Send a document (like Canvas) through this consumer

        Args:
            content: Document content to send
            channel: Optional channel/destination override

        Returns:
            MessageResult with document ID and URL if applicable
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of this consumer"""
        pass

    @property
    @abstractmethod
    def supports_documents(self) -> bool:
        """Check if this consumer supports document creation"""
        pass

    def send_with_document(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Send a document and notification message

        Args:
            content: Content to send
            channel: Optional channel/destination override

        Returns:
            Combined MessageResult
        """
        if not self.supports_documents:
            # Fallback to simple message if documents not supported
            return self.send_message(content, channel)

        # First create document
        doc_result = self.send_document(content, channel)
        if not doc_result.success:
            return doc_result

        # Then send notification with document link
        notification_content = MessageContent(
            title=content.title,
            markdown_content=content.notification_text,
            notification_text=content.notification_text,
            metadata={
                'document_id': doc_result.message_id,
                'document_url': doc_result.url,
                **(content.metadata or {})
            }
        )

        msg_result = self.send_message(notification_content, channel)

        # Combine results
        return MessageResult(
            success=msg_result.success,
            message_id=doc_result.message_id,
            url=doc_result.url,
            error=msg_result.error,
            metadata={
                'document': doc_result.metadata,
                'message': msg_result.metadata
            }
        )
