import os
from typing import Any, Literal
from datetime import datetime
from pydantic.v1 import UUID4
from uagents import Model, Protocol, Context
from uuid import uuid4
from invoice import InvoiceRequest, generate_invoice

AI_AGENT_ADDRESS = "agent1q0h70caed8ax769shpemapzkyk65uscw4xwk6dc4t3emvp5jdcvqs9xs32y"

if not AI_AGENT_ADDRESS:
    raise ValueError("AI_AGENT_ADDRESS not set")


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
    type: Literal["end-stream"]
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

chat_proto = Protocol(name="AgentChatProtocol", version="0.2.1")

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
            output_schema=InvoiceRequest.schema()
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

    ctx.logger.info(f"Raw output: {msg.output}")

    try:
        invoice_request = InvoiceRequest.parse_obj(msg.output)
        ctx.logger.info(f"Parsed invoice request: {invoice_request}")

        if "<UNKNOWN>" in str(msg.output):
            await ctx.send(
                session_sender,
                create_text_chat(
                    "Sorry, I couldn't process your invoice request. Please provide complete details."
                ),
            )
            return
        adjusted_items = [
            {
                "item_name": item.get("description", item.get("item_name", "Unknown")),
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
                "total_price": item["total_price"]
            }
            for item in invoice_request.invoice_items
        ]
        invoice_request.invoice_items = adjusted_items
        ctx.logger.info(f"Adjusted invoice items: {adjusted_items}")

        invoice_result = await generate_invoice(invoice_request)
        ctx.logger.info(f"Invoice generation result: {invoice_result}")

        if invoice_result.get("status") == "error":
            await ctx.send(
                session_sender,
                create_text_chat(f"Error generating invoice: {invoice_result.get('message', 'Unknown error')}")
            )
            return

        invoice_items_str = "\n".join(
            f"- {item['item_name']}: Qty {item['quantity']} @ ${item['unit_price']:.2f}"
            for item in invoice_request.invoice_items
        )
        total = sum(item["quantity"] * item["unit_price"] for item in invoice_request.invoice_items)
        chat_message = create_text_chat(
            f"Invoice generated and sent to {invoice_request.user_email}:\n"
            f"Business: {invoice_request.business_name}\n"
            f"Customer: {invoice_request.customer_name}\n"
            f"Items:\n{invoice_items_str}\n"
            f"Total: ${total:.2f}\n"
            f"Payment Due: {invoice_request.payment_due_date}\n"
            f"Bank Details: {invoice_request.bank_details}"
        )

        await ctx.send(session_sender, chat_message)
        await ctx.send(session_sender, create_end_session_chat())

    except Exception as err:
        ctx.logger.error(f"Could not process invoice request: {err}")
        await ctx.send(
            session_sender,
            create_text_chat(
                "Sorry, I couldn't understand your request. Please provide invoice details in the correct format."
            ),
        )