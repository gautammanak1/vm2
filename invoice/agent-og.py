import os
from enum import Enum

from uagents import Agent, Context, Model
from uagents.experimental.quota import QuotaProtocol, RateLimit
from uagents.models import ErrorMessage

from chat_proto import chat_proto, struct_output_client_proto
from invoice import InvoiceRequest, generate_invoice, InvoiceResponse  

AGENT_SEED = os.getenv("AGENT_SEED", "invoice-agent-fagdjhsdbhkabdkh")
AGENT_NAME = os.getenv("AGENT_NAME", "Invoice Agent")

PORT = 8013 
agent = Agent(
    name=AGENT_NAME,
    seed=AGENT_SEED,
    port=PORT,
    mailbox=True,
)

proto = QuotaProtocol(
    storage_reference=agent.storage,
    name="Invoice-Agent-Protocol",
    version="0.1.0",
    default_rate_limit=RateLimit(window_size_minutes=60, max_requests=6),
)

@proto.on_message(model=InvoiceRequest, replies={InvoiceResponse, ErrorMessage})
async def handle_invoice_request(ctx: Context, sender: str, msg: InvoiceRequest):
    ctx.logger.info(f"Received Invoice Request from {sender}")
    try:
        invoice_result = await generate_invoice(msg)
        ctx.logger.info(f"Invoice result: {invoice_result}")
        
        if invoice_result["status"] == "error":
            ctx.logger.error(f"Error: {invoice_result['message']}")
            await ctx.send(sender, ErrorMessage(error=invoice_result["message"]))
            return
        
        await ctx.send(sender, InvoiceResponse(**invoice_result))
    except Exception as err:
        ctx.logger.error(f"Unexpected error: {err}")
        await ctx.send(sender, ErrorMessage(error=str(err)))

agent.include(proto, publish_manifest=True)

### Health check related code
def agent_is_healthy() -> bool:
    """
    Implement the actual health check logic here.
    For example, check if the email server is reachable or if resources are sufficient.
    """
    condition = True  # TODO: Implement the actual health check logic
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