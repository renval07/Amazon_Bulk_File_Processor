import pandas as pd
import numpy as np
import re
import logging
from datetime import datetime, timedelta
from io import BytesIO

# Lazy-loaded NLP dependencies.
# Tests may monkeypatch these symbols directly.
SentenceTransformer = None
KMeans = None
silhouette_score = None
TfidfVectorizer = None

class BulkOptimizer:
    TYPE_A_LABEL = "Low Engagement"
    TYPE_B_LABEL = "High-Cost Non-Converter"
    TYPE_C_LABEL = "Low Visibility"
    AUTO_TARGET_BUCKETS = {
        "close-match",
        "loose-match",
        "substitutes",
        "complements",
        "close match",
        "loose match",
    }

    def __init__(
        self,
        file_source,
        filename=None,
        target_acos=0.30,
        min_bid=0.02,
        max_bid=5.00,
        enforce_48hr_rule=True,
        enable_logging=True,
        optimization_min_clicks=10,
        max_bid_change_pct=0.20,
        bleeder_type_a_impressions_threshold=1000,
        bleeder_type_a_z_threshold=-1.5,
        bleeder_type_b_clicks_std_multiplier=2.0,
        bleeder_type_c_impressions_threshold=100,
        bleeder_type_c_mode="fixed",
        bleeder_type_c_percentile=0.25,
        bleeder_type_c_z_threshold=-1.0,
        bleeder_segmentation_mode="none",
        segmentation_min_entities=25,
        confidence_enable=True,
        type_a_confidence_level=0.95,
        type_b_min_spend=5.0,
        cold_start_step_up_amount=0.02,
        cold_start_enable=True,
        cold_start_mode="fixed",
        cold_start_ladder_cap=0.08,
        cold_start_stalled_impressions=300,
    ):
        # Input validation
        if target_acos <= 0 or target_acos > 1:
            raise ValueError(f"target_acos must be between 0 and 1 (e.g., 0.30 for 30%), got {target_acos}")
        if min_bid < 0:
            raise ValueError(f"min_bid must be non-negative, got {min_bid}")
        if max_bid < min_bid:
            raise ValueError(f"max_bid ({max_bid}) must be greater than or equal to min_bid ({min_bid})")
        if optimization_min_clicks < 0:
            raise ValueError(f"optimization_min_clicks must be non-negative, got {optimization_min_clicks}")
        if max_bid_change_pct < 0 or max_bid_change_pct > 1:
            raise ValueError(f"max_bid_change_pct must be between 0 and 1, got {max_bid_change_pct}")
        if bleeder_type_a_impressions_threshold < 0:
            raise ValueError("bleeder_type_a_impressions_threshold must be non-negative")
        if bleeder_type_c_impressions_threshold < 0:
            raise ValueError("bleeder_type_c_impressions_threshold must be non-negative")
        if bleeder_type_b_clicks_std_multiplier < 0:
            raise ValueError("bleeder_type_b_clicks_std_multiplier must be non-negative")
        if bleeder_type_c_mode not in {"fixed", "percentile", "zscore"}:
            raise ValueError("bleeder_type_c_mode must be one of: fixed, percentile, zscore")
        if bleeder_segmentation_mode not in {"none", "match_type", "campaign"}:
            raise ValueError("bleeder_segmentation_mode must be one of: none, match_type, campaign")
        if segmentation_min_entities <= 0:
            raise ValueError("segmentation_min_entities must be > 0")
        if type_a_confidence_level not in {0.80, 0.85, 0.90, 0.95, 0.99}:
            raise ValueError("type_a_confidence_level must be one of: 0.80, 0.85, 0.90, 0.95, 0.99")
        if type_b_min_spend < 0:
            raise ValueError("type_b_min_spend must be non-negative")
        if bleeder_type_c_percentile <= 0 or bleeder_type_c_percentile >= 1:
            raise ValueError("bleeder_type_c_percentile must be between 0 and 1 (exclusive)")
        if cold_start_step_up_amount < 0:
            raise ValueError("cold_start_step_up_amount must be non-negative")
        if cold_start_mode not in {"fixed", "ladder"}:
            raise ValueError("cold_start_mode must be one of: fixed, ladder")
        if cold_start_ladder_cap < 0:
            raise ValueError("cold_start_ladder_cap must be non-negative")
        if cold_start_stalled_impressions < 0:
            raise ValueError("cold_start_stalled_impressions must be non-negative")

        self.file_source = file_source
        self.filename = filename or (file_source if isinstance(file_source, str) else "")
        self.target_acos = target_acos
        self.min_bid = min_bid
        self.max_bid = max_bid
        self.enforce_48hr_rule = enforce_48hr_rule
        self.optimization_min_clicks = optimization_min_clicks
        self.max_bid_change_pct = max_bid_change_pct
        self.bleeder_type_a_impressions_threshold = bleeder_type_a_impressions_threshold
        self.bleeder_type_a_z_threshold = bleeder_type_a_z_threshold
        self.bleeder_type_b_clicks_std_multiplier = bleeder_type_b_clicks_std_multiplier
        self.bleeder_type_c_impressions_threshold = bleeder_type_c_impressions_threshold
        self.bleeder_type_c_mode = bleeder_type_c_mode
        self.bleeder_type_c_percentile = bleeder_type_c_percentile
        self.bleeder_type_c_z_threshold = bleeder_type_c_z_threshold
        self.bleeder_segmentation_mode = bleeder_segmentation_mode
        self.segmentation_min_entities = segmentation_min_entities
        self.confidence_enable = confidence_enable
        self.type_a_confidence_level = type_a_confidence_level
        self.type_b_min_spend = type_b_min_spend
        self.cold_start_step_up_amount = cold_start_step_up_amount
        self.cold_start_enable = cold_start_enable
        self.cold_start_mode = cold_start_mode
        self.cold_start_ladder_cap = cold_start_ladder_cap
        self.cold_start_stalled_impressions = cold_start_stalled_impressions
        self.df = None
        self.original_sheets = {}
        self.file_end_date = None
        self.days_since_file_end = None
        self.optimization_log = []
        self.performance_metrics = {}

        # Setup logging
        if enable_logging:
            self.logger = logging.getLogger(f'BulkOptimizer_{id(self)}')
            self.logger.setLevel(logging.INFO)
            # Clear any existing handlers
            self.logger.handlers = []
            # Add handler if not already present
            if not self.logger.handlers:
                handler = logging.StreamHandler()
                formatter = logging.Formatter('[%(levelname)s] %(message)s')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
        else:
            self.logger = None

        self._log(f"Optimizer initialized: target_acos={target_acos}, min_bid=${min_bid}, max_bid=${max_bid}")

    def _log(self, message, level='info'):
        """Internal logging helper"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        self.optimization_log.append(log_entry)

        if self.logger:
            if level == 'info':
                self.logger.info(message)
            elif level == 'warning':
                self.logger.warning(message)
            elif level == 'error':
                self.logger.error(message)

    def get_optimization_log(self):
        """Returns the optimization log as a string"""
        return '\n'.join(self.optimization_log)

    def record_stage_timing(self, stage_name, duration_seconds):
        """Stores stage timing and adds it to the optimization log."""
        self.performance_metrics[stage_name] = float(duration_seconds)
        self._log(f"Timing: {stage_name} completed in {duration_seconds:.2f}s")

    def get_performance_metrics(self):
        """Returns per-stage performance timings in seconds."""
        return dict(self.performance_metrics)

    @classmethod
    def _normalized_targeting_expression(cls, series):
        """Normalizes product targeting expressions for matching/filtering."""
        return series.fillna('').astype(str).str.strip().str.lower()

    @classmethod
    def _is_auto_target_bucket(cls, series):
        normalized = cls._normalized_targeting_expression(series)
        return normalized.isin(cls.AUTO_TARGET_BUCKETS)

    def _ensure_nlp_dependencies(self):
        """Loads NLP dependencies on demand to keep startup lightweight."""
        global SentenceTransformer, KMeans, silhouette_score, TfidfVectorizer

        if KMeans is None:
            from sklearn.cluster import KMeans as _KMeans

            KMeans = _KMeans
        if silhouette_score is None:
            from sklearn.metrics import silhouette_score as _silhouette_score

            silhouette_score = _silhouette_score
        if TfidfVectorizer is None:
            from sklearn.feature_extraction.text import TfidfVectorizer as _TfidfVectorizer

            TfidfVectorizer = _TfidfVectorizer
        if SentenceTransformer is None:
            try:
                from sentence_transformers import SentenceTransformer as _SentenceTransformer

                SentenceTransformer = _SentenceTransformer
            except Exception:
                # Optional dependency: keep startup/deploy lightweight when transformer stack is unavailable.
                SentenceTransformer = False

    def _generate_search_embeddings(self, search_terms):
        """Generates vectors for search terms with a semantic-model first strategy and TF-IDF fallback."""
        self._ensure_nlp_dependencies()

        # Prefer sentence-transformers when installed and working.
        if SentenceTransformer:
            try:
                self._log("Loading NLP model (all-MiniLM-L6-v2)...")
                model = SentenceTransformer('all-MiniLM-L6-v2')
                self._log("Generating semantic embeddings...")
                embeddings = model.encode(search_terms, show_progress_bar=False)
                self._log("Embedding backend: sentence-transformers")
                return np.asarray(embeddings)
            except Exception as exc:
                self._log(
                    f"Sentence-transformers unavailable for this run ({exc}); falling back to TF-IDF.",
                    level='warning',
                )

        # Lightweight fallback that keeps clustering available in constrained environments.
        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=512)
        embeddings = vectorizer.fit_transform([str(term) for term in search_terms]).toarray()
        self._log("Embedding backend: TF-IDF fallback")
        return np.asarray(embeddings)

    def _z_score_for_confidence(self, confidence_level):
        """Maps supported confidence levels to z-scores."""
        mapping = {
            0.80: 1.282,
            0.85: 1.440,
            0.90: 1.645,
            0.95: 1.960,
            0.99: 2.576,
        }
        return mapping.get(confidence_level, 1.960)

    def _wilson_upper_bound(self, successes, trials, z):
        """Vectorized Wilson score upper bound for a binomial proportion."""
        n = pd.to_numeric(trials, errors="coerce").fillna(0).astype(float)
        k = pd.to_numeric(successes, errors="coerce").fillna(0).astype(float)
        p = np.where(n > 0, k / n, 0.0)
        denom = 1.0 + (z * z / np.maximum(n, 1.0))
        center = p + (z * z / (2.0 * np.maximum(n, 1.0)))
        margin = z * np.sqrt((p * (1.0 - p) / np.maximum(n, 1.0)) + (z * z / (4.0 * np.maximum(n, 1.0) ** 2)))
        upper = (center + margin) / denom
        return pd.Series(np.where(n > 0, upper, 0.0), index=trials.index if isinstance(trials, pd.Series) else None)

    def _build_bleeder_segment_key(self, df):
        """Builds a segment key for thresholding stats."""
        if self.bleeder_segmentation_mode == "none":
            return pd.Series("__all__", index=df.index, dtype="object")

        if self.bleeder_segmentation_mode == "match_type":
            if "Match Type" in df.columns:
                match = df["Match Type"].fillna("unknown").astype(str).str.strip().str.lower()
                return match.where(match != "", "unknown")
            return pd.Series("__all__", index=df.index, dtype="object")

        # campaign mode
        campaign_cols = ["Campaign Name", "Campaign Name (Informational only)"]
        campaign = pd.Series("unknown_campaign", index=df.index, dtype="object")
        for col in campaign_cols:
            if col in df.columns:
                values = (
                    df[col]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .replace({"nan": "", "NaN": "", "None": "", "none": ""})
                )
                campaign = campaign.where(campaign != "unknown_campaign", values.where(values != "", "unknown_campaign"))
        if "Match Type" in df.columns:
            match = df["Match Type"].fillna("unknown").astype(str).str.strip().str.lower()
            match = match.where(match != "", "unknown")
            return campaign.astype(str) + "|" + match.astype(str)
        return campaign

    def load_data(self):
        """Loads the bulk file and stores original sheets."""
        self._log(f"Loading bulk file: {self.filename}")

        if hasattr(self.file_source, 'seek'):
            self.file_source.seek(0)

        self.original_sheets = pd.read_excel(self.file_source, sheet_name=None)
        self.sheet_names = list(self.original_sheets.keys())
        self._log(f"Found {len(self.sheet_names)} sheets: {', '.join(self.sheet_names)}")

        # Working DataFrame: Sponsored Products Campaigns
        if 'Sponsored Products Campaigns' in self.original_sheets:
            self.df = self.original_sheets['Sponsored Products Campaigns'].copy()
            self._log(f"Loaded 'Sponsored Products Campaigns' sheet with {len(self.df)} rows")
        else:
            self._log("ERROR: Sheet 'Sponsored Products Campaigns' not found", level='error')
            raise ValueError("Sheet 'Sponsored Products Campaigns' not found in the bulk file.")

        # Validate required columns exist
        required_cols = ['Entity', 'Impressions', 'Clicks', 'Spend', 'Sales', 'Bid']
        missing_cols = [col for col in required_cols if col not in self.df.columns]
        if missing_cols:
            self._log(f"ERROR: Missing required columns: {', '.join(missing_cols)}", level='error')
            raise ValueError(f"Missing required columns: {', '.join(missing_cols)}")

        self._log("All required columns present")

        # Ensure numeric columns
        numeric_cols = ['Impressions', 'Clicks', 'Spend', 'Sales', 'Bid', 'Ad Group Default Bid']
        for col in numeric_cols:
            if col in self.df.columns:
                # Clean currency symbols and handle 'Infinity' ACOS
                if self.df[col].dtype == 'object':
                    self.df[col] = self.df[col].astype(str).str.replace('$', '', regex=False)
                    self.df[col] = self.df[col].replace(['Infinity', 'infinity', 'inf'], '0')
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce').fillna(0)

        self._log("Data cleaning complete (currency symbols, infinity values handled)")

        # Ensure Operation column exists and is object dtype (to avoid dtype warnings)
        if 'Operation' not in self.df.columns:
            self.df['Operation'] = ''
        # Convert to string FIRST (this converts NaN to 'nan' string)
        self.df['Operation'] = self.df['Operation'].astype(str)
        # Then replace 'nan' strings with empty string
        self.df['Operation'] = self.df['Operation'].replace(['nan', 'NaN', 'None'], '')
        # Also handle any remaining NaN (shouldn't be any, but just in case)
        self.df['Operation'] = self.df['Operation'].fillna('')

        # Log summary statistics
        keywords_count = (self.df['Entity'].isin(['Keyword', 'Product Targeting'])).sum()
        total_impressions = self.df['Impressions'].sum()
        total_clicks = self.df['Clicks'].sum()
        total_sales = self.df['Sales'].sum()
        total_spend = self.df['Spend'].sum()

        self._log(f"Data summary: {keywords_count} keywords/targets, {total_impressions:,.0f} impressions, {total_clicks:,.0f} clicks, ${total_sales:,.2f} sales, ${total_spend:,.2f} spend")

    def check_48_hour_rule(self):
        """
        Checks if the file name implies recent data.
        Stores date information and returns a warning message if detected.
        This is advisory-only and does not block processing.
        """
        # Regex to find date range in filename (e.g., 20251213-20260211)
        match = re.search(r'(\d{8})-(\d{8})', self.filename)
        if match:
            end_date_str = match.group(2)
            try:
                self.file_end_date = datetime.strptime(end_date_str, "%Y%m%d")
                self.days_since_file_end = (datetime.now() - self.file_end_date).days

                if self.days_since_file_end < 2:
                    warning_msg = (
                        f"WARNING: The file end date ({end_date_str}) is within the last 48 hours. "
                        f"Amazon attribution may be incomplete. This is the #1 cause of bad bid changes. "
                        f"Recommended: Wait {2 - self.days_since_file_end} more day(s) or download an older file."
                    )
                    return warning_msg
            except ValueError as e:
                pass
        return None

    def optimize_bids(self):
        """Applies RPC Bid Optimization."""
        self._log("Starting RPC bid optimization...")

        if self.df is None:
            self._log("ERROR: No data loaded", level='error')
            return 0

        # Filter for Keywords and Product Targeting only
        mask = self.df['Entity'].isin(['Keyword', 'Product Targeting'])
        eligible_count = mask.sum()
        self._log(f"Found {eligible_count} eligible keywords/targets for optimization")

        # Vectorized RPC Calculation
        # RPC = Sales / Clicks. Handle division by zero.
        rpc = np.where(self.df['Clicks'] > 0, self.df['Sales'] / self.df['Clicks'], 0)

        # Target Bid = RPC * Target ACOS
        new_bid = rpc * self.target_acos

        # Constraints
        # Fallback if Bid is 0/empty using numpy where
        current_bid = np.where(self.df['Bid'] == 0, self.df['Ad Group Default Bid'], self.df['Bid'])

        # 1. Max Change 20%
        # Calculate bounds
        lower_bound = current_bid * (1 - self.max_bid_change_pct)
        upper_bound = current_bid * (1 + self.max_bid_change_pct)

        # Apply limits
        optimized_bid = np.clip(new_bid, lower_bound, upper_bound)

        # 2. Min/Max Bids
        optimized_bid = np.clip(optimized_bid, self.min_bid, self.max_bid)

        # 3. Only apply if clicks > optimization_min_clicks (Statistical Significance)
        # We will use 'Clicks > 10' as the trigger to switch from "Current Bid" to "RPC Bid"
        # If Clicks <= 10, keep current bid with fallback (unless bleeder logic hits it)

        # Count keywords with insufficient data
        low_data_count = ((mask) & (self.df['Clicks'] <= self.optimization_min_clicks)).sum()
        self._log(f"Skipping {low_data_count} keywords with <={self.optimization_min_clicks} clicks (insufficient data)")

        # CRITICAL FIX: Use current_bid (which has Ad Group Default Bid fallback) instead of self.df['Bid']
        final_bid = np.where((mask) & (self.df['Clicks'] > self.optimization_min_clicks), optimized_bid, current_bid)

        # Count changes
        changes_mask = (mask) & (self.df['Clicks'] > self.optimization_min_clicks) & (final_bid != current_bid)
        changes = np.sum(changes_mask)

        # CRITICAL: Set Operation column to 'Update' for changed rows
        if changes > 0:
            self.df.loc[changes_mask, 'Operation'] = 'Update'

        # Log bid change statistics
        if changes > 0:
            bid_increases = np.sum((mask) & (self.df['Clicks'] > self.optimization_min_clicks) & (final_bid > current_bid))
            bid_decreases = np.sum((mask) & (self.df['Clicks'] > self.optimization_min_clicks) & (final_bid < current_bid))
            self._log(f"RPC optimization complete: {changes} bid changes ({bid_increases} increases, {bid_decreases} decreases)")
            self._log(f"  → Operation column set to 'Update' for {changes} rows")
        else:
            self._log("RPC optimization complete: No bid changes needed")

        self.df['Bid'] = final_bid
        return changes

    def identify_bleeders(self):
        """
        Identifies bleeders using Z-Scores and adjusts bids.
        Type A: Low CTR (Impression Bloat) -> Reduce Bid
        Type B: Click-heavy non-converting terms -> Reduce Bid
        Type C: Low volume terms -> Flag for "Test More"

        Returns: dict with counts by bleeder type
        """
        self._log("Starting bleeder identification using Z-Score analysis...")

        if self.df is None:
            self._log("ERROR: No data loaded", level='error')
            return {'type_a': 0, 'type_b': 0, 'type_c': 0, 'total': 0}

        mask = self.df['Entity'].isin(['Keyword', 'Product Targeting'])
        stats_df = self.df[mask].copy()

        if stats_df.empty:
            self._log("WARNING: No keywords/targets found for bleeder analysis", level='warning')
            return {'type_a': 0, 'type_b': 0, 'type_c': 0, 'total': 0}

        # Reset bleeder/action flags for active entities on each run.
        if 'Bleeder_Type' not in self.df.columns:
            self.df['Bleeder_Type'] = ''
        self.df.loc[mask, 'Bleeder_Type'] = ''

        if 'Cold_Start_Action' not in self.df.columns:
            self.df['Cold_Start_Action'] = ''
        self.df.loc[mask, 'Cold_Start_Action'] = ''

        # Build segmentation stats (or account-wide if segmentation disabled/small segment).
        stats_df['Calculated_CTR'] = np.where(stats_df['Impressions'] > 0, stats_df['Clicks'] / stats_df['Impressions'], 0)
        stats_df['_segment_key'] = self._build_bleeder_segment_key(stats_df)
        segment_stats = stats_df.groupby('_segment_key').agg(
            segment_count=('Calculated_CTR', 'count'),
            mean_ctr=('Calculated_CTR', 'mean'),
            std_ctr=('Calculated_CTR', 'std'),
            mean_clicks=('Clicks', 'mean'),
            std_clicks=('Clicks', 'std'),
        )
        stats_df = stats_df.join(segment_stats, on='_segment_key')

        global_mean_ctr = float(stats_df['Calculated_CTR'].mean())
        global_std_ctr = float(stats_df['Calculated_CTR'].std())
        global_mean_clicks = float(stats_df['Clicks'].mean())
        global_std_clicks = float(stats_df['Clicks'].std())

        small_segment_mask = stats_df['segment_count'] < self.segmentation_min_entities
        stats_df['eff_mean_ctr'] = np.where(small_segment_mask, global_mean_ctr, stats_df['mean_ctr'])
        stats_df['eff_std_ctr'] = np.where(small_segment_mask, global_std_ctr, stats_df['std_ctr'])
        stats_df['eff_mean_clicks'] = np.where(small_segment_mask, global_mean_clicks, stats_df['mean_clicks'])
        stats_df['eff_std_clicks'] = np.where(small_segment_mask, global_std_clicks, stats_df['std_clicks'])

        z_ctr = (stats_df['Calculated_CTR'] - stats_df['eff_mean_ctr']) / (stats_df['eff_std_ctr'] + 1e-9)

        type_a_candidates = stats_df[
            (stats_df['Impressions'] > self.bleeder_type_a_impressions_threshold)
            & (z_ctr < self.bleeder_type_a_z_threshold)
        ].copy()
        if self.confidence_enable and not type_a_candidates.empty:
            z_value = self._z_score_for_confidence(self.type_a_confidence_level)
            ctr_upper_bound = self._wilson_upper_bound(stats_df['Clicks'], stats_df['Impressions'], z_value)
            type_a_candidates = type_a_candidates[
                ctr_upper_bound.loc[type_a_candidates.index] < stats_df.loc[type_a_candidates.index, 'eff_mean_ctr']
            ]
        type_a_mask = (mask) & (self.df.index.isin(type_a_candidates.index))

        click_threshold = (
            stats_df['eff_mean_clicks']
            + (self.bleeder_type_b_clicks_std_multiplier * stats_df['eff_std_clicks'].fillna(0))
        )
        type_b_candidates = stats_df[
            (stats_df['Clicks'] > click_threshold)
            & (stats_df['Sales'] == 0)
        ].copy()
        if self.confidence_enable and not type_b_candidates.empty:
            min_clicks = max(3, self.optimization_min_clicks)
            type_b_candidates = type_b_candidates[
                (type_b_candidates['Spend'] >= self.type_b_min_spend)
                & (type_b_candidates['Clicks'] >= min_clicks)
            ]
        type_b_mask = (mask) & (self.df.index.isin(type_b_candidates.index))

        # Type C: Low volume terms (configurable mode)
        positive_impressions = stats_df[stats_df['Impressions'] > 0]['Impressions']
        if positive_impressions.empty:
            type_c_mask = mask & False
            type_c_threshold_desc = "n/a"
        elif self.bleeder_type_c_mode == "fixed":
            type_c_mask = (
                (mask)
                & (self.df['Impressions'] < self.bleeder_type_c_impressions_threshold)
                & (self.df['Impressions'] > 0)
            )
            type_c_threshold_desc = f"impressions < {self.bleeder_type_c_impressions_threshold}"
        elif self.bleeder_type_c_mode == "percentile":
            threshold_value = positive_impressions.quantile(self.bleeder_type_c_percentile)
            type_c_mask = (
                (mask)
                & (self.df['Impressions'] <= threshold_value)
                & (self.df['Impressions'] > 0)
            )
            pct = int(self.bleeder_type_c_percentile * 100)
            type_c_threshold_desc = f"impressions <= p{pct} ({threshold_value:.1f})"
        else:
            log_impressions = np.log1p(positive_impressions)
            mean_log_imp = log_impressions.mean()
            std_log_imp = log_impressions.std()
            if std_log_imp <= 0:
                z_log_imp = pd.Series(0, index=stats_df.index)
            else:
                z_log_imp = (np.log1p(stats_df['Impressions']) - mean_log_imp) / std_log_imp
            type_c_mask = (
                (mask)
                & (self.df['Impressions'] > 0)
                & (self.df.index.isin(stats_df[z_log_imp < self.bleeder_type_c_z_threshold].index))
            )
            type_c_threshold_desc = f"log-impression z < {self.bleeder_type_c_z_threshold:.2f}"

        # Apply changes
        type_a_count = int(type_a_mask.sum())
        type_b_count = int(type_b_mask.sum())
        type_c_count = int(type_c_mask.sum())

        # Apply Type A (Aggressive reduction)
        self.df.loc[type_a_mask, 'Bid'] = self.min_bid
        self.df.loc[type_a_mask, 'Operation'] = 'Update'
        self.df.loc[type_a_mask, 'Bleeder_Type'] = self.TYPE_A_LABEL

        # Apply Type B (Lower to scouting level)
        self.df.loc[type_b_mask, 'Bid'] = self.min_bid
        self.df.loc[type_b_mask, 'Operation'] = 'Update'
        self.df.loc[type_b_mask, 'Bleeder_Type'] = self.TYPE_B_LABEL

        # Apply Type C (Flag only, no bid change)
        self.df.loc[type_c_mask, 'Bleeder_Type'] = self.TYPE_C_LABEL

        # Cold-start lifecycle: step-up low-volume terms, and flag stalled no-click terms for review.
        cold_start_mask = (
            type_c_mask
            & (self.df['Clicks'] == 0)
            & (self.df['Sales'] == 0)
            & (~type_a_mask)
            & (~type_b_mask)
        )
        stalled_mask = cold_start_mask & (self.df['Impressions'] >= self.cold_start_stalled_impressions)
        cold_start_eligible_mask = cold_start_mask & (~stalled_mask)
        cold_start_count = int(cold_start_eligible_mask.sum())
        stalled_count = int(stalled_mask.sum())

        if self.cold_start_enable and cold_start_count > 0:
            if self.cold_start_mode == "ladder":
                threshold = max(float(self.bleeder_type_c_impressions_threshold), 1.0)
                impressions = self.df.loc[cold_start_eligible_mask, 'Impressions'].clip(lower=0).astype(float)
                ratio = impressions / threshold
                multipliers = np.select(
                    [ratio <= 0.25, ratio <= 0.50, ratio <= 0.75],
                    [2.0, 1.5, 1.25],
                    default=1.0,
                )
                increments = np.minimum(self.cold_start_step_up_amount * multipliers, self.cold_start_ladder_cap)
                self.df.loc[cold_start_eligible_mask, 'Bid'] = np.clip(
                    self.df.loc[cold_start_eligible_mask, 'Bid'] + increments,
                    self.min_bid,
                    self.max_bid,
                )
                self.df.loc[cold_start_eligible_mask, 'Cold_Start_Action'] = (
                    "Ladder step-up (+" + pd.Series(increments, index=impressions.index).round(2).astype(str) + ")"
                )
            else:
                self.df.loc[cold_start_eligible_mask, 'Bid'] = np.clip(
                    self.df.loc[cold_start_eligible_mask, 'Bid'] + self.cold_start_step_up_amount,
                    self.min_bid,
                    self.max_bid,
                )
                self.df.loc[cold_start_eligible_mask, 'Cold_Start_Action'] = (
                    f"Fixed step-up (+{self.cold_start_step_up_amount:.2f})"
                )
            self.df.loc[cold_start_eligible_mask, 'Operation'] = 'Update'

        if stalled_count > 0:
            self.df.loc[stalled_mask, 'Cold_Start_Action'] = "Stalled no-click term: review negate/pause"

        # Log results
        self._log(f"Bleeder detection complete:")
        self._log(
            f"  - Segmentation mode: {self.bleeder_segmentation_mode} "
            f"(fallback if segment size < {self.segmentation_min_entities})"
        )
        if self.confidence_enable:
            self._log(
                f"  - Confidence gating: enabled (Type A CI={self.type_a_confidence_level:.2f}, "
                f"Type B min spend=${self.type_b_min_spend:.2f})"
            )
        else:
            self._log("  - Confidence gating: disabled")
        if type_a_count > 0:
            self._log(f"  - {self.TYPE_A_LABEL}: {type_a_count} keywords reduced to ${self.min_bid}")
        if type_b_count > 0:
            self._log(f"  - {self.TYPE_B_LABEL}: {type_b_count} keywords reduced to ${self.min_bid}")
        if type_c_count > 0:
            self._log(f"  - {self.TYPE_C_LABEL}: {type_c_count} keywords flagged for testing ({type_c_threshold_desc})")
        if self.cold_start_enable and cold_start_count > 0:
            self._log(
                f"  - Cold-start step-up ({self.cold_start_mode}): {cold_start_count} low-volume zero-click terms adjusted"
            )
        if stalled_count > 0:
            self._log(f"  - Cold-start stalled terms: {stalled_count} flagged for negate/pause review")

        if type_a_count + type_b_count + type_c_count == 0:
            self._log("  - No bleeders detected")

        return {
            'type_a': type_a_count,
            'type_b': type_b_count,
            'type_c': type_c_count,
            'cold_start_stepups': cold_start_count if self.cold_start_enable else 0,
            'cold_start_stalled': stalled_count,
            'total': type_a_count + type_b_count + type_c_count
        }

    def validate_output(self):
        """
        Validates that the output file maintains data integrity.
        Returns: (is_valid, error_message)
        """
        self._log("Validating output file integrity...")

        # Check that all original sheets are preserved
        if set(self.original_sheets.keys()) != set(self.sheet_names):
            missing = set(self.sheet_names) - set(self.original_sheets.keys())
            return False, f"Missing sheets: {missing}"

        # Check that critical columns are preserved
        # Note: Different bulk file versions may have different ID column names
        sp_sheet = self.original_sheets['Sponsored Products Campaigns']

        # Check for essential columns (flexible based on what exists in the file)
        essential_cols = ['Entity', 'Bid']  # These are truly required

        # Check for at least one ID column to ensure we can identify rows
        id_cols = ['Record ID', 'Campaign ID', 'Ad Group ID', 'Keyword ID', 'Product Targeting ID']
        has_id_col = any(col in sp_sheet.columns for col in id_cols)

        missing_essential = [col for col in essential_cols if col not in sp_sheet.columns]

        if missing_essential:
            return False, f"Missing essential columns in output: {missing_essential}"

        if not has_id_col:
            return False, "No ID columns found in output (need at least one of: Record ID, Campaign ID, Keyword ID)"

        # Check that the number of rows hasn't changed dramatically (data loss check)
        if len(sp_sheet) == 0:
            return False, "Output file has no data rows"

        self._log("Output validation passed")
        return True, None

    def generate_test_more_report(self):
        """
        Generates a report of low-visibility terms that need more testing.
        Returns: DataFrame with low-impression keywords
        """
        if self.df is None:
            return pd.DataFrame()

        type_c_keywords = self.df[
            (self.df['Bleeder_Type'] == self.TYPE_C_LABEL)
        ].copy()

        if not type_c_keywords.empty:
            # Select relevant columns for the report
            report_cols = [
                'Campaign Name', 'Ad Group Name', 'Keyword or Product Targeting',
                'Match Type', 'Impressions', 'Clicks', 'Spend', 'Sales', 'Bid'
            ]
            # Only include columns that exist
            available_cols = [col for col in report_cols if col in type_c_keywords.columns]
            type_c_keywords = type_c_keywords[available_cols]

        self._log(f"Generated Test More report with {len(type_c_keywords)} low-visibility keywords")
        return type_c_keywords

    def save_optimized_file(
        self,
        output_path,
        include_analysis_sheets=True,
        amazon_upload_ready=False,
        amazon_updates_only=True,
        cannibalization_report=None,
        budget_report=None,
    ):
        """
        Saves the dataframes back to an Excel file with timestamp.

        Parameters:
        - output_path: Path to save file (string) or BytesIO object
        - include_analysis_sheets: Include Test More, Cannibalization, Budget reports (default True)
        - amazon_upload_ready: If True, only save sheets Amazon recognizes (default False)
        - amazon_updates_only: If True with amazon_upload_ready, keep only rows with non-empty Operation
        - cannibalization_report: Optional precomputed cannibalization DataFrame
        - budget_report: Optional precomputed budget recommendation DataFrame

        If output_path is a string, adds timestamp to filename.
        If output_path is BytesIO, writes directly.
        """
        self._log("Preparing to save optimized file...")

        # Validate before saving
        is_valid, error_msg = self.validate_output()
        if not is_valid:
            self._log(f"ERROR: Validation failed: {error_msg}", level='error')
            raise ValueError(f"Output validation failed: {error_msg}")

        # Update the main dataframe in the dictionary
        self.original_sheets['Sponsored Products Campaigns'] = self.df

        # Add timestamp to filename if it's a string path
        if isinstance(output_path, str):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Insert timestamp before file extension
            if output_path.endswith('.xlsx'):
                output_path = output_path.replace('.xlsx', f'_{timestamp}.xlsx')
            else:
                output_path = f"{output_path}_{timestamp}.xlsx"
            self._log(f"Saving to: {output_path}")

        # Amazon-recognized sheet names (based on common bulk file structure)
        amazon_sheets = [
            'Portfolios',
            'Sponsored Products Campaigns',
            'Sponsored Brands Campaigns',
            'SB Multi Ad Group Campaigns',
            'Sponsored Display Campaigns'
        ]

        with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
            written_sheets = 0
            # Save sheets
            for sheet_name, data in self.original_sheets.items():
                # If amazon_upload_ready mode, only save Amazon-recognized sheets
                if amazon_upload_ready:
                    if sheet_name in amazon_sheets:
                        data_to_save = data.copy()
                        if 'Operation' in data_to_save.columns:
                            cleaned_op = (
                                data_to_save['Operation']
                                .fillna('')
                                .astype(str)
                                .str.strip()
                                .replace(['nan', 'NaN', 'None', 'none'], '')
                            )
                            data_to_save['Operation'] = cleaned_op
                            if amazon_updates_only:
                                data_to_save = data_to_save[cleaned_op != '']
                                if data_to_save.empty and sheet_name != 'Sponsored Products Campaigns':
                                    continue
                        elif amazon_updates_only:
                            # Keep only the primary Sponsored Products sheet (headers only if no operation column).
                            if sheet_name != 'Sponsored Products Campaigns':
                                continue
                            data_to_save = data_to_save.iloc[0:0]

                        data_to_save.to_excel(writer, sheet_name=sheet_name, index=False)
                        written_sheets += 1
                        self._log(
                            f"Saved '{sheet_name}' sheet (Amazon-compatible, {len(data_to_save)} rows)"
                        )
                else:
                    # Also clean Operation column for non-Amazon sheets
                    data_to_save = data.copy()
                    if 'Operation' in data_to_save.columns:
                        data_to_save['Operation'] = data_to_save['Operation'].fillna('')
                    data_to_save.to_excel(writer, sheet_name=sheet_name, index=False)
                    written_sheets += 1

            # Add analysis sheets only if requested and not in Amazon upload mode
            if include_analysis_sheets and not amazon_upload_ready:
                # Add Test More report if there are Type C keywords
                test_more_report = self.generate_test_more_report()
                if not test_more_report.empty:
                    test_more_report.to_excel(writer, sheet_name='Test More Report', index=False)
                    self._log(f"Added 'Test More Report' sheet with {len(test_more_report)} ghost keywords")

                # Add Cannibalization Report if duplicates exist
                local_cannibalization = (
                    cannibalization_report if cannibalization_report is not None else self.detect_cannibalization()
                )
                if not local_cannibalization.empty:
                    local_cannibalization.to_excel(writer, sheet_name='Cannibalization Report', index=False)
                    self._log(f"Added 'Cannibalization Report' sheet with {len(local_cannibalization)} duplicate keywords")

                # Add Budget Optimization Report
                local_budget_report = budget_report if budget_report is not None else self.optimize_budgets()
                if not local_budget_report.empty:
                    local_budget_report.to_excel(writer, sheet_name='Budget Recommendations', index=False)
                    self._log(f"Added 'Budget Recommendations' sheet with {len(local_budget_report)} campaigns analyzed")

        if amazon_upload_ready:
            if amazon_updates_only:
                self._log(
                    f"File saved in Amazon upload-ready format (updated entries only across {written_sheets} sheet(s))"
                )
            else:
                self._log("File saved in Amazon upload-ready format (only Amazon-recognized sheets)")
        else:
            self._log("File saved with all sheets including analysis reports")

        # Return the output path for reference
        return output_path

    def generate_markdown_report(
        self,
        include_nlp=True,
        cannibalization=None,
        budget_recs=None,
        product_results=None,
        cluster_results=None,
    ):
        """
        Generates a comprehensive markdown report with all optimization results.
        Optional precomputed analysis objects can be provided to avoid recomputation.
        Returns: String containing formatted markdown
        """
        self._log("Generating markdown report...")

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        report = f"""# Amazon PPC Optimization Report

**Generated**: {timestamp}
**File**: {self.filename}
**Target ACOS**: {self.target_acos * 100:.1f}%

---

## 📊 Optimization Summary

### Core Bid Optimization (RPC Method)

"""
        # Count bid changes
        if self.df is not None and 'Operation' in self.df.columns:
            bid_updates = (self.df['Operation'] == 'Update').sum()
            report += f"- **Total Bid Updates**: {bid_updates} keywords/targets\n"

        # Add bleeder summary
        report += "\n### Bleeder Detection (Z-Score Analysis)\n\n"
        if 'Bleeder_Type' in self.df.columns:
            bleeder_counts = self.df['Bleeder_Type'].value_counts()
            for btype, count in bleeder_counts.items():
                if btype:
                    report += f"- **{btype}**: {count}\n"

        # Add Phase 2 analysis
        report += "\n---\n\n## 🏗️ Structural Analysis\n\n"

        # Cannibalization
        cannibalization = cannibalization if cannibalization is not None else self.detect_cannibalization()
        if not cannibalization.empty:
            report += f"### ⚠️ Cannibalization Issues ({len(cannibalization)} found)\n\n"
            report += "Keywords appearing in multiple ad groups (causing internal competition):\n\n"
            report += "| Keyword | Ad Groups | Total Spend | ACOS | Severity |\n"
            report += "|---------|-----------|-------------|------|----------|\n"

            for _, row in cannibalization.head(10).iterrows():
                keyword = str(row.get('Normalized_Keyword', 'N/A'))[:40]
                ad_groups = row.get('Ad_Group_Count', 'N/A')
                spend = row.get('Total_Spend', 0)
                acos = row.get('ACOS', 0)
                severity = row.get('Severity_Score', 0)
                report += f"| {keyword} | {ad_groups} | ${spend:.2f} | {acos:.2f} | {severity:.2f} |\n"

            if len(cannibalization) > 10:
                report += f"\n*...and {len(cannibalization) - 10} more. See full Excel report for details.*\n"
        else:
            report += "### ✅ No Cannibalization Issues\n\nYour account structure is optimal - no duplicate keywords found across ad groups.\n"

        # Budget optimization
        budget_recs = budget_recs if budget_recs is not None else self.optimize_budgets()
        if not budget_recs.empty:
            report += f"\n### 💰 Budget Optimization ({len(budget_recs)} campaigns)\n\n"

            if 'Category' in budget_recs.columns:
                category_counts = budget_recs['Category'].value_counts()
                report += "**Campaign Performance Breakdown:**\n\n"
                for category, count in category_counts.items():
                    report += f"- **{category}**: {count} campaigns\n"

            report += "\n**Top 5 Performers (Scale These):**\n\n"
            report += "| Campaign | ROAS | ACOS | Spend | Sales | Action |\n"
            report += "|----------|------|------|-------|-------|--------|\n"

            top_cols = ['Campaign Name', 'ROAS', 'ACOS', 'Spend', 'Sales', 'Recommendation']
            available_cols = [col for col in top_cols if col in budget_recs.columns]

            for _, row in budget_recs.head(5).iterrows():
                campaign = str(row.get('Campaign Name', 'N/A'))[:30]
                roas = row.get('ROAS', 0)
                acos = row.get('ACOS', 0)
                spend = row.get('Spend', 0)
                sales = row.get('Sales', 0)
                rec = str(row.get('Recommendation', 'N/A'))[:40]
                report += f"| {campaign} | {roas:.2f}x | {acos:.2f} | ${spend:.2f} | ${sales:.2f} | {rec} |\n"

            report += "\n**Bottom 5 Performers (Reduce These):**\n\n"
            report += "| Campaign | ROAS | ACOS | Spend | Sales | Action |\n"
            report += "|----------|------|------|-------|-------|--------|\n"

            for _, row in budget_recs.tail(5).iterrows():
                campaign = str(row.get('Campaign Name', 'N/A'))[:30]
                roas = row.get('ROAS', 0)
                acos = row.get('ACOS', 0)
                spend = row.get('Spend', 0)
                sales = row.get('Sales', 0)
                rec = str(row.get('Recommendation', 'N/A'))[:40]
                report += f"| {campaign} | {roas:.2f}x | {acos:.2f} | ${spend:.2f} | ${sales:.2f} | {rec} |\n"

        if include_nlp:
            # Add Phase 3 analysis (NLP)
            report += "\n---\n\n## 🤖 NLP Analysis (Phase 3)\n\n"

            # Product Target Analysis
            try:
                product_results = product_results if product_results is not None else self.analyze_product_targets()
                bleeder_counts = product_results.get('bleeder_counts', {})
                negative_recs = product_results.get('negative_recommendations', pd.DataFrame())
                savings = product_results.get('savings_estimate', 0)

                report += "### 🎯 Product Target Analysis\n\n"
                report += "**Bleeder Breakdown:**\n\n"
                report += f"- **Type A (Low CTR)**: {bleeder_counts.get('type_a', 0)} ASINs - Getting impressions but few clicks\n"
                report += f"- **Type B (Non-Converting)**: {bleeder_counts.get('type_b', 0)} ASINs - Getting clicks but zero sales [PRIORITY]\n"
                report += f"- **Type C (High ACOS)**: {bleeder_counts.get('type_c', 0)} ASINs - High spend relative to sales\n"
                report += f"- **Type D (Insufficient Data)**: {bleeder_counts.get('type_d', 0)} ASINs - Need more data\n"

                if not negative_recs.empty:
                    report += f"\n**💰 Estimated Monthly Savings**: ${savings:,.2f}\n"
                    report += f"\n**Top Wasteful Product Targets (Type B - Recommend Negative Targeting):**\n\n"
                    report += "| ASIN | Clicks | Spend | Sales | Conv Rate | Severity |\n"
                    report += "|------|--------|-------|-------|-----------|----------|\n"

                    for _, row in negative_recs.head(10).iterrows():
                        asin = str(row.get('Customer Search Term', 'N/A'))[:15]
                        clicks = row.get('Clicks', 0)
                        spend = row.get('Spend', 0)
                        sales = row.get('Sales', 0)
                        cvr = row.get('Conversion Rate', 0)
                        severity = row.get('Severity_Score', 0)
                        report += f"| {asin} | {clicks} | ${spend:.2f} | ${sales:.2f} | {cvr:.2%} | {severity:.2f} |\n"

                    if len(negative_recs) > 10:
                        report += f"\n*...and {len(negative_recs) - 10} more. Download 'Negative Product Targets' file to upload to Amazon.*\n"
                else:
                    report += "\n✅ No wasteful product targets found - all ASINs performing well!\n"

            except Exception:
                report += "Product target analysis skipped (no data available)\n"

            # Search Term Clustering
            try:
                cluster_results = cluster_results if cluster_results is not None else self.cluster_search_terms()
                n_clusters = cluster_results.get('n_clusters', 0)
                cluster_summary = cluster_results.get('cluster_summary', pd.DataFrame())

                if n_clusters > 0 and not cluster_summary.empty:
                    report += f"\n### 🔍 Search Term Intent Clustering\n\n"
                    report += f"**{n_clusters} Intent Clusters Identified** using NLP embeddings\n\n"

                    # Performance by category
                    if 'Performance_Category' in cluster_summary.columns:
                        perf_counts = cluster_summary['Performance_Category'].value_counts()
                        report += "**Performance Distribution:**\n\n"
                        for category, count in perf_counts.items():
                            report += f"- **{category}**: {count} clusters\n"

                    report += "\n**Top Intent Clusters by Spend:**\n\n"
                    report += "| Representative Terms | Terms | Spend | ROAS | ACOS | Performance |\n"
                    report += "|----------------------|-------|-------|------|------|-------------|\n"

                    for _, row in cluster_summary.head(5).iterrows():
                        terms = str(row.get('Representative_Terms', 'N/A'))[:40]
                        term_count = row.get('Term_Count', 0)
                        spend = row.get('Spend', 0)
                        roas = row.get('ROAS', 0)
                        acos = row.get('ACOS', 0)
                        category = str(row.get('Performance_Category', 'N/A'))[:20]
                        report += f"| {terms} | {term_count} | ${spend:.2f} | {roas:.2f}x | {acos:.2f} | {category} |\n"

                    # Insights
                    high_perf = cluster_summary[cluster_summary['Performance_Category'] == 'High-Performing Intent']
                    low_perf = cluster_summary[cluster_summary['Performance_Category'] == 'Low-Performing Intent']

                    if not high_perf.empty:
                        report += f"\n**✅ {len(high_perf)} High-Performing Intent Clusters** - Consider scaling these search term themes!\n"
                    if not low_perf.empty:
                        report += f"\n**⚠️ {len(low_perf)} Low-Performing Intent Clusters** - Consider adding these terms to negative keywords\n"
                else:
                    report += f"\n### 🔍 Search Term Intent Clustering\n\nInsufficient search term data for clustering analysis.\n"

            except Exception:
                report += "\nSearch term clustering skipped (no data available)\n"
        else:
            report += "\n---\n\n## 🤖 NLP Analysis (Phase 3)\n\nSkipped for this run.\n"

        # Add optimization log
        report += "\n---\n\n## 📋 Detailed Optimization Log\n\n```\n"
        report += self.get_optimization_log()
        report += "\n```\n"

        # Add next steps
        report += "\n---\n\n## 🚀 Next Steps\n\n"
        report += "1. **Upload Bid Changes**: Use the `amazon_upload_XXXXX.xlsx` file in Seller Central > Bulk Operations\n"
        if include_nlp:
            report += "2. **Upload Negative Product Targets**: Use the `negative_product_targets_XXXXX.xlsx` file to block wasteful ASINs\n"
            report += "3. **Upload Negative Keywords**: Use the `negative_keywords_XXXXX.xlsx` file to block wasteful search terms\n"
            report += "4. **Review Budgets**: Adjust campaign budgets based on recommendations above\n"
        else:
            report += "2. **Review Budgets**: Adjust campaign budgets based on recommendations above\n"

        if not cannibalization.empty:
            report += "5. **Fix Cannibalization**: Remove duplicate keywords from lower-performing ad groups\n"

        report += "\n### 📊 Expected Impact\n\n"
        report += "- **Bid Optimization**: Improved ROAS through RPC-based bid adjustments\n"
        report += "- **Negative Targeting**: Immediate reduction in wasted spend on non-converting traffic\n"
        report += "- **Budget Reallocation**: Increased profitability by scaling winners and cutting losers\n"
        report += "- **Structural Improvements**: Cleaner account structure with no internal competition\n"

        report += "\n---\n\n"
        report += "*Generated by Amazon PPC Bulk Optimizer v4.0 (Phase 3: NLP Intelligence)*\n"

        self._log("Markdown report generated")
        return report

    def detect_cannibalization(self):
        """
        Detects duplicate keywords/targets across different ad groups that may be
        competing against each other (cannibalization).

        Returns: DataFrame with cannibalization conflicts
        """
        self._log("Starting cannibalization detection...")

        if self.df is None:
            self._log("ERROR: No data loaded", level='error')
            return pd.DataFrame()

        # Filter for active keywords and product targets
        mask = self.df['Entity'].isin(['Keyword', 'Product Targeting'])
        active_items = self.df[mask].copy()

        if active_items.empty:
            self._log("No keywords or product targets found")
            return pd.DataFrame()

        # Identify the key column for matching (varies by entity type)
        # For keywords, we'll use the keyword text column
        # For product targeting, we'll use the ASIN/product identifier

        # Common column names for keywords in Amazon bulk files
        keyword_col_names = ['Keyword or Product Targeting', 'Keyword', 'Keyword Text', 'Customer Search Term']
        keyword_col = None
        for col in keyword_col_names:
            if col in active_items.columns:
                keyword_col = col
                break

        if not keyword_col:
            self._log("WARNING: Could not find keyword column for cannibalization check", level='warning')
            return pd.DataFrame()

        # Also need campaign and ad group info
        required_cols = ['Campaign Name', 'Ad Group Name', keyword_col]
        if not all(col in active_items.columns for col in required_cols):
            self._log("WARNING: Missing required columns for cannibalization check", level='warning')
            return pd.DataFrame()

        # Group by keyword to find duplicates across ad groups
        # Normalize keywords for comparison (lowercase, strip whitespace)
        active_items['Normalized_Keyword'] = active_items[keyword_col].astype(str).str.lower().str.strip()

        # Find keywords that appear in multiple ad groups
        keyword_groups = active_items.groupby('Normalized_Keyword').agg({
            'Ad Group Name': lambda x: list(x.unique()),
            'Campaign Name': lambda x: list(x.unique()),
            'Bid': ['mean', 'std', 'min', 'max'],
            'Impressions': 'sum',
            'Clicks': 'sum',
            'Spend': 'sum',
            'Sales': 'sum'
        })

        # Filter to keywords appearing in multiple ad groups
        keyword_groups['Ad_Group_Count'] = keyword_groups['Ad Group Name'].apply(len)
        duplicates = keyword_groups[keyword_groups['Ad_Group_Count'] > 1].copy()

        if duplicates.empty:
            self._log("No cannibalization detected - all keywords are unique to their ad groups")
            return pd.DataFrame()

        # Flatten the multi-index columns
        duplicates.columns = ['_'.join(col).strip('_') if isinstance(col, tuple) else col
                             for col in duplicates.columns]

        # Calculate metrics
        duplicates['Total_Spend'] = duplicates['Spend_sum']
        duplicates['Total_Sales'] = duplicates['Sales_sum']
        duplicates['ACOS'] = np.where(
            duplicates['Total_Sales'] > 0,
            (duplicates['Total_Spend'] / duplicates['Total_Sales']),
            np.inf
        )
        duplicates['Bid_Variance'] = duplicates['Bid_std']

        # Sort by severity (high spend + high variance = high priority)
        duplicates['Severity_Score'] = (
            duplicates['Total_Spend'] * duplicates['Bid_Variance'].fillna(0)
        )
        duplicates = duplicates.sort_values('Severity_Score', ascending=False)

        # Reset index to get keyword as column
        duplicates = duplicates.reset_index()

        self._log(f"Cannibalization detection complete: {len(duplicates)} keywords found in multiple ad groups")
        self._log(f"  - Total wasted spend (estimated): ${duplicates['Total_Spend'].sum():,.2f}")

        return duplicates

    def optimize_budgets(self):
        """
        Analyzes campaign performance and suggests budget reallocations.
        Note: Budget data may not be in the bulk file, so this provides
        recommendations based on ROAS analysis.

        Returns: DataFrame with budget recommendations
        """
        self._log("Starting budget optimization analysis...")

        if self.df is None:
            self._log("ERROR: No data loaded", level='error')
            return pd.DataFrame()

        # Check if budget column exists
        budget_col = None
        for col in ['Daily Budget', 'Budget', 'Campaign Daily Budget']:
            if col in self.df.columns:
                budget_col = col
                break

        # Group by campaign to calculate ROAS
        campaign_cols = ['Campaign Name', 'Campaign ID']
        available_campaign_cols = [col for col in campaign_cols if col in self.df.columns]

        if not available_campaign_cols:
            self._log("WARNING: No campaign columns found for budget optimization", level='warning')
            return pd.DataFrame()

        group_col = available_campaign_cols[0]

        # Aggregate by campaign
        campaign_performance = self.df.groupby(group_col).agg({
            'Impressions': 'sum',
            'Clicks': 'sum',
            'Spend': 'sum',
            'Sales': 'sum'
        }).reset_index()

        # Calculate ROAS
        campaign_performance['ROAS'] = np.where(
            campaign_performance['Spend'] > 0,
            campaign_performance['Sales'] / campaign_performance['Spend'],
            0
        )

        # Calculate ACOS
        campaign_performance['ACOS'] = np.where(
            campaign_performance['Sales'] > 0,
            campaign_performance['Spend'] / campaign_performance['Sales'],
            np.inf
        )

        # If budget column exists, include it
        if budget_col:
            budget_data = self.df.groupby(group_col)[budget_col].first()
            campaign_performance = campaign_performance.merge(
                budget_data.to_frame(),
                left_on=group_col,
                right_index=True,
                how='left'
            )
            campaign_performance['Budget_Utilization'] = np.where(
                campaign_performance[budget_col] > 0,
                (campaign_performance['Spend'] / campaign_performance[budget_col]) * 100,
                0
            )

        # Categorize campaigns
        target_roas = 1 / self.target_acos  # Convert ACOS to ROAS

        def categorize_campaign(row):
            if row['ROAS'] >= target_roas * 1.2:
                return 'Star Performer'
            elif row['ROAS'] >= target_roas:
                return 'Good Performer'
            elif row['ROAS'] >= target_roas * 0.8:
                return 'Needs Improvement'
            else:
                return 'Poor Performer'

        campaign_performance['Category'] = campaign_performance.apply(categorize_campaign, axis=1)

        # Generate recommendations
        def generate_recommendation(row):
            if row['Category'] == 'Star Performer':
                return 'INCREASE BUDGET: High ROAS - scale up aggressively (+50%)'
            elif row['Category'] == 'Good Performer':
                return 'INCREASE BUDGET: Meeting targets - scale up moderately (+20%)'
            elif row['Category'] == 'Needs Improvement':
                return 'OPTIMIZE: Below target - focus on bid optimization first'
            else:
                return 'DECREASE BUDGET: Poor ROAS - reduce spend or pause (-50%)'

        campaign_performance['Recommendation'] = campaign_performance.apply(generate_recommendation, axis=1)

        # Calculate suggested budget changes (if budget exists)
        if budget_col:
            def calculate_new_budget(row):
                current = row[budget_col]
                if pd.isna(current) or current == 0:
                    return current

                if row['Category'] == 'Star Performer':
                    return current * 1.5
                elif row['Category'] == 'Good Performer':
                    return current * 1.2
                elif row['Category'] == 'Needs Improvement':
                    return current  # No change
                else:
                    return current * 0.5

            campaign_performance['Suggested_Budget'] = campaign_performance.apply(calculate_new_budget, axis=1)
            campaign_performance['Budget_Change'] = (
                campaign_performance['Suggested_Budget'] - campaign_performance[budget_col]
            )
            campaign_performance['Budget_Change_Pct'] = np.where(
                campaign_performance[budget_col] > 0,
                (campaign_performance['Budget_Change'] / campaign_performance[budget_col]) * 100,
                0
            )

        # Sort by ROAS descending
        campaign_performance = campaign_performance.sort_values('ROAS', ascending=False)

        # Log summary
        star_count = (campaign_performance['Category'] == 'Star Performer').sum()
        poor_count = (campaign_performance['Category'] == 'Poor Performer').sum()

        self._log(f"Budget optimization analysis complete:")
        self._log(f"  - {star_count} star performers (consider increasing budget)")
        self._log(f"  - {poor_count} poor performers (consider decreasing budget)")

        if budget_col:
            total_current = campaign_performance[budget_col].sum()
            total_suggested = campaign_performance['Suggested_Budget'].sum()
            self._log(f"  - Current total budget: ${total_current:,.2f}")
            self._log(f"  - Suggested total budget: ${total_suggested:,.2f}")

        return campaign_performance

    def analyze_product_targets(self):
        """
        Analyze product targeting (ASIN) performance and identify wasteful spend.

        Uses statistical methods (Z-scores) to identify bleeders relative to account performance.

        Returns:
            dict with:
                - bleeder_counts: dict with Type A/B/C/D counts
                - negative_recommendations: DataFrame of ASINs to negate (Type B priority)
                - performance_analysis: DataFrame with all product targets and bleeder flags
                - savings_estimate: estimated monthly savings from blocking bleeders
        """
        self._log("Starting product target analysis (Phase 3)...")

        # Check if we have search term report sheets
        has_sp_search = 'SP Search Term Report' in self.original_sheets
        has_sb_search = 'SB Search Term Report' in self.original_sheets

        if not has_sp_search and not has_sb_search:
            self._log("No search term reports found - skipping product target analysis", level='warning')
            return {
                'bleeder_counts': {'type_a': 0, 'type_b': 0, 'type_c': 0, 'type_d': 0},
                'negative_recommendations': pd.DataFrame(),
                'performance_analysis': pd.DataFrame(),
                'savings_estimate': 0
            }

        # Combine SP and SB search term data
        search_term_data = []

        if has_sp_search:
            sp_df = self.original_sheets['SP Search Term Report'].copy()
            sp_df['Ad_Type'] = 'Sponsored Products'
            search_term_data.append(sp_df)
            self._log(f"Loaded SP Search Term Report: {len(sp_df)} rows")

        if has_sb_search:
            sb_df = self.original_sheets['SB Search Term Report'].copy()
            sb_df['Ad_Type'] = 'Sponsored Brands'
            search_term_data.append(sb_df)
            self._log(f"Loaded SB Search Term Report: {len(sb_df)} rows")

        df_search = pd.concat(search_term_data, ignore_index=True)
        self._log(f"Combined search term data: {len(df_search)} total rows")

        # Filter to product targets only (where Product Targeting ID is not null)
        product_target_mask = df_search['Product Targeting ID'].notna()
        df_products = df_search[product_target_mask].copy()
        auto_target_mask = self._is_auto_target_bucket(df_products['Product Targeting Expression'])
        df_products['Is_Auto_Target_Bucket'] = auto_target_mask

        if len(df_products) == 0:
            self._log("No product targeting data found - only keywords present")
            return {
                'bleeder_counts': {'type_a': 0, 'type_b': 0, 'type_c': 0, 'type_d': 0},
                'negative_recommendations': pd.DataFrame(),
                'performance_analysis': pd.DataFrame(),
                'savings_estimate': 0
            }

        self._log(f"Analyzing {len(df_products)} product targets (ASINs)")

        # Ensure numeric columns
        numeric_cols = ['Impressions', 'Clicks', 'Spend', 'Sales', 'Click-through Rate', 'Conversion Rate', 'ACOS', 'ROAS', 'CPC']
        for col in numeric_cols:
            if col in df_products.columns:
                df_products[col] = pd.to_numeric(df_products[col], errors='coerce').fillna(0)

        # Separate by data maturity
        sufficient_data_mask = df_products['Clicks'] >= 10
        insufficient_data_mask = df_products['Impressions'] < 100

        # Calculate account-wide statistics (only on sufficient data)
        stats_df = df_products[sufficient_data_mask]

        if len(stats_df) == 0:
            self._log("Insufficient data for statistical analysis - all product targets have <10 clicks")
            # Still flag Type D (ghost ASINs)
            df_products['Bleeder_Type'] = ''
            df_products.loc[insufficient_data_mask, 'Bleeder_Type'] = 'Type D: Insufficient Data'

            return {
                'bleeder_counts': {'type_a': 0, 'type_b': 0, 'type_c': 0, 'type_d': insufficient_data_mask.sum()},
                'negative_recommendations': pd.DataFrame(),
                'performance_analysis': df_products,
                'savings_estimate': 0
            }

        # Calculate mean and standard deviation for Z-scores
        mean_ctr = stats_df['Click-through Rate'].mean()
        std_ctr = stats_df['Click-through Rate'].std()
        mean_cvr = stats_df['Conversion Rate'].mean()
        std_cvr = stats_df['Conversion Rate'].std()
        mean_acos = stats_df['ACOS'].mean()
        std_acos = stats_df['ACOS'].std()

        self._log(f"Account statistics (product targets with >=10 clicks, n={len(stats_df)}):")
        self._log(f"  - Mean CTR: {mean_ctr:.2%}, StdDev: {std_ctr:.2%}")
        self._log(f"  - Mean CVR: {mean_cvr:.2%}, StdDev: {std_cvr:.2%}")
        self._log(f"  - Mean ACOS: {mean_acos:.1%}, StdDev: {std_acos:.1%}")

        # Calculate Z-scores (handle division by zero)
        df_products['Z_CTR'] = np.where(
            std_ctr > 0,
            (df_products['Click-through Rate'] - mean_ctr) / std_ctr,
            0
        )
        df_products['Z_CVR'] = np.where(
            std_cvr > 0,
            (df_products['Conversion Rate'] - mean_cvr) / std_cvr,
            0
        )
        df_products['Z_ACOS'] = np.where(
            std_acos > 0,
            (df_products['ACOS'] - mean_acos) / std_acos,
            0
        )

        # Initialize bleeder type column
        df_products['Bleeder_Type'] = ''
        df_products['Severity_Score'] = 0.0

        # Type A: Low-Intent ASINs (Impression Bloaters)
        # Criteria: Impressions > 500 AND Z_CTR < -1.5 AND Clicks < 5
        type_a_mask = (
            (df_products['Impressions'] > 500) &
            (df_products['Z_CTR'] < -1.5) &
            (df_products['Clicks'] < 5)
        )
        df_products.loc[type_a_mask, 'Bleeder_Type'] = 'Type A: Low CTR'

        # Type B: Click Wasters (Non-Converting ASINs) - HIGHEST PRIORITY
        # Criteria: (Clicks >= 20 AND Sales == 0) OR (Clicks >= 10 AND Conversion Rate < 2%)
        type_b_mask = (
            ((df_products['Clicks'] >= 20) & (df_products['Sales'] == 0)) |
            ((df_products['Clicks'] >= 10) & (df_products['Conversion Rate'] < 0.02))
        )
        df_products.loc[type_b_mask, 'Bleeder_Type'] = 'Type B: Non-Converting'

        # Type C: High-Spend Underperformers
        # Criteria: (ACOS > 80% AND Impressions > 100) OR (ROAS < 0.5 AND Clicks > 10) OR (Z_CVR < -1.5 AND Clicks > 15)
        type_c_mask = (
            ((df_products['ACOS'] > 0.8) & (df_products['Impressions'] > 100)) |
            ((df_products['ROAS'] < 0.5) & (df_products['Clicks'] > 10)) |
            ((df_products['Z_CVR'] < -1.5) & (df_products['Clicks'] > 15))
        )
        df_products.loc[type_c_mask, 'Bleeder_Type'] = 'Type C: High ACOS'

        # Type D: Ghost ASINs (Insufficient Data)
        # Criteria: Impressions < 100
        df_products.loc[insufficient_data_mask, 'Bleeder_Type'] = 'Type D: Insufficient Data'

        # Calculate severity score (spend-weighted prioritization)
        # Higher score = more urgent to fix
        # Formula: Spend * (1 - ROAS) = actual wasted money
        df_products['Severity_Score'] = df_products['Spend'] * (1 - df_products['ROAS'].clip(lower=0))

        # Count bleeders by type
        bleeder_counts = {
            'type_a': (df_products['Bleeder_Type'] == 'Type A: Low CTR').sum(),
            'type_b': (df_products['Bleeder_Type'] == 'Type B: Non-Converting').sum(),
            'type_c': (df_products['Bleeder_Type'] == 'Type C: High ACOS').sum(),
            'type_d': (df_products['Bleeder_Type'] == 'Type D: Insufficient Data').sum()
        }

        self._log(f"Product target bleeder detection complete:")
        self._log(f"  - Type A (Low CTR): {bleeder_counts['type_a']} ASINs")
        self._log(f"  - Type B (Non-Converting): {bleeder_counts['type_b']} ASINs [PRIORITY]")
        self._log(f"  - Type C (High ACOS): {bleeder_counts['type_c']} ASINs")
        self._log(f"  - Type D (Insufficient Data): {bleeder_counts['type_d']} ASINs")

        # Generate negative recommendations (Type B only - most urgent)
        # Exclude auto-target buckets (close/loose/substitutes/complements), which are not valid negative product targets.
        negative_recs = df_products[
            (df_products['Bleeder_Type'] == 'Type B: Non-Converting') &
            (~df_products['Is_Auto_Target_Bucket'])
        ].copy()
        negative_recs = negative_recs.sort_values('Severity_Score', ascending=False)
        excluded_auto_recs = (
            (df_products['Bleeder_Type'] == 'Type B: Non-Converting') &
            (df_products['Is_Auto_Target_Bucket'])
        ).sum()

        # Estimate monthly savings from blocking Type B bleeders
        # Assuming current data is for ~60 days (based on typical bulk file date ranges)
        # Extrapolate to 30 days
        days_in_data = 60  # Conservative estimate
        type_b_spend = negative_recs['Spend'].sum()
        monthly_savings = (type_b_spend / days_in_data) * 30

        if len(negative_recs) > 0:
            self._log(f"Negative product target recommendations:")
            self._log(f"  - {len(negative_recs)} ASINs recommended for negative targeting")
            self._log(f"  - Total wasted spend: ${type_b_spend:,.2f}")
            self._log(f"  - Estimated monthly savings: ${monthly_savings:,.2f}")
        if excluded_auto_recs > 0:
            self._log(
                f"  - Excluded {excluded_auto_recs} auto-target bucket rows from negative product recommendations"
            )

        return {
            'bleeder_counts': bleeder_counts,
            'negative_recommendations': negative_recs,
            'performance_analysis': df_products,
            'savings_estimate': monthly_savings
        }

    def cluster_search_terms(self, n_clusters=None, min_cluster_size=5):
        """
        Cluster search terms by customer intent using NLP embeddings.

        Uses sentence-transformers embeddings when available, with TF-IDF fallback,
        and applies K-means clustering.
        Only analyzes TEXT search terms (not ASINs).

        Args:
            n_clusters: Number of clusters (if None, auto-determines optimal number)
            min_cluster_size: Minimum number of terms required for clustering

        Returns:
            dict with:
                - clusters: DataFrame with search terms, cluster assignments, and performance
                - cluster_summary: DataFrame with performance metrics by cluster
                - n_clusters: Number of clusters created
        """
        self._log("Starting search term intent clustering (Phase 3 - NLP)...")

        # Check if we have search term report sheets
        has_sp_search = 'SP Search Term Report' in self.original_sheets
        has_sb_search = 'SB Search Term Report' in self.original_sheets

        if not has_sp_search and not has_sb_search:
            self._log("No search term reports found - skipping clustering", level='warning')
            return {
                'clusters': pd.DataFrame(),
                'cluster_summary': pd.DataFrame(),
                'n_clusters': 0
            }

        # Combine SP and SB search term data
        search_term_data = []

        if has_sp_search:
            sp_df = self.original_sheets['SP Search Term Report'].copy()
            sp_df['Ad_Type'] = 'Sponsored Products'
            search_term_data.append(sp_df)

        if has_sb_search:
            sb_df = self.original_sheets['SB Search Term Report'].copy()
            sb_df['Ad_Type'] = 'Sponsored Brands'
            search_term_data.append(sb_df)

        df_search = pd.concat(search_term_data, ignore_index=True)

        # Filter to TEXT search terms only (exclude ASINs)
        # ASINs are typically product IDs like "B06XTJ76X2" - all uppercase with numbers
        # Real search terms have lowercase letters and spaces
        text_search_mask = (
            df_search['Customer Search Term'].notna() &
            (df_search['Product Targeting ID'].isna()) &  # Not product targeting
            (df_search['Customer Search Term'].astype(str).str.contains(' |[a-z]', regex=True, na=False))  # Has spaces or lowercase
        )

        df_text_terms = df_search[text_search_mask].copy()

        if len(df_text_terms) < min_cluster_size:
            self._log(f"Insufficient text search terms for clustering (found {len(df_text_terms)}, need {min_cluster_size})")
            return {
                'clusters': pd.DataFrame(),
                'cluster_summary': pd.DataFrame(),
                'n_clusters': 0
            }

        self._log(f"Found {len(df_text_terms)} text search terms for NLP clustering")

        # Ensure numeric columns
        numeric_cols = ['Impressions', 'Clicks', 'Spend', 'Sales', 'ACOS', 'ROAS', 'Conversion Rate']
        for col in numeric_cols:
            if col in df_text_terms.columns:
                df_text_terms[col] = pd.to_numeric(df_text_terms[col], errors='coerce').fillna(0)

        # Get unique search terms with aggregated performance
        search_term_agg = df_text_terms.groupby('Customer Search Term').agg({
            'Impressions': 'sum',
            'Clicks': 'sum',
            'Spend': 'sum',
            'Sales': 'sum',
            'ACOS': 'mean',
            'ROAS': 'mean',
            'Conversion Rate': 'mean'
        }).reset_index()

        unique_terms = search_term_agg['Customer Search Term'].tolist()
        self._log(f"Analyzing {len(unique_terms)} unique search terms")

        # Generate embeddings (sentence-transformers when available, otherwise TF-IDF fallback)
        try:
            embeddings = self._generate_search_embeddings(unique_terms)
            self._log(f"Generated embeddings: shape {embeddings.shape}")
        except Exception as e:
            self._log(f"ERROR: Failed to generate embeddings: {e}", level='error')
            return {
                'clusters': pd.DataFrame(),
                'cluster_summary': pd.DataFrame(),
                'n_clusters': 0
            }

        # Determine optimal number of clusters if not specified
        if n_clusters is None:
            # Use rule of thumb: sqrt(n/2) for K-means
            n_clusters = max(3, min(10, int(np.sqrt(len(unique_terms) / 2))))
            self._log(f"Auto-determined optimal clusters: {n_clusters}")
        else:
            n_clusters = min(n_clusters, len(unique_terms) - 1)  # Can't have more clusters than data points
            self._log(f"Using specified number of clusters: {n_clusters}")

        # Apply K-means clustering
        try:
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(embeddings)

            # Calculate silhouette score (quality metric)
            if len(unique_terms) > n_clusters:
                silhouette = silhouette_score(embeddings, cluster_labels)
                self._log(f"Clustering quality (silhouette score): {silhouette:.3f} (higher is better, max 1.0)")
        except Exception as e:
            self._log(f"ERROR: Clustering failed: {e}", level='error')
            return {
                'clusters': pd.DataFrame(),
                'cluster_summary': pd.DataFrame(),
                'n_clusters': 0
            }

        # Add cluster labels to search term data
        search_term_agg['Cluster'] = cluster_labels

        # Generate cluster summary with performance metrics
        cluster_summary = search_term_agg.groupby('Cluster').agg({
            'Customer Search Term': 'count',  # Number of terms in cluster
            'Impressions': 'sum',
            'Clicks': 'sum',
            'Spend': 'sum',
            'Sales': 'sum',
            'ACOS': 'mean',
            'ROAS': 'mean',
            'Conversion Rate': 'mean'
        }).reset_index()

        cluster_summary.rename(columns={'Customer Search Term': 'Term_Count'}, inplace=True)

        # Calculate CTR for each cluster
        cluster_summary['CTR'] = np.where(
            cluster_summary['Impressions'] > 0,
            cluster_summary['Clicks'] / cluster_summary['Impressions'],
            0
        )

        # Add representative terms for each cluster (top 3 by spend)
        cluster_representatives = []
        for cluster_id in range(n_clusters):
            cluster_terms = search_term_agg[search_term_agg['Cluster'] == cluster_id]
            top_terms = cluster_terms.nlargest(3, 'Spend')['Customer Search Term'].tolist()
            cluster_representatives.append(', '.join(top_terms))

        cluster_summary['Representative_Terms'] = cluster_representatives

        # Sort by total spend (most important clusters first)
        cluster_summary = cluster_summary.sort_values('Spend', ascending=False)

        # Categorize clusters by performance
        target_roas = 1.0 / self.target_acos  # e.g., 30% ACOS = 3.33 ROAS

        def categorize_cluster(row):
            if row['ROAS'] >= target_roas * 1.2:
                return 'High-Performing Intent'
            elif row['ROAS'] >= target_roas * 0.8:
                return 'Average Intent'
            else:
                return 'Low-Performing Intent'

        cluster_summary['Performance_Category'] = cluster_summary.apply(categorize_cluster, axis=1)

        # Log summary
        high_perf = (cluster_summary['Performance_Category'] == 'High-Performing Intent').sum()
        low_perf = (cluster_summary['Performance_Category'] == 'Low-Performing Intent').sum()

        self._log(f"Search term clustering complete:")
        self._log(f"  - {n_clusters} intent clusters identified")
        self._log(f"  - {high_perf} high-performing intents (scale these!)")
        self._log(f"  - {low_perf} low-performing intents (consider negating)")

        return {
            'clusters': search_term_agg,
            'cluster_summary': cluster_summary,
            'n_clusters': n_clusters
        }

    def export_negative_product_targets_bulk_file(self, recommendations_df, output_buffer, match_type='Negative Exact'):
        """
        Export negative product targeting recommendations in Amazon bulk upload format.

        Args:
            recommendations_df: DataFrame from analyze_product_targets()['negative_recommendations']
            output_buffer: BytesIO buffer to write Excel file
            match_type: 'Negative Exact' or 'Negative Phrase' (default: Negative Exact)

        Returns:
            BytesIO buffer with Excel file ready for Amazon upload
        """
        if len(recommendations_df) == 0:
            self._log("No negative product target recommendations to export")
            # Return empty file
            empty_df = pd.DataFrame(columns=[
                'Product', 'Entity', 'Operation', 'Campaign ID', 'Ad Group ID',
                'Campaign Name (Informational only)', 'Ad Group Name (Informational only)',
                'Product Targeting Expression', 'Match Type'
            ])
            empty_df.to_excel(output_buffer, index=False, sheet_name='Negative Product Targets')
            return output_buffer

        auto_bucket_mask = self._is_auto_target_bucket(recommendations_df['Product Targeting Expression'])
        if auto_bucket_mask.any():
            excluded = int(auto_bucket_mask.sum())
            recommendations_df = recommendations_df[~auto_bucket_mask].copy()
            self._log(
                f"Excluded {excluded} auto-target bucket rows from negative product export"
            )

        if len(recommendations_df) == 0:
            self._log("No valid negative product target recommendations to export after filtering")
            empty_df = pd.DataFrame(columns=[
                'Product', 'Entity', 'Operation', 'Campaign ID', 'Ad Group ID',
                'Campaign Name (Informational only)', 'Ad Group Name (Informational only)',
                'Product Targeting Expression', 'Match Type'
            ])
            empty_df.to_excel(output_buffer, index=False, sheet_name='Negative Product Targets')
            return output_buffer

        self._log(f"Exporting {len(recommendations_df)} negative product targets for Amazon upload...")

        # Create DataFrame in Amazon bulk format
        negative_upload = pd.DataFrame()

        # Required columns for negative product targeting
        negative_upload['Product'] = recommendations_df['Ad_Type']
        negative_upload['Entity'] = 'Negative Product Targeting'
        negative_upload['Operation'] = 'Create'

        # Campaign and Ad Group identifiers
        negative_upload['Campaign ID'] = recommendations_df['Campaign ID']
        negative_upload['Ad Group ID'] = recommendations_df['Ad Group ID']
        negative_upload['Campaign Name (Informational only)'] = recommendations_df['Campaign Name (Informational only)']
        negative_upload['Ad Group Name (Informational only)'] = recommendations_df['Ad Group Name (Informational only)']

        # Product targeting expression (the ASIN to negate)
        negative_upload['Product Targeting Expression'] = recommendations_df['Product Targeting Expression']

        # Match type
        negative_upload['Match Type'] = match_type

        # Write to Excel
        with pd.ExcelWriter(output_buffer, engine='xlsxwriter') as writer:
            negative_upload.to_excel(writer, sheet_name='Negative Product Targets', index=False)

        self._log(f"Negative product targets export complete: {len(negative_upload)} rows")
        return output_buffer

    def export_negative_keywords_bulk_file(
        self,
        cluster_results,
        output_buffer,
        min_spend=10,
        max_acos=1.5,
        match_type='Negative Exact',
        require_low_intent_cluster=False,
    ):
        """
        Export negative keyword recommendations based on clustering analysis.

        Identifies low-performing search terms from clusters and formats for Amazon upload.

        Args:
            cluster_results: dict from cluster_search_terms()
            output_buffer: BytesIO buffer to write Excel file
            min_spend: Minimum spend to consider for negative keyword (default: $10)
            max_acos: Maximum ACOS threshold - terms above this are candidates (default: 150%)
            match_type: 'Negative Exact' or 'Negative Phrase' (default: Negative Exact)
            require_low_intent_cluster: If True, only terms from Low-Performing intent clusters are exported.

        Returns:
            BytesIO buffer with Excel file ready for Amazon upload
        """
        clusters_df = cluster_results.get('clusters', pd.DataFrame())

        if len(clusters_df) == 0:
            self._log("No search term clusters to analyze for negative keywords")
            # Return empty file
            empty_df = pd.DataFrame(columns=[
                'Product', 'Entity', 'Operation', 'Campaign ID', 'Ad Group ID',
                'Campaign Name', 'Ad Group Name',
                'Keyword Text', 'Match Type'
            ])
            empty_df.to_excel(output_buffer, index=False, sheet_name='Negative Keywords')
            return output_buffer

        # Identify wasteful search terms
        # Criteria: High spend + Poor performance (ACOS > threshold OR zero sales)
        negative_candidates = clusters_df[
            (clusters_df['Spend'] >= min_spend) &
            ((clusters_df['ACOS'] > max_acos) | (clusters_df['Sales'] == 0))
        ].copy()

        if require_low_intent_cluster:
            cluster_summary_df = cluster_results.get('cluster_summary', pd.DataFrame())
            if (
                not cluster_summary_df.empty
                and 'Cluster' in negative_candidates.columns
                and {'Cluster', 'Performance_Category'}.issubset(cluster_summary_df.columns)
            ):
                cluster_perf = cluster_summary_df[['Cluster', 'Performance_Category']].drop_duplicates('Cluster')
                negative_candidates = negative_candidates.merge(
                    cluster_perf,
                    on='Cluster',
                    how='left',
                )
                negative_candidates = negative_candidates[
                    negative_candidates['Performance_Category'] == 'Low-Performing Intent'
                ]
                self._log(
                    f"Filtered negative candidates to low-performing intent clusters: {len(negative_candidates)} terms remain"
                )
            else:
                self._log(
                    "Low-intent cluster filtering requested but cluster summary/labels unavailable; using term-level thresholds",
                    level='warning',
                )

        if len(negative_candidates) == 0:
            self._log("No search terms meet negative keyword criteria (all performing well!)")
            empty_df = pd.DataFrame(columns=[
                'Product', 'Entity', 'Operation', 'Campaign ID', 'Ad Group ID',
                'Campaign Name', 'Ad Group Name',
                'Keyword Text', 'Match Type'
            ])
            empty_df.to_excel(output_buffer, index=False, sheet_name='Negative Keywords')
            return output_buffer

        self._log(f"Identified {len(negative_candidates)} search terms for negative keyword recommendations")

        # Need to get campaign/ad group info from original search term reports
        # Merge with original data to get campaign details
        search_term_data = []
        if 'SP Search Term Report' in self.original_sheets:
            sp_df = self.original_sheets['SP Search Term Report'].copy()
            sp_df['Ad_Type'] = 'Sponsored Products'
            search_term_data.append(sp_df)

        if 'SB Search Term Report' in self.original_sheets:
            sb_df = self.original_sheets['SB Search Term Report'].copy()
            sb_df['Ad_Type'] = 'Sponsored Brands'
            search_term_data.append(sb_df)

        df_search = pd.concat(search_term_data, ignore_index=True)

        # Merge to get campaign/ad group details
        negative_with_details = negative_candidates.merge(
            df_search[
                [
                    'Customer Search Term',
                    'Campaign ID',
                    'Ad Group ID',
                    'Campaign Name (Informational only)',
                    'Ad Group Name (Informational only)',
                    'Ad_Type',
                ]
            ],
            left_on='Customer Search Term',
            right_on='Customer Search Term',
            how='left'
        )

        # Remove duplicates (same search term may appear in multiple ad groups)
        negative_with_details = negative_with_details.drop_duplicates(
            subset=['Customer Search Term', 'Campaign ID', 'Ad Group ID']
        )
        # Amazon requires parent IDs for create operations on negative keywords.
        negative_with_details = negative_with_details[
            negative_with_details['Campaign ID'].notna() & negative_with_details['Ad Group ID'].notna()
        ]
        if len(negative_with_details) == 0:
            self._log("No negative keywords with valid Campaign ID + Ad Group ID")
            empty_df = pd.DataFrame(columns=[
                'Product', 'Entity', 'Operation', 'Campaign ID', 'Ad Group ID',
                'Campaign Name', 'Ad Group Name', 'Keyword Text', 'Match Type'
            ])
            empty_df.to_excel(output_buffer, index=False, sheet_name='Negative Keywords')
            return output_buffer

        # Create DataFrame in Amazon bulk format
        negative_upload = pd.DataFrame()

        negative_upload['Product'] = negative_with_details['Ad_Type']
        negative_upload['Entity'] = 'Negative Keyword'
        negative_upload['Operation'] = 'Create'
        negative_upload['Campaign ID'] = negative_with_details['Campaign ID']
        negative_upload['Ad Group ID'] = negative_with_details['Ad Group ID']
        negative_upload['Campaign Name'] = negative_with_details['Campaign Name (Informational only)']
        negative_upload['Ad Group Name'] = negative_with_details['Ad Group Name (Informational only)']
        negative_upload['Keyword Text'] = negative_with_details['Customer Search Term']
        negative_upload['Match Type'] = match_type

        # Write to Excel
        with pd.ExcelWriter(output_buffer, engine='xlsxwriter') as writer:
            negative_upload.to_excel(writer, sheet_name='Negative Keywords', index=False)

        self._log(f"Negative keywords export complete: {len(negative_upload)} rows")
        return output_buffer
