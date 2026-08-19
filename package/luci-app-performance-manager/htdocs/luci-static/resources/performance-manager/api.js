'use strict';
'require rpc';

return {
	status: rpc.declare({ object: 'performance-manager', method: 'status', params: [] }),
	capabilities: rpc.declare({ object: 'performance-manager', method: 'capabilities', params: [] }),
	topology: rpc.declare({ object: 'performance-manager', method: 'topology', params: [] }),
	recommendations: rpc.declare({ object: 'performance-manager', method: 'recommendations', params: [] }),
	transactions: rpc.declare({ object: 'performance-manager', method: 'transactions', params: [] }),
	locks: rpc.declare({ object: 'performance-manager', method: 'locks', params: [] }),
	history: rpc.declare({ object: 'performance-manager', method: 'history', params: [ 'limit' ] }),
	rill: rpc.declare({ object: 'performance-manager', method: 'rill_status', params: [] }),
	rillRefresh: rpc.declare({ object: 'performance-manager', method: 'rill_refresh', params: [] }),
	diagnostics: rpc.declare({ object: 'performance-manager', method: 'diagnostics', params: [] }),
	apply: rpc.declare({ object: 'performance-manager', method: 'apply', params: [ 'actionId', 'target', 'executionSource', 'decisionId' ] }),
	confirm: rpc.declare({ object: 'performance-manager', method: 'confirm', params: [ 'transactionId' ] }),
	rollback: rpc.declare({ object: 'performance-manager', method: 'rollback', params: [ 'transactionId' ] }),
	benchmarkStart: rpc.declare({ object: 'performance-manager', method: 'benchmark_start', params: [ 'actionId', 'pathId', 'measurementClass', 'phase', 'sessionId', 'evidence', 'executionSource', 'decisionId' ] }),
	benchmarkStatus: rpc.declare({ object: 'performance-manager', method: 'benchmark_status', params: [ 'sessionId' ] }),
	benchmarkStop: rpc.declare({ object: 'performance-manager', method: 'benchmark_stop', params: [ 'sessionId' ] })
};
