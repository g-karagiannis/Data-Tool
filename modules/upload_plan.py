"""
Κανόνες της φόρτωσης αρχείων (Ρυθμίσεις φόρτωσης → κουμπί "Φόρτωση"): ποια αρχεία
περνούν από τις ρυθμίσεις, το συνολικό όριο μεγέθους, ποια αρχεία συνδυάζονται και
με ποια σειρά. Καμία εξάρτηση από Streamlit.
"""

MAX_TOTAL_UPLOAD_BYTES = 10 * 1024 * 1024
# .zip/.dat: φορτώνονται μόνο οι στήλες που διαλέγει ο χρήστης, άρα μένουν μικρά στη μνήμη
# όσο μεγάλο κι αν είναι το αρχείο· τα υπόλοιπα φορτώνονται ολόκληρα και μένουν στα 10MB.
MAX_LARGE_FILE_BYTES = 200 * 1024 * 1024
LARGE_FILE_EXTENSIONS = ("zip", "dat")
COMBINABLE_EXTENSIONS = ("csv", "xls", "xlsx", "zip", "dat")
ZIP_LOADABLE_EXTENSIONS = ("csv", "xls", "xlsx", "dat")   # τύποι που φορτώνονται από μέσα ένα zip


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower()


def size_limit(filename: str) -> int:
    """Μέγιστο μέγεθος ενός αρχείου: 200MB για .zip/.dat, 10MB για τα υπόλοιπα."""
    return MAX_LARGE_FILE_BYTES if _extension(filename) in LARGE_FILE_EXTENSIONS else MAX_TOTAL_UPLOAD_BYTES


def file_too_large(filename: str, n_bytes: int):
    """Μήνυμα αν το αρχείο ξεπερνά το όριό του, αλλιώς None. Ελέγχεται πριν διαβαστεί το αρχείο."""
    limit = size_limit(filename)
    if n_bytes <= limit:
        return None
    return (
        f"Το {filename} ({_megabytes(n_bytes)}) ξεπερνά το όριο των {_megabytes(limit)} για "
        f"αρχεία .{_extension(filename)}. Αφαίρεσέ το από το πλαίσιο ανεβάσματος."
    )


def is_combinable(filename: str) -> bool:
    """CSV/Excel/ZIP/DAT περνούν από τις ρυθμίσεις φόρτωσης (και μπορούν να συνδυαστούν)·
    PX/PDF/SQL φορτώνονται αμέσως."""
    return _extension(filename) in COMBINABLE_EXTENSIONS


def zip_choices(members: list):
    """members: [(όνομα, αποσυμπιεσμένο μέγεθος)] ενός zip. Επιστρέφει (όσα μπορούν να
    φορτωθούν, [(όνομα, λόγος)] όσων δεν μπορούν). Το όριο ισχύει για το ΑΠΟΣΥΜΠΙΕΣΜΕΝΟ
    μέγεθος, που ελέγχεται πριν αποσυμπιεστεί οτιδήποτε."""
    loadable, skipped = [], []
    for name, n_bytes in members:
        if _extension(name) not in ZIP_LOADABLE_EXTENSIONS:
            skipped.append((name, "τύπος που δεν φορτώνεται από zip"))
        elif n_bytes > size_limit(name):
            skipped.append((name, f"{_megabytes(n_bytes)} αποσυμπιεσμένο — όριο {_megabytes(size_limit(name))}"))
        else:
            loadable.append(name)
    return loadable, skipped


def codebook_candidates(members: list) -> list:
    """Τα PDF ενός zip που μπορούν να διαβαστούν ως codebook (μέσα στο όριο των 10MB αποσυμπιεσμένα)."""
    return [name for name, n_bytes in members if _extension(name) == "pdf" and n_bytes <= size_limit(name)]


def update_combine_order(order: list, ticked) -> list:
    """Η σειρά συνδυασμού είναι η σειρά με την οποία τικαρίστηκαν τα αρχεία: όσα
    παραμένουν τικαρισμένα κρατούν τη θέση τους, όσα ξετικαρίστηκαν φεύγουν, και τα
    νέα μπαίνουν στο τέλος."""
    ticked = list(ticked)
    kept = [f for f in order if f in ticked]
    return kept + [f for f in ticked if f not in kept]


def _megabytes(n_bytes: int) -> str:
    return f"{n_bytes / (1024 * 1024):.1f}MB"


def plan_load(file_sizes: dict, combine_order: list, combination_in_progress: bool = False,
              limit: int = MAX_TOTAL_UPLOAD_BYTES, not_ready: dict = None) -> dict:
    """
    file_sizes: {όνομα αρχείου: bytes} όσων περιμένουν φόρτωση. combine_order: τα
    τικαρισμένα, με τη σειρά των κλικ. Επιστρέφει {"total_bytes", "combine", "separate",
    "error"}: τα "combine" πάνε στον συνδυασμό (με αυτή τη σειρά), τα "separate" γίνονται
    ξεχωριστά datasets. Αν "error" δεν είναι None, δεν φορτώνεται τίποτα.
    not_ready: {αρχείο: λόγος} όσων οι ρυθμίσεις δεν επιτρέπουν ακόμα φόρτωση (π.χ. .dat με
    λάθος στον πίνακα θέσεων).
    """
    total = sum(file_sizes.values())
    combine = [f for f in combine_order if f in file_sizes]
    separate = [f for f in file_sizes if f not in combine]

    error = None
    if len(combine) == 1:
        error = "Τίκαρε τουλάχιστον 2 αρχεία για συνδυασμό ή κανένα."
    elif total > limit:
        error = (
            f"Το συνολικό μέγεθος των αρχείων ({_megabytes(total)}) ξεπερνά το όριο των "
            f"{_megabytes(limit)}. Αφαίρεσε αρχεία από το πλαίσιο ανεβάσματος."
        )
    elif combine and combination_in_progress:
        error = "Ολοκλήρωσε πρώτα τον συνδυασμό που είναι σε εξέλιξη."
    elif not_ready:
        fname, reason = next(iter(not_ready.items()))
        error = f"Το {fname} δεν είναι έτοιμο για φόρτωση: {reason}"
    return {"total_bytes": total, "combine": combine, "separate": separate, "error": error}
