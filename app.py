from io import BytesIO

import pandas as pd
import streamlit as st
from pypdf import PdfReader

st.set_page_config(page_title="VerifyFlow AI", page_icon="🔎", layout="wide")

st.title("🔎 VerifyFlow AI")
st.subheader("Supplier Document Discrepancy Detection")
st.write("Compare purchase orders, supplier invoices, and delivery receipts.")

st.info(
    "Supports text-based PDFs with product rows formatted as: "
    "Product name | Quantity | Unit Price. Scanned PDFs need OCR."
)


def extract_pdf_text(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))

    if reader.is_encrypted:
        raise ValueError("PDF is password-protected.")

    text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    ).strip()

    if not text:
        raise ValueError(
            "No selectable text found. This PDF may be scanned."
        )

    return text


def parse_product_lines(text, label):
    rows = []

    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]

        if len(parts) != 3:
            continue

        name, qty_text, price_text = parts

        try:
            qty = float(qty_text.replace(",", ""))
            price = float(
                price_text.replace(",", "")
                .replace("₹", "")
                .replace("INR", "")
                .strip()
            )
        except ValueError:
            continue

        if name and qty >= 0 and price >= 0:
            rows.append({
                "Product": name,
                "Quantity": qty,
                "Unit Price": price,
            })

    if not rows:
        raise ValueError(
            f"No product rows found in {label}. "
            "Expected: Product name | Quantity | Unit Price"
        )

    return pd.DataFrame(rows)


def normalize(frame):
    result = frame.copy()

    result["Product"] = (
        result["Product"].fillna("").astype(str).str.strip()
    )
    result["Product Key"] = (
        result["Product"].str.casefold().str.replace(
            r"\s+", " ", regex=True
        )
    )
    result["Quantity"] = pd.to_numeric(
        result["Quantity"], errors="coerce"
    )
    result["Unit Price"] = pd.to_numeric(
        result["Unit Price"], errors="coerce"
    )

    result = result[
        (result["Product Key"] != "")
        & result["Quantity"].notna()
        & result["Unit Price"].notna()
        & (result["Quantity"] >= 0)
        & (result["Unit Price"] >= 0)
    ]

    if result.empty:
        raise ValueError("No valid product rows found.")

    return result


def combine_duplicates(frame):
    return (
        frame.groupby("Product Key", as_index=False)
        .agg(
            Product=("Product", "first"),
            Quantity=("Quantity", "sum"),
            **{"Unit Price": ("Unit Price", "mean")},
        )
    )


def compare_documents(po_frame, invoice_frame, delivery_frame=None):
    po = combine_duplicates(normalize(po_frame)).set_index("Product Key")
    inv = combine_duplicates(normalize(invoice_frame)).set_index("Product Key")

    delivery = None
    if delivery_frame is not None:
        delivery = combine_duplicates(
            normalize(delivery_frame)
        ).set_index("Product Key")

    keys = set(po.index) | set(inv.index)
    if delivery is not None:
        keys |= set(delivery.index)

    rows = []

    for key in sorted(keys):
        p = po.loc[key] if key in po.index else None
        i = inv.loc[key] if key in inv.index else None
        d = (
            delivery.loc[key]
            if delivery is not None and key in delivery.index
            else None
        )

        product = (
            p["Product"] if p is not None
            else i["Product"] if i is not None
            else d["Product"]
        )

        pq = float(p["Quantity"]) if p is not None else None
        pr = float(p["Unit Price"]) if p is not None else None
        iq = float(i["Quantity"]) if i is not None else None
        ir = float(i["Unit Price"]) if i is not None else None
        dq = float(d["Quantity"]) if d is not None else None

        po_total = pq * pr if p is not None else None
        inv_total = iq * ir if i is not None else None

        issues = []

        if p is None:
            issues.append("Not found in purchase order")
        if i is None:
            issues.append("Missing from invoice")

        if p is not None and i is not None:
            if abs(iq - pq) > 0.000001:
                issues.append("Invoice quantity differs")
            if abs(ir - pr) > 0.005:
                issues.append("Unit price differs")
            if abs(inv_total - po_total) > 0.01:
                issues.append("Line total differs")

        if delivery is not None:
            if d is None:
                issues.append("Missing from delivery receipt")
            elif p is not None and abs(dq - pq) > 0.000001:
                issues.append("Delivered quantity differs from PO")

        rows.append({
            "Product": product,
            "PO Quantity": pq,
            "Invoice Quantity": iq,
            "Delivered Quantity": dq,
            "PO Unit Price": pr,
            "Invoice Unit Price": ir,
            "PO Total": po_total,
            "Invoice Total": inv_total,
            "Quantity Difference (Invoice - PO)": (
                iq - pq if p is not None and i is not None else None
            ),
            "Rate Difference (Invoice - PO)": (
                ir - pr if p is not None and i is not None else None
            ),
            "Total Difference (Invoice - PO)": (
                inv_total - po_total
                if p is not None and i is not None else None
            ),
            "Delivery Difference (Delivered - PO)": (
                dq - pq if p is not None and d is not None else None
            ),
            "Review Status": (
                "; ".join(issues) if issues else "No discrepancy detected"
            ),
        })

    return pd.DataFrame(rows)


if "vf_data" not in st.session_state:
    st.session_state["vf_data"] = None

if "vf_report" not in st.session_state:
    st.session_state["vf_report"] = None


st.header("1. Upload documents")

po_file = st.file_uploader(
    "Purchase Order PDF (required)", type=["pdf"], key="po_upload"
)
invoice_file = st.file_uploader(
    "Supplier Invoice PDF (required)", type=["pdf"], key="invoice_upload"
)
delivery_file = st.file_uploader(
    "Delivery Receipt PDF (optional)", type=["pdf"], key="delivery_upload"
)

if st.button("Extract PDFs and prepare comparison", type="primary"):
    if po_file is None or invoice_file is None:
        st.error("Upload both the Purchase Order and Supplier Invoice PDFs.")
    else:
        try:
            po_text = extract_pdf_text(po_file)
            invoice_text = extract_pdf_text(invoice_file)

            po_data = parse_product_lines(po_text, "purchase order")
            invoice_data = parse_product_lines(invoice_text, "supplier invoice")

            delivery_text = ""
            delivery_data = None

            if delivery_file is not None:
                delivery_text = extract_pdf_text(delivery_file)
                delivery_data = parse_product_lines(
                    delivery_text, "delivery receipt"
                )

            st.session_state["vf_data"] = {
                "po_text": po_text,
                "invoice_text": invoice_text,
                "delivery_text": delivery_text,
                "po_data": po_data,
                "invoice_data": invoice_data,
                "delivery_data": delivery_data,
            }

            st.session_state["vf_report"] = None
            st.success("PDFs extracted successfully.")

        except Exception as exc:
            st.session_state["vf_data"] = None
            st.session_state["vf_report"] = None
            st.error(f"Could not process PDFs: {exc}")


data = st.session_state["vf_data"]

if data is not None:
    with st.expander("Review extracted PDF text"):
        st.markdown("**Purchase Order**")
        st.text(data["po_text"])
        st.markdown("**Supplier Invoice**")
        st.text(data["invoice_text"])

        if data["delivery_text"]:
            st.markdown("**Delivery Receipt**")
            st.text(data["delivery_text"])

    st.header("2. Review extracted product data")
    st.caption("Check the values before generating the report.")

    po_edit = st.data_editor(
        data["po_data"],
        num_rows="dynamic",
        use_container_width=True,
        key="po_editor",
    )

    invoice_edit = st.data_editor(
        data["invoice_data"],
        num_rows="dynamic",
        use_container_width=True,
        key="invoice_editor",
    )

    delivery_edit = None

    if data["delivery_data"] is not None:
        st.markdown("**Delivery receipt data**")
        delivery_edit = st.data_editor(
            data["delivery_data"],
            num_rows="dynamic",
            use_container_width=True,
            key="delivery_editor",
        )

    if st.button("Generate discrepancy report", type="primary"):
        try:
            results = compare_documents(
                po_edit, invoice_edit, delivery_edit
            )
            st.session_state["vf_report"] = results
        except Exception as exc:
            st.session_state["vf_report"] = None
            st.error(f"Could not generate report: {exc}")


results = st.session_state["vf_report"]

if results is not None:
    st.header("3. Discrepancy report")

    flagged = results[
        results["Review Status"] != "No discrepancy detected"
    ]

    col1, col2 = st.columns(2)
    col1.metric("Products reviewed", len(results))
    col2.metric("Products flagged", len(flagged))

    st.dataframe(
        results,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download discrepancy report (CSV)",
        data=results.to_csv(index=False).encode("utf-8"),
        file_name="verifyflow_discrepancy_report.csv",
        mime="text/csv",
    )

    if flagged.empty:
        st.success("No discrepancies detected.")
    else:
        st.warning(
            "Discrepancies found. Review the flagged rows before taking action."
        )

st.divider()
st.caption(
    "VerifyFlow AI prototype | PDF text extraction with pypdf | "
    "Scanned PDF OCR is not included."
    )
