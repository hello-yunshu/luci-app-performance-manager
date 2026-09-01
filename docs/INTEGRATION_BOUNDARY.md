# Integration boundary

Performance Manager owns the business-specific feature mapping, Smart Decision
v2 policy state, selector, explainability and OpenWrt UI/package surface. Core
calls the external generic Rill Runtime v3 through a bounded UDS envelope and
keeps the final execution authority.

The external Rill Runtime owns generic ranking, online learning, persistence and
Runtime v3 conformance. It receives only the stable feature vector and legal
action candidates; it cannot call Core actuators. Missing Runtime, incompatible
schema/model generation, low confidence, drift or cooldown leaves Core on a
deterministic safe fallback or `pm.noop`.
