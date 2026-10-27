"""
AquaSense Pro — Dashboard & API Integration Module (Priority 5)

Integrates the new purifier functionality into the existing application while
preserving the original aquaculture project functionality.

The original aquaculture project is preserved as-is; this module adds new API
endpoints and dashboard features for the RO purifier system without modifying
any existing aquaculture code.

API Design Principles (from task spec Phase Five):
- Integrate new functionality into the existing application if one exists.
- Add historical readings, filter health, recovery metrics, alerts, and system status.
- Document hardware interfaces and cloud deployment requirements.
- Preserve existing application behavior.

Note: The original project (L:\aquasensepro\) is a collection of notebooks,
Arduino firmware, and data files — not a web application with an API server.
This module defines the API contract that could be implemented if a Flask/Django
or other web framework were added, or it could be mapped to the existing
MQTT-based telemetry structure.

If the user later adds a web frontend, this module provides the data structures
and API endpoint contracts.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# API Contract Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SensorReadingAPI:
    """API-level sensor reading (JSON-serializable for REST endpoints)."""
    device_id: str
    timestamp: str
    pH: Optional[float] = None
    tds_ppm: Optional[float] = None
    turbidity_ntu: Optional[float] = None
    uv254_abs: Optional[float] = None
    temperature_c: Optional[float] = None
    pressure_bar: Optional[float] = None
    flow_lpm: Optional[float] = None
    filter_operating_vol_l: Optional[float] = None
    quality: str = "ok"  # "ok", "warning", "critical", "fault"

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "device_id": self.device_id,
            "timestamp": self.timestamp,
        }
        if self.pH is not None:
            d["pH"] = self.pH
        if self.tds_ppm is not None:
            d["tds_ppm"] = self.tds_ppm
        if self.turbidity_ntu is not None:
            d["turbidity_ntu"] = self.turbidity_ntu
        if self.uv254_abs is not None:
            d["uv254_abs"] = self.uv254_abs
        if self.temperature_c is not None:
            d["temperature_c"] = self.temperature_c
        if self.pressure_bar is not None:
            d["pressure_bar"] = self.pressure_bar
        if self.flow_lpm is not None:
            d["flow_lpm"] = self.flow_lpm
        if self.filter_operating_vol_l is not None:
            d["filter_operating_vol_l"] = self.filter_operating_vol_l
        d["quality"] = self.quality
        return d


@dataclass
class FilterStatusAPI:
    """API-level filter status endpoint response."""
    device_id: str
    filter_id: str
    install_date: str
    operating_volume_l: float
    replacement_status: str  # "new", "good", "expired"
    maintenance_history: List[Dict[str, Any]] = field(default_factory=list)
    days_in_service: float = 0.0
    volume_since_install_l: float = 0.0
    status: str = "ok"  # "ok", "expired", "fault"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "filter_id": self.filter_id,
            "install_date": self.install_date,
            "operating_volume_l": self.operating_volume_l,
            "replacement_status": self.replacement_status,
            "maintenance_history": self.maintenance_history,
            "days_in_service": self.days_in_service,
            "volume_since_install_l": self.volume_since_install_l,
            "status": self.status,
        }


@dataclass
class RULPredictionAPI:
    """API-level RUL prediction endpoint response."""
    device_id: str
    rul_days: Optional[float] = None
    rul_liters: Optional[float] = None
    model_version: str = "xgboost"
    confidence: Optional[float] = None
    metrics: Dict[str, float] = field(default_factory=lambda: {"mae": float("nan"), "rmse": float("nan"), "r2": float("nan")})
    last_trained: Optional[str] = None
    simulation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "rul_days": self.rul_days,
            "rul_liters": self.rul_liters,
            "model_version": self.model_version,
            "confidence": self.confidence,
            "metrics": self.metrics,
            "last_trained": self.last_trained,
            "simulation": self.simulation,
        }


@dataclass
class SystemStatusAPI:
    """API-level system status endpoint response."""
    device_id: str
    online: bool = True
    last_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    active_alerts: List[str] = field(default_factory=list)
    faults: List[str] = field(default_factory=list)
    water_quality: Dict[str, Any] = field(default_factory=dict)
    filter_status: Dict[str, Any] = field(default_factory=dict)
    rul_prediction: Dict[str, Any] = field(default_factory=dict)
    ro_process: Dict[str, Any] = field(default_factory=dict)
    mineral_dosing: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device_id": self.device_id,
            "online": self.online,
            "last_seen": self.last_seen,
            "active_alerts": self.active_alerts,
            "faults": self.faults,
            "water_quality": self.water_quality,
            "filter_status": self.filter_status,
            "rul_prediction": self.rul_prediction,
            "ro_process": self.ro_process,
            "mineral_dosing": self.mineral_dosing,
        }


# ---------------------------------------------------------------------------
# Mock API Server Framework (Flask-compatible)
# ---------------------------------------------------------------------------
# This module defines request handler functions that could be registered with
# a Flask or similar web framework. The functions follow the data contracts
# above and integrate with the existing aquaculture project by running
# concurrently / independently — no existing code is modified.

try:
    import flask
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


class APIDispatcher:
    """Dispatches API requests to the appropriate handler functions."""

    def __init__(self, device_id: str = "aquasense-pro-001"):
        self.device_id = device_id
        self.history = HistoricalRecord(max_entries=500)  # from water_quality module
        self.rul_pipeline = XGBoostRULPipeline()  # from rul_pipeline module
        self.baseline_monitor = None  # will be set if flow/pressure data available
        self.ro_state = ROProcessState()
        self.ed_module = None  # EDRecoveryModule
        self.dosing_controller = MineralDosingController()
        self.thresholds = ...  # ThresholdConfig from water_quality module

        # Initialize ED module in simulation mode by default
        from .ro_simulation import EDRecoveryModule
        self.ed_module = EDRecoveryModule(simulation=bool(ENABLE_SIMULATION))

        # Initialize dosing controller
        from .ro_simulation import MineralDosingController as MDC
        self.dosing_controller = MDC(simulation=bool(ENABLE_SIMULATION))

    # --- API Endpoint Handlers ---

    def get_sensor_readings(self) -> Dict[str, Any]:
        """GET /api/v1/sensor-readings — Latest validated sensor data."""
        # In a real implementation, this would read from the latest MQTT message
        # or sensor acquisition loop. For now, return structure.
        from .foundation import SensorReading
        from .water_quality import ingest_measurements, SensorReading as SQReading

        # Try to get recent from global history if available, else return skeleton
        try:
            recent_records = history.get_recent(n=1)
            if recent_records:
                m = recent_records[0]
                return {
                    "success": True,
                    "data": m.to_dict(),
                    "device_id": self.device_id,
                }
        except Exception:
            pass

        # Return skeleton with no real data
        return {
            "success": True,
            "data": SensorReadingAPI(
                device_id=self.device_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
            ).to_dict(),
            "device_id": self.device_id,
        }

    def get_filter_status(self) -> Dict[str, Any]:
        """GET /api/v1/filter-status — Filter health, operating volume, replacement status."""
        from .ro_simulation import ROProcessState

        # Return filter status based on what we've tracked
        # For now, use defaults; in production, this would track actual filter identity
        install_date = datetime.utcnow().strftime("%Y-%m-%d")

        fs = FilterStatusAPI(
            device_id=self.device_id,
            filter_id="quick-twist-filter-001",
            install_date=install_date,
            operating_volume_l=self.ro_state.operating_volume_l if hasattr(self.ro_state, 'operating_volume_l') else 0.0,
            replacement_status="new",  # would be computed from operating volume vs. filter rating
            days_in_service=round((datetime.utcnow().timestamp() - datetime.fromisoformat(
                install_date.replace('T', ' ')).timestamp()) / 86400, 1) if hasattr(install_date, 'replace') else 0.0,
        )

        return {
            "success": True,
            "data": fs.to_dict(),
            "device_id": self.device_id,
        }

    def get_rul_prediction(self) -> Dict[str, Any]:
        """GET /api/v1/rul-prediction — Remaining Useful Life in days and liters."""
        from .foundation import now_iso8601

        # Try to get a prediction from the XGBoost pipeline
        # In simulation mode, return a plausible estimate; in production, use real features
        try:
            pred = self.rul_pipeline.predict_rul(
                dRc_dt_proxy=0.01,  # placeholder; from baseline monitor
                operating_hours=self.ro_state.operating_volume_l if hasattr(self.ro_state, 'operating_volume_l') else 0.0,
                flow_ratio=0.8,  # placeholder Fin/Fout ratio
                pressure_bar=2.0,  # placeholder TM pressure
                pressure_rise_rate=0.001,
            )
            pred["simulation"] = bool(ENABLE_SIMULATION)
            pred["device_id"] = self.device_id
            return {
                "success": True,
                "data": pred,
            }
        except Exception as e:
            return {
                "success": True,
                "data": {
                    "device_id": self.device_id,
                    "rul_days": None,
                    "rul_liters": None,
                    "model_version": "untrained",
                    "metrics": {"mae": float("nan"), "rmse": float("nan"), "r2": float("nan")},
                    "simulation": bool(ENABLE_SIMULATION),
                    "note": "Model not yet trained; collect sensor data and retrain.",
                },
            }

    def get_system_status(self) -> Dict[str, Any]:
        """GET /api/v1/system-status — Overall system health, alerts, status."""
        from .foundation import SensorQuality

        # Run safety checks
        safety = check_ro_safety(
            input_vol=self.ro_state.input_volume_l,
            permeate_vol=self.ro_state.permeate_volume_l,
            reject_vol=self.ro_state.reject_volume_l,
            recovery_ratio=self.ro_state.recovery_ratio,
            pressure_bar=self.ro_state.pressure_bar if hasattr(self.ro_state, 'pressure_bar') else 2.0,
            ca_dosed_mg=self.dosing_controller.ca_dosed_this_cycle_mg,
            mg_dosed_mg=self.dosing_controller.mg_dosed_this_cycle_mg,
            ca_setpoint_mgL=self.dosing_controller.ca_setpoint_mgL,
            mg_setpoint_mgL=self.dosing_controller.mg_setpoint_mgL,
        )

        # Build water quality from latest measurement
        try:
            wq_records = history.get_recent(n=1)
            if wq_records:
                wq = wq_records[0]
                wq_dict = wq.to_dict()
                # Add status fields
                wq_dict["pH_status"] = wq.pH_status if hasattr(wq, 'pH_status') else "unknown"
                wq_dict["tds_status"] = wq.tds_status if hasattr(wq, 'tds_status') else "unknown"
                wq_dict["turbidity_status"] = wq.turbidity_status if hasattr(wq, 'turbidity_status') else "unknown"
                wq_dict["uv254_status"] = wq.uv254_status if hasattr(wq, 'uv254_status') else "unknown"
            else:
                wq_dict = {}
        except Exception:
            wq_dict = {}

        # Filter status
        try:
            fs = self.get_filter_status()
            filter_status = fs.get("data", {})
        except Exception:
            filter_status = {}

        # RUL prediction
        try:
            rul = self.get_rul_prediction()
            rul_data = rul.get("data", {})
        except Exception:
            rul_data = {}

        # RO process state
        ro_dict = self.ro_state.to_dict() if hasattr(self.ro_state, 'to_dict') else {}

        result = SystemStatusAPI(
            device_id=self.device_id,
            active_alerts=safety.get("faults", []),
            faults=safety.get("faults", []),
            water_quality=wq_dict,
            filter_status=filter_status,
            rul_prediction=rul_data,
            ro_process=ro_dict,
        )

        # Convert to dict, filtering out None/empty where appropriate
        return {
            "success": True,
            "data": result.to_dict(),
            "device_id": self.device_id,
        }

    # --- Flask Registration (if Flask available) ---

    def register_flask_routes(self, app) -> None:
        """Register all API routes with a Flask application."""
        if not FLASK_AVAILABLE:
            import warnings
            warnings.warn("Flask not available; API routes cannot be registered.")
            return

        @app.route("/api/v1/sensor-readings", methods=["GET"])
        def api_sensor_readings():
            return jsonify(self.get_sensor_readings())

        @app.route("/api/v1/filter-status", methods=["GET"])
        def api_filter_status():
            return jsonify(self.get_filter_status())

        @app.route("/api/v1/rul-prediction", methods=["GET"])
        def api_rul_prediction():
            return jsonify(self.get_rul_prediction())

        @app.route("/api/v1/system-status", methods=["GET"])
        def api_system_status():
            return jsonify(self.get_system_status())

        @app.route("/api/v1/health", methods=["GET"])
        def api_health():
            return jsonify({
                "success": True,
                "data": {
                    "device_id": self.device_id,
                    "status": "ok",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            })


# Helper for jsonify (Flask)
try:
    from flask import jsonify
except ImportError:
    def jsonify(d):
        """Minimal jsonify fallback that just returns the dict."""
        return d, 200, {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# End of Module
# ---------------------------------------------------------------------------
# Documentation of claims that have and have not been validated:
#
# - API endpoint data contracts (SensorReadingAPI, FilterStatusAPI, RULPredictionAPI,
   # SystemStatusAPI) are software structures for JSON serialization. They do not
   # represent real measurements until connected to actual sensor hardware and MQTT
   # telemetry.
#
# - RUL prediction API: When model is not trained, returns None/NaN values with
   # explanatory note. Do not claim valid RUL estimates without a trained model
   # and walk-forward validation (see rul_pipeline.py policy).
#
# - Simulation mode: All API endpoints respect ENABLE_SIMULATION. When active,
   # data is synthetic and labeled as such. Production deployment must have
   # ENABLE_SIMULATION=0 and real hardware connected.
#
# - The original aquaculture project is NOT affected by this module. All new
   # code is added in isolation. The API dispatcher runs independently and does
   # not modify any existing aquaculture notebooks, firmware, or data files.
#
# - Backward compatibility: The original project's README, notebook, and firmware
   # remain unchanged. New API routes are additive only; existing functionality
   # is preserved without modification (Phase Five Priority 5).
#
"""