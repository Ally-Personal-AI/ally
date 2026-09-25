# Local Voice Boundary

Ally voice is part of the private-intelligence trust domain.

Audio captured from the user, speech transcripts, assistant response text, and
synthesized speech are private by default. A voice feature must not create a new
remote inference path around Ally's existing private chat boundary.

## Phase 1 contract

The hardware-independent voice substrate contains:

- bounded signed 16-bit PCM audio models;
- strict uncompressed PCM16 WAV inspection/loading;
- replaceable speech-recognition and speech-synthesis protocols;
- an explicit provider trust-domain declaration;
- an application-level voice-turn coordinator; and
- a read-only WAV inspection CLI.

No production ASR/TTS engine is selected yet.

## Audio boundary

Input WAV files must be:

- regular files, not symbolic links;
- uncompressed PCM;
- signed 16-bit samples;
- mono or stereo;
- 8 kHz through 48 kHz;
- non-empty;
- at most 120 seconds; and
- within the bounded PCM/file size limits.

The CLI can inspect this metadata without transcribing it:

```bash
uv run ally voice inspect-wav ./synthetic.wav --json
```

The JSON result is path-free. The inspection command performs no model
inference and persists no audio.

## Voice-turn authority

A voice turn is:

```text
bounded local PCM
       |
       v
local ASR provider
       |
       v
transcript
       |
       v
AllyApplication.send_message(...)
       |
       v
assistant response text
       |
       v
local TTS provider
       |
       v
bounded local PCM
```

The coordinator calls the existing private chat authority instead of adding a
second conversational runtime.

Therefore voice inherits:

- validated active runtime selection;
- loopback-only private inference;
- user instruction composition;
- memory and knowledge grounding;
- conversation persistence;
- existing permission/tool policy boundaries; and
- existing model/provider provenance.

The voice request deliberately has no raw development endpoint/model fields.

## Fail-closed provider trust

Both speech providers declare a trust domain.

The current accepted value for private voice is exactly `local`.

Before calling ASR, the coordinator verifies both ASR and TTS are local. This
means an external TTS provider cannot cause the user's audio to be transcribed
first, and an external ASR provider never receives the audio.

There is no cloud fallback.

## Persistence

Phase 1 does not persist raw input or output audio.

The existing chat boundary persists the recognized user text and assistant text
as normal conversation messages. This is intentional: voice is a presentation
mode for the same durable conversation, not a hidden parallel transcript store.

A future explicit audio-history feature would require a separate user-facing
retention decision.

## Production engines

The dedicated machine should eventually evaluate local ASR and TTS candidates
for:

- no-egress operation;
- recognition/synthesis quality;
- first-response latency;
- sustained latency;
- unified-memory usage;
- model/runtime artifact provenance;
- licensing;
- supported languages/voices; and
- failure behavior.

Do not select a production speech engine merely because it can be imported or
runs in hosted CI.

Likely engine families can be evaluated later, but the Ally Core contract should
remain independent of any one implementation.

## Future interaction layers

After a local ASR/TTS pair is qualified:

1. add signed-desktop microphone capture and audio playback;
2. expose clear microphone/recording state;
3. add turn cancellation;
4. add interruption/barge-in only after ordinary turns are stable; and
5. consider wake-word or continuous-listening modes only as explicit opt-in
   features with visible privacy state.

Voice must not expand task/tool authority. Spoken requests pass through the same
approval and policy paths as typed requests.
