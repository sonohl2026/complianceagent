#!/usr/bin/env python3
"""Seed the SonoHL example company/product/project used as the worked example.

Only uses the provisional working baseline already stated in
prompts/master_system_prompt.md §4.1 ("SonoHL Baseline: Current Working
Status") — no confidential information, and every hedged/unresolved fact from
that section is carried over as such rather than asserted as verified. This
is the first worked example only; the data model itself is company-agnostic
(see docs/data-model.md) and nothing here is SonoHL-specific at the schema
level.

Run inside the api container: `docker compose exec api python scripts/seed_sonohl_example.py`
(this is what `make seed` does).
"""
import asyncio
import sys

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.company import Company
from app.models.product import Product
from app.models.project import Project

SONOHL_DESCRIPTION = (
    "SonoHL is developing an investigational wearable acoustic-sensing platform "
    "involving multi-point acquisition of heart and lung sounds, supporting "
    "software, signal-handling functions, and a clinician-facing review "
    "environment. It is not cleared or approved by the U.S. Food and Drug "
    "Administration and is not available for commercial sale. Exact FDA "
    "pathway, final intended use, and reimbursement strategy remain under "
    "development (see prompts/master_system_prompt.md §4)."
)

PRODUCT_DEFAULTS = dict(
    name="SonoHL Acoustic-Sensing Platform (working baseline)",
    description=(
        "Multi-point cardiopulmonary acoustic acquisition device concept with "
        "clinician-support software. Sensor configuration is UNRESOLVED: "
        "working materials reference both 16-channel (10 anterior / 6 posterior) "
        "and 8-plus-sensor configurations; see master prompt §4.2."
    ),
    product_type="Wearable acoustic-sensing platform (investigational)",
    regulatory_stage="State A/B (concept-to-investigational; not established — see master prompt §8)",
    fda_status="Not cleared or approved; not commercially available (working baseline, unverified against controlled records)",
    intended_use="UNRESOLVED — narrow assistive/augmentative clinician-support role is a working regulatory hypothesis only (master prompt §4.1)",
    target_population="UNRESOLVED (master prompt §4.2)",
    intended_user="UNRESOLVED (master prompt §4.2)",
    site_of_service="UNRESOLVED — remote monitoring is a possible, not verified, use case (master prompt §4.1)",
    care_setting="UNRESOLVED (master prompt §4.2)",
    clinical_output="UNRESOLVED (master prompt §4.2)",
    ai_role="Framed as clinician support, not replacement of professional judgment (working hypothesis, master prompt §4.1)",
)


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        company = await db.scalar(select(Company).where(Company.name == "SonoHL Inc."))
        if company is None:
            company = Company(
                name="SonoHL Inc.",
                legal_name="SonoHL Inc.",
                description=SONOHL_DESCRIPTION,
                jurisdictions=["United States"],
            )
            db.add(company)
            await db.flush()
            print(f"[seed_sonohl_example] Created company {company.id}")
        else:
            print(f"[seed_sonohl_example] Company already exists: {company.id}")

        project = await db.scalar(
            select(Project).where(
                Project.company_id == company.id, Project.name == "Reimbursement Readiness Assessment"
            )
        )
        if project is None:
            project = Project(
                company_id=company.id,
                name="Reimbursement Readiness Assessment",
                description=(
                    "Worked example project seeded from the SonoHL master compliance prompt "
                    "working baseline. Populate with real company/authority documents to "
                    "exercise ingestion (Milestone 2+), retrieval (Milestone 3+), and analysis "
                    "(Milestone 5+)."
                ),
                jurisdiction="United States",
            )
            db.add(project)
            await db.flush()
            print(f"[seed_sonohl_example] Created project {project.id}")
        else:
            print(f"[seed_sonohl_example] Project already exists: {project.id}")

        product = await db.scalar(
            select(Product).where(
                Product.company_id == company.id, Product.name == PRODUCT_DEFAULTS["name"]
            )
        )
        if product is None:
            product = Product(company_id=company.id, **PRODUCT_DEFAULTS)
            db.add(product)
            await db.flush()
            if project.default_product_id is None:
                project.default_product_id = product.id
            print(f"[seed_sonohl_example] Created product {product.id}")
        else:
            print(f"[seed_sonohl_example] Product already exists: {product.id}")

        await db.commit()


def main() -> int:
    asyncio.run(seed())
    return 0


if __name__ == "__main__":
    sys.exit(main())
