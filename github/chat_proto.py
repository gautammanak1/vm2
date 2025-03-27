import os
from typing import Any, Literal
from datetime import datetime
from pydantic.v1 import UUID4
from uagents import Model, Protocol, Context
from uuid import uuid4
from github import RepoRequest, analyze_github_repo

AI_AGENT_ADDRESS = 'agent1qgg3dasyn8w34wfcdu9gj46mw3frf8et3xp9gzaxyxa34f9gjaqls356rp5'

class TextContent(Model):
    type: Literal["text"]
    text: str

class Resource(Model):
    uri: str
    metadata: dict[str, str]

class ResourceContent(Model):
    type: Literal["resource"]
    resource_id: UUID4
    resource: Resource | list[Resource]

class StartSessionContent(Model):
    type: Literal["start-session"]

class EndSessionContent(Model):
    type: Literal["end-session"]

class StartStreamContent(Model):
    type: Literal["start-stream"]
    stream_id: UUID4

class EndStreamContent(Model):
    type: Literal["start-stream"]  # Fixed typo from "start-stream"
    stream_id: UUID4

AgentContent = (
    TextContent
    | ResourceContent
    | StartSessionContent
    | EndSessionContent
    | StartStreamContent
    | EndStreamContent
)

class ChatMessage(Model):
    timestamp: datetime
    msg_id: UUID4
    content: list[AgentContent]

class ChatAcknowledgement(Model):
    timestamp: datetime
    acknowledged_msg_id: UUID4

def create_text_chat(text: str) -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[TextContent(type="text", text=text)],
    )

def create_end_session_chat() -> ChatMessage:
    return ChatMessage(
        timestamp=datetime.utcnow(),
        msg_id=uuid4(),
        content=[EndSessionContent(type="end-session")],
    )

chat_proto = Protocol(name="AgentChatProtcol", version="0.2.1")

struct_output_client_proto = Protocol(
    name="StructuredOutputClientProtocol", version="0.1.0"
)

class StructuredOutputPrompt(Model):
    prompt: str
    output_schema: dict[str, Any]

class StructuredOutputResponse(Model):
    output: dict[str, Any]

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    ctx.logger.info(f"Got a message from {sender}: {msg.content[0].text}")
    ctx.storage.set(str(ctx.session), sender)
    await ctx.send(
        sender,
        ChatAcknowledgement(timestamp=datetime.utcnow(), acknowledged_msg_id=msg.msg_id)
    )
    ctx.logger.info(f"Sending structured output prompt to {AI_AGENT_ADDRESS}")
    await ctx.send(
        AI_AGENT_ADDRESS,
        StructuredOutputPrompt(
            prompt=msg.content[0].text, 
            output_schema=RepoRequest.schema()
        ),
    )
    ctx.logger.info(f"Sent structured output prompt to {AI_AGENT_ADDRESS}")

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Got an acknowledgement from {sender} for {msg.acknowledged_msg_id}")

@struct_output_client_proto.on_message(StructuredOutputResponse)
async def handle_structured_output_response(
    ctx: Context, sender: str, msg: StructuredOutputResponse
):
    ctx.logger.info(f"Received structured output response from {sender}")
    session_sender = ctx.storage.get(str(ctx.session))

    if not session_sender:
        ctx.logger.error("No session sender found")
        return

    ctx.logger.info(str(msg.output))

    try:
        response = RepoRequest.parse_obj(msg.output)
        repo_url = response.repo_url
        ctx.logger.info(f"Extracted repo URL: {repo_url}")

        if "<UNKNOWN>" in str(msg.output):
            await ctx.send(
                session_sender,
                create_text_chat(
                    "Sorry, I couldn't process your repo request. Please try again later."
                ),
            )
            return

        repo_data = await analyze_github_repo(repo_url)
    
        
        if "error" in repo_data:
            await ctx.send(
                session_sender,
                create_text_chat(str(repo_data["error"]))
            )
            return

        # Properly formatted repo response with gemini_analysis
        chat_message = create_text_chat(
            f"Analysis of {repo_url}:\n"
            f"Name: {repo_data['name']}\n"
            f"Commits: {repo_data['commit_count']}\n"
            f"Files: {repo_data['file_count']}\n"
            f"Dependencies: {repo_data['dependencies']}\n"
            f"Gemini Analysis: {repo_data['gemini_analysis']}"
        )

        await ctx.send(session_sender, chat_message)
        await ctx.send(session_sender, create_end_session_chat())

    except Exception as err:
        ctx.logger.error(f"Could not parse as repo request: {err}")
        await ctx.send(
            session_sender,
            create_text_chat(
                "Sorry, I couldn't understand your request. Please ask about a GitHub repository."
            ),
        )
