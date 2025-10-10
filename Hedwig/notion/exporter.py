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

"""Markdown exporter for Notion pages"""

import os
import re
from urllib.parse import urlparse, urlunparse
from typing import Dict, Any

from notion2md.exporter.block import StringExporter


class MarkdownExporter:
    """Export Notion pages to markdown files"""

    def __init__(self, dump_path_template: str, header_template: str):
        """Initialize markdown exporter

        Args:
            dump_path_template: Path template for exported files
            header_template: Template for file headers
        """
        self.dump_path_template = dump_path_template
        self.header_template = header_template

    def export_page(
        self,
        page_id: str,
        page_info: Dict[str, Any],
        page_path: str,
        dump_dir: str
    ) -> str:
        """Export a Notion page to markdown

        Args:
            page_id: Notion page ID
            page_info: Page metadata
            page_path: Hierarchical path of the page
            dump_dir: Base directory for exports

        Returns:
            Path to exported file

        Raises:
            Exception: If export fails
        """
        # Generate target path
        target_path = self._generate_path(page_id, dump_dir)

        # Create directory if needed
        target_dir = os.path.dirname(target_path)
        os.makedirs(target_dir, exist_ok=True)

        # Export content
        content = StringExporter(block_id=page_id).export()
        content = self._simplify_image_links(content)
        content = self._sanitize_amazon_links(content)

        # Write to file
        with open(target_path, 'w') as f:
            header = self.header_template.format(
                note=page_info,
                path=page_path
            )
            f.write(header)
            f.write(content)

        return target_path

    def _generate_path(self, page_id: str, dump_dir: str) -> str:
        """Generate file path for a page

        Args:
            page_id: Notion page ID
            dump_dir: Base directory

        Returns:
            Full file path
        """
        return self.dump_path_template.format(
            dump_dir=dump_dir,
            noteid_0=page_id[:2],
            noteid_1=page_id[:4],
            noteid_2=page_id.rsplit('-', 1)[0],
            noteid=page_id
        )

    @staticmethod
    def _simplify_image_links(text: str) -> str:
        """Simplify image links in markdown text

        Args:
            text: Markdown text

        Returns:
            Text with simplified image links
        """
        pattern = r"!\[(.*?)\]\(.*?\)"
        return re.sub(pattern, r"![\1]()", text)

    @staticmethod
    def _sanitize_amazon_links(text: str) -> str:
        """Remove credential query parameters from Amazon S3 style links.

        Args:
            text: Markdown text

        Returns:
            Text with sanitized Amazon URLs
        """
        pattern = re.compile(r'(?P<prefix>!?)\[(?P<label>[^\]]*?)\]\((?P<url>[^)]+)\)')

        def _replace(match: re.Match) -> str:
            prefix = match.group('prefix')
            label = match.group('label')
            url = match.group('url').strip()
            sanitized = MarkdownExporter._strip_amazon_query(url)
            return f"{prefix}[{label}]({sanitized})"

        return pattern.sub(_replace, text)

    @staticmethod
    def _strip_amazon_query(url: str) -> str:
        """Strip query/fragment components from amazonaws.com URLs."""
        if not url:
            return ''

        parsed = urlparse(url)
        if parsed.netloc.lower().endswith('amazonaws.com') and (parsed.query or parsed.fragment):
            sanitized = parsed._replace(query='', fragment='')
            return urlunparse(sanitized)
        return url
