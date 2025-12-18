import os
from typing import Optional

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from learning_assistent import Topic, SubTopic, Exercise, Output as LearningOutput


class MarkdownInput(BaseModel):
    """Input to the Markdown formatting assistant."""

    topic: Topic = Field(..., description="Structured learning topic to be rendered")
    style_guide: Optional[str] = Field(
        default=None,
        description=(
            "Optional formatting constraints (tone, headings, bullets, etc). "
            "If omitted, use a clean default style."
        ),
    )


class MarkdownTopic(Topic):
    """A Topic object whose text fields are Markdown-ready strings."""


class MarkdownOutput(LearningOutput):
    """Return the same shape as LearningAssistant Output, but markdown-ready."""


class MarkdownAssistant:
    """Turns a structured Topic into a Markdown lesson plan."""

    def __init__(self, **kwargs):
        self.model = kwargs.get("model") or "openai/gpt-5-mini"
        self.openai_api_key = kwargs.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError(
                "OpenAI API key must be provided via argument or OPENAI_API_KEY environment variable."
            )
        self.openai_base_url = kwargs.get("openai_base_url") or os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )

        # We keep this assistant tool-free on purpose: it should only format.
        self.system_prompt = (
            "You are a Markdown formatting assistant. "
            "You receive a structured learning topic (with subtopics, exercises, and verification steps). "
            "You MUST return the same object shape (Topic -> SubTopic -> Exercise), but rewrite the text fields "
            "so they are ready to be used as Markdown inside GitHub issue bodies. "
            "Rules: (1) do not add/remove subtopics or exercises; do not invent content, only reformat, "
            "(2) output valid Markdown in these fields: Topic.description, SubTopic.description, "
            "SubTopic.verification_steps (each step may contain Markdown), Exercise.instructions, "
            "Exercise.acceptance_criteria (each item may contain Markdown), Exercise.hints (each item may contain Markdown), "
            "Exercise.starter_code (keep as-is if present; do NOT wrap it in extra fences), "
            "(3) keep names unchanged, "
            "(4) make formatting consistent and compact for GitHub issues."
        )

        self._llm = ChatOpenAI(
            model=self.model,
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_base_url,
        )

        self._agent = create_deep_agent(
            model=self._llm,
            tools=[],
            system_prompt=self.system_prompt,
            response_format=MarkdownOutput,
        )

    async def process(self, input: MarkdownInput) -> MarkdownOutput:
        style = input.style_guide or "Use a simple, professional style."

        # Send the structured data as JSON to reduce hallucinations.
        payload = input.topic.model_dump(mode="json")

        resp = await self._agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Rewrite the following Topic into the SAME Topic-shaped JSON where the specified fields are Markdown-ready. "
                            f"Style guide: {style}\n\n"
                            "Topic JSON:\n"
                            f"{payload}"
                        ),
                    }
                ]
            }
        )

        if isinstance(resp, MarkdownOutput):
            return resp
        if isinstance(resp, dict) and "structured_response" in resp:
            return MarkdownOutput.model_validate(resp["structured_response"])
        if isinstance(resp, dict):
            return MarkdownOutput.model_validate(resp)
        return MarkdownOutput.model_validate_json(resp)