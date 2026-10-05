# No network, no AI API

Full Migration, Context Handoff, receipts, validate, conformance and verify run on local files without GPT/Claude/Gemini or other AI APIs. No key/token is required, and no default runtime telemetry or feedback submission is added. PyYAML is the sole runtime dependency.

Conformance and the synthetic recording install a Python network sentinel over socket connections, DNS, urllib and HTTP(S) connection entry points. They remove API-key/token/secret environment variables for the check, deliberately run a blocked DNS canary to prove interception, then require **zero network attempts** during the workflows. The recording executes real CLI child processes. This is a Python sentinel, not an OS firewall or a sandbox for arbitrary plugin/native code.

Fresh installation and release tools are separate: pip may retrieve packages when explicitly enabled; optional dependency advisory checks fetch public package name/version metadata from PyPI. Neither sends fixture contents or user memory. Use a local wheelhouse and omit `--allow-index` for offline package installation. Current advisory checks cannot run completely offline and are recorded `NOT_RUN` when unavailable.

```sh
memlink conformance --report conformance.json
python -m memlink.demo --out synthetic-demo
```

Online Connectors, if introduced later, must remain optional and disclose costs, privacy, recipients and authorization separately. Core offline operation must remain available. Reading generated context in a client is outside this guarantee: that client may independently contact model services or maintain memory.
