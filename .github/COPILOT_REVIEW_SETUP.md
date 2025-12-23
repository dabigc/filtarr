# Enabling Automatic GitHub Copilot Code Review

This document explains how to enable automatic Copilot code review for this repository.

## Prerequisites

- GitHub Copilot Pro, Pro+, Business, or Enterprise subscription
- Repository admin access

## Setup via Repository Ruleset

1. Navigate to **Settings** → **Rules** → **Rulesets**
2. Click **New ruleset** → **New branch ruleset**
3. Configure the ruleset:

   | Setting | Value |
   |---------|-------|
   | Name | `copilot-code-review` |
   | Enforcement status | **Active** |
   | Target branches | Default branch (`main`) |

4. Under **Branch rules**, enable:
   - [x] **Automatically request Copilot code review**
   - [x] **Review new pushes** (reviews all commits, not just initial PR)
   - [ ] **Review draft pull requests** (optional - enable for early feedback)

5. Click **Create**

## What Copilot Reviews

The review instructions are defined in:

```
.github/
├── copilot-instructions.md              # General coding standards
└── instructions/
    ├── python-security.instructions.md  # Security vulnerabilities
    ├── python-performance.instructions.md # Performance issues
    └── python-quality.instructions.md   # Code smells & quality
```

### Severity Levels

| Severity | Examples | Action |
|----------|----------|--------|
| **HIGH** | Security vulnerabilities, async anti-patterns, missing types | Should block merge |
| **MEDIUM** | Code duplication, naming issues, minor inefficiencies | Review recommended |
| **LOW** | Style preferences, complexity warnings | Informational |

## Blocking Configuration

To enforce blocking on HIGH severity issues:

1. In the same ruleset, add **Require status checks**
2. Add `copilot / code-review` as a required check
3. This ensures PRs can't merge until Copilot review passes

> **Note**: As of late 2025, Copilot code review provides comments but doesn't natively produce a pass/fail status. For hard blocking, consider combining with:
> - Branch protection requiring human approval
> - CodeQL or other security scanning actions

## Customizing Review Focus

Edit files in `.github/instructions/` to adjust what Copilot looks for:

- Add project-specific patterns
- Adjust severity levels
- Include/exclude certain file types via `applyTo` frontmatter

### Example: Add TypeScript Review

Create `.github/instructions/typescript.instructions.md`:

```markdown
---
applyTo: "**/*.ts"
---

# TypeScript Review Guidelines

- Use strict mode
- Prefer interfaces over types for object shapes
- ...
```

## Troubleshooting

### Copilot Not Reviewing

1. Verify Copilot subscription is active
2. Check ruleset is enabled and targeting correct branches
3. Ensure PR is not a draft (unless draft review is enabled)

### Reviews Not Matching Instructions

1. Instruction files must have correct frontmatter syntax
2. Files must be in `.github/instructions/` directory
3. Check `applyTo` glob patterns match your files

## References

- [GitHub Docs: Configuring automatic code review](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/request-a-code-review/configure-automatic-review)
- [GitHub Blog: Master your instructions files](https://github.blog/ai-and-ml/unlocking-the-full-power-of-copilot-code-review-master-your-instructions-files/)
- [GitHub Docs: Using custom instructions](https://docs.github.com/en/copilot/tutorials/use-custom-instructions)
