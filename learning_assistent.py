import os
from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent



class Exercise(BaseModel):
    name: str = Field(..., description="Short title of the exercise")
    instructions: str = Field(..., description="What the learner should implement or accomplish")
    input_spec: Optional[str] = Field(None, description="Input format and constraints")
    examples: List[str] = Field(default_factory=list, description="Example inputs/outputs or usage")
    acceptance_criteria: List[str] = Field(
        default_factory=list,
        description="Objective checks to verify the solution"
    )
    hints: List[str] = Field(default_factory=list, description="Optional tips or guidance")
    estimated_time_minutes: Optional[int] = Field(None, ge=1, description="Rough time estimate")
    starter_code: Optional[str] = Field(None, description="Optional scaffold code")
    resources: List[str] = Field(default_factory=list, description="Optional learning links")


class SubTopic(BaseModel):
    name: str = Field(..., description="Name of the subtopic")
    difficulty_level: int = Field(
        ..., ge=1, le=5, description="Difficulty level from 1 (easy) to 5 (hard)"
    )
    description: str = Field(..., description="Description of the subtopic")
    exercises: List[Exercise] = Field(
        default_factory=list,
        description="Practice exercises to train this subtopic"
    )
    verification_steps: List[str] = Field(
        default_factory=list,
        description="Objective steps to verify mastery of the subtopic"
    )

class LlmTopic(BaseModel):
    name: str = Field(..., description="Name of the topic")
    description: str = Field(..., description="Description of the topic")
    subtopics: List[str] = Field(
        default_factory=list,
        description="Subtopics to learn the complete topic"
    )

class Topic(BaseModel):
    name: str = Field(..., description="Name of the topic")
    description: str = Field(..., description="Description of the topic")
    subtopics: List[SubTopic] = Field(
        default_factory=list,
        description="Subtopics to learn the complete topic"
    )


class Input(BaseModel):
    issue_title: str
    issue_body: str


class Output(BaseModel):
    topic: Topic


class LearningAssistant:
    def __init__(self, **kwargs):
        # System Prompt
        self.system_prompt_for_topic = """ You are an expert learning assistant. Your task is to help users learn new topics by breaking them down into manageable subtopics """
        
        # Model
        self.model = kwargs.get("model") or "openai/gpt-5-mini"
        # OpenAI API Configuration
        self.openai_api_key = kwargs.get("openai_api_key") or os.getenv("OPENAI_API_KEY")
        if not self.openai_api_key:
            raise ValueError("OpenAI API key must be provided via argument or OPENAI_API_KEY environment variable.")
        self.openai_base_url = kwargs.get("openai_base_url") or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        # Tavily
        self.tavily_api_key = kwargs.get("tavily_api_key") or os.getenv("TAVILY_API_KEY")
        if not self.tavily_api_key:
            raise ValueError("Tavily API key must be provided via argument or TAVILY_API_KEY environment variable.")
        
    async def __get_mcp_tools(self):
        """Load tools from Tavily MCP server."""
        client = MultiServerMCPClient(
            {
                "tavily": {
                    "url":  f"https://mcp.tavily.com/mcp/?tavilyApiKey={self.tavily_api_key}",
                    "transport": "streamable_http",
                }
            }
        )

        # Get tools from the MCP server
        tools = await client.get_tools()
        return tools
    
    async def __get_agent(self, system_prompt, response_type: type[BaseModel]):
        """Initialize the agent with tools from Tavily MCP server."""
        tools = await self.__get_mcp_tools()

        llm = ChatOpenAI(
            model=self.model,
            openai_api_key=self.openai_api_key,
            openai_api_base=self.openai_base_url,
        )

        agent = create_deep_agent(
            model=llm,
            tools=tools,
            system_prompt=system_prompt,
            response_format=response_type
        )
        
        return agent        
        

    async def process(self, input: Input) -> Output:
        topic_agent = await self.__get_agent("You are an expert learning assistant. Your task is to help users learn new topics by breaking them down into manageable subtopics.Give maximum of 3 subtopics.", LlmTopic)
        print("Processing topic:", input.issue_title)
        response = await topic_agent.ainvoke(
            { "messages": [
                    { "role": "user", "content": f"I want to learn {input.issue_title}?" },
                    { "role": "user", "content": f"I know {input.issue_body}" }
                ]
            }
        )
        print("Processed topic:", input.issue_title)
        sub_topic_agent = await self.__get_agent("You are an expert learning assistant.", SubTopic)
        llm_topic = self._normalize_structured_response(response, LlmTopic)
        
        output_topic = Topic(name=llm_topic.name, description=llm_topic.description, subtopics=[])
        for subtopic_name in llm_topic.subtopics:
            print("Processing subtopic:", subtopic_name)
            subtopic_response = await sub_topic_agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Create a detailed subtopic for '{subtopic_name}' when learning {input.issue_title}. "
                                "Include name, difficulty_level (1-5), description, exercises (with instructions), "
                                "and verification_steps."
                            ),
                        }
                    ]
                }
            )
            try:
                subtopic = self._normalize_structured_response(subtopic_response, SubTopic)
                output_topic.subtopics.append(subtopic)
            except (ValidationError, KeyError) as e:
                raise ValueError(f"Unexpected subtopic response structure for '{subtopic_name}': {e}")
            print("Processed subtopic:", subtopic_name)
            
        return Output(topic=output_topic)
        
        
    @staticmethod
    def _normalize_structured_response(resp, model_cls: type[BaseModel]) -> BaseModel:
        """
        Accepts whatever the agent returns and converts it into the given Pydantic model:
        - resp may be a dict
        - resp may be a BaseModel
        - resp may be a mapping under resp['structured_response']
        """
        # If agent returned a BaseModel already
        if isinstance(resp, BaseModel):
            # If it's already the right type, return as-is
            if isinstance(resp, model_cls):
                return resp
            # Otherwise, convert via dict
            return model_cls.model_validate(resp.model_dump())

        # If agent returned a mapping with structured_response
        if isinstance(resp, dict) and "structured_response" in resp:
            sr = resp["structured_response"]
            if isinstance(sr, BaseModel):
                if isinstance(sr, model_cls):
                    return sr
                return model_cls.model_validate(sr.model_dump())
            if isinstance(sr, dict):
                return model_cls.model_validate(sr)
            # Fallback: try to coerce from anything jsonable
            return model_cls.model_validate(sr)

        # If agent returned a plain dict of the right shape
        if isinstance(resp, dict):
            # Try direct validation
            return model_cls.model_validate(resp)

        # Last resort: attempt to serialize to dict if possible
        try:
            return model_cls.model_validate_json(resp)
        except Exception as e:
            raise ValueError(f"Cannot normalize agent response to {model_cls.__name__}: {e}")