# Output Data Improvement Notes

Last Updated: 2026-02-24

## Source Run Snapshot

Sample file tested:
- `bulk-a2kk083uqnb8ha-20260125-20260224-1771933500225.xlsx`

Observed:
- 39 RPC bid updates
- 12 low-visibility terms
- 84 rows with spend and zero sales
- 12 rows with impressions >= 100 and zero clicks
- NLP clustering fallback occurred when model download was unavailable

## Improvement Opportunities

1. Add reason-code columns for every changed row
- Proposed columns: `Optimization_Reason`, `Threshold_Context`
- Benefit: faster QA and safer approval workflows before Amazon upload.

2. Add `no-change` diagnostics
- Track rows excluded by low data, bid cap, and safety bounds.
- Benefit: explainability for why expected rows were not updated.

3. Add high-impression zero-click escalation
- After N runs without clicks, auto-mark for negative or pause recommendation.
- Benefit: avoid repeated spend on low-relevance traffic.

4. Expand trend reporting
- Show run-over-run deltas for:
  - `% zero-sale spend`
  - `% high-impression zero-click`
  - cold-start conversion pickup rate
- Benefit: detect strategy drift earlier.

5. Add confidence band to Type C z-score mode
- Use both relative (`zscore`) and absolute (`min/max impression`) guardrails.
- Benefit: reduce edge-case misclassification in sparse accounts.
