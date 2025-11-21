# Hedwig

Hedwig is a research note management system designed for research teams. It synchronizes Notion workspaces to Git repositories for version control and generates AI-powered daily summaries of research activities. The system creates both individual change summaries and team overview summaries with MVP highlights, then distributes them through messaging platforms like Slack.

## Features

- **Notion Synchronization**: Automatically sync research notes from Notion to a Git repository
- **AI-Powered Summaries**: Generate intelligent summaries of research changes using LLMs
- **Team Overviews**: Create consolidated team overviews with MVP highlights
- **Context Plugins**: Add contextual information (weather, calendar events) to overview summaries
- **Multi-Platform Messaging**: Distribute summaries through various messaging platforms (currently Slack)
- **Automated Pipeline**: Run the complete workflow with a single command
- **Flexible Configuration**: Customize prompts, models, and behavior through configuration

## Installation

Install Hedwig from PyPI:

```bash
pip install hedwiglab
```

Or install from source:

```bash
git clone https://github.com/ChangLabSNU/Hedwig
cd Hedwig
pip install -e .
```

## Quick Start

1. **Set up configuration**:
   ```bash
   # Download the example configuration
   curl -O https://raw.githubusercontent.com/ChangLabSNU/Hedwig/refs/heads/main/config.yml.example

   # Create your config file
   cp config.yml.example config.yml

   # Edit config.yml with your settings
   ```

2. **Configure API keys and etc**:
   ```yaml
   # In config.yml
   api:
     notion:
       api_key: 'your-notion-api-key'
     llm:
       key: 'your-gemini-api-key'
   messaging:
     slack:
       token: 'your-slack-bot-token'
   ```

3. **Check system health** (recommended before first sync):
   ```bash
   hedwig health --config config.yml
   ```
   This verifies that all components are properly configured and accessible.

4. **Sync Notion content**:
   ```bash
   hedwig sync
   ```

5. **Run the pipeline**:
   ```bash
   hedwig pipeline
   ```

## Workflow Overview

Hedwig follows a two-stage process:

```
┌─────────────┐
│   STAGE 1   │
│ Data Update │
└─────────────┘
      │
      ▼
┌─────────────┐
│ hedwig sync │ ─── Fetches latest research notes from Notion
└─────────────┘     and commits them to Git repository
      │
      │ (Run periodically or on-demand)
      │
      ▼
┌─────────────┐
│   STAGE 2   │
│  Pipeline   │
└─────────────┘
      │
      ▼
┌──────────────────────────┐
│ hedwig pipeline          │ ─── Automated 3-step process:
└──────────────────────────┘
      │
      ├─► generate-change-summary ─── Analyzes Git commits and creates
      │                               AI summaries of recent changes
      │
      ├─► generate-overview ──────── Consolidates individual summaries
      │                              into team-focused overview
      │
      └─► post-summary ───────────── Posts to messaging platform
                                     (e.g., Slack Canvas)
```

**Important**: The `sync` command must be run before the pipeline to ensure the Git repository has the latest Notion content. The sync is NOT part of the pipeline and should be scheduled separately.

## Commands

### `hedwig health`
Checks the health of all Hedwig components and dependencies. **Recommended to run before first sync** to ensure proper setup.

```bash
hedwig health [--config CONFIG] [--quick] [--json] [--quiet]
```

**Options:**
- `--config`: Configuration file path (default: `config.yml`)
- `--quick`: Skip API connectivity tests for faster results
- `--json`: Output results in JSON format for monitoring tools
- `--quiet`: Suppress informational messages

**Health Checks Include:**
- Configuration file validity and required keys
- Git repository status and permissions
- Python package dependencies
- Filesystem permissions and disk space
- API connectivity (Notion, LLM, Slack) unless `--quick` is used

**Exit Codes:**
- `0`: All checks passed (HEALTHY)
- `1`: Some non-critical checks failed (DEGRADED)
- `2`: Critical checks failed (CRITICAL)

**Example Usage:**
```bash
# Full health check before first sync
hedwig health --config config.yml

# Quick check (skip API tests)
hedwig health --quick

# JSON output for monitoring
hedwig health --json | jq '.overall_status'
```

### `hedwig sync`
Synchronizes Notion pages to a Git repository.

```bash
hedwig sync [--config CONFIG] [--quiet] [--verbose]
```

**Options:**
- `--config`: Configuration file path (default: `config.yml`)
- `--quiet`: Suppress progress messages
- `--verbose`: Show detailed debug output

### `hedwig sync-userlist`
Manually syncs user list from Notion and saves to TSV file. This command is typically not needed in regular workflows as it's automatically triggered when unknown users are encountered.

```bash
hedwig sync-userlist [--config CONFIG] [--quiet]
```

**Options:**
- `--config`: Configuration file path (default: `config.yml`)
- `--quiet`: Suppress progress messages

**Output:**
Creates a TSV file at the path specified in `paths.userlist_file` containing:
- `user_id`: Notion user UUID
- `name`: User's display name

**Override Feature:**
If `paths.userlist_override_file` is configured and the file exists, users from this file will override or supplement the Notion user list. This is useful for:
- Correcting names that appear incorrectly in Notion
- Adding custom display names for specific users
- Including users that may not be in the Notion workspace

The override file should have the same TSV format as the output file.

**Note:** With auto-sync enabled (default), this command is automatically run when `generate-change-summary` encounters unknown user IDs.

### `hedwig generate-change-summary`
Analyzes recent Git commits and generates AI-powered summaries.

```bash
hedwig generate-change-summary [--config CONFIG] [--no-write]
```

**Options:**
- `--config`: Configuration file path (default: `config.yml`)
- `--no-write`: Print to stdout instead of saving to file

**Auto User Sync:**
When `change_summary.auto_sync_userlist` is set to `true` (default), the command will automatically run `sync-userlist` if it encounters user IDs not found in the user list. This ensures that new team members are automatically added to the user list. Set to `false` to disable this behavior.

### `hedwig generate-overview`
Creates team-focused overview summaries from individual change summaries.

```bash
hedwig generate-overview [--config CONFIG] [--no-write]
```

**Options:**
- `--config`: Configuration file path (default: `config.yml`)
- `--no-write`: Print to stdout instead of saving to file

### `hedwig post-summary`
Posts summaries to configured messaging platforms.

```bash
hedwig post-summary --summary-file FILE --overview-file FILE --title TITLE [--config CONFIG]
```

**Options:**
- `--summary-file`: Path to the markdown summary file
- `--overview-file`: Path to the overview message file
- `--title`: Title for the posted summary
- `--config`: Configuration file path (default: `config.yml`)

### `hedwig pipeline`
Runs the complete summarization pipeline automatically.

```bash
hedwig pipeline [--config CONFIG] [--no-posting] [--quiet]
```

**Options:**
- `--config`: Configuration file path (default: `config.yml`)
- `--no-posting`: Skip posting the generated summaries to messaging platforms
- `--quiet`: Suppress informational messages during execution

Structured JSONL logs are generated automatically when `overview.jsonl_output.enabled` is set to `true` in `config.yml`.

**Note**: This command does NOT include syncing from Notion. Run `hedwig sync` separately before the pipeline to ensure the Git repository is up-to-date.

## Configuration

Hedwig uses a YAML configuration file. Download the example configuration and customize:

```bash
curl -O https://raw.githubusercontent.com/ChangLabSNU/Hedwig/refs/heads/main/config.yml.example
cp config.yml.example config.yml
```

### Essential Settings

```yaml
# Repository paths
paths:
  notes_repository: '/path/to/your/notes/repo'
  change_summary_output: '/path/to/summary/output'

# API Keys (can be set here OR as environment variables)
notion:
  api_key: 'your-notion-api-key'  # Alternative: export NOTION_API_KEY=...

api:
  llm:
    key: 'your-gemini-api-key'    # Alternative: export GEMINI_API_KEY=...
    url: 'https://generativelanguage.googleapis.com/v1beta/openai/'

messaging:
  slack:
    token: 'xoxb-your-bot-token'  # Alternative: export SLACK_TOKEN=...
```

### Key Configuration Options

- **Sync Settings**: Checkpoint tracking, timezone, lookback days
- **Summary Settings**: Model selection, prompt customization, diff length limits
- **Overview Settings**: Language selection, lab information, weekday configurations
- **Messaging Settings**: Platform selection, channel configuration
- **Pipeline Settings**: Title format customization

See `config.yml.example` for all available options with detailed comments.

## Automated Execution

Set up cron jobs for the two-stage process:

```bash
# Sync from Notion every hour during work hours
0 * * * * /usr/bin/hedwig sync --config /path/to/config.yml

# Run pipeline everyday except Sunday at 8:30 AM
30 8 * * 1-6 /usr/bin/hedwig pipeline --config /path/to/config.yml
```

## Messaging Platforms

### Slack Integration

Hedwig creates Canvas documents in Slack for rich formatting:

1. Create a Slack app with required permissions:
   - `channels:read`
   - `chat:write`
   - `canvases:write`
   - `canvases:read`

2. Install the app to your workspace

3. Configure in `config.yml`:
   ```yaml
   messaging:
     active: slack
     slack:
       token: 'xoxb-your-bot-token'
       channel_id: 'C12345678'
   ```

## Advanced Usage

### Custom Prompts

Customize LLM prompts for summaries:

```yaml
api:
  llm:
    diff_summary_prompt: |
      Your custom prompt for analyzing diffs...

    overview_prompt_template: |
      Your custom overview template with {summary_range} and {forthcoming_range}...
    
    # Customize how context information is introduced in the prompt
    overview_context_information_prefix: |
      Use the following context information minimally only at the appropriate places in the summary, and do not repeat the context information verbatim.
```

### Changing Language

Set overview language and customize instructions:

```yaml
overview:
  language: en  # Options: ko, en, ja, zh_CN
  lab_info: "Your Lab Name and Description"
```

### Context Plugins

Context plugins provide additional contextual information in overview summaries. This helps the AI generate more relevant and timely summaries by providing context about current conditions.

#### Date Plugin

Provides the current date and weekday:

```yaml
overview:
  context_plugins:
    date:
      enabled: true
```

Outputs: `Today: 2025-07-19 (Friday)`

This simple plugin helps the AI understand what day it is when generating summaries, which can be useful for contextual references.

#### Static Plugin

Provides fixed context information that remains constant across all summaries. Perfect for laboratory-specific information:

```yaml
overview:
  context_plugins:
    static:
      enabled: true
      content: |
        Laboratory: Computational Biology Lab
        Research Areas: Genomics, RNA Biology, Bioinformatics
        Current Projects:
        - Single-cell RNA sequencing analysis
        - Alternative splicing in cancer
        - Long-read sequencing methods
        Team Members:
        - Dr. Jane Smith (PI) - Computational genomics
        - Dr. John Doe - Machine learning for biology
        - Alice Johnson - RNA-seq analysis
        - Bob Wilson - Proteomics integration
```

**Use cases:**
- Laboratory information and research focus
- Current research topics and projects
- Team member list and expertise
- Laboratory policies or guidelines
- Any other static context that helps AI generate better summaries

The content is passed directly to the LLM without modification, allowing full control over the formatting and information structure.

#### Weather Plugin

Adds weather information to the overview prompt:

```yaml
overview:
  context_plugins:
    weather:
      enabled: true
      latitude: 37.5665      # Your location's latitude
      longitude: 126.9780    # Your location's longitude
      city_name: Seoul       # Display name for the location
```

The weather plugin fetches data from Open-Meteo API and includes:
- Yesterday's weather
- Today's weather
- Tomorrow's weather forecast

#### Calendar Plugin

Adds calendar events to provide context about holidays, meetings, or important dates:

```yaml
overview:
  context_plugins:
    calendar:
      enabled: true
      days_before: 1  # Include events from 1 day ago (0 = today only)
      days_after: 7   # Include events up to 7 days ahead
      calendars:
        # iCal example (public calendars)
        - name: Korean Holidays
          type: ical
          url: https://calendar.google.com/calendar/ical/ko.south_korea%23holiday%40group.v.calendar.google.com/public/basic.ics
          enabled: true
        
        # CalDAV example (private calendars, requires authentication)
        - name: Team Calendar
          type: caldav
          url: https://nextcloud.example.com/remote.php/dav/
          username: your-username  # Or use env var CALDAV_USERNAME
          password: your-password  # Or use env var CALDAV_PASSWORD
          calendar_url: https://nextcloud.example.com/remote.php/dav/calendars/user/personal/  # Optional
          enabled: true
```

**Features:**
- Supports both iCal (public) and CalDAV (private) calendars
- Multiple calendars can be configured
- Events are grouped by time periods (today, this week, next week, later)
- Calendars with no events are automatically suppressed from output
- CalDAV requires `pip install caldav` for authentication support

#### Custom Context Plugins

You can create custom context plugins by:

1. Creating a new Python file in `Hedwig/overview/context_plugins/`
2. Inheriting from `ContextPlugin` base class
3. Implementing the required methods:
   - `name` property: Unique identifier for your plugin
   - `get_context()` method: Returns the context string or None

Example custom plugin structure:
```python
from .base import ContextPlugin
from .registry import ContextPluginRegistry

class MyCustomPlugin(ContextPlugin):
    @property
    def name(self) -> str:
        return "custom"
    
    def get_context(self) -> Optional[str]:
        if not self.is_enabled():
            return None
        # Your logic here
        return "Your context information"

# Register the plugin
ContextPluginRegistry.register("custom", MyCustomPlugin)
```

## Troubleshooting

### Common Issues

1. **Configuration problems**: Run `hedwig health` to diagnose configuration issues
2. **No summaries generated**: Check if there are recent commits within the lookback period
3. **Sync failures**: Verify Notion API key and page permissions
4. **LLM errors**: Check API key and rate limits
5. **Messaging failures**: Verify bot token and channel permissions

### First-Time Setup Issues

If you encounter problems during initial setup, run the health check:

```bash
hedwig health --config config.yml
```

This will identify:
- Missing or invalid configuration
- Permission issues
- Missing dependencies
- API connectivity problems

### Debug Mode

Run with verbose output for troubleshooting:

```bash
hedwig pipeline --config config.yml --verbose
```

### Logs

Check application logs for detailed error messages. The location depends on your configuration.

## License

MIT License - see LICENSE.txt for details

## Author

Hyeshik Chang <hyeshik@snu.ac.kr>
