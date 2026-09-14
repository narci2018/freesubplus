const { createApp, ref, computed, onMounted, nextTick, watch } = Vue;

const RECOMMENDED_SOURCES = [
  "https://zip.cm.edu.kg/all.txt",
  "https://bestcf.pages.dev/domain/all.txt",
  "https://bestcf.pages.dev/domain/mini.txt",
  "https://bestcf.pages.dev/domain/Domain-Asia.txt",
  "https://bestcf.pages.dev/vps789/top10.txt",
  "https://bestcf.pages.dev/vps789/top20.txt",
  "https://bestcf.pages.dev/vps789/top50.txt",
  "https://bestcf.pages.dev/vps789/top100.txt",
  "https://bestcf.pages.dev/domain/Domain-AI-VPS789.txt",
  "https://bestcf.pages.dev/domain/ygkkk/all.txt",
  "https://bestcf.pages.dev/domain/qms/all.txt",
  "https://bestcf.pages.dev/domain/fiatnorm/all.txt",
  "https://bestcf.pages.dev/domain/senflare/all.txt",
  "https://bestcf.pages.dev/domain/wuya/all.txt",
  "https://bestcf.pages.dev/domain/ircf/all.txt",
  "https://bestcf.pages.dev/domain/Domain-TOP.txt",
  "https://bestcf.pages.dev/wetest/ipv4.txt",
  "https://bestcf.pages.dev/uouin/all.txt",
  "https://bestcf.pages.dev/xinyitang3/ipv4.txt",
  "https://bestcf.pages.dev/luoli/all.txt",
  "https://bestcf.pages.dev/cfyes/ipv4.txt",
  "https://bestcf.pages.dev/cfyes/ipv6.txt",
  "https://addressesapi.090227.xyz/CloudFlareYes",
  "https://bestcf.pages.dev/tiancheng/all.txt",
  "https://bestcf.pages.dev/tiancheng/mini.txt",
  "https://bestcf.pages.dev/tiancheng/hk.txt",
  "https://bestcf.pages.dev/tiancheng/sg.txt",
  "https://bestcf.pages.dev/tiancheng/jp.txt",
  "https://bestcf.pages.dev/tiancheng/kr.txt",
  "https://bestcf.pages.dev/tiancheng/us.txt",
  "https://bestcf.pages.dev/s5gy/all.txt",
  "https://bestcf.pages.dev/s5gy/mini.txt",
  "https://bestcf.pages.dev/s5gy/hk.txt",
  "https://bestcf.pages.dev/s5gy/sg.txt",
  "https://bestcf.pages.dev/s5gy/jp.txt",
  "https://bestcf.pages.dev/s5gy/kr.txt",
  "https://bestcf.pages.dev/s5gy/us.txt",
  "https://bestcf.pages.dev/s5gy/tw.txt",
  "https://bestcf.pages.dev/gslege/Cfxyz.txt",
  "https://bestcf.pages.dev/gslege/SG.txt",
  "https://bestcf.pages.dev/gslege/DE.txt",
  "https://bestcf.pages.dev/gslege/US.txt",
  "https://cf.junzhen.qzz.io/best_ips.txt",
  "https://cf.junzhen.qzz.io/best_ips_bj.txt",
  "https://raw.githubusercontent.com/svip-s/cloudflare_ip/refs/heads/main/best_ips.txt",
  "https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/best_ips.txt",
  "https://raw.githubusercontent.com/love-ztm/cfip/refs/heads/main/ubest_ips.txt",
  "https://bestcf.pages.dev/zhixuanwang/ipv4-onlyip.txt",
  "https://addressesapi.090227.xyz/ip.164746.xyz",
  "https://bestcf.pages.dev/vvhan/ipv4.txt",
  "https://bestcf.pages.dev/vvhan/ipv6.txt",
  "https://bestcf.pages.dev/nirevil/ipv4.txt",
  "https://bestcf.pages.dev/nirevil/ipv6.txt",
  "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv4.txt",
  "https://raw.githubusercontent.com/ymyuuu/IPDB/refs/heads/main/BestCF/bestcfv6.txt",
  "https://raw.githubusercontent.com/yuanxiawan/cfipv4db/refs/heads/main/cfip.txt",
  "https://bestcf.pages.dev/cmliu/all.txt",
  "https://bestcf.pages.dev/cmliu2/all.txt",
  "https://bestcf.pages.dev/moistr/all.txt",
  "https://bestcf.pages.dev/lzj/all.txt",
  "https://bestcf.pages.dev/lajiao/all.txt",
  "https://bestcf.pages.dev/kristi/all.txt",
  "https://raw.githubusercontent.com/joname1/BestCFip/refs/heads/main/ipv4.txt",
  "https://raw.githubusercontent.com/joname1/BestCFip/refs/heads/main/ipv6.txt",
  "https://raw.githubusercontent.com/Senflare/Senflare-IP/refs/heads/main/IPlist-Pro.txt",
  "https://bestcf.pages.dev/ircf/ipv4.txt",
  "https://raw.githubusercontent.com/einsitang/my-fast-cf-ip/refs/heads/master/fastips.txt",
  "https://raw.githubusercontent.com/hubbylei/bestcf/refs/heads/main/bestcf.txt",
  "https://raw.githubusercontent.com/gshtwy/CF-DNS-Clone/refs/heads/main/wetest-cloudflare-v4.txt",
  "https://warp-masque-bestip.pages.dev/?ips=50&level=all&port=random",
  "https://warp-masque-bestip.pages.dev/?ips=50&level=p0&port=random",
  "https://warp-masque-bestip.pages.dev/?ips=50&level=198&port=random",
  "https://warp-masque-bestip.pages.dev/?ips=50&level=193&port=random",
  "https://warp-masque-bestip.pages.dev/?ips=50&level=192&port=random",
  "https://bestcf.pages.dev/random-region/mix2.txt",
  "https://090227.pages.dev/bestcf?isp=all&ips=20",
  "https://randomip.pages.dev/?c=all&n=50&p=random",
  "https://bestcf.pages.dev/tiancheng2/all.txt",
  "https://bestcf.pages.dev/tiancheng3/all.txt"
];

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
      network: { front_proxy: '', max_workers: 32 },
      github_sync: { enabled: false, token: '', repo: '', branch: 'main', target_dir: 'output', cdn_links: {} }
    });

    const sources = ref([]);
    const cleanIps = ref([]);
    const testingCf = ref(false);
    const logs = ref([]);
    const customIpsText = ref('');
    const showAddModal = ref(false);
    const newSource = ref({ name: '', url: '' });
    const showEditModal = ref(false);
    const editSourceForm = ref({ id: '', name: '', url: '', enabled: true });

    // Toast
    const toast = ref({ show: false, message: '' });
    const showToast = (msg) => {
      toast.value = { show: true, message: msg };
      setTimeout(() => { toast.value.show = false; }, 3000);
    };

    // --- 节点列表弹窗状态 ---
    const showNodesModal = ref(false);
    const nodesModalFilter = ref('all');
    const nodesList = ref([]);
    const loadingNodes = ref(false);
    const nodesSearch = ref('');
    const nodesProtoFilter = ref('ALL');
    const nodesPage = ref(1);
    const nodesPerPage = 50;

    const availableProtos = computed(() => {
      const set = new Set();
      nodesList.value.forEach(n => { if (n.proto) set.add(n.proto); });
      return Array.from(set).sort();
    });

    const filteredNodes = computed(() => {
      let list = nodesList.value;
      const kw = nodesSearch.value.trim().toLowerCase();
      if (kw) {
        list = list.filter(n => 
          (n.tag && n.tag.toLowerCase().includes(kw)) ||
          (n.server && n.server.toLowerCase().includes(kw)) ||
          (n.proto && n.proto.toLowerCase().includes(kw)) ||
          (String(n.port).includes(kw))
        );
      }
      if (nodesProtoFilter.value !== 'ALL') {
        list = list.filter(n => n.proto === nodesProtoFilter.value);
      }
      return list;
    });

    const totalNodesPages = computed(() => Math.ceil(filteredNodes.value.length / nodesPerPage) || 1);

    const paginatedNodes = computed(() => {
      const start = (nodesPage.value - 1) * nodesPerPage;
      return filteredNodes.value.slice(start, start + nodesPerPage);
    });

    const openNodesModal = async (filter) => {
      nodesModalFilter.value = filter;
      showNodesModal.value = true;
      loadingNodes.value = true;
      nodesSearch.value = '';
      nodesProtoFilter.value = 'ALL';
      nodesPage.value = 1;
      nextTick(() => { lucide.createIcons(); });
      try {
        const r = await fetch(`/api/nodes?filter=${filter}`);
        if (r.ok) {
          const d = await r.json();
          nodesList.value = d.nodes || [];
        }
      } catch (e) {
        showToast('获取节点列表失败: ' + e);
      } finally {
        loadingNodes.value = false;
        nextTick(() => { lucide.createIcons(); });
      }
    };

    const copyAllFilteredNodes = () => {
      const uris = filteredNodes.value.map(n => n.raw_uri || `${n.proto.toLowerCase()}://${n.server}:${n.port}#${encodeURIComponent(n.tag)}`).filter(Boolean);
      if (!uris.length) {
        showToast('当前无可用节点链接');
        return;
      }
      copyText(uris.join('\n'));
      showToast(`已成功复制 ${uris.length} 个节点链接到剪贴板！`);
    };

    const copyNodeUri = (node) => {
      const uri = node.raw_uri || `${node.proto.toLowerCase()}://${node.server}:${node.port}#${encodeURIComponent(node.tag)}`;
      copyText(uri);
    };

    const getProtoBadgeClass = (proto) => {
      const p = (proto || '').toUpperCase();
      if (p.includes('VLESS')) return 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30';
      if (p.includes('VMESS')) return 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30';
      if (p.includes('SS') || p.includes('SHADOWSOCKS')) return 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30';
      if (p.includes('TROJAN')) return 'bg-amber-500/20 text-amber-300 border border-amber-500/30';
      if (p.includes('HYSTERIA') || p.includes('TUIC')) return 'bg-rose-500/20 text-rose-300 border border-rose-500/30';
      return 'bg-slate-800 text-slate-300 border border-white/10';
    };

    // --- 批量导入订阅源弹窗状态 ---
    const showBatchModal = ref(false);
    const batchUrlsText = ref('');
    const batchPrefix = ref('');

    const openBatchSourceModal = () => {
      showBatchModal.value = true;
      nextTick(() => { lucide.createIcons(); });
    };

    const fillRecommendedSources = () => {
      batchUrlsText.value = RECOMMENDED_SOURCES.join('\n');
      showToast(`已填入 ${RECOMMENDED_SOURCES.length} 个优质订阅源`);
    };

    const getBatchUrlCount = () => {
      return batchUrlsText.value.split('\n').map(s => s.trim()).filter(s => s.startsWith('http://') || s.startsWith('https://')).length;
    };

    const confirmBatchAddSources = async () => {
      const urls = batchUrlsText.value.split('\n').map(s => s.trim()).filter(s => s.startsWith('http://') || s.startsWith('https://'));
      if (!urls.length) {
        showToast('请在文本框中输入至少一个合法的 HTTP/HTTPS 链接');
        return;
      }
      try {
        const r = await fetch('/api/sources/batch', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urls: urls, prefix: batchPrefix.value })
        });
        const res = await r.json();
        if (r.ok) {
          showToast(`导入成功！新增 ${res.added_count} 个订阅源 (跳过重复 ${res.skipped_count} 个)`);
          showBatchModal.value = false;
          batchUrlsText.value = '';
          fetchSources();
        } else {
          showToast('导入失败: ' + res.detail);
        }
      } catch (e) {
        showToast('批量导入异常: ' + e);
      }
    };

    // --- GitHub 同步弹窗状态 ---
    const showGitHubModal = ref(false);
    const testingGitHub = ref(false);
    const syncingGitHub = ref(false);
    const ghForm = ref({
      enabled: false,
      token: '',
      repo: '',
      branch: 'main',
      target_dir: 'output'
    });

    const openGitHubModal = async () => {
      showGitHubModal.value = true;
      nextTick(() => { lucide.createIcons(); });
      try {
        const r = await fetch('/api/github-sync');
        if (r.ok) {
          const d = await r.json();
          const cfg = d.config || {};
          ghForm.value = {
            enabled: cfg.enabled || false,
            token: cfg.token || '',
            repo: cfg.repo || '',
            branch: cfg.branch || 'main',
            target_dir: cfg.target_dir || 'output'
          };
        }
      } catch (e) {}
    };

    const getJsdelivrUrl = (filename) => {
      const repo = (ghForm.value.repo || '').trim().replace(/^\/|\/$/g, '');
      const branch = (ghForm.value.branch || 'main').trim();
      const dir = (ghForm.value.target_dir || 'output').trim().replace(/^\/|\/$/g, '');
      const path = dir ? `${dir}/${filename}` : filename;
      return `https://cdn.jsdelivr.net/gh/${repo}@${branch}/${path}`;
    };

    const testGitHubConnection = async () => {
      if (!ghForm.value.token || !ghForm.value.repo) {
        showToast('请先输入 GitHub Token 和仓库名称');
        return;
      }
      testingGitHub.value = true;
      try {
        const r = await fetch('/api/github-sync/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(ghForm.value)
        });
        const res = await r.json();
        if (res.status === 'ok') {
          showToast(res.message);
        } else {
          showToast('连接失败: ' + res.message);
        }
      } catch (e) {
        showToast('测试网络异常: ' + e);
      } finally {
        testingGitHub.value = false;
      }
    };

    const saveGitHubConfig = async () => {
      try {
        const r = await fetch('/api/github-sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(ghForm.value)
        });
        if (r.ok) {
          showToast('GitHub 同步配置已成功保存！');
          fetchConfig();
          showGitHubModal.value = false;
        } else {
          showToast('保存失败');
        }
      } catch (e) {
        showToast('保存异常: ' + e);
      }
    };

    const syncGitHubNow = async () => {
      syncingGitHub.value = true;
      try {
        const r = await fetch('/api/github-sync/now', { method: 'POST' });
        const res = await r.json();
        if (r.ok && res.status === 'ok') {
          showToast(res.message);
          fetchStatus();
        } else {
          showToast('同步失败: ' + (res.message || res.detail));
        }
      } catch (e) {
        showToast('同步异常: ' + e);
      } finally {
        syncingGitHub.value = false;
      }
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
      showToast('链接已复制到剪贴板！');
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
      if (line.includes('[错误]') || line.includes('❌') || line.includes('[✗]')) return 'text-red-400';
      if (line.includes('🎉') || line.includes('[+]') || line.includes('[✓]')) return 'text-emerald-400';
      if (line.includes('🚀') || line.includes('===') || line.includes('优选') || line.includes('[⚡]')) return 'text-cyan-300 font-bold';
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
        if (r.ok) {
          const list = await r.json();
          // 按成功次数降序排列，按失败次数升序排列
          sources.value = list.sort((a, b) => {
            const scA = a.success_count || 0;
            const scB = b.success_count || 0;
            if (scB !== scA) return scB - scA;
            const fcA = a.fail_count || 0;
            const fcB = b.fail_count || 0;
            return fcA - fcB;
          });
          nextTick(() => { lucide.createIcons(); });
        }
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

    // --- 批量选中与删除订阅源 ---
    const selectedSourceIds = ref([]);

    const isAllSourcesSelected = computed(() => {
      if (!sources.value || sources.value.length === 0) return false;
      return sources.value.length === selectedSourceIds.value.length;
    });

    const toggleSelectAllSources = () => {
      if (isAllSourcesSelected.value) {
        selectedSourceIds.value = [];
      } else {
        selectedSourceIds.value = sources.value.map(s => s.id);
      }
    };

    const batchDeleteSources = async () => {
      const count = selectedSourceIds.value.length;
      if (count === 0) {
        showToast('请先勾选需要删除的订阅源');
        return;
      }
      if (!confirm(`确定要批量删除选中的 ${count} 个订阅源吗？删除后不可撤销。`)) return;
      try {
        const r = await fetch('/api/sources/batch-delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: selectedSourceIds.value })
        });
        const res = await r.json();
        if (r.ok && res.status === 'ok') {
          showToast(`已成功批量删除 ${res.deleted_count} 个订阅源！`);
          selectedSourceIds.value = [];
          fetchSources();
        } else {
          showToast('批量删除失败: ' + (res.detail || '未知错误'));
        }
      } catch (e) {
        showToast('批量删除异常: ' + e);
      }
    };

    const deleteSource = async (id) => {
      if (!confirm('确认删除此订阅源吗？')) return;
      try {
        const r = await fetch(`/api/sources/${id}`, { method: 'DELETE' });
        if (r.ok) {
          showToast('已删除订阅源');
          selectedSourceIds.value = selectedSourceIds.value.filter(item => item !== id);
          fetchSources();
        }
      } catch (e) {}
    };

    const openAddSourceModal = () => {
      newSource.value = { name: '', url: '' };
      showAddModal.value = true;
      nextTick(() => { lucide.createIcons(); });
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

    const openEditSourceModal = (src) => {
      editSourceForm.value = {
        id: src.id,
        name: src.name || '',
        url: src.url || '',
        enabled: src.enabled !== false
      };
      showEditModal.value = true;
      nextTick(() => { lucide.createIcons(); });
    };

    const confirmEditSource = async () => {
      if (!editSourceForm.value.url) {
        showToast('订阅源链接不能为空');
        return;
      }
      try {
        const r = await fetch(`/api/sources/${editSourceForm.value.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: editSourceForm.value.name,
            url: editSourceForm.value.url,
            enabled: editSourceForm.value.enabled
          })
        });
        if (r.ok) {
          showToast('订阅源修改已保存！');
          showEditModal.value = false;
          fetchSources();
        } else {
          const res = await r.json();
          showToast('修改失败: ' + (res.detail || '未知错误'));
        }
      } catch (e) {
        showToast('保存修改异常: ' + e);
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
      logs, customIpsText, showAddModal, newSource, showEditModal, editSourceForm, toast, nameTags, previewNodeName,
      subUrl, copyText, stageName, getLogColor, clearLogs, insertTag,
      triggerRun, toggleSource, deleteSource, openAddSourceModal, confirmAddSource,
      openEditSourceModal, confirmEditSource,
      testSource, saveNamingRule, saveCleanIpConfig, saveGlobalSettings, testCleanIps,
      // Nodes modal
      showNodesModal, nodesModalFilter, nodesList, loadingNodes, nodesSearch, nodesProtoFilter,
      nodesPage, nodesPerPage, availableProtos, filteredNodes, totalNodesPages, paginatedNodes,
      openNodesModal, copyAllFilteredNodes, copyNodeUri, getProtoBadgeClass,
      // Batch modal
      showBatchModal, batchUrlsText, batchPrefix, openBatchSourceModal, fillRecommendedSources,
      getBatchUrlCount, confirmBatchAddSources,
      // Batch selection & delete
      selectedSourceIds, isAllSourcesSelected, toggleSelectAllSources, batchDeleteSources,
      // GitHub modal
      showGitHubModal, testingGitHub, syncingGitHub, ghForm, openGitHubModal,
      getJsdelivrUrl, testGitHubConnection, saveGitHubConfig, syncGitHubNow
    };
  }
}).mount('#app');
