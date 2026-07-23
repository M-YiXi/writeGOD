<template>
  <div class="home" :class="{ dark: isDark }">
    <div class="flowing-bg">
      <span v-for="(q, i) in quotes" :key="i" class="flow-text" :style="getFlowStyle(i)">{{ q.text }}</span>
    </div>
    <div class="brand">
      <h1 class="brand-name" ref="brandName">writeGOD</h1>
      <div class="brand-intro">
        <div class="intro-bar"></div>
        <div class="intro-text" ref="introText"></div>
      </div>
    </div>
    <div class="topbar">
      <button class="tool-btn" @click="toggleLang">{{ lang === 'zh' ? 'EN' : '中文' }}</button>
      <button class="tool-btn" @click="toggleDark">{{ isDark ? '☀' : '☾' }}</button>
    </div>
    <div class="entry-area">
      <div class="entry-card" @click="goTo('outline')" ref="card1">
        <span class="card-icon">📚</span>
        <h2>素材大纲</h2>
        <p>导入参考资料，自动提取实体并构建关联网络</p>
        <div class="card-tags">
          <span>多源导入</span><span>实体提取</span><span>关联推理</span>
        </div>
      </div>
      <div class="entry-card" @click="goTo('prediction')" ref="card2">
        <span class="card-icon">📖</span>
        <h2>小说推演</h2>
        <p>分析整本小说，与角色对话，检测逻辑漏洞</p>
        <div class="card-tags">
          <span>角色对话</span><span>逻辑检测</span><span>多视角评论</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const lang = ref('zh')
const isDark = ref(false)
const brandName = ref(null)
const introText = ref(null)
const card1 = ref(null)
const card2 = ref(null)

const colors = [
  '#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#F4A261',
  '#6D597A', '#B56576', '#4A7CF7', '#E8A87C', '#C9A0DC',
  '#355070', '#6D6875', '#FFB703', '#FB8500', '#06D6A0',
  '#118AB2', '#EF476F', '#FFD166', '#073B4C', '#7B2D8E'
]

const quotes = [
  // 中文现代诗 80 句
  { text: '面朝大海，春暖花开', color: colors[0] },
  { text: '从明天起，做一个幸福的人', color: colors[1] },
  { text: '你来人间一趟，你要看看太阳', color: colors[2] },
  { text: '活在这珍贵的人间太阳强烈水波温柔', color: colors[3] },
  { text: '给每一条河每一座山取个温暖的名字', color: colors[4] },
  { text: '陌生人我也为你祝福', color: colors[5] },
  { text: '愿你有一个灿烂的前程', color: colors[6] },
  { text: '愿你有情人终成眷属', color: colors[7] },
  { text: '我只愿面朝大海春暖花开', color: colors[8] },
  { text: '黑夜给了我黑色的眼睛', color: colors[9] },
  { text: '我却用它寻找光明', color: colors[10] },
  { text: '你一会看我一会看云', color: colors[11] },
  { text: '我觉得你看我时很远你看云时很近', color: colors[12] },
  { text: '草在结它的种子风在摇它的叶子', color: colors[14] },
  { text: '我们站着不说话就十分美好', color: colors[15] },
  { text: '我是一个任性的孩子', color: colors[16] },
  { text: '我想在大地上画满窗子', color: colors[17] },
  { text: '让所有习惯黑暗的眼睛都习惯光明', color: colors[18] },
  { text: '你站在桥上看风景', color: colors[19] },
  { text: '看风景的人在楼上看你', color: colors[0] },
  { text: '明月装饰了你的窗子', color: colors[2] },
  { text: '你装饰了别人的梦', color: colors[4] },
  { text: '轻轻的我走了正如我轻轻的来', color: colors[6] },
  { text: '我轻轻的招手作别西天的云彩', color: colors[8] },
  { text: '悄悄是别离的笙箫', color: colors[10] },
  { text: '我挥一挥衣袖不带走一片云彩', color: colors[12] },
  { text: '我是天空里的一片云', color: colors[14] },
  { text: '偶尔投影在你的波心', color: colors[16] },
  { text: '你是爱是暖是希望', color: colors[18] },
  { text: '你是爱是暖是希望你是人间四月天', color: colors[1] },
  { text: '为什么我的眼里常含泪水', color: colors[3] },
  { text: '因为我对这土地爱得深沉', color: colors[5] },
  { text: '卑鄙是卑鄙者的通行证', color: colors[7] },
  { text: '高尚是高尚者的墓志铭', color: colors[9] },
  { text: '那时我们有梦关于文学', color: colors[11] },
  { text: '关于穿越世界的旅行', color: colors[13] },
  { text: '如今我们深夜饮酒杯子碰到一起', color: colors[15] },
  { text: '都是梦破碎的声音', color: colors[17] },
  { text: '玻璃晴朗橘子辉煌', color: colors[19] },
  { text: '我和这个世界不熟', color: colors[2] },
  { text: '月光还是少年的月光', color: colors[5] },
  { text: '九州一色还是李白的霜', color: colors[8] },
  { text: '乡愁是一枚小小的邮票', color: colors[11] },
  { text: '我在这头母亲在那头', color: colors[14] },
  { text: '下次你路过人间已无我', color: colors[17] },
  { text: '酒入豪肠七分酿成了月光', color: colors[0] },
  { text: '余下的三分啸成剑气', color: colors[3] },
  { text: '绣口一吐就半个盛唐', color: colors[6] },
  { text: '心有猛虎细嗅蔷薇', color: colors[9] },
  { text: '当我死时葬我在长江黄河之间', color: colors[12] },
  { text: '我们相爱一生还是太短', color: colors[15] },
  { text: '我行过许多地方的桥', color: colors[18] },
  { text: '看过许多次数的云', color: colors[1] },
  { text: '喝过许多种类的酒', color: colors[4] },
  { text: '却只爱过一个正当最好年龄的人', color: colors[7] },
  { text: '爱在左同情在右走在生命路的两旁', color: colors[10] },
  { text: '随时撒种随时开花', color: colors[16] },
  { text: '踏着荆棘不觉得痛苦', color: colors[19] },
  { text: '有泪可落也不是悲凉', color: colors[2] },
  { text: '即使踏着荆棘也不觉悲苦', color: colors[5] },
  { text: '从前的日色变得慢车马邮件都慢', color: colors[8] },
  { text: '一生只够爱一个人', color: colors[11] },
  { text: '记得早先少年时大家诚诚恳恳', color: colors[14] },
  { text: '说一句是一句', color: colors[17] },
  { text: '你锁了人家就懂了', color: colors[0] },
  { text: '黑夜慢慢降临遮住了一切', color: colors[3] },
  { text: '但遮不住我们相爱的眼睛', color: colors[6] },
  { text: '远方除了遥远一无所有', color: colors[9] },
  { text: '更远的地方更加孤独', color: colors[12] },
  { text: '远方的幸福是多少痛苦', color: colors[15] },
  { text: '风后面是风天空上面是天空', color: colors[18] },
  { text: '道路前面还是道路', color: colors[1] },
  { text: '世界以痛吻我要我报之以歌', color: colors[4] },
  { text: '如果你因失去了太阳而流泪', color: colors[7] },
  { text: '那么你也将失去群星', color: colors[10] },
  { text: '天空没有翅膀的痕迹但我已飞过', color: colors[13] },
  { text: '一颗心被燃烧不为灰烬', color: colors[19] },
  { text: '只为了那瞬间的明亮', color: colors[2] },
  { text: '我们都是长行的旅客向着同一归宿', color: colors[5] },
  { text: '记忆是相会的一种形式忘记是自由', color: colors[8] },
  { text: '青春是一本太仓促的书我们含泪读', color: colors[11] },
  // 英文现代诗 20 句
  { text: 'Two roads diverged in a yellow wood', color: colors[5] },
  { text: 'And sorry I could not travel both', color: colors[8] },
  { text: 'The woods are lovely dark and deep', color: colors[11] },
  { text: 'But I have promises to keep', color: colors[14] },
  { text: 'And miles to go before I sleep', color: colors[17] },
  { text: 'Do not go gentle into that good night', color: colors[0] },
  { text: 'Rage rage against the dying of the light', color: colors[3] },
  { text: 'Hope is the thing with feathers', color: colors[6] },
  { text: 'That perches in the soul', color: colors[9] },
  { text: 'I dwell in possibility', color: colors[12] },
  { text: 'A fairer house than prose', color: colors[15] },
  { text: 'Shall I compare thee to a summer day', color: colors[18] },
  { text: 'Thou art more lovely and more temperate', color: colors[1] },
  { text: 'April is the cruellest month', color: colors[4] },
  { text: 'This is the way the world ends', color: colors[7] },
  { text: 'Not with a bang but a whimper', color: colors[10] },
  { text: 'I am the master of my fate', color: colors[13] },
  { text: 'I am the captain of my soul', color: colors[16] },
  { text: 'The fog comes on little cat feet', color: colors[19] },
]

const introLines = [
  '以知识图谱重构创作边界，',
  '让每一粒文字的星辰找到归处。',
  '向量深处，灵感自现——',
  '写作之神，伴你书写不朽篇章。'
]

const getFlowStyle = (i) => {
  const q = quotes[i]
  return {
    top: `${(i * 2.1 + 3) % 100}%`,
    left: `${((i * 7 + 11) % 70) + 5}%`,
    animationDelay: `-${(i * 0.7) % 18}s`,
    animationDuration: `${45 + (i % 12) * 4}s`,
    fontSize: `${14 + (i % 8)}px`,
    color: q.color,
    opacity: 0.35 + (i % 3) * 0.1
  }
}

const toggleLang = () => {
  lang.value = lang.value === 'zh' ? 'en' : 'zh'
  document.documentElement.lang = lang.value
}

const toggleDark = () => {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  document.documentElement.style.colorScheme = isDark.value ? 'dark' : 'light'
}

const goTo = (type) => {
  router.push({ name: 'Process', params: { projectId: 'new' }, query: { type } })
}

let brandTween = null
let typewriterTimer = null

const startTypewriter = () => {
  if (!introText.value) return
  let lineIdx = 0
  let charIdx = 0
  introText.value.textContent = ''
  const typeNextChar = () => {
    if (lineIdx >= introLines.length) { lineIdx = 0; charIdx = 0; introText.value.textContent = '' }
    const line = introLines[lineIdx]
    if (charIdx < line.length) {
      introText.value.textContent += line[charIdx]
      charIdx++
      typewriterTimer = setTimeout(typeNextChar, 70)
    } else {
      if (lineIdx < introLines.length - 1) introText.value.textContent += '\n'
      lineIdx++; charIdx = 0
      typewriterTimer = setTimeout(typeNextChar, 1500)
    }
  }
  typeNextChar()
}

onMounted(async () => {
  let gsap
  try { const m = await import('gsap'); gsap = m.default || m } catch { gsap = null }
  if (gsap && brandName.value) {
    brandTween = gsap.from(brandName.value, { opacity: 0, y: -30, duration: 1, ease: 'power4.out' })
  }
  startTypewriter()
})

onUnmounted(() => {
  if (brandTween) brandTween.kill()
  if (typewriterTimer) clearTimeout(typewriterTimer)
})
</script>

<style scoped>
.home {
  position: relative;
  min-height: 100vh;
  background: #F1DDDF;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.4s ease;
}
.flowing-bg {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}
.flow-text {
  position: absolute;
  font-weight: 600;
  white-space: nowrap;
  animation: flowAcross linear infinite;
  user-select: none;
  will-change: transform;
  text-shadow: 0 0 4px rgba(255,255,255,0.3);
}
@keyframes flowAcross {
  0% { transform: translateX(105vw); opacity: 0; }
  8% { opacity: 1; }
  85% { opacity: 1; }
  100% { transform: translateX(-15vw); opacity: 0; }
}
.brand {
  position: fixed;
  top: 36px;
  left: 40px;
  z-index: 10;
}
.brand-name {
  font-size: 2.6rem;
  font-weight: 800;
  color: #122E8A;
  letter-spacing: 3px;
  line-height: 1.1;
  margin: 0 0 8px 0;
}
.brand-intro {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 48px;
}
.intro-bar {
  width: 3px;
  height: 44px;
  background: #122E8A;
  border-radius: 2px;
  flex-shrink: 0;
  animation: barPulse 2s ease-in-out infinite;
}
@keyframes barPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.intro-text {
  font-size: 0.9rem;
  color: #4A5A8A;
  line-height: 1.6;
  white-space: pre-wrap;
  font-weight: 400;
  min-height: 44px;
  max-width: 280px;
}
.topbar {
  position: fixed;
  top: 28px;
  right: 32px;
  display: flex;
  gap: 10px;
  z-index: 100;
}
.tool-btn {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #122E8A;
  background: rgba(255,255,255,0.5);
  border: 1px solid rgba(255,255,255,0.6);
  border-radius: 12px;
  backdrop-filter: blur(8px);
  transition: all 0.25s;
  cursor: pointer;
}
.tool-btn:hover { transform: scale(1.08); background: rgba(255,255,255,0.7); }
.entry-area {
  position: relative;
  z-index: 10;
  display: flex;
  gap: 28px;
  margin-top: 40px;
}
.entry-card {
  position: relative;
  width: 310px;
  padding: 30px 26px;
  cursor: pointer;
  background: rgba(255,255,255,0.55);
  border: 1px solid rgba(255,255,255,0.5);
  border-radius: 16px;
  backdrop-filter: blur(12px);
  transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.entry-card:hover {
  transform: translateY(-6px) scale(1.02);
  background: rgba(255,255,255,0.7);
  box-shadow: 0 20px 48px rgba(18,46,138,0.1);
}
.card-icon { font-size: 2.2rem; display: block; margin-bottom: 14px; }
.entry-card h2 { font-size: 1.4rem; font-weight: 700; color: #122E8A; margin-bottom: 8px; }
.entry-card p { font-size: 0.82rem; color: #4A5A8A; line-height: 1.5; opacity: 0.9; margin: 0; }
.card-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 14px; }
.card-tags span {
  font-size: 0.68rem;
  padding: 3px 10px;
  border-radius: 10px;
  background: rgba(18,46,138,0.1);
  color: #122E8A;
  font-weight: 500;
}
.home.dark { background: #1A1A2E; }
.home.dark .brand-name { color: #F1DDDF; }
.home.dark .intro-bar { background: #F1DDDF; }
.home.dark .intro-text { color: #C0B0C0; }
.home.dark .tool-btn { color: #F1DDDF; background: rgba(255,255,255,0.08); border-color: rgba(255,255,255,0.1); }
.home.dark .entry-card { background: rgba(26,26,46,0.6); border-color: rgba(241,221,223,0.1); }
.home.dark .entry-card:hover { background: rgba(26,26,46,0.8); }
.home.dark .entry-card h2 { color: #F1DDDF; }
.home.dark .entry-card p { color: #C0B0C0; }
.home.dark .card-tags span { background: rgba(241,221,223,0.12); color: #F1DDDF; }
@media (max-width: 768px) {
  .brand { top: 24px; left: 20px; }
  .brand-name { font-size: 1.8rem; }
  .entry-area { flex-direction: column; padding: 0 20px; gap: 20px; margin-top: 20px; }
  .entry-card { width: 100%; max-width: 360px; }
  .topbar { right: 16px; top: 16px; }
}
</style>
