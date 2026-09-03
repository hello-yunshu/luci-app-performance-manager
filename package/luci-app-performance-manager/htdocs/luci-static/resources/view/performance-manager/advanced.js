'use strict';
'require view';
'require performance-manager.api as pm';
'require performance-manager.ui as pu';

return view.extend({
	load: function() { return Promise.all([ pm.status(), pm.capabilities(), pm.topology(), pm.recommendations(), pm.transactions(), pm.locks(), pm.diagnostics() ]); },
	render: function(data) {
		const s=data[0]||{}, c=data[1]||{}, t=data[2]||{}, r=data[3]||{}, tx=data[4]||{}, locks=data[5]||{}, d=data[6]||{};
		const hidden=(c.capabilities||[]).filter(function(x){ return x.availability !== 'available'; });
		return pu.page(_('Advanced'), _('Inspect the read-only contracts and resource state that explain the decisions shown in the supported views.'), [
			pu.grid([
			pu.card(_('Profile contract'), pu.jsonBox(s.profile || d.profile || {}, _('Profile status JSON'))),
			pu.card(_('Build recommendations'), pu.jsonBox({ missingRecommendedPackages:(s.profile||{}).missingRecommendedPackages || [], benchmarkProviders:(r.benchmarkActions||[]).map(function(x){ return {id:x.id,status:x.status,provider:x.provider}; }) }, _('Build and provider recommendations'))),
			pu.card(_('Hidden capabilities'), pu.jsonBox(hidden, _('Unavailable capability JSON'))),
			pu.card(_('Capability / Topology / TargetRef JSON'), pu.jsonBox({capabilities:c,topology:t}, _('Raw topology contract'))),
			pu.card(_('Resource locks'), pu.jsonBox(locks, _('Locks JSON'))),
			pu.card(_('Transactions'), pu.jsonBox(tx, _('Transactions JSON'))),
			pu.card(_('Resource usage'), pu.jsonBox(d.resources || {}, _('Resource usage JSON'))),
			pu.card(_('Diagnostics'), pu.jsonBox(d, _('Diagnostics JSON')))
			], 'pm-card-grid--dense')
		]);
	}
});
