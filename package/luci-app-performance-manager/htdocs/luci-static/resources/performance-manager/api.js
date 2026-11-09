'use strict';
'require baseclass';
'require rpc';

return baseclass.extend({
	__init__: function() {
		this.status = rpc.declare({ object: 'performance-manager', method: 'status', params: [] });
		this.capabilities = rpc.declare({ object: 'performance-manager', method: 'capabilities', params: [] });
		this.topology = rpc.declare({ object: 'performance-manager', method: 'topology', params: [] });
		this.recommendations = rpc.declare({ object: 'performance-manager', method: 'recommendations', params: [] });
		this.transactions = rpc.declare({ object: 'performance-manager', method: 'transactions', params: [] });
		this.locks = rpc.declare({ object: 'performance-manager', method: 'locks', params: [] });
		this.history = rpc.declare({ object: 'performance-manager', method: 'history', params: [ 'limit' ] });
		this.rill = rpc.declare({ object: 'performance-manager', method: 'rill_status', params: [] });
		this.rillRefresh = rpc.declare({ object: 'performance-manager', method: 'rill_refresh', params: [] });
		this.resources = rpc.declare({ object: 'performance-manager', method: 'resources', params: [] });
		this.diagnostics = rpc.declare({ object: 'performance-manager', method: 'diagnostics', params: [] });
		this.apply = rpc.declare({ object: 'performance-manager', method: 'apply', params: [ 'actionId', 'target', 'executionSource', 'decisionId' ] });
		this.confirm = rpc.declare({ object: 'performance-manager', method: 'confirm', params: [ 'transactionId' ] });
		this.rollback = rpc.declare({ object: 'performance-manager', method: 'rollback', params: [ 'transactionId' ] });
		this.benchmarkStart = rpc.declare({ object: 'performance-manager', method: 'benchmark_start', params: [ 'actionId', 'pathId', 'measurementClass', 'phase', 'sessionId', 'evidence', 'executionSource', 'decisionId' ] });
		this.benchmarkStatus = rpc.declare({ object: 'performance-manager', method: 'benchmark_status', params: [ 'sessionId' ] });
		this.benchmarkStop = rpc.declare({ object: 'performance-manager', method: 'benchmark_stop', params: [ 'sessionId' ] });
	}
});
