"""
ETF Universe Definition.
Contains ~135 ETFs across 8 categories, all with >$100M AUM.
Each category has a designated benchmark for RS Line calculations.
"""

from __future__ import annotations

# Benchmark mapping per category
CATEGORY_BENCHMARKS = {
    "US Equity": "SPY",
    "US Sector": "SPY",
    "Thematic": "SPY",
    "Factor": "SPY",
    "Intl Equity": "EEM",  # Defaulting to EEM, but we'll map specific ones
    "Fixed Income": "BND",
    "Commodity": "DBC",
    "Real Estate": "VNQ",
    "Currency": "UUP",
    "Volatility": "SPY"
}

# The universe (filtered to >$100M AUM)
ETF_UNIVERSE = [
    # US Broad Market (Benchmark: SPY)
    {"symbol": "SPY", "name": "SPDR S&P 500", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "QQQ", "name": "Invesco Nasdaq 100", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "IWM", "name": "iShares Russell 2000", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "DIA", "name": "SPDR Dow Jones", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "VTI", "name": "Vanguard Total Market", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "MDY", "name": "SPDR S&P 400 Mid-Cap", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "IJH", "name": "iShares Core S&P Mid-Cap", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "IJR", "name": "iShares Core S&P Small-Cap", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "IVV", "name": "iShares Core S&P 500", "category": "US Equity", "benchmark": "SPY"},
    {"symbol": "VOO", "name": "Vanguard S&P 500", "category": "US Equity", "benchmark": "SPY"},

    # US Sectors (Benchmark: SPY)
    {"symbol": "XLK", "name": "Technology Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLF", "name": "Financial Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLE", "name": "Energy Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLV", "name": "Health Care Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLI", "name": "Industrial Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLY", "name": "Consumer Discret Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLP", "name": "Consumer Staples Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLU", "name": "Utilities Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLB", "name": "Materials Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLRE", "name": "Real Estate Select", "category": "US Sector", "benchmark": "SPY"},
    {"symbol": "XLC", "name": "Communication Services", "category": "US Sector", "benchmark": "SPY"},

    # Factors (Benchmark: SPY)
    {"symbol": "QUAL", "name": "iShares MSCI Quality", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "MTUM", "name": "iShares MSCI Momentum", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "USMV", "name": "iShares Min Volatility", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "VLUE", "name": "iShares MSCI Value", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "SIZE", "name": "iShares MSCI USA Size", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "IWF", "name": "iShares Russell 1000 Growth", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "IWD", "name": "iShares Russell 1000 Value", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "DGRO", "name": "iShares Core Dividend Growth", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "VIG", "name": "Vanguard Dividend Appreciation", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "DVY", "name": "iShares Select Dividend", "category": "Factor", "benchmark": "SPY"},
    {"symbol": "SCHD", "name": "Schwab US Dividend Equity", "category": "Factor", "benchmark": "SPY"},

    # Thematic (Benchmark: SPY)
    {"symbol": "ITA", "name": "iShares US Aerospace & Def", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "XAR", "name": "SPDR Aerospace & Defense", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "DFEN", "name": "Direxion Aerospace 3x", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "PPA", "name": "Invesco Aerospace & Defense", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "URA", "name": "VanEck Uranium & Nuclear", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "URNM", "name": "Sprott Uranium Miners", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "NLR", "name": "VanEck Nuclear Energy", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "ICLN", "name": "iShares Global Clean Energy", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "QCLN", "name": "First Trust NASDAQ Clean Edge", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "TAN", "name": "Invesco Solar", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "FAN", "name": "First Trust Global Wind", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "CNRG", "name": "SPDR S&P Kensho Clean Power", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "SOXX", "name": "iShares Semiconductor", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "SMH", "name": "VanEck Semiconductor", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "AIQ", "name": "Global X AI & Technology", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "ARKK", "name": "ARK Innovation", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "BOTZ", "name": "Global X Robotics & AI", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "ROBO", "name": "ROBO Global Robotics", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "HACK", "name": "ETFMG Prime Cyber Security", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "BUG", "name": "Global X Cybersecurity", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "CIBR", "name": "First Trust Cybersecurity", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "WCLD", "name": "WisdomTree Cloud Computing", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "CLOU", "name": "Global X Cloud Computing", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "FINX", "name": "Global X FinTech", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "BLOK", "name": "Amplify Transformational Data", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "IBB", "name": "iShares Biotech", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "XBI", "name": "SPDR Biotech", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "IHI", "name": "iShares Medical Devices", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "ARKG", "name": "ARK Genomic Revolution", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "PAVE", "name": "Global X US Infrastructure Dev", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "IFRA", "name": "iShares US Infrastructure", "category": "Thematic", "benchmark": "SPY"},
    {"symbol": "GII", "name": "SPDR Global Infrastructure", "category": "Thematic", "benchmark": "SPY"},

    # Intl Equity
    {"symbol": "EWU", "name": "iShares MSCI UK", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EWG", "name": "iShares MSCI Germany", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EWQ", "name": "iShares MSCI France", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EWI", "name": "iShares MSCI Italy", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EWP", "name": "iShares MSCI Spain", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "VGK", "name": "Vanguard FTSE Europe", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EZU", "name": "iShares MSCI Eurozone", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "IEUR", "name": "iShares Core MSCI Europe", "category": "Intl Equity", "benchmark": "VGK"},
    {"symbol": "EWJ", "name": "iShares MSCI Japan", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWA", "name": "iShares MSCI Australia", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWC", "name": "iShares MSCI Canada", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWT", "name": "iShares MSCI Taiwan", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWY", "name": "iShares MSCI South Korea", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWS", "name": "iShares MSCI Singapore", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "INDA", "name": "iShares MSCI India", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "MCHI", "name": "iShares MSCI China", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "FXI", "name": "iShares China Large-Cap", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "KWEB", "name": "KraneShares CSI China Internet", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWZ", "name": "iShares MSCI Brazil", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EEM", "name": "iShares MSCI EM", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "VWO", "name": "Vanguard FTSE EM", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "IEMG", "name": "iShares Core MSCI EM", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EWW", "name": "iShares MSCI Mexico", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "EIS", "name": "iShares MSCI Israel", "category": "Intl Equity", "benchmark": "EEM"},
    {"symbol": "ACWI", "name": "iShares MSCI ACWI", "category": "Intl Equity", "benchmark": "VT"},
    {"symbol": "VT", "name": "Vanguard Total World Stock", "category": "Intl Equity", "benchmark": "VT"},

    # Fixed Income (Benchmark: BND)
    {"symbol": "TLT", "name": "iShares 20+ Yr Treasury", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "IEF", "name": "iShares 7-10 Yr Treasury", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "SHY", "name": "iShares 1-3 Yr Treasury", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "GOVT", "name": "iShares US Treasury Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "BND", "name": "Vanguard Total Bond Market", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "AGG", "name": "iShares Core US Aggregate Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "BNDX", "name": "Vanguard Total Intl Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "LQD", "name": "iShares IG Corp Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "HYG", "name": "iShares High Yield Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "JNK", "name": "SPDR High Yield Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "EMB", "name": "iShares EM Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "TIP", "name": "iShares TIPS Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "VTIP", "name": "Vanguard Short-Term TIPS", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "MUB", "name": "iShares National Muni Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "VCIT", "name": "Vanguard Interm-Term Corp Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "VCSH", "name": "Vanguard Short-Term Corp Bond", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "BKLN", "name": "Invesco Senior Loan", "category": "Fixed Income", "benchmark": "BND"},
    {"symbol": "FLOT", "name": "iShares Floating Rate Bond", "category": "Fixed Income", "benchmark": "BND"},

    # Commodities (Benchmark: DBC)
    {"symbol": "GLD", "name": "SPDR Gold Shares", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "IAU", "name": "iShares Gold Trust", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "SLV", "name": "iShares Silver Trust", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "USO", "name": "United States Oil Fund", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "DBC", "name": "Invesco DB Commodity", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "DBA", "name": "Invesco DB Agriculture", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "PDBC", "name": "Invesco Optimum Yield Cmdty", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "CPER", "name": "United States Copper Index", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "WEAT", "name": "Teucrium Wheat Fund", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "CORN", "name": "Teucrium Corn Fund", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "PALL", "name": "Aberdeen Palladium ETF", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "PPLT", "name": "Aberdeen Platinum ETF", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "COPX", "name": "Global X Copper Miners", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "GDX", "name": "VanEck Gold Miners", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "GDXJ", "name": "VanEck Junior Gold Miners", "category": "Commodity", "benchmark": "DBC"},
    {"symbol": "SIL", "name": "Global X Silver Miners", "category": "Commodity", "benchmark": "DBC"},

    # Real Estate (Benchmark: VNQ)
    {"symbol": "VNQ", "name": "Vanguard Real Estate", "category": "Real Estate", "benchmark": "VNQ"},
    {"symbol": "IYR", "name": "iShares US Real Estate", "category": "Real Estate", "benchmark": "VNQ"},
    {"symbol": "SCHH", "name": "Schwab US REIT", "category": "Real Estate", "benchmark": "VNQ"},
    {"symbol": "XLRE", "name": "Real Estate Select SPDR", "category": "Real Estate", "benchmark": "VNQ"},
    {"symbol": "VNQI", "name": "Vanguard Global ex-US REIT", "category": "Real Estate", "benchmark": "VNQ"},

    # Currency (Benchmark: UUP)
    {"symbol": "UUP", "name": "Invesco DB US Dollar", "category": "Currency", "benchmark": "UUP"},
    {"symbol": "FXE", "name": "Invesco CurrencyShares Euro", "category": "Currency", "benchmark": "UUP"},
    {"symbol": "FXY", "name": "Invesco CurrencyShares Yen", "category": "Currency", "benchmark": "UUP"},
    {"symbol": "FXF", "name": "Invesco CurrencyShares CHF", "category": "Currency", "benchmark": "UUP"},

    # Volatility (Benchmark: SPY)
    {"symbol": "VIXY", "name": "ProShares VIX Short-Term", "category": "Volatility", "benchmark": "SPY"},
    {"symbol": "SVXY", "name": "ProShares Short VIX", "category": "Volatility", "benchmark": "SPY"},
]

def get_universe_tickers() -> list[str]:
    return [e["symbol"] for e in ETF_UNIVERSE]

def get_benchmark_tickers() -> list[str]:
    benchmarks = set(e["benchmark"] for e in ETF_UNIVERSE)
    return list(benchmarks)

def get_category_map() -> dict[str, str]:
    return {e["symbol"]: e["category"] for e in ETF_UNIVERSE}

def get_benchmark_map() -> dict[str, str]:
    return {e["symbol"]: e["benchmark"] for e in ETF_UNIVERSE}

def get_name_map() -> dict[str, str]:
    return {e["symbol"]: e["name"] for e in ETF_UNIVERSE}
