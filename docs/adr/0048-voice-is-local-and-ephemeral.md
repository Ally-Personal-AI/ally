# ADR 0048: Voice is local-only and audio is ephemeral by default

## Status

Accepted

## Context

Conversational voice is central to Ally's long-term personal-assistant vision,
but microphone audio and synthesized responses are highly private.

Choosing an ASR or TTS engine before the dedicated machine is available would
couple Ally to an unmeasured implementation. Allowing a voice layer to call its
own model/runtime would also create a second private-inference authority that
could bypass validated runtime selection, context composition, or tool policy.

Raw audio persistence is not required for a basic conversational turn and would
create an additional sensitive data store.

## Decision

Define provider-neutral ASR and TTS contracts before selecting concrete engines.

Private voice providers must explicitly declare the `local` trust domain. The
voice-turn coordinator verifies both providers before either is called.

Recognized text is routed through the existing
`AllyApplication.send_message` operation. Voice therefore does not gain its own
model endpoint, model selection, memory/context composition, or tool authority.

Raw input and synthesized output audio are ephemeral by default. The existing
conversation store may persist the recognized user text and assistant response
text exactly as it does for typed chat.

Initial file ingestion supports only bounded uncompressed signed 16-bit PCM WAV
with explicit duration, size, channel, and sample-rate limits.

## Consequences

- cloud ASR/TTS and remote fallback are excluded from private voice;
- voice inherits Ally's existing validated private-inference and authority
  boundaries;
- an external TTS configuration fails before ASR receives private audio;
- voice turns do not create a parallel conversation or transcript store;
- production speech-engine selection can wait for measured dedicated-machine
  evidence;
- microphone capture, playback, wake-word, and always-listening behavior remain
  separate presentation/platform decisions; and
- a future explicit raw-audio retention feature would require its own privacy
  and user-control design.
