"""LangGraph pipeline wiring for the learning + markdown assistants.

Flow:
UserInput -> LearningAssistant -> MarkdownAssistant -> MarkdownOutput
"""

from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.graph import StateGraph, END

from learning_assistent import LearningAssistant, Input as LearningInput, Output as LearningOutput
from markdown_assistent import MarkdownAssistant, MarkdownInput, MarkdownOutput
from github_issues import (
	GitHubClient,
	GitHubIssueCreationResult,
	build_issue_drafts,
)


class GraphState(TypedDict, total=False):
	issue_title: str
	issue_body: str
	style_guide: Optional[str]

	# GitHub settings
	github_owner: str
	github_repo: str
	create_github_issues: bool
	dry_run: bool

	learning_output: LearningOutput
	markdown_output: MarkdownOutput
	github_result: GitHubIssueCreationResult


async def _learning_node(state: GraphState) -> GraphState:
	assistant = LearningAssistant()
	inp = LearningInput(issue_title=state["issue_title"], issue_body=state["issue_body"])
	out = await assistant.process(inp)
	return {**state, "learning_output": out}


async def _markdown_node(state: GraphState) -> GraphState:
	assistant = MarkdownAssistant()
	learning_out = state["learning_output"]
	md_inp = MarkdownInput(topic=learning_out.topic, style_guide=state.get("style_guide"))
	md_out = await assistant.process(md_inp)
	return {**state, "markdown_output": md_out}


async def _github_issues_node(state: GraphState) -> GraphState:
	"""Create a GitHub issue for the topic and one issue per subtopic.

	If create_github_issues is false (default), this node is a no-op.
	If dry_run is true, it will only build drafts and return placeholders.
	"""

	if not state.get("create_github_issues"):
		return state

	owner = state.get("github_owner")
	repo = state.get("github_repo")
	if not owner or not repo:
		raise ValueError("github_owner and github_repo must be provided when create_github_issues=true")

	md_out = state["markdown_output"]
	topic_draft, sub_drafts = build_issue_drafts(md_out)

	if state.get("dry_run"):
		result = GitHubIssueCreationResult(
			topic_issue={"id": 0, "number": 0, "url": "DRY_RUN", "title": topic_draft.title},
			sub_issues=[
				{"id": 0, "number": 0, "url": "DRY_RUN", "title": d.title} for d in sub_drafts
			],
		)
		return {**state, "github_result": result}

	client = GitHubClient()
	created_topic = await client.create_issue(
		owner=owner,
		repo=repo,
		title=topic_draft.title,
		body=topic_draft.body,
		labels=topic_draft.labels,
	)

	created_subs = []
	for d in sub_drafts:
		body = f"Parent: #{created_topic.number}\n\n{d.body}" if d.body else f"Parent: #{created_topic.number}"
		created_subs.append(
			await client.create_issue(
				owner=owner,
				repo=repo,
				title=d.title,
				body=body,
				labels=d.labels,
			)
		)

	for sub in created_subs:
		try:
			await client.add_sub_issue(
				owner=owner,
				repo=repo,
				parent_issue_number=created_topic.number,
				sub_issue_id=sub.id,
				replace_parent=True,
			)
		except Exception:
			pass

	result = GitHubIssueCreationResult(topic_issue=created_topic, sub_issues=created_subs)
	return {**state, "github_result": result}


def build_graph():
	graph = StateGraph(GraphState)
	graph.add_node("learn", _learning_node)
	graph.add_node("markdown", _markdown_node)
	graph.add_node("github_issues", _github_issues_node)

	graph.set_entry_point("learn")
	graph.add_edge("learn", "markdown")
	graph.add_edge("markdown", "github_issues")
	graph.add_edge("github_issues", END)
	return graph.compile()


async def run_graph(
	*,
	issue_title: str,
	issue_body: str,
	style_guide: Optional[str] = None,
	github_owner: Optional[str] = None,
	github_repo: Optional[str] = None,
	create_github_issues: bool = False,
	dry_run: bool = True,
) -> MarkdownOutput:
	app = build_graph()
	final_state = await app.ainvoke(
		{
			"issue_title": issue_title,
			"issue_body": issue_body,
			"style_guide": style_guide,
			"github_owner": github_owner,
			"github_repo": github_repo,
			"create_github_issues": create_github_issues,
			"dry_run": dry_run,
		}
	)
	return final_state["markdown_output"]


async def run_graph_with_github(
	*,
	issue_title: str,
	issue_body: str,
	style_guide: Optional[str] = None,
	github_owner: str,
	github_repo: str,
	dry_run: bool = True,
) -> tuple[MarkdownOutput, Optional[GitHubIssueCreationResult]]:
	"""Convenience wrapper that returns both the markdown output and created GitHub issues."""
	app = build_graph()
	final_state = await app.ainvoke(
		{
			"issue_title": issue_title,
			"issue_body": issue_body,
			"style_guide": style_guide,
			"github_owner": github_owner,
			"github_repo": github_repo,
			"create_github_issues": True,
			"dry_run": dry_run,
		}
	)
	return final_state["markdown_output"], final_state.get("github_result")
