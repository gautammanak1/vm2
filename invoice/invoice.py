from uagents.models import Field
from uagents import Model
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import pandas as pd
from io import BytesIO
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_SENDER = "gautammanak1@gmail.com"
EMAIL_PASSWORD = "xxle hdyo hsbg bqik"

class InvoiceRequest(Model):
    business_name: str = Field(description="Name of the business")
    business_address: str = Field(description="Business address")
    customer_name: str = Field(description="Name of the customer")
    billing_name: str = Field(description="Billing contact name")
    payment_due_date: str = Field(description="Payment due date")
    bank_details: str = Field(description="Bank details for payment")
    invoice_items: list = Field(description="List of items for the invoice")
    user_email: str = Field(description="Email address to send the invoice")

class InvoiceResponse(Model):
    status: str
    message: str

async def generate_invoice(request: InvoiceRequest) -> dict:
    try:
        # Process invoice items into a DataFrame
        invoice_df = pd.DataFrame(request.invoice_items)
        invoice_df['total_price'] = invoice_df['quantity'] * invoice_df['unit_price']

        # Generate PDF in memory
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=letter)
        width, height = letter

        # Add business details
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, height - 50, request.business_name)
        c.setFont("Helvetica", 12)
        c.drawString(50, height - 80, f"Business Address: {request.business_address}")
        c.drawString(50, height - 100, f"Customer Name: {request.customer_name}")
        c.drawString(50, height - 120, f"Billing Contact: {request.billing_name}")
        c.drawString(50, height - 140, f"Payment Due: {request.payment_due_date}")

        # Create table for invoice items
        y_position = height - 180
        table_data = [["Item", "Quantity", "Unit Price", "Total"]]
        for _, row in invoice_df.iterrows():
            table_data.append([
                row.get('item_name', 'N/A'),
                str(row.get('quantity', 0)),
                f"${row.get('unit_price', 0.00):.2f}",
                f"${row.get('total_price', 0.00):.2f}"
            ])

        table = Table(table_data, colWidths=[200, 100, 100, 100])
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ])
        table.setStyle(style)
        table.wrapOn(c, width, height)
        table.drawOn(c, 50, y_position - (len(table_data) * 20))

        # Add grand total and bank details
        grand_total = invoice_df['total_price'].sum()
        c.setFont("Helvetica-Bold", 12)
        c.drawString(400, y_position - (len(table_data) * 20) - 30, "Grand Total:")
        c.drawString(500, y_position - (len(table_data) * 20) - 30, f"${grand_total:.2f}")
        c.setFont("Helvetica", 10)
        c.drawString(50, y_position - (len(table_data) * 20) - 80, f"Bank Details: {request.bank_details}")

        c.save()
        pdf_buffer.seek(0)

        # Send email with the invoice
        send_email(request.user_email, pdf_buffer)

        return {
            "status": "success",
            "message": "Invoice generated and sent via email."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate invoice: {str(e)}"
        }

def send_email(user_email: str, pdf_buffer: BytesIO):
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = user_email
        msg['Subject'] = "Your Invoice"

        body = "Hello,\n\nPlease find your invoice attached.\n\nBest Regards,\nInvoice Agent"
        msg.attach(MIMEText(body, 'plain'))

        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_buffer.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment; filename=invoice.pdf")
        msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, user_email, msg.as_string())
    except Exception as e:
        raise Exception(f"Error sending email: {str(e)}")