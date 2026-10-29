from io import BytesIO
from xml.sax.saxutils import escape

import pandas as pd
import streamlit as st
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)

st.set_page_config(page_title="VerifyFlow AI", page_icon="🔎", layout="wide")
st.title("🔎 VerifyFlow AI")
st.subheader("Supplier Document Discrepancy Detection")
st.write("Compare purchase orders, supplier invoices, and delivery receipts.")
st.info("Supports text-based PDFs with product rows formatted as: Product name | Quantity | Unit Price. Scanned PDFs need OCR.")


def extract_pdf_text(uploaded_file):
    reader = PdfReader(BytesIO(uploaded_file.getvalue()))
    if reader.is_encrypted:
        raise ValueError("PDF is password-protected.")
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError("No selectable text found. This PDF may be scanned.")
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
            price = float(price_text.replace(",", "").replace("₹", "").replace("INR", "").strip())
        except ValueError:
            continue
        if name and qty >= 0 and price >= 0:
            rows.append({"Product": name, "Quantity": qty, "Unit Price": price})

    if not rows:
        raise ValueError(
            f"No product rows found in {label}. Expected: Product name | Quantity | Unit Price"
        )
    return pd.DataFrame(rows)


def normalize(frame):
    result = frame.copy()
    result["Product"] = result["Product"].fillna("").astype(str).str.strip()
    result["Product Key"] = result["Product"].str.casefold().str.replace(r"\s+", " ", regex=True)
    result["Quantity"] = pd.to_numeric(result["Quantity"], errors="coerce")
    result["Unit Price"] = pd.to_numeric(result["Unit Price"], errors="coerce")
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
        delivery = combine_duplicates(normalize(delivery_frame)).set_index("Product Key")

    keys = set(po.index) | set(inv.index)
    if delivery is not None:
        keys |= set(delivery.index)

    rows = []
    for key in sorted(keys):
        p = po.loc[key] if key in po.index else None
        i = inv.loc[key] if key in inv.index else None
        d = delivery.loc[key] if delivery is not None and key in delivery.index else None

        product = p["Product"] if p is not None else i["Product"] if i is not None else d["Product"]
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
            "Quantity Difference (Invoice - PO)": iq - pq if p is not None and i is not None else None,
            "Rate Difference (Invoice - PO)": ir - pr if p is not None and i is not None else None,
            "Total Difference (Invoice - PO)": inv_total - po_total if p is not None and i is not None else None,
            "Delivery Difference (Delivered - PO)": dq - pq if p is not None and d is not None else None,
            "Review Status": "; ".join(issues) if issues else "No discrepancy detected",
        })

    return pd.DataFrame(rows)


def money(value):
    if pd.isna(value):
        return "—"
    return f"₹{float(value):,.2f}"


def quantity(value):
    if pd.isna(value):
        return "—"
    return f"{float(value):,.2f}".rstrip("0").rstrip(".")


def build_pdf_report(results):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title="VerifyFlow AI Discrepancy Report",
        author="VerifyFlow AI",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="ReportTitle", parent=styles["Title"],
        alignment=TA_CENTER, fontSize=18, leading=22,
        textColor=colors.HexColor("#16324F"), spaceAfter=5,
    ))
    styles.add(ParagraphStyle(
        name="SmallCell", parent=styles["BodyText"],
        fontSize=7, leading=8, wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="SmallCellBold", parent=styles["SmallCell"],
        fontName="Helvetica-Bold",
    ))

    flagged = results[results["Review Status"] != "No discrepancy detected"]
    story = [
        Paragraph("VerifyFlow AI", styles["ReportTitle"]),
        Paragraph("Supplier Document Discrepancy Report", styles["Heading2"]),
        Paragraph(
            f"Products reviewed: {len(results)} &nbsp;&nbsp; Products flagged: {len(flagged)}",
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
    ]

    po_total = pd.to_numeric(results["PO Total"], errors="coerce").sum()
    invoice_total = pd.to_numeric(results["Invoice Total"], errors="coerce").sum()
    total_difference = invoice_total - po_total

    summary = Table([
        ["Purchase order total", "Invoice total", "Invoice difference"],
        [money(po_total), money(invoice_total), money(total_difference)],
    ], colWidths=[75 * mm, 75 * mm, 75 * mm])

    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([summary, Spacer(1, 6 * mm)])
    story.append(Paragraph("Product-by-product results", styles["Heading2"]))

    columns = [
        ("Product", "Product"),
        ("PO Quantity", "PO Qty"),
        ("Invoice Quantity", "Invoice Qty"),
        ("Delivered Quantity", "Delivered"),
        ("PO Unit Price", "PO Rate"),
        ("Invoice Unit Price", "Invoice Rate"),
        ("PO Total", "PO Total"),
        ("Invoice Total", "Invoice Total"),
        ("Review Status", "Review Status"),
    ]

    table_data = [[
        Paragraph(escape(label), styles["SmallCellBold"])
        for _, label in columns
    ]]

    for _, row in results.iterrows():
        cells = []
        for key, label in columns:
            value = row.get(key)
            if key == "Product":
                rendered = str(value)
            elif key in ("PO Unit Price", "Invoice Unit Price", "PO Total", "Invoice Total"):
                rendered = money(value)
            elif key in ("PO Quantity", "Invoice Quantity", "Delivered Quantity"):
                rendered = quantity(value)
            else:
                rendered = "—" if pd.isna(value) else str(value)
            cells.append(Paragraph(escape(rendered), styles["SmallCell"]))
        table_data.append(cells)

    available_width = landscape(A4)[0] - 24 * mm
    relative_widths = [1.6, 0.75, 0.85, 0.8, 0.8, 0.9, 0.85, 0.9, 2.2]
    total_weight = sum(relative_widths)
    widths = [available_width * w / total_weight for w in relative_widths]

    detail_table = Table(table_data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    detail_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#16324F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F3F6F9")
        ]),
    ]))
    story.extend([detail_table, Spacer(1, 5 * mm)])
    story.append(Paragraph("Flagged items", styles["Heading2"]))

    if flagged.empty:
        story.append(Paragraph("No discrepancies detected.", styles["BodyText"]))
    else:
        for _, row in flagged.iterrows():
            story.append(Paragraph(
                f"<b>{escape(str(row['Product']))}</b>: {escape(str(row['Review Status']))}",
                styles["BodyText"],
            ))
            story.append(Spacer(1, 2 * mm))

    story.extend([
        Spacer(1, 5 * mm),
        Paragraph(
            "Prototype report: verify extracted values against the original documents "
            "before making payment or inventory decisions.",
            styles["Italic"],
        ),
    ])

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


if "vf_data" not in st.session_state:
    st.session_state["vf_data"] = None
if "vf_report" not in st.session_state:
    st.session_state["vf_report"] = None

st.header("1. Upload documents")
po_file = st.file_uploader("Purchase Order PDF (required)", type=["pdf"], key="po_upload")
invoice_file = st.file_uploader("Supplier Invoice PDF (required)", type=["pdf"], key="invoice_upload")
delivery_file = st.file_uploader("Delivery Receipt PDF (optional)", type=["pdf"], key="delivery_upload")

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
                delivery_data = parse_product_lines(delivery_text, "delivery receipt")

            st.session_state["vf_data"] = {
                "po_text": po_text,
                "invoice_text": invoice_text,
                "delivery_text": delivery_text,
                "po_data": po_data,
                "invoice_data": invoice_data,
                "delivery_data": delivery_data,
            }
            st.session_state["vf_report"] = None
            st.success("PDFs extracted successfully. Review the tables below.")
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
    st.caption("Correct extraction errors before generating the report.")

    po_edit = st.data_editor(
        data["po_data"], num_rows="dynamic",
        use_container_width=True, key="po_editor"
    )
    invoice_edit = st.data_editor(
        data["invoice_data"], num_rows="dynamic",
        use_container_width=True, key="invoice_editor"
    )

    delivery_edit = None
    if data["delivery_data"] is not None:
        st.markdown("**Delivery receipt data**")
        delivery_edit = st.data_editor(
            data["delivery_data"], num_rows="dynamic",
            use_container_width=True, key="delivery_editor"
        )

    if st.button("Generate discrepancy report", type="primary"):
        try:
            st.session_state["vf_report"] = compare_documents(
                po_edit, invoice_edit, delivery_edit
            )
        except Exception as exc:
            st.session_state["vf_report"] = None
            st.error(f"Could not generate report: {exc}")

results = st.session_state["vf_report"]

if results is not None:
    st.header("3. Discrepancy report")
    flagged = results[results["Review Status"] != "No discrepancy detected"]

    col1, col2 = st.columns(2)
    col1.metric("Products reviewed", len(results))
    col2.metric("Products flagged", len(flagged))
    st.dataframe(results, use_container_width=True, hide_index=True)

    st.download_button(
        "Download discrepancy report (CSV)",
        data=results.to_csv(index=False).encode("utf-8"),
        file_name="verifyflow_discrepancy_report.csv",
        mime="text/csv",
        key="download_csv",
    )

    try:
        pdf_bytes = build_pdf_report(results)
        st.download_button(
            "Download discrepancy report (PDF)",
            data=pdf_bytes,
            file_name="verifyflow_discrepancy_report.pdf",
            mime="application/pdf",
            key="download_pdf",
        )
    except Exception as exc:
        st.error(f"Could not create PDF report: {exc}")

    if flagged.empty:
        st.success("No discrepancies detected.")
    else:
        st.warning("Discrepancies found. Review flagged rows before taking action.")

st.divider()
st.caption("VerifyFlow AI prototype | Text-based PDF extraction with pypdf | Scanned PDF OCR is not included.")
