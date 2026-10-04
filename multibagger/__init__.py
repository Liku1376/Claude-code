"""Multibagger screener for Indian equities.

Collects company data from Screener.in and runs it through the
"Value Investing Process — Indian Equities" guide to rank the strongest
candidates for enduring multibagger returns.
"""

from .engine import Result, Settings, analyse, rank  # noqa: F401
from .model import Company  # noqa: F401

# Stage 1 of the guide: the quality-at-a-price screen, run monthly.
# Deliberately no valuation filter (no "PE < 20").
STAGE1_QUERY = """Market Capitalization > 500 AND
Average return on capital employed 10Years > 15 AND
Return on equity > 15 AND
Debt to equity < 0.6 AND
Sales growth 10Years > 10 AND
Profit growth 10Years > 10 AND
OPM 5Year > 12 AND
Promoter holding > 40 AND
Pledged percentage < 5"""
