<template>
  <div class="graph-panel">
    <div class="panel-header">
      <span class="panel-title">图谱关系可视化</span>
      <!-- 顶部工具栏 (Internal Top Right) -->
      <div class="header-tools">
        <button class="tool-btn" @click="$emit('refresh')" :disabled="loading" :title="$t('graph.refreshGraph')">
          <span class="icon-refresh" :class="{ 'spinning': loading }">↻</span>
          <span class="btn-text">刷新</span>
        </button>
        <button class="tool-btn" @click="$emit('toggle-maximize')" :title="$t('graph.toggleMaximize')">
          <span class="icon-maximize">⛶</span>
        </button>
      </div>
    </div>
    
    <div class="graph-container" ref="graphContainer">
      <!-- 顶部状态栏 -->
      <div v-if="graphData" class="graph-stats-bar">
        <span class="stat-item">
          <span class="stat-icon">◉</span>
          <span class="stat-value">{{ graphData.nodes?.length || graphData.node_count || 0 }}</span>
          <span class="stat-label">节点</span>
        </span>
        <span class="stat-divider"></span>
        <span class="stat-item">
          <span class="stat-icon">─</span>
          <span class="stat-value">{{ graphData.edges?.length || graphData.edge_count || 0 }}</span>
          <span class="stat-label">关系</span>
        </span>
        <span class="stat-divider"></span>
        <span class="stat-item">
          <span class="stat-icon">◆</span>
          <span class="stat-value">{{ entityTypes.length }}</span>
          <span class="stat-label">类型</span>
        </span>
        <span class="stat-divider"></span>
        <span class="stat-item">
          <span class="stat-icon">⚡</span>
          <span class="stat-value" id="aiSpeedStat">{{ aiSpeed }}</span>
          <span class="stat-label">推理速度</span>
        </span>
        <span class="stat-divider"></span>
        <span class="stat-item">
          <span class="stat-icon">∑</span>
          <span class="stat-value" id="charCountStat">{{ totalChars }}</span>
          <span class="stat-label">信息流量</span>
        </span>
      </div>
      <!-- 图谱可视化 -->
      <div v-if="graphData" class="graph-view">
        <svg ref="graphSvg" class="graph-svg"></svg>
        
        <!-- 节点为空时的提示（不遮挡，仅底部小提示） -->
        <div v-if="!graphData.nodes || graphData.nodes.length === 0" class="graph-empty-hint">
          {{ currentPhase === 2 ? '正在提取实体，请稍候...' : '未提取到实体' }}
        </div>
        
        <!-- 构建中提示（不遮挡，仅角落提示） -->
        <div v-if="currentPhase === 2" class="graph-building-corner-hint">
          <span class="corner-dot"></span> 实时构建中
        </div>
        <div v-if="showSimulationFinishedHint" class="graph-building-hint finished-hint">
          <div class="hint-icon-wrapper">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="hint-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="16" x2="12" y2="12"></line>
              <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>
          </div>
          <span class="hint-text">{{ $t('graph.pendingContentHint') }}</span>
          <button class="hint-close-btn" @click="dismissFinishedHint" :title="$t('graph.closeHint')">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <!-- 节点/边详情面板 -->
        <div v-if="selectedItem" class="detail-panel">
          <div class="detail-panel-header">
            <span class="detail-title">{{ selectedItem.type === 'node' ? '节点详情' : '关系详情' }}</span>
            <span v-if="selectedItem.type === 'node'" class="detail-type-badge" :style="{ background: selectedItem.color, color: '#fff' }">
              {{ translateType(selectedItem.entityType) }}
            </span>
            <button class="detail-close" @click="closeDetailPanel">×</button>
          </div>
          
          <!-- 节点详情 -->
          <div v-if="selectedItem.type === 'node'" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">名称：</span>
              <span class="detail-value">{{ selectedItem.data.name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">标识：</span>
              <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
            </div>
            <div class="detail-row" v-if="selectedItem.data.created_at">
              <span class="detail-label">创建时间：</span>
              <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
            </div>
            
            <!-- Properties -->
            <div class="detail-section" v-if="selectedItem.data.attributes && Object.keys(selectedItem.data.attributes).length > 0">
              <div class="section-title">属性：</div>
              <div class="properties-list">
                <div v-for="(value, key) in selectedItem.data.attributes" :key="key" class="property-item">
                  <span class="property-key">{{ key }}：</span>
                  <span class="property-value">{{ value || '无' }}</span>
                </div>
              </div>
            </div>
            
            <!-- Summary -->
            <div class="detail-section" v-if="selectedItem.data.summary">
              <div class="section-title">摘要：</div>
              <div class="summary-text">{{ selectedItem.data.summary }}</div>
            </div>
            
            <!-- Labels -->
            <div class="detail-section" v-if="selectedItem.data.labels && selectedItem.data.labels.length > 0">
              <div class="section-title">标签：</div>
              <div class="labels-list">
                <span v-for="label in selectedItem.data.labels" :key="label" class="label-tag">
                  {{ label }}
                </span>
              </div>
            </div>
          </div>
          
          <!-- 边详情 -->
          <div v-else class="detail-content">
            <!-- 自环组详情 -->
            <template v-if="selectedItem.data.isSelfLoopGroup">
              <div class="edge-relation-header self-loop-header">
                {{ selectedItem.data.source_name }} - 自关联
                <span class="self-loop-count">{{ selectedItem.data.selfLoopCount }} 项</span>
              </div>
              
              <div class="self-loop-list">
                <div 
                  v-for="(loop, idx) in selectedItem.data.selfLoopEdges" 
                  :key="loop.uuid || idx" 
                  class="self-loop-item"
                  :class="{ expanded: expandedSelfLoops.has(loop.uuid || idx) }"
                >
                  <div 
                    class="self-loop-item-header"
                    @click="toggleSelfLoop(loop.uuid || idx)"
                  >
                    <span class="self-loop-index">#{{ idx + 1 }}</span>
                    <span class="self-loop-name">{{ loop.name || loop.fact_type || '关联' }}</span>
                    <span class="self-loop-toggle">{{ expandedSelfLoops.has(loop.uuid || idx) ? '−' : '+' }}</span>
                  </div>
                  
                  <div class="self-loop-item-content" v-show="expandedSelfLoops.has(loop.uuid || idx)">
                    <div class="detail-row" v-if="loop.uuid">
                      <span class="detail-label">标识：</span>
                      <span class="detail-value uuid-text">{{ loop.uuid }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact">
                      <span class="detail-label">事实：</span>
                      <span class="detail-value fact-text">{{ loop.fact }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.fact_type">
                      <span class="detail-label">类型：</span>
                      <span class="detail-value">{{ loop.fact_type }}</span>
                    </div>
                    <div class="detail-row" v-if="loop.created_at">
                      <span class="detail-label">创建时间：</span>
                      <span class="detail-value">{{ formatDateTime(loop.created_at) }}</span>
                    </div>
                    <div v-if="loop.episodes && loop.episodes.length > 0" class="self-loop-episodes">
                      <span class="detail-label">情节：</span>
                      <div class="episodes-list compact">
                        <span v-for="ep in loop.episodes" :key="ep" class="episode-tag small">{{ ep }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            
            <!-- 普通边详情 -->
            <template v-else>
              <div class="edge-relation-header">
                {{ selectedItem.data.source_name }} → {{ selectedItem.data.name || '关联' }} → {{ selectedItem.data.target_name }}
              </div>
              
              <div class="detail-row">
                <span class="detail-label">标识：</span>
                <span class="detail-value uuid-text">{{ selectedItem.data.uuid }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">标签：</span>
                <span class="detail-value">{{ selectedItem.data.name || '关联' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">类型：</span>
                <span class="detail-value">{{ selectedItem.data.fact_type || '未知' }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.fact">
                <span class="detail-label">事实：</span>
                <span class="detail-value fact-text">{{ selectedItem.data.fact }}</span>
              </div>
              
              <!-- Episodes -->
              <div class="detail-section" v-if="selectedItem.data.episodes && selectedItem.data.episodes.length > 0">
                <div class="section-title">情节：</div>
                <div class="episodes-list">
                  <span v-for="ep in selectedItem.data.episodes" :key="ep" class="episode-tag">
                    {{ ep }}
                  </span>
                </div>
              </div>
              
              <div class="detail-row" v-if="selectedItem.data.created_at">
                <span class="detail-label">创建时间：</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.created_at) }}</span>
              </div>
              <div class="detail-row" v-if="selectedItem.data.valid_at">
                <span class="detail-label">生效时间：</span>
                <span class="detail-value">{{ formatDateTime(selectedItem.data.valid_at) }}</span>
              </div>
            </template>
          </div>
        </div>
      </div>
      
      <!-- 加载状态 -->
      <div v-else-if="loading" class="graph-state">
        <div class="loading-spinner"></div>
        <p>{{ $t('graph.graphDataLoading') }}</p>
      </div>
      
      <!-- 等待/空状态 -->
      <div v-else-if="currentPhase === 2" class="graph-state">
        <div class="building-spinner"></div>
        <p class="empty-text">正在构建知识图谱...</p>
        <p class="empty-sub">实体提取后将在此实时显示</p>
      </div>
      <div v-else class="graph-state">
        <div class="empty-icon">❖</div>
        <p class="empty-text">{{ $t('graph.waitingOntology') }}</p>
      </div>
    </div>

    <!-- 底部图例 (Bottom Left) -->
    <div v-if="graphData && entityTypes.length" class="graph-legend">
      <span class="legend-title">实体类型</span>
      <div class="legend-items">
        <div class="legend-item" v-for="type in entityTypes" :key="type.name">
          <span class="legend-dot" :style="{ background: type.color }"></span>
          <span class="legend-label">{{ type.name }}</span>
        </div>
      </div>
    </div>
    
    <!-- 显示边标签开关 -->
    <div v-if="graphData" class="edge-labels-toggle">
      <label class="toggle-switch">
        <input type="checkbox" v-model="showEdgeLabels" />
        <span class="slider"></span>
      </label>
      <span class="toggle-label">显示边标签</span>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from 'vue'
import * as d3 from 'd3'

const props = defineProps({
  graphData: Object,
  loading: Boolean,
  currentPhase: Number,
  isSimulating: Boolean
})

const emit = defineEmits(['refresh', 'toggle-maximize'])

const graphContainer = ref(null)
const graphSvg = ref(null)
const selectedItem = ref(null)
const showEdgeLabels = ref(true)
const expandedSelfLoops = ref(new Set())
const showSimulationFinishedHint = ref(false)
const wasSimulating = ref(false)
const aiSpeed = ref('—')

// 关闭模拟结束提示
const dismissFinishedHint = () => {
  showSimulationFinishedHint.value = false
}

// 监听 isSimulating 变化，检测模拟结束
watch(() => props.isSimulating, (newValue, oldValue) => {
  if (wasSimulating.value && !newValue) {
    // 从模拟中变为非模拟状态，显示结束提示
    showSimulationFinishedHint.value = true
  }
  wasSimulating.value = newValue
}, { immediate: true })

// 切换自环项展开/折叠状态
const toggleSelfLoop = (id) => {
  const newSet = new Set(expandedSelfLoops.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  expandedSelfLoops.value = newSet
}

// 实体类型英文->中文映射
const typeLabelMap = {
  'StoryCharacter': '角色', 'Character': '角色', 'Person': '人物',
  'StoryOrganization': '组织', 'Organization': '组织',
  'StoryItem': '物品', 'Item': '物品',
  'StoryEvent': '事件', 'Event': '事件',
  'StoryConcept': '概念', 'Concept': '概念',
  'StoryLocation': '地点', 'Location': '地点',
  'StoryCreature': '生物', 'Creature': '生物',
  'StoryMagic': '法术', 'Magic': '法术',
  'Entity': '实体',
  'Miss': '小姐', 'YoungMaster': '公子', 'YoungLady': '小姐',
  'Madam': '夫人', 'Master': '老爷', 'HousekeeperMadam': '管家',
  'Maid': '丫鬟',
}
const translateType = (t) => typeLabelMap[t] || t

// 计算实体类型用于图例
const entityTypes = computed(() => {
  if (!props.graphData?.nodes) return []
  const typeMap = {}
  const colors = ['#122E8A', '#E63946', '#2A9D8F', '#E9C46A', '#F4A261', '#457B9D', '#6D597A', '#B56576']
  
  props.graphData.nodes.forEach(node => {
    const type = node.labels?.find(l => l !== 'Entity') || 'Entity'
    const zhName = translateType(type)
    if (!typeMap[type]) {
      typeMap[type] = { name: zhName, rawName: type, count: 0, color: colors[Object.keys(typeMap).length % colors.length] }
    }
    typeMap[type].count++
  })
  return Object.values(typeMap)
})

// 计算总字数（信息流量）
const totalChars = computed(() => {
  if (!props.graphData?.nodes) return 0
  let total = 0
  props.graphData.nodes.forEach(n => {
    if (n.summary) total += n.summary.length
    if (n.name) total += n.name.length
    const attrs = n.attributes || {}
    Object.values(attrs).forEach(v => {
      if (typeof v === 'string') total += v.length
    })
  })
  return total.toLocaleString()
})

// 格式化时间
const formatDateTime = (dateStr) => {
  if (!dateStr) return ''
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true 
    })
  } catch {
    return dateStr
  }
}

const closeDetailPanel = () => {
  selectedItem.value = null
  expandedSelfLoops.value = new Set() // 重置展开状态
}

let currentSimulation = null
let linkLabelsRef = null
let linkLabelBgRef = null

const renderGraph = () => {
  if (!graphSvg.value || !props.graphData) return
  
  // 停止之前的仿真
  if (currentSimulation) {
    currentSimulation.stop()
  }
  
  const container = graphContainer.value
  const width = container.clientWidth
  const height = container.clientHeight
  
  const svg = d3.select(graphSvg.value)
    .attr('width', width)
    .attr('height', height)
    .attr('viewBox', `0 0 ${width} ${height}`)
    
  svg.selectAll('*').remove()
  
  const nodesData = props.graphData.nodes || []
  const edgesData = props.graphData.edges || []
  
  if (nodesData.length === 0) return

  // Prep data
  const nodeMap = {}
  nodesData.forEach(n => nodeMap[n.uuid] = n)
  
  const nodes = nodesData.map(n => ({
    id: n.uuid,
    name: n.name || 'Unnamed',
    type: n.labels?.find(l => l !== 'Entity') || 'Entity',
    rawData: n
  }))
  
  const nodeIds = new Set(nodes.map(n => n.id))
  
  // 处理边数据，计算同一对节点间的边数量和索引
  const edgePairCount = {}
  const selfLoopEdges = {} // 按节点分组的自环边
  const tempEdges = edgesData
    .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))
  
  // 统计每对节点之间的边数量，收集自环边
  tempEdges.forEach(e => {
    if (e.source_node_uuid === e.target_node_uuid) {
      // 自环 - 收集到数组中
      if (!selfLoopEdges[e.source_node_uuid]) {
        selfLoopEdges[e.source_node_uuid] = []
      }
      selfLoopEdges[e.source_node_uuid].push({
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      })
    } else {
      const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
      edgePairCount[pairKey] = (edgePairCount[pairKey] || 0) + 1
    }
  })
  
  // 记录当前处理到每对节点的第几条边
  const edgePairIndex = {}
  const processedSelfLoopNodes = new Set() // 已处理的自环节点
  
  const edges = []
  
  tempEdges.forEach(e => {
    const isSelfLoop = e.source_node_uuid === e.target_node_uuid
    
    if (isSelfLoop) {
      // 自环边 - 每个节点只添加一条合并的自环
      if (processedSelfLoopNodes.has(e.source_node_uuid)) {
        return // 已处理过，跳过
      }
      processedSelfLoopNodes.add(e.source_node_uuid)
      
      const allSelfLoops = selfLoopEdges[e.source_node_uuid]
      const nodeName = nodeMap[e.source_node_uuid]?.name || 'Unknown'
      
      edges.push({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: 'SELF_LOOP',
        name: `自关联 (${allSelfLoops.length})`,
        curvature: 0,
        isSelfLoop: true,
        rawData: {
          isSelfLoopGroup: true,
          source_name: nodeName,
          target_name: nodeName,
          selfLoopCount: allSelfLoops.length,
          selfLoopEdges: allSelfLoops // 存储所有自环边的详细信息
        }
      })
      return
    }
    
    const pairKey = [e.source_node_uuid, e.target_node_uuid].sort().join('_')
    const totalCount = edgePairCount[pairKey]
    const currentIndex = edgePairIndex[pairKey] || 0
    edgePairIndex[pairKey] = currentIndex + 1
    
    // 判断边的方向是否与标准化方向一致（源UUID < 目标UUID）
    const isReversed = e.source_node_uuid > e.target_node_uuid
    
    // 计算曲率：多条边时分散开，单条边为直线
    let curvature = 0
    if (totalCount > 1) {
      // 均匀分布曲率，确保明显区分
      // 曲率范围根据边数量增加，边越多曲率范围越大
      const curvatureRange = Math.min(1.2, 0.6 + totalCount * 0.15)
      curvature = ((currentIndex / (totalCount - 1)) - 0.5) * curvatureRange * 2
      
      // 如果边的方向与标准化方向相反，翻转曲率
      // 这样确保所有边在同一参考系下分布，不会因方向不同而重叠
      if (isReversed) {
        curvature = -curvature
      }
    }
    
    edges.push({
      source: e.source_node_uuid,
      target: e.target_node_uuid,
      type: e.fact_type || e.name || '关联',
      name: e.name || e.fact_type || '关联',
      curvature,
      isSelfLoop: false,
      pairIndex: currentIndex,
      pairTotal: totalCount,
      rawData: {
        ...e,
        source_name: nodeMap[e.source_node_uuid]?.name,
        target_name: nodeMap[e.target_node_uuid]?.name
      }
    })
  })
    
  // Color scale
  const colorMap = {}
  entityTypes.value.forEach(t => colorMap[t.name] = t.color)
  const getColor = (type) => colorMap[type] || '#4A5A8A'

  // Simulation - 根据边数量动态调整节点间距
  const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(d => {
      // 根据这对节点之间的边数量动态调整距离
      // 基础距离 150，每多一条边增加 40
      const baseDistance = 150
      const edgeCount = d.pairTotal || 1
      return baseDistance + (edgeCount - 1) * 50
    }))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collide', d3.forceCollide(50))
    // 添加向中心的引力，让独立的节点群聚集到中心区域
    .force('x', d3.forceX(width / 2).strength(0.04))
    .force('y', d3.forceY(height / 2).strength(0.04))
  
  currentSimulation = simulation

  const g = svg.append('g')
  
  // Zoom
  svg.call(d3.zoom().extent([[0, 0], [width, height]]).scaleExtent([0.1, 4]).on('zoom', (event) => {
    g.attr('transform', event.transform)
  }))

  // Links - 使用 path 支持曲线
  const linkGroup = g.append('g').attr('class', 'links')
  
  // 计算曲线路径
  const getLinkPath = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y
    
    // 检测自环
    if (d.isSelfLoop) {
      // 自环：绘制一个圆弧从节点出发再返回
      const loopRadius = 30
      // 从节点右侧出发，绕一圈回来
      const x1 = sx + 8  // 起点偏移
      const y1 = sy - 4
      const x2 = sx + 8  // 终点偏移
      const y2 = sy + 4
      // 使用圆弧绘制自环（sweep-flag=1 顺时针）
      return `M${x1},${y1} A${loopRadius},${loopRadius} 0 1,1 ${x2},${y2}`
    }
    
    if (d.curvature === 0) {
      // 直线
      return `M${sx},${sy} L${tx},${ty}`
    }
    
    // 计算曲线控制点 - 根据边数量和距离动态调整
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    // 垂直于连线方向的偏移，根据距离比例计算，保证曲线明显可见
    // 边越多，偏移量占距离的比例越大
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05 // 基础25%，每多一条边增加5%
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY
    
    return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`
  }
  
  // 计算曲线中点（用于标签定位）
  const getLinkMidpoint = (d) => {
    const sx = d.source.x, sy = d.source.y
    const tx = d.target.x, ty = d.target.y
    
    // 检测自环
    if (d.isSelfLoop) {
      // 自环标签位置：节点右侧
      return { x: sx + 70, y: sy }
    }
    
    if (d.curvature === 0) {
      return { x: (sx + tx) / 2, y: (sy + ty) / 2 }
    }
    
    // 二次贝塞尔曲线的中点 t=0.5
    const dx = tx - sx, dy = ty - sy
    const dist = Math.sqrt(dx * dx + dy * dy)
    const pairTotal = d.pairTotal || 1
    const offsetRatio = 0.25 + pairTotal * 0.05
    const baseOffset = Math.max(35, dist * offsetRatio)
    const offsetX = -dy / dist * d.curvature * baseOffset
    const offsetY = dx / dist * d.curvature * baseOffset
    const cx = (sx + tx) / 2 + offsetX
    const cy = (sy + ty) / 2 + offsetY
    
    // 二次贝塞尔曲线公式 B(t) = (1-t)²P0 + 2(1-t)tP1 + t²P2, t=0.5
    const midX = 0.25 * sx + 0.5 * cx + 0.25 * tx
    const midY = 0.25 * sy + 0.5 * cy + 0.25 * ty
    
    return { x: midX, y: midY }
  }
  
  const link = linkGroup.selectAll('path')
    .data(edges)
    .enter().append('path')
    .attr('stroke', 'rgba(18,46,138,0.2)')
    .attr('stroke-width', 1.5)
    .attr('fill', 'none')
    .style('cursor', 'pointer')
    .on('click', (event, d) => {
      event.stopPropagation()
      // 重置之前选中边的样式
      linkGroup.selectAll('path').attr('stroke', 'rgba(18,46,138,0.2)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
      linkLabels.attr('fill', '#4A5A8A')
      // 高亮当前选中的边
      d3.select(event.target).attr('stroke', '#E63946').attr('stroke-width', 3)
      
      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels background (白色背景使文字更清晰)
  const linkLabelBg = linkGroup.selectAll('rect')
    .data(edges)
    .enter().append('rect')
    .attr('fill', 'rgba(255,255,255,0.95)')
    .attr('rx', 3)
    .attr('ry', 3)
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      linkGroup.selectAll('path').attr('stroke', 'rgba(18,46,138,0.2)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
      linkLabels.attr('fill', '#4A5A8A')
      // 高亮对应的边
      link.filter(l => l === d).attr('stroke', '#E63946').attr('stroke-width', 3)
      d3.select(event.target).attr('fill', 'rgba(230,57,70,0.1)')
      
      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })

  // Link labels
  const linkLabels = linkGroup.selectAll('text')
    .data(edges)
    .enter().append('text')
    .text(d => d.name)
    .attr('font-size', '9px')
    .attr('fill', '#4A5A8A')
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'middle')
    .style('cursor', 'pointer')
    .style('pointer-events', 'all')
    .style('font-family', 'system-ui, sans-serif')
    .style('display', showEdgeLabels.value ? 'block' : 'none')
    .on('click', (event, d) => {
      event.stopPropagation()
      linkGroup.selectAll('path').attr('stroke', 'rgba(18,46,138,0.2)').attr('stroke-width', 1.5)
      linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
      linkLabels.attr('fill', '#4A5A8A')
      // 高亮对应的边
      link.filter(l => l === d).attr('stroke', '#E63946').attr('stroke-width', 3)
      d3.select(event.target).attr('fill', '#E63946')
      
      selectedItem.value = {
        type: 'edge',
        data: d.rawData
      }
    })
  
  // 保存引用供外部控制显隐
  linkLabelsRef = linkLabels
  linkLabelBgRef = linkLabelBg

  // Nodes group
  const nodeGroup = g.append('g').attr('class', 'nodes')
  
  // Node circles
  const node = nodeGroup.selectAll('circle')
    .data(nodes)
    .enter().append('circle')
    .attr('r', 10)
    .attr('fill', d => getColor(d.type))
    .attr('stroke', '#fff')
    .attr('stroke-width', 2.5)
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (event, d) => {
        // 只记录位置，不重启仿真（区分点击和拖拽）
        d.fx = d.x
        d.fy = d.y
        d._dragStartX = event.x
        d._dragStartY = event.y
        d._isDragging = false
      })
      .on('drag', (event, d) => {
        // 检测是否真正开始拖拽（移动超过阈值）
        const dx = event.x - d._dragStartX
        const dy = event.y - d._dragStartY
        const distance = Math.sqrt(dx * dx + dy * dy)
        
        if (!d._isDragging && distance > 3) {
          // 首次检测到真正拖拽，才重启仿真
          d._isDragging = true
          simulation.alphaTarget(0.3).restart()
        }
        
        if (d._isDragging) {
          d.fx = event.x
          d.fy = event.y
        }
      })
      .on('end', (event, d) => {
        // 只有真正拖拽过才让仿真逐渐停止
        if (d._isDragging) {
          simulation.alphaTarget(0)
        }
        d.fx = null
        d.fy = null
        d._isDragging = false
      })
    )
    .on('click', (event, d) => {
      event.stopPropagation()
      // 重置所有节点样式
      node.attr('stroke', '#fff').attr('stroke-width', 2.5)
      linkGroup.selectAll('path').attr('stroke', 'rgba(18,46,138,0.2)').attr('stroke-width', 1.5)
      // 高亮选中节点
      d3.select(event.target).attr('stroke', '#E63946').attr('stroke-width', 4)
      // 高亮与此节点相连的边
      link.filter(l => l.source.id === d.id || l.target.id === d.id)
        .attr('stroke', '#E63946')
        .attr('stroke-width', 2.5)
      
      selectedItem.value = {
        type: 'node',
        data: d.rawData,
        entityType: d.type,
        color: getColor(d.type)
      }
    })
    .on('mouseenter', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', '#122E8A').attr('stroke-width', 3)
      }
    })
    .on('mouseleave', (event, d) => {
      if (!selectedItem.value || selectedItem.value.data?.uuid !== d.rawData.uuid) {
        d3.select(event.target).attr('stroke', '#fff').attr('stroke-width', 2.5)
      }
    })

  // Node Labels
  const nodeLabels = nodeGroup.selectAll('text')
    .data(nodes)
    .enter().append('text')
    .text(d => d.name.length > 8 ? d.name.substring(0, 8) + '…' : d.name)
    .attr('font-size', '11px')
    .attr('fill', '#122E8A')
    .attr('font-weight', '500')
    .attr('dx', 14)
    .attr('dy', 4)
    .style('pointer-events', 'none')
    .style('font-family', 'system-ui, sans-serif')

  simulation.on('tick', () => {
    // 更新曲线路径
    link.attr('d', d => getLinkPath(d))
    
    // 更新边标签位置（无旋转，水平显示更清晰）
    linkLabels.each(function(d) {
      const mid = getLinkMidpoint(d)
      d3.select(this)
        .attr('x', mid.x)
        .attr('y', mid.y)
        .attr('transform', '') // 移除旋转，保持水平
    })
    
    // 更新边标签背景
    linkLabelBg.each(function(d, i) {
      const mid = getLinkMidpoint(d)
      const textEl = linkLabels.nodes()[i]
      const bbox = textEl.getBBox()
      d3.select(this)
        .attr('x', mid.x - bbox.width / 2 - 4)
        .attr('y', mid.y - bbox.height / 2 - 2)
        .attr('width', bbox.width + 8)
        .attr('height', bbox.height + 4)
        .attr('transform', '') // 移除旋转
    })

    node
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)

    nodeLabels
      .attr('x', d => d.x)
      .attr('y', d => d.y)
  })
  
  // 点击空白处关闭详情面板
  svg.on('click', () => {
    selectedItem.value = null
    node.attr('stroke', '#fff').attr('stroke-width', 2.5)
    linkGroup.selectAll('path').attr('stroke', 'rgba(18,46,138,0.2)').attr('stroke-width', 1.5)
    linkLabelBg.attr('fill', 'rgba(255,255,255,0.95)')
    linkLabels.attr('fill', '#4A5A8A')
  })
}

watch(() => props.graphData, () => {
  nextTick(renderGraph)
}, { deep: true })

// 监听边标签显示开关
watch(showEdgeLabels, (newVal) => {
  if (linkLabelsRef) {
    linkLabelsRef.style('display', newVal ? 'block' : 'none')
  }
  if (linkLabelBgRef) {
    linkLabelBgRef.style('display', newVal ? 'block' : 'none')
  }
})

const handleResize = () => {
  nextTick(renderGraph)
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
  // 模拟推理速度更新（后续可改为从 prop/event 接收）
  aiSpeed.value = '42ms'
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (currentSimulation) {
    currentSimulation.stop()
  }
})
</script>

<style scoped>
.graph-panel {
  position: relative;
  width: 100%;
  height: 100%;
  background-color: var(--bg-primary);
  background-image: radial-gradient(var(--accent) 1px, transparent 1px);
  background-size: 24px 24px;
  overflow: hidden;
}

.panel-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding: 12px 16px;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: linear-gradient(to bottom, var(--bg-secondary), transparent);
  pointer-events: none;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  pointer-events: auto;
}

.header-tools {
  pointer-events: auto;
  display: flex;
  gap: 8px;
  align-items: center;
}

.tool-btn {
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--card-border, rgba(0,0,0,0.08));
  background: var(--bg-secondary);
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
  box-shadow: 0 1px 3px var(--card-shadow, rgba(0,0,0,0.03));
  font-size: 12px;
}

.tool-btn:hover {
  background: var(--accent);
  color: var(--text-primary);
  border-color: var(--accent-strong);
}

.tool-btn .btn-text { font-size: 11px; }
.icon-refresh.spinning { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* 顶部状态栏 */
.graph-stats-bar {
  position: absolute;
  top: 48px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-secondary);
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid var(--card-border, rgba(0,0,0,0.06));
  box-shadow: 0 2px 8px var(--card-shadow, rgba(0,0,0,0.04));
  z-index: 10;
  font-size: 12px;
}

.stat-item { display: flex; align-items: center; gap: 4px; }
.stat-icon { font-size: 10px; color: var(--accent-strong); }
.stat-value { font-weight: 600; color: var(--text-primary); min-width: 20px; text-align: center; }
.stat-label { color: var(--text-secondary); font-size: 11px; }
.stat-divider { width: 1px; height: 12px; background: var(--card-border, rgba(0,0,0,0.08)); }

.graph-container {
  width: 100%;
  height: 100%;
}

.graph-view, .graph-svg { width: 100%; height: 100%; display: block; }
.graph-svg { background: transparent; }

.graph-state {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  text-align: center;
  color: var(--text-muted, var(--text-secondary));
}

.empty-icon { font-size: 48px; margin-bottom: 16px; opacity: 0.2; }
.building-spinner {
  width: 40px; height: 40px;
  border: 3px solid rgba(18,46,138,0.15);
  border-top-color: #122E8A;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 16px;
}
.empty-sub { font-size: 12px; color: #4A5A8A; opacity: 0.6; margin-top: 4px; }

/* 节点为空时的底部小提示 */
.graph-empty-hint {
  position: absolute;
  bottom: 60px;
  left: 50%;
  transform: translateX(-50%);
  color: #4A5A8A;
  font-size: 13px;
  background: rgba(255,255,255,0.7);
  padding: 8px 16px;
  border-radius: 20px;
  pointer-events: none;
  z-index: 5;
}

/* 构建中角落提示 */
.graph-building-corner-hint {
  position: absolute;
  top: 100px;
  right: 20px;
  background: rgba(18,46,138,0.85);
  color: #F1DDDF;
  padding: 6px 12px;
  border-radius: 16px;
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 6px;
  z-index: 10;
}
.corner-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #4CAF50;
  animation: breathe 1.5s ease-in-out infinite;
}

/* 实体类型图例 - 左下角 */
.graph-legend {
  position: absolute;
  bottom: 24px;
  left: 24px;
  background: var(--bg-secondary);
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid var(--card-border, rgba(0,0,0,0.06));
  box-shadow: 0 4px 16px var(--card-shadow, rgba(0,0,0,0.06));
  z-index: 10;
}

.legend-title {
  display: block;
  font-size: 10px;
  font-weight: 600;
  color: var(--accent-strong);
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.legend-items { display: flex; flex-wrap: wrap; gap: 8px 14px; max-width: 320px; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-secondary); }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.legend-label { white-space: nowrap; }

/* Detail Panel - Right Side - COMPACT REDESIGN */
.detail-panel {
  position: absolute;
  top: 80px;
  right: 16px;
  width: 280px;
  max-height: calc(100% - 110px);
  background: var(--bg-secondary);
  border: 1px solid var(--card-border, rgba(0,0,0,0.08));
  border-radius: 10px;
  box-shadow: 0 8px 32px var(--card-shadow, rgba(0,0,0,0.1));
  overflow: hidden;
  font-size: 12px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(12px);
}

.detail-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg-primary);
  border-bottom: 1px solid var(--card-border, rgba(0,0,0,0.06));
  flex-shrink: 0;
}

.detail-title { font-weight: 600; color: var(--text-primary); font-size: 13px; }

.detail-type-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  margin-left: auto;
  margin-right: 8px;
}

.detail-close {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--text-muted, var(--text-secondary));
  line-height: 1;
  padding: 0 2px;
  transition: color 0.2s;
}
.detail-close:hover { color: var(--text-primary); }

.detail-content {
  padding: 12px 14px;
  overflow-y: auto;
  flex: 1;
}

.detail-row { margin-bottom: 8px; display: flex; gap: 4px; }
.detail-label { color: var(--text-muted, var(--text-secondary)); font-size: 11px; font-weight: 500; min-width: 60px; flex-shrink: 0; }
.detail-value { color: var(--text-primary); flex: 1; word-break: break-word; font-size: 12px; }
.detail-value.uuid-text { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: var(--text-muted, var(--text-secondary)); }
.detail-value.fact-text { line-height: 1.4; color: var(--text-primary); }

.detail-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--card-border, rgba(0,0,0,0.06)); }
.section-title { font-size: 11px; font-weight: 600; color: var(--accent-strong); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.3px; }

.properties-list { display: flex; flex-direction: column; gap: 6px; }
.property-item { display: flex; gap: 6px; font-size: 11px; }
.property-key { color: var(--text-muted, var(--text-secondary)); font-weight: 500; min-width: 70px; flex-shrink: 0; }
.property-value { color: var(--text-primary); flex: 1; }

.summary-text { line-height: 1.5; color: var(--text-secondary); font-size: 11px; }

.labels-list { display: flex; flex-wrap: wrap; gap: 4px; }
.label-tag { padding: 2px 8px; background: var(--accent); border-radius: 10px; font-size: 10px; color: var(--text-primary); }

.episodes-list { display: flex; flex-direction: column; gap: 4px; }
.episode-tag { padding: 4px 8px; background: var(--bg-primary); border: 1px solid var(--card-border, rgba(0,0,0,0.06)); border-radius: 4px; font-size: 10px; color: var(--text-secondary); word-break: break-all; }

/* Edge relation header */
.edge-relation-header {
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.4;
  word-break: break-word;
}

/* Building hint */
.graph-building-hint {
  position: absolute;
  bottom: 140px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0,0,0,0.7);
  backdrop-filter: blur(8px);
  color: #fff;
  padding: 8px 16px;
  border-radius: 24px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.15);
  z-index: 100;
  font-weight: 500;
}

.memory-icon-wrapper { display: flex; align-items: center; justify-content: center; animation: breathe 2s ease-in-out infinite; }
.memory-icon { width: 16px; height: 16px; color: #4CAF50; }

@keyframes breathe {
  0%, 100% { opacity: 0.7; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.15); }
}

/* Loading spinner */
.loading-spinner {
  width: 32px; height: 32px;
  border: 3px solid var(--card-border, rgba(0,0,0,0.08));
  border-top-color: var(--accent-strong);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin: 0 auto 12px;
}

/* Self-loop styles */
.self-loop-header { display: flex; align-items: center; gap: 6px; background: var(--bg-primary); border: 1px solid var(--card-border, rgba(0,0,0,0.06)); }
.self-loop-count { margin-left: auto; font-size: 10px; color: var(--text-muted, var(--text-secondary)); }
.self-loop-list { display: flex; flex-direction: column; gap: 8px; }
.self-loop-item { background: var(--bg-primary); border: 1px solid var(--card-border, rgba(0,0,0,0.06)); border-radius: 6px; }
.self-loop-item-header { display: flex; align-items: center; gap: 6px; padding: 8px 10px; cursor: pointer; transition: background 0.2s; }
.self-loop-item-header:hover { background: var(--accent); }
.self-loop-item.expanded .self-loop-item-header { background: var(--accent); }
.self-loop-index { font-size: 9px; font-weight: 600; color: var(--text-muted, var(--text-secondary)); background: var(--accent); padding: 1px 5px; border-radius: 3px; }
.self-loop-name { font-size: 11px; font-weight: 500; color: var(--text-primary); flex: 1; }
.self-loop-toggle { width: 18px; height: 18px; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; color: var(--text-muted, var(--text-secondary)); background: var(--accent); border-radius: 3px; }
.self-loop-item-content { padding: 10px; border-top: 1px solid var(--card-border, rgba(0,0,0,0.06)); }
.self-loop-item-content .detail-row { margin-bottom: 6px; }
.self-loop-item-content .detail-label { font-size: 10px; min-width: 50px; }
.episode-tag.small { padding: 2px 5px; font-size: 9px; }

/* Edge Labels Toggle - keeps original position */
.edge-labels-toggle {
  position: absolute;
  bottom: 24px;
  right: 24px;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-secondary);
  padding: 6px 12px;
  border-radius: 16px;
  border: 1px solid var(--card-border, rgba(0,0,0,0.06));
  box-shadow: 0 2px 8px var(--card-shadow, rgba(0,0,0,0.04));
  z-index: 10;
}
.toggle-switch { position: relative; display: inline-block; width: 32px; height: 18px; }
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.slider { position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background: var(--card-border, rgba(0,0,0,0.12)); border-radius: 18px; transition: 0.3s; }
.slider:before { position: absolute; content: ""; height: 14px; width: 14px; left: 2px; bottom: 2px; background: white; border-radius: 50%; transition: 0.3s; }
input:checked + .slider { background: var(--accent-strong); }
input:checked + .slider:before { transform: translateX(14px); }
.toggle-label { font-size: 11px; color: var(--text-secondary); }
</style>
