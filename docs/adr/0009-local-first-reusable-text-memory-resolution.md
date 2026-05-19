# Local-first Reusable Text Memory resolution

## Context

Reusable Text Memory is a local store of user-provided snippets for later insertion into the Input Environment. In real speech use, users do not say a saved name exactly every time. They may say "邮箱", "邮箱地址", "电子邮箱", or "email" for the same saved value, and speech recognition may produce personalized word errors such as a person's name being heard as a similar-sounding phrase.

The Voice Keyboard Engine must support those variations without turning Reusable Text Memory into a broad knowledge base or a provider-controlled search feature. Wrong recall is worse than missed recall because the engine may insert the recalled text into the user's current Input Environment.

## Decision

Reusable Text Memory recall is resolved locally before asking a Speech Interpretation Provider to choose a key. The local resolver owns query extraction, type detection, alias matching, confidence scoring, and ambiguity handling.

Reusable Text Memory and Personal Lexicon are separate concepts:

- Reusable Text Memory stores the content that may be inserted.
- Personal Lexicon stores user-specific aliases, corrections, and preferred written forms that help interpret speech before a Reusable Text Operation is resolved.
- Reusable Text Memory edits change saved snippets or saved names. They do not automatically create Personal Lexicon rules unless the user explicitly asks for future wording to be remembered.

The first implementation will keep Personal Lexicon behavior small: it may derive aliases from saved names, saved values, and future explicit user alias rules, but it will not silently create new facts.

Resolver outcomes are explicit:

- `exact`: one saved memory name or alias directly matches the spoken query.
- `unique`: one saved memory has a strong type or alias match.
- `ambiguous`: multiple saved memories are plausible and the engine should ask the user to be more specific.
- `none`: no saved memory is safe to recall.

Only `exact` and `unique` outcomes may produce Text Insertion. `ambiguous` and `none` produce auxiliary feedback and do not insert a guessed value.

## Rules

1. Local deterministic evidence is the primary recall path. A Speech Interpretation Provider may help classify Instruction Mode, but it must not be the sole authority for which Reusable Text Memory key is read.
2. Stable value types, such as `contact.email`, `contact.phone`, `url`, `ssh_endpoint`, `api_key`, and `address`, are detected locally from saved values and key names.
3. Aliases are data, not scattered code branches. They may come from user wording, saved names, detected value types, or explicit future Personal Lexicon rules.
4. A type match can recall a value only when it selects one clear candidate. If the user has multiple email memories, "我的邮箱是什么" is ambiguous.
5. Sensitive memories are never shown in full in logs or list output. Sensitive values are not sent to remote providers for matching or embedding.
6. Corrective utterances such as "刚刚说的 X，那个 Y 实际上是 Z" may edit the matching Reusable Text Memory entry locally. If more than one entry could be edited, the engine asks for a more specific target instead of guessing.
7. For terms that speech recognition cannot reliably spell, the user may select the correct written form and teach a spoken form such as "以后我说 X 就是这个词". The Personal Lexicon stores the spoken form and local pronunciation variants against the selected written form.
8. Vector search or remote semantic matching may be added later only as candidate recall. It must pass the local resolver's confidence and ambiguity gates before a value is inserted.
9. The resolver may miss. It must not guess a low-confidence candidate.

## Consequences

Common Reusable Text Operations, such as recalling one saved email or phone number, can complete without a provider round trip and should stay fast. The resolver's local decision path should remain small enough to run in memory with a target of P95 under 30 ms for typical local stores.

The engine needs a small metadata layer around saved Reusable Text Memory. The local store is `reusable_text_memory.json`; current code should not keep a parallel old naming surface for the capability.

Personal Lexicon needs its own module and persistence in a later slice. Keeping it separate prevents correction rules, hotwords, and reusable snippets from becoming one overloaded memory feature.
