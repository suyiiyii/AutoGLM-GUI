# Android Agent Reverse Connection Plan

## Current Implementation Snapshot

The current `android-agent-unified` line has already landed the first usable server-side reverse-agent building blocks.

Implemented pieces:

- pairing creation
- pairing claim
- in-memory reverse-agent registry
- reverse-agent heartbeat updates
- reverse WebSocket session entry
- desktop-side Android Agent unified entry compatibility

Current API surface:

- `POST /api/reverse_agents/pairings`
- `POST /api/reverse_agents/pairings/claim`
- `GET /api/reverse_agents/registry`
- `GET /api/reverse_agents/registry/{agent_id}`
- `WS /api/reverse_agents/agents/{agent_id}/ws`

Current state expression includes:

- `pairing_id`
- `agent_id`
- `display_name`
- `status`
- `capabilities`
- `metadata`
- `last_seen`

### Current security boundary

The reverse-agent registry endpoints are currently intended for a trusted management surface.

That means:

- they should be treated as management-plane APIs
- they should not be exposed to untrusted public callers without additional protection

Follow-up hardening that should be tracked separately:

- access control for registry read APIs
- registry lifecycle cleanup (agent TTL / stale record cleanup)
- metadata size limits and truncation rules

## Goal

Add a second Android Agent connection mode that lowers connection cost for ordinary users without replacing the current LAN direct-connect model.

This phase is not about "full public internet remote control". It is about making Android Agent easier to pair, easier to understand, and easier to recover when disconnected.

## Product Boundary

### Keep current direct LAN mode

The current model remains supported:

- AutoGLM-GUI actively connects to Android Agent
- best for MVP, LAN, local deployment, technical users
- already works and should not be broken

### Add reverse connection as a second mode

The new mode should be positioned as:

- a lower-friction connection mode
- suitable for ordinary users and remote scenarios
- focused on pairing, online presence, and basic command execution

Not the goal:

- replacing the direct model
- promising full public-network remote control
- solving every networking scenario in phase 1

## Success Criteria

Phase 1 is only successful if it improves user outcomes, not just transport connectivity.

Must be true:

1. The user does not need to manually fill in device IP or port during first connection.
2. The user can understand the main states:
   - paired
   - online
   - connected
   - executable
3. The agent can automatically recover from disconnects without requiring full re-initialization.
4. The mode is materially easier to explain and use than the current direct LAN path.

## State Model

These states must be explicitly separated in both API design and product expression:

- `paired`
- `online`
- `connected`
- `executable`

Important rule:

- `online` does not mean `executable`

Execution readiness also depends on device-side capability and permissions:

- `foreground_running`
- `accessibility_enabled`
- `screen_capture_ready`

The service side should be able to express:

- online but missing permissions
- online and executable

## Recommended Architecture

Use a reverse connection model where Android Agent opens an outbound long-lived connection to a control-side service.

Recommended first transport:

- `WebSocket` over `wss`

Reasoning:

- easier through NAT than server-initiated device access
- simpler than full custom tunnel design
- enough for phase 1 registration, heartbeat, and command forwarding

### High-level flow

1. Android Agent starts
2. Agent opens outbound `wss` connection to relay/control service
3. Agent authenticates and binds to workspace/controller
4. Agent sends heartbeat and capability state
5. AutoGLM-GUI sees the agent via server-side registry
6. AutoGLM-GUI sends basic commands through the service
7. Agent executes locally and returns results

## Phase 1 Minimal Protocol

Only introduce the minimum message set.

### 1. `register`

Sent by agent on first connect.

Suggested fields:

- `agent_id`
- `device_name`
- `app_version`
- `platform`
- `capabilities`

### 2. `auth_bind`

Completes pairing/binding.

Suggested fields:

- `pairing_code` or short-lived binding token
- `agent_id`

### 3. `heartbeat`

Periodic state report.

Suggested fields:

- `paired`
- `foreground_running`
- `accessibility_enabled`
- `screen_capture_ready`
- `app_version`
- `last_seen_at`

### 4. `command`

Server-to-agent command envelope.

Phase 1 only supports:

- `current_app`
- `screenshot`
- `tap`
- `swipe`
- `type_text`

### 5. `command_result`

Agent-to-server execution result.

Suggested fields:

- `command_id`
- `success`
- `error`
- `payload`
- `started_at`
- `finished_at`

### Optional: `agent_state_changed`

Useful for prompt state sync when permissions or runtime state change.

## Pairing and Auth

Phase 1 should avoid a heavy account model.

Recommended model:

1. AutoGLM-GUI or relay service generates a short-lived pairing code
2. User enters or scans it in Android Agent
3. Agent exchanges pairing code for a long-lived device token
4. Future reconnects use `agent_id + device_token`

Why this model:

- easier for users to understand than raw tokens
- lighter than full login/account flows
- safer than permanent manual credentials

## Server-side Additions

Phase 1 requires at least these server-side components.

### 1. Agent Registry

Stores:

- agent identity
- bind relationship
- capabilities
- last online time
- current execution readiness state

### 2. Connection Manager

Handles:

- active WebSocket sessions
- online/offline transitions
- single-agent connection ownership

### 3. Pairing Service

Handles:

- pairing code creation
- one-time validation
- long-lived device token issuance

### 4. Command Router

Handles:

- routing commands from AutoGLM-GUI to agent
- delivering `command_result` back to caller

### 5. State Store

Tracks:

- paired
- online
- connected
- executable
- reconnecting
- permission-related readiness fields

## Android Agent Additions

Do not replace the current local execution layer. Add a reverse-connection layer above it.

Needed modules:

### 1. `ReverseConnectionClient`

- manages outbound WebSocket
- handles reconnect

### 2. `PairingStateStore`

- stores `agent_id`
- stores long-lived device token
- stores bind metadata

### 3. `ReconnectPolicy`

- exponential backoff
- reconnect on network recovery

### 4. `StateReporter`

- reports foreground state
- reports accessibility state
- reports screen capture readiness

The existing command implementation can be reused:

- screenshot
- tap
- swipe
- type_text
- current_app

## AutoGLM-GUI Additions

### 1. Connection mode abstraction

Add a connection mode flag for devices:

- `direct_lan`
- `reverse_agent`

### 2. Dedicated "Add Android Agent" entry

The desktop side should not force users to infer ADB vs remote device vs agent mode.

Needs:

- create pairing code
- show pairing status
- show online/connectable state
- guide first verification

### 3. Command routing split

- `direct_lan` continues using current Remote Device path
- `reverse_agent` uses server-side agent router

### 4. User-readable states

At minimum:

- not paired
- paired
- online
- connected
- executable
- reconnecting
- missing permission

## Setup Flow Changes

These are not post-protocol polish. They are part of the value of the next phase.

### 1. Convert Android Agent home from status panel to setup checklist

The home screen should answer:

- what this app is
- what is incomplete
- what to do next

### 2. Turn permission flow into a serial checklist

At minimum:

1. start agent
2. enable accessibility
3. grant screen capture
4. return to AutoGLM-GUI for pairing/connect

### 3. De-emphasize IP/port in the main flow

Address/port should become advanced/debug information rather than primary user guidance.

### 4. Explicitly tell the user what to do next in AutoGLM-GUI

After phone-side prep is complete, the app should say:

- setup complete
- return to AutoGLM-GUI
- add Android Agent / complete pairing
- run first connectivity checks

### 5. Add clear "Add Android Agent" desktop entry

This should exist regardless of direct or reverse mode.

### 6. Productize first-connect verification

Suggested fixed verification path:

1. test screenshot
2. test current_app
3. test simple action

### 7. Make failure recovery explicit

At minimum, handle:

- pairing failed
- online but not executable
- reconnecting
- desktop cannot find device
- required permission missing

## Phase 1 Scope

Phase 1 should deliver only:

1. one Android Agent can pair successfully
2. agent can keep an outbound reverse connection
3. AutoGLM-GUI can see it as online
4. AutoGLM-GUI can send the five basic commands
5. disconnects can auto-recover
6. user does not need to manually enter IP/port

## Phase 1 Non-goals

Do not include in phase 1:

- multi-tenant architecture
- complex public-network traversal strategy
- device group scheduling
- full account system
- advanced permission orchestration
- media streaming
- file transfer platform
- multi-device advanced orchestration

## Risk Areas

### 1. Android background survivability

Different Android variants may aggressively manage background connections.

### 2. Pairing security

Need short TTL and one-time-use behavior for pairing code.

### 3. Reconnect storms

Need backoff and server-side throttling.

### 4. State inconsistency

Online, connected, and executable must not be conflated.

### 5. Expectation drift

Public messaging must not imply full public-network remote control in phase 1.

## Failure Recovery Requirements

The formal plan must include at least these flows:

1. pairing failure
2. agent online but not executable
3. reconnecting after disconnect

Each should define:

- what the user sees
- what next step is recommended
- what the system retries automatically

## Recommended Implementation Order

1. pairing API and agent registry
2. reverse connection client in Android Agent
3. heartbeat and reconnect policy
4. desktop "Add Android Agent" entry
5. command router for the five basic actions
6. setup checklist and failure recovery UX

## One-line Definition

Add a second, lower-friction Android Agent reverse connection mode without replacing the current LAN direct-connect model, and ship it together with a setup flow upgrade that turns Android Agent from an engineering status page into a user-facing initialization flow.
