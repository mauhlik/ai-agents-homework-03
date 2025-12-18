import asyncio
import argparse

from dotenv import load_dotenv, find_dotenv

from graph import run_graph, run_graph_with_github


async def main():
    _ = load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser(description="Run the LangGraph learning -> markdown pipeline")
    parser.add_argument("--issue-title", type=str, required=True)
    parser.add_argument("--issue-body", type=str, required=True)
    parser.add_argument(
        "--style-guide",
        type=str,
        required=False,
        default=None,
        help="Optional markdown style guide instructions",
    )

    parser.add_argument("--github-owner", type=str, required=False, default=None)
    parser.add_argument("--github-repo", type=str, required=False, default=None)
    parser.add_argument(
        "--create-github-issues",
        action="store_true",
        help="Create a GitHub issue for the topic and one issue per subtopic",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Actually create issues (requires GITHUB_TOKEN). Default is dry-run.",
    )

    args = parser.parse_args()

    gh = None
    if args.create_github_issues:
        if not args.github_owner or not args.github_repo:
            raise SystemExit("--github-owner and --github-repo are required with --create-github-issues")

        md, gh = await run_graph_with_github(
            issue_title=args.issue_title,
            issue_body=args.issue_body,
            style_guide=args.style_guide,
            github_owner=args.github_owner,
            github_repo=args.github_repo,
            dry_run=not args.no_dry_run,
        )
    else:
        md = await run_graph(
            issue_title=args.issue_title,
            issue_body=args.issue_body,
            style_guide=args.style_guide,
        )

    topic = md.topic
    print(f"# {topic.name}\n")
    print(topic.description)

    for sub in topic.subtopics:
        print("\n---\n")
        print(f"## {sub.name}\n")
        print(sub.description)

        if sub.verification_steps:
            print("\n### Verification steps\n")
            for step in sub.verification_steps:
                print(f"- {step}")

        if sub.exercises:
            print("\n### Exercises\n")
            for ex in sub.exercises:
                print(f"#### {ex.name}\n")
                print(ex.instructions)

                if ex.acceptance_criteria:
                    print("\n**Acceptance criteria**")
                    for ac in ex.acceptance_criteria:
                        print(f"- {ac}")

                if ex.hints:
                    print("\n**Hints**")
                    for h in ex.hints:
                        print(f"- {h}")

                if ex.starter_code:
                    print("\n**Starter code**\n")
                    code = ex.starter_code.strip("\n")
                    if "```" in code:
                        print(code)
                    else:
                        print("```python")
                        print(code)
                        print("```")

    if gh:
        print("\n---\n")
        print("## Created GitHub issues")
        print(f"- Topic: {gh.topic_issue.url}")
        for i in gh.sub_issues:
            print(f"- Sub-issue: {i.url}")


if __name__ == "__main__":
    asyncio.run(main())
