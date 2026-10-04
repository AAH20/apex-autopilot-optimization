"""MLOps package: model registry, serving, versioning, experiments, and drift.

Provides the foundational infrastructure for learning-based planning and
multi-agent coordination: a persistent model registry, an in-process model
server, experiment tracking, and data drift detection.
"""

from apex_autopilot_optimization.mlops.drift import DriftDetector
from apex_autopilot_optimization.mlops.experiment import Experiment, ExperimentTracker
from apex_autopilot_optimization.mlops.registry import ModelRegistry
from apex_autopilot_optimization.mlops.server import ModelServer
from apex_autopilot_optimization.mlops.version import ModelStage, ModelVersion

__all__ = [
    "DriftDetector",
    "Experiment",
    "ExperimentTracker",
    "ModelRegistry",
    "ModelServer",
    "ModelStage",
    "ModelVersion",
]
