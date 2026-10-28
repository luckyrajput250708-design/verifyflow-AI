# VerifyFlow AI — One-Page Problem Statement

## Project title
**VerifyFlow AI: AI-assisted checking of supplier documents for small distributors**

## Background
Small distributors and wholesalers routinely work with purchase orders, supplier invoices, and delivery receipts. These documents may arrive as PDFs, scans, photographs, spreadsheets, or emails. To confirm that an invoice matches what was ordered and delivered, an employee may need to open multiple files and compare supplier details, product descriptions, quantities, unit prices, and totals.

## Problem
Manual document comparison can be repetitive and difficult to scale. Product names may be written differently across documents, fields may be missing or hard to read, and discrepancies can be overlooked when staff are busy. Existing accounting or enterprise systems may already solve parts of this workflow, but some smaller businesses may find their current process fragmented, manual, or more complex than needed. This is a hypothesis to validate with customer interviews, not an assumption that all businesses have the same problem.

## Target users
The initial target segment is small auto-parts distributors and wholesalers that process supplier invoices and purchase orders without a fully automated document-matching workflow. The first research phase will interview 10–15 potential users to understand document volume, current tools, common mistakes, time spent, and willingness to test a lightweight solution.

## Proposed solution
VerifyFlow AI will be a document discrepancy assistant. The first version will accept structured sample data, compare expected and billed quantities and prices, and flag possible mismatches with a clear explanation. Later versions may extract fields from PDFs and scanned documents using OCR, match inconsistent item descriptions, and compare purchase orders, invoices, and delivery receipts. A human user will review every flag before acting.

## Project goals
1. Reduce the time needed to identify differences across supplier documents.
2. Make potential discrepancies easier to understand by showing the relevant values and source evidence.
3. Measure extraction quality, mismatch precision/recall, false alarms, and time saved against a manual baseline.
4. Determine whether a clearly defined group of businesses has enough need to adopt or pay for the tool.

## Scope and limitations
The MVP will not approve payments, make final fraud accusations, or replace accounting advice. OCR and AI outputs can be wrong, so the product must display uncertainty and support human review. Development will begin with synthetic or explicitly approved sample documents. Confidential business data will not be committed to the public repository.

## Success criteria
The initial prototype is successful if it can compare a test set of sample documents, flag defined quantity/price/total mismatches, explain why each item was flagged, and pass automated tests for common edge cases. Business validation will require feedback from target users and, ideally, a real pilot. The project will not claim savings or accuracy figures until they have been measured.

## Initial 90-day outcome
Deliver a working prototype, a documented test dataset, a technical evaluation, customer interview findings, and a decision to continue, narrow, or pivot based on evidence.
