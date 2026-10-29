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
st.subheader("Supplier Document Discrepancy Detection")
st.write(
    "Compare purchase orders, supplier invoices, "
    "and delivery receipts using PDF text extraction."
)

st.warning(
    "Prototype: review all extracted values before relying on a report. "
    "Only text-based PDFs with the supported row format are parsed."
)


def extract_pdf_text(uploaded_file):
    """Extract selectable text from a PDF upload."""
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))

    if reader.is_encrypted:
        raise ValueError(
            "This PDF is password-protected. Upload an unlocked PDF."
        )

    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")

    text = "\n".join(pages).strip()

    if not text:
        raise ValueError(
            "No selectable text was found. The PDF may be scanned "
            "and require OCR."
        )

    return text


def parse_product_lines(text):
    """
    Read product lines in this format:
    Product name | quantity | unit price
    """
    rows = []

    for line in text.splitlines():
        parts = [part.strip() for part in line.split("|")]

        if len(parts) != 3:
            continue

        item, quantity_text, price_text = parts

        try:
            quantity = float(
                quantity_text.replace(",", "")
            )
            price = float(
                price_text.replace(",", "")
                .replace("₹", "")
                .replace("INR", "")
                .strip()
            )
        except ValueError:
            continue

        if item and quantity >= 0 and price >= 0:
            rows.append(
                {
                    "Product": item,
                    "Quantity": quantity,
                    "Unit Price": price,
                }
            )

    return pd.DataFrame(
        rows,
        columns=["Product", "Quantity", "Unit Price"],
    )


def normalize_products(frame):
    """Normalize product names and numeric fields."""
    result = frame.copy()

    result["Product"] = result["Product"].fillna("").astype(str).str.strip()
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

    return result


def read_document(uploaded_file, label):
    """Extract and parse one uploaded document."""
    text = extract_pdf_text(uploaded_file)
    products = parse_product_lines(text)

    if products.empty:
        raise ValueError(
            f"No supported product rows found in {label}. "
            "Use: Product name | quantity | unit price"
        )

    return text, normalize_products(products)


def combine_duplicate_products(frame):
    """Combine repeated rows for the same product."""
    return (
        frame.groupby("Product Key", as_index=False)
        .agg(
            Product=("Product", "first"),
            Quantity=("Quantity", "sum"),
            **{"Unit Price": ("Unit Price", "mean")},
        )
    )


st.header("1. Upload your documents")

po_file = st.file_uploader(
    "Purchase Order PDF (required)",
    type=["pdf"],
    key="po_upload",
)

invoice_file = st.file_uploader(
    "Supplier Invoice PDF (required)",
    type=["pdf"],
    key="invoice_upload",
)

delivery_file = st.file_uploader(
    "Delivery Receipt PDF (optional)",
    type=["pdf"],
    key="delivery_upload",
)

st.info(
    "Supported product line example: USB Keyboard | 100 | 500.00"
)

if st.button("Extract and compare documents", type="primary"):
    if not po_file or not invoice_file:
        st.error(
            "Please upload both a Purchase Order PDF "
            "and a Supplier Invoice PDF."
        )
    else:
        try:
            po_text, po_data = read_document(
                po_file, "the purchase order"
            )
            invoice_text, invoice_data = read_document(
                invoice_file, "the supplier invoice"
            )

            delivery_data = None
            delivery_text = ""

            if delivery_file:
                delivery_text, delivery_data = read_document(
                    delivery_file, "the delivery receipt"
                )

            st.success("PDF text extracted successfully.")

            with st.expander("Review extracted PDF text"):
                st.markdown("**Purchase Order**")
                st.text(po_text)

                st.markdown("**Supplier Invoice**")
                st.text(invoice_text)

                if delivery_file:
                    st.markdown("**Delivery Receipt**")
                    st.text(delivery_text)

            st.header("2. Review extracted product data")

            st.caption(
                "Check the values below. Correct any extraction "
                "errors before generating the report."
            )

            po_data = st.data_editor(
                po_data[["Product", "Quantity", "Unit Price"]],
                num_rows="dynamic",
                use_container_width=True,
                key="po_editor",
            )

            invoice_data = st.data_editor(
                invoice_data[["Product", "Quantity", "Unit Price"]],
                num_rows="dynamic",
                use_container_width=True,
                key="invoice_editor",
            )

            if delivery_data is not None:
                st.markdown("**Delivery receipt data**")

                delivery_data = st.data_editor(
                    delivery_data[
                        ["Product", "Quantity", "Unit Price"]
                    ],
                    num_rows="dynamic",
                    use_container_width=True,
                    key="delivery_editor",
                )

            if st.button("Generate discrepancy report"):
                po = normalize_products(po_data)
                invoice = normalize_products(invoice_data)

                if po.empty or invoice.empty:
                    st.error(
                        "Purchase order and invoice must each contain "
                        "at least one valid product row."
                    )
                    st.stop()

                po = combine_duplicate_products(po)
                invoice = combine_duplicate_products(invoice)

                po = po.rename(
                    columns={
                        "Product": "PO Product",
                        "Quantity": "PO Quantity",
                        "Unit Price": "PO Unit Price",
                    }
                )

                invoice = invoice.rename(
                    columns={
                        "Product": "Invoice Product",
                        "Quantity": "Invoice Quantity",
                        "Unit Price": "Invoice Unit Price",
                    }
                )

                report = po.merge(
                    invoice,
                    on="Product Key",
                    how="outer",
                    indicator="PO Invoice Match",
                )

                report["Product"] = report["PO Product"].combine_first(
                    report["Invoice Product"]
                )

                report["PO Total"] = (
                    report["PO Quantity"] * report["PO Unit Price"]
                )
                report["Invoice Total"] = (
                    report["Invoice Quantity"]
                    * report["Invoice Unit Price"]
                )

                report["Quantity Difference"] = (
                    report["Invoice Quantity"] - report["PO Quantity"]
                )
                report["Rate Difference"] = (
                    report["Invoice Unit Price"] - report["PO Unit Price"]
                )
                report["Total Difference"] = (
                    report["Invoice Total"] - report["PO Total"]
                )

                if delivery_data is not None:
                    delivery = normalize_products(delivery_data)

                    if delivery.empty:
                        st.error(
                            "The delivery receipt contains no valid rows."
                        )
                        st.stop()

                    delivery = combine_duplicate_products(delivery)
                    delivery = delivery[
                        ["Product Key", "Quantity"]
                    ].rename(
                        columns={"Quantity": "Delivered Quantity"}
                    )

                    report = report.merge(
                        delivery,
                        on="Product Key",
                        how="outer",
                        indicator="Delivery Match",
                    )

                    report["Product"] = (
                        report["Product"].combine_first(
                            report["Product Key"]
                        )
                    )

                    report["Delivered Quantity Difference"] = (
                        report["Delivered Quantity"]
                        - report["PO Quantity"]
                    )

                def review_row(row):
                    issues = []

                    if row["PO Invoice Match"] == "left_only":
                        issues.append("Missing from invoice")
                    elif row["PO Invoice Match"] == "right_only":
                        issues.append("Not found in purchase order")
                    else:
                        if abs(row["Quantity Difference"]) > 0.000001:
                            issues.append("Invoice quantity differs")

                        if abs(row["Rate Difference"]) > 0.005:
                            issues.append("Unit price differs")

                        if abs(row["Total Difference"]) > 0.01:
                            issues.append("Line total differs")

                    if delivery_data is not None:
                        if row["Delivery Match"] == "left_only":
                            issues.append("Missing from delivery receipt")
                        elif row["Delivery Match"] == "right_only":
                            issues.append("Not found in PO/invoice")
                        elif pd.notna(row["PO Quantity"]):
                            difference = row[
                                "Delivered Quantity Difference"
                            ]

                            if abs(difference) > 0.000001:
                                issues.append(
                                    "Delivered quantity differs from PO"
                                )

                    return (
                        "; ".join(issues)
                        if issues
                        else "No discrepancy detected"
                    )

                report["Review Status"] = report.apply(
                    review_row, axis=1
                )

                output_columns = [
                    "Product",
                    "PO Quantity",
                    "Invoice Quantity",
                    "PO Unit Price",
                    "Invoice Unit Price",
                    "PO Total",
                    "Invoice Total",
                    "Quantity Difference",
                    "Rate Difference",
                    "Total Difference",
                ]

                if delivery_data is not None:
                    output_columns.extend(
                        [
                            "Delivered Quantity",
                            "Delivered Quantity Difference",
                        ]
                    )

                output_columns.append("Review Status")

                results = report[output_columns].copy()

                st.header("3. Discrepancy report")

                flagged = results[
                    results["Review Status"]
                    != "No discrepancy detected"
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
                    st.success("No discrepancies were detected.")
                else:
                    st.warning(
                        "Discrepancies found. Review the flagged rows "
                        "and supporting documents before taking action."
                    )

        except Exception as error:
            st.error(f"Could not process documents: {error}")

else:
    st.caption(
        "Upload your documents and tap Extract and compare documents "
        "to begin."
    )

st.divider()
st.caption(
    "VerifyFlow AI prototype | PDF text extraction with pypdf | "
    "Scanned PDF OCR is not included."
                        )
