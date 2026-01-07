# Git Setup Commands for Amazon Parent Dashboard

## Step 1: Initialize Repository

```bash
# Navigate to directory
cd C:\Users\Eric\Desktop\amzp

# Initialize git
git init

# Check status
git status
```

## Step 2: Initial Commit (Main Branch)

```bash
# Add all files
git add .

# Create initial commit
git commit -m "feat: Amazon Parent Dashboard integration with cookie refresh

Integration features:
- Amazon Parent Dashboard Home Assistant integration
- Playwright-based authentication add-on
- Automatic cookie refresh on session expiration
- HTTP API for cookie retrieval
- Persistent notifications for re-auth
- Support for multiple children and devices

Components:
- amazonparent/ - Home Assistant custom integration
- amazonparent-playwright-ha/ - Browser automation add-on"

# Rename default branch to main (if needed)
git branch -M main
```

## Step 3: Create Feature Branch

```bash
# Create and switch to feature branch
git checkout -b feature/cookie-refresh-implementation

# This branch contains the untested cookie refresh implementation
```

## Step 4: Add Remote and Push

```bash
# Add your GitHub remote (replace with your actual repo URL)
git remote add origin https://github.com/YOUR_USERNAME/amazonparent-ha.git

# Push main branch
git push -u origin main

# Push feature branch
git push -u origin feature/cookie-refresh-implementation
```

## Step 5: Create Pull Request on GitHub

1. Go to your GitHub repository
2. Click "Pull requests" → "New pull request"
3. Base: `main` ← Compare: `feature/cookie-refresh-implementation`
4. Title: "Add automatic cookie refresh functionality"
5. Description: Copy from IMPLEMENTATION_SUMMARY.md
6. Add labels: `enhancement`, `needs-testing`
7. Create pull request (DO NOT MERGE YET)

## Step 6: Testing Phase

### Install in Home Assistant
```bash
# Copy to Home Assistant custom_components directory
# Test in a development/test Home Assistant instance first!
```

### Test Scenarios
- [ ] Normal operation (60-second update cycle)
- [ ] Cookie expiration (401 response)
- [ ] Automatic refresh success
- [ ] Automatic refresh failure (add-on down)
- [ ] Manual re-authentication via add-on
- [ ] Notification creation and clearing
- [ ] Multiple children/devices

### Document Test Results
```bash
# On feature branch
git checkout feature/cookie-refresh-implementation

# Create test results file
cat > TEST_RESULTS.md << 'EOF'
# Test Results - Cookie Refresh Implementation

## Test Environment
- Home Assistant Version: X.X.X
- Python Version: 3.X
- Test Date: YYYY-MM-DD

## Test Results

### ✅ Passed
- [ ] Test 1: Description
- [ ] Test 2: Description

### ❌ Failed
- [ ] Test 3: Description
  - Error: ...
  - Fix applied: ...

### 🔧 Bugs Found
1. Bug description
   - File: path/to/file.py:line
   - Fix: ...

EOF

git add TEST_RESULTS.md
git commit -m "docs: Add test results"
git push
```

## Step 7: Bug Fixes (if needed)

```bash
# Stay on feature branch
git checkout feature/cookie-refresh-implementation

# Make fixes
# ... edit files ...

git add .
git commit -m "fix: [description of what was fixed]"
git push
```

## Step 8: Merge to Main (After Testing)

### Option A: Merge on GitHub (Recommended)
1. Go to Pull Request
2. Click "Merge pull request"
3. Choose merge strategy:
   - "Create a merge commit" (preserves history)
   - "Squash and merge" (cleaner history)
4. Confirm merge

### Option B: Merge Locally
```bash
# Switch to main
git checkout main

# Merge feature branch
git merge feature/cookie-refresh-implementation

# Tag the release
git tag -a v0.2.0 -m "Release v0.2.0: Cookie refresh implementation"

# Push to GitHub
git push origin main --tags
```

## Step 9: Cleanup (Optional)

```bash
# Delete local feature branch
git branch -d feature/cookie-refresh-implementation

# Delete remote feature branch
git push origin --delete feature/cookie-refresh-implementation
```

## Quick Reference

### Check Current Branch
```bash
git branch
```

### Switch Branches
```bash
git checkout main
git checkout feature/cookie-refresh-implementation
```

### View Commit History
```bash
git log --oneline --graph --all
```

### Undo Last Commit (if not pushed)
```bash
git reset --soft HEAD~1
```

### View Changes
```bash
git diff
git diff --cached  # staged changes
git status
```

## Troubleshooting

### If you accidentally committed to main instead of feature branch:
```bash
# Create feature branch from current HEAD
git branch feature/cookie-refresh-implementation

# Reset main to previous commit
git checkout main
git reset --hard HEAD~1

# Switch to feature branch
git checkout feature/cookie-refresh-implementation

# Push both
git push -u origin feature/cookie-refresh-implementation
git push origin main --force  # Use with caution!
```

### If you need to update branch from main:
```bash
git checkout feature/cookie-refresh-implementation
git merge main
# Or: git rebase main (for cleaner history)
```
