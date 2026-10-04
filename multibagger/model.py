"""The normalised company record that every data source fills in.

Both sources (Screener.in company pages and Screener.in Excel exports) are
turned into a ``Company``. The engine only ever reads a ``Company``, so it
does not care where the numbers came from.

All money figures are in ₹ crore, as Screener shows them. Every yearly series
is a list aligned with ``years`` (oldest first). A missing value is ``None``.
"""

from dataclasses import dataclass, field
from typing import List, Optional

Series = List[Optional[float]]


@dataclass
class Company:
    name: str
    symbol: str = ""
    source: str = ""
    years: List[str] = field(default_factory=list)  # e.g. ["Mar 2016", ..., "Mar 2025"]

    # Snapshot
    price: float = 0.0  # current share price, ₹
    mcap: float = 0.0  # market capitalisation, ₹ crore
    face_value: Optional[float] = None
    pe_now: Optional[float] = None  # Screener's "Stock P/E" (TTM), if known

    # Profit & loss
    sales: Series = field(default_factory=list)
    op_profit: Series = field(default_factory=list)  # operating profit (EBITDA before other income)
    other_income: Series = field(default_factory=list)
    interest: Series = field(default_factory=list)
    dep: Series = field(default_factory=list)
    pbt: Series = field(default_factory=list)
    tax: Series = field(default_factory=list)
    pat: Series = field(default_factory=list)
    div_amt: Series = field(default_factory=list)  # total dividend paid, ₹ crore
    eps: Series = field(default_factory=list)  # reported EPS, ₹ (used only for the dilution check)

    # Balance sheet
    equity_capital: Series = field(default_factory=list)
    reserves: Series = field(default_factory=list)
    borrowings: Series = field(default_factory=list)
    other_liab: Series = field(default_factory=list)
    total_assets: Series = field(default_factory=list)
    net_block: Series = field(default_factory=list)
    cwip: Series = field(default_factory=list)
    investments: Series = field(default_factory=list)
    receivables: Series = field(default_factory=list)
    inventory: Series = field(default_factory=list)
    cash: Series = field(default_factory=list)
    share_count: Series = field(default_factory=list)  # split-adjusted where the source allows

    # Cash flow
    cfo: Series = field(default_factory=list)

    # Ratios Screener computes for us (used when the raw lines are missing)
    debtor_days: Series = field(default_factory=list)
    inventory_days: Series = field(default_factory=list)

    # Market history: share price at each fiscal year end (split-adjusted)
    year_price: Series = field(default_factory=list)

    # Ownership: promoter holding %, one value per year (oldest first)
    promoter_holding: Series = field(default_factory=list)
    pledged_pct: Optional[float] = None

    # Banks, NBFCs and insurers need a different method (see guide §3.1)
    is_financial: bool = False
    notes: List[str] = field(default_factory=list)

    def series(self, name: str) -> Series:
        """Return a series padded/truncated to the number of years."""
        s = list(getattr(self, name) or [])
        n = len(self.years)
        if len(s) < n:
            s = [None] * (n - len(s)) + s
        return s[-n:] if n else s

    @property
    def shares(self) -> Optional[float]:
        """Shares outstanding in crore, derived from market cap and price."""
        if self.price and self.mcap:
            return self.mcap / self.price
        return None
