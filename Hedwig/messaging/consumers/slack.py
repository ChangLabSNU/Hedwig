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
from typing import Dict, Any, Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..base import MessageConsumer, MessageContent, MessageResult
from ...utils.markdown_converter import (
    markdown_to_slack_mrkdwn,
    markdown_to_slack_canvas,
    markdown_to_slack_rich_text,
    limit_text_length
)
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

        try:
            # Convert markdown to Slack format
            message_text = markdown_to_slack_mrkdwn(content.notification_text)

            # Build blocks
            blocks = [
                {
                    'type': 'header',
                    'text': {
                        'type': 'plain_text',
                        'text': limit_text_length(content.title, self.header_max_length)
                    }
                },
                markdown_to_slack_rich_text(message_text)
            ]

            # Add document link if present in metadata
            if content.metadata:
                doc_url = content.metadata.get('document_url')
                doc_id = content.metadata.get('document_id')

                if doc_url or doc_id:
                    if doc_url:
                        link_text = f"\n<{doc_url}|View Canvas>"
                    else:
                        link_text = f"\n(Canvas created, ID: {doc_id})"

                    blocks.append({
                        'type': 'context',
                        'elements': [
                            {'type': 'mrkdwn', 'text': link_text}
                        ]
                    })

            # Send message
            response = self.client.chat_postMessage(
                channel=channel_id,
                text=content.notification_text,  # Fallback text
                blocks=blocks,
                unfurl_links=False,
                unfurl_media=False
            )

            if response.get("ok"):
                self.logger.info(f"Message sent successfully to {channel_id}")
                return MessageResult(
                    success=True,
                    message_id=response.get('ts'),
                    metadata={'response': response.data}
                )
            else:
                error_msg = response.get('error', 'Unknown error')
                self.logger.error(f"Failed to send message: {error_msg}")
                return MessageResult(
                    success=False,
                    error=error_msg
                )

        except SlackApiError as e:
            self.logger.error(f"Slack API error: {e.response['error']}")
            return MessageResult(
                success=False,
                error=f"Slack API error: {e.response['error']}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return MessageResult(
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

    def send_document(self, content: MessageContent, channel: Optional[str] = None) -> MessageResult:
        """Create a Slack Canvas document

        Args:
            content: Document content
            channel: Channel ID for access permissions

        Returns:
            MessageResult with Canvas ID and URL
        """
        try:
            self.logger.info(f"Creating Canvas with title: {content.title}")

            # Convert markdown to Canvas format
            canvas_content = markdown_to_slack_canvas(content.markdown_content)

            # Create Canvas
            try:
                response = self.client.canvases_create(
                    title=content.title,
                    document_content={
                        "type": "markdown",
                        "markdown": canvas_content
                    }
                )
            except AttributeError:
                # Fallback to API call
                self.logger.warning("canvases_create not found, using API call")
                response = self.client.api_call(
                    "canvases.create",
                    json={
                        "title": content.title,
                        "document_content": {
                            "type": "markdown",
                            "markdown": canvas_content
                        }
                    }
                )

            if not response.get("ok"):
                error_msg = response.get('error', 'Unknown error')
                self.logger.error(f"Canvas creation failed: {error_msg}")
                return MessageResult(
                    success=False,
                    error=f"Canvas creation failed: {error_msg}"
                )

            canvas_id = response.get("canvas_id")
            self.logger.info(f"Canvas created successfully. ID: {canvas_id}")

            # Get Canvas permalink
            canvas_url = self._get_canvas_permalink(canvas_id)

            # Set Canvas access for channel
            channel_id = channel or self.default_channel
            if channel_id and canvas_id:
                self._set_canvas_access(canvas_id, [channel_id])

            return MessageResult(
                success=True,
                message_id=canvas_id,
                url=canvas_url,
                metadata={'canvas_response': response.data}
            )

        except SlackApiError as e:
            self.logger.error(f"Slack API error: {e.response['error']}")
            return MessageResult(
                success=False,
                error=f"Slack API error: {e.response['error']}"
            )
        except Exception as e:
            self.logger.error(f"Unexpected error: {e}")
            return MessageResult(
                success=False,
                error=f"Unexpected error: {str(e)}"
            )

    def _get_canvas_permalink(self, canvas_id: str) -> Optional[str]:
        """Get permalink for a Canvas"""
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

    def _set_canvas_access(self, canvas_id: str, channel_ids: list) -> bool:
        """Set Canvas access for channels"""
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
