"""Calendar quarters: labels like "2024Q3", their date ranges and midpoints."""
from datetime import date


def quarter_of(year: int, month: int) -> str:
    # Months 1-3 -> Q1, 4-6 -> Q2, ... ((month - 1) // 3 is 0..3)
    return f"{year}Q{(month - 1) // 3 + 1}"


def quarter_of_date(d: date) -> str:
    return quarter_of(d.year, d.month)


def quarter_labels(start_year: int, today: date) -> list[str]:
    """All quarters from start_year Q1 up to and including today's quarter."""
    current = quarter_of_date(today)
    labels = []
    for year in range(start_year, today.year + 1):
        for q in range(1, 5):
            label = f"{year}Q{q}"
            labels.append(label)
            if label == current:
                return labels
    return labels


def mid_quarter(label: str) -> date:
    """The 15th of the quarter's middle month: Feb 15, May 15, Aug 15 or Nov 15."""
    year, q = int(label[:4]), int(label[-1])
    return date(year, 3 * q - 1, 15)


def next_quarter(label: str) -> str:
    year, q = int(label[:4]), int(label[-1])
    return f"{year + 1}Q1" if q == 4 else f"{year}Q{q + 1}"
