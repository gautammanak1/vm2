from anthropic import Anthropic
from dotenv import load_dotenv
from uagents_core.contrib.protocols.chat import (
    chat_protocol_spec,
    ChatMessage,
    ChatAcknowledgement,
    TextContent,
    StartSessionContent,
)
from uagents import Agent, Context, Protocol
from uagents.setup import fund_agent_if_low
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import mcp
from mcp.client.streamable_http import streamablehttp_client
import json
import base64
import asyncio
from typing import Dict, List, Optional, Any
from contextlib import AsyncExitStack
import os

# Load environment variables
load_dotenv()

# Get Anthropic API key from environment variable
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("Please set the ANTHROPIC_API_KEY environment variable in your .env file")

class MedicalResearchMCPClient:
    def __init__(self):
        self.sessions: Dict[str, mcp.ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self.anthropic = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.all_tools = []
        self.tool_server_map = {}
        self.server_configs = {}
        self.default_timeout = timedelta(seconds=30)  # Default timeout of 30 seconds

    def get_server_config(self, server_path: str) -> dict:
        """Get or create server configuration"""
        if server_path not in self.server_configs:
            config_templates = {
                "@nickclyde/duckduckgo-mcp-server": {},
                "@JackKuo666/pubmed-mcp-server": {},
                "@openags/paper-search-mcp": {},
                "@JackKuo666/clinicaltrials-mcp-server": {},
                "@vitaldb/medcalc": {},
            }
            self.server_configs[server_path] = config_templates.get(server_path, {})
        return self.server_configs[server_path]

    async def connect_to_servers(self, ctx: Context):
        """Connect to all MCP servers and collect their tools"""
        base_config = {
            "ignoreRobotsTxt": True
        }
        smithery_api_key = "2c1f1f6a-6db6-44d3-8ec3-6486f02a3b74"

        servers = [
            "@JackKuo666/pubmed-mcp-server",
            "@openags/paper-search-mcp",
            "@JackKuo666/clinicaltrials-mcp-server",
            "@vitaldb/medcalc",
        ]

        for server_path in servers:
            try:
                ctx.logger.info(f"Connecting to server: {server_path}")
                server_config = self.get_server_config(server_path)
                config = {**base_config, **server_config}
                config_b64 = base64.b64encode(json.dumps(config).encode()).decode()
                url = f"https://server.smithery.ai/{server_path}/mcp?config={config_b64}&api_key={smithery_api_key}"

                try:
                    read_stream, write_stream, _ = await self.exit_stack.enter_async_context(
                        streamablehttp_client(url)
                    )
                    session = await self.exit_stack.enter_async_context(
                        mcp.ClientSession(read_stream, write_stream)
                    )

                    await session.initialize()

                    tools_result = await session.list_tools()
                    tools = tools_result.tools

                    self.sessions[server_path] = session
                    for tool in tools:
                        tool_info = {
                            "name": tool.name,
                            "description": f"[{server_path}] {tool.description}",
                            "input_schema": tool.inputSchema,
                            "server": server_path,
                            "tool_name": tool.name
                        }
                        self.all_tools.append(tool_info)
                        self.tool_server_map[tool.name] = server_path

                    ctx.logger.info(f"Successfully connected to {server_path}")
                    ctx.logger.info(f"Available tools: {', '.join([t.name for t in tools])}")

                except Exception as e:
                    ctx.logger.error(f"Error during connection setup: {str(e)}")
                    ctx.logger.error(f"Error type: {type(e)}")
                    import traceback
                    ctx.logger.error(f"Traceback: {traceback.format_exc()}")
                    raise

            except Exception as e:
                ctx.logger.error(f"Error connecting to {server_path}: {str(e)}")
                ctx.logger.error(f"Error type: {type(e)}")
                import traceback
                ctx.logger.error(f"Traceback: {traceback.format_exc()}")
                continue

    async def process_query(self, query: str, ctx: Context) -> str:
        try:
            messages = [{"role": "user", "content": query}]
            claude_tools = [{
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["input_schema"]
            } for tool in self.all_tools]

            response = self.anthropic.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                messages=messages,
                tools=claude_tools
            )

            tool_response = None
            for content in response.content:
                if content.type == 'tool_use':
                    tool_name = content.name
                    tool_args = content.input
                    server_path = self.tool_server_map.get(tool_name)
                    if server_path and server_path in self.sessions:
                        ctx.logger.info(f"Calling tool {tool_name} from {server_path}")
                        try:
                            result = await asyncio.wait_for(
                                self.sessions[server_path].call_tool(tool_name, tool_args),
                                timeout=self.default_timeout.total_seconds()
                            )
                            if isinstance(result.content, str):
                                tool_response = result.content
                            elif isinstance(result.content, list):
                                tool_response = "\n".join([str(item) for item in result.content])
                            else:
                                tool_response = str(result.content)
                        except asyncio.TimeoutError:
                            return f"Error: The MCP server did not respond. Please try again later."
                        except Exception as e:
                            return f"Error calling tool {tool_name}: {str(e)}"

            if tool_response:
                format_prompt = f"""Please format the following response in a clear, user-friendly way. Do not add any additional information or knowledge, just format what is provided: {tool_response} Instructions: 1. If the response contains multiple records (like clinical trials), present ALL records in a clear format, do not say something like "Saved to a CSV file" or anything similar. 2. Use appropriate headings and sections 3. Maintain all the original information 4. Do not add any external knowledge or commentary 5. Do not summarize or modify the content 6. Keep the formatting simple and clean 7. If the response mentions a CSV file, do not include that information in the response. 9. For long responses, ensure all records are shown, not just a subset"""

                format_response = self.anthropic.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": format_prompt}]
                )

                if format_response.content and len(format_response.content) > 0:
                    return format_response.content[0].text
                else:
                    return tool_response
            else:
                return "No response received from the tool."

        except Exception as e:
            ctx.logger.error(f"Error processing query: {str(e)}")
            ctx.logger.error(f"Error type: {type(e)}")
            import traceback
            ctx.logger.error(f"Traceback: {traceback.format_exc()}")
            return f"An error occurred while processing your query: {str(e)}"

    async def cleanup(self):
        await self.exit_stack.aclose()

# Initialize chat protocol and agent
chat_proto = Protocol(spec=chat_protocol_spec)
mcp_agent = Agent(name='MedicalResearchMCPAgent', seed="Medical-Research-MCPAgent", port=8006, mailbox=True, readme_path="README.md", publish_agent_details=True)
client = MedicalResearchMCPClient()

@chat_proto.on_message(model=ChatMessage)
async def handle_chat_message(ctx: Context, sender: str, msg: ChatMessage):
    try:
        ack = ChatAcknowledgement(
            timestamp=datetime.now(timezone.utc),
            acknowledged_msg_id=msg.msg_id
        )
        await ctx.send(sender, ack)

        if not client.sessions:
            await client.connect_to_servers(ctx)

        for item in msg.content:
            if isinstance(item, StartSessionContent):
                ctx.logger.info(f"Got a start session message from {sender}")
                continue
            elif isinstance(item, TextContent):
                ctx.logger.info(f"Got a message from {sender}: {item.text}")
                response_text = await client.process_query(item.text, ctx)
                ctx.logger.info(f"Response text: {response_text}")
                response = ChatMessage(
                    timestamp=datetime.now(timezone.utc),
                    msg_id=uuid4(),
                    content=[TextContent(type="text", text=response_text)]
                )
                await ctx.send(sender, response)
            else:
                ctx.logger.info(f"Got unexpected content from {sender}")
    except Exception as e:
        ctx.logger.error(f"Error handling chat message: {str(e)}")
        ctx.logger.error(f"Error type: {type(e)}")
        import traceback
        ctx.logger.error(f"Traceback: {traceback.format_exc()}")
        error_response = ChatMessage(
            timestamp=datetime.now(timezone.utc),
            msg_id=uuid4(),
            content=[TextContent(type="text", text=f"An error occurred: {str(e)}")]
        )
        await ctx.send(sender, error_response)

@chat_proto.on_message(model=ChatAcknowledgement)
async def handle_chat_acknowledgement(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Received acknowledgement from {sender} for message {msg.acknowledged_msg_id}")
    if msg.metadata:
        ctx.logger.info(f"Metadata: {msg.metadata}")

mcp_agent.include(chat_proto)

if __name__ == "__main__":
    try:
        fund_agent_if_low(mcp_agent.wallet.address())
        mcp_agent.run()
    except Exception as e:
        print(f"Error running agent: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
    finally:
        asyncio.run(client.cleanup())