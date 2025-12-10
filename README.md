# Runway

CLI for Plane project management.

## Install

```
pip install -e .
```

## Configure

```
runway --configure
```

You'll need your API key, workspace slug, and project ID from Plane.

Or create `~/.runway.json`:

```json
{
  "api_key": "your-api-key",
  "base_url": "https://api.plane.so",
  "workspace": "your-workspace",
  "project_id": "your-project-uuid"
}
```

## Usage

```bash
# Issues
runway list                     # list 20 most recent issues
runway list -a                  # list ALL issues
runway list -l 50               # list 50 issues
runway list -p high             # list only high priority
runway list -a -p none          # list all unprioritized issues
runway stats                    # show priority breakdown
runway get <id>                 # get issue details
runway create -t "Title"        # create issue
runway quick "Title"            # quick create
runway update <id> -p high      # update priority
runway update <id> -s done      # update state
runway update <id> --parent <p> # set parent issue
runway delete <id>              # delete issue

# Cycles
runway cycles                   # list cycles
runway cycle-get <id>           # get cycle details
runway cycle-create -n "Name"   # create cycle
runway cycle-update <id> -n "X" # update cycle
runway cycle-delete <id>        # delete cycle
runway cycle-add-issue <c> <i>  # add issue to cycle
runway cycle-remove-issue <c> <i>

# Modules
runway modules                  # list modules
runway module-get <id>          # get module details
runway module-create -n "Name"  # create module
runway module-update <id> -n "X"# update module
runway module-delete <id>       # delete module
runway module-add-issue <m> <i> # add issue to module
runway module-remove-issue <m> <i>
```

Partial IDs work (first 8 chars).

## Options

**Issues:** `-t` title, `-d` description, `-p` priority (none/low/medium/high/urgent), `-s` state (backlog/todo/in-progress/done/cancelled), `--parent` parent ID

**Cycles:** `-n` name, `-d` description, `-s` start date, `-e` end date (YYYY-MM-DD)

**Modules:** `-n` name, `-d` description, `-s` start date, `-t` target date (YYYY-MM-DD)

**List:** `-l/--limit` count, `-a/--all` for all, `-p/--priority` filter
