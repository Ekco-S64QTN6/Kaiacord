"""Kaia's radio: shortwave listening and a local scanner.

Shortwave: military EAMs (eam.watch), number stations (Priyom), scheduled
recording from public KiwiSDRs, the NCDXF beacon chain and UVB-76. Those are
hobbyist feeds, polled gently — every few hours, one request at a time, cached
on disk — because the data is a novelty, not a feed anyone needs live.

Local: an RTL-SDR on the bot runs a nightly waterfall watch over the voice
bands and keeps a ledger of what it hears (scanner, waterfall, ledger, dongle).
"""
