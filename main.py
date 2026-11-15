#!/usr/bin/env python3
"""Wash-out turn catcher for btc-race-24h-20261115-0828 (bars-replay/v1).

Paper $1,000 of cbBTC vs USDC for 24 hours. The dev window slides 4%
downhill over the day, so holding the trend loses money and all six kit
baselines finish red. This bot therefore stays in cash nearly the whole
race and only steps in after a wash-out that is already turning: the
latest close 2% or more below the high of the last 60 minutes, with the
last two closes both above the one before them. It spends the whole
cash balance, then leaves at +1.5% or cuts at -2%, whichever prints
first, and sits out five bars after every exit so one slide is never
chased twice. One position at a time, no leverage, no clock, no
network, no files: identical bars always produce identical replies.

The wire belongs to the kit's Python shim (vendor/makefun_bars.py): it
keeps the account and the latest bar current, hands each batch to
on_batch, and writes exactly one reply per batch echoing its seq. All
this file decides is which orders, if any, a batch deserves.
"""

import os
import sys
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"
LOOKBACK = 60        # minutes of closes kept for the high-water mark
DIP_PCT = 98         # enter only while close <= 98% of the 60-min high
COOLDOWN = 5         # bars to sit out after an exit before re-entering
TAKE_NUM = 203       # leave at 101.5% of the position's cost (203/200)
TAKE_DEN = 200
STOP_NUM = 49        # leave at 98% of the position's cost (49/50)
STOP_DEN = 50
SLIP_BPS = 100       # max slippage asked for on every order


class WashoutCatcher:
    """One open trade at most; the rule from the dev-window backtest."""

    def __init__(self):
        self.closes = deque(maxlen=LOOKBACK)  # newest close last
        self.exited_at = -10 ** 9             # seq of the most recent exit

    def decide(self, state):
        """Orders for this batch (possibly none)."""
        close = state.close(SYMBOL)
        if close is None:
            return []
        self.closes.append(close)
        if state.warming_up:
            return []  # warm-up bars build history; orders here are refused
        held = state.positions.get(SYMBOL)
        if held is not None:
            return self._finish(state, held, close)
        return self._maybe_open(state, close)

    def _finish(self, state, held, close):
        """Holding: take the gain, or cut the loss, or wait."""
        worth = state.value(SYMBOL, held.qty, close)
        if worth * TAKE_DEN >= held.cost * TAKE_NUM:
            return self._sell(state, held)
        if worth * STOP_DEN <= held.cost * STOP_NUM:
            return self._sell(state, held)
        return []

    def _sell(self, state, held):
        self.exited_at = state.seq
        return [{"side": "sell", "symbol": SYMBOL, "qty": held.qty,
                 "max_slippage_bps": SLIP_BPS}]

    def _maybe_open(self, state, close):
        """Flat: open only on a deep dip that is already turning up."""
        if state.cash <= 0:
            return []
        if state.seq - self.exited_at < COOLDOWN:
            return []
        if len(self.closes) < LOOKBACK:
            return []
        if close * 100 > max(self.closes) * DIP_PCT:
            return []
        if not (self.closes[-1] > self.closes[-2] > self.closes[-3]):
            return []
        return [{"side": "buy", "symbol": SYMBOL,
                 "notional_quote_units": state.cash,
                 "max_slippage_bps": SLIP_BPS}]


_CATCHER = WashoutCatcher()


def on_batch(state, batch):
    return _CATCHER.decide(state)


makefun_bars.run(on_batch)
