#!/usr/bin/env python3
import argparse, os, sys, json, requests
from pathlib import Path

CONFIG = Path.home() / ".runway.json"

def load_config():
    if CONFIG.exists():
        for k, v in json.loads(CONFIG.read_text()).items():
            os.environ.setdefault(f"PLANE_{k.upper()}", v)
        return
    for p in [Path.cwd() / ".env", Path(__file__).parent / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return

def configure():
    print("Runway Configuration\n" + "=" * 40)
    existing = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    config = {
        "api_key": input(f"API Key [{existing.get('api_key', '')[:8]}...]: ").strip() or existing.get("api_key", ""),
        "base_url": input(f"Base URL [{existing.get('base_url', 'https://api.plane.so')}]: ").strip() or existing.get("base_url", "https://api.plane.so"),
        "workspace": input(f"Workspace [{existing.get('workspace', '')}]: ").strip() or existing.get("workspace", ""),
        "project_id": input(f"Project ID [{existing.get('project_id', '')}]: ").strip() or existing.get("project_id", ""),
    }
    if not all([config["api_key"], config["workspace"], config["project_id"]]):
        sys.exit("Error: api_key, workspace, and project_id required")
    CONFIG.write_text(json.dumps(config, indent=2))
    CONFIG.chmod(0o600)
    print(f"\n✓ Saved to {CONFIG}")

class PlaneClient:
    def __init__(self):
        load_config()
        self.api_key = os.environ.get("PLANE_API_KEY")
        self.base_url = os.environ.get("PLANE_BASE_URL", "https://api.plane.so")
        self.workspace = os.environ.get("PLANE_WORKSPACE")
        self.project_id = os.environ.get("PLANE_PROJECT_ID")
        if not self.api_key or not self.project_id:
            sys.exit("Not configured. Run: runway --configure")

    def _headers(self):
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def _issues_url(self):
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}/projects/{self.project_id}/issues"

    def _cycles_url(self):
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}/projects/{self.project_id}/cycles"

    def _resolve_id(self, partial, items):
        if len(partial) == 36:
            return partial
        for item in items:
            if item["id"].startswith(partial):
                return item["id"]
        return partial

    def _get_results(self, data):
        return data.get("results", data) if isinstance(data, dict) else data

    def list_issues(self, limit=20):
        r = requests.get(f"{self._issues_url()}/", headers=self._headers(), params={"per_page": limit})
        r.raise_for_status()
        return self._get_results(r.json())

    def get_issue(self, issue_id):
        full_id = self._resolve_id(issue_id, self.list_issues(100))
        r = requests.get(f"{self._issues_url()}/{full_id}/", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_issue(self, name, description="", priority=None, parent=None):
        data = {"name": name}
        if description: data["description_html"] = f"<p>{description}</p>"
        if priority: data["priority"] = priority
        if parent: data["parent"] = self._resolve_id(parent, self.list_issues(100))
        r = requests.post(f"{self._issues_url()}/", headers=self._headers(), json=data)
        r.raise_for_status()
        return r.json()

    def update_issue(self, issue_id, **kwargs):
        full_id = self._resolve_id(issue_id, self.list_issues(100))
        r = requests.patch(f"{self._issues_url()}/{full_id}/", headers=self._headers(), json=kwargs)
        r.raise_for_status()
        return r.json()

    def delete_issue(self, issue_id):
        full_id = self._resolve_id(issue_id, self.list_issues(100))
        requests.delete(f"{self._issues_url()}/{full_id}/", headers=self._headers()).raise_for_status()
        return full_id

    def list_cycles(self):
        r = requests.get(f"{self._cycles_url()}/", headers=self._headers())
        r.raise_for_status()
        return self._get_results(r.json())

    def get_cycle(self, cycle_id):
        full_id = self._resolve_id(cycle_id, self.list_cycles())
        r = requests.get(f"{self._cycles_url()}/{full_id}/", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_cycle(self, name, description="", start_date=None, end_date=None):
        data = {"name": name}
        if description: data["description"] = description
        if start_date: data["start_date"] = start_date
        if end_date: data["end_date"] = end_date
        r = requests.post(f"{self._cycles_url()}/", headers=self._headers(), json=data)
        r.raise_for_status()
        return r.json()

    def update_cycle(self, cycle_id, **kwargs):
        full_id = self._resolve_id(cycle_id, self.list_cycles())
        r = requests.patch(f"{self._cycles_url()}/{full_id}/", headers=self._headers(), json=kwargs)
        r.raise_for_status()
        return r.json()

    def delete_cycle(self, cycle_id):
        full_id = self._resolve_id(cycle_id, self.list_cycles())
        requests.delete(f"{self._cycles_url()}/{full_id}/", headers=self._headers()).raise_for_status()
        return full_id

    def cycle_add_issue(self, cycle_id, issue_id):
        cid = self._resolve_id(cycle_id, self.list_cycles())
        iid = self._resolve_id(issue_id, self.list_issues(100))
        r = requests.post(f"{self._cycles_url()}/{cid}/cycle-issues/", headers=self._headers(), json={"issues": [iid]})
        r.raise_for_status()

    def cycle_remove_issue(self, cycle_id, issue_id):
        cid = self._resolve_id(cycle_id, self.list_cycles())
        iid = self._resolve_id(issue_id, self.list_issues(100))
        requests.delete(f"{self._cycles_url()}/{cid}/cycle-issues/{iid}/", headers=self._headers()).raise_for_status()

def main():
    p = argparse.ArgumentParser(prog="runway")
    p.add_argument("--configure", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("list").add_argument("-l", "--limit", type=int, default=20)
    sub.add_parser("get").add_argument("id")
    c = sub.add_parser("create")
    c.add_argument("-t", "--title", required=True)
    c.add_argument("-d", "--description", default="")
    c.add_argument("-p", "--priority", choices=["none", "low", "medium", "high", "urgent"])
    c.add_argument("--parent")
    sub.add_parser("quick").add_argument("title")
    u = sub.add_parser("update")
    u.add_argument("id")
    u.add_argument("-t", "--title")
    u.add_argument("-p", "--priority", choices=["none", "low", "medium", "high", "urgent"])
    u.add_argument("--parent")
    u.add_argument("--no-parent", action="store_true")
    d = sub.add_parser("delete")
    d.add_argument("id")
    d.add_argument("-f", "--force", action="store_true")

    sub.add_parser("cycles")
    sub.add_parser("cycle-get").add_argument("id")
    cc = sub.add_parser("cycle-create")
    cc.add_argument("-n", "--name", required=True)
    cc.add_argument("-d", "--description", default="")
    cc.add_argument("-s", "--start")
    cc.add_argument("-e", "--end")
    cu = sub.add_parser("cycle-update")
    cu.add_argument("id")
    cu.add_argument("-n", "--name")
    cu.add_argument("-d", "--description")
    cu.add_argument("-s", "--start")
    cu.add_argument("-e", "--end")
    cd = sub.add_parser("cycle-delete")
    cd.add_argument("id")
    cd.add_argument("-f", "--force", action="store_true")
    ca = sub.add_parser("cycle-add-issue")
    ca.add_argument("cycle_id")
    ca.add_argument("issue_id")
    cr = sub.add_parser("cycle-remove-issue")
    cr.add_argument("cycle_id")
    cr.add_argument("issue_id")

    args = p.parse_args()
    if args.configure:
        return configure()
    if not args.cmd:
        return p.print_help()

    client = PlaneClient()
    try:
        if args.cmd == "list":
            for i in client.list_issues(args.limit):
                icon = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(i.get("priority"), "⚪")
                print(f"{icon} [{i['id'][:8]}] {i['name']}")
        elif args.cmd == "get":
            print(json.dumps(client.get_issue(args.id), indent=2))
        elif args.cmd == "create":
            i = client.create_issue(args.title, args.description, args.priority, args.parent)
            print(f"✓ [{i['id'][:8]}] {i['name']}")
        elif args.cmd == "quick":
            i = client.create_issue(args.title)
            print(f"✓ [{i['id'][:8]}] {i['name']}")
        elif args.cmd == "update":
            updates = {}
            if args.title: updates["name"] = args.title
            if args.priority: updates["priority"] = args.priority
            if args.parent: updates["parent"] = client._resolve_id(args.parent, client.list_issues(100))
            if args.no_parent: updates["parent"] = None
            if not updates: sys.exit("No updates specified")
            i = client.update_issue(args.id, **updates)
            print(f"✓ [{i['id'][:8]}] {i['name']}")
        elif args.cmd == "delete":
            if not args.force and input(f"Delete {args.id}? [y/N] ").lower() != "y":
                sys.exit("Aborted")
            client.delete_issue(args.id)
            print(f"✓ Deleted {args.id}")
        elif args.cmd == "cycles":
            for c in client.list_cycles():
                print(f"🔄 [{c['id'][:8]}] {c['name']} ({c.get('start_date', 'N/A')} → {c.get('end_date', 'N/A')})")
        elif args.cmd == "cycle-get":
            print(json.dumps(client.get_cycle(args.id), indent=2))
        elif args.cmd == "cycle-create":
            c = client.create_cycle(args.name, args.description, args.start, args.end)
            print(f"✓ [{c['id'][:8]}] {c['name']}")
        elif args.cmd == "cycle-update":
            updates = {}
            if args.name: updates["name"] = args.name
            if args.description: updates["description"] = args.description
            if args.start: updates["start_date"] = args.start
            if args.end: updates["end_date"] = args.end
            if not updates: sys.exit("No updates specified")
            c = client.update_cycle(args.id, **updates)
            print(f"✓ [{c['id'][:8]}] {c['name']}")
        elif args.cmd == "cycle-delete":
            if not args.force and input(f"Delete {args.id}? [y/N] ").lower() != "y":
                sys.exit("Aborted")
            client.delete_cycle(args.id)
            print(f"✓ Deleted {args.id}")
        elif args.cmd == "cycle-add-issue":
            client.cycle_add_issue(args.cycle_id, args.issue_id)
            print(f"✓ Added {args.issue_id} to {args.cycle_id}")
        elif args.cmd == "cycle-remove-issue":
            client.cycle_remove_issue(args.cycle_id, args.issue_id)
            print(f"✓ Removed {args.issue_id} from {args.cycle_id}")
    except requests.HTTPError as e:
        sys.exit(f"API Error: {e.response.status_code} - {e.response.text}")

if __name__ == "__main__":
    main()
