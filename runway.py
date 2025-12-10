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
    # State name to ID mapping (fetched once)
    _states_cache = None
    
    def __init__(self):
        load_config()
        self.api_key = os.environ.get("PLANE_API_KEY")
        self.base_url = os.environ.get("PLANE_BASE_URL", "https://api.plane.so")
        self.workspace = os.environ.get("PLANE_WORKSPACE")
        self.project_id = os.environ.get("PLANE_PROJECT_ID")
        if not self.api_key or not self.project_id:
            sys.exit("Not configured. Run: runway --configure")
        self._issues_cache = None  # Cache for ID resolution

    def _headers(self):
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    def _issues_url(self):
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}/projects/{self.project_id}/issues"

    def _cycles_url(self):
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}/projects/{self.project_id}/cycles"

    def _modules_url(self):
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}/projects/{self.project_id}/modules"

    def _states_url(self):
        return f"{self.base_url}/api/v1/workspaces/{self.workspace}/projects/{self.project_id}/states"

    def _get_state_id(self, state_name):
        """Get state UUID from friendly name."""
        if PlaneClient._states_cache is None:
            r = requests.get(f"{self._states_url()}/", headers=self._headers())
            r.raise_for_status()
            PlaneClient._states_cache = {s["name"].lower().replace(" ", "-"): s["id"] for s in r.json().get("results", [])}
        return PlaneClient._states_cache.get(state_name)

    def _resolve_id(self, partial, items=None):
        """Resolve partial ID to full UUID. Uses cached issues if items not provided."""
        if len(partial) == 36:
            return partial
        if items is None:
            if self._issues_cache is None:
                self._issues_cache = self.list_issues(500)  # Fetch all for resolution
            items = self._issues_cache
        for item in items:
            if item["id"].startswith(partial):
                return item["id"]
        return partial

    def _get_results(self, data):
        return data.get("results", data) if isinstance(data, dict) else data

    def _clear_cache(self):
        """Clear issues cache after modifications."""
        self._issues_cache = None

    def list_issues(self, limit=20):
        r = requests.get(f"{self._issues_url()}/", headers=self._headers(), params={"per_page": limit})
        r.raise_for_status()
        return self._get_results(r.json())

    def get_issue(self, issue_id):
        full_id = self._resolve_id(issue_id)
        r = requests.get(f"{self._issues_url()}/{full_id}/", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_issue(self, name, description="", priority=None, parent=None):
        data = {"name": name}
        if description: data["description_html"] = f"<p>{description}</p>"
        if priority: data["priority"] = priority
        if parent: data["parent"] = self._resolve_id(parent)
        r = requests.post(f"{self._issues_url()}/", headers=self._headers(), json=data)
        r.raise_for_status()
        self._clear_cache()
        return r.json()

    def update_issue(self, issue_id, **kwargs):
        full_id = self._resolve_id(issue_id)
        r = requests.patch(f"{self._issues_url()}/{full_id}/", headers=self._headers(), json=kwargs)
        r.raise_for_status()
        self._clear_cache()
        return r.json()

    def delete_issue(self, issue_id):
        full_id = self._resolve_id(issue_id)
        requests.delete(f"{self._issues_url()}/{full_id}/", headers=self._headers()).raise_for_status()
        self._clear_cache()
        return full_id

    def batch_update_priority(self, priority_map):
        """Batch update priorities. priority_map: {partial_id: priority}"""
        issues = self.list_issues(500)
        updated = 0
        for issue in issues:
            for partial, priority in priority_map.items():
                if issue["id"].startswith(partial):
                    try:
                        r = requests.patch(
                            f"{self._issues_url()}/{issue['id']}/",
                            headers=self._headers(),
                            json={"priority": priority}
                        )
                        r.raise_for_status()
                        updated += 1
                        yield issue, priority, True
                    except requests.HTTPError as e:
                        yield issue, priority, False
                    break
        self._clear_cache()

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
        data = {"name": name, "project_id": self.project_id}
        # Get owner from first issue
        issues = self.list_issues(1)
        if issues:
            data["owned_by"] = issues[0].get("created_by")
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
        iid = self._resolve_id(issue_id)
        r = requests.post(f"{self._cycles_url()}/{cid}/cycle-issues/", headers=self._headers(), json={"issues": [iid]})
        r.raise_for_status()

    def cycle_remove_issue(self, cycle_id, issue_id):
        cid = self._resolve_id(cycle_id, self.list_cycles())
        iid = self._resolve_id(issue_id)
        requests.delete(f"{self._cycles_url()}/{cid}/cycle-issues/{iid}/", headers=self._headers()).raise_for_status()

    def list_modules(self):
        r = requests.get(f"{self._modules_url()}/", headers=self._headers())
        r.raise_for_status()
        return self._get_results(r.json())

    def get_module(self, module_id):
        full_id = self._resolve_id(module_id, self.list_modules())
        r = requests.get(f"{self._modules_url()}/{full_id}/", headers=self._headers())
        r.raise_for_status()
        return r.json()

    def create_module(self, name, description="", start_date=None, target_date=None):
        data = {"name": name}
        if description: data["description"] = description
        if start_date: data["start_date"] = start_date
        if target_date: data["target_date"] = target_date
        r = requests.post(f"{self._modules_url()}/", headers=self._headers(), json=data)
        r.raise_for_status()
        return r.json()

    def update_module(self, module_id, **kwargs):
        full_id = self._resolve_id(module_id, self.list_modules())
        r = requests.patch(f"{self._modules_url()}/{full_id}/", headers=self._headers(), json=kwargs)
        r.raise_for_status()
        return r.json()

    def delete_module(self, module_id):
        full_id = self._resolve_id(module_id, self.list_modules())
        requests.delete(f"{self._modules_url()}/{full_id}/", headers=self._headers()).raise_for_status()
        return full_id

    def module_add_issue(self, module_id, issue_id):
        mid = self._resolve_id(module_id, self.list_modules())
        iid = self._resolve_id(issue_id)
        r = requests.post(f"{self._modules_url()}/{mid}/module-issues/", headers=self._headers(), json={"issues": [iid]})
        r.raise_for_status()

    def module_remove_issue(self, module_id, issue_id):
        mid = self._resolve_id(module_id, self.list_modules())
        iid = self._resolve_id(issue_id)
        requests.delete(f"{self._modules_url()}/{mid}/module-issues/{iid}/", headers=self._headers()).raise_for_status()

def main():
    p = argparse.ArgumentParser(prog="runway")
    p.add_argument("--configure", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    ls = sub.add_parser("list", help="List issues")
    ls.add_argument("-l", "--limit", type=int, default=20, help="Number of issues (use -1 or 'all' for all)")
    ls.add_argument("-a", "--all", action="store_true", help="List all issues")
    ls.add_argument("--priority", "-p", choices=["none", "low", "medium", "high", "urgent"], help="Filter by priority")
    sub.add_parser("stats", help="Show issue statistics")
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
    u.add_argument("-s", "--state", choices=["backlog", "todo", "in-progress", "done", "cancelled"])
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

    # Module commands
    sub.add_parser("modules")
    sub.add_parser("module-get").add_argument("id")
    mc = sub.add_parser("module-create")
    mc.add_argument("-n", "--name", required=True)
    mc.add_argument("-d", "--description", default="")
    mc.add_argument("-s", "--start")
    mc.add_argument("-t", "--target")
    mu = sub.add_parser("module-update")
    mu.add_argument("id")
    mu.add_argument("-n", "--name")
    mu.add_argument("-d", "--description")
    mu.add_argument("-s", "--start")
    mu.add_argument("-t", "--target")
    md = sub.add_parser("module-delete")
    md.add_argument("id")
    md.add_argument("-f", "--force", action="store_true")
    ma = sub.add_parser("module-add-issue")
    ma.add_argument("module_id")
    ma.add_argument("issue_id")
    mr = sub.add_parser("module-remove-issue")
    mr.add_argument("module_id")
    mr.add_argument("issue_id")

    args = p.parse_args()
    if args.configure:
        return configure()
    if not args.cmd:
        return p.print_help()

    client = PlaneClient()
    try:
        if args.cmd == "list":
            limit = 500 if args.all or args.limit == -1 else args.limit
            issues = client.list_issues(limit)
            if args.priority:
                issues = [i for i in issues if i.get("priority") == args.priority]
            for i in issues:
                icon = {"urgent": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(i.get("priority"), "⚪")
                print(f"{icon} [{i['id'][:8]}] {i['name']}")
            if args.all:
                print(f"\n{len(issues)} issues total")
        elif args.cmd == "stats":
            issues = client.list_issues(500)
            cycles = client.list_cycles()
            counts = {"urgent": 0, "high": 0, "medium": 0, "low": 0, "none": 0}
            for i in issues:
                p = i.get("priority") or "none"
                counts[p] = counts.get(p, 0) + 1
            print(f"📊 Issue Statistics")
            print(f"   Total: {len(issues)} issues, {len(cycles)} cycles")
            print(f"   🔴 Urgent: {counts['urgent']}")
            print(f"   🟠 High:   {counts['high']}")
            print(f"   🟡 Medium: {counts['medium']}")
            print(f"   🟢 Low:    {counts['low']}")
            print(f"   ⚪ None:   {counts['none']}")
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
            if args.state:
                state_id = client._get_state_id(args.state)
                if state_id: updates["state"] = state_id
            if args.parent: updates["parent"] = client._resolve_id(args.parent)
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
        elif args.cmd == "modules":
            for m in client.list_modules():
                print(f"📦 [{m['id'][:8]}] {m['name']} ({m.get('start_date', 'N/A')} → {m.get('target_date', 'N/A')})")
        elif args.cmd == "module-get":
            print(json.dumps(client.get_module(args.id), indent=2))
        elif args.cmd == "module-create":
            m = client.create_module(args.name, args.description, args.start, args.target)
            print(f"✓ [{m['id'][:8]}] {m['name']}")
        elif args.cmd == "module-update":
            updates = {}
            if args.name: updates["name"] = args.name
            if args.description: updates["description"] = args.description
            if args.start: updates["start_date"] = args.start
            if args.target: updates["target_date"] = args.target
            if not updates: sys.exit("No updates specified")
            m = client.update_module(args.id, **updates)
            print(f"✓ [{m['id'][:8]}] {m['name']}")
        elif args.cmd == "module-delete":
            if not args.force and input(f"Delete {args.id}? [y/N] ").lower() != "y":
                sys.exit("Aborted")
            client.delete_module(args.id)
            print(f"✓ Deleted {args.id}")
        elif args.cmd == "module-add-issue":
            client.module_add_issue(args.module_id, args.issue_id)
            print(f"✓ Added {args.issue_id} to module {args.module_id}")
        elif args.cmd == "module-remove-issue":
            client.module_remove_issue(args.module_id, args.issue_id)
            print(f"✓ Removed {args.issue_id} from module {args.module_id}")
    except requests.HTTPError as e:
        sys.exit(f"API Error: {e.response.status_code} - {e.response.text}")

if __name__ == "__main__":
    main()
