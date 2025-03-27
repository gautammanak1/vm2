import os
from enum import Enum

from uagents import Agent, Context, Model
from uagents.experimental.quota import QuotaProtocol, RateLimit
from uagents.models import ErrorMessage

from chat_proto import chat_proto, struct_output_client_proto
from github import analyze_github_repo, RepoRequest, RepoAnalysis

AGENT_SEED = os.getenv("AGENT_SEED", "github-agent-fagdjhsdbhkabdkh")
AGENT_NAME = os.getenv("AGENT_NAME", "GitHub Agent")

PORT = 8003
agent = Agent(
    name=AGENT_NAME,
    seed=AGENT_SEED,
    port=PORT,
    mailbox=True,
)

proto = QuotaProtocol(
    storage_reference=agent.storage,
    name="GitHub-Agent-Protocol",
    version="0.1.0",
    default_rate_limit=RateLimit(window_size_minutes=60, max_requests=6),
)

@proto.on_message(
    RepoRequest, replies={RepoAnalysis, ErrorMessage}
)
async def handle_request(ctx: Context, sender: str, msg: RepoRequest):
    ctx.logger.info(f"Received Repo Request: {msg.repo_url}")
    try:
        repo_data = await analyze_github_repo(msg.repo_url)
        ctx.logger.info(f"Repo data: {repo_data}")
    except Exception as err:
        ctx.logger.error(err)
        await ctx.send(sender, ErrorMessage(error=str(err)))
        return

    if "error" in repo_data:
        ctx.logger.error(f"Error: {repo_data['error']}")
        await ctx.send(sender, ErrorMessage(error=repo_data["error"]))
        return
    await ctx.send(sender, RepoAnalysis(**repo_data))

agent.include(proto, publish_manifest=True)

### Health check related code
def agent_is_healthy() -> bool:
    """
    Implement the actual health check logic here.

    For example, check if the agent can connect to a third party API,
    check if the agent has enough resources, etc.
    """
    condition = True  # TODO: logic here
    return bool(condition)

class HealthCheck(Model):
    pass

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"

class AgentHealth(Model):
    agent_name: str
    status: HealthStatus

health_protocol = QuotaProtocol(
    storage_reference=agent.storage, name="HealthProtocol", version="0.1.0"
)

@health_protocol.on_message(HealthCheck, replies={AgentHealth})
async def handle_health_check(ctx: Context, sender: str, msg: HealthCheck):
    status = HealthStatus.UNHEALTHY
    try:
        if agent_is_healthy():
            status = HealthStatus.HEALTHY
    except Exception as err:
        ctx.logger.error(err)
    finally:
        await ctx.send(sender, AgentHealth(agent_name=AGENT_NAME, status=status))

agent.include(health_protocol, publish_manifest=True)
agent.include(chat_proto, publish_manifest=True)
agent.include(struct_output_client_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
