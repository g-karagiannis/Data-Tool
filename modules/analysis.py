"""Στατιστική ανάλυση (Περιγραφικά στατιστικά)."""
import pandas as pd


def describe_numeric(df: pd.DataFrame) -> pd.DataFrame:
    return df.select_dtypes(include="number").describe().T


def describe_non_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Περιγραφικά στατιστικά μη αριθμητικών στηλών (text/κατηγορικές, datetime):
    count (μη-κενές τιμές), unique, top (πιο συχνή τιμή), freq (πλήθος της top).
    Εντελώς κενή στήλη -> unique/top/freq = None, χωρίς crash.
    """
    non_numeric = df.select_dtypes(exclude="number")
    rows, index = [], []
    for col in non_numeric.columns:
        s = non_numeric[col].dropna()
        index.append(col)
        if s.empty:
            rows.append({"count": 0, "unique": None, "top": None, "freq": None})
        else:
            vc = s.value_counts()
            rows.append({
                "count": int(s.shape[0]),
                "unique": int(s.nunique()),
                # str() εδώ γιατί η στήλη 'top' μπορεί να περιέχει ανομοιογενείς τύπους
                # (κείμενο ΚΑΙ ημερομηνίες) ανάμεσα σε διαφορετικές γραμμές — το Arrow
                # (backend του st.dataframe) δεν δέχεται μεικτούς τύπους στην ίδια στήλη.
                "top": str(vc.index[0]),
                "freq": int(vc.iloc[0]),
            })
    return pd.DataFrame(rows, index=index)
