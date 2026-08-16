'use strict';

export const VERSION = '1.0.0-rc.5';
export const SCHEMA_VERSION = 2;
export const WORKLOAD_CLASSES = [
	'plain_forwarding', 'local_endpoint', 'transparent_proxy', 'vpn_tunnel',
	'pppoe', 'wireless', 'storage_service'
];
export const APPLY_SCOPES = [ 'system', 'service', 'device', 'interface', 'radio', 'storage' ];
export const PERSISTENCE_CLASSES = [ 'runtime', 'uci_delta', 'persistent_config', 'pm_policy_replay' ];
export const OWNERS = [ 'user', 'external', 'preexisting', 'performance_manager', 'unknown' ];
export const TX_STATES = [
	'planned', 'locked', 'snapshotted', 'pending', 'applied', 'verified',
	'awaiting_confirm', 'committed', 'rolled_back', 'failed'
];
export const MEASUREMENT_CLASSES = [ 'controlled_ab', 'passive_before_after', 'health_only' ];
export const SAFE_ACTIONS = [ 'nic.ring.floor' ];
export const BENCHMARK_ACTIONS = [
	'network.backlog', 'network.budget', 'network.buffers', 'network.busy_poll',
	'netdev.tx_queue_len', 'nic.coalescing', 'service.irqbalance', 'tcp.cc',
	'qdisc.replace', 'fastpath.software_flow_offload', 'fastpath.hardware_flow_offload',
	'fastpath.third_party_sfe', 'cpu.governor'
];
