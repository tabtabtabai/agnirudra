# Rudra - Smart Single-Pass Code Review

> **Status**: Design only. Not built yet.

## What It Is

A GitHub App that performs single-pass code review on pull requests.

## Trigger

Assigned as a reviewer on a PR (via GitHub `review_requested` webhook).

## Behavior

1. Fetches the full PR diff
2. Sends to Claude with a startup-aware system prompt:
   - Focus on: security vulnerabilities, data loss, critical bugs
   - Skip: race conditions, style nitpicks, theoretical performance concerns
3. Returns one of:
   - **APPROVE** (no comments) - clean code
   - **APPROVE with comments** - minor non-blocking observations
   - **REQUEST_CHANGES** - critical issues only (security, data loss)
4. Does NOT re-run unless it previously rejected AND new commits are pushed

## Key Difference

Rudra reviews once, gives a clear verdict, and shuts up. No comment spam on every push.

## Deployment

Cloud Run or Azure Container App (webhook receiver).

## Architecture

```
PR review requested -> GitHub webhook -> Rudra service
  1. Fetch full diff via GitHub API
  2. Send to Claude with focused system prompt
  3. Submit review (approve/request changes)
  4. Done. No re-runs unless new commits on a rejected PR.
```

## System Prompt Design

- Prioritize: security, data integrity, correctness
- Ignore: style, naming conventions, minor refactors
- Be decisive: approve or reject, no wishy-washy "consider maybe"
- One review. One verdict. Move on.
