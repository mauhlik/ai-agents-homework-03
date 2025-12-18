
# Learning Assistant + Markdown Formatter (LangGraph)

This folder contains a small pipeline:

1. **Learning assistant**: turns a user request (topic) into a structured `Topic` (subtopics, exercises, verification steps).
2. **Markdown assistant**: returns the *same `Topic` shape*, but rewrites the text fields so they are Markdown-ready for GitHub issue bodies.

This is useful when you want:

- a **GitHub issue** for the main topic using `topic.description` as the issue body
- **sub-issues** per subtopic using `subtopic.description`, `subtopic.verification_steps`, and exercises as Markdown

The nodes are wired together using **LangGraph** in `graph.py`.

## Environment variables

- `OPENAI_API_KEY` (required)
- `OPENAI_BASE_URL` (optional, default: `https://api.openai.com/v1`)
- `TAVILY_API_KEY` (required by the learning assistant)

For GitHub issue creation:

- `GITHUB_TOKEN` (required when using `--create-github-issues` with `--no-dry-run`)
	- Needs permission to create issues in the target repo.

You can place them in a `.env` file (the runners load it automatically).

## Run

### LangGraph pipeline (recommended)

Use `run_graph.py` to run the full chain and print the Topic/subtopics in a Markdown-friendly layout.

```bash
uv run run_graph.py --issue-title "Python async" --issue-body "I want a plan and practice" \
	--style-guide "Keep it concise. Use checklists."
```

### Create GitHub issues (dry-run by default)

```bash
uv run run_graph.py --issue-title "Python async" --issue-body "I want a plan and practice" \
	--create-github-issues --github-owner "OWNER" --github-repo "REPO"
```

```bash
uv run run_graph.py --issue-title "Python async" --issue-body "I want a plan and practice" \
	--create-github-issues --github-owner "OWNER" --github-repo "REPO" --no-dry-run
```

Note: When running with `--no-dry-run`, the pipeline will create the parent issue and then attach each subtopic issue as a **true sub-issue** using GitHub's sub-issues API. A simple `Parent: #<n>` line is also added to the sub-issue body as a human-readable backlink.

### Learning assistant only

```bash
uv run run.py --issue-title "Python async" --issue-body "I want a plan and practice"
```

Dry-run will build the drafts and show placeholder URLs.

```bash
python run_graph.py --issue-title "Python async" --issue-body "I want a plan and practice" \
	--create-github-issues --github-owner "OWNER" --github-repo "REPO"
```

Actually create issues (requires `GITHUB_TOKEN`):

```bash
python run_graph.py --issue-title "Python async" --issue-body "I want a plan and practice" \
	--create-github-issues --github-owner "OWNER" --github-repo "REPO" --no-dry-run
```

Note: When running with `--no-dry-run`, the pipeline will create the parent issue and then attach each subtopic issue as a **true sub-issue** using GitHub's sub-issues API. A simple `Parent: #<n>` line is also added to the sub-issue body as a human-readable backlink.

### Learning assistant only

```bash
python run.py --issue-title "Python async" --issue-body "I want a plan and practice"
```
