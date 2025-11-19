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
from datetime import datetime
from . import __version__


def create_parser():
    """Create and configure the argument parser"""
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
        '--config', '-c',
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
        '--config', '-c',
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
        '--config', '-c',
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
        '--config', '-c',
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
    overview_parser.add_argument(
        '--print-prompt',
        action='store_true',
        help='Print the LLM input prompt to stdout and exit'
    )
    overview_parser.add_argument(
        '--force',
        action='store_true',
        help='Regenerate overview even if an up-to-date file already exists'
    )
    overview_parser.add_argument(
        '--date',
        help='Date (YYYY-MM-DD) whose summaries should be processed instead of today'
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
        '--config', '-c',
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
        '--config', '-c',
        default='config.yml',
        help='Path to configuration file'
    )
    pipeline_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    # Health check
    health_parser = subparsers.add_parser(
        'health',
        help='Check the health of Hedwig components'
    )
    health_parser.add_argument(
        '--config', '-c',
        default='config.yml',
        help='Path to configuration file'
    )
    health_parser.add_argument(
        '--quick',
        action='store_true',
        help='Skip API connectivity tests for faster results'
    )
    health_parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    health_parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress information messages'
    )

    return parser


def handle_sync(args):
    """Handle sync command"""
    from .notion.sync import NotionSyncer
    syncer = NotionSyncer(config_path=args.config)
    syncer.sync(quiet=args.quiet, verbose=args.verbose)


def handle_sync_userlist(args):
    """Handle sync-userlist command"""
    from .notion.sync import NotionSyncer
    syncer = NotionSyncer(config_path=args.config)
    syncer.sync_userlist(quiet=args.quiet)


def handle_generate_change_summary(args):
    """Handle generate-change-summary command"""
    from .change_summary.generator import ChangeSummaryGenerator

    generator = ChangeSummaryGenerator(config_path=args.config, quiet=args.quiet)
    summaries = generator.generate(write_to_file=not args.no_write)

    # Print summaries if not writing to file (unless quiet)
    if args.no_write and summaries and not args.quiet:
        print("\n---\n".join(summaries))


def handle_generate_overview(args):
    """Handle generate-overview command"""
    from .overview.generator import OverviewGenerator

    generator = OverviewGenerator(config_path=args.config, quiet=args.quiet)

    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            print("Error: --date must be in YYYY-MM-DD format")
            sys.exit(1)

    # If --print-prompt is specified, print the prompt and exit
    if args.print_prompt:
        prompt_info = generator.get_prompt_for_debugging(target_date)
        if prompt_info:
            print("=== PROMPT ===")
            print(prompt_info['prompt'])
            print("\n=== USER INPUT ===")
            print(prompt_info['user_input'])
        else:
            print("No prompt available (e.g., no summaries found or Sunday)")
        return

    # Skip expensive regeneration if cached overview is fresher than inputs
    if not args.no_write and not args.force:
        cached_overview = generator.get_up_to_date_overview_path(target_date)
        if cached_overview:
            if not args.quiet:
                print(f"Overview already up to date at {cached_overview}. Skipping generation.")
            return

    overview = generator.generate(write_to_file=not args.no_write, target_date=target_date)

    # Print overview if not writing to file (unless quiet)
    if args.no_write and overview and not args.quiet:
        print(overview)


def handle_post_summary(args):
    """Handle post-summary command"""
    from .messaging.manager import MessageManager

    manager = MessageManager(config_path=args.config, quiet=args.quiet)

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


def handle_pipeline(args):
    """Handle pipeline command"""
    from .pipeline import SummarizerPipeline

    pipeline = SummarizerPipeline(config_path=args.config, quiet=args.quiet)
    success = pipeline.run()
    sys.exit(0 if success else 1)


def handle_health(args):
    """Handle health check command"""
    from .health import HealthCheck

    checker = HealthCheck(config_path=args.config, quiet=args.quiet)
    results = checker.check_all(quick=args.quick)

    # Format and print results
    output = checker.format_results(results, json_output=args.json)
    print(output)

    # Exit with appropriate code
    status = results["overall_status"]
    if status == "HEALTHY":
        sys.exit(0)
    elif status == "DEGRADED":
        sys.exit(1)
    else:  # CRITICAL
        sys.exit(2)


def main():
    """Main entry point for the hedwig command line tool"""
    parser = create_parser()
    args = parser.parse_args()

    # Show help if no command specified
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # Command handler mapping
    command_handlers = {
        'sync': handle_sync,
        'sync-userlist': handle_sync_userlist,
        'generate-change-summary': handle_generate_change_summary,
        'generate-overview': handle_generate_overview,
        'post-summary': handle_post_summary,
        'pipeline': handle_pipeline,
        'health': handle_health
    }

    # Execute the appropriate handler
    handler = command_handlers.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
