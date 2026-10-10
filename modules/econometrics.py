"""
Χρονοσειρές για το Workshop: Ιστορική Μεταβλητότητα και Κινητοί Μέσοι, υπολογισμένοι
πάντα με αύξουσα ημερομηνία, όποια σειρά κι αν έχουν οι γραμμές. Καθαρές συναρτήσεις
πάνω σε pandas Series — καμία εξάρτηση από Streamlit εδώ.
"""
import numpy as np
import pandas as pd


def _returns(prices: pd.Series, use_log_returns: bool = True) -> pd.Series:
    if (prices.dropna() <= 0).any():
        raise ValueError("Η στήλη τιμών περιέχει μηδενικές ή αρνητικές τιμές — δεν μπορεί να υπολογιστεί return/μεταβλητότητα.")
    if use_log_returns:
        return np.log(prices / prices.shift(1))
    return prices.pct_change()


def _date_ascending_index(dates: pd.Series) -> pd.Index:
    """
    Επιστρέφει τα index labels ταξινομημένα κατά ΑΥΞΟΥΣΑ ημερομηνία (σταθερή ταξινόμηση —
    ισόποσες/κενές ημερομηνίες κρατούν τη σχετική τους αρχική σειρά, οι κενές πάνε στο τέλος).
    Χρησιμοποιείται από όλα τα rolling/χρονοσειριακά εργαλεία ώστε να υπολογίζουν πάντα με
    βάση τη χρονολογική σειρά, ανεξάρτητα από τη σειρά των γραμμών στο αρχείο/table· η
    ευθυγράμμιση του αποτελέσματος πίσω στις αρχικές γραμμές γίνεται μέσω του pandas index
    (όχι μέσω θέσης).
    """
    return dates.sort_values(kind="stable").index


def historical_volatility(
    prices: pd.Series, dates: pd.Series, window: int, annualization_factor: int = 252, use_log_returns: bool = True
) -> pd.Series:
    """
    Κυλιόμενη (rolling) τυπική απόκλιση των returns σε παράθυρο `window` περιόδων,
    υπολογισμένη με τα δεδομένα ταξινομημένα κατά ΑΥΞΟΥΣΑ ημερομηνία (dates) — όχι κατά τη
    σειρά των γραμμών στο αρχείο/table. Το αποτέλεσμα επιστρέφεται ευθυγραμμισμένο στις ΙΔΙΕΣ
    γραμμές με το prices (μέσω index)· οι `window` χρονολογικά παλαιότερες γραμμές μένουν
    πάντα NaN, αφού δεν υπάρχει αρκετό ιστορικό γι' αυτές. Προσαρμοσμένη σε ετήσια βάση
    (× sqrt(annualization_factor))· annualization_factor=1 -> μη ετησιοποιημένη μεταβλητότητα.
    """
    if window < 2:
        raise ValueError("Το παράθυρο πρέπει να είναι τουλάχιστον 2 περίοδοι.")
    sort_index = _date_ascending_index(dates)
    sorted_prices = prices.loc[sort_index]
    returns = _returns(sorted_prices, use_log_returns)
    vol_sorted = returns.rolling(window=window).std() * np.sqrt(annualization_factor)
    result = pd.Series(np.nan, index=prices.index, dtype=float)
    result.loc[vol_sorted.index] = vol_sorted.values
    return result


def moving_average(series: pd.Series, dates: pd.Series, window: int, method: str = "SMA") -> pd.Series:
    """
    method: 'SMA' (απλός κυλιόμενος μέσος) ή 'EMA' (εκθετικός κυλιόμενος μέσος). Υπολογίζεται
    με τα δεδομένα ταξινομημένα κατά ΑΥΞΟΥΣΑ ημερομηνία (dates), και το αποτέλεσμα επιστρέφεται
    ευθυγραμμισμένο στις ΙΔΙΕΣ γραμμές με το series (μέσω index). Για SMA οι `window` χρονολογικά
    παλαιότερες γραμμές μένουν NaN (δεν υπάρχει αρκετό ιστορικό)· το EMA δεν χρειάζεται πλήρες
    παράθυρο για να ξεκινήσει, οπότε δεν αφήνει NaN.
    """
    if window < 1:
        raise ValueError("Το παράθυρο πρέπει να είναι τουλάχιστον 1 περίοδος.")
    sort_index = _date_ascending_index(dates)
    sorted_series = series.loc[sort_index]
    if method == "EMA":
        computed = sorted_series.ewm(span=window, adjust=False).mean()
    elif method == "SMA":
        computed = sorted_series.rolling(window=window).mean()
    else:
        raise ValueError(f"Άγνωστη μέθοδος κινητού μέσου: '{method}'.")
    result = pd.Series(np.nan, index=series.index, dtype=float)
    result.loc[computed.index] = computed.values
    return result
