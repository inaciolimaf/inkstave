"""Deterministic, network-free stand-ins for slow externals (spec 54).

This package ships with the application but is **only activated by env flags**
(``COMPILE_MODE=mock`` / ``LLM_STUB=true``). The default production code paths
(``compile_mode="real"``, ``llm_stub=False``) never import or touch it, so the
real Tectonic and LLM integrations are unchanged. The e2e suite (spec 54) flips
these flags to keep its smoke tier instant and reproducible.
"""
