# Amazon PPC Bulk Optimizer

A Python-based tool for automating Amazon PPC bid optimizations using **statistical methods** and **NLP-powered semantic intelligence** instead of arbitrary rules.

## Features

### Core Optimization (Phase 1-2)
- **Revenue-Per-Click (RPC) Optimization**: More stable than ACOS-only targeting
- **Statistical Bleeder Detection**: Identifies underperforming keywords using Z-scores (Types A, B, C)
- **48-Hour Freshness Advisory**: Warns when filename date range is within 48 hours
- **Safety Rails**: ±20% max bid changes, min/max bid limits, minimum data thresholds
- **Cannibalization Detection**: Finds duplicate keywords across ad groups
- **Budget Optimization**: ROAS-based budget recommendations

### Advanced Features (Phase 3 - NLP Intelligence) 🆕
- **Product Target Analysis**: Statistical framework for ASIN performance (4 bleeder types)
- **Search Term Intent Clustering**: NLP-powered customer intent analysis using sentence-transformers
- **Negative Product Targets Export**: Auto-generated Amazon-ready file to block wasteful ASINs
- **Negative Keywords Export**: Auto-generated Amazon-ready file to block wasteful search terms
- **Estimated Savings Calculator**: Know your ROI before implementing

### User Experience
- **Comprehensive Logging**: Full audit trail of all optimization decisions
- **Progress Indicators**: Real-time feedback during processing
- **Performance Metrics**: Per-stage runtime timings for troubleshooting and tuning
- **Output Validation**: Ensures file integrity before download
- **6 Download Options**: Bid changes, analysis report, full data, 2 negative recommendation files, and optimization log
- **User-Friendly UI**: Streamlit web interface with detailed metrics and expandable reports

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt

# Optional (development/testing tooling)
pip install -r requirements-dev.txt
```

### 2. Run the App

```bash
streamlit run streamlit_app.py
```

### 3. Use the Tool

1. Configure settings in the sidebar (Target ACOS, min/max bids)
2. Upload your Amazon bulk file (.xlsx)
3. Click "Run Optimization"
4. Download the optimized file
5. Upload to Amazon Seller Central

## Environment Profiles

Runtime profiles are supported for `local`, `dev`, and `prod`.

- Default profile: `local`
- Override with env var: `APP_ENV=dev` (or `prod`)
- CLI override: `--env local|dev|prod`

Profile files are in `config/profiles/`.
- `prod` profile defaults NLP analysis to off for Streamlit Cloud stability.

## CLI Mode

You can run the optimizer from terminal without Streamlit.

### Basic Commands

```bash
# Single file mode
python -m src.cli --input "path/to/bulk-file.xlsx"

# Batch mode (all matching files in a folder)
python -m src.cli --input-dir "data/samples" --pattern "*.xlsx"

# Run under a specific profile
python -m src.cli --env dev --input "path/to/bulk-file.xlsx"
```

### Common Commands

```bash
# Set optimization controls
python -m src.cli --input "bulk.xlsx" --target-acos 0.30 --min-bid 0.10 --max-bid 5.00

# Write outputs to a custom folder
python -m src.cli --input "bulk.xlsx" --output-dir "outputs/run_01"

# Hide 48-hour advisory warning output (legacy compatibility flag)
python -m src.cli --input "bulk.xlsx" --disable-48hr-rule

# Skip NLP phase for faster runs
python -m src.cli --input "bulk.xlsx" --skip-nlp

# Batch mode with recursive search and fail-fast behavior
python -m src.cli --input-dir "data/samples" --pattern "*bulk*.xlsx" --recursive --fail-fast

# Tune NLP clustering and negative keyword thresholds
python -m src.cli --input "bulk.xlsx" --n-clusters 8 --min-cluster-size 10 --negative-keyword-min-spend 15 --negative-keyword-max-acos 1.2

# Configure low-volume handling and cold-start step-up
python -m src.cli --input "bulk.xlsx" --bleeder-type-c-mode percentile --bleeder-type-c-percentile 0.20 --cold-start-step-up 0.02

# Show all available options
python -m src.cli --help
```

### CLI Outputs

By default, CLI writes per-file outputs into `outputs/`:
- Amazon upload-ready Excel
- Full analysis Excel
- Markdown optimization report
- Optimization log (`.txt`)
- Negative product targets Excel (unless `--skip-nlp`)
- Negative keywords Excel (unless `--skip-nlp`)
- Batch summary CSV (only when using `--input-dir`)
- Persistent run history CSV (`outputs/run_history.csv`) for UI/CLI comparison tracking

CLI also prints per-stage runtime timings at the end of each run.

The Streamlit UI includes a **Historical Run Tracking** panel to compare the latest successful run against the previous one.
Basic drift alerts are also shown when key metrics deviate materially from recent successful runs.

## Docker Deployment

```bash
# Build and run with default (prod) profile
docker compose up --build

# Run with a specific profile
APP_ENV=dev docker compose up --build
```

Use `env/*.env.example` as templates for environment files.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| **Target ACOS** | 30% | Your target Advertising Cost of Sale |
| **Min Bid** | $0.02 | Minimum bid floor |
| **Max Bid** | $5.00 | Maximum bid ceiling |
| **48-Hour Freshness Check** | Advisory | Warns for likely incomplete attribution windows |

### Advanced Thresholds (Sidebar)

| Setting | Default | Description |
|---------|---------|-------------|
| **Min Clicks for Optimization** | 10 | Minimum clicks required before RPC bid updates are applied |
| **Max Bid Change per Run** | 20% | Caps bid movement up/down in one run |
| **Low Engagement Min Impressions** | 1000 | Minimum impressions before low-CTR detection applies |
| **Low Engagement Z-Score Threshold** | -1.5 | Cutoff for low-CTR outlier detection |
| **High-Cost Non-Converter StdDev Multiplier** | 2.0 | Controls strictness of click-heavy zero-sale detection |
| **Low Visibility Mode** | fixed | `fixed`, `percentile`, or `zscore` low-volume detection |
| **Low Visibility Max Impressions** | 100 | Used when mode = `fixed` |
| **Cold-Start Step-Up** | $0.02 | Bid increase for low-volume zero-click terms |

## How It Works

### RPC Bid Optimization

Instead of reacting to ACOS volatility, the tool uses:

```
New Bid = (Total Sales / Total Clicks) × Target ACOS
```

With safety constraints:
- Maximum ±20% change per run
- Only optimizes keywords with >10 clicks
- Respects min/max bid limits

### Bleeder Detection

Uses Z-score analysis to identify:

**For Keywords:**
- **Low Engagement**: Low CTR outliers with sufficient impressions → Reduce bid
- **High-Cost Non-Converter**: High clicks + zero sales → Reduce to scouting level
- **Low Visibility**: Low-volume terms → Flag for "Test More" report
- **Cold-Start Step-Up**: Low-visibility terms with zero clicks/sales → increase bid by configured amount (default $0.02)

**For Product Targets (ASINs):** 🆕
- **Type A**: Low CTR (Z-score < -1.5) → Reduce bid
- **Type B**: Non-converting (Clicks ≥ 20, Sales = 0) → Add to negative targeting ⚠️ PRIORITY
- **Type C**: High ACOS (> 80%) → Reduce bid or negate
- **Type D**: Insufficient data (< 100 impressions) → Flag for testing

### NLP Intent Clustering 🆕

Uses machine learning to group search terms by customer intent:

```
Example Results:
Cluster 1: "dress up clothes", "princess costume" → ROAS 4.2x ✅ Scale
Cluster 2: "cheap dress", "dollar dress" → ROAS 0.3x ❌ Negate
```

**Technology**: sentence-transformers (384-dimensional embeddings) + K-means clustering

### Amazon-Ready Negative Files 🆕

Automatically generates two Excel files formatted for direct Amazon upload:

1. **Negative Product Targets** - Block wasteful ASINs
2. **Negative Keywords** - Block wasteful search terms

No manual formatting needed - just download and upload to Seller Central!

## Important: The 48-Hour Rule

⚠️ **Amazon attribution can take up to 48 hours.** Optimizing on recent data is the #1 cause of bad bid changes.

The tool:
- Checks your bulk file's end date (from filename)
- Warns if data appears <48 hours old
- Continues processing (advisory-only behavior)

**Best Practice**: Wait 48 hours after your data period ends before downloading the bulk file.

## Requirements

- Python 3.10 or higher
- Windows, macOS, or Linux
- Amazon Seller Central bulk file (.xlsx)

## Troubleshooting

### "Missing required columns" Error

Your bulk file must include: Entity, Impressions, Clicks, Spend, Sales, Bid

**Fix**: Download a fresh bulk file from Amazon Seller Central

### "File within 48 hours" Warning

Your file data is too recent (incomplete sales attribution).

**Best-practice options**:
1. Wait 48 hours and download a new bulk file
2. Download a file with an earlier date range
3. Continue anyway if you intentionally accept attribution lag

### No Bid Changes Made

Possible reasons:
- Keywords have <10 clicks (need more data)
- Current bids already align with target ACOS
- Min/max bid limits are too restrictive

### NLP clustering shows 0 clusters

Possible reasons:
- Model download is blocked in your environment
- Not enough valid search-term rows

Fix options:
1. Enable internet/model cache for `sentence-transformers`
2. Disable NLP for the run (sidebar `Run NLP Analysis` or CLI `--skip-nlp`)

## Streamlit Cloud Deployment

This repo is ready for Streamlit Cloud:

1. Push to GitHub.
2. In Streamlit Cloud, set:
   - Repository: this project
   - Branch: `main`
   - Main file path: `streamlit_app.py`
3. Ensure `runtime.txt` is present (Python pin for deterministic cloud runtime).
4. Set `APP_ENV=prod` (recommended) to use production defaults.
5. Deploy.

Notes:
- In `prod`, `Run NLP Analysis` defaults to OFF to keep cloud runs lighter and more reliable.
- Enable NLP per run only when you need clustering/negative recommendation intelligence.
- First NLP-enabled run may take longer while model files are downloaded.

## Project Structure

```
src/
├── app.py          # Streamlit UI
├── cli.py          # Command-line interface
├── optimizer.py    # Optimization logic
├── run_history.py  # Historical tracking + drift checks
└── settings.py     # Runtime profile loader
config/
└── profiles/       # local/dev/prod runtime profiles
env/                # Environment file templates
Dockerfile          # Container runtime definition
docker-compose.yml  # Container orchestration
tests/              # Pytest suite (active)
data/
└── samples/        # Local sample input files (gitignored by default)
docs/
├── CLAUDE.md       # Developer instructions
└── gemini.md       # Original project specification (historical reference)

ROADMAP.md          # Authoritative roadmap (single source of truth)
SUMMARY.md          # Working technical summary
CHANGELOG.md        # Change history
RELEASE_CHECKLIST.md # First GitHub release checklist
README.md           # User guide
CONTRIBUTING.md     # Contribution workflow
LICENSE             # MIT license
archive/docs/       # Archived status/phase documentation
archive/tests_legacy/ # Archived script-style test runners
requirements.txt    # Python dependencies
```

## Testing

Run the automated test suites:

```bash
# Active automated suite
python -m pytest tests/
```

Legacy script-style test runners were archived to `archive/tests_legacy/` for reference.

All tests should pass before using the tool on production data.

## Safety Features

✅ **Data Validation**: Checks for required columns before processing
✅ **Input Validation**: Rejects invalid configurations
✅ **48-Hour Advisory**: Warns on potentially incomplete data windows
✅ **Incremental Changes**: Limits bid swings to ±20%
✅ **Min Data Threshold**: Requires >10 clicks for optimization
✅ **Fallback Logic**: Uses Ad Group Default Bid when needed

## Development

See **docs/CLAUDE.md** for detailed developer instructions.

## License

MIT License - see `LICENSE`.

## Support

For issues or questions:
1. Review **ROADMAP.md** for current priorities and status
2. Review **SUMMARY.md** for architecture/workflow context
3. Check **archive/docs/** for historical phase/status notes
4. Run `python -m pytest tests/` to verify installation

---

**Built with**: Python, Streamlit, Pandas, NumPy, Openpyxl, sentence-transformers, scikit-learn, PyTorch

**Version**: 4.1 (P2 Scale + P3 Packaging)

**Last Updated**: 2026-02-24
