# Accounting Office Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans for implementation.

**Goal:** Run the Bolder accounting-office application as a Docker Compose project.

**Architecture:** React renders the workflow views. FastAPI controllers call services using PostgreSQL repositories. Authorization is enforced at the API.

**Tech Stack:** React, FastAPI, PostgreSQL, Docker Compose.

**Spec:** [Architecture](../specs/2026-11-25-accounting-office-design.md) and [requirements](../../requirements.md).

## Tasks

- [x] Establish account sessions, role and data policies, organization, customer, task and notification operations. Verify signed-in and unauthorized access paths.
- [x] Implement attendance, requests, review history, leave balances, calendar, and report workflows. Verify a request can cross role boundaries with atomic state updates.
- [x] Implement Bolder dashboard and workflow screens against the API. Verify desktop and mobile navigation and operations.
- [x] Package Compose services and validate the Compose configuration and production frontend build.
- [x] Build and run the packaged services in Docker. Verified the web page, API health, owner login and logout, and Mailpit against the running containers.

## Open decisions

Retain the open policy, production configuration and work-time calculations identified in the spec. Local previews and exports must identify any demonstration rules or data. Use explicit application settings for integrations and record any remaining workflow gaps.
