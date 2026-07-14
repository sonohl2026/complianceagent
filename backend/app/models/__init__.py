# Import every model module here so Alembic autogenerate and Base.metadata
# discover all tables.
from app.models.analysis import AnalysisRun, Finding  # noqa: F401
from app.models.chat_message import ChatMessage  # noqa: F401
from app.models.citation import Citation  # noqa: F401
from app.models.claim import ExtractedClaim  # noqa: F401
from app.models.coding import CodingCandidate, CodingRequirement  # noqa: F401
from app.models.company import Company  # noqa: F401
from app.models.compliance_issue import ComplianceIssue  # noqa: F401
from app.models.crawl import CrawledPage, CrawlSnapshot  # noqa: F401
from app.models.enums import (  # noqa: F401
    AuthorityLevel,
    CitationRole,
    CitationVerificationStatus,
    ClaimCategory,
    ClaimDisposition,
    CodingEligibilityStatus,
    CollectionType,
    ComplianceIssueStatus,
    ConfidentialityLevel,
    EmbeddingStatus,
    EvidenceStatus,
    ExpressOrImplied,
    FindingDomain,
    JobStatus,
    ParseStatus,
    RiskLevel,
    RobotsStatus,
    Verdict,
)
from app.models.job import Job  # noqa: F401
from app.models.monitoring import Alert, ScheduledRecrawl  # noqa: F401
from app.models.product import Product  # noqa: F401
from app.models.project import Project  # noqa: F401
from app.models.prompt_version import PromptVersion  # noqa: F401
from app.models.source_chunk import SourceChunk  # noqa: F401
from app.models.source_document import SourceDocument  # noqa: F401

__all__ = [
    "Company",
    "Product",
    "Project",
    "SourceDocument",
    "SourceChunk",
    "Job",
    "CrawlSnapshot",
    "CrawledPage",
    "PromptVersion",
    "AnalysisRun",
    "Finding",
    "Citation",
    "ExtractedClaim",
    "CodingCandidate",
    "CodingRequirement",
    "ComplianceIssue",
    "ComplianceIssueStatus",
    "ChatMessage",
    "ScheduledRecrawl",
    "Alert",
    "CollectionType",
    "AuthorityLevel",
    "ParseStatus",
    "EmbeddingStatus",
    "ConfidentialityLevel",
    "JobStatus",
    "RobotsStatus",
    "FindingDomain",
    "EvidenceStatus",
    "Verdict",
    "RiskLevel",
    "CitationRole",
    "CitationVerificationStatus",
    "ClaimCategory",
    "ExpressOrImplied",
    "ClaimDisposition",
    "CodingEligibilityStatus",
]
