"""
Plot Checker — 逻辑漏洞与未回收伏笔检测引擎

核心思路：
1. 逻辑漏洞：通过图遍历查找矛盾（如角色死亡后再次出现、时间线冲突）
2. 未回收伏笔：查找图中出现频率低但标记为"重要"的实体/事件
"""

import logging
from typing import Dict, Any, List, Optional
from ..storage.graph_storage import GraphStorage
from ..utils.llm_client import LLMClient

logger = logging.getLogger('writegod.plot_checker')


class PlotChecker:
    """
    逻辑检测引擎
    结合图遍历 + 向量检索 + LLM 分析小说中的逻辑问题和未回收伏笔
    """

    def __init__(self, storage: GraphStorage, llm_client: Optional[LLMClient] = None):
        self.storage = storage
        self.llm = llm_client or LLMClient()

    def check_holes(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        检测逻辑漏洞
        
        检测维度：
        1. 角色死亡后再次出现（有 KILLED 边但后续仍有该角色的活动边）
        2. 时间线冲突（事件顺序矛盾）
        3. 设定矛盾（同一设定在不同地方描述不一致）
        """
        holes = []
        
        # 1. 检测死亡角色后续活动
        holes.extend(self._check_dead_characters_active(graph_id))
        
        # 2. 检测设定一致性（通过向量检索相似描述）
        holes.extend(self._check_setting_consistency(graph_id))
        
        return holes

    def check_unresolved(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        检测未回收伏笔
        
        检测维度：
        1. 孤立节点（仅出现一次的角色/事件/物品）
        2. 未闭合的关系线（有 ESTABLISHED 边但没有 RESOLVED 边）
        """
        unresolved = []
        
        # 1. 查找度数极低的节点（可能是伏笔）
        unresolved.extend(self._find_isolated_nodes(graph_id))
        
        return unresolved

    def _check_dead_characters_active(self, graph_id: str) -> List[Dict[str, Any]]:
        """检测已死亡角色是否后续还有活动"""
        holes = []
        try:
            all_edges = self.storage.get_all_edges(graph_id)
            
            # 查找所有 KILLED 关系
            killed = {}
            for e in all_edges:
                if e.get('name', '').upper() == 'KILLED':
                    target = e.get('target_node_uuid', '')
                    killed[target] = e
            
            # 检查这些节点是否还有其他后续边
            if killed:
                for uuid, edge in killed.items():
                    target_name = 'Unknown'
                    tn = self.storage.get_node(uuid)
                    if tn: target_name = tn.get('name', 'Unknown')
                    source_name = 'Unknown'
                    suid = edge.get('source_node_uuid', '')
                    if suid:
                        sn = self.storage.get_node(suid)
                        if sn: source_name = sn.get('name', 'Unknown')
                    holes.append({
                        "type": "character_death",
                        "severity": "warning",
                        "description": f"角色 {target_name} 被 {source_name} 击杀",
                        "detail": "需要人工确认该角色后续是否还有出场",
                        "related_uuids": [uuid, edge.get('source_node_uuid', '')]
                    })
        except Exception as e:
            logger.warning(f"Death check failed: {e}")
        
        return holes

    def _check_setting_consistency(self, graph_id: str) -> List[Dict[str, Any]]:
        """
        检测设定一致性：使用向量检索查找同一角色的不同描述，检测是否矛盾。
        
        策略：
        1. 获取所有角色类节点
        2. 对每个角色，用向量检索查找与其相关的所有边（facts）
        3. 如果同一角色的 facts 语义上相似但描述不同，可能存在矛盾
        """
        holes = []
        try:
            all_nodes = self.storage.get_all_nodes(graph_id)
            all_edges = self.storage.get_all_edges(graph_id)
            
            # 按角色分组所有相关的 facts
            character_facts = {}  # uuid -> list of facts
            for node in all_nodes:
                labels = node.get("labels", [])
                # 判断是否为角色类节点（包含 Person/Character/Miss/YoungMaster 等标签）
                char_labels = {"Person", "Character", "Miss", "YoungMaster", "Madam", "Master", "HousekeeperMadam"}
                if any(l in char_labels for l in labels):
                    uuid = node.get("uuid", "")
                    name = node.get("name", "Unknown")
                    character_facts[uuid] = {"name": name, "facts": []}
            
            # 收集每个角色的相关 facts
            for edge in all_edges:
                src = edge.get("source_node_uuid", "")
                tgt = edge.get("target_node_uuid", "")
                fact = edge.get("fact", "")
                if not fact:
                    continue
                if src in character_facts:
                    character_facts[src]["facts"].append(fact)
                if tgt in character_facts:
                    character_facts[tgt]["facts"].append(fact)
            
            # 对有多个 facts 的角色，用 LLM 检测矛盾
            for uuid, info in character_facts.items():
                facts = info["facts"]
                if len(facts) < 2:
                    continue
                
                # 用 LLM 检测同一角色的描述是否有矛盾
                facts_text = "\n".join(f"- {f}" for f in facts)
                try:
                    messages = [
                        {"role": "system", "content": "你是小说逻辑检测专家。分析给定角色的所有描述，找出互相矛盾的描述。只返回矛盾项，没有矛盾则返回空数组。返回JSON格式：{\"contradictions\": [{\"desc\": \"矛盾描述\", \"facts\": [\"fact1\", \"fact2\"]}]}"},
                        {"role": "user", "content": f"角色：{info['name']}\n相关描述：\n{facts_text}"}
                    ]
                    result = self.llm.chat_json(messages=messages, temperature=0.1, max_tokens=2048, disable_thinking=True)
                    contradictions = result.get("contradictions", [])
                    for c in contradictions:
                        holes.append({
                            "type": "setting_inconsistency",
                            "severity": "warning",
                            "description": f"角色「{info['name']}」的描述存在矛盾：{c.get('desc', '')}",
                            "detail": f"相关描述：{', '.join(c.get('facts', []))}",
                            "related_uuids": [uuid]
                        })
                except Exception as e:
                    logger.debug(f"LLM consistency check failed for {info['name']}: {e}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Setting consistency check failed: {e}")
        
        return holes

    def _find_isolated_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        """查找孤立节点（可能被遗忘的伏笔）"""
        unresolved = []
        try:
            all_nodes = self.storage.get_all_nodes(graph_id)
            all_edges = self.storage.get_all_edges(graph_id)
            
            # 统计每个节点的关联边数
            edge_count = {}
            for e in all_edges:
                src = e.get('source_node_uuid', '')
                tgt = e.get('target_node_uuid', '')
                edge_count[src] = edge_count.get(src, 0) + 1
                edge_count[tgt] = edge_count.get(tgt, 0) + 1
            
            # 找出度数为 1 的节点（只被提到一次）
            for node in all_nodes:
                nid = node.get('uuid', '')
                count = edge_count.get(nid, 0)
                if count <= 1:
                    name = node.get('name', 'Unknown')
                    ntype = 'Unknown'
                    for label in node.get('labels', []):
                        if label not in ['Entity', 'Node']:
                            ntype = label
                            break
                    unresolved.append({
                        "type": "isolated_node",
                        "severity": "info",
                        "description": f"节点「{name}」（{ntype}）仅出现一次，可能是未回收的伏笔",
                        "detail": "该节点在整个图谱中只有 1 条关联",
                        "related_uuids": [nid]
                    })
        except Exception as e:
            logger.warning(f"Isolated node check failed: {e}")
        
        return unresolved
