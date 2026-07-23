<template>
  <div class="workspace">
    <!-- 顶部导航 -->
    <nav class="topbar">
      <button class="back-btn" @click="goHome">←</button>
      <span class="project-name">{{ projectName }}</span>
      <span class="mode-badge">{{ isOutline ? '素材大纲' : '小说推演' }}</span>
      <div class="topbar-right">
        <div class="step-indicator">
          <div :class="['step-dot', { active: step >= 1, done: step > 1 }]"><span>1</span></div>
          <div class="step-line" :class="{ done: step > 1 }"></div>
          <div :class="['step-dot', { active: step >= 2, done: step > 2 }]"><span>2</span></div>
          <div class="step-line" :class="{ done: step > 2 }"></div>
          <div :class="['step-dot', { active: step >= 3, done: step > 3 }]"><span>3</span></div>
        </div>
        <div class="status-text" ref="statusText">{{ statusMsg }}</div>
      </div>
    </nav>

    <div class="workspace-body">
      <!-- 左侧：图谱（无遮盖层，直接显示） -->
      <div class="graph-area">
        <GraphPanel :graphData="graphData" :loading="graphLoading" :currentPhase="step" :isSimulating="false" @refresh="refreshGraph" />
      </div>

      <!-- 右侧面板 -->
      <aside class="side-panel">
        <!-- 步骤1：上传 -->
        <section class="panel-section" v-if="step === 1">
          <h3 class="section-title">📤 上传素材</h3>
          <div class="upload-area" @click="triggerUpload">
            <input type="file" ref="fileInput" multiple accept=".pdf,.md,.txt" style="display:none" @change="handleFile" />
            <div class="upload-placeholder" v-if="!files.length">
              <div class="upload-icon-big">+</div>
              <p>点击上传 PDF / MD / TXT</p>
            </div>
            <div v-else class="file-list">
              <div v-for="(f, i) in files" :key="i" class="file-item">{{ f.name }}</div>
            </div>
          </div>
          <button class="primary-btn" @click="startProcessing" :disabled="!files.length || processing">
            {{ processing ? '处理中...' : '开始分析' }}
          </button>
          <div v-if="errorMsg && step === 1" class="error-box">{{ errorMsg }}</div>
        </section>

        <!-- 步骤2 + 3 的错误提示 -->
        <div v-if="errorMsg && step >= 2" class="error-box" style="margin:8px 12px">{{ errorMsg }}</div>

        <!-- 步骤2：处理中 -->
        <section class="panel-section" v-if="step === 2">
          <h3 class="section-title">⚙️ 处理进度</h3>
          <div class="progress-list">
            <div v-for="(item, i) in progressItems" :key="i" :class="['progress-item', item.status]">
              <span class="progress-icon" :class="{ spinning: item.status === 'doing' }">{{ item.status === 'done' ? '✓' : item.status === 'error' ? '✗' : '◌' }}</span>
              <span class="progress-label">{{ item.label }}</span>
              <span v-if="item.detail" class="progress-detail">{{ item.detail }}</span>
            </div>
          </div>
          <div class="stats-grid" v-if="liveStats.totalEntities > 0 || liveStats.chunksProcessed > 0">
            <div class="stat-box">
              <span class="stat-num">{{ liveStats.totalEntities }}</span>
              <span class="stat-lb">实体</span>
            </div>
            <div class="stat-box">
              <span class="stat-num">{{ liveStats.totalRelations }}</span>
              <span class="stat-lb">关系</span>
            </div>
            <div class="stat-box">
              <span class="stat-num">{{ liveStats.chunksProcessed }}</span>
              <span class="stat-lb">文本段</span>
            </div>
            <div class="stat-box">
              <span class="stat-num">{{ liveStats.nerSpeed }}</span>
              <span class="stat-lb">段/分</span>
            </div>
          </div>
          <div class="status-msg" v-if="taskMessage">{{ taskMessage }}</div>
          <div class="progress-bar-wrapper" v-if="taskProgress > 0">
            <div class="progress-bar-track">
              <div class="progress-bar-fill" :style="{ width: taskProgress + '%' }"></div>
            </div>
            <span class="progress-bar-text">{{ taskProgress }}%</span>
          </div>
          <div class="eta-line">已用时：{{ liveStats.elapsed }}</div>
        </section>

        <!-- 步骤3：完成 -->
        <section class="panel-section" v-if="step === 3">
          <h3 class="section-title">📊 图谱概览</h3>
          <div class="stats-grid">
            <div class="stat-box"><span class="stat-num">{{ graphStats?.nodes || 0 }}</span><span class="stat-lb">实体</span></div>
            <div class="stat-box"><span class="stat-num">{{ graphStats?.edges || 0 }}</span><span class="stat-lb">关系</span></div>
            <div class="stat-box"><span class="stat-num">{{ graphStats?.types || 0 }}</span><span class="stat-lb">类型</span></div>
          </div>
          <div class="tool-tabs">
            <button :class="['tab-btn', { active: activeTab === 'chat' }]" @click="activeTab='chat'" :disabled="!graphReady">
              <span class="tab-icon">💬</span> 对话
            </button>
            <button :class="['tab-btn', { active: activeTab === 'qa' }]" @click="activeTab='qa'" :disabled="!graphReady">
              <span class="tab-icon">🤖</span> 问答
            </button>
            <button :class="['tab-btn', { active: activeTab === 'check' }]" @click="activeTab='check'" :disabled="!graphReady">
              <span class="tab-icon">🔍</span> 检测
            </button>
          </div>

          <!-- 对话：选角 + 记忆增强 -->
          <div v-if="activeTab === 'chat' && graphReady" class="panel-section">
            <h3 class="section-title">💬 角色对话</h3>
            <div class="char-select-row">
              <select v-model="selectedCharacterName" class="char-select" @change="onCharacterSelect">
                <option value="">-- 选择角色 --</option>
                <option v-for="c in characterList" :key="c.uuid" :value="c.name">{{ c.name }}（{{ c.type }}）</option>
              </select>
            </div>
            <div class="chat-box">
              <div class="chat-msgs" ref="chatBox">
                <div v-for="(msg, i) in chatMessages" :key="i" :class="['msg', msg.role]">
                  <span class="msg-name">{{ msg.name }}</span>
                  <span class="msg-text">{{ msg.text }}</span>
                  <div v-if="msg.references && msg.references.length" class="msg-refs">
                    <span class="ref-title">引用原文：</span>
                    <div v-for="(ref, j) in msg.references" :key="j" class="ref-item">{{ ref }}</div>
                  </div>
                </div>
              </div>
              <div class="chat-input-row">
                <input v-model="chatInput" class="chat-input" placeholder="输入你想对角色说的话..." @keyup.enter="sendChat" />
                <button class="send-btn" @click="sendChat">→</button>
              </div>
            </div>
          </div>

          <!-- 智能问答 -->
          <div v-if="activeTab === 'qa' && graphReady" class="panel-section">
            <h3 class="section-title">🤖 智能问答</h3>
            <div class="chat-box">
              <div class="chat-msgs" ref="qaBox">
                <div v-for="(msg, i) in qaMessages" :key="i" :class="['msg', msg.role]">
                  <span class="msg-name">{{ msg.name }}</span>
                  <span class="msg-text">{{ msg.text }}</span>
                  <div v-if="msg.references && msg.references.length" class="msg-refs">
                    <span class="ref-title">检索依据：</span>
                    <div v-for="(ref, j) in msg.references" :key="j" class="ref-item">{{ ref }}</div>
                  </div>
                </div>
              </div>
              <div class="chat-input-row">
                <input v-model="qaInput" class="chat-input" placeholder="用自然语言提问..." @keyup.enter="sendQA" />
                <button class="send-btn" @click="sendQA">-></button>
              </div>
            </div>
          </div>

          <!-- 创作检测 -->
          <div v-if="activeTab === 'check' && graphReady" class="panel-section">
            <h3 class="section-title">🔍 创作检测</h3>
            <div class="check-btns">
              <button class="primary-btn small" @click="runPlotCheck" :disabled="checking">逻辑漏洞</button>
              <button class="primary-btn small" @click="runForeshadow" :disabled="checking">伏笔追踪</button>
              <button class="primary-btn small" @click="runConsistency" :disabled="checking">角色一致性</button>
            </div>
            <div v-if="checking" class="checking-hint">检测中...</div>
            <div v-if="checkResults.length" class="result-list">
              <div v-for="(r, i) in checkResults" :key="i" :class="['result-item', r.severity || 'info']">
                <span class="result-badge">{{ r.type }}</span>
                <span class="result-desc">{{ r.description }}</span>
                <div v-if="r.detail" class="result-detail">{{ r.detail }}</div>
              </div>
            </div>
            <div v-if="checkResults.length === 0 && !checking && hasChecked" class="empty-result">未发现问题</div>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import GraphPanel from '../components/GraphPanel.vue'
import service from '../api/index.js'

const router = useRouter()
const route = useRoute()
const props = defineProps({ projectId: String })
const isOutline = ref(true)
const projectName = ref('新项目')
const step = ref(1)
const files = ref([])
const fileInput = ref(null)
const graphData = ref(null)
const graphId = ref('')
const graphLoading = ref(false)
const processing = ref(false)
const processingMsg = ref('')
const processingDetail = ref('')
const errorMsg = ref('')
const graphStats = ref(null)
const graphReady = ref(false)
const activeTab = ref('chat')
const chatInput = ref('')
const chatMessages = ref([])
const chatBox = ref(null)
const selectedCharacterName = ref('')
const characterList = ref([])
const qaInput = ref('')
const qaMessages = ref([])
const qaBox = ref(null)
const checking = ref(false)
const checkResults = ref([])
const hasChecked = ref(false)
const taskMessage = ref('')
const taskProgress = ref(0)
const logLines = ref([])
const liveStats = ref({ totalEntities: 0, totalRelations: 0, chunksProcessed: 0, elapsed: '0s', nerSpeed: 0, eta: '计算中...' })
let startTime = 0
const statusMsg = ref('就绪')
const progressItems = ref([])

const goHome = () => router.push('/')
const triggerUpload = () => fileInput.value?.click()

const handleFile = (e) => {
  files.value = Array.from(e.target.files)
}

const addLog = (msg, type = 'info') => {
  const now = new Date()
  const time = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`
  logLines.value.push({ time, msg, type })
  if (logLines.value.length > 50) logLines.value.shift()
}

const fmtElapsed = () => {
  if (!startTime) return '0s'
  const sec = Math.floor((Date.now() - startTime) / 1000)
  if (sec < 60) return `${sec}s`
  return `${Math.floor(sec/60)}m${sec%60}s`
}

const startProcessing = async () => {
  if (!files.value.length) return
  processing.value = true
  errorMsg.value = ''
  step.value = 2
  statusMsg.value = '处理中'
  startTime = Date.now()
  logLines.value = []
  taskProgress.value = 0
  taskMessage.value = '正在初始化...'
  progressItems.value = [
    { label: '文件解析', status: 'doing', detail: '' },
    { label: '本体生成', status: 'pending', detail: '' },
    { label: '实体提取', status: 'pending', detail: '' },
    { label: '图谱构建', status: 'pending', detail: '' },
    { label: '向量嵌入', status: 'pending', detail: '' },
  ]

  // 步骤1: 文件解析
  processingMsg.value = '正在解析文件...'
  addLog('开始处理文件', 'info')
  await new Promise(r => setTimeout(r, 500))
  progressItems.value[0].status = 'done'
  progressItems.value[0].detail = `${files.value.length} 个文件`
  addLog('文件解析完成', 'done')
  progressItems.value[1].status = 'doing'
  processingMsg.value = '正在调用 AI 生成本体...'
  taskMessage.value = '调用 AI 生成本体定义中...'
  taskProgress.value = 5
  addLog('调用 DeepSeek 生成本体定义...', 'info')

  // 本体生成是同步阻塞调用，期间用动画提示用户系统在工作
  let dots = 0
  const ontologyAnimTimer = setInterval(() => {
    dots = (dots + 1) % 4
    const dotStr = '.'.repeat(dots)
    processingMsg.value = `正在调用 AI 生成本体${dotStr}`
    taskMessage.value = `AI 正在分析文本并生成本体定义${dotStr}`
    progressItems.value[1].detail = `AI 分析中${dotStr}`
    statusMsg.value = `生成本体${dotStr}`
  }, 800)

  try {
    const form = new FormData()
    files.value.forEach(f => form.append('files', f))
    form.append('simulation_requirement', '分析小说素材')
    form.append('project_name', projectName.value)

    const ontRes = await service({
      url: '/api/graph/ontology/generate', method: 'post',
      data: form, headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 180000
    })
    clearInterval(ontologyAnimTimer)
    if (!ontRes.success) throw new Error(ontRes.error || '本体生成失败')
    progressItems.value[1].status = 'done'
    progressItems.value[1].detail = `${ontRes.data?.ontology?.entity_types?.length || 0} 类型`
    addLog(`本体生成完成: ${ontRes.data?.ontology?.entity_types?.length || 0} 个实体类型`, 'done')

    const pid = ontRes.data?.project_id
    if (!pid) throw new Error('未获取到项目ID')

    // 步骤2: 构建图谱
    progressItems.value[2].status = 'doing'
    processingMsg.value = '正在提取实体和关系...'
    progressItems.value[2].detail = '调用AI中'

    const buildRes = await service({
      url: '/api/graph/build', method: 'post',
      data: {
        project_id: pid,
        graph_name: projectName.value + '知识图谱'
      },
      timeout: 300000
    })
    if (!buildRes.success) throw new Error(buildRes.error || '图谱构建失败')
    progressItems.value[2].status = 'done'

    // 轮询任务
    const taskId = buildRes.data?.task_id
    if (taskId) {
      progressItems.value[3].status = 'doing'
      progressItems.value[3].detail = '等待中'
      processingMsg.value = '正在构建知识图谱...'

      let pollCount = 0
      while (true) {
        await new Promise(r => setTimeout(r, 3000))
        let taskRes
        try {
          taskRes = await service({ url: `/api/graph/task/${taskId}`, method: 'get' })
        } catch (e) {
          pollCount++
          if (pollCount > 10) throw new Error('持续无法连接服务器')
          continue
        }
        if (taskRes.success) {
          const td = taskRes.data
          if (td.progress) taskProgress.value = Math.max(taskProgress.value, td.progress)
          if (td.message) { processingMsg.value = td.message; statusMsg.value = td.message }
          if (td.progress_detail) {
            const pd = td.progress_detail
            if (pd.entities) liveStats.value.totalEntities = pd.entities
            if (pd.relations) liveStats.value.totalRelations = pd.relations
            if (pd.chunks_processed) {
              liveStats.value.chunksProcessed = pd.chunks_processed
              const elapsedMin = (Date.now() - startTime) / 60000
              if (elapsedMin > 0) liveStats.value.nerSpeed = (pd.chunks_processed / elapsedMin).toFixed(1)
            }
            if (pd.total_chunks) {
              const remaining = pd.total_chunks - (pd.chunks_processed || 0)
              const speed = parseFloat(liveStats.value.nerSpeed) || 0
              if (speed > 0) liveStats.value.eta = remaining / speed < 1 ? `${Math.ceil(remaining / speed * 60)}s` : `${Math.ceil(remaining / speed)}min`
            }
            // 实时加载图谱：检测到 graph_id 后立即开始拉取图谱数据
            // 构建过程中持续轮询，节点写入 Neo4j 后就能在图谱上看到
            if (pd.graph_id && !graphId.value) {
              graphId.value = pd.graph_id
              loadGraphData()
            }
          }
          if (td.status === 'completed' || td.status === 'success' || td.status === 'completed_with_warning') {
            progressItems.value.forEach(p => { if (p.status === 'doing' || p.status === 'pending') p.status = 'done' })
            taskProgress.value = 100
            stopGraphRefresh()
            refreshGraph()
            // 如果是警告状态，显示警告信息
            if (td.status === 'completed_with_warning') {
              errorMsg.value = td.message || '图谱构建完成但未提取到实体，请检查 API 配置'
            }
            break
          } else if (td.status === 'failed') {
            throw new Error(td.error || '任务失败')
          }
          liveStats.value.elapsed = fmtElapsed()
        }
      }

      // 加载图谱数据
      const pRes = await service({ url: `/api/graph/project/${pid}`, method: 'get' })
      if (pRes.success && pRes.data?.graph_id) {
        graphId.value = pRes.data.graph_id
        const gRes = await service({ url: `/api/graph/data/${graphId.value}`, method: 'get' })
        if (gRes.success) {
          graphData.value = gRes.data
          const nc = gRes.data.nodes?.length || 0
          const ec = gRes.data.edges?.length || 0
          graphStats.value = { nodes: nc, edges: ec, types: Object.keys(gRes.data.entity_types || {}).length, vectors: nc, speed: '42ms' }
          graphReady.value = true
        }
      }
    }

    step.value = 3
    statusMsg.value = '完成'
    processing.value = false
    processingMsg.value = ''
    loadCharacters()

  } catch (e) {
    clearInterval(ontologyAnimTimer)
    errorMsg.value = e.message || '处理失败，请检查API密钥和网络连接'
    progressItems.value.forEach(p => { if (p.status === 'doing') p.status = 'error' })
    processing.value = false
    statusMsg.value = '失败'
  }
}

const onCharacterSelect = () => {
  chatMessages.value = []
}

const loadCharacters = async () => {
  if (!graphId.value) return
  try {
    const res = await service({ url: `/api/graph/characters/${graphId.value}`, method: 'get' })
    if (res.success) characterList.value = res.data.characters || []
  } catch (e) { console.warn('Load characters failed', e) }
}

const sendChat = async () => {
  if (!chatInput.value.trim() || !graphReady.value || !selectedCharacterName.value) return
  const msg = chatInput.value
  chatMessages.value.push({ role: 'user', name: '我', text: msg })
  chatInput.value = ''
  try {
    const res = await service({
      url: '/api/graph/character/chat', method: 'post',
      data: { character_name: selectedCharacterName.value, message: msg, graph_id: graphData.value?.graph_id || '' }
    })
    if (res.success) {
      chatMessages.value.push({
        role: 'char', name: res.data.character_name, text: res.data.response,
        references: res.data.references || []
      })
    }
  } catch (e) { errorMsg.value = '对话请求失败' }
  nextTick(() => chatBox.value?.scrollTo(0, chatBox.value.scrollHeight))
}

const sendQA = async () => {
  if (!qaInput.value.trim() || !graphReady.value) return
  const msg = qaInput.value
  qaMessages.value.push({ role: 'user', name: '我', text: msg })
  qaInput.value = ''
  try {
    const res = await service({
      url: '/api/graph/qa', method: 'post',
      data: { question: msg, graph_id: graphData.value?.graph_id || '' }
    })
    if (res.success) {
      qaMessages.value.push({
        role: 'bot', name: '助手', text: res.data.answer,
        references: res.data.references || []
      })
    }
  } catch (e) { errorMsg.value = '问答请求失败' }
  nextTick(() => qaBox.value?.scrollTo(0, qaBox.value.scrollHeight))
}

const runPlotCheck = async () => {
  if (!graphReady.value) return
  checking.value = true
  checkResults.value = []
  try {
    const res = await service({
      url: '/api/graph/plot/check', method: 'post',
      data: { graph_id: graphData.value?.graph_id || '' }
    })
    if (res.success) {
      const holes = res.data.holes || []
      const unresolved = res.data.unresolved || []
      checkResults.value = [...holes, ...unresolved]
    }
  } catch (e) { errorMsg.value = '逻辑检测失败' }
  checking.value = false
  hasChecked.value = true
}

const runForeshadow = async () => {
  if (!graphReady.value) return
  checking.value = true
  checkResults.value = []
  try {
    const res = await service({
      url: '/api/graph/foreshadow/track', method: 'post',
      data: { graph_id: graphData.value?.graph_id || '' }
    })
    if (res.success) {
      checkResults.value = (res.data.foreshadows || []).map(f => ({
        type: '伏笔', severity: 'info',
        description: f.description, detail: (f.related_facts || []).join('; ')
      }))
    }
  } catch (e) { errorMsg.value = '伏笔追踪失败' }
  checking.value = false
  hasChecked.value = true
}

const runConsistency = async () => {
  if (!graphReady.value) return
  checking.value = true
  checkResults.value = []
  try {
    const res = await service({
      url: '/api/graph/character/consistency', method: 'post',
      data: { graph_id: graphData.value?.graph_id || '' }
    })
    if (res.success) {
      const results = res.data.results || []
      const items = []
      for (const r of results) {
        for (const c of (r.contradictions || [])) {
          items.push({
            type: '一致性', severity: 'warning',
            description: `角色「${r.character}」：${c.desc || ''}`,
            detail: (c.facts || []).join('; ')
          })
        }
      }
      checkResults.value = items
    }
  } catch (e) { errorMsg.value = '一致性检测失败' }
  checking.value = false
  hasChecked.value = true
}

const refreshGraph = async () => {
  if (!graphId.value) return
  try {
    const res = await service({ url: `/api/graph/data/${graphId.value}`, method: 'get' })
    if (res.success) graphData.value = res.data
  } catch (e) { console.warn('Refresh failed', e) }
}

// 实时加载图谱数据（处理过程中周期性刷新）
let graphRefreshTimer = null
const loadGraphData = () => {
  // 立即加载一次
  refreshGraph()
  // 然后每 5 秒刷新一次，直到处理完成
  if (!graphRefreshTimer) {
    graphRefreshTimer = setInterval(() => {
      refreshGraph()
    }, 2000)
  }
}

const stopGraphRefresh = () => {
  if (graphRefreshTimer) {
    clearInterval(graphRefreshTimer)
    graphRefreshTimer = null
  }
}

onMounted(() => {
  isOutline.value = route.query.type !== 'prediction'
})

onUnmounted(() => {
  stopGraphRefresh()
})
</script>

<style scoped>
.workspace {
  height: 100vh; display: flex; flex-direction: column;
  background: #F1DDDF; color: #122E8A;
}
.topbar {
  height: 48px; display: flex; align-items: center; gap: 12px; padding: 0 16px;
  background: rgba(255,255,255,0.7); border-bottom: 1px solid rgba(18,46,138,0.08);
  flex-shrink: 0;
}
.back-btn { background: none; border: none; font-size: 18px; cursor: pointer; color: #122E8A; padding: 4px 8px; border-radius: 6px; }
.back-btn:hover { background: rgba(18,46,138,0.08); }
.project-name { font-weight: 600; font-size: 14px; flex: 1; }
.mode-badge { font-size: 11px; padding: 3px 10px; border-radius: 10px; background: #122E8A; color: #F1DDDF; }
.topbar-right { display: flex; align-items: center; gap: 12px; }
.step-indicator { display: flex; align-items: center; gap: 4px; }
.step-dot {
  width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600; border: 2px solid rgba(18,46,138,0.2); color: rgba(18,46,138,0.3);
  transition: all 0.3s;
}
.step-dot.active { border-color: #122E8A; background: #122E8A; color: #F1DDDF; }
.step-dot.done { border-color: #122E8A; background: #122E8A; color: #F1DDDF; }
.step-line { width: 20px; height: 2px; background: rgba(18,46,138,0.15); transition: all 0.3s; }
.step-line.done { background: #122E8A; }
.status-text { font-size: 11px; color: #4A5A8A; }
.workspace-body { flex: 1; display: flex; overflow: hidden; }
.graph-area { flex: 1; position: relative; overflow: hidden; }
/* processing-overlay 已移除 */
.side-panel {
  width: 280px; background: rgba(255,255,255,0.5); border-left: 1px solid rgba(18,46,138,0.06);
  overflow-y: auto; padding: 12px; flex-shrink: 0; backdrop-filter: blur(8px);
}
.panel-section { margin-bottom: 14px; }
.section-title { font-size: 12px; font-weight: 600; color: #122E8A; margin-bottom: 8px; letter-spacing: 0.3px; }
.upload-area {
  padding: 20px; border: 1px dashed rgba(18,46,138,0.15); border-radius: 10px;
  cursor: pointer; text-align: center; transition: all 0.2s; background: rgba(255,255,255,0.4);
}
.upload-area:hover { border-color: #122E8A; background: rgba(255,255,255,0.6); }
.upload-icon-big { font-size: 28px; color: #122E8A; opacity: 0.4; margin-bottom: 8px; }
.upload-placeholder p { font-size: 12px; color: #4A5A8A; margin: 0; }
.file-list { text-align: left; }
.file-item { font-size: 11px; padding: 4px 0; color: #122E8A; }
.primary-btn {
  width: 100%; padding: 10px; margin-top: 8px; border: none; border-radius: 8px;
  background: #122E8A; color: #F1DDDF; font-size: 13px; font-weight: 600; cursor: pointer;
  transition: all 0.2s;
}
.primary-btn:hover { background: #1E4AB0; transform: translateY(-1px); }
.primary-btn:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }
.primary-btn.small { padding: 6px; font-size: 11px; }
.error-box { margin-top: 8px; padding: 8px; background: rgba(230,57,70,0.08); border-radius: 6px; font-size: 11px; color: #E63946; }
.progress-list { display: flex; flex-direction: column; gap: 6px; }
.progress-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; font-size: 11px; background: rgba(255,255,255,0.4); }
.progress-item.done { color: #2A9D8F; }
.progress-item.error { color: #E63946; }
.progress-item.doing { color: #122E8A; background: rgba(18,46,138,0.04); }
.progress-icon { font-size: 12px; width: 16px; text-align: center; }
.progress-icon.spinning { animation: spin 1.2s linear infinite; display: inline-block; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.progress-label { flex: 1; }
.progress-detail { font-size: 10px; opacity: 0.6; }
.stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.stat-box { text-align: center; padding: 10px; background: rgba(255,255,255,0.5); border-radius: 8px; }
.stat-num { display: block; font-size: 18px; font-weight: 700; color: #122E8A; }
.stat-lb { font-size: 10px; color: #4A5A8A; }
.tool-tabs { display: flex; gap: 4px; margin-top: 8px; }
.tab-btn {
  flex: 1; padding: 7px 4px; border: 1px solid rgba(18,46,138,0.1); border-radius: 8px;
  background: rgba(255,255,255,0.4); cursor: pointer; font-size: 11px; color: #4A5A8A;
  transition: all 0.2s; display: flex; flex-direction: column; align-items: center; gap: 2px;
}
.tab-btn.active { background: #122E8A; color: #F1DDDF; border-color: #122E8A; }
.tab-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.tab-icon { font-size: 14px; }
.chat-box { display: flex; flex-direction: column; gap: 6px; }
.chat-msgs { max-height: 200px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; }
.msg { padding: 6px 10px; border-radius: 8px; font-size: 12px; line-height: 1.4; max-width: 85%; }
.msg.user { background: #122E8A; color: #F1DDDF; align-self: flex-end; }
.msg.char { background: rgba(255,255,255,0.6); color: #122E8A; align-self: flex-start; }
.msg-name { display: block; font-weight: 600; font-size: 10px; margin-bottom: 1px; opacity: 0.7; }
.chat-input-row { display: flex; gap: 4px; margin-top: 4px; }
.chat-input { flex: 1; padding: 6px 10px; border: 1px solid rgba(18,46,138,0.1); border-radius: 6px; font-size: 12px; outline: none; background: rgba(255,255,255,0.5); color: #122E8A; }
.send-btn { padding: 6px 12px; border: none; border-radius: 6px; background: #122E8A; color: #F1DDDF; cursor: pointer; font-size: 14px; }
.mini-input { width: 100%; padding: 6px 10px; border: 1px solid rgba(18,46,138,0.1); border-radius: 6px; font-size: 12px; outline: none; background: rgba(255,255,255,0.5); color: #122E8A; margin-bottom: 4px; }
.comments-wall { display: flex; flex-direction: column; gap: 6px; max-height: 300px; overflow-y: auto; margin-top: 6px; }
.comment-card { padding: 8px 10px; background: rgba(255,255,255,0.5); border-radius: 8px; border-left: 3px solid #122E8A; }
.comment-tag { font-size: 10px; font-weight: 600; color: #122E8A; display: block; margin-bottom: 3px; }
.comment-text { font-size: 11px; line-height: 1.4; color: #4A5A8A; }
.result-list { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.result-item { padding: 6px 10px; border-radius: 6px; font-size: 11px; border-left: 3px solid; }
.result-item.warning { background: rgba(244,162,97,0.08); border-color: #F4A261; }
.result-item.info { background: rgba(69,123,157,0.08); border-color: #457B9D; }
.result-badge { font-weight: 600; font-size: 10px; display: block; margin-bottom: 2px; }
.result-desc { color: #4A5A8A; line-height: 1.4; }
.result-detail { font-size: 10px; color: #6A7AAA; margin-top: 2px; opacity: 0.7; }
.char-select-row { margin-bottom: 6px; }
.char-select { width: 100%; padding: 6px 10px; border: 1px solid rgba(18,46,138,0.1); border-radius: 6px; font-size: 12px; outline: none; background: rgba(255,255,255,0.6); color: #122E8A; cursor: pointer; }
.msg-refs { margin-top: 4px; padding: 4px 6px; background: rgba(18,46,138,0.04); border-radius: 4px; font-size: 10px; }
.ref-title { font-weight: 600; color: #122E8A; display: block; margin-bottom: 2px; }
.ref-item { color: #4A5A8A; line-height: 1.3; margin-bottom: 1px; }
.msg.bot { background: rgba(255,255,255,0.6); color: #122E8A; align-self: flex-start; }
.check-btns { display: flex; gap: 4px; margin-bottom: 6px; }
.check-btns .primary-btn { flex: 1; }
.checking-hint { font-size: 11px; color: #4A5A8A; text-align: center; padding: 8px; }
.empty-result { font-size: 11px; color: #2A9D8F; text-align: center; padding: 8px; }
.eta-line { font-size: 10px; color: #4A5A8A; margin-top: 4px; }
.status-msg { font-size: 11px; color: #122E8A; margin-top: 8px; padding: 6px 8px; background: rgba(255,255,255,0.4); border-radius: 6px; }
.progress-bar-wrapper { display: flex; align-items: center; gap: 6px; margin-top: 6px; }
.progress-bar-track { flex: 1; height: 6px; background: rgba(18,46,138,0.1); border-radius: 3px; overflow: hidden; }
.progress-bar-fill { height: 100%; background: #122E8A; border-radius: 3px; transition: width 0.5s ease; }
.progress-bar-text { font-size: 10px; color: #4A5A8A; min-width: 30px; text-align: right; }
</style>
