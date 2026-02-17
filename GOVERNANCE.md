# Governance for Cloud Custodian
Cloud Custodian is governed with the goals of transparency, vendor neutrality, and scalable community leadership. All contributors are expected to follow the CNCF Code of Conduct.
## 1. Project Areas

Cloud Custodian is organized into several functional areas, each responsible for a part of the project:

- AWS Provider  
- GCP Provider  
- Azure Provider  
- Tencent Cloud  
- Oracle Cloud  
- c7n-org (multi-cloud management)  
- Mailing & Notifications (`c7n-mailer`, alert handling)  
- Documentation & Community (website, docs, community guidance)  
- Releases & Tooling (release scripts, packaging, CI/CD, container images)

  Each area has at least one **Area Maintainer** defined in `OWNERS.md` and reflected in `CODEOWNERS`.

**Adding or Removing Areas**  
- To add a new area, nominate at least one Area Maintainer via a PR to update `OWNERS.md`; approval from current Core Maintainers is required.  
- To remove an area, an Area Maintainer can propose removal, which is finalized after code integration and consensus.

## 2. Maintainer Roles

- **Core Maintainers**: Oversee the entire project, make cross-area decisions, and coordinate CNCF engagement.  
- **Area Maintainers**: Own and manage specific project areas. They review and merge PRs, mentor contributors, and ensure ongoing health of their area.

## 3. Contributor Roles & Responsibilities

Cloud Custodian defines a structured contributor ladder to support growth and clarity.

- **Contributor**: Follow documentation and Code of Conduct; file issues; submit PRs.  
  *Requirements:* First-time or casual code, documentation, or issue contributors.
  
   **Area Maintainer**: Own and triage PRs/issues in one or more areas; mentor contributors; manage CI and releases in their area.  
  *Requirements:* ≥10 meaningful contributions per year; 6+ months of involvement; ~10 hrs/month commitment.

- **Core Maintainer**: Oversee project-wide changes; lead community initiatives; coordinate with CNCF; manage cross-area releases and security.  
  *Requirements:* Area Maintainer in multiple areas; demonstrated project-wide understanding; ~5 days/month involvement.

**Becoming a Maintainer**  
Nomination through a PR to `OWNERS.md`. Approval by a majority of maintainers in the area (for Area Maintainers) and by Core Maintainers (for Core Maintainers).

**Emeritus Offboarding**  
Maintainers who become inactive for 12+ months without explanation may be transitioned to Emeritus status by decision among maintainers. Emeritus status preserves recognition without active responsibilities.

## 4. Decision-Making & Escalation

- Technical decisions in each area are guided by consensus among Area Maintainers.  
- Cross-area or governance changes require Core Maintainer approval.  
- **Escalation path:** Contributor → Area Maintainers → Core Maintainers → CNCF TOC Liaison.

## 5. Inactivity Policy

Defined inactive periods:  
- Contributor: 12 months  
- Area Maintainer: 12 months  
- Core Maintainer: 12 months  

Failure to meet expectations may lead to emeritus designation or removal after consensus among maintainers.

## 6. GitHub Permissions & Documentation

`CODEOWNERS` and repository permissions reflect the defined maintainers for each area. Branch protection, CI checks, and reviewer requirements are enforced to uphold governance standards.

## 7. Code of Conduct

Cloud Custodian follows the CNCF Code of Conduct, which is published in `CODE_OF_CONDUCT.md` and linked across governance and contributor documents.

## 8. Transparency & Updates
`GOVERNANCE.md` is located in the repository root. Updates are tracked in GitHub with dates and rationale.Any changes require review and approval by a majority of Core Maintainers through a pull request. This document is linked from the project’s main `README` and contribution guides.


**Referenced files:**  
- `README.md`  
- `GOVERNANCE.md` (this document)  
- `OWNERS.md` (area and core maintainers list)  
- `CODE_OF_CONDUCT.md` (CNCF Code of Conduct link)
