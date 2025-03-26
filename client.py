from datetime import datetime
from uagents import Agent, Context, Model
from chat_proto import chat_proto, ChatMessage, create_text_chat, ChatAcknowledgement

agent = Agent(
    name="bob",
    seed="bob recovery phrase 12345678fgjfjfgh8",
    port=8002,
    endpoint="http://localhost:8002/submit"
)

AGENT_ADDRESS = "agent1qtla8vpsk09rsek9cs24h2dnrrrr06gu27642nhzwtugpaq9vkdpvw09e7s"

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
        create_text_chat("Analysis this repo https://github.com/gautammanak1/git-agent")
    )

agent.include(chat_proto, publish_manifest=True)

if __name__ == "__main__":
    agent.run()
