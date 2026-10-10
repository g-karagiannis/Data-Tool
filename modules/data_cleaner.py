"""Επισκόπηση στηλών για το tab View (τύπος, κενές τιμές, Min/Max ανά στήλη)."""
import pandas as pd


def _text_min_max(series: pd.Series, df: pd.DataFrame, date_tie_col):
    """
    Custom Min/Max για text στήλες:
    Min = λιγότερο συχνή τιμή, Max = περισσότερο συχνή τιμή (null αγνοούνται).
    Tie-break: μέσω date_tie_col (παλαιότερη/πιο πρόσφατη ημερομηνία ανάμεσα στις
    ισοβαθμούσες τιμές) αν δοθεί, αλλιώς αλφαβητικά (πρώτη/τελευταία).
    """
    col = series.name
    vc = series.dropna().value_counts()
    if vc.empty:
        return None, None

    def resolve(candidates, want_oldest):
        if len(candidates) == 1:
            return candidates[0]
        if date_tie_col is not None:
            sub = df[df[col].isin(candidates)]
            dates = sub[date_tie_col]
            if dates.notna().any():
                idx = dates.idxmin() if want_oldest else dates.idxmax()
                return sub.loc[idx, col]
        ordered = sorted(candidates)
        return ordered[0] if want_oldest else ordered[-1]

    min_count, max_count = vc.min(), vc.max()
    min_candidates = vc[vc == min_count].index.tolist()
    max_candidates = vc[vc == max_count].index.tolist()
    return resolve(min_candidates, True), resolve(max_candidates, False)


def profile(df: pd.DataFrame, date_tie_col=None) -> pd.DataFrame:
    """
    Επισκόπηση στηλών (tab View): Στήλη, Τύπος, Κενές τιμές, Min, Max.
    Numeric -> πραγματικό min/max. Date/Datetime -> παλαιότερη/πιο πρόσφατη.
    Text -> λιγότερο/περισσότερο συχνή τιμή (βλ. _text_min_max για tie-break).
    date_tie_col: όνομα στήλης ημερομηνίας που θα χρησιμοποιηθεί για tie-break στις
    text στήλες, όταν υπάρχουν 2+ στήλες ημερομηνίας στο dataset (επιλογή χρήστη).
    """
    rows = []
    for col in df.columns:
        s = df[col]
        dtype = s.dtype
        non_null = s.dropna()
        if pd.api.types.is_datetime64_any_dtype(dtype):
            min_v = non_null.min() if not non_null.empty else None
            max_v = non_null.max() if not non_null.empty else None
        elif pd.api.types.is_numeric_dtype(dtype):
            min_v = non_null.min() if not non_null.empty else None
            max_v = non_null.max() if not non_null.empty else None
        else:
            min_v, max_v = _text_min_max(s, df, date_tie_col)
        rows.append({
            "Στήλη": col,
            "Τύπος": str(dtype),
            "Κενές τιμές": int(s.isna().sum()),
            # str() εδώ γιατί η στήλη Min/Max του πίνακα προφίλ περιέχει ανομοιογενείς τύπους
            # (αριθμούς, ημερομηνίες, κείμενο) ανά γραμμή — το Arrow (backend του st.dataframe)
            # δεν δέχεται μεικτούς τύπους στην ίδια στήλη.
            "Min": None if min_v is None else str(min_v),
            "Max": None if max_v is None else str(max_v),
        })
    return pd.DataFrame(rows)
