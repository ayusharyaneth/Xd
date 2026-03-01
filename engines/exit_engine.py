# ============================================================
# SMART EXIT ASSISTANT ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_currency, format_percentage
from api.dexscreener import TokenPair


logger = get_logger("exit_engine")


class ExitTriggerType(Enum):
    """Types of exit triggers"""
    LIQUIDITY_DROP = "liquidity_drop"
    WHALE_EXIT = "whale_exit"
    RISK_ESCALATION = "risk_escalation"
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    TIME_BASED = "time_based"


class ExitUrgency(Enum):
    """Exit urgency levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ExitSignal:
    """Exit signal recommendation"""
    token_address: str
    trigger_type: ExitTriggerType
    urgency: ExitUrgency
    message: str
    current_price: float
    entry_price: Optional[float]
    current_pnl: Optional[float]
    recommendation: str
    rationale: List[str]
    suggested_action: str
    timestamp: int = field(default_factory=get_timestamp)


@dataclass
class Position:
    """Tracked position"""
    token_address: str
    entry_price: float
    entry_timestamp: int
    position_size: float
    highest_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    trailing_stop_price: float = 0.0
    profit_target_hit: bool = False


class SmartExitAssistant:
    """Provide intelligent exit recommendations"""
    
    def __init__(self):
        self.config = get_config()
        self.exit_config = self.config.strategy.exit_assistant
        self._positions: Dict[str, Position] = {}
        self._exit_history: List[ExitSignal] = []
        self._cooldowns: Dict[str, int] = {}
        self._lock = asyncio.Lock()
    
    async def track_position(
        self,
        token_address: str,
        entry_price: float,
        position_size: float,
        entry_timestamp: Optional[int] = None
    ):
        """Track a new position"""
        
        async with self._lock:
            self._positions[token_address] = Position(
                token_address=token_address,
                entry_price=entry_price,
                entry_timestamp=entry_timestamp or get_timestamp(),
                position_size=position_size,
                highest_price=entry_price,
                current_price=entry_price,
                trailing_stop_price=entry_price * 0.85  # 15% trailing stop
            )
    
    async def update_position(
        self,
        token_address: str,
        current_price: float
    ):
        """Update position with current price"""
        
        async with self._lock:
            if token_address not in self._positions:
                return
            
            position = self._positions[token_address]
            position.current_price = current_price
            
            # Update highest price
            if current_price > position.highest_price:
                position.highest_price = current_price
                # Update trailing stop
                triggers = self.exit_config.triggers
                if triggers.get('profit_target', {}).get('enabled', False):
                    trailing_pct = triggers['profit_target'].get('trailing_stop_percent', 15) / 100
                    position.trailing_stop_price = current_price * (1 - trailing_pct)
            
            # Calculate unrealized PnL
            if position.entry_price > 0:
                position.unrealized_pnl = (
                    (current_price - position.entry_price) / position.entry_price * 100
                )
    
    async def check_exit_signals(
        self,
        pair: TokenPair,
        risk_score: Optional[float] = None,
        whale_movements: Optional[List[Dict]] = None,
        rug_probability: Optional[float] = None
    ) -> List[ExitSignal]:
        """Check for exit signals"""
        
        signals = []
        token_address = pair.token_address
        
        async with self._lock:
            position = self._positions.get(token_address)
        
        # Check cooldown
        if await self._is_on_cooldown(token_address):
            return []
        
        # 1. Liquidity drop check
        liq_signal = await self._check_liquidity_drop(pair, position)
        if liq_signal:
            signals.append(liq_signal)
        
        # 2. Whale exit check
        whale_signal = await self._check_whale_exit(pair, position, whale_movements)
        if whale_signal:
            signals.append(whale_signal)
        
        # 3. Risk escalation check
        risk_signal = await self._check_risk_escalation(pair, position, risk_score, rug_probability)
        if risk_signal:
            signals.append(risk_signal)
        
        # 4. Profit target check
        profit_signal = await self._check_profit_target(pair, position)
        if profit_signal:
            signals.append(profit_signal)
        
        # Set cooldown if signals found
        if signals:
            await self._set_cooldown(
                token_address,
                self.exit_config.alert_cooldown_seconds
            )
            
            # Store signals
            async with self._lock:
                self._exit_history.extend(signals)
                # Keep only recent history
                cutoff = get_timestamp() - 86400
                self._exit_history = [
                    s for s in self._exit_history
                    if s.timestamp > cutoff
                ]
        
        return signals
    
    async def _check_liquidity_drop(
        self,
        pair: TokenPair,
        position: Optional[Position]
    ) -> Optional[ExitSignal]:
        """Check for significant liquidity drop"""
        
        trigger = self.exit_config.triggers.get('liquidity_drop', {})
        if not trigger.get('enabled', False):
            return None
        
        # This would need historical liquidity data
        # For now, check if liquidity is critically low
        threshold = trigger.get('threshold_percent', 20)
        
        if pair.liquidity_usd < 10000:
            return ExitSignal(
                token_address=pair.token_address,
                trigger_type=ExitTriggerType.LIQUIDITY_DROP,
                urgency=ExitUrgency.CRITICAL,
                message="CRITICAL: Liquidity critically low",
                current_price=pair.price_usd,
                entry_price=position.entry_price if position else None,
                current_pnl=position.unrealized_pnl if position else None,
                recommendation="EXIT IMMEDIATELY",
                rationale=[
                    f"Liquidity is critically low (${pair.liquidity_usd:,.2f})",
                    "High slippage on exit",
                    "Possible liquidity removal"
                ],
                suggested_action="Sell entire position immediately"
            )
        
        return None
    
    async def _check_whale_exit(
        self,
        pair: TokenPair,
        position: Optional[Position],
        whale_movements: Optional[List[Dict]]
    ) -> Optional[ExitSignal]:
        """Check for whale exit signals"""
        
        trigger = self.exit_config.triggers.get('whale_exit', {})
        if not trigger.get('enabled', False):
            return None
        
        if not whale_movements:
            return None
        
        min_exit = trigger.get('min_exit_usd', 20000)
        velocity_threshold = trigger.get('exit_velocity_threshold', 3)
        
        # Count recent large sells
        recent_sells = [
            m for m in whale_movements
            if m.get('movement_type') == 'sell'
            and m.get('amount_usd', 0) >= min_exit
        ]
        
        if len(recent_sells) >= velocity_threshold:
            total_sold = sum(m.get('amount_usd', 0) for m in recent_sells)
            
            return ExitSignal(
                token_address=pair.token_address,
                trigger_type=ExitTriggerType.WHALE_EXIT,
                urgency=ExitUrgency.HIGH,
                message=f"ALERT: {len(recent_sells)} whales exiting",
                current_price=pair.price_usd,
                entry_price=position.entry_price if position else None,
                current_pnl=position.unrealized_pnl if position else None,
                recommendation="Consider partial or full exit",
                rationale=[
                    f"{len(recent_sells)} large sells detected",
                    f"Total whale exit volume: ${total_sold:,.2f}",
                    "Smart money may know something"
                ],
                suggested_action="Consider taking profits or reducing position"
            )
        
        return None
    
    async def _check_risk_escalation(
        self,
        pair: TokenPair,
        position: Optional[Position],
        risk_score: Optional[float],
        rug_probability: Optional[float]
    ) -> Optional[ExitSignal]:
        """Check for risk escalation"""
        
        trigger = self.exit_config.triggers.get('risk_escalation', {})
        if not trigger.get('enabled', False):
            return None
        
        risk_jump = trigger.get('risk_score_jump', 20)
        prob_threshold = trigger.get('probability_threshold', 0.5)
        
        signals = []
        
        # Check risk score
        if risk_score and risk_score > 70:
            signals.append(f"Risk score elevated to {risk_score:.0f}/100")
        
        # Check rug probability
        if rug_probability and rug_probability > prob_threshold:
            signals.append(f"Rug probability at {rug_probability:.0%}")
        
        if signals:
            urgency = ExitUrgency.CRITICAL if (rug_probability and rug_probability > 0.7) else ExitUrgency.HIGH
            
            return ExitSignal(
                token_address=pair.token_address,
                trigger_type=ExitTriggerType.RISK_ESCALATION,
                urgency=urgency,
                message="Risk escalation detected",
                current_price=pair.price_usd,
                entry_price=position.entry_price if position else None,
                current_pnl=position.unrealized_pnl if position else None,
                recommendation="Exit recommended" if urgency == ExitUrgency.CRITICAL else "Monitor closely",
                rationale=signals,
                suggested_action="Exit position" if urgency == ExitUrgency.CRITICAL else "Set tight stop loss"
            )
        
        return None
    
    async def _check_profit_target(
        self,
        pair: TokenPair,
        position: Optional[Position]
    ) -> Optional[ExitSignal]:
        """Check profit targets and trailing stops"""
        
        trigger = self.exit_config.triggers.get('profit_target', {})
        if not trigger.get('enabled', False):
            return None
        
        if not position:
            return None
        
        target_multiplier = trigger.get('target_multiplier', 3.0)
        
        current_pnl = position.unrealized_pnl
        
        # Check if profit target hit
        if current_pnl >= (target_multiplier - 1) * 100:
            if not position.profit_target_hit:
                position.profit_target_hit = True
                
                return ExitSignal(
                    token_address=pair.token_address,
                    trigger_type=ExitTriggerType.PROFIT_TARGET,
                    urgency=ExitUrgency.MEDIUM,
                    message=f"Profit target reached: +{current_pnl:.1f}%",
                    current_price=pair.price_usd,
                    entry_price=position.entry_price,
                    current_pnl=current_pnl,
                    recommendation="Consider taking profits",
                    rationale=[
                        f"Target of {target_multiplier}x reached",
                        f"Current PnL: {current_pnl:.1f}%",
                        f"Trailing stop at ${position.trailing_stop_price:.8f}"
                    ],
                    suggested_action="Take partial profits or set trailing stop"
                )
        
        # Check trailing stop
        if position.profit_target_hit and pair.price_usd <= position.trailing_stop_price:
            return ExitSignal(
                token_address=pair.token_address,
                trigger_type=ExitTriggerType.STOP_LOSS,
                urgency=ExitUrgency.HIGH,
                message="Trailing stop triggered",
                current_price=pair.price_usd,
                entry_price=position.entry_price,
                current_pnl=current_pnl,
                recommendation="EXIT NOW",
                rationale=[
                    "Price hit trailing stop",
                    f"Highest price: ${position.highest_price:.8f}",
                    f"Trailing stop: ${position.trailing_stop_price:.8f}"
                ],
                suggested_action="Exit entire position immediately"
            )
        
        return None
    
    async def _is_on_cooldown(self, token_address: str) -> bool:
        """Check if token is on cooldown"""
        async with self._lock:
            return get_timestamp() < self._cooldowns.get(token_address, 0)
    
    async def _set_cooldown(self, token_address: str, duration_seconds: int):
        """Set cooldown for token"""
        async with self._lock:
            self._cooldowns[token_address] = get_timestamp() + duration_seconds
    
    async def get_position_summary(
        self,
        token_address: str
    ) -> Optional[Dict[str, Any]]:
        """Get summary of tracked position"""
        
        async with self._lock:
            position = self._positions.get(token_address)
        
        if not position:
            return None
        
        holding_time = get_timestamp() - position.entry_timestamp
        
        return {
            'entry_price': position.entry_price,
            'current_price': position.current_price,
            'position_size': position.position_size,
            'unrealized_pnl': round(position.unrealized_pnl, 2),
            'unrealized_pnl_usd': round(
                position.position_size * (position.unrealized_pnl / 100),
                2
            ),
            'highest_price': position.highest_price,
            'trailing_stop': position.trailing_stop_price,
            'holding_time_seconds': holding_time,
            'profit_target_hit': position.profit_target_hit
        }
    
    async def get_exit_history(
        self,
        token_address: Optional[str] = None,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get exit signal history"""
        
        cutoff = get_timestamp() - (hours * 3600)
        
        async with self._lock:
            signals = [
                s for s in self._exit_history
                if s.timestamp > cutoff
                and (token_address is None or s.token_address == token_address)
            ]
        
        return [
            {
                'token': s.token_address,
                'trigger': s.trigger_type.value,
                'urgency': s.urgency.value,
                'message': s.message,
                'recommendation': s.recommendation,
                'timestamp': s.timestamp
            }
            for s in signals
        ]
    
    async def close_position(
        self,
        token_address: str,
        exit_price: float
    ) -> Optional[Dict[str, Any]]:
        """Close a tracked position"""
        
        async with self._lock:
            position = self._positions.pop(token_address, None)
        
        if not position:
            return None
        
        realized_pnl = (
            (exit_price - position.entry_price) / position.entry_price * 100
        )
        
        holding_time = get_timestamp() - position.entry_timestamp
        
        return {
            'token_address': token_address,
            'entry_price': position.entry_price,
            'exit_price': exit_price,
            'realized_pnl_percent': round(realized_pnl, 2),
            'realized_pnl_usd': round(
                position.position_size * (realized_pnl / 100),
                2
            ),
            'holding_time_seconds': holding_time,
            'position_size': position.position_size
        }
    
    async def cleanup(self):
        """Clean up old data"""
        
        cutoff = get_timestamp() - (7 * 86400)  # 7 days
        
        async with self._lock:
            # Clean old positions
            old_positions = [
                addr for addr, pos in self._positions.items()
                if pos.entry_timestamp < cutoff
            ]
            for addr in old_positions:
                del self._positions[addr]
            
            # Clean old history
            self._exit_history = [
                s for s in self._exit_history
                if s.timestamp > cutoff
            ]
            
            # Clean expired cooldowns
            current_time = get_timestamp()
            self._cooldowns = {
                k: v for k, v in self._cooldowns.items()
                if v > current_time
            }


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_exit_assistant: Optional[SmartExitAssistant] = None


def get_exit_assistant() -> SmartExitAssistant:
    """Get or create exit assistant singleton"""
    global _exit_assistant
    if _exit_assistant is None:
        _exit_assistant = SmartExitAssistant()
    return _exit_assistant
