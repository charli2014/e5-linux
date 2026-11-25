'use strict';
// Standby policy screen: the same e5-power rpcd object LuCI uses, so both
// surfaces share one backend and one config file (/etc/e5-power.json).

return function(ctx) {
	function fail(r, code) {
		return { status: code ?? 502, type: 'application/json', body: sprintf('%J', r ?? { ok: false, error: 'Standby service unavailable' }) };
	}
	return {
		'GET /status': function(req) {
			let r = ctx.ubus('e5-power', 'get', {});
			return r ?? fail(null);
		},
		'POST /apply': function(req) {
			let b = req.body;
			if (type(b) != 'object') return fail({ ok: false, error: 'Invalid request' }, 400);
			let changes = {};
			for (let key in [ 'idle_min', 'deep_min', 'hold_awake_min' ]) {
				if (b[key] == null) continue;
				if (type(b[key]) != 'int' || b[key] < 0 || b[key] > 1440)
					return fail({ ok: false, error: 'Invalid minutes' }, 400);
				changes[key] = b[key];
			}
			if (b.inhibit != null) {
				if (type(b.inhibit) != 'bool') return fail({ ok: false, error: 'Invalid keep-awake flag' }, 400);
				changes.inhibit = b.inhibit;
			}
			if (b.wake_on_client != null) {
				if (type(b.wake_on_client) != 'bool') return fail({ ok: false, error: 'Invalid client-wake flag' }, 400);
				changes.wake_on_client = b.wake_on_client;
			}
			let r = ctx.ubus('e5-power', 'apply', { changes, persist: true });
			return r ?? fail(null);
		},
		'POST /reset': function(req) {
			let r = ctx.ubus('e5-power', 'reset', {});
			return r ?? fail(null);
		}
	};
};