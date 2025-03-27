from datetime import datetime
from uagents import Agent, Context, Model
from chat_proto import chat_proto, ChatMessage, create_text_chat, ChatAcknowledgement

agent = Agent(
    name="bob",
    seed="bob recovery phrase 12345678fgjfjfgh8",
    port=8002,
    endpoint="http://localhost:8002/submit"
)

AGENT_ADDRESS = "agent1qdp50yecnqwwc47qga0ea2756mfl4cmxpn20rj03l200nd64rdxcwz0yk6d"

@chat_proto.on_message(ChatAcknowledgement)
async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
    ctx.logger.info(f"Got acknowledgement from {sender}. Timestamp: {msg.timestamp}, "
                    f"Acknowledged Message ID: {msg.acknowledged_msg_id}")

@chat_proto.on_message(ChatMessage)
async def handle_message(ctx: Context, sender: str, msg: ChatMessage):
    for content in msg.content:
        if content.type == "text":
            ctx.logger.info(f"Received response from {sender}: {content.text}")
        elif content.type == "end-session":
            ctx.logger.info(f"Session ended by {sender}")

    await ctx.send(
        sender,
        ChatAcknowledgement(
            timestamp=datetime.utcnow(),
            acknowledged_msg_id=msg.msg_id
        )
    )

@agent.on_event("startup")
async def introduce_agent(ctx: Context):
    ctx.logger.info(f"Hello, I'm agent {agent.name} and my address is {agent.address}.")
    ctx.logger.debug(f"Chat protocol digest: {chat_proto.digest}")
    
    await ctx.send(
        AGENT_ADDRESS,
        create_text_chat("Generate an invoice for My Business, located at 123 Main St. The invoice is for customer John Doe, with billing contact Jane Doe. The payment is due by 2025-04-10, and payment should be made to Bank XYZ, Account: 123456. The invoice includes the following items: Product A with a quantity of 2 at $10.00 each, and Product B with a quantity of 1 at $25.00. Send the invoice to the email address gautam.kumar@fetch.ai")
    )

agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()