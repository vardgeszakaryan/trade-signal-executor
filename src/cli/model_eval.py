"""Evaluate every model declared in configs/router.yaml against the
100-message human-text dataset, one model at a time (no fallbacks).

Usage: uv run test-models
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import dotenv
from litellm.router import Router
from loguru import logger

from trade_executor.config import all_config_import
from trade_executor.listener import RawMessage
from trade_executor.parser.ai_parser import LLMParser
from trade_executor.parser.base import ModelConfig, ParsedData, SignalAction

dotenv.load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent.parent
REPORT_PATH = PROJECT_ROOT / "tests" / "eval" / "model_eval_report.json"


@dataclass
class Case:
    idx: int
    text: str
    action: SignalAction
    has_entry: bool
    entry_type: Optional[str] = None
    entry_unit: Optional[str] = None
    size: Optional[float] = None


# (text, action, has_entry, entry_type, entry_unit, size)
RAW_CASES = [
    # --- plain buy signals ------------------------------------------------
    ("BUY XAUUSDm 0.02 3950 SL 3920 TP 4000", "BUY", True, "single", "price", 0.02),
    (
        "buy 0.01 gold at 3965, stop loss 3940, take profit 4010 🚀",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "🔥🔥 long XAUUSDm 0.03 entry 3948 sl 3900 tp 4050 lets gooo",
        "BUY",
        True,
        "single",
        "price",
        0.03,
    ),
    (
        "Pls buy gold 0.01 @3972. Sl 3955. Tp 4005. Thx 🙏",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "XAUUSDm BUY 0.05 @ 3930 | SL: 3890 | TP: 4030 ✅",
        "BUY",
        True,
        "single",
        "price",
        0.05,
    ),
    (
        "guys im longin gold 0.02 @ 3958, sl at 3935 and tp 3995 💰",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "🟢 BUY signal: XAUUSDm 0.01 entry 3968, SL 3948, TP1 4000",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "Yo buy 0.04 xauusdm at 3925 stop 3900 target 3980 😤",
        "BUY",
        True,
        "single",
        "price",
        0.04,
    ),
    (
        "BUY GOLD!! 0.02 @ 3945, sl 3925, tp 4000, trust the process 📈",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "New signal 🆕 buy XAUUSDm 0.01 @ 3975, stop loss 3960, take profit 4015",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    ("long xau 0.03 @3938 sl 3910 tp 3990 🎯🎯", "BUY", True, "single", "price", 0.03),
    (
        "Buy buy buy 💎 0.01 gold @ 3980 SL 3965 TP 4020",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    # --- plain sell signals -----------------------------------------------
    ("SELL XAUUSDm 0.02 @ 4020 SL 4050 TP 3950", "SELL", True, "single", "price", 0.02),
    (
        "short gold 0.01 at 4015, sl 4040, tp 3970 🔻",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "📉 SELL 0.03 XAUUSDm @ 4025, stop 4060, target 3960",
        "SELL",
        True,
        "single",
        "price",
        0.03,
    ),
    ("sellin xau 0.02 @4010 sl 4035 tp 3975 💸", "SELL", True, "single", "price", 0.02),
    (
        "🔴 SELL signal: gold 0.01 entry 4030 SL 4055 TP 3980",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "Bro short this 0.01 @ 4022 sl 4045 tp 3985 😎",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "SELL NOW 0.02 XAUUSDm @ 4018, SL: 4042, TP: 3965 ⚠️",
        "SELL",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "going short on gold 0.04 @ 4008, stop loss 4030, take profit 3955",
        "SELL",
        True,
        "single",
        "price",
        0.04,
    ),
    (
        "sell xauusdm 0.01 @4035 sl 4060 tp 3990 🐻🐻",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "short it 📉 0.02 gold @ 4028, sl 4050, tp 3970",
        "SELL",
        True,
        "single",
        "price",
        0.02,
    ),
    # --- market orders (no entry) ------------------------------------------
    (
        "BUY XAUUSDm 0.01 market price, SL 20 pips, TP 40 pips",
        "BUY",
        False,
        None,
        None,
        0.01,
    ),
    ("market buy gold 0.02 🚀 no entry just hit it", "BUY", False, None, None, 0.02),
    (
        "buy at market 0.01, stop 30 pips, target 60 pips ✅",
        "BUY",
        False,
        None,
        None,
        0.01,
    ),
    ("Market BUY xau 0.03 🟢 sl 25 pips tp 50 pips", "BUY", False, None, None, 0.03),
    (
        "sell at market price 0.01, SL 15 pips TP 30 pips 🔻",
        "SELL",
        False,
        None,
        None,
        0.01,
    ),
    ("market sell gold 0.02 now!! sl 20 pips", "SELL", False, None, None, 0.02),
    (
        "BUY NOW AT MARKET 0.01 🔥 SL 10 pips, TP 20 pips",
        "BUY",
        False,
        None,
        None,
        0.01,
    ),
    (
        "yo just buy market 0.01, stop loss 25 pips take profit 75 pips 💰",
        "BUY",
        False,
        None,
        None,
        0.01,
    ),
    (
        "Market order: SELL XAUUSDm 0.01, stop 35 pips, target 70 pips",
        "SELL",
        False,
        None,
        None,
        0.01,
    ),
    (
        "market buy 0.02 xauusdm no limit, sl 30 pips tp 90 pips 🎯",
        "BUY",
        False,
        None,
        None,
        0.02,
    ),
    # --- limit orders -------------------------------------------------------
    (
        "BUY LIMIT XAUUSDm 0.01 @ 3955 SL 3935 TP 3995",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "limit buy gold 0.02 @ 3960, stop 3940, tp 4010 📥",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    ("Buy limit 0.01 @ 3948 sl 3930 tp 3990 ✅", "BUY", True, "single", "price", 0.01),
    (
        "pending buy 0.02 xau @ 3952, SL 3928, TP 4000 🕐",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "SELL LIMIT 0.01 gold @ 4032 SL 4055 TP 3985",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "limit sell xauusdm 0.02 @ 4026, stop 4048, target 3975 📉",
        "SELL",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "set a buy limit on gold 0.01 @ 3962 sl 3945 tp 4005 🙏",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "Pending SELL 0.03 @ 4040 | SL 4065 | TP 3980 ⏳",
        "SELL",
        True,
        "single",
        "price",
        0.03,
    ),
    # --- multiple entry levels ---------------------------------------------
    (
        "BUY XAUUSDm 0.02 entries 3950 / 3945 SL 3920 TP 4000",
        "BUY",
        True,
        "multiple",
        "price",
        0.02,
    ),
    (
        "buy gold 0.03, enter at 3948 and 3942, sl 3915, tp 4010 🎯",
        "BUY",
        True,
        "multiple",
        "price",
        0.03,
    ),
    (
        "Long xau 0.01 @ 3955 / 3960 / 3965, stop 3930, target 4020 📈",
        "BUY",
        True,
        "multiple",
        "price",
        0.01,
    ),
    (
        "SELL 0.02 entries 4020 / 4025 SL 4050 TP 3960",
        "SELL",
        True,
        "multiple",
        "price",
        0.02,
    ),
    (
        "short gold 0.01 at 4030 and 4038, sl 4060, tp 3975 🔻",
        "SELL",
        True,
        "multiple",
        "price",
        0.01,
    ),
    (
        "buy zone entries: 3950, 3946, 3942 — 0.02 lots, sl 3918 tp 4005 ✅",
        "BUY",
        True,
        "multiple",
        "price",
        0.02,
    ),
    (
        "Entries 4015/4020 sell 0.01 xauusdm, SL 4045, TP 3965 🐻",
        "SELL",
        True,
        "multiple",
        "price",
        0.01,
    ),
    # --- SL only ------------------------------------------------------------
    ("BUY XAUUSDm 0.01 @ 3970 SL 3950", "BUY", True, "single", "price", 0.01),
    (
        "buy gold 0.02 @ 3962, stop loss only 3945 🛡️",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    ("long 0.01 xau @3975 sl 3958 no tp yet 🤷", "BUY", True, "single", "price", 0.01),
    (
        "SELL 0.01 @ 4028, SL 4052 (no target for now)",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "short gold 0.02 @ 4019 stop 4041 only 🚫🎯",
        "SELL",
        True,
        "single",
        "price",
        0.02,
    ),
    # --- TP only ------------------------------------------------------------
    ("BUY XAUUSDm 0.01 @ 3968 TP 4010", "BUY", True, "single", "price", 0.01),
    ("buy gold 0.02 @ 3959, target 4000 only 🎯", "BUY", True, "single", "price", 0.02),
    (
        "long xau 0.01 @ 3971 tp 4015 no stop, yolo 😅",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    ("SELL 0.01 @ 4026 take profit 3980", "SELL", True, "single", "price", 0.01),
    (
        "short 0.02 gold @ 4017, tp 3970 only, no sl 🙈",
        "SELL",
        True,
        "single",
        "price",
        0.02,
    ),
    # --- multiple TP levels --------------------------------------------------
    (
        "BUY XAUUSDm 0.02 @ 3955 SL 3930 TP 3990 / 4020",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "buy gold 0.01 @ 3963, sl 3945, tp1 3995 tp2 4015 tp3 4040 🚀",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "long 0.02 xau @ 3950 sl 3925 targets: 3985, 4010, 4030 ✅",
        "BUY",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "SELL 0.01 @ 4030 SL 4055 TP 4000 / 3975 / 3950",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "short gold 0.02 @ 4024 sl 4048, take profits 3990 & 3960 📉",
        "SELL",
        True,
        "single",
        "price",
        0.02,
    ),
    (
        "buy 0.01 @ 3966 sl 3950 tp 4000/4025 💰 split exits",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    # --- pips-based SL/TP ------------------------------------------------------
    ("BUY XAUUSDm 0.01 SL 30 pips TP 60 pips", "BUY", False, None, None, 0.01),
    (
        "buy gold 0.02, stop loss 25 pips, take profit 75 pips 🎯",
        "BUY",
        False,
        None,
        None,
        0.02,
    ),
    ("long xau 0.01 sl 20 pips tp 40 pips 📈", "BUY", False, None, None, 0.01),
    ("SELL 0.01 SL 35 pips TP 70 pips 🔻", "SELL", False, None, None, 0.01),
    ("short gold 0.02, sl 15 pips, tp 45 pips ✅", "SELL", False, None, None, 0.02),
    ("buy 0.01 market sl 50 pips tp 100 pips 🚀🚀", "BUY", False, None, None, 0.01),
    (
        "BUY XAU 0.01 @ 3970, SL 30 pips, TP 90 pips",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "sell xauusdm 0.01 @ 4025 stop 25 pips target 60 pips 🐻",
        "SELL",
        True,
        "single",
        "price",
        0.01,
    ),
    # --- range entries -------------------------------------------------------
    (
        "BUY XAUUSDm 0.02 entry zone 3940-3950 SL 3915 TP 4000",
        "BUY",
        True,
        "range",
        "price",
        0.02,
    ),
    (
        "buy gold 0.01 between 3945 and 3955, sl 3920, tp 4010 🎯",
        "BUY",
        True,
        "range",
        "price",
        0.01,
    ),
    (
        "long xau 0.03, entry range 3938 to 3948, stop 3910, target 4005 📈",
        "BUY",
        True,
        "range",
        "price",
        0.03,
    ),
    ("SELL 0.02 entry 4020-4030 SL 4055 TP 3965", "SELL", True, "range", "price", 0.02),
    (
        "short gold 0.01 in the 4025-4035 zone, sl 4060 tp 3970 🔻",
        "SELL",
        True,
        "range",
        "price",
        0.01,
    ),
    (
        "buy zone 3950 to 3960, 0.02 lots, sl 3925 tp 4015 ✅",
        "BUY",
        True,
        "range",
        "price",
        0.02,
    ),
    (
        "sell zone 4015-4025 xau 0.01, stop 4045, target 3960 📉",
        "SELL",
        True,
        "range",
        "price",
        0.01,
    ),
    # --- close ---------------------------------------------------------------
    ("CLOSE XAUUSDm", "CLOSE", False, None, None, None),
    ("close all my gold positions 🛑", "CLOSE", False, None, None, None),
    ("exit everything on xau pls 🙏", "CLOSE", False, None, None, None),
    ("Close all positions NOW ⚠️⚠️", "CLOSE", False, None, None, None),
    ("flatten my gold trades 0 risk tonight 😴", "CLOSE", False, None, None, None),
    ("close it all, im done for today 🏁", "CLOSE", False, None, None, None),
    ("GET ME OUT OF GOLD 🔥🔥 close everything", "CLOSE", False, None, None, None),
    ("Close all open trades on XAUUSDm, thanks 👍", "CLOSE", False, None, None, None),
    # --- cancel ----------------------------------------------------------------
    ("CANCEL all pending orders", "CANCEL", False, None, None, None),
    ("cancel my gold pendings 🚫", "CANCEL", False, None, None, None),
    ("delete all open orders on xau 🗑️", "CANCEL", False, None, None, None),
    ("CANCEL PENDING ORDERS NOW ⚠️", "CANCEL", False, None, None, None),
    ("remove all my limit orders pls 🙏", "CANCEL", False, None, None, None),
    ("nah cancel everything, trade is off ❌", "CANCEL", False, None, None, None),
    # --- other symbols / messy intent --------------------------------------------
    (
        "BUY EURUSD 0.5 @ 1.0850 SL 1.0820 TP 1.0900",
        "BUY",
        True,
        "single",
        "price",
        0.5,
    ),
    (
        "sell GBPJPY 0.2 at 191.50, sl 192.00, tp 190.20 💷",
        "SELL",
        True,
        "single",
        "price",
        0.2,
    ),
    (
        "BUY BTCUSD 0.01 @ 64000 SL 62500 TP 68000 🚀",
        "BUY",
        True,
        "single",
        "price",
        0.01,
    ),
    (
        "buy EURUSD 0.5 and GBPUSD 0.3 both at market 🇪🇺🇬🇧",
        "BUY",
        False,
        None,
        None,
        None,
    ),
    ("BUY gold!! 🚀🚀🚀", "BUY", False, None, None, None),
    ("sell sell sell xau now 😱", "SELL", False, None, None, None),
    ("buy the dip boys 0.01 💎🙌", "BUY", False, None, None, 0.01),
    ("quick long 0.02 gold before it moons 🌙", "BUY", False, None, None, 0.02),
]
# (text, action, has_entry, entry_type, entry_unit, size)
ADVANCED_RAW_CASES = [
    # ----------------------------------------------------------------------
    # Human style / slang / incomplete but understandable
    # ----------------------------------------------------------------------
    ("Guys finally breaking 4000, im jumping long on gold here. 0.02 size, stop below 3970, targets 4050 and 4080",
     "BUY", True, "single", "price", 0.02),
    ("Gold looking weak. Taking a short with small risk. 0.01 lot around current price, SL above 4035 TP 3980",
     "SELL", False, None, None, 0.01),
    ("🚨 XAU is about to move. I am buying this zone. 2 entries, first one now and second lower. SL 3920 TP 4010",
     "BUY", True, "multiple", "price", None),
    ("I like gold here. If we get a pullback into 3950 area I'll take the buy. Not entering yet",
     "BUY", True, "single", "price", None),
    ("watching XAUUSD. No trade yet, waiting for confirmation above 4000",
     "IGNORE", False, None, None, None),

    # ----------------------------------------------------------------------
    # Fake signals / discussion, not execution
    # ----------------------------------------------------------------------
    ("Yesterday's BUY XAUUSD from 3950 hit TP 4000 🔥🔥",
     "IGNORE", False, None, None, None),
    ("My friend opened a SELL on gold at 4020, SL 4050",
     "IGNORE", False, None, None, None),
    ("Should I buy gold here or wait for 3950?",
     "IGNORE", False, None, None, None),
    ("BUY was cancelled earlier, don't enter this anymore",
     "CANCEL", False, None, None, None),

    # ----------------------------------------------------------------------
    # Updates / continuation messages (very important)
    # ----------------------------------------------------------------------
    ("SL moved to breakeven",
     "UPDATE", False, None, None, None),
    ("TP1 reached, close half and let the rest run",
     "UPDATE", False, None, None, None),
    ("Move stop to 3990 now",
     "UPDATE", False, None, None, None),
    ("Add another entry at 3940",
     "UPDATE", True, "single", "price", None),
    ("Forgot to mention, take profit is 4050",
     "UPDATE", False, None, None, None),

    # ----------------------------------------------------------------------
    # Very confusing CLOSE vs SELL
    # ----------------------------------------------------------------------
    ("Get me out of this gold trade before news",
     "CLOSE", False, None, None, None),
    ("I don't want this position anymore, close everything",
     "CLOSE", False, None, None, None),
    ("Gold is dead, I'm done with this setup",
     "CLOSE", False, None, None, None),
    ("Close half now, keep the rest running",
     "UPDATE", False, None, None, None),

    # ----------------------------------------------------------------------
    # Pending order confusion
    # ----------------------------------------------------------------------
    ("If gold comes back to 3945 I want to buy, otherwise ignore",
     "BUY", True, "single", "price", None),
    ("Place a limit order below current price around 3950",
     "BUY", True, "single", "price", None),
    ("Don't buy yet. Prepare a buy limit at 3940",
     "BUY", True, "single", "price", None),
    ("Cancel that limit idea, market changed",
     "CANCEL", False, None, None, None),

    # ----------------------------------------------------------------------
    # Risk based instead of explicit lots
    # ----------------------------------------------------------------------
    ("BUY gold risking 1% account. Entry 3960 SL 3940 TP 4020",
     "BUY", True, "single", "price", None),
    ("Short XAU with $50 risk, entry around 4025",
     "SELL", True, "single", "price", None),
    ("Long gold. Use normal size, not aggressive",
     "BUY", False, None, None, None),

    # ----------------------------------------------------------------------
    # Multiple symbols
    # ----------------------------------------------------------------------
    ("""Morning setup:
     BUY XAUUSD 0.02 @3950 SL3920 TP4000
     SELL EURUSD 0.5 @1.0850 SL1.0880 TP1.0800""",
     "BUY", True, "single", "price", 0.02),
    ("Close gold only, leave EURUSD open",
     "CLOSE", False, None, None, None),

    # ----------------------------------------------------------------------
    # Emoji / influencer style
    # ----------------------------------------------------------------------
    ("🚀🚀🚀 GOLD IS READY!!! Long squad let's go. Entry 3965-3970 SL 3940 TP moon 🌙",
     "BUY", True, "range", "price", None),
    ("🐻 Bears taking control. Short XAU now. Small position. TP 3950",
     "SELL", False, None, None, None),

    # ----------------------------------------------------------------------
    # Contradictions
    # ----------------------------------------------------------------------
    ("BUY XAUUSD 0.01 @3960 SL 4000 TP3900",
     "BUY", True, "single", "price", 0.01),
    ("Sell gold but if it breaks 4050 buy instead",
     "SELL", True, "single", "price", None),
    ("BUY 0.02 gold. Actually forget it, don't enter",
     "CANCEL", False, None, None, None),

    # ----------------------------------------------------------------------
    # Professional trader language
    # ----------------------------------------------------------------------
    ("Taking a long position on XAUUSD. Scaling in between 3940-3950. Invalid below 3920. Targeting 4020.",
     "BUY", True, "range", "price", None),
    ("Short bias on gold. Waiting for rejection at 4030 before entry",
     "SELL", True, "single", "price", None),
    ("Setup invalidated. Remove pending orders.",
     "CANCEL", False, None, None, None),

    # ----------------------------------------------------------------------
    # Typos / bad grammar
    # ----------------------------------------------------------------------
    ("buuuy gold 0.01 lot @3950 sl3920 tp4000",
     "BUY", True, "single", "price", 0.01),
    ("selll xau 0.02 now market sl 50 tp100",
     "SELL", False, None, None, 0.02),
    ("clos all xau trades pls",
     "CLOSE", False, None, None, None),
]
def _to_cases(raw: list[tuple], offset: int = 0) -> list[Case]:
    return [
        Case(
            idx=offset + i + 1,
            text=text,
            action=SignalAction(action),
            has_entry=has_entry,
            entry_type=etype,
            entry_unit=eunit,
            size=size,
        )
        for i, (text, action, has_entry, etype, eunit, size) in enumerate(raw)
    ]


CASES = _to_cases(RAW_CASES)
ADVANCED_CASES = _to_cases(ADVANCED_RAW_CASES, offset=len(CASES))


def check(case: Case, parsed: ParsedData) -> list[str]:
    problems = []
    if parsed.action != case.action:
        problems.append(
            f"action: expected {case.action.value}, got {parsed.action.value}"
        )
    if case.action in (SignalAction.BUY, SignalAction.SELL):
        if (parsed.entry is not None) != case.has_entry:
            problems.append(
                f"entry presence: expected {case.has_entry}, got {parsed.entry}"
            )
        if case.size is not None and abs(parsed.size - case.size) > 1e-9:
            problems.append(f"size: expected {case.size}, got {parsed.size}")
        if parsed.entry is not None:
            if case.entry_type and parsed.entry.type != case.entry_type:
                problems.append(
                    f"entry type: expected {case.entry_type}, got {parsed.entry.type}"
                )
            if case.entry_unit and parsed.entry.unit != case.entry_unit:
                problems.append(
                    f"entry unit: expected {case.entry_unit}, got {parsed.entry.unit}"
                )
    return problems


def snippet(text: str) -> str:
    # consoles may use non-UTF-8 codecs (cp1252); strip unencodable emoji
    return text[:60].encode("ascii", "replace").decode("ascii")


def build_parser(model_entry: dict, system_prompt: str) -> tuple[LLMParser, Router]:
    """Build a parser bound to a single router.yaml model entry (no fallbacks)."""
    config = ModelConfig(
        model=model_entry["model_name"],
        system_prompt=system_prompt,
        response_schema=ParsedData,
    )
    router = Router(model_list=[model_entry], timeout=60)
    parser = LLMParser(
        system_prompt=config.system_prompt, router=router, model_config=config
    )
    logger.debug(
        "Parser ready: group='{}' model='{}'",
        model_entry["model_name"],
        model_entry["litellm_params"]["model"],
    )
    return parser, router


async def run_case(parser: LLMParser, case: Case) -> dict:
    start = time.perf_counter()
    error, parsed = None, None
    try:
        parsed = await parser.parse(
            RawMessage(id=case.idx, message=case.text, date=datetime.now(timezone.utc))
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    problems = [] if parsed is None else check(case, parsed)
    return {
        "message": case.text,
        "expected_action": case.action.value,
        "parsed_action": parsed.action.value if parsed else None,
        "wall_ms": round((time.perf_counter() - start) * 1000, 1),
        "llm_resp_time_ms": parsed.resp_time if parsed else None,
        "error": error,
        "problems": problems,
    }


def summarize(results: list[dict], cases: list[Case]) -> dict:
    ran = len(results)
    errored = [r for r in results if r["error"]]
    mismatches = [r for r in results if not r["error"] and r["problems"]]
    ok = ran - len(errored) - len(mismatches)
    walls = sorted(r["wall_ms"] for r in results if not r["error"])

    per_action = {}
    for action in SignalAction:
        subset = [
            r for c, r in zip(cases, results) if c.action == action and not r["error"]
        ]
        if subset:
            per_action[action.value] = (
                f"{sum(1 for r in subset if not r['problems'])}/{len(subset)}"
            )

    return {
        "ran": ran,
        "ok": ok,
        "errors": len(errored),
        "mismatches": len(mismatches),
        "error_rate": f"{100 * len(errored) / ran:.1f}%" if ran else "n/a",
        "accuracy": f"{100 * ok / ran:.1f}%" if ran else "n/a",
        "avg_response_ms": round(sum(walls) / len(walls), 1) if walls else 0.0,
        "p95_response_ms": walls[int(0.95 * (len(walls) - 1))] if walls else 0.0,
        "max_response_ms": walls[-1] if walls else 0.0,
        "per_action": per_action,
    }


EARLY_ABORT_AFTER = 5  # consecutive API errors => treat the model as unreachable
SIMPLE_PASS_ACCURACY = 0.8  # simple-set accuracy required to unlock the advanced set


async def _run_cases(
    parser: LLMParser, cases: list[Case], model_id: str, phase: str
) -> tuple[list[dict], bool]:
    results: list[dict] = []
    consecutive_errors = 0
    aborted = False

    for case in cases:
        record = await run_case(parser, case)
        results.append(record)

        if record["error"]:
            consecutive_errors += 1
            logger.error(
                "[{} {:03d}] FAILED after {:.0f} ms: {}",
                phase, case.idx, record["wall_ms"], record["error"][:300],
            )
            if consecutive_errors >= EARLY_ABORT_AFTER:
                logger.error(
                    "{} ({}): {} consecutive failures; aborting remaining {} cases",
                    model_id, phase, consecutive_errors, len(cases) - len(results),
                )
                aborted = True
                break
        else:
            consecutive_errors = 0
            if record["problems"]:
                logger.warning(
                    "[{} {:03d}] MISMATCH ({}): {}",
                    phase, case.idx, record["parsed_action"], "; ".join(record["problems"]),
                )
            else:
                logger.debug(
                    "[{} {:03d}] ok {:.0f} ms {}",
                    phase, case.idx, record["wall_ms"], snippet(case.text),
                )

        if len(results) % 10 == 0:
            logger.info("{} ({}): progress {}/{}", model_id, phase, len(results), len(cases))

    return results, aborted


async def evaluate_model(entry: dict, system_prompt: str) -> dict:
    """Evaluate one model entry fully isolated: own router, own error handling."""
    name = entry["model_name"]
    model_id = entry["litellm_params"]["model"]
    logger.info(
        "=== Evaluating group '{}' -> {} ({} simple + {} advanced cases) ===",
        name, model_id, len(CASES), len(ADVANCED_CASES),
    )

    try:
        parser, router = build_parser(entry, system_prompt)
    except Exception as exc:
        logger.exception("Setup failed for {}: {}", model_id, exc)
        return {
            "summary": {"status": "setup_failed", "error": f"{type(exc).__name__}: {exc}"},
            "advanced": None,
            "results": [],
            "results_advanced": [],
        }

    try:
        results, aborted = await _run_cases(parser, CASES, model_id, "simple")
        summary = summarize(results, CASES)
        summary["status"] = "aborted" if aborted else "completed"
        logger.info(
            "=== {} simple done: accuracy={} error_rate={} avg={}ms ===",
            model_id, summary["accuracy"], summary["error_rate"], summary["avg_response_ms"],
        )

        advanced_results: list[dict] = []
        accuracy = summary["ok"] / summary["ran"] if summary["ran"] else 0.0
        if aborted or accuracy < SIMPLE_PASS_ACCURACY:
            reason = (
                "early abort" if aborted
                else f"accuracy {accuracy:.1%} below required {SIMPLE_PASS_ACCURACY:.0%}"
            )
            logger.warning("{}: advanced cases skipped ({})", model_id, reason)
            advanced: dict = {"status": "skipped", "reason": reason}
        else:
            logger.info(
                "=== {} passed the simple set; running {} advanced cases ===",
                model_id, len(ADVANCED_CASES),
            )
            advanced_results, adv_aborted = await _run_cases(
                parser, ADVANCED_CASES, model_id, "advanced"
            )
            advanced = summarize(advanced_results, ADVANCED_CASES)
            advanced["status"] = "aborted" if adv_aborted else "completed"
            logger.info(
                "=== {} advanced done: accuracy={} error_rate={} avg={}ms ===",
                model_id, advanced["accuracy"], advanced["error_rate"],
                advanced["avg_response_ms"],
            )

        return {
            "summary": summary,
            "advanced": advanced,
            "results": results,
            "results_advanced": advanced_results,
        }
    finally:
        shutdown = getattr(router, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown()
            except Exception as exc:
                logger.debug("Router cleanup for {} raised: {}", model_id, exc)
        logger.debug("Released router for {}", model_id)


async def evaluate_all(configs: dict) -> dict:
    prompt = ModelConfig(
        model="loader", system_prompt=configs["model"]["system_prompt"]
    ).system_prompt
    entries = configs["router"]["model_list"]
    logger.info("Loaded {} model(s) from router.yaml; dataset size {}", len(entries), len(CASES))

    report = {}
    for entry in entries:
        model_id = entry["litellm_params"]["model"]
        try:
            report[model_id] = await evaluate_model(entry, prompt)
        except Exception as exc:
            # isolate: one model crashing must never stop the others
            logger.exception("Model {} crashed; continuing with next model", model_id)
            report[model_id] = {
                "summary": {"status": "crashed", "error": f"{type(exc).__name__}: {exc}"},
                "results": [],
            }

    logger.info("=========== COMPARISON ===========")
    for model_id, data in report.items():
        s = data["summary"]
        adv = data.get("advanced") or {}
        if adv.get("status") == "skipped":
            advanced_info = f"skipped ({adv['reason']})"
        elif adv:
            advanced_info = f"accuracy={adv.get('accuracy', 'n/a')} error_rate={adv.get('error_rate', 'n/a')}"
        else:
            advanced_info = "n/a"
        logger.info(
            "{}: status={} | simple accuracy={} error_rate={} avg={}ms p95={}ms | advanced: {} | per-action={}",
            model_id, s.get("status", "n/a"), s.get("accuracy", "n/a"),
            s.get("error_rate", "n/a"), s.get("avg_response_ms", "-"),
            s.get("p95_response_ms", "-"), advanced_info, s.get("per_action", {}),
        )
    return report


def main():
    if not os.environ.get("HF_TOKEN"):
        logger.error("HF_TOKEN is not set; cannot reach the models.")
        raise SystemExit(1)

    configs = all_config_import(PROJECT_ROOT / "configs", True, **os.environ)
    logger.info("Starting model evaluation")
    report = asyncio.run(evaluate_all(configs))

    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Report written to {}", REPORT_PATH)


if __name__ == "__main__":
    main()
