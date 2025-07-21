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

"""External content manager for including additional Markdown files in overview generation"""

from pathlib import Path
from typing import Dict, Any
import logging


class ExternalContentManager:
    """Manages external Markdown content files for overview generation"""

    def __init__(self, config: Dict[str, Any], summary_dir: Path):
        """Initialize external content manager

        Args:
            config: Overview configuration containing external_content settings
            summary_dir: Base directory for summaries
        """
        self.config = config
        self.summary_dir = summary_dir
        self.logger = logging.getLogger('Hedwig.overview.external_content')
        
        # Get external content configuration
        self.external_config = config.get('external_content', {})
        self.enabled = self.external_config.get('enabled', False)
        self.sources = self.external_config.get('sources', [])

    def fetch_all_content(self, date: str) -> Dict[str, str]:
        """Fetch content from all configured external Markdown files for the given date

        Args:
            date: Date string in YYYY-MM-DD format

        Returns:
            Dictionary mapping source names to content strings
        """
        if not self.enabled:
            return {}

        external_content = {}
        
        # Parse date to get year and month
        year = date[:4]
        month = date[5:7]

        for source in self.sources:
            source_name = source.get('name', 'unnamed')
            file_suffix = source.get('file_suffix', '')
            required = source.get('required', False)
            
            if not file_suffix:
                self.logger.warning(f"No file_suffix specified for source '{source_name}'")
                continue
                
            # Construct file path
            # Convert date from YYYY-MM-DD to YYYYMMDD for filename
            date_for_filename = date.replace('-', '')
            filename = f'{date_for_filename}{file_suffix}'
            filepath = self.summary_dir / year / month / filename
            
            try:
                if filepath.exists():
                    content = filepath.read_text(encoding='utf-8').strip()
                    if content:
                        external_content[source_name] = content
                        self.logger.info(f"Loaded external content from {filepath}")
                    else:
                        self.logger.debug(f"File is empty: {filepath}")
                        if required:
                            self.logger.warning(f"Required source '{source_name}' has empty content for {date}")
                else:
                    self.logger.debug(f"File not found: {filepath}")
                    if required:
                        self.logger.warning(f"Required source '{source_name}' file not found for {date}")
            except Exception as e:
                self.logger.error(f"Error reading file {filepath}: {e}")
                if required:
                    raise

        return external_content

    def format_content_for_prompt(self, external_content: Dict[str, str]) -> str:
        """Format external content for inclusion in LLM prompt

        Args:
            external_content: Dictionary mapping source names to content

        Returns:
            Formatted string for prompt inclusion
        """
        if not external_content:
            return ""

        formatted = "\n\n## Additional Content\n"
        
        for source_name, content in external_content.items():
            # Find the source configuration to get its description
            source_config = next(
                (s for s in self.sources if s.get('name') == source_name), 
                None
            )
            
            if source_config and source_config.get('description'):
                section_title = source_config['description']
            else:
                # Fallback: convert snake_case to Title Case
                section_title = source_name.replace('_', ' ').title()

            formatted += f"\n### {section_title}\n{content}\n"

        return formatted