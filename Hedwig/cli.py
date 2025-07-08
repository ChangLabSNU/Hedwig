#!/usr/bin/env python
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

"""
Command line interface for Hedwig package
"""

import argparse
import sys
from . import __version__
import os
import tempfile
import yaml


def get_config_with_quiet(config_path: str, quiet: bool) -> str:
    """Get config path, potentially with quiet setting overridden

    Args:
        config_path: Original config file path
        quiet: Whether to force quiet mode

    Returns:
        Path to config file (may be temporary with quiet override)
    """
    if not quiet:
        return config_path

    # Create a temporary config with quiet=true
    from .utils.config import Config
    config = Config(config_path)
    config.data.setdefault('output', {})['quiet'] = True

    # Write to temporary file
    import yaml
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.safe_dump(config.data, f, default_flow_style=False)
        return f.name


def main():
    """Main entry point for the hedwig command line tool"""
    parser = argparse.ArgumentParser(
        prog='hedwig',
        description='Hedwig - A tool for managing and processing various data workflows'
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(
        dest='command',
        help='Available commands'
    )

    # Add subcommands for different functionalities
    # These will be implemented to route to the existing scripts

    # Sync Notion to Git
    sync_parser = subparsers.add_parser(
        'sync',
        help='Sync Notion content to Git repository'
    )
    sync_parser.add_argument(
        '--config',
        default='config.yml',
        help='Path to configuration file'
    )
    sync_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages and progress bar'
    )
    sync_parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug output'
    )

    # Sync user list from Notion
    sync_userlist_parser = subparsers.add_parser(
        'sync-userlist',
        help='Sync user list from Notion to TSV file'
    )
    sync_userlist_parser.add_argument(
        '--config',
        default='config.yml',
        help='Path to configuration file'
    )
    sync_userlist_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    # Generate change summary
    change_summary_parser = subparsers.add_parser(
        'generate-change-summary',
        help='Generate summaries for recent changes in research notes'
    )
    change_summary_parser.add_argument(
        '--config',
        default='config.yml',
        help='Path to configuration file'
    )
    change_summary_parser.add_argument(
        '--no-write',
        action='store_true',
        help='Do not write summaries to file, only print them'
    )
    change_summary_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    # Generate overview
    overview_parser = subparsers.add_parser(
        'generate-overview',
        help='Generate overview summary from individual change summaries'
    )
    overview_parser.add_argument(
        '--config',
        default='config.yml',
        help='Path to configuration file'
    )
    overview_parser.add_argument(
        '--no-write',
        action='store_true',
        help='Do not write overview to file, only print it'
    )
    overview_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    # Post summary to messaging platform
    post_parser = subparsers.add_parser(
        'post-summary',
        help='Post summary to configured messaging platform'
    )
    post_parser.add_argument(
        '--summary-file',
        required=True,
        help='Path to the markdown summary file to post'
    )
    post_parser.add_argument(
        '--overview-file',
        required=True,
        help='Path to the file containing overview message'
    )
    post_parser.add_argument(
        '--title',
        required=True,
        help='Title for the summary'
    )
    post_parser.add_argument(
        '--config',
        default='config.yml',
        help='Path to configuration file'
    )
    post_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    # Run complete summarizer pipeline
    pipeline_parser = subparsers.add_parser(
        'pipeline',
        help='Run complete summarizer pipeline (change-summary -> overview -> post-summary)'
    )
    pipeline_parser.add_argument(
        '--config',
        default='config.yml',
        help='Path to configuration file'
    )
    pipeline_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    # Parse arguments
    args = parser.parse_args()

    # Route to appropriate function based on command
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Placeholder for command routing
    # These will be implemented to call the actual functionality
    if args.command == 'sync':
        from .notion.sync import NotionSyncer
        syncer = NotionSyncer(config_path=args.config)
        syncer.sync(quiet=args.quiet, verbose=args.verbose)
    elif args.command == 'sync-userlist':
        from .notion.sync import NotionSyncer
        syncer = NotionSyncer(config_path=args.config)
        syncer.sync_userlist(quiet=args.quiet)
    elif args.command == 'generate-change-summary':
        from .change_summary.generator import ChangeSummaryGenerator

        # Get config with quiet override if needed
        config_path = get_config_with_quiet(args.config, args.quiet)
        try:
            generator = ChangeSummaryGenerator(config_path=config_path)

            # Generate summaries with write_to_file based on --no-write flag
            summaries = generator.generate(write_to_file=not args.no_write)

            # Print summaries if not writing to file (unless quiet)
            if args.no_write and summaries and not args.quiet:
                print("\n---\n".join(summaries))
        finally:
            # Clean up temp file if created
            if config_path != args.config and os.path.exists(config_path):
                os.unlink(config_path)
    elif args.command == 'generate-overview':
        from .overview.generator import OverviewGenerator

        # Get config with quiet override if needed
        config_path = get_config_with_quiet(args.config, args.quiet)
        try:
            generator = OverviewGenerator(config_path=config_path)

            # Generate overview with write_to_file based on --no-write flag
            overview = generator.generate(write_to_file=not args.no_write)

            # Print overview if not writing to file (unless quiet)
            if args.no_write and overview and not args.quiet:
                print(overview)
        finally:
            # Clean up temp file if created
            if config_path != args.config and os.path.exists(config_path):
                os.unlink(config_path)
    elif args.command == 'post-summary':
        from .messaging.manager import MessageManager

        # Get config with quiet override if needed
        config_path = get_config_with_quiet(args.config, args.quiet)
        try:
            manager = MessageManager(config_path=config_path)

            # Check if messaging is configured
            if not manager.consumer_name:
                if not args.quiet:
                    print("Error: No messaging platform configured in config file")
                sys.exit(1)

            # Post summary
            result = manager.post_summary(
                markdown_file=args.summary_file,
                message_file=args.overview_file,
                title=args.title,
                channel_override=None
            )

            # Report result (unless quiet)
            if not args.quiet:
                if result.success:
                    print(f"Successfully posted summary via {manager.consumer_name}")
                    if result.url:
                        print(f"Summary URL: {result.url}")
                else:
                    print(f"Failed to post summary: {result.error}")

            if not result.success:
                sys.exit(1)
        finally:
            # Clean up temp file if created
            if config_path != args.config and os.path.exists(config_path):
                os.unlink(config_path)
    elif args.command == 'pipeline':
        from .pipeline import SummarizerPipeline

        # Get config with quiet override if needed
        config_path = get_config_with_quiet(args.config, args.quiet)
        try:
            pipeline = SummarizerPipeline(config_path=config_path)

            # Run the pipeline
            success = pipeline.run()

            # Exit with appropriate code
            sys.exit(0 if success else 1)
        finally:
            # Clean up temp file if created
            if config_path != args.config and os.path.exists(config_path):
                os.unlink(config_path)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
