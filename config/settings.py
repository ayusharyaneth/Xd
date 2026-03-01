# ============================================================
# CONFIGURATION SETTINGS - Pydantic Models
# ============================================================

import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import yaml

# Load environment variables
load_dotenv()


# ============================================================
# YAML Configuration Models
# ============================================================

class Stage1Filter(BaseModel):
    min_liquidity_usd: float = 10000
    min_volume_24h_usd: float = 5000
    min_market_cap_usd: float = 50000
    max_token_age_hours: int = 72
    min_holders: int = 50
    excluded_chains: List[str] = Field(default_factory=list)


class Stage2Filter(BaseModel):
    min_price_change_5m: float = -20
    max_price_change_5m: float = 100
    min_transactions_5m: int = 10
    min_buy_ratio: float = 0.55
    require_verified_contract: bool = False


class FilterConfig(BaseModel):
    stage1: Stage1Filter = Field(default_factory=Stage1Filter)
    stage2: Stage2Filter = Field(default_factory=Stage2Filter)


class RiskScoringWeights(BaseModel):
    liquidity_risk: float = 0.25
    volume_risk: float = 0.20
    holder_concentration: float = 0.20
    contract_risk: float = 0.15
    developer_risk: float = 0.20


class RiskScoringThresholds(BaseModel):
    low_risk_max: int = 30
    medium_risk_max: int = 60
    high_risk_max: int = 85
    critical_risk_max: int = 100


class RiskScoringConfig(BaseModel):
    weights: RiskScoringWeights = Field(default_factory=RiskScoringWeights)
    thresholds: RiskScoringThresholds = Field(default_factory=RiskScoringThresholds)
    factors: Dict[str, float] = Field(default_factory=dict)


class VolumeAuthenticityConfig(BaseModel):
    min_natural_volume_ratio: float = 0.6
    max_wash_trade_score: float = 0.4
    suspicious_patterns: List[str] = Field(default_factory=list)
    metrics: Dict[str, float] = Field(default_factory=dict)
    scoring_weights: Dict[str, float] = Field(default_factory=dict)


class DeveloperReputationConfig(BaseModel):
    track_history_days: int = 90
    min_previous_tokens: int = 1
    scoring_factors: Dict[str, int] = Field(default_factory=dict)
    red_flags: List[str] = Field(default_factory=list)
    reputation_thresholds: Dict[str, int] = Field(default_factory=dict)


class WalletTier(BaseModel):
    min_usd: float
    weight: float


class BuyQualityConfig(BaseModel):
    wallet_tiers: Dict[str, WalletTier] = Field(default_factory=dict)
    quality_factors: Dict[str, float] = Field(default_factory=dict)
    min_quality_score: int = 40
    high_quality_threshold: int = 75


class WhaleThresholds(BaseModel):
    min_wallet_value_usd: float = 50000
    min_single_buy_usd: float = 10000
    min_token_holdings_usd: float = 5000


class WhaleTracking(BaseModel):
    max_wallets_to_track: int = 100
    position_update_interval_seconds: int = 60
    significant_movement_threshold: float = 0.1


class AlertCondition(BaseModel):
    threshold_usd: float
    cooldown_seconds: int


class WhaleAlertConditions(BaseModel):
    large_buy: AlertCondition = Field(default_factory=lambda: AlertCondition(threshold_usd=20000, cooldown_seconds=300))
    large_sell: AlertCondition = Field(default_factory=lambda: AlertCondition(threshold_usd=15000, cooldown_seconds=300))
    position_accumulation: Dict[str, Any] = Field(default_factory=dict)


class WhaleDetectionConfig(BaseModel):
    thresholds: WhaleThresholds = Field(default_factory=WhaleThresholds)
    tracking: WhaleTracking = Field(default_factory=WhaleTracking)
    alert_conditions: WhaleAlertConditions = Field(default_factory=WhaleAlertConditions)


class EarlyBuyerTracking(BaseModel):
    first_n_buyers: int = 50
    track_duration_minutes: int = 60
    profit_check_interval_seconds: int = 120


class EarlyBuyerThresholds(BaseModel):
    significant_profit_multiplier: float = 2.0
    distribution_warning_percent: int = 50
    early_sell_warning_count: int = 10


class EarlyBuyerScoring(BaseModel):
    unrealized_pnl_weight: float = 0.4
    holding_behavior_weight: float = 0.35
    sell_pressure_weight: float = 0.25


class EarlyBuyerConfig(BaseModel):
    tracking: EarlyBuyerTracking = Field(default_factory=EarlyBuyerTracking)
    thresholds: EarlyBuyerThresholds = Field(default_factory=EarlyBuyerThresholds)
    scoring: EarlyBuyerScoring = Field(default_factory=EarlyBuyerScoring)


class WalletClusterDetection(BaseModel):
    min_cluster_size: int = 3
    max_wallet_age_days: int = 7
    funding_similarity_threshold: float = 0.85
    timing_similarity_threshold: float = 0.75
    trade_pattern_similarity: float = 0.80


class WalletClusterSuspicion(BaseModel):
    same_funding_source: int = 30
    coordinated_trading: int = 40
    similar_position_sizes: int = 20
    new_wallet_creation: int = 10


class WalletClusterConfig(BaseModel):
    detection: WalletClusterDetection = Field(default_factory=WalletClusterDetection)
    suspicion_indicators: WalletClusterSuspicion = Field(default_factory=WalletClusterSuspicion)
    scoring_weights: Dict[str, float] = Field(default_factory=dict)


class CapitalRotationWindow(BaseModel):
    exit_detection_minutes: int = 30
    entry_detection_minutes: int = 30
    max_rotation_gap_minutes: int = 15


class CapitalRotationThresholds(BaseModel):
    min_exit_volume_usd: float = 25000
    min_entry_volume_usd: float = 25000
    whale_overlap_threshold: float = 0.3


class CapitalRotationScoring(BaseModel):
    rotation_detected_boost: int = 15
    whale_involvement_boost: int = 10
    volume_correlation_boost: int = 5


class CapitalRotationConfig(BaseModel):
    detection_window: CapitalRotationWindow = Field(default_factory=CapitalRotationWindow)
    thresholds: CapitalRotationThresholds = Field(default_factory=CapitalRotationThresholds)
    scoring: CapitalRotationScoring = Field(default_factory=CapitalRotationScoring)


class RugProbabilityIndicators(BaseModel):
    liquidity_removal_risk: float = 0.30
    holder_concentration_risk: float = 0.25
    contract_risk: float = 0.20
    developer_risk: float = 0.15
    volume_manipulation_risk: float = 0.10


class WarningLevel(BaseModel):
    max_probability: float
    action: str


class RugProbabilityConfig(BaseModel):
    indicators: RugProbabilityIndicators = Field(default_factory=RugProbabilityIndicators)
    warning_levels: Dict[str, WarningLevel] = Field(default_factory=dict)
    early_warning_signs: List[str] = Field(default_factory=list)


class ExitTrigger(BaseModel):
    enabled: bool
    threshold_percent: Optional[int] = None
    min_exit_usd: Optional[float] = None
    exit_velocity_threshold: Optional[int] = None
    risk_score_jump: Optional[int] = None
    probability_threshold: Optional[float] = None
    target_multiplier: Optional[float] = None
    trailing_stop_percent: Optional[int] = None


class ExitAssistantConfig(BaseModel):
    triggers: Dict[str, ExitTrigger] = Field(default_factory=dict)
    alert_cooldown_seconds: int = 180


class BufferWindow(BaseModel):
    enabled: bool = True
    window_seconds: int = 300
    max_alerts_in_window: int = 50


class AlertRankingConfig(BaseModel):
    buffer_window: BufferWindow = Field(default_factory=BufferWindow)
    composite_score_weights: Dict[str, float] = Field(default_factory=dict)
    ranking_limits: Dict[str, int] = Field(default_factory=dict)


class RegimeIndicators(BaseModel):
    price_trend: str
    volume_trend: str
    sentiment: str


class ThresholdAdjustments(BaseModel):
    risk_tolerance: float
    volume_requirement: float


class RegimeType(BaseModel):
    indicators: RegimeIndicators
    threshold_adjustments: ThresholdAdjustments


class MarketRegimeConfig(BaseModel):
    analysis_window: Dict[str, int] = Field(default_factory=dict)
    regime_types: Dict[str, RegimeType] = Field(default_factory=dict)


class WatchActivation(BaseModel):
    inline_button_enabled: bool = True
    command_enabled: bool = True


class WatchMonitoring(BaseModel):
    update_interval_seconds: int = 60
    expiry_minutes: int = 30
    max_concurrent: int = 50


class WatchEscalation(BaseModel):
    price_change_threshold: int = 20
    volume_spike_threshold: float = 3.0
    risk_score_change: int = 15
    alert_on_escalation: bool = True


class WatchNotifications(BaseModel):
    send_periodic_updates: bool = True
    send_escalation_alerts: bool = True
    include_all_metrics: bool = False


class WatchModeConfig(BaseModel):
    activation: WatchActivation = Field(default_factory=WatchActivation)
    monitoring: WatchMonitoring = Field(default_factory=WatchMonitoring)
    escalation: WatchEscalation = Field(default_factory=WatchEscalation)
    notifications: WatchNotifications = Field(default_factory=WatchNotifications)


class SelfDefenseMonitoring(BaseModel):
    check_interval_seconds: int = 30
    metrics_window_seconds: int = 300


class ActivationThresholds(BaseModel):
    api_error_rate: float = 0.1
    avg_latency_ms: int = 5000
    memory_usage_mb: int = 1800
    cpu_usage_percent: int = 85
    consecutive_failures: int = 5


class SafeModeActions(BaseModel):
    reduce_poll_frequency: bool = True
    pause_non_critical_features: bool = True
    increase_cooldowns: bool = True
    alert_admins: bool = True


class SelfDefenseRecovery(BaseModel):
    auto_recovery_enabled: bool = True
    recovery_check_interval_seconds: int = 60
    exit_safe_mode_after_seconds: int = 300


class SelfDefenseConfig(BaseModel):
    monitoring: SelfDefenseMonitoring = Field(default_factory=SelfDefenseMonitoring)
    activation_thresholds: ActivationThresholds = Field(default_factory=ActivationThresholds)
    safe_mode_actions: SafeModeActions = Field(default_factory=SafeModeActions)
    recovery: SelfDefenseRecovery = Field(default_factory=SelfDefenseRecovery)


class HealthChecks(BaseModel):
    api_connectivity: bool = True
    bot_responsiveness: bool = True
    memory_usage: bool = True
    disk_space: bool = True
    database_connection: bool = False


class HealthThresholds(BaseModel):
    max_memory_percent: int = 85
    min_disk_space_gb: int = 5
    max_response_time_ms: int = 2000


class HealthCheckConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = 300
    checks: HealthChecks = Field(default_factory=HealthChecks)
    thresholds: HealthThresholds = Field(default_factory=HealthThresholds)


class StrategyConfig(BaseModel):
    filters: FilterConfig = Field(default_factory=FilterConfig)
    risk_scoring: RiskScoringConfig = Field(default_factory=RiskScoringConfig)
    volume_authenticity: VolumeAuthenticityConfig = Field(default_factory=VolumeAuthenticityConfig)
    developer_reputation: DeveloperReputationConfig = Field(default_factory=DeveloperReputationConfig)
    buy_quality: BuyQualityConfig = Field(default_factory=BuyQualityConfig)
    whale_detection: WhaleDetectionConfig = Field(default_factory=WhaleDetectionConfig)
    early_buyer: EarlyBuyerConfig = Field(default_factory=EarlyBuyerConfig)
    wallet_cluster: WalletClusterConfig = Field(default_factory=WalletClusterConfig)
    capital_rotation: CapitalRotationConfig = Field(default_factory=CapitalRotationConfig)
    rug_probability: RugProbabilityConfig = Field(default_factory=RugProbabilityConfig)
    exit_assistant: ExitAssistantConfig = Field(default_factory=ExitAssistantConfig)
    alert_ranking: AlertRankingConfig = Field(default_factory=AlertRankingConfig)
    market_regime: MarketRegimeConfig = Field(default_factory=MarketRegimeConfig)
    watch_mode: WatchModeConfig = Field(default_factory=WatchModeConfig)
    self_defense: SelfDefenseConfig = Field(default_factory=SelfDefenseConfig)
    health_check: HealthCheckConfig = Field(default_factory=HealthCheckConfig)


# ============================================================
# Environment Settings (Pydantic BaseSettings)
# ============================================================

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Telegram Bot Tokens
    SIGNAL_BOT_TOKEN: str = Field(default="", env="SIGNAL_BOT_TOKEN")
    ALERT_BOT_TOKEN: str = Field(default="", env="ALERT_BOT_TOKEN")
    
    # Chat IDs
    SIGNAL_CHAT_ID: str = Field(default="", env="SIGNAL_CHAT_ID")
    ALERT_CHAT_ID: str = Field(default="", env="ALERT_CHAT_ID")
    ADMIN_CHAT_ID: str = Field(default="", env="ADMIN_CHAT_ID")
    
    # API Configuration
    DEXSCREENER_API_BASE: str = Field(default="https://api.dexscreener.com/latest", env="DEXSCREENER_API_BASE")
    DEXSCREENER_PAIRS_ENDPOINT: str = Field(default="/dex/pairs", env="DEXSCREENER_PAIRS_ENDPOINT")
    DEXSCREENER_TOKENS_ENDPOINT: str = Field(default="/dex/tokens", env="DEXSCREENER_TOKENS_ENDPOINT")
    
    # RPC Configuration (support multiple common naming conventions)
    RPC_ENDPOINT: str = Field(default="https://api.mainnet-beta.solana.com", env="RPC_ENDPOINT")
    RPC_BACKUP_ENDPOINT: str = Field(default="https://solana-api.projectserum.com", env="RPC_BACKUP_ENDPOINT")
    rpc_base_url: Optional[str] = Field(default=None, env="rpc_base_url")  # Alternative name
    
    # Polling Configuration (support multiple common naming conventions)
    POLL_INTERVAL_SECONDS: int = Field(default=30, env="POLL_INTERVAL_SECONDS")
    poll_interval: Optional[int] = Field(default=None, env="poll_interval")  # Alternative name
    WATCH_UPDATE_INTERVAL_SECONDS: int = Field(default=60, env="WATCH_UPDATE_INTERVAL_SECONDS")
    HEALTH_CHECK_INTERVAL_SECONDS: int = Field(default=300, env="HEALTH_CHECK_INTERVAL_SECONDS")
    
    # System Configuration
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="logs/dex_intel.log", env="LOG_FILE")
    MAX_MEMORY_MB: int = Field(default=2048, env="MAX_MEMORY_MB")
    MAX_CPU_PERCENT: int = Field(default=80, env="MAX_CPU_PERCENT")
    
    # Self-Defense Thresholds (override YAML)
    SAFE_MODE_API_ERROR_THRESHOLD: int = Field(default=10, env="SAFE_MODE_API_ERROR_THRESHOLD")
    SAFE_MODE_LATENCY_THRESHOLD_MS: int = Field(default=5000, env="SAFE_MODE_LATENCY_THRESHOLD_MS")
    SAFE_MODE_MEMORY_THRESHOLD_MB: int = Field(default=1800, env="SAFE_MODE_MEMORY_THRESHOLD_MB")
    
    # Watch Mode Settings
    WATCH_EXPIRY_MINUTES: int = Field(default=30, env="WATCH_EXPIRY_MINUTES")
    WATCH_ESCALATION_THRESHOLD: int = Field(default=3, env="WATCH_ESCALATION_THRESHOLD")
    MAX_CONCURRENT_WATCHES: int = Field(default=50, env="MAX_CONCURRENT_WATCHES")
    
    # Cooldown Settings
    ALERT_COOLDOWN_SECONDS: int = Field(default=300, env="ALERT_COOLDOWN_SECONDS")
    TOKEN_COOLDOWN_MINUTES: int = Field(default=60, env="TOKEN_COOLDOWN_MINUTES")
    
    # Feature Flags
    ENABLE_SELF_DEFENSE: bool = Field(default=True, env="ENABLE_SELF_DEFENSE")
    ENABLE_WATCH_MODE: bool = Field(default=True, env="ENABLE_WATCH_MODE")
    ENABLE_EXIT_ASSISTANT: bool = Field(default=True, env="ENABLE_EXIT_ASSISTANT")
    ENABLE_WHALE_DETECTION: bool = Field(default=True, env="ENABLE_WHALE_DETECTION")
    ENABLE_CLUSTER_DETECTION: bool = Field(default=True, env="ENABLE_CLUSTER_DETECTION")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra fields in .env
        case_sensitive = False  # Allow case-insensitive matching


# ============================================================
# Configuration Loader
# ============================================================

class ConfigManager:
    """Manages both YAML and environment configuration"""
    
    def __init__(self, yaml_path: str = "strategy.yaml"):
        self.yaml_path = yaml_path
        self._settings = Settings()
        self._strategy = self._load_strategy()
    
    def _load_strategy(self) -> StrategyConfig:
        """Load strategy configuration from YAML file"""
        if not os.path.exists(self.yaml_path):
            return StrategyConfig()
        
        try:
            with open(self.yaml_path, 'r') as f:
                yaml_data = yaml.safe_load(f)
            return StrategyConfig(**yaml_data)
        except Exception as e:
            print(f"Error loading strategy.yaml: {e}. Using defaults.")
            return StrategyConfig()
    
    @property
    def settings(self) -> Settings:
        """Get environment settings"""
        return self._settings
    
    @property
    def strategy(self) -> StrategyConfig:
        """Get strategy configuration"""
        return self._strategy
    
    def reload_strategy(self):
        """Reload strategy configuration from YAML"""
        self._strategy = self._load_strategy()


# Global configuration instance
_config_manager: Optional[ConfigManager] = None


def get_config() -> ConfigManager:
    """Get or create global configuration manager"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def reload_config():
    """Reload configuration"""
    global _config_manager
    if _config_manager:
        _config_manager.reload_strategy()
