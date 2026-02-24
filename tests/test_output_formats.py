from io import BytesIO

import pandas as pd


def test_operation_column_has_no_nan_or_nan_string(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    assert optimizer.df["Operation"].isna().sum() == 0
    assert (optimizer.df["Operation"] == "nan").sum() == 0


def test_amazon_upload_file_excludes_analysis_sheets(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    output = BytesIO()
    optimizer.save_optimized_file(output, include_analysis_sheets=False, amazon_upload_ready=True)
    output.seek(0)

    sheets = pd.ExcelFile(output).sheet_names
    analysis_sheets = {"Test More Report", "Budget Recommendations", "Cannibalization Report"}
    assert analysis_sheets.isdisjoint(set(sheets))

    # Amazon upload should contain actionable rows only (non-empty Operation)
    sp_df = pd.read_excel(output, sheet_name="Sponsored Products Campaigns")
    if not sp_df.empty and "Operation" in sp_df.columns:
        operations = (
            sp_df["Operation"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace({"nan": "", "NaN": "", "None": "", "none": ""})
        )
        assert (operations != "").all()


def test_full_analysis_file_includes_budget_sheet(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    output = BytesIO()
    optimizer.save_optimized_file(output, include_analysis_sheets=True, amazon_upload_ready=False)
    output.seek(0)

    sheets = pd.ExcelFile(output).sheet_names
    assert "Budget Recommendations" in sheets


def test_amazon_upload_excludes_unsupported_keyword_group_targets(optimizer):
    optimizer.optimize_bids()
    optimizer.identify_bleeders()

    row = {col: "" for col in optimizer.df.columns}
    row.update(optimizer.df.iloc[0].to_dict())
    row["Product"] = "Sponsored Products"
    row["Entity"] = "Product Targeting"
    row["Operation"] = "Update"
    row["Product Targeting Expression"] = 'keyword-group="gift"'
    if "Resolved Product Targeting Expression (Informational only)" in optimizer.df.columns:
        row["Resolved Product Targeting Expression (Informational only)"] = (
            'keyword-group="Keywords related to gifts"'
        )

    optimizer.df = pd.concat([optimizer.df, pd.DataFrame([row])], ignore_index=True)

    output = BytesIO()
    optimizer.save_optimized_file(output, include_analysis_sheets=False, amazon_upload_ready=True)
    output.seek(0)

    sp_df = pd.read_excel(output, sheet_name="Sponsored Products Campaigns")
    if "Product Targeting Expression" in sp_df.columns:
        expr = sp_df["Product Targeting Expression"].fillna("").astype(str).str.strip().str.lower()
        assert not expr.str.startswith("keyword-group=").any()
