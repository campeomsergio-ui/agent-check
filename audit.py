#!/usr/bin/env python3
"""Agent reliability audit: reads a project's Claude Code / agent setup from disk and writes a one-page report.

Usage: python3 audit.py [PROJECT_DIR] [--out report.md] [--no-user]
Also reads your user-level ~/.claude/settings.json unless --no-user is given.
Reads files only. Never runs hooks, MCP servers or project code, and never prints secret values.
"""
import json, os, re, shlex, shutil, subprocess, sys
from pathlib import Path

HIGH, MEDIUM, LOW = "high", "medium", "low"
SECRET_PATTERNS = {
    "Anthropic API key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "OpenAI API key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{32,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "Private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "out"}
BROAD_ALLOW = re.compile(r"^(?:Bash|Bash\(\*\)|Bash\(\s*\*?\s*:\*\)|\*|Write|Edit|WebFetch)$")
INTERPRETERS = {"python", "python3", "node", "bash", "sh", "zsh", "ruby", "perl", "deno", "bun"}
DANGEROUS_ALLOW = re.compile(r"Bash\((?:rm|sudo|curl|wget|git push|chmod|ssh)\b")


def finding(sev, area, title, detail, fix):
    return {"severity": sev, "area": area, "title": title, "detail": detail, "fix": fix}


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, None
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, str(e)


def project_files(root):
    """Tracked files if this is a git repo, otherwise a bounded walk."""
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, timeout=20, check=True).stdout
        return [root / p for p in out.decode().split("\0") if p]
    except (subprocess.SubprocessError, FileNotFoundError):
        files = []
        for d, dirs, names in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            files += [Path(d) / n for n in names]
            if len(files) > 20000:
                break
        return files


def check_settings(root, home=None):
    out = []
    targets = [(rel, root / rel) for rel in (".claude/settings.json", ".claude/settings.local.json")]
    if home is not None:
        targets.append(("~/.claude/settings.json", Path(home) / ".claude/settings.json"))
    for rel, path in targets:
        data, err = load_json(path)
        if err:
            out.append(finding(HIGH, "Settings", f"{rel} is not valid JSON", err[:120], "Fix the JSON; Claude Code ignores a settings file it cannot parse."))
            continue
        if not data:
            continue
        if not isinstance(data, dict):
            out.append(finding(HIGH, "Settings", f"{rel} is not a settings object", "The file holds a list or value, not {...}.", "Wrap the settings in a JSON object; Claude Code can't read this shape."))
            continue
        perms = data.get("permissions") or {}
        if perms.get("defaultMode") == "bypassPermissions":
            out.append(finding(HIGH, "Permissions", f"{rel} skips all permission prompts", "defaultMode is bypassPermissions.", "Use acceptEdits or default, and allow the specific commands you need."))
        allow = perms.get("allow") or []
        broad = [a for a in allow if BROAD_ALLOW.match(str(a).strip())]
        if broad:
            out.append(finding(HIGH, "Permissions", f"{rel} allows whole tools without limits", ", ".join(broad), "Replace with narrow rules such as Bash(npm test:*)."))
        risky = [a for a in allow if DANGEROUS_ALLOW.search(str(a))]
        if risky:
            out.append(finding(MEDIUM, "Permissions", f"{rel} pre-approves risky commands", ", ".join(risky[:5]), "Move these to ask, or narrow them to exact arguments."))
        if broad and not (perms.get("deny") or []):
            out.append(finding(LOW, "Permissions", f"{rel} has no deny rules", "Nothing blocks reading .env or secrets folders.", 'Add deny rules such as "Read(./.env*)" and "Read(./secrets/**)".'))
        out += check_hooks(root, rel, data.get("hooks") or {})
    return out


def check_hooks(root, rel, hooks):
    out = []
    for event, groups in hooks.items():
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                cmd = str(hook.get("command", ""))
                if not cmd:
                    continue
                try:
                    words = shlex.split(cmd.replace("${CLAUDE_PROJECT_DIR}", str(root)).replace("$CLAUDE_PROJECT_DIR", str(root)))
                except ValueError:
                    continue  # Shell syntax we can't read safely: say nothing rather than guess.
                if not words:
                    continue
                first = words[0]
                if Path(first).name in INTERPRETERS and len(words) > 1 and not words[1].startswith("-"):
                    script = words[1]
                    if not (root / script).expanduser().exists():
                        shown = script.replace(str(root), ".", 1)
                        out.append(finding(HIGH, "Hooks", f"{event} hook points at a missing file", f"{rel}: {shown}", "Fix the path or remove the hook; a missing script fails on every event."))
                if "/" in first and not (root / first).expanduser().exists() and not Path(first).expanduser().exists():
                    shown = first.replace(str(root), ".", 1)
                    out.append(finding(HIGH, "Hooks", f"{event} hook points at a missing file", f"{rel}: {shown}", "Fix the path or remove the hook; a missing script fails on every event."))
                elif "/" not in first and not shutil.which(first) and first not in {"cd", "echo", "test", "["}:
                    out.append(finding(MEDIUM, "Hooks", f"{event} hook needs '{first}', which is not installed here", rel, "Install it or call it by full path, so the hook doesn't fail on other machines."))
                if re.search(r"\|\|\s*true|2>\s*/dev/null|;\s*exit 0\s*$", cmd):
                    out.append(finding(MEDIUM, "Hooks", f"{event} hook hides its own failures", cmd[:80], "Let it fail loudly, or log the error; a silent hook looks like a working one."))
    return out


def check_mcp(root):
    out = []
    data, err = load_json(root / ".mcp.json")
    if err:
        return [finding(HIGH, "MCP", ".mcp.json is not valid JSON", err[:120], "Fix the JSON; none of its servers will load.")]
    if data is not None and not isinstance(data, dict):
        return [finding(HIGH, "MCP", ".mcp.json is not an object", "Expected {\"mcpServers\": {...}}.", "Fix the shape; none of its servers will load.")]
    for name, srv in ((data or {}).get("mcpServers") or {}).items():
        if not isinstance(srv, dict):
            out.append(finding(HIGH, "MCP", f"MCP server '{name}' is not an object", "Its entry is a list or value.", "Give it a command or url inside {...}."))
            continue
        url, cmd = srv.get("url", ""), srv.get("command", "")
        if url and url.startswith("http://") and not re.match(r"http://(localhost|127\.0\.0\.1|\[::1\])(?:[:/]|$)", url):
            out.append(finding(HIGH, "MCP", f"MCP server '{name}' uses plain http", url[:80], "Use https; tokens and tool results travel in clear text."))
        if cmd and not cmd.startswith("${") and not shutil.which(cmd) and not Path(cmd).exists():
            out.append(finding(MEDIUM, "MCP", f"MCP server '{name}' can't start here", f"'{cmd}' is not on PATH.", "Install it or use a full path; the server will fail to connect."))
        for key, val in (srv.get("env") or {}).items():
            if isinstance(val, str) and val and not val.startswith("${") and re.search(r"key|token|secret|password", key, re.I):
                out.append(finding(HIGH, "Secrets", f"MCP server '{name}' has a secret written into .mcp.json", f"env {key} is a literal value.", "Use ${" + key + "} and keep the value in the environment."))
    return out


def check_secrets(root, files):
    out, seen = [], set()
    for f in files:
        rel = f.relative_to(root).as_posix() if f.is_absolute() else str(f)
        name = f.name
        if re.fullmatch(r"\.env(\..+)?", name) and not name.endswith((".example", ".sample", ".template")):
            out.append(finding(HIGH, "Secrets", f"{rel} is in the repo", "Environment files usually hold live keys.", "Remove it from git, rotate the keys, add it to .gitignore."))
        try:
            if f.stat().st_size > 512_000:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pat in SECRET_PATTERNS.items():
            if pat.search(text) and (rel, label) not in seen:
                seen.add((rel, label))
                out.append(finding(HIGH, "Secrets", f"{label} found in {rel}", "Value not shown.", "Rotate the key, then remove it from the file and from git history."))
    return out


def check_basics(root):
    out = []
    if not any((root / p).exists() for p in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md", "AGENTS.md")):
        out.append(finding(MEDIUM, "Instructions", "No CLAUDE.md or AGENTS.md", "The agent starts every session without project rules.", "Add a short CLAUDE.md: how to build, test, and what never to touch."))
    else:
        for p in ("CLAUDE.md", ".claude/CLAUDE.md"):
            if (root / p).exists() and (root / p).stat().st_size > 40_000:
                out.append(finding(LOW, "Instructions", f"{p} is very long", f"{(root / p).stat().st_size // 1000} kB loads into every session.", "Keep it short; move detail to linked files."))
    gi = (root / ".gitignore").read_text(errors="ignore") if (root / ".gitignore").exists() else ""
    if not re.search(r"^\s*/?\.env", gi, re.M):
        out.append(finding(MEDIUM, "Secrets", ".env is not in .gitignore", "One git add -A away from leaking keys.", "Add .env* (and keep .env.example)."))
    if (root / ".claude").exists() and "settings.local.json" not in gi:
        out.append(finding(LOW, "Settings", ".claude/settings.local.json is not ignored", "Personal permissions can end up shared.", "Add .claude/settings.local.json to .gitignore."))
    return out


def audit(root, home=None):
    """home: folder holding the user's ~/.claude; None skips user-level settings."""
    root = Path(root).resolve()
    files = project_files(root)
    found = check_basics(root) + check_settings(root, home) + check_mcp(root) + check_secrets(root, files)
    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    return sorted(found, key=lambda f: order[f["severity"]])


GROUPS = [(HIGH, "Fix first"), (MEDIUM, "Worth fixing"), (LOW, "When you have a minute")]


def report(root, findings, user=False):
    name = Path(root).resolve().name
    n = {s: sum(f["severity"] == s for f in findings) for s in (HIGH, MEDIUM, LOW)}
    if n[HIGH]:
        top = f"{n[HIGH]} thing{'s' if n[HIGH] > 1 else ''} to fix before you trust this setup."
    elif findings:
        top = "Nothing urgent. A few things worth tidying."
    else:
        top = "No findings in the files checked."
    lines = [f"# {name}: agent setup check", "", f"**{top}**", ""]
    for sev, heading in GROUPS:
        items = [f for f in findings if f["severity"] == sev]
        if not items:
            continue
        lines += [f"## {heading}", ""]
        for i, f in enumerate(items, 1):
            lines += [f"{i}. **{f['title']}**  ", f"   {f['detail']}  ", f"   Fix: {f['fix']}", ""]
    scope = "project settings" + (" and your ~/.claude/settings.json" if user else "")
    lines += ["---", f"What this looked at: {scope}, hooks, MCP config, project files for keys and .env files, project instructions.",
              "What it can't see: how the agent behaves while running, or whether MCP servers connect. It reads files only.",
              "Recognised keys are masked. Rules, commands and URLs are quoted, so read the report before you share it."]
    return "\n".join(lines) + "\n"


USAGE = "usage: python3 audit.py [PROJECT_DIR] [--out REPORT.md] [--no-user]\n"


def main(argv):
    if "-h" in argv or "--help" in argv:
        sys.stdout.write(USAGE)
        return 0
    unknown = [a for a in argv if a.startswith("-") and a not in ("--out", "--no-user")]
    if unknown:
        sys.stderr.write(f"unknown option {unknown[0]}\n{USAGE}")
        return 2
    home = None if "--no-user" in argv else Path.home()
    args = [a for a in argv if a not in ("--out", "--no-user")]
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    if out:
        args.remove(out)
    root = args[0] if args else "."
    findings = audit(root, home)
    text = report(root, findings, user=home is not None)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 1 if any(f["severity"] == HIGH for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
