import os
import random
import csv
import pandas as pd
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def generate_gst_csv(path, set_id):
    # GST CSV expected cols: gstin, period, taxable value, igst, cgst, sgst
    data = []
    gstin = f"27AAAAA{random.randint(1000,9999)}A1Z{set_id}"
    for month in range(1, 13):
        period = f"01-{month:02d}-2025"
        sales = random.randint(100000, 5000000)
        igst = sales * 0.09
        cgst = sales * 0.09
        sgst = 0
        data.append([gstin, period, sales, igst, cgst, sgst])
    
    df = pd.DataFrame(data, columns=["GSTIN", "Return Period", "Taxable Value", "IGST", "CGST", "SGST"])
    df.to_csv(path, index=False)

def generate_bank_pdf(path, set_id):
    # Bank Statement expects table with: Date, Narration, Debit, Credit, Balance
    doc = SimpleDocTemplate(path, pagesize=letter)
    elements = []
    
    data = [["Date", "Narration", "Debit", "Credit", "Balance"]]
    balance = random.randint(50000, 500000)
    
    start_date = datetime(2025, 1, 1)
    
    for i in range(1, 50):
        current_date = start_date + timedelta(days=i*7)
        date_str = current_date.strftime("%d-%m-%Y")
        
        is_credit = random.choice([True, False])
        if is_credit:
            credit = random.randint(10000, 200000)
            debit = 0.0
            narr = "Sample Deposit"
            balance += credit
        else:
            credit = 0.0
            debit = random.randint(5000, 150000)
            narr = "Sample Withdrawal"
            balance -= debit
            
        data.append([date_str, narr, f"{debit:.2f}", f"{credit:.2f}", f"{balance:.2f}"])
        
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    elements.append(t)
    doc.build(elements)

def generate_itr_pdf(path, set_id):
    # ITR PDF needs specific keywords
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    pan = f"ABCDE{random.randint(1000,9999)}F"
    gti = random.randint(2000000, 50000000)
    business_income = gti * 0.8
    tax = gti * 0.2
    
    lines = [
        f"INCOME TAX RETURN - MOCK DATA SET {set_id}",
        f"PAN: {pan}",
        "Assessment Year: 2024-25",
        f"Gross Total Income: {gti}",
        f"Income from Business: {business_income}",
        f"Total Tax Paid: {tax}",
        f"Depreciation: {random.randint(50000, 200000)}",
        f"Net Profit: {gti - random.randint(100000, 500000)}"
    ]
    
    for line in lines:
        elements.append(Paragraph(line, styles['Normal']))
        elements.append(Paragraph("<br/>", styles['Normal']))
        
    doc.build(elements)

def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "test_data_sets")
    os.makedirs(base_dir, exist_ok=True)
    
    for i in range(1, 11):
        set_dir = os.path.join(base_dir, f"set_{i:02d}")
        os.makedirs(set_dir, exist_ok=True)
        
        generate_gst_csv(os.path.join(set_dir, f"gst_set_{i:02d}.csv"), i)
        generate_bank_pdf(os.path.join(set_dir, f"bank_set_{i:02d}.pdf"), i)
        generate_itr_pdf(os.path.join(set_dir, f"itr_set_{i:02d}.pdf"), i)
        print(f"Generated Set {i:02d} inside {set_dir}")

if __name__ == "__main__":
    main()
