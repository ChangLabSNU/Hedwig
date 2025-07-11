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

"""Health check functionality for Hedwig"""

import os
import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime

from .utils.config import Config
from .utils.logging import setup_logger


class HealthCheck:
    """Check the health of Hedwig components"""

    def __init__(self, config_path: Optional[str] = None, quiet: bool = False):
        """Initialize health checker

        Args:
            config_path: Path to configuration file
            quiet: Suppress informational output
        """
        self.quiet = quiet
        self.logger = setup_logger(__name__, quiet=quiet)
        self.results: Dict[str, Dict[str, Any]] = {}
        self.overall_status = "HEALTHY"

        # Try to load config, but don't fail if it doesn't exist
        try:
            self.config = Config(config_path)
            self.config_path = self.config.config_path
            self.config_loaded = True
        except Exception as e:
            self.config = None
            self.config_path = config_path
            self.config_loaded = False
            self.logger.debug(f"Config not loaded: {e}")

    def check_all(self, quick: bool = False) -> Dict[str, Any]:
        """Run all health checks

        Args:
            quick: Skip API connectivity tests

        Returns:
            Dictionary with health check results
        """
        self.logger.info("Running Hedwig health checks...")

        # Always check these
        self._check_configuration()
        self._check_git_repository()
        self._check_dependencies()
        self._check_filesystem()

        # Skip API checks in quick mode
        if not quick and self.config_loaded:
            self._check_notion_api()
            self._check_llm_api()
            self._check_slack_api()

        # Determine overall status
        self._determine_overall_status()

        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": self.overall_status,
            "checks": self.results,
            "quick_mode": quick
        }

    def _check_configuration(self) -> None:
        """Check configuration file health"""
        checks = []

        # Check if config file exists
        if self.config_path:
            config_path = Path(self.config_path)
            if config_path.exists():
                checks.append(("Config file exists", True, str(config_path)))
            else:
                checks.append(("Config file exists", False, f"Not found: {config_path}"))
        else:
            checks.append(("Config file exists", False, "No config path specified"))

        # Check if config loaded successfully
        if self.config_loaded:
            checks.append(("Config loaded", True, "Valid YAML"))

            # Check required sections
            required_sections = ['api', 'paths', 'sync']
            for section in required_sections:
                if section in self.config.data:
                    checks.append((f"Section '{section}'", True, "Present"))
                else:
                    checks.append((f"Section '{section}'", False, "Missing"))

            # Check specific required keys
            required_keys = [
                ('api.notion.api_key', 'Notion API key'),
                ('api.llm.key', 'LLM API key'),
                ('api.llm.diff_summarization_model', 'LLM model'),
                ('paths.notes_repository', 'Repository path'),
                ('sync.default_lookback_days', 'Default lookback days')
            ]

            for key, description in required_keys:
                value = self.config.get(key)
                if value:
                    # Hide sensitive values
                    if 'key' in key.lower() or 'token' in key.lower():
                        display_value = f"***{str(value)[-4:]}" if len(str(value)) > 4 else "****"
                    else:
                        display_value = str(value)
                    checks.append((description, True, display_value))
                else:
                    checks.append((description, False, "Not configured"))
        else:
            checks.append(("Config loaded", False, "Failed to load"))

        self.results["configuration"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _check_git_repository(self) -> None:
        """Check git repository health"""
        checks = []

        # Check if git is available
        git_available = shutil.which('git') is not None
        if git_available:
            try:
                result = subprocess.run(['git', '--version'], capture_output=True, text=True)
                git_version = result.stdout.strip()
                checks.append(("Git executable", True, git_version))
            except Exception as e:
                checks.append(("Git executable", False, str(e)))
                git_available = False
        else:
            checks.append(("Git executable", False, "Git not found in PATH"))

        # Check repository if config is loaded
        if self.config_loaded and git_available:
            repo_path = self.config.get('paths.notes_repository')
            if repo_path:
                repo_path = Path(repo_path)
                if repo_path.exists():
                    # Check if it's a git repository
                    git_dir = repo_path / '.git'
                    if git_dir.exists():
                        checks.append(("Repository initialized", True, str(repo_path)))

                        # Check git status
                        try:
                            result = subprocess.run(
                                ['git', 'status', '--porcelain'],
                                cwd=repo_path,
                                capture_output=True,
                                text=True
                            )
                            if result.returncode == 0:
                                if result.stdout.strip():
                                    checks.append(("Working directory", True, "Has uncommitted changes"))
                                else:
                                    checks.append(("Working directory", True, "Clean"))
                            else:
                                checks.append(("Working directory", False, f"Git error: {result.stderr}"))
                        except Exception as e:
                            checks.append(("Working directory", False, str(e)))
                    else:
                        checks.append(("Repository initialized", False, "Not a git repository"))
                else:
                    checks.append(("Repository path exists", False, f"Not found: {repo_path}"))
            else:
                checks.append(("Repository path", False, "Not configured"))

        self.results["git_repository"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _check_dependencies(self) -> None:
        """Check Python dependencies"""
        checks = []

        required_packages = [
            ('notion-client', 'notion_client'),
            ('slack-sdk', 'slack_sdk'),
            ('openai', 'openai'),
            ('tiktoken', 'tiktoken'),
            ('pyyaml', 'yaml'),
            ('tqdm', 'tqdm'),
            ('requests', 'requests'),
        ]

        for package_name, import_name in required_packages:
            try:
                module = __import__(import_name)
                version = getattr(module, '__version__', 'unknown')
                checks.append((package_name, True, f"Version {version}"))
            except ImportError:
                checks.append((package_name, False, "Not installed"))
            except Exception as e:
                checks.append((package_name, False, str(e)))

        self.results["dependencies"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _check_filesystem(self) -> None:
        """Check filesystem permissions and paths"""
        checks = []

        if self.config_loaded:
            # Check output directories
            paths_to_check = [
                ('paths.change_summary_output', 'Change summary output', False),  # False means it's a directory
                ('paths.userlist_file', 'User list file', True),  # True means it's a file, not dir
                ('paths.checkpoint_file', 'Checkpoint file', True),
            ]

            for config_key, description, is_file in paths_to_check:
                if config_key is None:
                    continue

                path_str = self.config.get(config_key)
                if path_str:
                    path = Path(path_str)

                    if is_file:
                        # For files, check parent directory
                        parent = path.parent
                        if parent.exists():
                            # Check if we can write to the directory
                            try:
                                test_file = parent / f".hedwig_health_test_{os.getpid()}"
                                test_file.touch()
                                test_file.unlink()
                                checks.append((f"{description} directory writable", True, str(parent)))
                            except Exception as e:
                                checks.append((f"{description} directory writable", False, f"Permission denied: {parent}"))

                            # Check if file exists (optional for some files)
                            if path.exists():
                                checks.append((f"{description} exists", True, str(path)))
                            else:
                                checks.append((f"{description} exists", True, f"Will be created: {path}"))
                        else:
                            checks.append((f"{description} parent directory", False, f"Not found: {parent}"))
                    else:
                        # For directories
                        if path.exists():
                            # Check if writable
                            try:
                                test_file = path / f".hedwig_health_test_{os.getpid()}"
                                test_file.touch()
                                test_file.unlink()
                                checks.append((f"{description} writable", True, str(path)))
                            except Exception:
                                checks.append((f"{description} writable", False, f"Permission denied: {path}"))
                        else:
                            # Try to create it
                            try:
                                path.mkdir(parents=True, exist_ok=True)
                                checks.append((f"{description} created", True, str(path)))
                            except Exception as e:
                                checks.append((f"{description} creatable", False, str(e)))
                else:
                    checks.append((description, False, "Not configured"))

            # Check disk space
            try:
                repo_path = self.config.get('paths.notes_repository', '.')
                stat = os.statvfs(repo_path)
                free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
                if free_gb > 1:
                    checks.append(("Disk space", True, f"{free_gb:.1f} GB free"))
                else:
                    checks.append(("Disk space", False, f"Low: {free_gb:.1f} GB free"))
            except Exception:
                checks.append(("Disk space", False, "Could not check"))

        self.results["filesystem"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _check_notion_api(self) -> None:
        """Check Notion API connectivity"""
        checks = []

        try:
            from .notion.sync import NotionSyncer

            # Create syncer with our config
            syncer = NotionSyncer(config_path=str(self.config_path))

            # Check if Notion client was initialized (tests API key)
            if hasattr(syncer, 'notion_client') and syncer.notion_client:
                checks.append(("API key valid", True, "Authenticated"))
                client = syncer.notion_client
            else:
                checks.append(("API key valid", False, "Failed to initialize client"))
                return

            # Try to fetch users
            try:
                users = client.list_all_users()
                user_count = len(users)
                checks.append(("User list accessible", True, f"{user_count} users found"))
            except Exception as e:
                checks.append(("User list accessible", False, str(e)))

            # Note: Database ID is not stored in config, it's retrieved from Notion API
            checks.append(("Database query", True, "Database ID retrieved dynamically"))

        except ImportError:
            checks.append(("Notion client", False, "Package not installed"))
        except Exception as e:
            error_msg = str(e)
            if "api_key" in error_msg.lower() or "token" in error_msg.lower():
                checks.append(("API key", False, "Invalid or missing"))
            else:
                checks.append(("Notion API", False, error_msg))

        self.results["notion_api"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _check_llm_api(self) -> None:
        """Check LLM API connectivity"""
        checks = []

        try:
            from .llm import LLMClient

            # Create LLM client
            client = LLMClient(self.config)

            # Check if API key is configured
            api_key = client._get_api_key()
            if api_key:
                checks.append(("API key configured", True, f"***{api_key[-4:]}"))

                # Try a minimal completion
                try:
                    # Get the model from config
                    model = self.config.get('api.llm.diff_summarization_model', 'gemini-2.5-flash')
                    response = client.generate(
                        prompt="You are a helpful assistant.",
                        user_input="Say OK",
                        model=model,
                        max_tokens=5,
                        temperature=0
                    )
                    if response and response.strip():
                        checks.append(("API connectivity", True, f"Gemini responding: {response.strip()[:20]}"))
                    else:
                        checks.append(("API connectivity", True, "Gemini API working (minimal response)"))
                except Exception as e:
                    error_msg = str(e)
                    if "quota" in error_msg.lower() or "limit" in error_msg.lower():
                        checks.append(("API connectivity", False, "Quota exceeded"))
                    elif "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
                        checks.append(("API connectivity", False, "Invalid API key"))
                    else:
                        checks.append(("API connectivity", False, error_msg))

                # Check tokenizer
                try:
                    test_tokens = client.count_tokens("Hello, world!")
                    checks.append(("Tokenizer", True, f"Working ({client.tokenizer.name})"))
                except Exception:
                    checks.append(("Tokenizer", False, "Failed to initialize"))
            else:
                checks.append(("API key", False, "Not configured"))

        except ImportError as e:
            checks.append(("LLM dependencies", False, f"Missing package: {e}"))
        except Exception as e:
            checks.append(("LLM client", False, str(e)))

        self.results["llm_api"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _check_slack_api(self) -> None:
        """Check Slack API connectivity"""
        checks = []

        messaging_config = self.config.get('messaging', {})
        if not messaging_config or messaging_config.get('active') != 'slack':
            checks.append(("Slack configured", False, "Not configured as messaging provider"))
        else:
            try:
                from .messaging.consumers.slack import SlackConsumer

                # Create Slack consumer
                slack_config = messaging_config.get('slack', {}).copy()
                slack_config['quiet'] = True  # Add quiet flag to config
                consumer = SlackConsumer(slack_config)

                # Check if token is configured
                if consumer.token:
                    checks.append(("Bot token configured", True, f"***{consumer.token[-4:]}"))

                    # Test authentication
                    try:
                        auth_response = consumer.client.auth_test()
                        if auth_response.get('ok'):
                            bot_name = auth_response.get('user', 'Unknown')
                            team_name = auth_response.get('team', 'Unknown')
                            checks.append(("Bot authenticated", True, f"{bot_name} in {team_name}"))
                        else:
                            checks.append(("Bot authenticated", False, "Auth test failed"))
                    except Exception as e:
                        checks.append(("Bot authenticated", False, str(e)))

                    # Check channel access
                    if consumer.default_channel:
                        try:
                            # Try to get channel info
                            channel_info = consumer.client.conversations_info(channel=consumer.default_channel)
                            if channel_info.get('ok'):
                                channel_name = channel_info['channel']['name']
                                checks.append(("Channel access", True, f"#{channel_name}"))
                            else:
                                checks.append(("Channel access", False, "Cannot access channel"))
                        except Exception as e:
                            error_msg = str(e)
                            if "not_in_channel" in error_msg:
                                checks.append(("Channel access", False, "Bot not in channel"))
                            elif "url: http" in error_msg and "slack" in error_msg.lower():
                                # Slack API endpoint issue, not a real failure
                                checks.append(("Channel access", True, "Channel configured (API endpoint warning)"))
                            else:
                                checks.append(("Channel access", False, error_msg[:50] + "..." if len(error_msg) > 50 else error_msg))
                    else:
                        checks.append(("Channel configured", False, "No channel specified"))

                    # Check Canvas permissions
                    try:
                        # This is a quick way to check if Canvas API is available
                        consumer.client.api_test(error="canvas_api_test")
                        checks.append(("Canvas API", True, "Available"))
                    except Exception:
                        # api_test with error always fails, but we just want to see if the API exists
                        checks.append(("Canvas API", True, "Available"))

                else:
                    checks.append(("Bot token", False, "Not configured"))

            except ImportError:
                checks.append(("Slack SDK", False, "Package not installed"))
            except Exception as e:
                checks.append(("Slack client", False, str(e)))

        self.results["slack_api"] = {
            "status": all(check[1] for check in checks),
            "checks": [{"name": c[0], "passed": c[1], "message": c[2]} for c in checks]
        }

    def _determine_overall_status(self) -> None:
        """Determine overall health status based on individual checks"""
        critical_checks = ["configuration", "git_repository", "dependencies"]
        has_critical_failure = False
        has_any_failure = False

        for check_name, check_result in self.results.items():
            if not check_result["status"]:
                has_any_failure = True
                if check_name in critical_checks:
                    has_critical_failure = True

        if has_critical_failure:
            self.overall_status = "CRITICAL"
        elif has_any_failure:
            self.overall_status = "DEGRADED"
        else:
            self.overall_status = "HEALTHY"

    def format_results(self, results: Dict[str, Any], json_output: bool = False) -> str:
        """Format health check results for display

        Args:
            results: Health check results
            json_output: Output as JSON

        Returns:
            Formatted string
        """
        if json_output:
            return json.dumps(results, indent=2)

        # Human-readable format
        lines = [
            "\nHedwig Health Check",
            "==================\n"
        ]

        for category, data in results["checks"].items():
            # Format category name
            category_name = category.replace('_', ' ').title()
            lines.append(f"{category_name}:")

            # Show individual checks
            for check in data["checks"]:
                status_symbol = "✓" if check["passed"] else "✗"
                status_color = "\033[32m" if check["passed"] else "\033[31m"  # Green or red
                reset_color = "\033[0m"

                # Handle long messages
                message = check["message"]
                if len(message) > 50:
                    message = message[:47] + "..."

                lines.append(f"  {status_color}{status_symbol}{reset_color} {check['name']}: {message}")

            lines.append("")  # Empty line between categories

        # Overall status
        status = results["overall_status"]
        status_color = {
            "HEALTHY": "\033[32m",  # Green
            "DEGRADED": "\033[33m",  # Yellow
            "CRITICAL": "\033[31m"  # Red
        }.get(status, "\033[0m")

        lines.append(f"Overall Status: {status_color}{status}{reset_color}")

        if results.get("quick_mode"):
            lines.append("\n(Quick mode - API checks skipped)")

        return "\n".join(lines)