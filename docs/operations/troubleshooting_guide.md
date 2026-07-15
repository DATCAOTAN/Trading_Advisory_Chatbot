# Troubleshooting Guide

## Provider Quota or Timeout

If a provider quota or timeout appears during normal app use, treat it as a provider error artifact. Do not fabricate an answer. Incomplete answers should not be marked complete.

## Streaming Interruption

A streaming interruption should be captured as a safe error state. Re-run the user request only when appropriate; do not bypass compliance or answer completeness checks.

## Corrupt JSONL

Use the Evaluation Dashboard System Health / Recovery section or `SystemHardeningService` tests to detect corrupt JSONL lines. Corrupt lines can be quarantined with their original hash preserved. Do not silently delete the source file.

## Invalid Manifest

Invalid JSON manifests should produce FAIL diagnostics. Do not overwrite them automatically. Export a diagnostic report and inspect the safe summary.

## Empty Dashboard

An empty dashboard usually means no evaluation registry entries are loaded or persisted yet. Run evaluations, save current records, or load persisted records.

## Missing Registry

Missing registry artifacts are WARN states in dashboard or runtime hardening. They should not crash the UI.

## Benchmark Fail

Golden benchmark failures identify mismatched fixtures, task leakage, missing sources, forbidden sources, unsafe output, or unexpected execution flags. Do not weaken benchmark expectations to hide a real regression.

## Dashboard Health Warnings

Health warnings are diagnostic signals. Missing optional files can be normal in a fresh checkout. Unsafe or corrupt records should be quarantined or corrected through explicit safe workflows.

## Qdrant Not Available

If Qdrant or retrieval infrastructure is unavailable during normal app use, the evidence path should fail safely or degrade according to existing gates. Do not delete Qdrant collections as a troubleshooting shortcut.

## API Key Missing

If provider credentials are missing, provider-backed app features may not run. Deterministic unit tests, replay fixtures, benchmarks, and hardening tests should still run without live provider calls.
