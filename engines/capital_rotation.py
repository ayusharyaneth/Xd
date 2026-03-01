# ============================================================
# CAPITAL ROTATION TRACKER ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, format_currency, shorten_address
from api.dexscreener import TokenPair


logger = get_logger("rotation_engine")


@dataclass
class CapitalRotation:
    """Represents detected capital rotation"""
    rotation_id: str
    source_token: str
    target_token: str
    exit_wallets: List[str]
    entry_wallets: List[str]
    overlap_wallets: List[str]
    exit_volume: float
    entry_volume: float
    rotation_window_seconds: int
    detection_time: int
    confidence: float
    significance: str


@dataclass
class RotationSignal:
    """Signal for capital rotation opportunity"""
    token_address: str
    signal_type: str  # 'incoming', 'outgoing'
    strength: float  # 0-100
    related_tokens: List[str]
    whale_overlap: int
    volume_estimate: float
    urgency: str  # 'low', 'medium', 'high'


class CapitalRotationTracker:
    """Track capital rotation between tokens"""
    
    def __init__(self):
        self.config = get_config()
        self.rotation_config = self.config.strategy.capital_rotation
        self._token_exits: Dict[str, List[Dict]] = defaultdict(list)
        self._token_entries: Dict[str, List[Dict]] = defaultdict(list)
        self._detected_rotations: List[CapitalRotation] = []
        self._wallet_token_positions: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
    
    async def track_exit(
        self,
        token_address: str,
        wallet: str,
        amount_usd: float,
        timestamp: int,
        price_at_exit: float
    ):
        """Track a token exit"""
        
        window = self.rotation_config.detection_window
        window_start = timestamp - (window.exit_detection_minutes * 60)
        
        async with self._lock:
            # Clean old exits
            self._token_exits[token_address] = [
                e for e in self._token_exits[token_address]
                if e['timestamp'] > window_start
            ]
            
            # Add new exit
            self._token_exits[token_address].append({
                'wallet': wallet,
                'amount': amount_usd,
                'timestamp': timestamp,
                'price': price_at_exit
            })
            
            # Update wallet positions
            self._wallet_token_positions[wallet].discard(token_address)
    
    async def track_entry(
        self,
        token_address: str,
        wallet: str,
        amount_usd: float,
        timestamp: int,
        price_at_entry: float
    ):
        """Track a token entry"""
        
        window = self.rotation_config.detection_window
        window_start = timestamp - (window.entry_detection_minutes * 60)
        
        async with self._lock:
            # Clean old entries
            self._token_entries[token_address] = [
                e for e in self._token_entries[token_address]
                if e['timestamp'] > window_start
            ]
            
            # Add new entry
            self._token_entries[token_address].append({
                'wallet': wallet,
                'amount': amount_usd,
                'timestamp': timestamp,
                'price': price_at_entry
            })
            
            # Update wallet positions
            self._wallet_token_positions[wallet].add(token_address)
    
    async def detect_rotation(
        self,
        source_token: str,
        target_token: str
    ) -> Optional[CapitalRotation]:
        """Detect capital rotation between two tokens"""
        
        window = self.rotation_config.detection_window
        thresholds = self.rotation_config.thresholds
        
        async with self._lock:
            source_exits = self._token_exits.get(source_token, [])
            target_entries = self._token_entries.get(target_token, [])
        
        if not source_exits or not target_entries:
            return None
        
        # Find overlapping wallets
        exit_wallets = {e['wallet'] for e in source_exits}
        entry_wallets = {e['wallet'] for e in target_entries}
        overlap = exit_wallets & entry_wallets
        
        if len(overlap) < 2:  # Need at least 2 wallets for meaningful rotation
            return None
        
        # Check whale overlap threshold
        whale_overlap_ratio = len(overlap) / max(len(exit_wallets), len(entry_wallets))
        if whale_overlap_ratio < thresholds.whale_overlap_threshold:
            return None
        
        # Calculate volumes
        exit_volume = sum(e['amount'] for e in source_exits)
        entry_volume = sum(e['amount'] for e in target_entries)
        
        if exit_volume < thresholds.min_exit_volume_usd:
            return None
        if entry_volume < thresholds.min_entry_volume_usd:
            return None
        
        # Check time gap
        latest_exit = max(e['timestamp'] for e in source_exits)
        earliest_entry = min(e['timestamp'] for e in target_entries)
        
        time_gap = earliest_entry - latest_exit
        max_gap = window.max_rotation_gap_minutes * 60
        
        if time_gap > max_gap or time_gap < -3600:  # Entry before exit is suspicious
            return None
        
        # Calculate confidence
        confidence = self._calculate_confidence(
            len(overlap),
            whale_overlap_ratio,
            exit_volume,
            entry_volume
        )
        
        # Determine significance
        significance = self._classify_significance(exit_volume, entry_volume, len(overlap))
        
        rotation = CapitalRotation(
            rotation_id=f"rot_{get_timestamp()}_{hash(source_token + target_token) % 10000}",
            source_token=source_token,
            target_token=target_token,
            exit_wallets=list(exit_wallets),
            entry_wallets=list(entry_wallets),
            overlap_wallets=list(overlap),
            exit_volume=exit_volume,
            entry_volume=entry_volume,
            rotation_window_seconds=abs(int(time_gap)),
            detection_time=get_timestamp(),
            confidence=round(confidence, 2),
            significance=significance
        )
        
        # Store rotation
        async with self._lock:
            self._detected_rotations.append(rotation)
            # Keep only recent rotations
            cutoff = get_timestamp() - 86400
            self._detected_rotations = [
                r for r in self._detected_rotations
                if r.detection_time > cutoff
            ]
        
        return rotation
    
    def _calculate_confidence(
        self,
        overlap_count: int,
        overlap_ratio: float,
        exit_volume: float,
        entry_volume: float
    ) -> float:
        """Calculate confidence in rotation detection"""
        
        # More overlapping wallets = higher confidence
        wallet_score = min(1.0, overlap_count / 5)
        
        # Higher overlap ratio = higher confidence
        ratio_score = overlap_ratio
        
        # Volume correlation
        volume_ratio = min(exit_volume, entry_volume) / max(exit_volume, entry_volume)
        volume_score = volume_ratio
        
        # Weighted average
        confidence = (wallet_score * 0.4) + (ratio_score * 0.3) + (volume_score * 0.3)
        
        return confidence
    
    def _classify_significance(
        self,
        exit_volume: float,
        entry_volume: float,
        overlap_count: int
    ) -> str:
        """Classify rotation significance"""
        
        total_volume = exit_volume + entry_volume
        
        if total_volume > 500000 and overlap_count >= 5:
            return "critical"
        elif total_volume > 200000 and overlap_count >= 3:
            return "high"
        elif total_volume > 50000 and overlap_count >= 2:
            return "medium"
        else:
            return "low"
    
    async def scan_for_rotations(
        self,
        token_address: str,
        candidate_tokens: List[str]
    ) -> List[CapitalRotation]:
        """Scan for capital rotations to/from a token"""
        
        rotations = []
        
        for candidate in candidate_tokens:
            if candidate == token_address:
                continue
            
            # Check rotation in both directions
            rotation1 = await self.detect_rotation(token_address, candidate)
            if rotation1:
                rotations.append(rotation1)
            
            rotation2 = await self.detect_rotation(candidate, token_address)
            if rotation2:
                rotations.append(rotation2)
        
        # Sort by confidence
        rotations.sort(key=lambda r: r.confidence, reverse=True)
        
        return rotations
    
    async def generate_rotation_signals(
        self,
        pair: TokenPair
    ) -> List[RotationSignal]:
        """Generate trading signals based on capital rotation"""
        
        signals = []
        
        async with self._lock:
            recent_rotations = [
                r for r in self._detected_rotations
                if r.target_token == pair.token_address
                or r.source_token == pair.token_address
            ]
        
        for rotation in recent_rotations[-5:]:  # Last 5 rotations
            if rotation.target_token == pair.token_address:
                # Incoming rotation - bullish signal
                signal_type = 'incoming'
                strength = min(100, rotation.confidence * 100 + 20)
                urgency = 'high' if rotation.significance in ['critical', 'high'] else 'medium'
            else:
                # Outgoing rotation - bearish signal
                signal_type = 'outgoing'
                strength = min(100, rotation.confidence * 100)
                urgency = 'high' if rotation.significance in ['critical', 'high'] else 'medium'
            
            signal = RotationSignal(
                token_address=pair.token_address,
                signal_type=signal_type,
                strength=round(strength, 2),
                related_tokens=[rotation.source_token, rotation.target_token],
                whale_overlap=len(rotation.overlap_wallets),
                volume_estimate=rotation.entry_volume if signal_type == 'incoming' else rotation.exit_volume,
                urgency=urgency
            )
            
            signals.append(signal)
        
        return signals
    
    async def get_rotation_score(
        self,
        token_address: str
    ) -> Dict[str, Any]:
        """Get capital rotation score for a token"""
        
        async with self._lock:
            incoming = [
                r for r in self._detected_rotations
                if r.target_token == token_address
            ]
            outgoing = [
                r for r in self._detected_rotations
                if r.source_token == token_address
            ]
        
        total_incoming = sum(r.entry_volume for r in incoming)
        total_outgoing = sum(r.exit_volume for r in outgoing)
        
        # Calculate score boost
        scoring = self.rotation_config.scoring
        boost = 0
        
        if incoming:
            boost += scoring.rotation_detected_boost
            
            # Whale involvement boost
            avg_overlap = sum(len(r.overlap_wallets) for r in incoming) / len(incoming)
            if avg_overlap >= 3:
                boost += scoring.whale_involvement_boost
            
            # Volume correlation boost
            if total_incoming > 100000:
                boost += scoring.volume_correlation_boost
        
        return {
            'rotation_score_boost': boost,
            'incoming_rotations': len(incoming),
            'outgoing_rotations': len(outgoing),
            'incoming_volume': round(total_incoming, 2),
            'outgoing_volume': round(total_outgoing, 2),
            'net_flow': round(total_incoming - total_outgoing, 2),
            'recent_rotations': [
                {
                    'type': 'incoming' if r.target_token == token_address else 'outgoing',
                    'token': r.source_token if r.target_token == token_address else r.target_token,
                    'volume': format_currency(r.entry_volume if r.target_token == token_address else r.exit_volume),
                    'wallets': len(r.overlap_wallets),
                    'confidence': r.confidence,
                    'time_ago': get_timestamp() - r.detection_time
                }
                for r in (incoming + outgoing)[-5:]
            ]
        }
    
    async def get_wallet_rotation_history(
        self,
        wallet: str,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get rotation history for a specific wallet"""
        
        cutoff = get_timestamp() - (hours * 3600)
        
        async with self._lock:
            # Find exits by this wallet
            exits = []
            for token, exit_list in self._token_exits.items():
                for e in exit_list:
                    if e['wallet'] == wallet and e['timestamp'] > cutoff:
                        exits.append({
                            'token': token,
                            'amount': e['amount'],
                            'timestamp': e['timestamp']
                        })
            
            # Find entries by this wallet
            entries = []
            for token, entry_list in self._token_entries.items():
                for e in entry_list:
                    if e['wallet'] == wallet and e['timestamp'] > cutoff:
                        entries.append({
                            'token': token,
                            'amount': e['amount'],
                            'timestamp': e['timestamp']
                        })
        
        # Detect rotation patterns
        rotations = []
        for exit_tx in exits:
            for entry_tx in entries:
                time_diff = entry_tx['timestamp'] - exit_tx['timestamp']
                if 0 < time_diff < 3600:  # Within 1 hour
                    rotations.append({
                        'from_token': exit_tx['token'],
                        'to_token': entry_tx['token'],
                        'exit_amount': exit_tx['amount'],
                        'entry_amount': entry_tx['amount'],
                        'time_gap_seconds': time_diff
                    })
        
        return {
            'wallet': shorten_address(wallet),
            'total_exits': len(exits),
            'total_entries': len(entries),
            'suspected_rotations': len(rotations),
            'exit_volume': round(sum(e['amount'] for e in exits), 2),
            'entry_volume': round(sum(e['amount'] for e in entries), 2),
            'rotation_details': rotations[:10]
        }
    
    async def cleanup(self):
        """Clean up old rotation data"""
        
        window = self.rotation_config.detection_window
        cutoff = get_timestamp() - (max(window.exit_detection_minutes, window.entry_detection_minutes) * 60)
        
        async with self._lock:
            # Clean exits
            for token in list(self._token_exits.keys()):
                self._token_exits[token] = [
                    e for e in self._token_exits[token]
                    if e['timestamp'] > cutoff
                ]
                if not self._token_exits[token]:
                    del self._token_exits[token]
            
            # Clean entries
            for token in list(self._token_entries.keys()):
                self._token_entries[token] = [
                    e for e in self._token_entries[token]
                    if e['timestamp'] > cutoff
                ]
                if not self._token_entries[token]:
                    del self._token_entries[token]
            
            # Clean rotations
            rotation_cutoff = get_timestamp() - 86400
            self._detected_rotations = [
                r for r in self._detected_rotations
                if r.detection_time > rotation_cutoff
            ]


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_rotation_tracker: Optional[CapitalRotationTracker] = None


def get_rotation_tracker() -> CapitalRotationTracker:
    """Get or create capital rotation tracker singleton"""
    global _rotation_tracker
    if _rotation_tracker is None:
        _rotation_tracker = CapitalRotationTracker()
    return _rotation_tracker
