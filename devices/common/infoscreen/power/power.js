'use strict';
/* Standby policy for the info screen; shares the e5-power backend with LuCI. */

const app = document.getElementById('app');
const titleNode = document.getElementById('screen-title');
const subtitleNode = document.getElementById('screen-subtitle');
const POLL_MS = 2000;

const L = (zh, en) => (e5.lang === 'en' ? en : zh);
const STATE_TEXT = {
	ONLINE: () => L('在线', 'Online'),
	IDLE: () => L('浅待机 · 热点保持', 'Idle · hotspot kept'),
	DEEP: () => L('深睡', 'Deep sleep')
};
const BLOCK_TEXT = {
	'audio playing': () => L('正在播放音频', 'Audio is playing'),
	'SIPA wakelock still held': () => L('基带仍持有唤醒锁', 'Modem holds a wakelock')
};

function el(tag, cls, text) {
	const n = document.createElement(tag);
	if (cls) n.className = cls;
	if (text != null) n.textContent = text;
	return n;
}
function duration(seconds) {
	if (seconds == null) return '—';
	seconds = Math.max(0, Math.round(seconds));
	if (seconds < 60) return seconds + L(' 秒', ' s');
	return Math.floor(seconds / 60) + L(' 分 ', ' min ') + (seconds % 60) + L(' 秒', ' s');
}

let busy = false;
let inputs = {};
let badge, countdown, message;

function statusLine(s) {
	const live = s.state || {};
	if (live.state === 'IDLE')
		return live.deep_in != null ? L('距深睡：', 'Deep sleep in: ') + duration(live.deep_in)
			: L('深睡已禁用，热点保持开启', 'Deep sleep disabled; hotspot stays on');
	if (live.state === 'DEEP') return L('系统挂起中', 'System suspending');
	if (live.idle_in != null) return L('距浅待机：', 'Idle in: ') + duration(live.idle_in);
	if ((live.config || s.config || {}).idle_min === 0) return L('自动待机已关闭', 'Automatic standby is off');
	if (live.hold_in != null) return L('唤醒保持中：', 'Holding awake: ') + duration(live.hold_in);
	return L('等待空闲计时', 'Waiting for the idle timer');
}

function paintStatus(s) {
	const live = s.state || {};
	badge.textContent = (STATE_TEXT[live.state] || (() => '—'))();
	let line = statusLine(s);
	if (live.deep_blocked)
		line += ' · ' + L('深睡暂缓：', 'Deep sleep deferred: ') + (BLOCK_TEXT[live.deep_blocked] || (() => live.deep_blocked))();
	countdown.textContent = line;
	if (live.last_error) showMessage(live.last_error, true);
}

function showMessage(text, error) {
	message.textContent = text;
	message.classList.toggle('error', !!error);
}

function numberField(label, key, value, min, note) {
	const wrap = el('label', 'field');
	wrap.append(el('span', 'field-label', label));
	const input = el('input');
	input.type = 'number'; input.min = min; input.max = 1440; input.step = 1;
	input.value = value == null ? '' : value;
	inputs[key] = input;
	wrap.append(input);
	if (note) wrap.append(el('small', 'note', note));
	return wrap;
}

function render(s) {
	app.replaceChildren();
	inputs = {};
	titleNode.textContent = L('省电待机', 'Power standby');
	subtitleNode.textContent = L('空闲自动待机 · 热点浅待机保持', 'Staged standby · hotspot kept while idle');

	const status = el('section', 'card');
	status.append(el('h2', null, L('当前状态', 'Current state')));
	const row = el('div', 'status-row');
	badge = el('span', 'badge');
	countdown = el('span', 'countdown');
	row.append(badge, countdown);
	status.append(row);
	app.append(status);

	if (!s.ok) {
		app.append(el('section', 'card', s.error || L('待机服务不可用', 'Standby service unavailable')));
		message = el('p', 'message');
		app.append(message);
		return;
	}
	const cfg = s.config || {};
	const form = el('section', 'card');
	form.append(el('h2', null, L('待机策略', 'Standby policy')));
	form.append(numberField(L('空闲多久进入浅待机（分钟）', 'Idle minutes before standby'), 'idle_min', cfg.idle_min, 0,
		L('0 = 关闭。浅待机关闭蜂窝、蓝牙与 SIM 轮询，热点保持；手机连上 Wi-Fi 即恢复网络。',
		  '0 = off. Idle turns off cellular, Bluetooth and SIM polling; a phone associating restores the network.')));
	form.append(numberField(L('浅待机多久进入深睡（分钟）', 'Idle minutes before deep sleep'), 'deep_min', cfg.deep_min, 0,
		L('0 = 深睡已禁用。深睡关闭热点并挂起系统，仅电源键、USB 或充电器唤醒。',
		  '0 = disabled. Deep sleep stops the hotspot and suspends; only power key, USB or charger wake it.')));
	form.append(numberField(L('唤醒后保持清醒（分钟）', 'Minutes awake after waking'), 'hold_awake_min', cfg.hold_awake_min, 1,
		L('避免刚唤醒又立刻待机。', 'Prevents immediately re-entering standby.')));
	const check = el('label', 'check');
	const inhibit = el('input');
	inhibit.type = 'checkbox'; inhibit.checked = !!cfg.inhibit;
	inputs.inhibit = inhibit;
	check.append(inhibit, el('span', null, L('保持唤醒（暂停自动待机）', 'Keep awake (pause standby)')));
	form.append(check);
	const wakeCheck = el('label', 'check');
	const wakeOnClient = el('input');
	wakeOnClient.type = 'checkbox'; wakeOnClient.checked = !!cfg.wake_on_client;
	inputs.wake_on_client = wakeOnClient;
	wakeCheck.append(wakeOnClient, el('span', null, L('仅连接设备时开启基带（亮屏保持浅待机，连 Wi-Fi 或 USB 才联网）', 'Only restore cellular on client connect (stay idle until Wi-Fi or USB)')));
	form.append(wakeCheck);
	form.append(el('p', 'note', L('浅待机与深睡期间不接收短信和来电。计时参数保存后即时生效。',
		'SMS and calls are not received while idle or asleep. Timer changes apply immediately.')));
	const actions = el('div', 'actions');
	const apply = el('button', 'primary', L('应用设置', 'Apply'));
	const reset = el('button', null, L('恢复默认', 'Defaults'));
	apply.onclick = () => change(false);
	reset.onclick = () => change(true);
	actions.append(apply, reset);
	form.append(actions);
	app.append(form);
	message = el('p', 'message');
	message.setAttribute('role', 'status');
	app.append(message);
	paintStatus(s);
}

async function change(reset) {
	if (busy) return;
	busy = true;
	app.querySelectorAll('button,input').forEach(n => n.disabled = true);
	try {
		let result;
		if (reset) result = await e5.api('/reset', { method: 'POST', body: {} });
		else {
			const body = {};
			for (const key of ['idle_min', 'deep_min', 'hold_awake_min']) {
				const input = inputs[key];
				if (!input.checkValidity() || input.value === '')
					throw new Error(L('请填写有效的分钟数', 'Enter a valid number of minutes'));
				body[key] = +input.value;
			}
			body.inhibit = inputs.inhibit.checked;
			body.wake_on_client = inputs.wake_on_client.checked;
			result = await e5.api('/apply', { method: 'POST', body });
		}
		if (!result.ok) throw new Error(result.error || 'Failed');
		render(result);
		showMessage(L('已保存，即时生效', 'Saved; applies immediately'), false);
	} catch (e) {
		showMessage(e.message, true);
	} finally {
		busy = false;
		app.querySelectorAll('button,input').forEach(n => n.disabled = false);
	}
}

async function refresh(initial) {
	try {
		const s = await e5.api('/status');
		if (initial) render(s);
		else if (!busy && badge) paintStatus(s);
	} catch (e) {
		if (initial) render({ ok: false, error: e.message });
	}
}

e5.onLang(() => refresh(true));
refresh(true);
setInterval(() => { if (!document.hidden) refresh(false); }, POLL_MS);