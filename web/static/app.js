const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

createApp({
  setup() {
    const currentTab = ref('dashboard');
    const tabs = [
      { id: 'dashboard', name: '仪表盘', icon: 'layout-dashboard' },
      { id: 'sources', name: '订阅源管理', icon: 'server' },
      { id: 'naming', name: '节点命名规则', icon: 'tag' },
      { id: 'cf', name: 'Cloudflare 优选', icon: 'sparkles' },
      { id: 'console', name: '运行控制台', icon: 'terminal' },
      { id: 'settings', name: '系统设置', icon: 'settings' },
    ];

    const status = ref({
      is_running: false,
      current_stage: 'idle',
      progress: { current: 0, total: 0, percentage: 0 },
      last_run: null,
      last_status: '就绪',
      last_node_count: 0,
      last_residential_count: 0,
      output_files: []
    });

    const stats = ref({
      total_nodes: 0,
      residential_nodes: 0,
      by_proto: {},
      top_countries: {}
    });

    const config = ref({
      port: 18168,
      scheduler: { enabled: true, interval_hours: 6 },
      naming_rule: { template: '{flag} {cname} {idx:02d}{tag}{risk_tag} - {lat_str}-{spd_str}' },
      cf_clean_ip: { enabled: true, custom_ips: [], top_n_to_use: 3 },
      network: { front_proxy: '', max_workers: 32 }
    });

    const sources = ref([]);
    const cleanIps = ref([]);
    const testingCf = ref(false);
    const logs = ref([]);
    const customIpsText = ref('');
    const showAddModal = ref(false);
    const newSource = ref({ name: '', url: '' });

    const toast = ref({ show: false, message: '' });
    const showToast = (msg) => {
      toast.value = { show: true, message: msg };
      setTimeout(() => { toast.value.show = false; }, 3000);
    };

    const nameTags = [
      { key: '{flag}', desc: '国旗Emoji' },
      { key: '{cname}', desc: '地区中文全称' },
      { key: '{cc}', desc: '国家代码HK/TW' },
      { key: '{idx:02d}', desc: '两位序号01' },
      { key: '{tag}', desc: '家宽标识' },
      { key: '{risk_tag}', desc: '风控分数' },
      { key: '{lat_str}', desc: '延迟如93ms' },
      { key: '{spd_str}', desc: '带宽如45Mbps' },
      { key: '{proto}', desc: '协议类型' },
    ];

    const insertTag = (tagKey) => {
      config.value.naming_rule.template += tagKey;
    };

    const previewNodeName = computed(() => {
      let tmpl = config.value.naming_rule?.template || '{flag} {cname} {idx:02d}{tag} - {lat_str}-{spd_str}';
      return tmpl
        .replace('{flag}', '🇭🇰')
        .replace('{cname}', '中国香港 (Hong Kong)')
        .replace('{country}', '中国香港 (Hong Kong)')
        .replace('{cc}', 'HK')
        .replace('{idx:02d}', '01')
        .replace('{idx}', '1')
        .replace('{tag}', ' (家宽)')
        .replace('{risk_tag}', '')
        .replace('{lat_str}', '93ms')
        .replace('{latency}', '93ms')
        .replace('{spd_str}', '45Mbps')
        .replace('{speed}', '45Mbps')
        .replace('{proto}', 'VLESS');
    });

    const subUrl = (filename) => {
      const host = window.location.host;
      const protocol = window.location.protocol;
      return `${protocol}//${host}/sub/${filename}`;
    };

    const copyText = (text) => {
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text);
      } else {
        const inp = document.createElement('input');
        inp.value = text;
        document.body.appendChild(inp);
        inp.select();
        document.execCommand('copy');
        document.body.removeChild(inp);
      }
      showToast('订阅链接已复制到剪贴板！');
    };

    const stageName = (st) => {
      const names = {
        idle: '空闲',
        starting: '正在准备启动',
        preparing: '校验 sing-box 内核及环境',
        fetching: '抓取全部上游订阅源',
        parsing: '协议特征智能解包解析',
        optimizing_cf: 'Cloudflare 优选 IP 注入',
        prefiltering: 'DoH + 端口连通性预检',
        probing: '多进程真实隧道 HTTPS 测活',
        chain_retest: '家宽双跳链式复测',
        exporting: '生成多格式客户端订阅'
      };
      return names[st] || st;
    };

    const getLogColor = (line) => {
      if (line.includes('[错误]') || line.includes('❌')) return 'text-red-400';
      if (line.includes('🎉') || line.includes('[+]')) return 'text-emerald-400';
      if (line.includes('🚀') || line.includes('===') || line.includes('优选')) return 'text-cyan-300 font-bold';
      if (line.includes('进度:')) return 'text-indigo-300';
      return 'text-slate-300';
    };

    const clearLogs = () => { logs.value = []; };

    // --- API Calls ---
    const fetchStatus = async () => {
      try {
        const r = await fetch('/api/status');
        if (r.ok) status.value = await r.json();
      } catch (e) {}
    };

    const fetchStats = async () => {
      try {
        const r = await fetch('/api/stats');
        if (r.ok) {
          stats.value = await r.json();
          renderCharts();
        }
      } catch (e) {}
    };

    const fetchConfig = async () => {
      try {
        const r = await fetch('/api/config');
        if (r.ok) {
          const cfg = await r.json();
          config.value = cfg;
          customIpsText.value = (cfg.cf_clean_ip?.custom_ips || []).join('\n');
        }
      } catch (e) {}
    };

    const fetchSources = async () => {
      try {
        const r = await fetch('/api/sources');
        if (r.ok) sources.value = await r.json();
      } catch (e) {}
    };

    const fetchCleanIps = async () => {
      try {
        const r = await fetch('/api/cf-clean-ips');
        if (r.ok) {
          const d = await r.json();
          cleanIps.value = d.clean_ips || [];
        }
      } catch (e) {}
    };

    const testCleanIps = async () => {
      testingCf.value = true;
      try {
        const r = await fetch('/api/cf-clean-ips/test', { method: 'POST' });
        if (r.ok) {
          const d = await r.json();
          cleanIps.value = d.clean_ips || [];
          showToast('Clean IP 测速更新完成！');
        }
      } catch (e) {
        showToast('测速失败: ' + e);
      } finally {
        testingCf.value = false;
      }
    };

    const triggerRun = async () => {
      try {
        const r = await fetch('/api/run', { method: 'POST' });
        const res = await r.json();
        if (r.ok) {
          showToast(res.message);
          fetchStatus();
          currentTab.value = 'console';
        } else {
          showToast('失败: ' + res.detail);
        }
      } catch (e) {
        showToast('请求异常: ' + e);
      }
    };

    const toggleSource = async (id) => {
      try {
        const r = await fetch(`/api/sources/${id}/toggle`, { method: 'POST' });
        if (r.ok) fetchSources();
      } catch (e) {}
    };

    const deleteSource = async (id) => {
      if (!confirm('确认删除此订阅源吗？')) return;
      try {
        const r = await fetch(`/api/sources/${id}`, { method: 'DELETE' });
        if (r.ok) {
          showToast('已删除订阅源');
          fetchSources();
        }
      } catch (e) {}
    };

    const openAddSourceModal = () => {
      newSource.value = { name: '', url: '' };
      showAddModal.value = true;
    };

    const confirmAddSource = async () => {
      if (!newSource.value.url) return;
      try {
        const r = await fetch('/api/sources', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newSource.value)
        });
        if (r.ok) {
          showToast('添加成功');
          showAddModal.value = false;
          fetchSources();
        }
      } catch (e) {
        showToast('添加失败');
      }
    };

    const testSource = async (src) => {
      showToast(`正在测试抓取: ${src.name}...`);
      try {
        const r = await fetch('/api/sources/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: src.url })
        });
        const res = await r.json();
        if (res.status === 'ok') {
          showToast(`测试成功! 提取到 ${res.node_count} 个节点`);
        } else {
          showToast(`拉取失败: ${res.message}`);
        }
      } catch (e) {
        showToast('测试网络异常');
      } finally {
        fetchSources();
      }
    };

    const saveNamingRule = async () => {
      try {
        const r = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ naming_rule: config.value.naming_rule })
        });
        if (r.ok) showToast('命名规则已保存！');
      } catch (e) {
        showToast('保存失败');
      }
    };

    const saveCleanIpConfig = async () => {
      const ips = customIpsText.value.split('\n').map(s => s.trim()).filter(Boolean);
      config.value.cf_clean_ip.custom_ips = ips;
      try {
        const r = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cf_clean_ip: config.value.cf_clean_ip })
        });
        if (r.ok) {
          showToast('Cloudflare 优选设置已保存！');
          fetchCleanIps();
        }
      } catch (e) {
        showToast('保存失败');
      }
    };

    const saveGlobalSettings = async () => {
      try {
        const r = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            scheduler: config.value.scheduler,
            network: config.value.network
          })
        });
        if (r.ok) showToast('全局配置已成功保存！');
      } catch (e) {
        showToast('保存失败');
      }
    };

    // --- SSE Real-time Logs ---
    let eventSource = null;
    const startLogStream = () => {
      if (eventSource) eventSource.close();
      eventSource = new EventSource('/api/logs/stream');
      eventSource.onmessage = (ev) => {
        if (ev.data && !ev.data.startsWith(':')) {
          logs.value.push(ev.data);
          if (logs.value.length > 2000) logs.value.shift();
          nextTick(() => {
            const el = document.getElementById('terminal-box');
            if (el) el.scrollTop = el.scrollHeight;
          });
        }
      };
    };

    // --- Chart.js Rendering ---
    let protoChart = null;
    let countryChart = null;

    const renderCharts = () => {
      nextTick(() => {
        // 1. Proto Chart
        const pCtx = document.getElementById('protoChart');
        if (pCtx && stats.value.by_proto) {
          const labels = Object.keys(stats.value.by_proto);
          const data = Object.values(stats.value.by_proto);
          if (protoChart) protoChart.destroy();
          protoChart = new Chart(pCtx, {
            type: 'doughnut',
            data: {
              labels: labels.map(l => l.toUpperCase()),
              datasets: [{
                data: data,
                backgroundColor: ['#38bdf8', '#818cf8', '#34d399', '#f59e0b', '#ec4899', '#a855f7'],
                borderColor: '#0f172a',
                borderWidth: 2
              }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', font: { size: 11 } } } }
            }
          });
        }

        // 2. Country Chart
        const cCtx = document.getElementById('countryChart');
        if (cCtx && stats.value.top_countries) {
          const labels = Object.keys(stats.value.top_countries);
          const data = Object.values(stats.value.top_countries);
          if (countryChart) countryChart.destroy();
          countryChart = new Chart(cCtx, {
            type: 'bar',
            data: {
              labels: labels,
              datasets: [{
                label: '节点数量',
                data: data,
                backgroundColor: 'rgba(99, 102, 241, 0.7)',
                borderColor: '#6366f1',
                borderRadius: 6
              }]
            },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: { legend: { display: false } },
              scales: {
                x: { ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
              }
            }
          });
        }
      });
    };

    onMounted(async () => {
      await fetchConfig();
      await fetchSources();
      await fetchStatus();
      await fetchStats();
      await fetchCleanIps();
      startLogStream();

      // 定时轮询状态
      setInterval(fetchStatus, 3000);
      setInterval(fetchStats, 15000);

      // 初始化图标
      nextTick(() => { lucide.createIcons(); });
    });

    watch(currentTab, () => {
      nextTick(() => {
        lucide.createIcons();
        if (currentTab.value === 'dashboard') renderCharts();
      });
    });

    return {
      currentTab, tabs, status, stats, config, sources, cleanIps, testingCf,
      logs, customIpsText, showAddModal, newSource, toast, nameTags, previewNodeName,
      subUrl, copyText, stageName, getLogColor, clearLogs, insertTag,
      triggerRun, toggleSource, deleteSource, openAddSourceModal, confirmAddSource,
      testSource, saveNamingRule, saveCleanIpConfig, saveGlobalSettings, testCleanIps
    };
  }
}).mount('#app');
