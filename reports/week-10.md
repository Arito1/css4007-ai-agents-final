# Semester Week 10 Progress Report

## Completed Work

- Forked the instructor repository and cloned the fork.
- Read the shared README and the A, C and D level documents, including the A-level guardrail and research paper requirements.
- Chose the project topic: **JumysAI Career Agent**. It is an autonomous job-search agent and will become the "agent mode" of my diploma project, JumysAI.
- Studied the existing diploma prototype, looking at which LLM features already exist (resume parsing, vacancy matching, resume generation, mock interview). These features are separate and started manually; there is no agent loop yet.
- Selected level A and drafted the functions, tools, permission levels, architecture, evaluation plan and milestones in `reports/proposal.md`.

Note: the proposal was finalised and committed on 12 November, which falls in Week 11. During Week 10 itself the work was planning only. The fork contains no project code from this week.

## Important Commits

- Commit hash: none in Week 10. The only commit in the fork is the inherited instructor starter `b537533`.
- Description: the proposal and this report are committed in Week 11.
- Link: https://github.com/Arito1/css4007-ai-agents-final/commits/main

## Current Functionality

Nothing runs yet. The repository contains the instructor starter and the completed proposal. The agent design (tools, permissions, state, guardrails) is described in the proposal.

## Problems Encountered

- Choosing a topic that is useful beyond the course. I considered a customer-support agent for parcel lockers and an Excel report agent from my job.
- The diploma is a team project and already has code, but the course project is individual and must be developed in this fork week by week.

## Solutions

- I chose the agent mode for my diploma. It is the missing part of JumysAI: the existing features become tools, and the agent decides their order from intermediate results.
- The agent will be written from scratch in this fork as a standalone Python module on fictional mock data. It will later be ported into the diploma, and it will be my own individual part of it. No diploma code or real personal data will be copied into the fork.

## What I Learned

- The difference between a pipeline, where the user chooses the order of steps, and an agent, where the LLM chooses actions from observations within limits enforced by code.
- Why guardrails must be enforced in application code and not only in the system prompt: permission checks, approval for consequential actions, and treating vacancy texts as untrusted data.
- The development consistency coefficient, and the need for meaningful progress every week.

## Next Week

- Set up the Python project (`pyproject`/requirements, `pytest`).
- Implement the Claude API adapter `llm.complete(messages, tools)` and make the first working request.
- Extend `.env.example` and add a setup section to the README.
