# Product requirements

## Problem

AI agents take real actions through tools. Letting them act unchecked is unsafe, and asking a person to approve every action wears that person out until the approvals mean nothing. Human attention is the scarce resource, and today nothing manages it.

## Goal

For every action an agent proposes, pick the cheapest reviewer that is still safe enough: the agent itself, a safety model, or a human. Spend human attention on the actions that need it most, and explain every choice.

## Users

Teams running agents that touch real systems, and researchers studying scalable oversight.

## Requirements

1. Score the risk of an action from the tool call itself, using a policy file people can read and edit.
2. Route by risk and by how much attention the human has left (availability, interrupts per hour, minimum gap).
3. Critical actions always go to a human. If no human is around they wait; they are never handed to a model.
4. The router is deterministic and never calls a model. Model calls happen only in the safety model module.
5. The safety model fails closed: errors, refusals, unreadable output or hitting the spend cap all mean "ask a human".
6. Model answers are cached and spending is capped by `MAX_SPEND_USD`.
7. Every decision and every human answer is logged with its reasons.
8. The core does not depend on any model provider; providers plug in through adapters.
9. All evaluation data is synthetic. Every published number comes from a script anyone can rerun.

## Success measure

Against fixed risk tiers and against sending everything to a human: fewer human interrupts per day at the same or lower share of harmful actions executed, reported with confidence intervals and with the costs (waiting time, blocked good actions) shown next to it.

## Out of scope for now

A web interface for reviewers, multi reviewer teams, learning the policy from data.
