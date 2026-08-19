# Maintenance Investigation and Work-Order Safety Procedure

Document ID: SOP-MAINT-001
Revision: 1
Applicable assets: all rotating equipment

## Evidence Requirements

Maintenance recommendations should identify the asset, relevant sensor trends, maintenance-history findings, data-quality limitations, and supporting engineering-document sections.

If evidence is missing, contradictory, stale, or unreliable, the investigation should state the limitation and request additional inspection rather than presenting an unsupported diagnosis.

## Work-Order Approval

Read-only investigation may occur without approval. Creating a proposed work order does not authorize physical maintenance.

A state-changing application action requires a valid persisted human approval. Approval must match the work order and current request version and must not be expired, revoked, rejected, or previously consumed.

## Machinery Control Boundary

The maintenance copilot must not start or stop machinery, modify PLC parameters, bypass interlocks, or issue direct control commands.

Approved work-order execution changes only application records. Physical isolation, lockout/tagout, permit-to-work, and field maintenance remain controlled by authorized site personnel.