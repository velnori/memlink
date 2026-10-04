# ChatGPT conversation transcript export

Format `chatgpt` reads conversation JSON; it is not ChatGPT Saved Memory. The reader selects `current_node` and follows its parent chain to the active conversation branch. Without current_node it can infer only a unique valid leaf. Cycles, orphan parents, missing current nodes and ambiguous active paths produce deterministic invalid records.

User/assistant readable text becomes transcript bodies with timestamps and canonical identity. Non-active branches and original graph fields are preserved in `chatgpt_transcript` transport extensions with warnings; they are not concatenated into the selected conversation. Tool/attachment/opaque content is preserved/reported as raw data, not interpreted or OCRed. Conversations with no supported human text are marked unsupported rather than converted into an empty green memory.

This is reader-only. Convert to a supported writer with best-effort receipt/archive, or strict mode to block unallowed adaptation. Returning to ChatGPT/Saved Memory and online upload are outside this file adapter.
