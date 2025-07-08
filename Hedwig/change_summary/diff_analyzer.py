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

"""Git diff analyzer for extracting and processing changes"""

import subprocess
import datetime
from typing import List, Dict, Optional, Callable
from pathlib import Path

from ..utils.logging import setup_logger


class DiffAnalyzer:
    """Analyze git diffs from repository"""

    def __init__(self, repo_path: str, quiet: bool = False, user_lookup: Optional[Dict[str, str]] = None,
                 unknown_user_callback: Optional[Callable[[str], Optional[str]]] = None):
        """Initialize diff analyzer

        Args:
            repo_path: Path to git repository
            quiet: Suppress logging output
            user_lookup: Dictionary mapping user IDs to names
            unknown_user_callback: Callback function for user IDs not found in lookup, returns name or None
        """
        self.repo_path = Path(repo_path)
        self.logger = setup_logger('Hedwig.summary.diff_analyzer', quiet=quiet)
        self.user_lookup = user_lookup or {}
        self.unknown_user_callback = unknown_user_callback

    def get_diffs_since(self, max_age_seconds: int) -> List[str]:
        """Get all git diffs from the repository within the specified age limit

        Args:
            max_age_seconds: Maximum age of commits to include

        Returns:
            List of individual file diffs
        """
        # Calculate the cutoff time in UTC
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff_time = now - datetime.timedelta(seconds=max_age_seconds)
        cutoff_time_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S UTC')

        self.logger.info(f"Getting changes since {cutoff_time_str} ({max_age_seconds/3600:.1f} hours ago)")

        # Find commits within our time range
        cmd_log = ['git', 'log', '--format=%H', f'--since={cutoff_time_str}']
        try:
            log_result = subprocess.check_output(cmd_log, cwd=self.repo_path, text=True).strip()
        except subprocess.CalledProcessError:
            self.logger.info(f"No commits found within {max_age_seconds} seconds ({max_age_seconds/3600:.1f} hours)")
            return []

        if not log_result:
            self.logger.info(f"No commits found within {max_age_seconds} seconds ({max_age_seconds/3600:.1f} hours)")
            return []

        commits = log_result.split('\n')
        self.logger.info(f"Found {len(commits)} commits since {cutoff_time_str}")

        # Get the state before the oldest commit to compare against HEAD
        # We need to find the parent of the oldest (last in list) commit
        oldest_commit = commits[-1]

        # Try to get the parent of the oldest commit
        try:
            parent_cmd = ['git', 'rev-parse', f'{oldest_commit}^']
            parent_commit = subprocess.check_output(
                parent_cmd,
                cwd=self.repo_path,
                text=True,
                stderr=subprocess.DEVNULL
            ).strip()
            base_commit = parent_commit
            self.logger.debug(f"Using parent commit {parent_commit[:8]} as base")
        except subprocess.CalledProcessError:
            # If oldest_commit has no parent (it's the root commit),
            # use the empty tree object to include the first commit
            # The empty tree SHA is a git constant
            base_commit = '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
            self.logger.debug(f"Oldest commit {oldest_commit[:8]} is root commit, using empty tree as base")

        # Get all changes from base to HEAD
        cmd = ['git', 'diff', base_commit, 'HEAD', '--']
        try:
            result = subprocess.check_output(cmd, cwd=self.repo_path, text=True)
        except subprocess.CalledProcessError:
            self.logger.info("No changes found or unable to get diff")
            return []

        if not result.strip():
            self.logger.info("No changes found in the specified time range")
            return []

        self.logger.info("Changes found, processing diffs...")
        filediffs = result.split('\ndiff --git ')
        return ['diff --git ' + d for d in filediffs if d.strip()]

    def extract_metadata(self, diff: str, max_age_seconds: Optional[int] = None) -> Dict[str, str]:
        """Extract metadata information from diff header

        Args:
            diff: Git diff text
            max_age_seconds: If provided, extract all editors within this time range

        Returns:
            Dictionary with metadata (Title, Page Location, Last Edited By/Editors)
        """
        diffheader = diff.splitlines()[:20]

        # Find the file path from diff header
        filepath = None
        for line in diffheader:
            if line.startswith('+++'):
                filepath = line.split('/', 1)[-1].strip()
                break

        if not filepath:
            raise ValueError("No file path found in diff header")

        fullpath = self.repo_path / filepath

        # Read metadata from file header
        try:
            with open(fullpath, 'r', encoding='utf-8') as f:
                meta_lines = [f.readline() for _ in range(5)]

                # Extract title (first line after '# ')
                header = {'Title': meta_lines[0][2:].strip() if meta_lines[0].startswith('# ') else 'Untitled'}

                # Extract other metadata
                for line in meta_lines[1:]:
                    if line.startswith('- ') and ':' in line:
                        key, value = line.split(':', 1)
                        key = key[2:]  # Remove '- ' prefix
                        value = value.strip()

                        # Replace UUID with real name for "Last Edited By" field
                        if key == 'Last Edited By':
                            if value in self.user_lookup:
                                value = self.user_lookup[value]
                            elif self.unknown_user_callback:
                                # Call callback for unknown user
                                result = self.unknown_user_callback(value)
                                if result:
                                    value = result

                        header[key] = value

                # If max_age_seconds is provided, get all editors for this file
                if max_age_seconds and filepath:
                    all_editors = self.get_all_editors_for_file(filepath, max_age_seconds)
                    if all_editors:
                        # Always use "Editors" field
                        if 'Last Edited By' in header:
                            del header['Last Edited By']
                        header['Editors'] = ', '.join(all_editors)
                    else:
                        # No editors found in history, use current Last Edited By if available
                        if 'Last Edited By' in header:
                            header['Editors'] = header['Last Edited By']
                            del header['Last Edited By']
                else:
                    # No max_age_seconds provided, convert Last Edited By to Editors
                    if 'Last Edited By' in header:
                        header['Editors'] = header['Last Edited By']
                        del header['Last Edited By']

                return header
        except Exception as e:
            self.logger.error(f"Error reading metadata from {fullpath}: {e}")
            return {
                'Title': 'Unknown',
                'Page Location': str(filepath),
                'Editors': 'Unknown'
            }

    @staticmethod
    def get_max_age_for_weekday(weekday: int, weekday_config: Dict[str, int] = None) -> int:
        """Get maximum age in seconds based on weekday

        Args:
            weekday: Day of week (0=Monday, 6=Sunday)
            weekday_config: Dictionary mapping weekday names to max age in days

        Returns:
            Maximum age in seconds
        """
        # Default configuration
        default_config = {
            'monday': 2,
            'tuesday': 1,
            'wednesday': 1,
            'thursday': 1,
            'friday': 1,
            'saturday': 1,
            'sunday': 1
        }

        # Use provided config or defaults
        config = weekday_config or default_config

        # Map weekday number to name
        weekday_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        weekday_name = weekday_names[weekday]

        # Get days for this weekday (default to 1 if not specified)
        days = config.get(weekday_name, 1)

        return 86400 * days

    def get_all_editors_for_file(self, filepath: str, max_age_seconds: int) -> List[str]:
        """Get all unique editors who modified a file within the time range

        Args:
            filepath: Path to the file relative to repo root
            max_age_seconds: Maximum age of commits to include

        Returns:
            List of unique editor IDs/names
        """
        # Calculate the cutoff time in UTC
        now = datetime.datetime.now(datetime.timezone.utc)
        cutoff_time = now - datetime.timedelta(seconds=max_age_seconds)
        cutoff_time_str = cutoff_time.strftime('%Y-%m-%d %H:%M:%S UTC')

        # Get all commits for this file within the time range
        cmd = ['git', 'log', '--format=%H', f'--since={cutoff_time_str}', '--', filepath]
        try:
            result = subprocess.check_output(cmd, cwd=self.repo_path, text=True).strip()
        except subprocess.CalledProcessError:
            return []

        if not result:
            return []

        commits = result.split('\n')
        editors = []

        # Extract Last Edited By from each commit
        for commit in commits:
            cmd_show = ['git', 'show', f'{commit}:{filepath}']
            try:
                content = subprocess.check_output(cmd_show, cwd=self.repo_path, text=True)
                # Look for Last Edited By in first 5 lines
                for line in content.split('\n')[:5]:
                    if line.startswith('- Last Edited By:'):
                        editor_id = line.split(':', 1)[1].strip()
                        if editor_id:
                            # Replace UUID with real name if available
                            if editor_id in self.user_lookup:
                                editor_name = self.user_lookup[editor_id]
                            elif self.unknown_user_callback:
                                result = self.unknown_user_callback(editor_id)
                                editor_name = result if result else editor_id
                            else:
                                editor_name = editor_id

                            if editor_name not in editors:
                                editors.append(editor_name)
                        break
            except subprocess.CalledProcessError:
                # File might not exist in this commit
                continue

        return editors
