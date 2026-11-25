'use strict';
'require view';
'require rpc';
'require poll';
'require mu300.common as M';

const getPower = rpc.declare({object:'e5-power',method:'get',expect:{}});
const applyPower = rpc.declare({object:'e5-power',method:'apply',params:['changes','persist'],expect:{}});
const resetPower = rpc.declare({object:'e5-power',method:'reset',expect:{}});
const text = (zh,en) => M.translate(zh);
const STATE_TEXT = {ONLINE:['在线','Online'],IDLE:['浅待机 · 热点保持','Idle · hotspot kept'],DEEP:['深睡','Deep sleep']};
const BLOCK_TEXT = {'audio playing':['正在播放音频','Audio is playing'],'SIPA wakelock still held':['基带仍持有唤醒锁','Modem still holds a wakelock']};

function node(tag, cls, value) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (value != null) el.textContent = value;
    return el;
}
function field(label, input, note) {
    const wrap = node('label','power-field');
    wrap.append(node('span',null,label),input);
    if (note) wrap.append(node('small','mud-note',note));
    return wrap;
}
function duration(seconds) {
    if (seconds == null) return '—';
    seconds = Math.max(0, Math.round(seconds));
    if (seconds < 60) return seconds + text(' 秒',' s');
    return Math.floor(seconds/60) + text(' 分 ',' min ') + (seconds%60) + text(' 秒',' s');
}

return view.extend({
    load: function() { return getPower(); },
    render: function(s) {
        M.injectCss(); M.localizeMenu();
        this.root = node('div','mud mud-power power-settings');
        this.root.append(node('style',null,`
.mud-power{max-width:860px;margin:0 auto;padding:4px 0 12px}
.mud-power h2{margin:0 0 8px;padding:0;border:0;font-size:1.5rem;font-weight:650;letter-spacing:-.03em;color:var(--text,#222)}
.mud-power .mud-note{margin:0;color:var(--text-muted,#777);font-size:.77rem;line-height:1.65}
.mud-power .power-section{padding:22px;margin:0 0 20px;overflow-wrap:anywhere}
.mud-power .power-section h3{margin:0 0 14px;padding:0;border:0;font-size:1rem;font-weight:650;color:var(--text,#222)}
.power-status{display:flex;flex-wrap:wrap;align-items:baseline;gap:10px;margin-bottom:10px}
.power-state{border:1px solid var(--hairline,#ddd);border-radius:99px;padding:4px 12px;font-size:.8rem;font-weight:600;background:var(--surface-sunken,rgba(127,127,127,.05));color:var(--text,#222)}
.power-countdown{font-size:.85rem;color:var(--text-muted,#777);font-variant-numeric:tabular-nums}
.power-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:14px}
.power-field{display:flex;flex-direction:column;gap:7px;margin:0;font-size:.75rem;color:var(--text-muted,#777)}
.power-field input[type=number]{width:100%;box-sizing:border-box;margin:0;min-height:40px;padding:8px 10px;border:1px solid var(--hairline,#ddd);border-radius:8px;background:var(--surface,#fff);color:var(--text,#222);font-size:.84rem;font-variant-numeric:tabular-nums}
.power-field input:focus-visible{outline:2px solid var(--brand,#2f7bf6);outline-offset:2px}
.power-check{display:flex;gap:10px;align-items:flex-start;margin:16px 0 0;font-size:.8rem;color:var(--text,#222);cursor:pointer}
.power-check input{margin:3px 0 0;accent-color:var(--brand,#2f7bf6)}
.power-actions{display:flex;flex-wrap:wrap;gap:12px;justify-content:flex-end;padding-top:18px;margin-top:18px;border-top:1px solid var(--hairline,#ddd)}
.power-actions .mud-btn{min-height:38px;padding:8px 16px}
.power-message{font-size:.8rem;line-height:1.65;margin-top:14px;overflow-wrap:anywhere}
.power-message.error{color:var(--danger,#df596a)}
.power-note{font-size:.75rem;line-height:1.65;color:var(--text-muted,#777);margin:12px 0 0;overflow-wrap:anywhere}
@media(max-width:600px){.mud-power .power-section{padding:16px}.power-actions .mud-btn{flex:1}}
`));
        this.content = node('div'); this.root.append(this.content);
        this.paint(s);
        poll.add(() => {
            if (!this.root.isConnected || document.hidden || this.busy) return Promise.resolve();
            return getPower().then(fresh => {
                if (!fresh.ok) throw new Error(fresh.error || 'power state unavailable');
                this.paintStatus(fresh);
            }).catch(e => this.message(e.message,true));
        },2);
        return this.root;
    },
    message: function(value,error) {
        this.messageBox.textContent = M.translate(value);
        this.messageBox.classList.toggle('error',!!error);
    },
    paintStatus: function(s) {
        const live = s.state || {};
        const pair = STATE_TEXT[live.state] || ['—','—'];
        this.stateBadge.textContent = text(pair[0],pair[1]);
        let line;
        if (live.state === 'IDLE')
            line = live.deep_in != null ? text('距深睡：','Deep sleep in: ') + duration(live.deep_in)
                : text('深睡已禁用，热点保持开启','Deep sleep disabled; hotspot stays on');
        else if (live.state === 'DEEP')
            line = text('系统挂起中','System suspending');
        else if (live.idle_in != null)
            line = text('距浅待机：','Idle in: ') + duration(live.idle_in);
        else if ((live.config || s.config || {}).idle_min === 0)
            line = text('自动待机已关闭','Automatic standby is off');
        else if (live.hold_in != null)
            line = text('唤醒保持中：','Holding awake: ') + duration(live.hold_in);
        else
            line = text('等待空闲计时','Waiting for the idle timer');
        if (live.deep_blocked) {
            const reason = BLOCK_TEXT[live.deep_blocked] || [live.deep_blocked,live.deep_blocked];
            line += ' · ' + text('深睡暂缓：','Deep sleep deferred: ') + text(reason[0],reason[1]);
        }
        this.countdown.textContent = line;
        if (live.last_error) this.message(live.last_error,true);
    },
    paint: function(s) {
        this.content.replaceChildren();
        const head = node('div');
        head.append(node('h2',null,text('省电待机','Power standby')),
            node('p','mud-note',text('长时间无人使用时分级待机；热点在浅待机期间保持开启','Staged standby when unused; the hotspot stays on during idle')));
        this.content.append(head);
        if (!s.ok) {
            this.content.append(node('div','mud-card power-section',M.translate(s.error) || text('待机服务不可用','Standby service unavailable')));
            this.messageBox = node('div','power-message'); this.content.append(this.messageBox);
            return;
        }
        const cfg = s.config || {};
        const status = node('section','mud-card power-section');
        status.append(node('h3',null,text('当前状态','Current state')));
        const row = node('div','power-status');
        this.stateBadge = node('span','power-state');
        this.countdown = node('span','power-countdown');
        row.append(this.stateBadge,this.countdown);
        status.append(row);
        this.content.append(status);

        const form = node('section','mud-card power-section');
        form.append(node('h3',null,text('待机策略','Standby policy')));
        const grid = node('div','power-grid');
        const minutes = (key,value,min) => {
            const input = node('input');
            input.type = 'number'; input.min = min; input.max = 1440; input.step = 1;
            input.value = value == null ? '' : value;
            input.dataset.setting = key;
            return input;
        };
        this.idleMin = minutes('idle_min',cfg.idle_min,0);
        this.deepMin = minutes('deep_min',cfg.deep_min,0);
        this.holdMin = minutes('hold_awake_min',cfg.hold_awake_min,1);
        grid.append(
            field(text('空闲多久进入浅待机（分钟）','Idle minutes before standby'),this.idleMin,
                text('0 = 关闭自动待机。浅待机关闭蜂窝、蓝牙与 SIM 轮询，热点保持开启；手机连上 Wi-Fi 即恢复网络。','0 = off. Idle turns off cellular, Bluetooth and SIM polling; the hotspot stays on and a phone associating restores the network.')),
            field(text('浅待机多久进入深睡（分钟）','Idle minutes before deep sleep'),this.deepMin,
                text('0 = 深睡已禁用。深睡还会关闭热点并挂起系统，仅电源键、USB 或充电器可唤醒。','0 = deep sleep disabled. Deep sleep also stops the hotspot and suspends the system; only the power key, USB or the charger wake it.')),
            field(text('唤醒后保持清醒（分钟）','Minutes to stay awake after waking'),this.holdMin,
                text('避免刚唤醒又立刻待机。','Prevents immediately re-entering standby after a wake.')));
        form.append(grid);
        const check = node('label','power-check');
        this.inhibit = node('input'); this.inhibit.type = 'checkbox'; this.inhibit.checked = !!cfg.inhibit;
        check.append(this.inhibit,node('span',null,text('保持唤醒（暂停自动待机）','Keep awake (pause automatic standby)')));
        form.append(check);
        const wakeCheck = node('label','power-check');
        this.wakeOnClient = node('input'); this.wakeOnClient.type = 'checkbox'; this.wakeOnClient.checked = !!cfg.wake_on_client;
        wakeCheck.append(this.wakeOnClient,node('span',null,text('仅连接设备时开启基带（深睡唤醒/亮屏保持浅待机，有 Wi-Fi 或 USB 连接才恢复联网）','Only restore cellular when a client connects (keep idle on wake/bright screen until Wi-Fi or USB connects)')));
        form.append(wakeCheck);
        form.append(node('p','power-note',text('浅待机与深睡期间不接收短信和来电。计时参数保存后即时生效，无需重启。','SMS and calls are not received during idle or deep sleep. Timer changes apply immediately without a restart.')));
        const actions = node('div','power-actions');
        const apply = node('button','mud-btn on',text('应用设置','Apply settings'));
        const reset = node('button','mud-btn',text('恢复默认','Restore defaults'));
        apply.onclick = () => this.change(false);
        reset.onclick = () => this.change(true);
        actions.append(apply,reset);
        form.append(actions);
        this.content.append(form);
        this.messageBox = node('div','power-message');
        this.messageBox.setAttribute('role','status');
        this.content.append(this.messageBox);
        this.paintStatus(s);
    },
    change: async function(reset) {
        if (this.busy) return;
        try {
            let result;
            this.busy = true;
            this.content.querySelectorAll('button,input').forEach(e => e.disabled = true);
            if (reset) result = await resetPower();
            else {
                const changes = {};
                [['idle_min',this.idleMin],['deep_min',this.deepMin],['hold_awake_min',this.holdMin]].forEach(([key,input]) => {
                    if (!input.checkValidity() || input.value === '') throw new Error(text('请填写有效的分钟数','Enter a valid number of minutes'));
                    changes[key] = +input.value;
                });
                changes.inhibit = this.inhibit.checked;
                changes.wake_on_client = this.wakeOnClient.checked;
                result = await applyPower(changes,true);
            }
            if (!result.ok) throw new Error(result.error || 'Failed');
            this.paint(result);
            this.message(text('已保存，计时参数即时生效','Saved; timer changes apply immediately'));
        } catch(e) { this.message(e.message,true); }
        finally {
            this.busy = false;
            this.content.querySelectorAll('button,input').forEach(e => e.disabled = false);
        }
    },
    handleSaveApply:null,handleSave:null,handleReset:null
});