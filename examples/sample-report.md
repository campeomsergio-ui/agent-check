# messy-project: agent setup check

**4 things to fix before you trust this setup.**

## Fix first

1. **.claude/settings.json allows whole tools without limits**  
   Bash  
   Fix: Replace with narrow rules such as Bash(npm test:*).

2. **PostToolUse hook points at a missing file**  
   .claude/settings.json: ./scripts/format.sh  
   Fix: Fix the path or remove the hook; a missing script fails on every event.

3. **MCP server 'tickets' uses plain http**  
   http://tickets.example.com/mcp  
   Fix: Use https; tokens and tool results travel in clear text.

4. **MCP server 'tickets' has a secret written into .mcp.json**  
   env API_TOKEN is a literal value.  
   Fix: Use ${API_TOKEN} and keep the value in the environment.

## Worth fixing

1. **No CLAUDE.md or AGENTS.md**  
   The agent starts every session without project rules.  
   Fix: Add a short CLAUDE.md: how to build, test, and what never to touch.

2. **.env is not in .gitignore**  
   One git add -A away from leaking keys.  
   Fix: Add .env* (and keep .env.example).

3. **.claude/settings.json pre-approves risky commands**  
   Bash(git push:*)  
   Fix: Move these to ask, or narrow them to exact arguments.

4. **PostToolUse hook hides its own failures**  
   $CLAUDE_PROJECT_DIR/scripts/format.sh || true  
   Fix: Let it fail loudly, or log the error; a silent hook looks like a working one.

## When you have a minute

1. **.claude/settings.local.json is not ignored**  
   Personal permissions can end up shared.  
   Fix: Add .claude/settings.local.json to .gitignore.

2. **.claude/settings.json has no deny rules**  
   Nothing blocks reading .env or secrets folders.  
   Fix: Add deny rules such as "Read(./.env*)" and "Read(./secrets/**)".

---
What this looked at: project and user settings, permissions, hooks, MCP servers, secrets in the repo, project instructions.
What it can't see: how the agent behaves while running. It only reads files, and never shows a secret's value.
