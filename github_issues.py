import os
from typing import List, Optional

import httpx
from pydantic import BaseModel, Field

from learning_assistent import Output as LearningOutput


class GitHubIssueDraft(BaseModel):
    title: str
    body: str
    labels: List[str] = Field(default_factory=list)


class GitHubCreatedIssue(BaseModel):
    id: int
    number: int
    url: str
    title: str


class GitHubIssueCreationResult(BaseModel):
    topic_issue: GitHubCreatedIssue
    sub_issues: List[GitHubCreatedIssue] = Field(default_factory=list)


def _as_fenced_code(code: str, *, language: str = "python") -> str:
    """Return code wrapped in a fenced Markdown block unless already fenced."""
    c = (code or "").strip("\n")
    if not c:
        return ""
    # If the user/model already included fences, keep as-is.
    if "```" in c:
        return c
    return f"```{language}\n{c}\n```"


def build_issue_drafts(
    md_output: LearningOutput,
    *,
    topic_labels: Optional[List[str]] = None,
    subtopic_labels: Optional[List[str]] = None,
) -> tuple[GitHubIssueDraft, List[GitHubIssueDraft]]:
    """Convert MarkdownOutput (LearningOutput-shaped) into issue drafts.

    Linking strategy:
    - Create topic issue with topic.description
    - Each sub-issue body includes a reference: "Parent: #<topic_number>" (filled after creation)
      (body patch done during creation).
    """

    topic_labels = topic_labels or ["learning"]
    subtopic_labels = subtopic_labels or ["learning", "subtopic"]

    topic = md_output.topic

    topic_draft = GitHubIssueDraft(
        title=topic.name,
        body=topic.description or "",
        labels=topic_labels,
    )

    sub_drafts: List[GitHubIssueDraft] = []
    for st in topic.subtopics:
        parts: list[str] = []
        if st.description:
            parts.append(st.description)

        if st.verification_steps:
            parts.append("### Verification steps\n" + "\n".join(f"- {s}" for s in st.verification_steps))

        if st.exercises:
            ex_md: list[str] = ["### Exercises"]
            for ex in st.exercises:
                ex_md.append(f"#### {ex.name}\n\n{ex.instructions}")
                if ex.acceptance_criteria:
                    ex_md.append(
                        "**Acceptance criteria**\n" + "\n".join(f"- {a}" for a in ex.acceptance_criteria)
                    )
                if ex.hints:
                    ex_md.append("**Hints**\n" + "\n".join(f"- {h}" for h in ex.hints))
                if ex.starter_code:
                    ex_md.append("**Starter code**\n\n" + _as_fenced_code(ex.starter_code))
            parts.append("\n\n".join(ex_md))

        body = "\n\n".join(p.strip() for p in parts if p and p.strip())

        sub_drafts.append(
            GitHubIssueDraft(
                title=st.name,
                body=body,
                labels=subtopic_labels,
            )
        )

    return topic_draft, sub_drafts


class GitHubClient:
    def __init__(
        self,
        *,
        token: Optional[str] = None,
        api_base: str = "https://api.github.com",
        timeout_s: float = 30.0,
    ):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN must be set to create GitHub issues")

        self.api_base = api_base.rstrip("/")
        self.timeout_s = timeout_s

    async def create_issue(
        self,
        *,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[List[str]] = None,
    ) -> GitHubCreatedIssue:
        url = f"{self.api_base}/repos/{owner}/{repo}/issues"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()

            return GitHubCreatedIssue(
                id=data["id"],
                number=data["number"],
                url=data["html_url"],
                title=data["title"],
            )

    async def add_sub_issue(
        self,
        *,
        owner: str,
        repo: str,
        parent_issue_number: int,
        sub_issue_id: int,
        replace_parent: bool = False,
    ) -> None:
        """Attach an existing issue as a sub-issue of another issue.

        API: POST /repos/{owner}/{repo}/issues/{issue_number}/sub_issues
        """

        url = f"{self.api_base}/repos/{owner}/{repo}/issues/{parent_issue_number}/sub_issues"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {"sub_issue_id": sub_issue_id, "replace_parent": replace_parent}

        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
