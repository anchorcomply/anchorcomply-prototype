# anchorcomply_prototype.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from io import BytesIO
from difflib import get_close_matches
import re
from fpdf import FPDF

st.set_page_config(page_title="AnchorComply Prototype", layout="wide")

st.title("AnchorComply — Prototype Audit Assistant")
st.markdown("Upload CSVs (sales invoices, GSTR-1, GSTR-3B). Prototype flags: invoice mismatch, duplicates, delayed filings. Use mapping UI if headers differ.")

# -----------------------
# Helper functions
# -----------------------
def norm_col(c):
    return re.sub(r'[^a-z0-9]', '', c.lower())

def fuzzy_match(columns, candidates, cutoff=0.6):
    cols_norm = {norm_col(c): c for c in columns}
    norm_map = list(cols_norm.keys())
    for cand in candidates:
        matches = get_close_matches(norm_col(cand), norm_map, n=1, cutoff=cutoff)
        if matches:
            return cols_norm[matches[0]]
    return None

def to_num(s):
    if pd.isna(s): return 0.0
    if isinstance(s, (int, float)): return float(s)
    try:
        s = str(s).replace(',', '').replace('(', '-').replace(')', '').strip()
        return float(s) if s!='' else 0.0
    except:
        return 0.0

def parse_date_series(s):
    try:
        return pd.to_datetime(s, dayfirst=False, errors='coerce').dt.date
    except:
        return pd.to_datetime(s, errors='coerce').dt.date

# robust file reader
def read_any(fileobj):
    if fileobj is None: return None
    try:
        name = getattr(fileobj, "name", "")
        fileobj.seek(0)
        if name.lower().endswith(".xlsx"):
            return pd.read_excel(fileobj, dtype=str)
        else:
            # try default csv read (handles most)
            fileobj.seek(0)
            txt = fileobj.read()
            # streamlit gives bytes; handle that
            if isinstance(txt, bytes):
                b = BytesIO(txt)
                try:
                    return pd.read_csv(b, dtype=str)
                except:
                    b.seek(0)
                    return pd.read_csv(b, sep=';', dtype=str, engine='python')
            else:
                return pd.read_csv(BytesIO(txt.encode('utf-8')), dtype=str)
    except Exception as e:
        st.sidebar.error(f"Read failed: {e}")
        return None

# -----------------------
# Upload & Mapping UI
# -----------------------
st.sidebar.header("Upload & Map Files")
sales_file = st.sidebar.file_uploader("Upload sales / invoices (CSV or XLSX)", type=["csv","xlsx"])
gstr1_file = st.sidebar.file_uploader("Upload GSTR-1 (optional)", type=["csv","xlsx"])
gstr3b_file = st.sidebar.file_uploader("Upload GSTR-3B (optional)", type=["csv","xlsx"])

sales_df_raw = read_any(sales_file)
gstr1_df_raw = read_any(gstr1_file)
gstr3b_df_raw = read_any(gstr3b_file)

def show_map_ui(df, name, required_fields):
    if df is None:
        st.sidebar.info(f"Upload {name} to map columns")
        return None
    st.sidebar.markdown(f"**{name} - Column mapping**")
    cols = list(df.columns)
    mapping = {}
    for field, label in required_fields.items():
        candidates = label if isinstance(label, list) else [label]
        auto = None
        for cand in candidates:
            auto = fuzzy_match(cols, candidates)
        mapping[field] = st.sidebar.selectbox(f"Map '{field}'", options=[""]+cols, index=(cols.index(auto)+1 if auto else 0))
    st.sidebar.write(df.head(3))
    return mapping

sales_map = show_map_ui(sales_df_raw, "Sales / Invoices", {
    "invoice_no":["invoice","invoice_no","billno","bill_number","invno","inv_no"],
    "date":["date","invoice_date","bill_date","created_date"],
    "customer_gstin":["gstin","customer_gstin","buyer_gstin","gst_no"],
    "taxable_value":["taxable_value","taxable","value","amount","net_amount"],
    "igst":["igst"],
    "cgst":["cgst"],
    "sgst":["sgst"]
})
gstr1_map = show_map_ui(gstr1_df_raw, "GSTR-1", {
    "invoice_no":["invoice","invoice_no","invno","inv_no"],
    "date":["date","invoice_date"],
    "taxable_value":["taxable_value","taxable","value"]
})
gstr3b_map = show_map_ui(gstr3b_df_raw, "GSTR-3B", {
    "month":["month","period","tax_period"],
    "filing_date":["filing_date","date_of_filing","filed_on","filingdate"],
    "total_tax_paid":["total_tax_paid","tax_paid","total_tax"]
})

def materialize(df_raw, mapping):
    if df_raw is None or mapping is None:
        return None
    df = df_raw.copy()
    rename_map = {}
    for standard, colname in mapping.items():
        if colname and colname in df.columns:
            rename_map[colname] = standard
    df = df.rename(columns=rename_map)
    if 'date' in df.columns:
        df['date'] = parse_date_series(df['date'])
    if 'filing_date' in df.columns:
        df['filing_date'] = parse_date_series(df['filing_date'])
    for ncol in ['taxable_value','igst','cgst','sgst','total_tax_paid']:
        if ncol in df.columns:
            df[ncol] = df[ncol].apply(to_num)
    return df

sales_df = materialize(sales_df_raw, sales_map)
gstr1_df = materialize(gstr1_df_raw, gstr1_map)
gstr3b_df = materialize(gstr3b_df_raw, gstr3b_map)

# -----------------------
# Main Audit Logic
# -----------------------
st.header("Run Audit Checks")
late_fee_per_day = st.number_input("Late fee per day (prototype estimate)", value=50, step=10)

if st.button("Run Audit"):
    if sales_df is None:
        st.error("Please upload and map your Sales/Invoices file.")
    else:
        st.success("Running checks...")
        # Ensure gstr1 exists (can be None)
        if gstr1_df is None:
            gstr1_df = pd.DataFrame(columns=[])
        # 1) MISMATCH
        if 'invoice_no' in sales_df.columns:
            merged = sales_df.merge(gstr1_df[['invoice_no','taxable_value']].rename(columns={'taxable_value':'gstr1_taxable'}), on='invoice_no', how='left')
        else:
            # fallback: no invoice_no — attempt to match by date+amount+customer
            merged = sales_df.copy()
            merged['gstr1_taxable'] = pd.NA
        # numeric ensure
        merged['taxable_value'] = merged.get('taxable_value', pd.Series([0]*len(merged))).apply(to_num)
        merged['gstr1_taxable'] = merged.get('gstr1_taxable', pd.Series([pd.NA]*len(merged))).apply(lambda x: to_num(x) if not pd.isna(x) else pd.NA)
        merged['diff'] = (merged['taxable_value'] - merged['gstr1_taxable']).abs()
        merged['mismatch_flag'] = merged['gstr1_taxable'].isnull() | (merged['diff'] > 1.0)
        mismatches = merged[merged['mismatch_flag']].copy().fillna('')
        st.subheader("Mismatched / Missing Invoices")
        st.dataframe(mismatches.head(50))

        # 2) DUPLICATES
        dup_by_no = pd.DataFrame()
        dup_by_combo = pd.DataFrame()
        if 'invoice_no' in sales_df.columns:
            dup_by_no = sales_df[sales_df.duplicated(subset=['invoice_no'], keep=False)].copy()
        # combo duplicates
        combo_cols = [c for c in ['taxable_value','date','customer_gstin'] if c in sales_df.columns]
        if combo_cols:
            dup_by_combo = sales_df[sales_df.duplicated(subset=combo_cols, keep=False)].copy()
        st.subheader("Possible Duplicates")
        if not dup_by_no.empty:
            st.markdown("**Duplicate invoice numbers**")
            st.dataframe(dup_by_no)
        if not dup_by_combo.empty:
            st.markdown("**Possible duplicate entries (amount + date + customer)**")
            st.dataframe(dup_by_combo)
        if dup_by_no.empty and dup_by_combo.empty:
            st.write("No obvious duplicates found in uploaded invoices.")

        # 3) DELAYED FILINGS
        late_rows = []
        if gstr3b_df is not None and not gstr3b_df.empty:
            for idx, row in gstr3b_df.iterrows():
                try:
                    m = row.get('month', None)
                    if isinstance(m, str) and len(m) >= 7:
                        due = datetime.strptime(m + "-20", "%Y-%m-%d").date()
                    else:
                        due = None
                    filed = row.get('filing_date', None)
                    if pd.isna(filed):
                        filed = None
                    if isinstance(filed, pd.Timestamp):
                        filed = filed.date()
                    if due and filed:
                        days_late = (filed - due).days
                        if days_late > 0:
                            late_rows.append({
                                'month': row.get('month'),
                                'due_date': due,
                                'filing_date': filed,
                                'days_late': days_late,
                                'estimated_fee': int(days_late * late_fee_per_day)
                            })
                except Exception:
                    continue
        st.subheader("Delayed Filings & Estimated Late Fees")
        if late_rows:
            lf_df = pd.DataFrame(late_rows)
            st.dataframe(lf_df)
        else:
            st.write("No delayed filings found in provided GSTR-3B file.")

        # Summary
        total_potential_penalty = sum([r['estimated_fee'] for r in late_rows]) if late_rows else 0
        st.markdown("---")
        st.subheader("Summary")
        st.write(f"Total mismatches found: **{len(mismatches)}**")
        st.write(f"Total duplicate records flagged: **{len(dup_by_no) + len(dup_by_combo)}**")
        st.write(f"Estimated late filing fees (prototype calc): **₹{total_potential_penalty:,}**")

        # -----------------------
        # PDF generation with fpdf2
        # -----------------------
        def make_pdf_buffer(summary_text, mismatches_df, duplicates_df, late_df):
            pdf = FPDF()
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()
            pdf.set_font("Arial", "B", 14)
            pdf.cell(0, 8, "AnchorComply — Audit Summary Report (Prototype)", ln=True)
            pdf.ln(4)
            pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 6, summary_text)
            pdf.ln(4)
            if not mismatches_df.empty:
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 6, "Mismatched / Missing Invoices (sample):", ln=True)
                pdf.ln(2)
                pdf.set_font("Courier", size=9)
                for i, row in mismatches_df.head(10).iterrows():
                    inv = str(row.get('invoice_no',''))
                    dt = str(row.get('date',''))
                    salesv = str(row.get('taxable_value',''))
                    gstrv = str(row.get('gstr1_taxable',''))
                    diffv = str(row.get('diff',''))
                    line = f"{inv} | {dt} | Sales:{salesv} | GSTR1:{gstrv} | Diff:{diffv}"
                    pdf.multi_cell(0, 5, line)
                pdf.ln(4)
            if not duplicates_df.empty:
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 6, "Duplicate entries (sample):", ln=True)
                pdf.ln(2)
                pdf.set_font("Courier", size=9)
                for i, row in duplicates_df.head(10).iterrows():
                    inv = str(row.get('invoice_no',''))
                    dt = str(row.get('date',''))
                    amt = str(row.get('taxable_value',''))
                    cust = str(row.get('customer_gstin',''))
                    line = f"{inv} | {dt} | {amt} | {cust}"
                    pdf.multi_cell(0, 5, line)
                pdf.ln(4)
            if late_df is not None and not late_df.empty:
                pdf.set_font("Arial", "B", 12)
                pdf.cell(0, 6, "Delayed Filings (sample):", ln=True)
                pdf.ln(2)
                pdf.set_font("Courier", size=9)
                for i, row in late_df.head(10).iterrows():
                    line = f"{row.month} | Filed: {row.filing_date} | Days late: {row.days_late} | Fee: ₹{row.estimated_fee}"
                    pdf.multi_cell(0, 5, line)
                pdf.ln(4)
            pdf.set_font("Arial", size=10)
            pdf.multi_cell(0, 6, "Action: Reconcile mismatched invoices with GSTR-1, correct duplicates, and ensure timely filings to avoid penalties.")
            pdf.ln(6)
            pdf.set_font("Arial", size=8)
            pdf.multi_cell(0, 5, "Confidential: This report is a prototype estimate. For final compliance work consult your CA.")
            # output bytes
            buf = BytesIO()
            buf.write(pdf.output(dest='S').encode('latin-1'))
            buf.seek(0)
            return buf

        pdf_buf = make_pdf_buffer(f"AnchorComply Prototype report: {len(mismatches)} mismatches, {len(dup_by_no)+len(dup_by_combo)} duplicates, estimated fees ₹{total_potential_penalty:,}.", mismatches, pd.concat([dup_by_no, dup_by_combo]).drop_duplicates() if (not dup_by_no.empty or not dup_by_combo.empty) else pd.DataFrame(), pd.DataFrame(late_rows))
        st.download_button("Download PDF Report", data=pdf_buf, file_name="anchorcomply_report.pdf", mime="application/pdf")

# -----------------------
# Help / Import Guide
# -----------------------
with st.expander("📖 Help & Import Guide"):
    st.markdown("""
    ### AnchorComply — Audit & Import Guide

    **CSV Templates (required headers):**

    **A) sales_invoices.csv**
    ```
    invoice_no,date,customer_gstin,taxable_value,igst,cgst,sgst,hsn,place_of_supply
    ```
    - `date`: YYYY-MM-DD  
    - `taxable_value, igst, cgst, sgst`: numbers only  
    - `customer_gstin`: GSTIN of buyer  

    **B) gstr1.csv**
    ```
    invoice_no,date,customer_gstin,taxable_value,igst,cgst,sgst
    ```

    **C) gstr3b.csv**
    ```
    month,return_type,filing_date,total_outward_taxable_value,total_tax_paid
    ```

    ---

    ### Audit Logic (prototype)
    - **Invoice mismatch**: flags invoices missing or differing between sales vs GSTR-1.  
    - **Duplicates**: flags duplicate invoice numbers or same-date+amount+customer combos.  
    - **Delayed filings**: prototype assumes due = 20th of next month; compares to filing_date and estimates a fee.

    """)
