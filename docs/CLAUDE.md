# Amazon PPC Bulk Optimizer - Claude Instructions

## Project Overview

This is a Python-based tool for automating Amazon PPC (Pay-Per-Click) bid optimizations using bulk files (.xlsx). The tool moves from static, arbitrary rules to dynamic, statistical optimizations based on Revenue-Per-Click (RPC) and Z-Score analysis.

**Key Goal**: Prevent bad bid changes by using statistical methods and enforcing the 48-hour attribution rule.

---

## Project Structure

```
Bulk File/
├── src/
│   ├── app.py                 # Streamlit UI (user interface)
│   ├── optimizer.py           # Core optimization logic (the "brain")
│   └── __init__.py
├── gemini.md                  # Original project specification
├── BUGFIXES.md               # Documentation of critical bug fixes
├── requirements.txt           # Python dependencies
├── test_fixes.py             # Automated test suite
└── bulk-*.xlsx               # Sample Amazon bulk files
```

---

## Technical Stack

- **Language**: Python 3.10+
- **UI Framework**: Streamlit (local web app)
- **Data Processing**: Pandas + NumPy
- **Excel Handling**: Openpyxl / XlsxWriter
- **Statistics**: SciPy (for Z-scores)
- **NLP/AI**: sentence-transformers, scikit-learn (Phase 3)

---

## Core Optimization Logic

### 1. Revenue-Per-Click (RPC) Bid Optimization

**Formula**: `New Bid = (Total Sales / Total Clicks) * Target ACOS`

**Safety Rails**:
- **Max Change**: Bids won't shift more than ±20% in a single run
- **Min Data Threshold**: No optimization until keyword has >10 clicks
- **Floor/Ceiling**: Hard limits on min ($0.10) and max ($5.00) bids
- **Fallback Logic**: If `Bid` is 0, uses `Ad Group Default Bid`

### 2. Dynamic Bleeder Detection (Z-Score Analysis)

Identifies underperforming keywords relative to account-wide statistics:

- **Type A: Irrelevant (Low CTR)**
  - Logic: `Impressions > 1000` AND `Z_CTR < -1.5`
  - Action: Reduce to min bid

- **Type B: Click-Happy (Wasteful Spend)**
  - Logic: `Clicks > (Mean + 2*StdDev)` AND `Sales == 0`
  - Action: Reduce to scouting level ($0.10)

- **Type C: Ghost Keywords** ✅ IMPLEMENTED
  - Logic: `Impressions < 100`
  - Action: Flag for "Test More" report (no bid change)

### 3. Product Target Analysis (Phase 3 - Statistical Framework)

Analyzes ASIN (product targeting) performance using research-backed thresholds:

- **Type A: Low CTR (Impression Bloaters)**
  - Logic: `Impressions > 500` AND `Z_CTR < -1.5` AND `Clicks < 5`
  - Action: Reduce bid 20-30%

- **Type B: Non-Converting (Click Wasters)** ⚠️ PRIORITY
  - Logic: `(Clicks ≥ 20 AND Sales = 0)` OR `(Clicks ≥ 10 AND CVR < 2%)`
  - Action: Add to negative product targeting (auto-generated file)

- **Type C: High ACOS (Underperformers)**
  - Logic: `(ACOS > 80% AND Impressions > 100)` OR `(ROAS < 0.5 AND Clicks > 10)`
  - Action: Reduce bid or add to negatives

- **Type D: Insufficient Data (Ghost ASINs)**
  - Logic: `Impressions < 100`
  - Action: Flag for testing (no changes)

**Key Differences from Keywords:**
- Product targeting has lower CTR (0.1-0.3% vs 0.4-0.5% for keywords)
- Higher conversion rates (12-15% vs 8-10%)
- Fewer clicks needed for decisions (10-20 vs 20-30)

### 4. Search Term Intent Clustering (Phase 3 - NLP)

Uses machine learning to group search terms by customer intent:

- **Technology**: sentence-transformers (all-MiniLM-L6-v2 model)
- **Method**: Generate embeddings → K-means clustering → Performance analysis
- **Output**:
  - Intent clusters with representative terms
  - Performance category (High/Average/Low Performing)
  - Negative keyword recommendations (auto-generated file)

**Example:**
```
Cluster 1: "dress up clothes", "princess dress" → ROAS 4.2x (High-Performing)
Cluster 2: "cheap dress", "dollar dress" → ROAS 0.3x (Low-Performing)
```

### 5. Negative Recommendation Exports (Phase 3 - Amazon-Ready)

Automatically generates Amazon bulk upload files:

- **Negative Product Targets** (`negative_product_targets_XXXXX.xlsx`)
  - Format: `Product | Entity | Operation | Campaign ID | Product Targeting Expression | Match Type`
  - Upload directly to Amazon Seller Central to block wasteful ASINs

- **Negative Keywords** (`negative_keywords_XXXXX.xlsx`)
  - Format: `Product | Entity | Operation | Campaign Name | Keyword Text | Match Type`
  - Upload directly to Amazon Seller Central to block wasteful search terms

---

## Critical Rules & Constraints

### ⚠️ THE 48-HOUR RULE (ENFORCED)
**The #1 cause of bad bid changes**

Amazon attribution can take up to 48 hours. Files with data ending within the last 48 hours may have incomplete sales attribution, leading to incorrect optimization decisions.

**Implementation**:
- Tool parses end date from filename (e.g., `bulk-...-20260211-...`)
- If end date is within 48 hours of today, tool blocks optimization by default
- User can override via "Safety Settings" checkbox (not recommended)

### 📋 Data Integrity Requirements

1. **Preserve IDs**: Never modify `Record ID`, `Campaign ID`, `Keyword ID` columns
2. **Column Headers**: Must match Amazon's exact format (case-sensitive)
3. **Sheet Names**: Must preserve all original sheet names
4. **Incremental Changes**: Limit bid changes to ±20% per cycle
5. **No Low-Data Optimization**: Don't optimize keywords with <10 clicks

### 🚫 Never Do This

- ❌ Overwrite original files (always export with new name)
- ❌ Optimize on low data (<10 clicks)
- ❌ Change column headers or sheet names
- ❌ Hardcode thresholds (use statistics or configuration)
- ❌ Ignore the 48-hour rule

---

## File Format & Data Structure

### Amazon Bulk File Format

- **Format**: Multi-sheet Excel (.xlsx)
- **Key Sheet**: `Sponsored Products Campaigns`
- **Required Columns**:
  - `Entity` (must be "Keyword" or "Product Targeting" for optimization)
  - `Impressions`, `Clicks`, `Spend`, `Sales`
  - `Bid`, `Ad Group Default Bid`
  - `Operation` (for marking updates)

### Data Cleaning

The tool handles:
- Currency symbols (e.g., "$100.50" → 100.50)
- Infinity ACOS (when Sales = 0)
- Empty/null cells
- Object dtype conversion

---

## How to Run

### Start the Streamlit App
```bash
cd "C:\Users\genek\OneDrive\Desktop\AI Projects\CLI\Bulk File"
streamlit run src/app.py
```

### Run Tests
```bash
python test_fixes.py
```

### Basic Usage
1. Open Streamlit app in browser (auto-opens at http://localhost:8501)
2. Configure settings in sidebar:
   - Target ACOS (default: 30%)
   - Min/Max Bid
   - Safety Settings (48-hour rule)
3. Upload Amazon bulk file (.xlsx)
4. Click "Run Optimization"
5. Download optimized file
6. Upload to Amazon Seller Central

---

## Configuration Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `target_acos` | 0.30 | 0.05-1.00 | Target Advertising Cost of Sale (30% = 0.30) |
| `min_bid` | $0.10 | $0.01-$5.00 | Minimum allowed bid |
| `max_bid` | $5.00 | $0.10-$10.00 | Maximum allowed bid |
| `enforce_48hr_rule` | True | True/False | Block files with data <48 hours old |

### Hardcoded Thresholds (Future: Make Configurable)

- **Min clicks for optimization**: 10
- **Type A bleeder threshold**: 1000 impressions, Z_CTR < -1.5
- **Type B bleeder threshold**: Clicks > Mean + 2*StdDev, 0 sales
- **Max bid change per cycle**: ±20%

---

## Development Guidelines

### Code Style

1. **Modular Architecture**: Keep UI (`app.py`) separate from logic (`optimizer.py`)
2. **Vectorization**: Use NumPy operations over pandas loops where possible
3. **Error Handling**: Provide clear, actionable error messages
4. **Validation**: Validate inputs before processing
5. **Documentation**: Use docstrings for all public methods

### Testing

- Always run `test_fixes.py` after making changes
- Test with real bulk files (check for edge cases)
- Verify output file opens in Excel and uploads to Amazon
- Check for pandas/numpy warnings

### Adding New Features

1. Update `optimizer.py` for logic changes
2. Update `app.py` for UI changes
3. Add tests to `test_fixes.py`
4. Update this CLAUDE.md file
5. Document in BUGFIXES.md or create CHANGELOG.md

---

## Known Issues & Limitations

### Current Limitations

1. **No per-row timestamps**: Can only check file-level date (from filename)
2. **Type C bleeders not implemented**: Ghost Keywords (low impressions) not yet handled
3. **No logging**: No audit trail of what changed and why
4. **No undo**: Once optimized, need to re-upload original file to revert
5. **Single-file processing**: Can't batch process multiple files

### Future Enhancements (Spec Phases 2-3)

- **Phase 2**: Cannibalization detection, budget optimization
- **Phase 3**: Semantic NLP clustering, negative keyword recommendations
- **Export timestamps**: Add timestamp to output filename
- **Progress indicators**: Show real-time progress for large files
- **Configuration file**: YAML/JSON for advanced settings

---

## Common Issues & Troubleshooting

### "Missing required columns" Error
- Ensure bulk file is from Amazon Seller Central (not manually created)
- Check that "Sponsored Products Campaigns" sheet exists
- Verify columns: Entity, Impressions, Clicks, Spend, Sales, Bid

### "CRITICAL: File within 48 hours" Error
- File data is too recent (incomplete attribution)
- **Fix 1**: Wait 48 hours and download a new bulk file
- **Fix 2**: Download a bulk file with an earlier date range
- **Fix 3**: Disable "Enforce 48-Hour Rule" (NOT RECOMMENDED)

### No Bid Changes Made
- Check if keywords have >10 clicks (threshold for optimization)
- Verify target ACOS is realistic (not already at current performance)
- Check min/max bid limits aren't too restrictive

### Output File Won't Upload to Amazon
- Verify all sheet names preserved
- Check column headers unchanged
- Ensure no manual edits to IDs (Record ID, Campaign ID, Keyword ID)

---

## Important Context for AI Assistants

When working on this project:

1. **Always preserve data integrity**: This tool modifies financial advertising data. Bugs can cost money.

2. **The 48-hour rule is sacred**: Per the spec, this is "the #1 cause of bad bid changes." Never remove or weaken this check without explicit user request.

3. **Test before committing**: Run `test_fixes.py` after any changes to optimizer.py

4. **Understand the math**:
   - RPC = Revenue per click stabilizes volatile ACOS
   - Z-scores detect relative underperformance (not absolute thresholds)
   - 20% max change prevents algorithm shock

5. **Excel compatibility**: Always test that output files open correctly in Excel/LibreOffice

6. **Windows paths**: This project uses Windows paths with backslashes. Use raw strings (r'path\to\file').

---

## Quick Reference

### Key Files

- **src/optimizer.py:54-94** - RPC bid optimization logic
- **src/optimizer.py:96-162** - Bleeder detection logic
- **src/optimizer.py:16-48** - Data loading and validation
- **src/app.py:39-64** - Main optimization workflow

### Key Variables

- `self.df` - Main working DataFrame (Sponsored Products Campaigns sheet)
- `self.original_sheets` - Dictionary of all sheets (for preservation)
- `mask` - Boolean filter for Keywords and Product Targeting entities
- `current_bid` - Bid with fallback to Ad Group Default Bid

### Key Methods

- `load_data()` - Loads file, validates columns, cleans data
- `check_48_hour_rule()` - Validates file date (blocks if too recent)
- `optimize_bids()` - Applies RPC optimization with safety rails
- `identify_bleeders()` - Detects and reduces underperforming keywords
- `save_optimized_file()` - Exports all sheets to Excel

---

## Version History

- **2026-02-11 (v4.0)**: Phase 3 - NLP Intelligence
  - Product target analysis with statistical framework (Z-scores)
  - NLP-powered search term intent clustering (sentence-transformers)
  - Negative product target recommendations (Amazon-ready export)
  - Negative keyword recommendations (Amazon-ready export)
  - 5 download options (added 2 new negative recommendation files)
  - Enhanced UI with Phase 3 metrics and expandable reports
  - Comprehensive test suite (7 Phase 3 tests)
  - Research-backed thresholds for product targeting

- **2026-02-11 (v3.1)**: Amazon Upload Fix
  - Fixed Operation column cleaning (no more 'nan' strings)
  - Separate Amazon upload file (only compatible sheets)
  - Markdown report generation
  - Three-file output system

- **2026-02-11 (v3.0)**: Phase 2 - Structural Control
  - Cannibalization detection across ad groups
  - Budget optimization recommendations (ROAS-based)
  - Operation column set to 'Update' for bid changes
  - Enhanced reporting with structural analysis

- **2026-02-11 (v2.0)**: Priority 2 Features
  - Implemented Type C bleeder detection (Ghost Keywords)
  - Added Test More Report generation
  - Comprehensive logging system with audit trail
  - Output file validation before export
  - Automatic timestamp in filenames
  - Progress indicators in Streamlit UI
  - Enhanced metrics display with bleeder breakdown

- **2026-02-11 (v1.0)**: Critical bug fixes
  - Fixed bid fallback logic bug
  - Implemented 48-hour rule enforcement
  - Added input validation and data cleaning
  - Fixed pandas dtype warnings
  - Added automated test suite

---

## Contact & Support

For issues, refer to:
1. **gemini.md** - Original project specification
2. **BUGFIXES.md** - Documentation of critical fixes
3. **test_fixes.py** - Test suite for verification

---

*Last Updated: 2026-02-11*
