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

"""Git integration utilities"""

import subprocess
from typing import Optional
from pathlib import Path


class GitManager:
    """Manage git operations for synced content"""

    def __init__(self, repo_path: str, quiet: bool = False):
        """Initialize git manager

        Args:
            repo_path: Path to git repository
            quiet: Suppress git output
        """
        self.repo_path = Path(repo_path)
        self.quiet = quiet
        self._ensure_git_repo()

    def add_all(self) -> None:
        """Add all changes to git staging area"""
        self._run_git_command(['git', 'add', '.'])

    def commit(self, message: str) -> None:
        """Commit staged changes

        Args:
            message: Commit message
        """
        self._run_git_command(['git', 'commit', '-m', message])

    def _ensure_git_repo(self) -> None:
        """Ensure the repository path exists and is a git repository"""
        # Create directory if it doesn't exist
        if not self.repo_path.exists():
            self.repo_path.mkdir(parents=True, exist_ok=True)
            if not self.quiet:
                print(f"Created directory: {self.repo_path}")

        # Check if .git directory exists
        git_dir = self.repo_path / '.git'
        if not git_dir.exists():
            # Initialize git repository
            result = self._run_git_command(['git', 'init'])
            if result.returncode == 0 and not self.quiet:
                print(f"Initialized git repository in: {self.repo_path}")

    def _run_git_command(self, command: list) -> subprocess.CompletedProcess:
        """Run a git command in the repository

        Args:
            command: Command and arguments

        Returns:
            Completed process result
        """
        output = subprocess.DEVNULL if self.quiet else None
        return subprocess.run(
            command,
            cwd=self.repo_path,
            stdout=output,
            stderr=output,
            check=False
        )
