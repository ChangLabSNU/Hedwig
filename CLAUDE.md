# Hedwig - Research Note Management System

## Overview
Hedwig is a Python package for managing research notes, synchronizing with Notion, generating change summaries using LLM analysis, and distributing content through various messaging platforms.

## Installation
```bash
pip install -e .
```

## Configuration
Copy `config.yml.example` to `config.yml` and update with your settings:
- Notion API key
- Repository paths
- LLM API configuration
- Pipeline settings (title format for summaries)

## Commands

### Health Check
```bash
python -m hedwig health
python -m hedwig health --quick  # Skip API connectivity tests
python -m hedwig health --json   # Output as JSON for monitoring
```
Verifies all components are properly configured and operational. Recommended to run before first sync. Checks configuration, Git repository, dependencies, filesystem permissions, and API connectivity. Exit codes: 0=healthy, 1=degraded, 2=critical.

### Sync from Notion
```bash
python -m hedwig sync
```
Synchronizes research notes from Notion to local git repository.

### Sync User List
```bash
python -m hedwig sync-userlist
```
Retrieves the user list from Notion and saves it to a TSV file configured in `paths.userlist_file`. The TSV file contains user IDs and names. If `paths.userlist_override_file` is configured, users from that file will override or supplement the Notion user list, allowing for custom name mappings.

### Generate Change Summary
```bash
python -m hedwig generate-change-summary
python -m hedwig generate-change-summary --no-write  # Print to stdout without saving to file
```
Analyzes recent git changes and generates summaries using LLM. By default, saves summaries to `{change_summary_output}/YYYY/MM/YYYYMMDD-indiv.md`.

### Generate Overview
```bash
python -m hedwig generate-overview
python -m hedwig generate-overview --no-write  # Print to stdout without saving to file
python -m hedwig generate-overview --print-prompt  # Print the LLM prompt and input to stdout for debugging
```
Creates an overview summary from individual change summaries. Generates a team-focused summary with MVP highlights. By default, saves overview to `{change_summary_output}/YYYY/MM/YYYYMMDD-overview.md`.

The `--print-prompt` option is useful for debugging and understanding what's being sent to the LLM. It prints both the system prompt and the user input (individual summaries + external content) to stdout.

### Post Summary
```bash
python -m hedwig post-summary --summary-file FILE --overview-file FILE --title TITLE
```
Posts a summary to the configured messaging platform (e.g., Slack Canvas). The platform is configured via the `messaging` section in config.yml.

### Pipeline
```bash
python -m hedwig pipeline
```
Runs the complete summarizer pipeline automatically:
1. Generate change summaries from recent git commits
2. Generate overview summary from individual summaries
3. Post the summary to the configured messaging platform

The pipeline stops gracefully if there are no changes to report or if it's a day when no summary should be generated (e.g., Sunday for overviews).

## Testing
Before committing changes, run:
```bash
# Health check to verify system integrity
python -m hedwig health --config config.yml

# Type checking (if mypy is configured)
mypy hedwig/

# Linting (if configured)
pylint hedwig/
# or
ruff check hedwig/

# Tests (if test suite exists)
pytest tests/
```

## Key Features
- Automatic git repository initialization
- Configurable lookback days for missing sync checkpoints
- Weekday-based change summary time ranges
- Configurable overview language (ko: Korean, en: English, ja: Japanese, zh_CN: Simplified Chinese)
- Customizable LLM prompts for overview generation
- Modular architecture with separate concerns
- Graceful handling of edge cases (root commits, missing files)
- External content sources for enriching overview summaries

## Directory Structure
```
hedwig/
├── __init__.py
├── __main__.py
├── cli.py
├── notion/          # Notion sync functionality
├── change_summary/  # Change summary generation
├── overview/        # Overview summary generation
├── messaging/       # Messaging platform abstraction
│   ├── base.py     # Abstract interfaces
│   ├── factory.py  # Consumer factory
│   ├── manager.py  # High-level API
│   └── consumers/  # Platform implementations
│       └── slack.py
└── utils/           # Shared utilities
```

## Messaging Architecture
The messaging system uses a plugin architecture:
- `MessageConsumer`: Abstract base class for all messaging platforms
- `MessageConsumerFactory`: Creates consumers based on configuration
- `MessageManager`: High-level API for sending messages/documents
- Platform-specific implementations in `consumers/` directory

To add a new messaging platform:
1. Create a new consumer class inheriting from `MessageConsumer`
2. Implement required methods: `send_message()`, `send_document()`
3. Register it in `MessageConsumerFactory.CONSUMER_REGISTRY`
4. Add configuration section in config.yml

## External Content Sources

Hedwig supports including external Markdown files in overview generation to provide additional context for the LLM. This allows you to incorporate team discussions, meeting notes, or other relevant information alongside the individual change summaries.

### Configuration

Enable external content in your `config.yml`:

```yaml
overview:
  external_content:
    enabled: true
    sources:
      - name: "slack_conversations"
        file_suffix: "-slack.md"
        description: "Team discussions from Slack"
        required: false
      - name: "meeting_notes"
        file_suffix: "-meeting.md"
        description: "Meeting minutes and decisions"
        required: false
```

### Usage

Place Markdown files with the configured suffix in the summary directory:
- Location: `{change_summary_output}/YYYY/MM/YYYYMMDD{file_suffix}`
- Example: `/path/to/summaries/2025/07/20250721-slack.md`

The content from these files will be automatically included when generating the overview summary for that date.

### File Format

External content files should be in Markdown format. The content will be included in the overview generation under an "Additional Context" section with appropriate headings based on the configured description.