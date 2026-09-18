# NIFTY 50 Historical Membership

## Source

Aditya Jha, *NSE Historical Membership (Point-in-Time)*:
https://github.com/aditya-jha/nse-historical-membership

The dataset is reconstructed from publicly published NSE/Nifty Indices
press releases and circulars and stores membership as effective-date
intervals. It is independent of NSE/Nifty Indices and is not an official
licensed NSE historical constituent feed.

Official NIFTY 50 reference:
https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50

## Backtest period

2020-01-01 through 2026-03-31.

## Point-in-time method

The backtester receives the constituent set applicable to each trading
date. It does not use today's NIFTY 50 composition for historical dates.

The source uses canonical rename-chain symbols. For the LTIMindtree/LTM
rename, the project converts LTM back to LTIM before 2026-02-27, because
NSE changed the trading symbol from LTIM to LTM effective 2026-02-27.

## Validation

Every trading day represented in the NIFTY 50 index price file must contain
exactly 50 unique constituents. The build is rejected if this invariant
fails.

## Known limitation

The membership source is a third-party reconstruction from public NSE
materials. Its documented coverage is strongest from 2017 onward. The
2020-2026 period used here falls inside its high-confidence coverage
window, but the dataset should still be disclosed as a reconstructed
point-in-time universe in the academic report.
