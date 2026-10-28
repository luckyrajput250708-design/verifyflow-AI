import streamlit as st
import pandas as pd

st.set_page_config(page_title="VerifyFlow AI", page_icon="🔎", layout="wide")

st.title("🔎 VerifyFlow AI")
st.caption("Prototype: compare purchase-order lines with invoice lines and flag possible discrepancies.")

st.warning(
    "Demo only. Use synthetic data. Flags are not proof of wrongdoing; "
    "a person must verify documents before taking action."
)

purchase_order = pd.DataFrame([
    {"item": "Bearing A", "quantity": 100, "unit_price": 500.00},
    {"item": "Bolt B", "quantity": 50, "unit_price": 12.00},
])
invoice = pd.DataFrame([
    {"item": "Bearing A", "quantity": 110, "unit_price": 500.00},
    {"item": "Bolt B", "quantity": 50, "unit_price": 12.00},
])

left, right = st.columns(2)
with left:
    st.subheader("Purchase order (expected)")
    st.dataframe(purchase_order, use_container_width=True)
with right:
    st.subheader("Supplier invoice (billed)")
    st.dataframe(invoice, use_container_width=True)

po = purchase_order.copy()
inv = invoice.copy()
po["item_key"] = po["item"].str.strip().str.casefold()
inv["item_key"] = inv["item"].str.strip().str.casefold()

merged = po.merge(inv, on="item_key", how="outer", suffixes=("_po", "_invoice"), indicator=True)
merged["item_display"] = merged["item_po"].fillna(merged["item_invoice"])
merged["quantity_difference"] = merged["quantity_invoice"].fillna(0) - merged["quantity_po"].fillna(0)
merged["unit_price_difference"] = merged["unit_price_invoice"].fillna(0) - merged["unit_price_po"].fillna(0)
merged["po_line_total"] = merged["quantity_po"].fillna(0) * merged["unit_price_po"].fillna(0)
merged["invoice_line_total"] = merged["quantity_invoice"].fillna(0) * merged["unit_price_invoice"].fillna(0)
merged["potential_total_difference"] = merged["invoice_line_total"] - merged["po_line_total"]

def explain(row):
    reasons = []
    if row["_merge"] == "left_only":
        reasons.append("Missing from invoice")
    elif row["_merge"] == "right_only":
        reasons.append("Not found in purchase order")
    else:
        if row["quantity_difference"] != 0:
            reasons.append("Quantity differs")
        if abs(row["unit_price_difference"]) > 0.005:
            reasons.append("Unit price differs")
        if abs(row["potential_total_difference"]) > 0.01:
            reasons.append("Line total differs")
    return ", ".join(reasons) if reasons else "No discrepancy found by basic rules"

merged["status"] = merged.apply(explain, axis=1)
results = merged[[
    "item_display", "quantity_po", "quantity_invoice", "unit_price_po",
    "unit_price_invoice", "potential_total_difference", "status"
]].rename(columns={
    "item_display": "Item",
    "quantity_po": "PO quantity",
    "quantity_invoice": "Invoice quantity",
    "unit_price_po": "PO unit price",
    "unit_price_invoice": "Invoice unit price",
    "potential_total_difference": "Potential line-total difference (₹)",
    "status": "Review status",
})

st.subheader("Comparison results")
st.dataframe(results, use_container_width=True, hide_index=True)
st.download_button(
    "Download review report (CSV)",
    data=results.to_csv(index=False).encode("utf-8"),
    file_name="verifyflow_review_report.csv",
    mime="text/csv",
)
st.info("Next step: replace the built-in synthetic examples with validated input handling and automated tests.")
