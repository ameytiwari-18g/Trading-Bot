# Historical NIFTY 50 Membership Source

Source used by `download_constituents.py`:

BKKB20/nse-index-history, a public research repository reconstructing historical NSE index constituents from NSE/Nifty Indices reconstitution circulars.

Repository: https://github.com/BKKB20/nse-index-history

The repository states that its NIFTY 50 reconstruction covers 2004–2026 and provides a FLAT_LIST and WIDE_FORMAT output. The dataset is a third-party reconstruction and is not an official NSE data feed. Known limitations stated by the repository include scanned 2018–2019 circulars and mapping limitations for earlier periods.

Our project uses the reconstructed NIFTY 50 membership at monthly resolution. This is intended to reduce survivorship bias compared with applying today's constituent list to the whole historical period.
