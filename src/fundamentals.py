"""
Fetch fundamental data for ETFs using yfinance.
Extracts AUM, Expense Ratio, Yield, and category-specific metrics (P/E, Duration).
"""

from __future__ import annotations

import time
import pandas as pd
import yfinance as yf

def fetch_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """
    Изтегля фундаментални данни за списък от ETF-и.
    Връща DataFrame с колони:
    ticker, aum, expense_ratio, yield, pe_ratio, duration, holdings_turnover
    """
    rows = []
    
    print(f"Fetching fundamentals for {len(tickers)} ETFs...")
    for i, ticker in enumerate(tickers):
        record = {
            "ticker": ticker,
            "aum": None,
            "expense_ratio": None,
            "yield": None,
            "pe_ratio": None,
            "duration": None,
            "holdings_turnover": None
        }
        
        try:
            tk = yf.Ticker(ticker)
            info = tk.info
            
            # Basic info
            aum = info.get("totalAssets") or info.get("netAssets")
            if aum:
                record["aum"] = aum
                
            div_yield = info.get("yield") or info.get("trailingAnnualDividendYield")
            if div_yield:
                record["yield"] = float(div_yield) * 100.0  # Convert to percentage
                
            # Funds data (newer yfinance API)
            try:
                fd = tk.funds_data
                
                # Operations (Expense Ratio, Turnover)
                if hasattr(fd, "fund_operations") and fd.fund_operations is not None:
                    ops = fd.fund_operations
                    if not ops.empty and ticker in ops.columns:
                        if "Annual Report Expense Ratio" in ops.index:
                            val = ops.loc["Annual Report Expense Ratio", ticker]
                            if pd.notna(val):
                                record["expense_ratio"] = float(val) * 100.0
                        
                        if "Annual Holdings Turnover" in ops.index:
                            val = ops.loc["Annual Holdings Turnover", ticker]
                            if pd.notna(val):
                                record["holdings_turnover"] = float(val) * 100.0
                
                # Equity metrics (P/E)
                if hasattr(fd, "equity_holdings") and fd.equity_holdings is not None:
                    eq = fd.equity_holdings
                    if not eq.empty and ticker in eq.columns:
                        if "Price/Earnings" in eq.index:
                            val = eq.loc["Price/Earnings", ticker]
                            if pd.notna(val):
                                record["pe_ratio"] = float(val)
                
                # Bond metrics (Duration)
                if hasattr(fd, "bond_holdings") and fd.bond_holdings is not None:
                    bonds = fd.bond_holdings
                    if not bonds.empty and ticker in bonds.columns:
                        if "Duration" in bonds.index:
                            val = bonds.loc["Duration", ticker]
                            if pd.notna(val):
                                record["duration"] = float(val)
                                
            except Exception as e:
                # Silently fail for funds_data errors, some ETFs might not have it
                pass
                
        except Exception as e:
            print(f"Error fetching fundamentals for {ticker}: {e}")
            
        rows.append(record)
        
        # Rate limiting
        if (i + 1) % 20 == 0:
            time.sleep(1)
            
    df = pd.DataFrame(rows)
    return df
