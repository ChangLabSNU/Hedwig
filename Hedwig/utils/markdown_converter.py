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

"""Markdown to Slack format converter"""

import re
import json
from typing import List, Dict, Any, Union, Tuple, Optional


class MarkdownConverter:
    """Converter for transforming Markdown to various Slack formats"""

    @staticmethod
    def _is_divider(line: str) -> bool:
        """Check if a line is a markdown horizontal rule/divider."""
        stripped = line.strip()
        return bool(re.match(r'^(---+|\*\*\*+|___+)$', stripped))

    @staticmethod
    def _parse_inline_formatting(text: str) -> List[Dict[str, Any]]:
        """Parse inline formatting (bold, italic, and code) in a text string."""
        elements = []

        # Combined pattern to match:
        # - Bold: **text** or __text__
        # - Italic: *text* or _text_ (but not ** or __)
        # - Code: `text`
        pattern = r'(\*\*|__|(?<!\*)\*(?!\*)|(?<!_)_(?!_)|`)(.+?)\1'
        last_end = 0

        for match in re.finditer(pattern, text):
            # Add any plain text before the match
            if match.start() > last_end:
                plain_text = text[last_end:match.start()]
                if plain_text:
                    elements.append({
                        "type": "text",
                        "text": plain_text
                    })

            # Add the formatted text
            delimiter = match.group(1)
            content = match.group(2)

            if delimiter == '`':
                # Code formatting
                elements.append({
                    "type": "text",
                    "text": content,
                    "style": {
                        "code": True
                    }
                })
            elif delimiter in ['**', '__']:
                # Bold formatting
                elements.append({
                    "type": "text",
                    "text": content,
                    "style": {
                        "bold": True
                    }
                })
            elif delimiter in ['*', '_']:
                # Italic formatting
                elements.append({
                    "type": "text",
                    "text": content,
                    "style": {
                        "italic": True
                    }
                })

            last_end = match.end()

        # Add any remaining plain text
        if last_end < len(text):
            remaining_text = text[last_end:]
            if remaining_text:
                elements.append({
                    "type": "text",
                    "text": remaining_text
                })

        # If no formatting was found, return the entire text as plain
        if not elements:
            elements.append({
                "type": "text",
                "text": text
            })

        return elements

    @staticmethod
    def _is_list_item(line: str) -> Tuple[bool, int, str]:
        """
        Check if a line is a list item and return its properties.
        Returns (is_list_item, indent_level, content)
        """
        match = re.match(r'^(\s*)[-*]\s+(.*)$', line)
        if match:
            indent = match.group(1)
            content = match.group(2).strip()
            # Calculate indent level (4 spaces or 1 tab = 1 level)
            indent_level = len(indent.replace('\t', '    ')) // 4
            return True, indent_level, content
        return False, 0, line

    @classmethod
    def _create_paragraph_section(cls, lines: List[str]) -> Dict[str, Any]:
        """Create a paragraph section from lines of text."""
        combined_text = ' '.join(lines)
        elements = cls._parse_inline_formatting(combined_text)

        return {
            "type": "rich_text_section",
            "elements": elements
        }

    @classmethod
    def _create_list_section(cls, items: List[Tuple[int, str]]) -> List[Dict[str, Any]]:
        """
        Create list sections from items with indentation levels.
        Returns a list of sections (lists at different indent levels).
        """
        if not items:
            return []

        result_sections = []
        current_level_items = []
        current_level = 0

        # Group items by consecutive same-level items
        for indent_level, content in items:
            if not current_level_items or indent_level == current_level:
                current_level = indent_level
                current_level_items.append(content)
            else:
                # Flush current level items
                if current_level_items:
                    list_elements = []
                    for item_text in current_level_items:
                        item_elements = cls._parse_inline_formatting(item_text)
                        list_elements.append({
                            "type": "rich_text_section",
                            "elements": item_elements
                        })

                    list_block = {
                        "type": "rich_text_list",
                        "style": "bullet",
                        "elements": list_elements
                    }

                    if current_level > 0:
                        list_block["indent"] = current_level

                    result_sections.append(list_block)

                # Start new level
                current_level = indent_level
                current_level_items = [content]

        # Don't forget the last group
        if current_level_items:
            list_elements = []
            for item_text in current_level_items:
                item_elements = cls._parse_inline_formatting(item_text)
                list_elements.append({
                    "type": "rich_text_section",
                    "elements": item_elements
                })

            list_block = {
                "type": "rich_text_list",
                "style": "bullet",
                "elements": list_elements
            }

            if current_level > 0:
                list_block["indent"] = current_level

            result_sections.append(list_block)

        return result_sections

    @classmethod
    def _create_heading_section(cls, line: str) -> Optional[Dict[str, Any]]:
        """Create a heading section from a markdown heading."""
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not match:
            return None

        heading_text = match.group(2).strip()

        # Parse inline formatting in the heading text
        elements = cls._parse_inline_formatting(heading_text)

        # Add bold style to all elements for heading emphasis
        for element in elements:
            if element.get("type") == "text":
                if "style" in element:
                    element["style"]["bold"] = True
                else:
                    element["style"] = {"bold": True}

        return {
            "type": "rich_text_section",
            "elements": elements
        }

    @classmethod
    def _process_rich_text_segment(cls, lines: List[str]) -> List[Dict[str, Any]]:
        """
        Process a segment of lines (without dividers) into rich_text elements.

        Args:
            lines: List of markdown lines to process

        Returns:
            List of rich_text elements (sections, lists, etc.)
        """
        sections = []
        current_paragraph = []
        current_list_items = []
        in_list = False

        # Process each line
        for line in lines:
            # Check if this line is a heading
            heading_match = re.match(r'^#{1,6}\s+', line)

            # Check if this line is a list item
            is_list, indent_level, content = cls._is_list_item(line)

            if heading_match:
                # Save any pending paragraph
                if current_paragraph:
                    sections.append(cls._create_paragraph_section(current_paragraph))
                    current_paragraph = []

                # Save any pending list
                if current_list_items:
                    sections.extend(cls._create_list_section(current_list_items))
                    current_list_items = []
                    in_list = False

                # Create and add the heading section
                heading_section = cls._create_heading_section(line)
                if heading_section:
                    sections.append(heading_section)

            elif is_list:
                # Save any pending paragraph
                if current_paragraph and not in_list:
                    sections.append(cls._create_paragraph_section(current_paragraph))
                    current_paragraph = []

                in_list = True
                current_list_items.append((indent_level, content))

            else:
                # Save any pending list
                if current_list_items:
                    sections.extend(cls._create_list_section(current_list_items))
                    current_list_items = []
                    in_list = False

                # Add to current paragraph if line is not empty
                if line.strip():
                    current_paragraph.append(line)
                else:
                    # Empty line - save current paragraph if any
                    if current_paragraph:
                        sections.append(cls._create_paragraph_section(current_paragraph))
                        current_paragraph = []

        # Handle any remaining content
        if current_list_items:
            sections.extend(cls._create_list_section(current_list_items))
        elif current_paragraph:
            sections.append(cls._create_paragraph_section(current_paragraph))

        return sections

    @classmethod
    def to_slack_canvas(cls, content: str) -> str:
        """Convert Markdown to Slack Canvas format

        Args:
            content: Markdown formatted text

        Returns:
            Slack Canvas formatted text
        """
        # Split the input string into parts based on code blocks and inline code
        parts = re.split(r"(?s)(```.+?```|`[^`\n]+?`)", content)

        # Apply minimal formatting for canvas
        result = ""
        for part in parts:
            if part.startswith("```") or part.startswith("`"):
                result += part
            else:
                # Convert numbered lists to bullet lists
                part = re.sub(r"(?m)^(\s*)\d+\.\s+(.*)", r"\1* \2", part)
                result += part
        return result

    @classmethod
    def to_slack_rich_text(cls, markdown_text: str, return_json: bool = False) -> Union[List[Dict[str, Any]], str]:
        """
        Convert Markdown text to Slack block format with proper divider handling.

        Supports:
        - Headings (# through ######)
        - Bold text (**text** or __text__)
        - Italic text (*text* or _text_)
        - Bullet lists (lines starting with - or *)
        - Inline code (`code`)
        - Horizontal rules/dividers (---, ***, or ___)

        Note: Slack's rich_text format has limited support for nested lists.
        This converter will flatten nested lists and add indent markers.

        When dividers are present, the content is split into separate rich_text blocks
        with divider blocks placed at the top level between them.

        Args:
            markdown_text: The Markdown formatted text to convert
            return_json: If True, returns JSON string; if False, returns list of blocks

        Returns:
            A list of Slack blocks or JSON string representing the blocks
        """
        lines = markdown_text.strip().split('\n')

        # First pass: split content by dividers
        content_segments = []
        current_segment = []

        for line in lines:
            if cls._is_divider(line):
                if current_segment:
                    content_segments.append(current_segment)
                    current_segment = []
                content_segments.append(['__DIVIDER__'])
            else:
                current_segment.append(line)

        # Don't forget the last segment
        if current_segment:
            content_segments.append(current_segment)

        # Process each segment
        result_blocks = []

        for segment in content_segments:
            if segment == ['__DIVIDER__']:
                # Add divider block
                result_blocks.append({"type": "divider"})
            else:
                # Process as rich_text content
                rich_text_elements = cls._process_rich_text_segment(segment)
                if rich_text_elements:
                    result_blocks.append({
                        "type": "rich_text",
                        "elements": rich_text_elements
                    })

        # Return as JSON string if requested
        if return_json:
            return json.dumps(result_blocks)
        else:
            return result_blocks


def limit_text_length(text: str, limit: int) -> str:
    """Limit text length with ellipsis

    Args:
        text: Text to limit
        limit: Maximum length

    Returns:
        Limited text with ellipsis if truncated
    """
    if len(text) > limit:
        return text[:limit-3] + '…'
    return text
