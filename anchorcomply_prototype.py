import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import io
import base64
from dateutil.relativedelta import relativedelta

# Page config
st.set_page_config(page_title="AnchorComply Prototype", page_icon="📊", layout="wide")

# App title and description
st.title("📊 AnchorComply Prototype")
st.markdown("Quick compliance checks for GST/GSTR filings with PDF reporting")

# Initialize session state
if 'invoice_data' not in st.session_state:
    st.session_state.invoice_data = None
if 'gstr1_data' not in st.session_state:
    st.session_state.gstr1_data = None
if 'gstr3b_data' not in st.session_state:
    st.session_state.gstr3b_data = None
if 'mapping_config' not in st.session_state:
    st.session_state.mapping_config = {}

# Sample data for testing
def create_sample_data():
    sample_invoices = pd.DataFrame({
        'invoice_no': ['INV-001', 'INV-002', 'INV-003', 'INV-004'],
        'invoice_date': ['2024-01-15', '2024-01-16', '2024-01-17', '2024-01-18'],
        'customer_gstin': ['29ABCDE1234F1Z5', '27FGHIJ5678K9L0', '06MNOPQ9012R3S4', ''],
        'taxable_value': [10000, 15000, 20000, 5000],
        'igst': [1800, 2700, 3600, 0],
        'cgst': [0, 0, 0, 450],
        'sgst': [0, 0, 0, 450],
        'total_amount': [11800, 17700, 23600, 5900]
    })
    
    sample_gstr1 = pd.DataFrame({
        'invoice_number': ['INV-001', 'INV-002', 'INV-005'],
        'invoice_date': ['2024-01-15', '2024-01-16', '2024-01-20'],
        'gstin': ['29ABCDE1234F1Z5', '27FGHIJ5678K9L0', '32STUVW3456X7Y8'],
        'taxable_value': [10000, 15000, 25000],
        'igst': [1800, 2700, 4500],
        'total_value': [11800, 17700, 29500]
    })
    
    sample_gstr3b = pd.DataFrame({
        'month': ['Jan-2024', 'Jan-2024', 'Jan-2024'],
        'gstin': ['29ABCDE1234F1Z5', '27FGHIJ5678K9L0', '32STUVW3456X7Y8'],
        'tax_paid': [1800, 2700, 4500],
        'filing_date': ['2024-02-20', '2024-02-21', '2024-02-22']
    })
    
    return sample_invoices, sample_gstr1, sample_gstr3b

# File upload section
st.sidebar.header("📁 Upload Files")
st.sidebar.info("Upload your invoice data, GSTR-1, and GSTR-3B files")

uploaded_invoices = st.sidebar.file_uploader("Invoice Data (CSV/XLSX)", type=['csv', 'xlsx'])
uploaded_gstr1 = st.sidebar.file_uploader("GSTR-1 Data (CSV/XLSX)", type=['csv', 'xlsx'])
uploaded_gstr3b = st.sidebar.file_uploader("GSTR-3B Data (CSV/XLSX)", type=['csv', 'xlsx'])

# Load sample data button
if st.sidebar.button("Use Sample Data"):
    invoices, gstr1, gstr3b = create_sample_data()
    st.session_state.invoice_data = invoices
    st.session_state.gstr1_data = gstr1
    st.session_state.gstr3b_data = gstr3b
    st.sidebar.success("Sample data loaded!")

# Load uploaded files
def load_data(uploaded_file):
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith('.csv'):
                return pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith('.xlsx'):
                return pd.read_excel(uploaded_file, engine='openpyxl')
        except Exception as e:
            st.error(f"Error loading file: {e}")
            return None
    return None

if uploaded_invoices:
    st.session_state.invoice_data = load_data(uploaded_invoices)
if uploaded_gstr1:
    st.session_state.gstr1_data = load_data(uploaded_gstr1)
if uploaded_gstr3b:
    st.session_state.gstr3b_data = load_data(uploaded_gstr3b)

# Column mapping UI
def show_mapping_ui(df, df_name):
    st.subheader(f"Column Mapping for {df_name}")
    
    if df is not None:
        st.write("Detected columns:", list(df.columns))
        
        mapping = {}
        required_fields = {
            'invoice_data': ['invoice_no', 'invoice_date', 'customer_gstin', 'taxable_value', 'total_amount'],
            'gstr1_data': ['invoice_number', 'invoice_date', 'gstin', 'taxable_value', 'total_value'],
            'gstr3b_data': ['month', 'gstin', 'tax_paid', 'filing_date']
        }
        
        for field in required_fields[df_name]:
            options = [''] + list(df.columns)
            default_index = 0
            if field in df.columns:
                default_index = options.index(field) + 1
            mapping[field] = st.selectbox(
                f"Map to '{field}'", 
                options=options,
                index=default_index,
                key=f"{df_name}_{field}"
            )
        
        return mapping
    return {}

# Show mapping UIs if data is loaded
if st.session_state.invoice_data is not None:
    st.session_state.mapping_config['invoice_data'] = show_mapping_ui(
        st.session_state.invoice_data, 'invoice_data'
    )

if st.session_state.gstr1_data is not None:
    st.session_state.mapping_config['gstr1_data'] = show_mapping_ui(
        st.session_state.gstr1_data, 'gstr1_data'
    )

if st.session_state.gstr3b_data is not None:
    st.session_state.mapping_config['gstr3b_data'] = show_mapping_ui(
        st.session_state.gstr3b_data, 'gstr3b_data'
    )

# Apply mapping to data
def apply_mapping(df, mapping):
    if df is None:
        return None
    
    mapped_df = df.copy()
    for target_col, source_col in mapping.items():
        if source_col and source_col in df.columns:
            mapped_df[target_col] = df[source_col]
        elif source_col:
            mapped_df[target_col] = None
    
    # Keep only mapped columns
    keep_cols = [col for col in mapping.values() if col]
    return mapped_df[keep_cols] if keep_cols else None

# Audit functions
def find_mismatched_invoices(invoices, gstr1):
    if invoices is None or gstr1 is None:
        return pd.DataFrame()
    
    # Find invoices not in GSTR-1
    merged = invoices.merge(gstr1, left_on='invoice_no', right_on='invoice_number', how='left', indicator=True)
    mismatched = merged[merged['_merge'] == 'left_only']
    
    return mismatched

def find_duplicate_invoices(invoices):
    if invoices is None:
        return pd.DataFrame()
    
    duplicates = invoices[invoices.duplicated(subset=['invoice_no'], keep=False)]
    return duplicates

def calculate_late_fees(gstr3b, filing_deadline_day=20):
    if gstr3b is None:
        return pd.DataFrame()
    
    gstr3b = gstr3b.copy()
    gstr3b['filing_date'] = pd.to_datetime(gstr3b['filing_date'])
    gstr3b['month'] = pd.to_datetime(gstr3b['month'])
    
    gstr3b['deadline_date'] = gstr3b['month'] + pd.offsets.MonthEnd(0)
    gstr3b['deadline_date'] = gstr3b['deadline_date'].apply(
        lambda x: x.replace(day=filing_deadline_day)
    )
    
    gstr3b['days_late'] = (gstr3b['filing_date'] - gstr3b['deadline_date']).dt.days
    gstr3b['days_late'] = gstr3b['days_late'].apply(lambda x: max(0, x))
    
    gstr3b['late_fee'] = gstr3b['days_late'].apply(
        lambda x: min(5000, max(100, x * 50))  # Simplified late fee calculation
    )
    
    return gstr3b

# Run audit button
if st.button("🚀 Run Compliance Audit", type="primary"):
    if (st.session_state.invoice_data is not None and 
        st.session_state.gstr1_data is not None and 
        st.session_state.gstr3b_data is not None):
        
        # Apply mappings
        mapped_invoices = apply_mapping(
            st.session_state.invoice_data, 
            st.session_state.mapping_config.get('invoice_data', {})
        )
        mapped_gstr1 = apply_mapping(
            st.session_state.gstr1_data, 
            st.session_state.mapping_config.get('gstr1_data', {})
        )
        mapped_gstr3b = apply_mapping(
            st.session_state.gstr3b_data, 
            st.session_state.mapping_config.get('gstr3b_data', {})
        )
        
        # Run audits
        mismatched = find_mismatched_invoices(mapped_invoices, mapped_gstr1)
        duplicates = find_duplicate_invoices(mapped_invoices)
        late_fees = calculate_late_fees(mapped_gstr3b)
        
        # Store results
        st.session_state.audit_results = {
            'mismatched': mismatched,
            'duplicates': duplicates,
            'late_fees': late_fees,
            'summary': {
                'total_invoices': len(mapped_invoices) if mapped_invoices is not None else 0,
                'mismatched_count': len(mismatched),
                'duplicates_count': len(duplicates),
                'total_late_fees': late_fees['late_fee'].sum() if not late_fees.empty else 0
            }
        }
        
        st.success("Audit completed successfully!")
        
        # Show summary
        st.subheader("📊 Audit Summary")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Invoices", st.session_state.audit_results['summary']['total_invoices'])
        col2.metric("Mismatched", st.session_state.audit_results['summary']['mismatched_count'])
        col3.metric("Duplicates", st.session_state.audit_results['summary']['duplicates_count'])
        col4.metric("Total Late Fees", f"₹{st.session_state.audit_results['summary']['total_late_fees']:,.2f}")
        
        # Show details
        if not mismatched.empty:
            with st.expander("🔍 Mismatched Invoices (not in GSTR-1)"):
                st.dataframe(mismatched)
        
        if not duplicates.empty:
            with st.expander("⚠️ Duplicate Invoices"):
                st.dataframe(duplicates)
        
        if not late_fees.empty:
            with st.expander("⏰ Late Filing Details"):
                st.dataframe(late_fees)
    else:
        st.error("Please upload all required files or use sample data")

# PDF generation
def create_pdf_report(results):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30
    )
    story.append(Paragraph("AnchorComply Compliance Audit Report", title_style))
    story.append(Spacer(1, 12))
    
    # Summary
    story.append(Paragraph("Summary", styles['Heading2']))
    summary_data = [
        ['Metric', 'Value'],
        ['Total Invoices', str(results['summary']['total_invoices'])],
        ['Mismatched Invoices', str(results['summary']['mismatched_count'])],
        ['Duplicate Invoices', str(results['summary']['duplicates_count'])],
        ['Total Late Fees', f"₹{results['summary']['total_late_fees']:,.2f}"]
    ]
    
    summary_table = Table(summary_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 20))
    
    # Details
    if not results['mismatched'].empty:
        story.append(PageBreak())
        story.append(Paragraph("Mismatched Invoices", styles['Heading2']))
        mismatched_data = [list(results['mismatched'].columns)] + results['mismatched'].values.tolist()
        mismatched_table = Table(mismatched_data)
        mismatched_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(mismatched_table)
    
    doc.build(story)
    buffer.seek(0)
    return buffer

# Download PDF button
if 'audit_results' in st.session_state:
    st.subheader("📄 Download Report")
    pdf_buffer = create_pdf_report(st.session_state.audit_results)
    
    st.download_button(
        label="Download PDF Report",
        data=pdf_buffer,
        file_name=f"compliance_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/pdf"
    )

# Help section
with st.sidebar.expander("ℹ️ Help & Instructions"):
    st.markdown("""
    **Supported Files:**
    - CSV or XLSX files
    - Invoice data, GSTR-1, and GSTR-3B exports
    
    **Required Columns:**
    - Invoices: invoice_no, invoice_date, customer_gstin, taxable_value, total_amount
    - GSTR-1: invoice_number, invoice_date, gstin, taxable_value, total_value
    - GSTR-3B: month, gstin, tax_paid, filing_date
    
    **Sample Data:**
    Click "Use Sample Data" to test with sample records.
    
    **Mapping:**
    Map your CSV columns to expected format if auto-detection fails.
    """)

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown("**AnchorComply Prototype** v1.0")
