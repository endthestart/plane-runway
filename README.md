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

```
runway list                     # list issues
runway get <id>                 # get issue details
runway create -t "Title"        # create issue
runway quick "Title"            # quick create
runway update <id> -t "New"     # update issue
runway delete <id>              # delete issue

runway cycles                   # list cycles
runway cycle-create -n "Name"   # create cycle
runway cycle-add-issue <c> <i>  # add issue to cycle
```

Partial IDs work (first 8 chars).

## Options

Issues: `-t` title, `-d` description, `-p` priority (none/low/medium/high/urgent), `--parent` parent ID

Cycles: `-n` name, `-d` description, `-s` start date, `-e` end date (YYYY-MM-DD)
