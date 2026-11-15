from typing import List
from app.evaluation.schemas import EvaluationSample

GOLDEN_EVALUATION_DATASET: List[EvaluationSample] = [
    EvaluationSample(
        id="eval-001",
        query="What is the company policy regarding remote work and VPN usage?",
        ground_truth_answer="All remote employees must connect via the enterprise GlobalProtect VPN with multi-factor authentication (MFA) enabled. Split tunneling is strictly prohibited on company-managed devices.",
        ground_truth_contexts=[
            "Section 4.2 Remote Access Policy: All remote employees and contractors accessing internal networks must use the corporate GlobalProtect VPN with MFA enabled. Split tunneling is strictly prohibited on company-owned laptops to prevent data exfiltration.",
            "Section 4.3 Hardware Security: Remote workstations must remain locked when unattended and have disk encryption (BitLocker or FileVault) enforced at all times.",
        ],
        department="IT_SECURITY",
        metadata={"category": "Security Policy", "difficulty": "Medium"},
    ),
    EvaluationSample(
        id="eval-002",
        query="What are our customer SLA response times and uptime commitments?",
        ground_truth_answer="The platform guarantees 99.9% monthly service uptime. Critical Severity-1 incidents require an initial response within 15 minutes, while Severity-2 issues require response within 2 hours.",
        ground_truth_contexts=[
            "Service Level Agreement (SLA): Acme Corp commits to a 99.9% monthly service uptime target for Tier-1 production clusters.",
            "Incident Response Targets: Severity-1 (Service Outage) initial response within 15 minutes and updates every 30 minutes. Severity-2 (Major Impairment) response within 2 hours.",
        ],
        department="CUSTOMER_SUCCESS",
        metadata={"category": "Contracts & SLAs", "difficulty": "Easy"},
    ),
    EvaluationSample(
        id="eval-003",
        query="How does the engineering onboarding process work for code reviews and branch permissions?",
        ground_truth_answer="New engineers must submit pull requests against feature branches. Merges to the 'main' branch require at least two approving reviews from senior engineers and passing automated CI checks.",
        ground_truth_contexts=[
            "Engineering Handbook - Git Workflow: All code contributions require a dedicated feature branch. Direct pushes to 'main' or 'staging' branches are permanently blocked.",
            "Code Review Standards: Every pull request targeting 'main' mandates a minimum of two peer review approvals, including at least one Senior or Staff Engineer, alongside green automated CI test pipelines.",
        ],
        department="ENGINEERING",
        metadata={"category": "Engineering Practices", "difficulty": "Medium"},
    ),
    EvaluationSample(
        id="eval-004",
        query="What is the data retention schedule for customer PII under GDPR compliance?",
        ground_truth_answer="Customer Personally Identifiable Information (PII) is retained for 30 days following formal account termination, after which it undergoes permanent cryptographic erasure. Audit logs are retained for 365 days.",
        ground_truth_contexts=[
            "Data Governance Policy: In compliance with GDPR and SOC2 Type II, customer PII must be purged within 30 days of formal service termination via cryptographic erasure.",
            "Audit & Compliance Logging: Application access and security audit logs are archived in immutable WORM storage and retained for exactly 365 days before automatic deletion.",
        ],
        department="LEGAL_COMPLIANCE",
        metadata={"category": "Compliance & Privacy", "difficulty": "Hard"},
    ),
    EvaluationSample(
        id="eval-005",
        query="What are the annual PTO accrual rates and rollover rules for full-time employees?",
        ground_truth_answer="Full-time employees accrue 20 days of Paid Time Off (PTO) per calendar year, accrued semi-monthly. A maximum of 5 unused PTO days can be rolled over into the subsequent calendar year.",
        ground_truth_contexts=[
            "Employee Benefits & Leave Policy: Regular full-time employees accrue 20 days (160 hours) of Paid Time Off (PTO) annually, accrued pro-rata on the 1st and 15th of each month.",
            "PTO Rollover: Employees may roll over a maximum of 5 unused PTO days into the following calendar year. Any additional accrued but unused days expire on December 31st.",
        ],
        department="HUMAN_RESOURCES",
        metadata={"category": "HR Policies", "difficulty": "Easy"},
    ),
]
