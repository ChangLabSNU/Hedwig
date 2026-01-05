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

"""Slack message consumer implementation"""

import os
from typing import Dict, Any, Optional, List, Callable

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..base import MessageConsumer, MessageContent, MessageResult
from ...utils.markdown_converter import MarkdownConverter, limit_text_length
from ...utils.logging import setup_logger


class SlackConsumer(MessageConsumer):
    """Slack implementation of message consumer"""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Slack consumer

        Args:
            config: Slack configuration including token and channel settings
        """
        super().__init__(config)

        # Initialize Slack client
        self.client = WebClient(token=self.token)
        quiet = self.config.get('quiet', False)
        self.logger = setup_logger('Hedwig.messaging.slack', quiet=quiet)

        # Set default channel
        self.default_channel = self.config.get('channel_id')
        self.post_details_in_canvas = self.config.get('post_details_in_canvas', True)
        self.post_details_link = self.config.get('post_details_link', '')

    def _validate_config(self) -> None:
        """Validate Slack configuration"""
        # Check for token
        self.token = self.config.get('token')
        if not self.token:
            # Try environment variable
            self.token = os.environ.get('SLACK_TOKEN')
            if not self.token:
                raise ValueError("Slack token not found in config or SLACK_TOKEN environment variable")

        # Get other settings with defaults
        self.header_max_length = self.config.get('header_max_length', 150)

    @property
    def name(self) -> str:
        """Get consumer name"""
        return "slack"

    @property
    def supports_documents(self) -> bool:
        """Slack supports Canvas documents"""
        return True

    def _build_message_blocks(self, content: MessageContent) -> List[Dict[str, Any]]:
        """Build Slack blocks for a message

        Args:
            content: Message content

        Returns:
            List of Slack blocks
        """
        blocks = [
            {
                'type': 'header',
                'text': {
                    'type': 'plain_text',
                    'text': limit_text_length(content.title, self.header_max_length)
                }
            }
        ]

        # Add markdown blocks
        blocks.extend(MarkdownConverter.to_slack_rich_text(content.notification_text))

        # Add document link if present in metadata
        doc_link_block = self._create_document_link_block(content.metadata)
        if doc_link_block:
            blocks.append(doc_link_block)

        return blocks

    def _create_document_link_block(self, metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Create a document link block from metadata

        Args:
            metadata: Message metadata

        Returns:
            Document link block or None
        """
        if not metadata:
            return None

        doc_url = metadata.get('document_url')
        doc_id = metadata.get('document_id')

        if not (doc_url or doc_id):
            return None

        if doc_url:
            link_text = f"\n<{doc_url}|View Timeline>"
        else:
            link_text = f"\n(Canvas created, ID: {doc_id})"

        return {
            'type': 'context',
            'elements': [
                {'type': 'mrkdwn', 'text': link_text}
            ]
        }

    def _handle_slack_operation(self, operation: Callable, operation_name: str, **kwargs) -> MessageResult:
        """Generic handler for Slack API operations with consistent error handling

        Args:
            operation: The Slack API operation to perform
            operation_name: Name of the operation for logging
            **kwargs: Arguments to pass to the operation

        Returns:
            MessageResult
        """
        try:
            response = operation(**kwargs)

            if response.get("ok"):
                self.logger.info(f"{operation_name} completed successfully")
                return MessageResult(
                    success=True,
                    message_id=response.get('ts') or response.get('canvas_id'),
                    metadata={'response': response.data}
                )
            else:
                error_msg = response.get('error', 'Unknown error')
                self.logger.error(f"{operation_name} failed: {error_msg}")
                return MessageResult(
                    success=False,
                    error=error_msg
                )

        except SlackApiError as e:
            error_msg = f"Slack API error: {e.response['error']}"
            self.logger.error(f"{operation_name} - {error_msg}")
            return MessageResult(
                success=False,
                error=error_msg
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"{operation_name} - {error_msg}")
            return MessageResult(
                success=False,
                error=error_msg
            )

    def send_message(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Send a message to Slack channel

        Args:
            content: Message content
            channel: Channel ID override

        Returns:
            MessageResult
        """
        channel_id = channel or self.default_channel
        if not channel_id:
            return MessageResult(
                success=False,
                error="No channel ID specified"
            )

        # Build message blocks
        blocks = self._build_message_blocks(content)

        # Send message using generic handler
        def send_operation():
            return self.client.chat_postMessage(
                channel=channel_id,
                text=content.notification_text,  # Fallback text
                blocks=blocks,
                unfurl_links=False,
                unfurl_media=False
            )

        result = self._handle_slack_operation(
            send_operation,
            f"Message send to {channel_id}"
        )

        if result.success:
            self.logger.info(f"Message sent successfully to {channel_id}")

        return result

    def send_with_document(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Send message with optional Canvas depending on configuration."""
        if not self.post_details_in_canvas:
            metadata = dict(content.metadata or {})
            details_link = (self.post_details_link or "").strip()
            if details_link:
                metadata["document_url"] = details_link

            message_content = MessageContent(
                title=content.title,
                markdown_content=content.markdown_content,
                notification_text=content.notification_text,
                metadata=metadata or None,
            )
            return self.send_message(message_content, channel)

        return super().send_with_document(content, channel)

    def send_document(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Create a Slack Canvas document

        Args:
            content: Document content
            channel: Channel ID for access permissions

        Returns:
            MessageResult with Canvas ID and URL
        """
        self.logger.info(f"Creating Canvas with title: {content.title}")

        # Convert markdown to Canvas format
        canvas_content = MarkdownConverter.to_slack_canvas(content.markdown_content)

        # Create Canvas using improved method
        result = self._create_canvas(content.title, canvas_content)

        if not result.success:
            return result

        canvas_id = result.message_id

        # Get Canvas permalink and set access
        canvas_url = self._get_canvas_permalink(canvas_id)

        channel_id = channel or self.default_channel
        if channel_id and canvas_id:
            self._set_canvas_access(canvas_id, [channel_id])

        # Update result with URL
        return MessageResult(
            success=True,
            message_id=canvas_id,
            url=canvas_url,
            metadata=result.metadata
        )

    def _create_canvas(self, title: str, content: str) -> MessageResult:
        """Create a Slack Canvas with fallback handling

        Args:
            title: Canvas title
            content: Canvas content

        Returns:
            MessageResult
        """
        canvas_payload = {
            "title": title,
            "document_content": {
                "type": "markdown",
                "markdown": content
            }
        }

        # Try new SDK method first
        try:
            def canvas_create_operation():
                return self.client.canvases_create(**canvas_payload)

            return self._handle_slack_operation(
                canvas_create_operation,
                "Canvas creation (SDK method)"
            )

        except AttributeError:
            # Fallback to API call
            self.logger.warning("canvases_create not found, using API call")

            def canvas_api_operation():
                return self.client.api_call("canvases.create", json=canvas_payload)

            return self._handle_slack_operation(
                canvas_api_operation,
                "Canvas creation (API call)"
            )

    def _get_canvas_permalink(self, canvas_id: str) -> Optional[str]:
        """Get permalink for a Canvas

        Args:
            canvas_id: Canvas ID

        Returns:
            Canvas permalink or None
        """
        try:
            response = self.client.files_info(file=canvas_id)
            if response.get("ok") and response.get("file"):
                permalink = response["file"].get("permalink")
                if permalink:
                    self.logger.info(f"Retrieved permalink: {permalink}")
                    return permalink
        except Exception as e:
            self.logger.warning(f"Error getting Canvas permalink: {e}")
        return None

    def _set_canvas_access(self, canvas_id: str, channel_ids: List[str]) -> bool:
        """Set Canvas access for channels

        Args:
            canvas_id: Canvas ID
            channel_ids: List of channel IDs

        Returns:
            True if successful, False otherwise
        """
        try:
            response = self.client.api_call(
                "canvases.access.set",
                json={
                    "canvas_id": canvas_id,
                    "access_level": "write",
                    "channel_ids": channel_ids
                }
            )

            if response.get("ok"):
                self.logger.info(f"Successfully set access for Canvas {canvas_id}")
                return True
            else:
                error_msg = response.get('error', 'Unknown error')
                self.logger.warning(f"Failed to set Canvas access: {error_msg}")
                return False
        except Exception as e:
            self.logger.warning(f"Error setting Canvas access: {e}")
            return False
