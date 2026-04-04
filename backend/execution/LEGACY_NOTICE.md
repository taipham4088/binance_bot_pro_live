# Legacy Execution Decision Engine

This directory contains the deprecated execution decision engine.

It is NOT used in the current production architecture.

Current production flow:
    backend/core/*
    execution/live_execution_system.py

The following modules are considered legacy:
    - decision/*
    - state_machine/*
    - timeline/*
    - execution_orchestrator.py (legacy)

Do not use ExecutionPlanType or decision_table in new code.