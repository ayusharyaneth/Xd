# ============================================================
# WALLET CLUSTER DETECTION ENGINE
# ============================================================

import asyncio
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import statistics

from config.settings import get_config
from utils.logger import get_logger
from utils.helpers import get_timestamp, shorten_address


logger = get_logger("cluster_engine")


@dataclass
class WalletCluster:
    """Represents a detected wallet cluster"""
    cluster_id: str
    wallets: List[str]
    suspicion_score: float
    indicators: List[str]
    common_funding_sources: List[str]
    formation_time: int
    last_activity: int
    confidence: float


@dataclass
class ClusterAnalysis:
    """Analysis result for wallet clustering"""
    clusters: List[WalletCluster]
    total_wallets_analyzed: int
    clustered_wallets: int
    cluster_rate: float
    highest_suspicion_score: float
    risk_assessment: str
    recommendations: List[str]


class WalletClusterDetector:
    """Detect clusters of related wallets"""
    
    def __init__(self):
        self.config = get_config()
        self.cluster_config = self.config.strategy.wallet_cluster
        self._clusters: Dict[str, WalletCluster] = {}
        self._wallet_data: Dict[str, Dict] = {}
        self._funding_graph: Dict[str, Set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()
    
    async def analyze_wallets(
        self,
        wallets: List[str],
        transaction_data: Optional[List[Dict]] = None,
        funding_data: Optional[Dict[str, List[str]]] = None
    ) -> ClusterAnalysis:
        """Analyze wallets for clustering patterns"""
        
        if len(wallets) < self.cluster_config.detection.min_cluster_size:
            return ClusterAnalysis(
                clusters=[],
                total_wallets_analyzed=len(wallets),
                clustered_wallets=0,
                cluster_rate=0.0,
                highest_suspicion_score=0.0,
                risk_assessment="low",
                recommendations=["Insufficient wallets for cluster analysis"]
            )
        
        # Build funding graph
        if funding_data:
            await self._build_funding_graph(wallets, funding_data)
        
        # Detect clusters
        clusters = await self._detect_clusters(wallets, transaction_data)
        
        # Calculate metrics
        clustered_wallets = sum(len(c.wallets) for c in clusters)
        cluster_rate = clustered_wallets / len(wallets) if wallets else 0
        
        highest_suspicion = max(
            (c.suspicion_score for c in clusters),
            default=0
        )
        
        risk_assessment = self._assess_risk(clusters, cluster_rate)
        recommendations = self._generate_recommendations(clusters, risk_assessment)
        
        return ClusterAnalysis(
            clusters=clusters,
            total_wallets_analyzed=len(wallets),
            clustered_wallets=clustered_wallets,
            cluster_rate=round(cluster_rate, 2),
            highest_suspicion_score=round(highest_suspicion, 2),
            risk_assessment=risk_assessment,
            recommendations=recommendations
        )
    
    async def _build_funding_graph(
        self,
        wallets: List[str],
        funding_data: Dict[str, List[str]]
    ):
        """Build graph of wallet funding relationships"""
        
        async with self._lock:
            for wallet in wallets:
                sources = funding_data.get(wallet, [])
                self._funding_graph[wallet] = set(sources)
    
    async def _detect_clusters(
        self,
        wallets: List[str],
        transaction_data: Optional[List[Dict]]
    ) -> List[WalletCluster]:
        """Detect wallet clusters"""
        
        clusters = []
        processed = set()
        
        detection = self.cluster_config.detection
        min_cluster_size = detection.min_cluster_size
        
        for wallet in wallets:
            if wallet in processed:
                continue
            
            # Find similar wallets
            similar_wallets = await self._find_similar_wallets(
                wallet,
                wallets,
                transaction_data
            )
            
            if len(similar_wallets) >= min_cluster_size:
                cluster = await self._create_cluster(
                    similar_wallets,
                    transaction_data
                )
                
                if cluster.suspicion_score > 30:  # Only keep suspicious clusters
                    clusters.append(cluster)
                
                processed.update(similar_wallets)
        
        # Sort by suspicion score
        clusters.sort(key=lambda c: c.suspicion_score, reverse=True)
        
        return clusters
    
    async def _find_similar_wallets(
        self,
        target_wallet: str,
        all_wallets: List[str],
        transaction_data: Optional[List[Dict]]
    ) -> List[str]:
        """Find wallets similar to target"""
        
        similar = [target_wallet]
        detection = self.cluster_config.detection
        
        for wallet in all_wallets:
            if wallet == target_wallet:
                continue
            
            similarity_score = 0.0
            checks = 0
            
            # Check funding similarity
            async with self._lock:
                target_funding = self._funding_graph.get(target_wallet, set())
                wallet_funding = self._funding_graph.get(wallet, set())
            
            if target_funding and wallet_funding:
                overlap = len(target_funding & wallet_funding)
                union = len(target_funding | wallet_funding)
                if union > 0:
                    funding_similarity = overlap / union
                    if funding_similarity >= detection.funding_similarity_threshold:
                        similarity_score += funding_similarity
                    checks += 1
            
            # Check timing similarity
            if transaction_data:
                timing_sim = await self._calculate_timing_similarity(
                    target_wallet,
                    wallet,
                    transaction_data
                )
                if timing_sim >= detection.timing_similarity_threshold:
                    similarity_score += timing_sim
                checks += 1
            
            # Check trade pattern similarity
            if transaction_data:
                pattern_sim = await self._calculate_pattern_similarity(
                    target_wallet,
                    wallet,
                    transaction_data
                )
                if pattern_sim >= detection.trade_pattern_similarity:
                    similarity_score += pattern_sim
                checks += 1
            
            # Average similarity
            if checks > 0:
                avg_similarity = similarity_score / checks
                if avg_similarity >= 0.6:  # Threshold for similarity
                    similar.append(wallet)
        
        return similar
    
    async def _calculate_timing_similarity(
        self,
        wallet1: str,
        wallet2: str,
        transaction_data: List[Dict]
    ) -> float:
        """Calculate timing similarity between two wallets"""
        
        # Get timestamps for each wallet
        ts1 = [
            tx.get('timestamp', 0)
            for tx in transaction_data
            if tx.get('buyer') == wallet1 or tx.get('seller') == wallet1
        ]
        
        ts2 = [
            tx.get('timestamp', 0)
            for tx in transaction_data
            if tx.get('buyer') == wallet2 or tx.get('seller') == wallet2
        ]
        
        if not ts1 or not ts2:
            return 0.0
        
        # Check for similar timing patterns
        similar_count = 0
        threshold_seconds = 60  # Within 1 minute
        
        for t1 in ts1:
            for t2 in ts2:
                if abs(t1 - t2) <= threshold_seconds:
                    similar_count += 1
                    break
        
        return min(1.0, similar_count / max(len(ts1), len(ts2)))
    
    async def _calculate_pattern_similarity(
        self,
        wallet1: str,
        wallet2: str,
        transaction_data: List[Dict]
    ) -> float:
        """Calculate trade pattern similarity"""
        
        # Get trades for each wallet
        trades1 = [
            tx for tx in transaction_data
            if tx.get('buyer') == wallet1 or tx.get('seller') == wallet1
        ]
        
        trades2 = [
            tx for tx in transaction_data
            if tx.get('buyer') == wallet2 or tx.get('seller') == wallet2
        ]
        
        if not trades1 or not trades2:
            return 0.0
        
        # Compare trade sizes
        sizes1 = [tx.get('amount_usd', 0) for tx in trades1]
        sizes2 = [tx.get('amount_usd', 0) for tx in trades2]
        
        if not sizes1 or not sizes2:
            return 0.0
        
        avg1 = statistics.mean(sizes1) if sizes1 else 0
        avg2 = statistics.mean(sizes2) if sizes2 else 0
        
        if avg1 == 0 or avg2 == 0:
            return 0.0
        
        # Similar average trade size
        size_similarity = 1 - abs(avg1 - avg2) / max(avg1, avg2)
        
        # Compare trade frequency
        freq_similarity = 1 - abs(len(trades1) - len(trades2)) / max(len(trades1), len(trades2))
        
        return (size_similarity * 0.6) + (freq_similarity * 0.4)
    
    async def _create_cluster(
        self,
        wallets: List[str],
        transaction_data: Optional[List[Dict]]
    ) -> WalletCluster:
        """Create a wallet cluster with suspicion score"""
        
        cluster_id = f"cluster_{get_timestamp()}_{hash(tuple(wallets)) % 10000}"
        
        # Calculate suspicion indicators
        indicators = []
        suspicion_score = 0.0
        
        suspicion = self.cluster_config.suspicion_indicators
        
        # Check for same funding source
        async with self._lock:
            common_funding = set.intersection(*[
                self._funding_graph.get(w, set())
                for w in wallets
            ]) if all(self._funding_graph.get(w) for w in wallets) else set()
        
        if common_funding:
            indicators.append("Same funding source detected")
            suspicion_score += suspicion.same_funding_source
        
        # Check for coordinated trading
        if transaction_data and len(wallets) >= 3:
            coordination = await self._detect_coordination(wallets, transaction_data)
            if coordination:
                indicators.append("Coordinated trading pattern detected")
                suspicion_score += suspicion.coordinated_trading
        
        # Check for similar position sizes
        if transaction_data:
            similar_sizes = await self._check_similar_sizes(wallets, transaction_data)
            if similar_sizes:
                indicators.append("Similar position sizes")
                suspicion_score += suspicion.similar_position_sizes
        
        # Check for new wallets
        new_wallet_count = sum(
            1 for w in wallets
            if self._wallet_data.get(w, {}).get('is_new', False)
        )
        if new_wallet_count > len(wallets) * 0.5:
            indicators.append(f"Many new wallets ({new_wallet_count}/{len(wallets)})")
            suspicion_score += suspicion.new_wallet_creation * (new_wallet_count / len(wallets))
        
        # Calculate confidence
        confidence = min(1.0, len(indicators) * 0.25 + 0.25)
        
        return WalletCluster(
            cluster_id=cluster_id,
            wallets=wallets,
            suspicion_score=round(min(100, suspicion_score), 2),
            indicators=indicators,
            common_funding_sources=list(common_funding)[:5],
            formation_time=get_timestamp(),
            last_activity=get_timestamp(),
            confidence=round(confidence, 2)
        )
    
    async def _detect_coordination(
        self,
        wallets: List[str],
        transaction_data: List[Dict]
    ) -> bool:
        """Detect coordinated trading among wallets"""
        
        # Group transactions by time window (5 minutes)
        time_windows = defaultdict(list)
        
        for tx in transaction_data:
            wallet = tx.get('buyer') or tx.get('seller', '')
            if wallet in wallets:
                window = tx.get('timestamp', 0) // 300  # 5-min windows
                time_windows[window].append(wallet)
        
        # Check for windows with multiple wallets from cluster
        coordinated_windows = 0
        for window, window_wallets in time_windows.items():
            cluster_in_window = sum(1 for w in window_wallets if w in wallets)
            if cluster_in_window >= len(wallets) * 0.5:
                coordinated_windows += 1
        
        return coordinated_windows >= 2
    
    async def _check_similar_sizes(
        self,
        wallets: List[str],
        transaction_data: List[Dict]
    ) -> bool:
        """Check if wallets have similar position sizes"""
        
        wallet_volumes = defaultdict(float)
        
        for tx in transaction_data:
            wallet = tx.get('buyer') or tx.get('seller', '')
            if wallet in wallets:
                wallet_volumes[wallet] += tx.get('amount_usd', 0)
        
        if len(wallet_volumes) < 2:
            return False
        
        volumes = list(wallet_volumes.values())
        if not volumes:
            return False
        
        avg_volume = statistics.mean(volumes)
        if avg_volume == 0:
            return False
        
        # Check if most volumes are within 50% of average
        similar_count = sum(
            1 for v in volumes
            if abs(v - avg_volume) / avg_volume < 0.5
        )
        
        return similar_count >= len(volumes) * 0.6
    
    def _assess_risk(self, clusters: List[WalletCluster], cluster_rate: float) -> str:
        """Assess overall risk from clusters"""
        
        if not clusters:
            return "low"
        
        high_suspicion = sum(1 for c in clusters if c.suspicion_score > 60)
        
        if high_suspicion >= 2 or cluster_rate > 0.5:
            return "critical"
        elif high_suspicion == 1 or cluster_rate > 0.3:
            return "high"
        elif cluster_rate > 0.1:
            return "medium"
        else:
            return "low"
    
    def _generate_recommendations(
        self,
        clusters: List[WalletCluster],
        risk_assessment: str
    ) -> List[str]:
        """Generate recommendations based on cluster analysis"""
        
        recommendations = []
        
        if risk_assessment == "critical":
            recommendations.append("URGENT: High probability of coordinated manipulation")
            recommendations.append("Avoid this token - significant wash trading risk")
        elif risk_assessment == "high":
            recommendations.append("Suspicious wallet clustering detected")
            recommendations.append("Exercise extreme caution - possible coordinated activity")
        elif risk_assessment == "medium":
            recommendations.append("Some wallet clustering observed")
            recommendations.append("Monitor for unusual trading patterns")
        else:
            recommendations.append("No significant clustering detected")
        
        # Specific recommendations based on indicators
        for cluster in clusters[:3]:
            if "Same funding source" in cluster.indicators:
                recommendations.append(
                    f"Cluster {shorten_address(cluster.cluster_id)} shares funding sources"
                )
            if "Coordinated trading" in cluster.indicators:
                recommendations.append(
                    f"Detected coordinated trading in cluster"
                )
        
        return recommendations
    
    async def update_wallet_data(
        self,
        wallet: str,
        data: Dict[str, Any]
    ):
        """Update stored data for a wallet"""
        async with self._lock:
            self._wallet_data[wallet] = data
    
    async def get_cluster_details(
        self,
        cluster_id: str
    ) -> Optional[WalletCluster]:
        """Get details for a specific cluster"""
        async with self._lock:
            return self._clusters.get(cluster_id)
    
    async def cleanup(self):
        """Clean up old cluster data"""
        cutoff = get_timestamp() - (3 * 86400)  # 3 days
        
        async with self._lock:
            old_clusters = [
                cid for cid, c in self._clusters.items()
                if c.last_activity < cutoff
            ]
            
            for cid in old_clusters:
                del self._clusters[cid]
            
            if old_clusters:
                logger.info(f"Cleaned up {len(old_clusters)} old clusters")


# ============================================================
# SINGLETON INSTANCE
# ============================================================

_cluster_detector: Optional[WalletClusterDetector] = None


def get_cluster_detector() -> WalletClusterDetector:
    """Get or create wallet cluster detector singleton"""
    global _cluster_detector
    if _cluster_detector is None:
        _cluster_detector = WalletClusterDetector()
    return _cluster_detector
