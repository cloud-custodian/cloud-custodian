# Cloud Custodian Upgrade Procedure

## Overview
This document describes the standardized procedure for upgrading our Cloud Custodian fork with upstream changes while preserving ManomanoTech (MM) custom modifications.

## Branch Strategy

### Branch Structure
```
upstream/main           ← Official Cloud Custodian repository
    ↓
upstream-mirror        ← Protected clean mirror of upstream
    ↓ (via Merge Request)
master                 ← Production branch with MM modifications
    ↓
feature branches       ← Individual features (GT-XXXX, etc.)
```

### Branch Protection
- `upstream-mirror` branch is **protected** and cannot be deleted
- Only maintainers can push directly to `upstream-mirror`
- All changes to `master` must go through Merge Requests (company standard)

## Setup (One-time)

### Phase 1: Initial Setup
```bash
# 1. Create upstream-mirror branch from upstream
git checkout -b upstream-mirror upstream/main
git push origin upstream-mirror

# 2. Set upstream tracking
git branch --set-upstream-to=upstream/main upstream-mirror

# 3. Protect the branch in GitLab
# Go to: Project Settings > Repository > Protected Branches
# Add: upstream-mirror (Maintainer push, No merge)
```

## Regular Upgrade Procedure

### Phase 2: Upstream Sync

#### Step 1: Update upstream-mirror
```bash
# Switch to upstream-mirror
git checkout upstream-mirror

# Fetch latest upstream changes
git fetch upstream main

# Update upstream-mirror with latest upstream
git pull upstream main

# Push to origin
git push origin upstream-mirror
```

#### Step 2: Create Merge Request for Master
```bash
# Create feature branch for upgrade
git checkout master
git checkout -b upgrade/upstream-sync-YYYY-MM-DD

# Merge upstream-mirror into upgrade branch
git merge upstream-mirror --no-ff -m "Merge upstream changes from upstream-mirror"

# Push upgrade branch
git push origin upgrade/upstream-sync-YYYY-MM-DD
```

#### Step 3: Merge Request Process
1. **Create MR**: `upgrade/upstream-sync-YYYY-MM-DD` → `master`
2. **Title**: "Upgrade: Sync with upstream Cloud Custodian (YYYY-MM-DD)"

#### Step 4: Conflict Resolution

**Resolution Strategy**:
```bash
# For conflicts in MM-modified files:
# 1. Keep MM enhancements (actions/ directory is safe)
# 2. Integrate upstream changes carefully
# 3. Test MM-specific functionality

# Example conflict resolution:
git status  # See conflicted files
# Edit conflicted files to preserve MM modifications
git add <resolved-files>
git commit -m "Resolve conflicts: preserve MM modifications"
```



## Rollback Procedure

If upgrade causes issues:

```bash
# Option 1: Revert the merge commit
git checkout master
git revert -m 1 <merge-commit-hash>
git push origin master

# Option 2: Reset to previous state
git checkout master
git reset --hard <previous-commit-hash>
git push --force-with-lease origin master
```
