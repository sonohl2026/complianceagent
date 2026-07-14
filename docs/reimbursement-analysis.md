# Reimbursement Analysis — Why Coding, Coverage, Payment, Billing Stay Separate

This mirrors the compliance master prompt §14 and is a hard product constraint, not just a
writing convention:

- **Coding** — does a standardized code (CPT/HCPCS/ICD-10) describe the item or service? A code
  existing (or being obtainable, e.g. via Category III application) says nothing about whether
  anyone will pay for it.
- **Coverage** — will a specific payer (Medicare via NCD/LCD/billing article, a specific MAC
  jurisdiction, or a named commercial payer's medical policy) cover the item/service for this
  patient, indication, provider, and site of service? Coverage can be — and often is — narrower
  than FDA-authorized labeling.
- **Payment** — given coverage, what methodology and amount applies (Physician Fee Schedule,
  OPPS/APC, IPPS/MS-DRG, NTAP, ASC, DMEPOS, or a negotiated commercial rate)? A national-average
  rate is not a guaranteed provider payment; it must always be labeled with year, locality,
  facility/nonfacility status, and proposed-vs-final status.
- **Billing** — can a provider actually submit a compliant claim, given the real operational
  workflow (order, consent, setup, data capture, monitoring days, interactive communication,
  interpretation, documentation)? A code and a payable rate mean nothing if the workflow can't
  produce the required documentation.
- **Provider economics** — does payment exceed the provider's cost and operational burden of
  delivering the service?
- **Manufacturer economics** — how does the company actually receive revenue (device sale, lease,
  software fee, subscription, bundled facility contract)? This is often decoupled from whether a
  code, coverage policy, or payment rate exists at all.

The application enforces this separation structurally: `CodingCandidate` has independent
`eligibility_status`, `coverage_status`, `payment_status`, and `billing_status` fields (Milestone
2+ data model), and no pipeline stage is permitted to collapse them into a single "reimbursable"
verdict (`prompts/synthesis.md`). This file will gain worked examples once the coding/coverage/
payment/billing analysis modules (Milestone 5) exist.
