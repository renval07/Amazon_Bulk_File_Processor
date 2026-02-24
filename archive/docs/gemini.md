# Amazon PPC Bulk Optimizer: Project Plan

## Project Overview
A reusable Python-based tool designed to automate Amazon PPC optimizations using bulk files (.xlsx). The goal is to move from static, arbitrary rules to dynamic, statistical optimizations.

---

## 1. Technical Architecture
- **Language:** Python 3.x
- **UI Framework:** Streamlit (Local Web App)
- **Data Processing:** Pandas
- **Excel Handling:** Openpyxl / XlsxWriter
- **AI/Semantics:** Scikit-learn (TF-IDF) & Sentence-Transformers (Future Phase)

---

## 2. Optimization Logic (The "Brain")

### A. Advanced Bid Optimization (Revenue-Based)
Instead of basic ACOS targeting, we use the **Revenue Per Click (RPC)** method for stability and proactive scaling.
- **Formula:** `New Bid = (Total Sales / Total Clicks) * Target ACOS`
- **Safety Rails:**
    - **Max Change %:** Bids won't shift more than 20% in a single run.
    - **Min Data Threshold:** No optimization until a keyword has >10 clicks.
    - **Floor/Ceiling:** Hard limits on min ($0.10) and max ($5.00) bids.

### B. Dynamic Bleeder Control (Statistical Z-Scores)
Bleeders are identified relative to the account's current performance, automatically adjusting for seasonality.
- **Method:** Calculate Z-Scores for CTR and Clicks-per-Sale.
- **Categorization:**
    1.  **Type A: Irrelevant (Low CTR)**
        - *Logic:* `Impressions > 1000` AND `Z_CTR < -1.5`.
        - *Action:* Aggressive bid reduction (Stop "Impression Bloat").
    2.  **Type B: Click-Happy (Wasteful Spend)**
        - *Logic:* `Clicks > (Account Mean + 2*StdDev)` AND `Sales == 0`.
        - *Action:* Lower bid to "scouting" level ($0.10) or tag for negation.
    3.  **Type C: Ghost Keywords (Low Volume)**
        - *Logic:* `Impressions < 100`.
        - *Action:* Move to a "Test More" report; no automatic bid reduction.

---

## 3. Data Integrity Factors
- **The 48-Hour Rule:** To account for Amazon's attribution lag, the most recent 48 hours of data from the bulk file will be excluded from optimization calculations.
- **Data Cleaning:** Handle currency symbols, "Infinity" ACOS (0 sales), and empty cells across different bulk file versions.

---

## 4. Implementation Roadmap

### Phase 1: Foundation & Core Ops (MVP)
- Streamlit UI for file upload.
- Implementation of RPC Bid Logic.
- Implementation of Z-Score Bleeder Logic.
- Export of valid Amazon Bulk File format.

### Phase 2: Structural Control
- **Cannibalization Check:** Detect duplicate targets across ad groups.
- **Budget Optimization:** Reallocate funds to high-ROAS campaigns.

### Phase 3: Semantic Intelligence
- Cluster search terms by "Intent" using NLP.
- Recommend new negative keywords based on semantic irrelevance.

---

## 5. Do's and Don'ts

### **Do's**
- **Preserve IDs:** Always keep the `Record ID`, `Campaign ID`, and `Keyword ID` columns intact. Amazon uses these to identify which rows to update.
- **The 48-Hour Rule:** Always exclude the last 2 days of data. Decisions based on incomplete attribution are the #1 cause of bad bid changes.
- **Incremental Changes:** Limit bid changes to +/- 20% per cycle. Rapid jumps confuse the Amazon algorithm and can kill campaign momentum.
- **Modular Logic:** Keep the optimization math (`optimizer.py`) separate from the interface (`app.py`). This allows for easier testing and future CLI support.
- **Validate Before Export:** Check that the "Optimized" file has the exact same headers and sheet names as the original.

### **Don'ts**
- **Don't Optimize on Low Data:** Never lower a bid just because it has 3 clicks and 0 sales. Wait for statistical significance (Z-Score > 2.0).
- **Don't Overwrite Original Files:** Always export a new file (e.g., `bulk_optimized_TIMESTAMP.xlsx`) to maintain a history and backup.
- **Don't Hardcode Thresholds:** Avoid using static numbers like "10 clicks = bleeder." Use the account-wide mean and standard deviation.
- **Don't Change Column Headers:** Amazon's bulk upload tool will fail if a single header name is modified or misspelled.

---

## 6. Needed Tools & Libraries

### **Core Stack**
- **Python 3.10+**: The base programming language.
- **Pandas**: For heavy data manipulation and statistical calculations.
- **Streamlit**: To build the interactive dashboard and file upload UI.
- **Openpyxl**: Engine used by Pandas to read/write `.xlsx` files.
- **XlsxWriter**: Used for advanced formatting in the output Excel file.

### **Development Tools**
- **VS Code / Cursor**: Recommended IDE for coding.
- **Excel / Google Sheets**: To manually verify the output before uploading to Amazon.
- **Virtual Environment (venv)**: To keep project dependencies isolated.
