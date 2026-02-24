# Pending Features & Future Enhancements

## Date: 2026-02-11
## Current Version: v4.0 (NLP Intelligence - Phase 3 Complete)

---

## 📋 Overview

This document tracks features from the original specification that are **not yet implemented**, as well as potential enhancements identified during development.

---

## 🚧 From Original Specification

### **Phase 2: Structural Control** ❌ NOT STARTED

#### 1. Cannibalization Check
**Status**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: MODERATE

**Description**:
Detect duplicate targets across ad groups that may be competing against each other, driving up costs.

**Implementation Plan**:
- Scan all ad groups for duplicate keywords/targets
- Check for:
  - Exact same keyword in multiple ad groups
  - Same keyword with different match types
  - Overlapping product targeting
- Generate report with:
  - Conflicting ad group pairs
  - Bid differences
  - Performance metrics for each instance
- Recommend consolidation or bid adjustments

**Technical Approach**:
```python
def detect_cannibalization(self):
    """
    Identifies duplicate keywords across ad groups.
    Returns: DataFrame with conflicts
    """
    # Group by keyword text
    # Find keywords appearing in multiple ad groups
    # Calculate performance differences
    # Flag high-severity conflicts
```

**Estimated Effort**: 4-6 hours

**Benefits**:
- Prevent internal competition
- Reduce wasted spend
- Improve campaign structure

---

#### 2. Budget Optimization
**Status**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: HIGH

**Description**:
Reallocate campaign budgets based on ROAS (Return on Ad Spend) to maximize overall account performance.

**Implementation Plan**:
- Calculate ROAS for each campaign
- Identify high-performing campaigns (ROAS > target)
- Identify low-performing campaigns (ROAS < target)
- Suggest budget reallocations:
  - Increase budget for high-ROAS campaigns
  - Decrease/pause budget for low-ROAS campaigns
- Generate "Budget Reallocation Report"

**Technical Approach**:
```python
def optimize_budgets(self):
    """
    Analyzes campaign ROAS and suggests budget changes.
    Returns: dict with budget recommendations
    """
    # Calculate ROAS per campaign
    # Sort by ROAS
    # Apply budget allocation algorithm
    # Generate recommendations with expected impact
```

**Challenges**:
- Need campaign-level budget data (may not be in bulk file)
- Amazon has daily budget constraints
- Need to account for seasonality

**Estimated Effort**: 8-12 hours

**Benefits**:
- Maximize account-wide ROAS
- Automatically scale winners
- Cut losses quickly

---

### **Phase 3: Semantic Intelligence** ✅ COMPLETE (v4.0)

#### 1. Search Term Intent Clustering
**Status**: ✅ IMPLEMENTED (2026-02-11)
**Priority**: ~~LOW~~ COMPLETED
**Complexity**: HIGH

**Description**:
Use NLP to cluster search terms by customer intent, allowing smarter negative keyword recommendations and campaign structure improvements.

**Implementation Plan**:
- Add NLP dependencies:
  - `sentence-transformers` (for embeddings)
  - `scikit-learn` (for clustering)
- Process search term report:
  - Generate embeddings for each search term
  - Apply clustering (K-means or DBSCAN)
  - Label clusters by intent
- Generate reports:
  - "Intent Clusters" showing grouped terms
  - Performance by intent
  - Suggested campaign structure

**Technical Approach**:
```python
from sentence_transformers import SentenceTransformer
from sklearn.cluster import KMeans

def cluster_search_terms(self):
    """
    Clusters search terms by semantic similarity.
    Returns: DataFrame with cluster assignments
    """
    # Load pre-trained model
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # Generate embeddings
    embeddings = model.encode(search_terms)

    # Cluster
    clusters = KMeans(n_clusters=10).fit_predict(embeddings)

    # Analyze performance by cluster
```

**Estimated Effort**: 12-16 hours

**Benefits**:
- Better campaign organization
- Discover new keyword opportunities
- Identify irrelevant traffic patterns

---

#### 2. Negative Keyword Recommendations
**Status**: ✅ IMPLEMENTED (2026-02-11)
**Priority**: LOW
**Complexity**: MODERATE

**Description**:
Automatically suggest negative keywords based on semantic irrelevance to product/campaign.

**Implementation Plan**:
- Require user input: campaign description or product category
- Compare search terms to campaign intent using embeddings
- Flag terms with low semantic similarity + poor performance
- Generate "Suggested Negatives" report

**Technical Approach**:
```python
def recommend_negative_keywords(self, campaign_description):
    """
    Suggests negative keywords based on semantic irrelevance.
    Returns: list of suggested negatives
    """
    # Encode campaign description
    # Encode each search term
    # Calculate similarity scores
    # Filter low-similarity + poor performers
    # Return recommendations
```

**Estimated Effort**: 6-8 hours

**Benefits**:
- Reduce wasted spend
- Improve campaign relevance
- Automate tedious negative keyword research

---

## 🔧 Additional Improvements (Not in Original Spec)

### **1. Configurable Thresholds**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: LOW

**Description**:
Make hardcoded thresholds adjustable via UI.

**Currently Hardcoded**:
- Min clicks for optimization: 10
- Type A impressions threshold: 1,000
- Type A Z-score threshold: -1.5
- Type B Z-score multiplier: 2.0
- Type C impressions threshold: 100
- Max bid change per cycle: ±20%

**Implementation**:
- Add "Advanced Settings" section in Streamlit sidebar
- Add sliders/inputs for each threshold
- Pass to optimizer as parameters
- Save/load configurations (JSON file)

**Estimated Effort**: 2-3 hours

**Benefits**:
- Flexibility for different account types
- A/B test different strategies
- Power users can fine-tune

---

### **2. Export Optimization Log**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: LOW

**Description**:
Allow users to download the optimization log as a text file for record-keeping.

**Implementation**:
- Add "Download Log" button in Streamlit
- Export log as `.txt` or `.log` file
- Include timestamp in filename

**Estimated Effort**: 1 hour

**Benefits**:
- Better audit trail
- Compliance/record-keeping
- Debugging assistance

---

### **3. Batch Processing**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: MODERATE

**Description**:
Process multiple bulk files at once (for agencies managing multiple accounts).

**Implementation**:
- Allow multi-file upload in Streamlit
- Process each file sequentially
- Generate combined summary report
- Zip all output files for download

**Estimated Effort**: 4-6 hours

**Benefits**:
- Huge time saver for agencies
- Consistent optimization across accounts
- Bulk reporting

---

### **4. Historical Tracking & Comparison**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: MODERATE

**Description**:
Track optimization runs over time and compare performance.

**Implementation**:
- Store optimization results in SQLite database
- Track key metrics per run:
  - Date/time
  - Bid changes count
  - Bleeder counts
  - File hash (to detect same file)
- Add "History" page to Streamlit
- Visualize trends over time (charts)

**Estimated Effort**: 6-8 hours

**Benefits**:
- See optimization impact over time
- Identify trends
- Performance analytics

---

### **5. Performance Profiling**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: LOW

**Description**:
Add performance timing to identify bottlenecks in large files.

**Implementation**:
- Use Python's `time` or `cProfile`
- Log time spent in each optimization step
- Display timing summary in log
- Identify optimization opportunities

**Estimated Effort**: 2-3 hours

**Benefits**:
- Optimize for large files
- User transparency
- Development insights

---

### **6. API Mode / CLI Mode**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: MODERATE

**Description**:
Add command-line interface for automation/scripting.

**Implementation**:
```bash
# CLI usage
python -m optimizer --input bulk.xlsx --output optimized.xlsx --target-acos 0.30

# Or as API
from optimizer import BulkOptimizer
opt = BulkOptimizer('file.xlsx')
opt.run()
opt.save('output.xlsx')
```

**Estimated Effort**: 3-4 hours

**Benefits**:
- Automation workflows
- Integration with other tools
- Scheduled optimizations

---

### **7. Email Notifications**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: LOW

**Description**:
Send email when optimization completes (useful for large files).

**Implementation**:
- Add email settings in config
- Use SMTP to send notification
- Include optimization summary in email
- Attach optimized file (optional)

**Estimated Effort**: 2-3 hours

**Benefits**:
- Convenience for long-running jobs
- Automated workflows
- Multi-user teams

---

### **8. Unit Tests (Granular)**
**Status**: ❌ PARTIALLY IMPLEMENTED
**Priority**: MEDIUM
**Complexity**: MODERATE

**Current State**:
- Integration tests exist (test_fixes.py, test_priority2_features.py)
- No unit tests for individual methods

**Implementation**:
```python
# Unit test examples
def test_rpc_calculation():
    """Test RPC formula in isolation"""
    assert calculate_rpc(sales=100, clicks=10) == 10

def test_z_score_calculation():
    """Test Z-score computation"""
    assert calculate_z_score(value=5, mean=3, std=2) == 1.0
```

**Estimated Effort**: 4-6 hours

**Benefits**:
- Catch bugs early
- Safe refactoring
- Better code quality

---

### **9. Docker Deployment**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: LOW

**Description**:
Containerize the app for easy deployment.

**Implementation**:
```dockerfile
FROM python:3.10
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "src/app.py"]
```

**Estimated Effort**: 1-2 hours

**Benefits**:
- Consistent environment
- Easy deployment
- Cloud-ready

---

### **10. Data Visualization Dashboard**
**Status**: ❌ NOT IMPLEMENTED
**Priority**: LOW
**Complexity**: MODERATE

**Description**:
Add charts/graphs to Streamlit for better insights.

**Potential Charts**:
- Bid change distribution (histogram)
- Performance by campaign (bar chart)
- ACOS trend over time (line chart)
- Bleeder breakdown (pie chart)
- Before/after comparison

**Implementation**:
- Use Plotly or Streamlit's built-in charts
- Add "Analytics" tab to Streamlit

**Estimated Effort**: 4-6 hours

**Benefits**:
- Visual insights
- Better decision-making
- Professional appearance

---

## 📊 Priority Matrix

| Feature | Priority | Complexity | Effort | Business Value |
|---------|----------|------------|--------|----------------|
| **Configurable Thresholds** | 🔴 HIGH | LOW | 2-3h | HIGH |
| **Cannibalization Check** | 🟡 MEDIUM | MODERATE | 4-6h | HIGH |
| **Budget Optimization** | 🟡 MEDIUM | HIGH | 8-12h | HIGH |
| **Export Log** | 🟢 LOW | LOW | 1h | MEDIUM |
| **Batch Processing** | 🟢 LOW | MODERATE | 4-6h | MEDIUM |
| **Historical Tracking** | 🟢 LOW | MODERATE | 6-8h | MEDIUM |
| **Unit Tests** | 🟡 MEDIUM | MODERATE | 4-6h | MEDIUM |
| **Performance Profiling** | 🟢 LOW | LOW | 2-3h | LOW |
| **CLI Mode** | 🟢 LOW | MODERATE | 3-4h | LOW |
| **Email Notifications** | 🟢 LOW | LOW | 2-3h | LOW |
| **Docker Deployment** | 🟢 LOW | LOW | 1-2h | MEDIUM |
| **Visualization Dashboard** | 🟢 LOW | MODERATE | 4-6h | MEDIUM |
| **Intent Clustering** | 🟢 LOW | HIGH | 12-16h | LOW |
| **Negative Keyword Recs** | 🟢 LOW | MODERATE | 6-8h | MEDIUM |

---

## 🎯 Recommended Roadmap

### **Phase 3 (Quick Wins) - 5-10 hours**
1. ✅ Configurable Thresholds (2-3h)
2. ✅ Export Optimization Log (1h)
3. ✅ Performance Profiling (2-3h)
4. ✅ Docker Deployment (1-2h)

### **Phase 4 (Structural Improvements) - 12-18 hours**
1. ✅ Cannibalization Check (4-6h)
2. ✅ Budget Optimization (8-12h)

### **Phase 5 (Advanced Features) - 10-14 hours**
1. ✅ Batch Processing (4-6h)
2. ✅ Historical Tracking (6-8h)

### **Phase 6 (Intelligence) - 18-24 hours**
1. ✅ Search Term Intent Clustering (12-16h)
2. ✅ Negative Keyword Recommendations (6-8h)

---

## 📝 Notes

### **Why Not Implemented Yet?**
- **Phase 1 & 2 priorities**: Focus was on critical bugs and core functionality
- **Diminishing returns**: Current version solves 80% of the problem
- **Spec dependencies**: Phase 3 features require additional libraries (NLP models)
- **User feedback needed**: Some features may not be valuable to actual users

### **Should You Implement These?**
- **If you're an agency**: Batch processing + cannibalization check would be huge
- **If you're data-driven**: Historical tracking + visualization
- **If you're technical**: CLI mode + Docker
- **If you want AI features**: Intent clustering + negative keyword recs

### **Current State is Production-Ready**
The tool is fully functional without these features. These are enhancements, not requirements.

---

## 🤔 Questions Before Implementing

1. **Who are the primary users?**
   - Individual sellers → Current features sufficient
   - Agencies → Need batch processing
   - Enterprises → Need API/automation

2. **What's the biggest pain point?**
   - Slow optimizations → Performance profiling
   - Manual work → Automation features
   - Poor decisions → Advanced analytics

3. **What's the budget?**
   - Low → Focus on quick wins (Phase 3)
   - Medium → Add structural features (Phase 4)
   - High → Full AI implementation (Phase 6)

---

## ✅ Summary

**From Original Spec**:
- ❌ 2 major features from Phase 2 (Cannibalization, Budget Optimization)
- ❌ 2 major features from Phase 3 (Intent Clustering, Negative Keywords)

**Potential Enhancements**:
- ❌ 10 improvements identified (configurable thresholds, batch processing, etc.)

**Total Pending Work**:
- **Estimated**: 70-110 hours for everything
- **Recommended next**: Phase 3 Quick Wins (5-10 hours)

**Current Status**:
- ✅ Core functionality: 100% complete
- ✅ Production ready: YES
- ✅ Pending features: Nice-to-have, not critical

---

*Last Updated: 2026-02-11*
