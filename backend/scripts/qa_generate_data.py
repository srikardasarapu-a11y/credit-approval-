import os
import random
import csv
import pandas as pd
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "qa_test_data")
os.makedirs(BASE_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_gst_csv(path, monthly_sales_list, gstin="27AAAAA1234A1Z1"):
    """
    monhly_sales_list: list of floats [sales1, sales2, ...] for Jan, Feb, Mar 2024
    """
    data = []
    months = ["01-01-2024", "01-02-2024", "01-03-2024"]
    for i, sales in enumerate(monthly_sales_list):
        month = months[i % len(months)]
        igst = sales * 0.09
        cgst = sales * 0.09
        sgst = 0
        data.append([gstin, month, sales, igst, cgst, sgst])
    
    df = pd.DataFrame(data, columns=["GSTIN", "Return Period", "Taxable Value", "IGST", "CGST", "SGST"])
    df.to_csv(path, index=False)

def generate_bank_pdf(path, transactions):
    """
    transactions: list of dicts {"Date": str, "Narration": str, "Debit": float, "Credit": float, "Balance": float}
    """
    doc = SimpleDocTemplate(path, pagesize=letter)
    elements = []
    
    data = [["Date", "Narration", "Debit", "Credit", "Balance"]]
    for tx in transactions:
        data.append([
            tx["Date"], 
            tx["Narration"], 
            f"{tx['Debit']:.2f}", 
            f"{tx['Credit']:.2f}", 
            f"{tx['Balance']:.2f}"
        ])
        
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

def generate_itr_pdf(path, gti, pan="ABCDE1234F"):
    doc = SimpleDocTemplate(path, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    
    business_income = gti * 0.8
    tax = gti * 0.2
    
    lines = [
        "INCOME TAX RETURN",
        f"PAN: {pan}",
        "Assessment Year: 2024-25",
        f"Gross Total Income: {gti}",
        f"Income from Business: {business_income}",
        f"Total Tax Paid: {tax}",
        f"Depreciation: 50000",
        f"Net Profit: {gti * 0.4}"
    ]
    
    for line in lines:
        elements.append(Paragraph(line, styles['Normal']))
        elements.append(Paragraph("<br/>", styles['Normal']))
        
    doc.build(elements)

# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def create_scenario_healthy():
    """1. Healthy Company: High sales, consistent bank credits, low EMI, no bounces."""
    target_dir = os.path.join(BASE_DIR, "scenario_healthy")
    os.makedirs(target_dir, exist_ok=True)
    
    # GST: 1M, 1.1M, 1.2M
    generate_gst_csv(os.path.join(target_dir, "gst.csv"), [1000000, 1100000, 1200000])
    
    # ITR: 10M income
    generate_itr_pdf(os.path.join(target_dir, "itr.pdf"), 10000000)
    
    # Bank Statement: Consistent credits matching GST
    txns = []
    balance = 500000
    for i in range(1, 31):
        date = (datetime(2024, 1, 1) + timedelta(days=i)).strftime("%d-%m-%Y")
        if i % 10 == 0: # Large credits
            credit = 350000
            balance += credit
            txns.append({"Date": date, "Narration": "SALARY CREDIT", "Debit": 0.0, "Credit": credit, "Balance": balance})
        else: # Small debits
            debit = 10000
            balance -= debit
            txns.append({"Date": date, "Narration": "VENDOR PAYMENT", "Debit": debit, "Credit": 0.0, "Balance": balance})
    
    # Add recurring EMI (small)
    for m in range(1, 4):
        date = f"05-0{m}-2024"
        debit = 25000
        balance -= debit
        txns.append({"Date": date, "Narration": "EMI INSTALLMENT HDFC", "Debit": debit, "Credit": 0.0, "Balance": balance})

    generate_bank_pdf(os.path.join(target_dir, "bank.pdf"), txns)

def create_scenario_overleveraged():
    """2. Overleveraged: High EMI relative to monthly net credit."""
    target_dir = os.path.join(BASE_DIR, "scenario_overleveraged")
    os.makedirs(target_dir, exist_ok=True)
    
    generate_gst_csv(os.path.join(target_dir, "gst.csv"), [500000, 500000, 500000])
    generate_itr_pdf(os.path.join(target_dir, "itr.pdf"), 4000000)
    
    # Bank Statement: Net credit 500k/mo, but EMI 300k/mo
    txns = []
    balance = 100000
    for m in range(1, 4):
        # Salary credit
        txns.append({"Date": f"01-0{m}-2024", "Narration": "SALARY CREDIT", "Debit": 0.0, "Credit": 500000, "Balance": balance+500000})
        balance += 500000
        # Heavy EMI
        txns.append({"Date": f"10-0{m}-2024", "Narration": "LOAN EMI REPAYMENT", "Debit": 300000, "Credit": 0.0, "Balance": balance-300000})
        balance -= 300000
        # Other debits
        txns.append({"Date": f"20-0{m}-2024", "Narration": "OFFICE RENT", "Debit": 100000, "Credit": 0.0, "Balance": balance-100000})
        balance -= 100000
        
    generate_bank_pdf(os.path.join(target_dir, "bank.pdf"), txns)

def create_scenario_high_bounce():
    """3. High Bounce: 3+ bounced cheques (auto-reject)."""
    target_dir = os.path.join(BASE_DIR, "scenario_high_bounce")
    os.makedirs(target_dir, exist_ok=True)
    
    generate_gst_csv(os.path.join(target_dir, "gst.csv"), [800000, 800000, 800000])
    generate_itr_pdf(os.path.join(target_dir, "itr.pdf"), 6000000)
    
    txns = []
    balance = 50000
    for i in range(1, 5):
        date = f"{i*5:02d}-01-2024"
        # Bounced cheque entry
        txns.append({"Date": date, "Narration": "CHQ RET INSUFFICIENT FUNDS", "Debit": 500.0, "Credit": 0.0, "Balance": balance-500.0})
        balance -= 500.0
        
    # Standard transactions
    txns.append({"Date": "20-01-2024", "Narration": "SALARY CREDIT", "Debit": 0.0, "Credit": 750000, "Balance": balance+750000})
    
    generate_bank_pdf(os.path.join(target_dir, "bank.pdf"), txns)

def create_scenario_anomaly_reconciliation():
    """4. Anomaly Company (Reconciliation): GST >> Bank Credits."""
    target_dir = os.path.join(BASE_DIR, "scenario_anomaly")
    os.makedirs(target_dir, exist_ok=True)
    
    # GST reported as 2M
    generate_gst_csv(os.path.join(target_dir, "gst.csv"), [2000000, 2000000, 2000000])
    generate_itr_pdf(os.path.join(target_dir, "itr.pdf"), 15000000)
    
    # but Bank credits only 1M
    txns = []
    balance = 1000000
    for m in range(1, 4):
        date = f"01-0{m}-2024"
        txns.append({"Date": date, "Narration": "BUSINESS CREDIT", "Debit": 0.0, "Credit": 1000000, "Balance": balance+1000000})
        balance += 1000000
        
    generate_bank_pdf(os.path.join(target_dir, "bank.pdf"), txns)

def create_scenario_unusual_txns():
    """5. Unusual Transactions: A few very large transactions (3x median)."""
    target_dir = os.path.join(BASE_DIR, "scenario_unusual")
    os.makedirs(target_dir, exist_ok=True)
    
    generate_gst_csv(os.path.join(target_dir, "gst.csv"), [1000000, 1000000, 1000000])
    generate_itr_pdf(os.path.join(target_dir, "itr.pdf"), 8000000)
    
    txns = []
    balance = 2000000
    # Average transaction size ~10-20k
    for i in range(1, 11):
        txns.append({"Date": f"{i:02d}-01-2024", "Narration": "SMALL DEBIT", "Debit": 15000, "Credit": 0.0, "Balance": balance-15000})
        balance -= 15000
    
    # Large unusual transaction (500k)
    txns.append({"Date": "15-01-2024", "Narration": "LARGE ONE OFF TRANSFER", "Debit": 500000, "Credit": 0.0, "Balance": balance-500000})
    balance -= 500000
    
    generate_bank_pdf(os.path.join(target_dir, "bank.pdf"), txns)

if __name__ == "__main__":
    print("Generating QA Scenarios...")
    create_scenario_healthy()
    create_scenario_overleveraged()
    create_scenario_high_bounce()
    create_scenario_anomaly_reconciliation()
    create_scenario_unusual_txns()
    print(f"Test data generated in {BASE_DIR}")
