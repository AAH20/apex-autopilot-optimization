# Apex Autopilot Optimization

Unified macro architecture for UAV/UAS and ground vehicle autopilot optimization.

## Overview

This project provides a comprehensive framework for:
- Path planning and trajectory optimization for UAVs (PX4, ArduPilot) and ground vehicles
- Multi-agent coordination and swarm optimization
- NP-hard problem identification and approximation algorithms
- Sensor fusion and state estimation pipelines
- Simulation and benchmarking against real autopilot stacks

## Architecture

```
src/apex_autopilot_optimization/
├── core/           # Domain types, interfaces
├── planning/       # Path planning algorithms (A*, RRT, PRM)
├── optimization/   # Trajectory optimization (MPC, minimum snap)
├── estimation/     # State estimation (EKF, UKF, factor graphs)
├── swarm/          # Multi-agent coordination
├── perception/     # Sensor fusion pipelines
├── simulation/     # Simulation environment
└── interfaces/     # PX4/ArduPilot integration adapters
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

AGPL-3.0
