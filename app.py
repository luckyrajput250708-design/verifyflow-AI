
import re
from io import BytesIO

import pandas as pd
import streamlit as st
from pypdf import PdfReader

st.set_page_config(
    page_title="VerifyFlow AI",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 VerifyFlow AI")
st.caption("Supplier document verification for small businesses")

st.warning(
    "Prototype only. Review extracted information before acting "
    "on any discrepancy. Uploaded documents are processed in this app."
)


def extract_pdf_text(uploaded_file):
    """Extract selectable text from a PDF."""
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))

    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported.")

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")

    return "\n".join(pages).strip()


def parse_lines(text):
    """
    Supported line format:
    Product name | quantity | unit price

    Example:
    Bearing A | 100 | 500.00
    """
    rows = []

    for line in text.splitlines():
        parts = [p.strip() for p in line.split("|")]

        if len(parts) != 3:
            continue

        item, quantity, price = parts

        try:
            qty = float(quantity.replace(",", ""))
            rate = float(price.replace(",", "").replace("₹", "").strip())
        except ValueError:
            continue

        if item and qty >= 0 and rate >= 0:
            rows.append({
                "item": item,
                "quantity": qty,
                "unit_price": rate,
            })

    return pd.DataFrame(
        rows, columns=["item", "quantity", "unit_price"]
    )


st.subheader("1. Upload documents")

po_file = st.file_uploader(
    "Purchase Order PDF",
    type=["pdf"],
    key="po_pdf",
)

invoice_file = st.file_uploader(
    "Supplier Invoice PDF",
    type=["pdf"],
    key="invoice_pdf",
)

if po_file and invoice_file:
    try:
        po_text = extract_pdf_text(po_file)
        invoice_text = extract_pdf_text(invoice_file)

        with st.expander("Review extracted PDF text"):
            st.write("Purchase Order")
            st.text(po_text or "No selectable text found.")
            st.write("Supplier Invoice")
            st.text(invoice_text or "No selectable text found.")

        st.info(
            "For automatic row extraction, format each product line as: "
            "Product name | quantity | unit price. "
            "Review extracted values before comparing."
        )

        po = parse_lines(po_text)
        inv = parse_lines(invoice_text)

        if po.empty or inv.empty:
            st.error(
                "Could not extract supported product rows from both PDFs. "
                "Use the format shown above, or enter data manually below."
            )
        else:
            st.success(
                f"Extracted {len(po)} purchase-order rows and "
                f"{len(inv)} invoice rows."
            )

            st.subheader("2. Verify extracted data")
            st.write("Purchase Order")
            po = st.data_editor(po, num_rows="dynamic", key="po_editor")
            st.write("Invoice")
            inv = st.data_editor(inv, num_rows="dynamic", key="inv_editor")

            if st.button("Compare documents", type="primary"):
                po = po.copy()
                inv = inv.copy()

                po["item_key"] = po["item"].str.strip().str.casefold()
                inv["item_key"] = inv["item"].str.strip().str.casefold()

                merged = po.merge(
                    inv,
                    on="item_key",
                    how="outer",
                    suffixes=("_po", "_invoice"),
                    indicator=True,
                )

                merged["Item"] = merged["item_po"].fillna(
                    merged["item_invoice"]
                )
                merged["PO quantity"] = merged["quantity_po"]
                merged["Invoice quantity"] = merged["quantity_invoice"]
                merged["PO unit price"] = merged["unit_price_po"]
                merged["Invoice unit price"] = merged["unit_price_invoice"]

                merged["PO total (₹)"] = (
                    merged["quantity_po"] * merged["unit_price_po"]
                )
                merged["Invoice total (₹)"] = (
                    merged["quantity_invoice"] * merged["unit_price_invoice"]
                )

                
                 merged["Difference (₹)"] = (
                     merged["Invoice total (₹)"] - merged["PO total (₹)"]
                )

                def explain(row):
                    reasons = []

                    if row["_merge"] == "left_only":
                        reasons.append("Missing from invoice")
                    elif row["_merge"] == "right_only":
                        reasons.append("Not found in purchase order")
                    else:
                        if abs(
                            row["quantity_invoice"] - row["quantity_po"]
                        ) > 0.000001:
                            reasons.append("Quantity differs")

                        if abs(
                            row["unit_price_invoice"] - row["unit_price_po"]
                        ) > 0.005:
                            reasons.append("Unit price differs")

                        if abs(row["Difference (₹)"]) > 0.01:
                            reasons.append("Line total differs")

                    return "; ".join(reasons) if reasons else "No discrepancy detected"

                merged["Review status"] = merged.apply(explain, axis=1)

                columns = [
                    "Item",
                    "PO quantity",
                    "Invoice quantity",
                    "PO unit price",
                    "Invoice unit price",
                    "PO total (₹)",
                    "Invoice total (₹)",
                    "Difference (₹)",
                    "Review status",
                ]

                results = merged[columns]

                st.subheader("3. Discrepancy report")
                st.dataframe(results, use_container_width=True, hide_index=True)

                st.download_button(
                    "Download review report (CSV)",
                    data=results.to_csv(index=False).encode("utf-8"),
                    file_name="verifyflow_review_report.csv",
                    mime="text/csv",
                )

    except Exception as exc:
        st.error(f"Could not process the PDFs: {exc}")

else:
    st.info("Upload both PDFs to begin verification.")

    st.subheader("Demo mode")
    st.write(
        "PDF comparison requires supported product rows in both documents. "
        "Scanned PDFs need OCR, which is not included in this version."
            )
    
