"""
Relation Reasoner — 关联推理引擎
分析图谱中两个节点之间的关系，给出关系类型、原因和原文证据。

用于：当用户在知识图谱中点击两个节点之间的连线时，
不仅显示关系名称，还解释"为什么它们有关系"以及"原文哪里提到过"。
"""

import logging
from typing import Dict, Any, List, Optional

from ..utils.llm_client import LLMClient
from ..storage.graph_storage import GraphStorage

logger = logging.getLogger('writegod.relation_reasoner')


class RelationReasoner:
    """
    关联推理引擎
    
    从 Neo4j 图谱中提取两个节点的上下文信息，
    调用 LLM 分析它们之间的关系类型、原因和原文证据。
    """

    def __init__(
        self,
        storage: GraphStorage,
        llm_client: Optional[LLMClient] = None
    ):
        self.storage = storage
        self.llm = llm_client or LLMClient()

    def reason(
        self,
        source_uuid: str,
        target_uuid: str,
        graph_id: str
    ) -> Dict[str, Any]:
        """
        推理两个节点之间的关联

        Args:
            source_uuid: 源节点ID
            target_uuid: 目标节点ID
            graph_id: 图谱ID

        Returns:
            {
                "relation_type": "师徒",
                "relation_category": "social",  # social / narrative / spatial / event
                "reason": "第3章中，张三正式收李四为徒，传授剑术",
                "evidence": "原文段落...",
                "confidence": 0.85,
                "source_node": {"name": "...", "type": "..."},
                "target_node": {"name": "...", "type": "..."}
            }
        """
        # 1. 获取两个节点的详细信息
        source_node = self.storage.get_node(source_uuid)
        target_node = self.storage.get_node(target_uuid)

        if not source_node or not target_node:
            raise ValueError(f"Node not found: source={source_uuid}, target={target_uuid}")

        # 2. 获取它们之间的直接边
        edges = self._get_edges_between(source_uuid, target_uuid, graph_id)

        # 3. 获取两个节点的共同上下文（共享的其他邻居节点）
        shared_context = self._get_shared_context(source_uuid, target_uuid, graph_id)

        # 4. 如果有直接边且有事实描述，直接使用
        if edges:
            best_edge = max(edges, key=lambda e: len(e.get('fact', '')))
            return {
                "relation_type": best_edge.get('name', 'RELATED_TO'),
                "relation_category": self._categorize_relation(best_edge.get('name', '')),
                "reason": best_edge.get('fact', ''),
                "evidence": best_edge.get('fact', ''),
                "confidence": 0.95,
                "source_node": {
                    "name": source_node.get('name', ''),
                    "type": self._get_entity_type(source_node)
                },
                "target_node": {
                    "name": target_node.get('name', ''),
                    "type": self._get_entity_type(target_node)
                }
            }

        # 5. 没有直接边，用 LLM 分析共同上下文
        return self._llm_reasoning(source_node, target_node, shared_context, graph_id)

    def _get_edges_between(
        self,
        source_uuid: str,
        target_uuid: str,
        graph_id: str
    ) -> List[Dict[str, Any]]:
        """获取两个节点之间的所有边"""
        edges = []
        all_edges = self.storage.get_all_edges(graph_id)
        for edge in all_edges:
            s = edge.get('source_node_uuid', '')
            t = edge.get('target_node_uuid', '')
            if (s == source_uuid and t == target_uuid) or (s == target_uuid and t == source_uuid):
                edges.append(edge)
        return edges

    def _get_shared_context(
        self,
        source_uuid: str,
        target_uuid: str,
        graph_id: str
    ) -> Dict[str, Any]:
        """获取两个节点的共同上下文信息"""
        # 获取源节点的所有边
        source_edges = self.storage.get_node_edges(source_uuid)
        target_edges = self.storage.get_node_edges(target_uuid)

        # 找出共同关联的节点
        source_neighbors = set()
        for e in source_edges:
            s = e.get('source_node_uuid', '')
            t = e.get('target_node_uuid', '')
            if s == source_uuid:
                source_neighbors.add(t)
            else:
                source_neighbors.add(s)

        target_neighbors = set()
        for e in target_edges:
            s = e.get('source_node_uuid', '')
            t = e.get('target_node_uuid', '')
            if s == target_uuid:
                target_neighbors.add(t)
            else:
                target_neighbors.add(s)

        shared = source_neighbors & target_neighbors
        shared_node_details = []
        for nid in shared:
            node = self.storage.get_node(nid)
            if node:
                shared_node_details.append(node)

        return {
            "source_node_edges": source_edges[:20],
            "target_node_edges": target_edges[:20],
            "shared_nodes": shared_node_details
        }

    def _llm_reasoning(
        self,
        source_node: Dict[str, Any],
        target_node: Dict[str, Any],
        shared_context: Dict[str, Any],
        graph_id: str
    ) -> Dict[str, Any]:
        """用 LLM 分析两个节点的关联"""
        src_name = source_node.get('name', 'Unknown')
        src_type = self._get_entity_type(source_node)
        tgt_name = target_node.get('name', 'Unknown')
        tgt_type = self._get_entity_type(target_node)

        # 构建上下文描述
        context_parts = []
        if shared_context['shared_nodes']:
            shared_names = [n.get('name', '?') for n in shared_context['shared_nodes']]
            context_parts.append(f"共同关联：{', '.join(shared_names)}")

        context_text = "\n".join(context_parts) if context_parts else "无直接共同关联"

        prompt = f"""分析小说知识图谱中两个节点之间的关联：

节点A：{src_name}（类型：{src_type}）
节点B：{tgt_name}（类型：{tgt_type}）

上下文信息：
{context_text}

请分析这两个节点可能存在的叙事关系。输出JSON格式：
{{
    "relation_type": "关系类型（如：师徒、父子、敌对、盟友、爱恋、位于、持有、参与、导致等）",
    "relation_category": "关系类别（social/spatial/narrative/event）",
    "reason": "关系原因分析",
    "confidence": 0.0-1.0
}}

注意：如果无明显关联，confidence 应低于 0.3。不要强行制造关联。"""

        messages = [
            {
                "role": "system",
                "content": "你是一个小说叙事关系分析专家。你严格基于已知信息分析角色/事件/地点之间的关联，不编造不存在的关系。"
            },
            {"role": "user", "content": prompt}
        ]

        try:
            result = self.llm.chat_json(messages=messages, temperature=0.3, max_tokens=1024)
            return {
                "relation_type": result.get('relation_type', 'UNKNOWN'),
                "relation_category": result.get('relation_category', 'unknown'),
                "reason": result.get('reason', ''),
                "evidence": "基于共同上下文推断",
                "confidence": result.get('confidence', 0.5),
                "source_node": {"name": src_name, "type": src_type},
                "target_node": {"name": tgt_name, "type": tgt_type}
            }
        except Exception as e:
            logger.error(f"LLM reasoning failed: {e}")
            return {
                "relation_type": "UNKNOWN",
                "relation_category": "unknown",
                "reason": "无法自动分析关联",
                "evidence": "",
                "confidence": 0.0,
                "source_node": {"name": src_name, "type": src_type},
                "target_node": {"name": tgt_name, "type": tgt_type}
            }

    def _get_entity_type(self, node: Dict[str, Any]) -> str:
        """获取节点的实体类型"""
        labels = node.get('labels', [])
        for label in labels:
            if label not in ['Entity', 'Node']:
                return label
        return 'Unknown'

    def _categorize_relation(self, relation_name: str) -> str:
        """对关系类型进行分类"""
        social = ['PARENT_OF', 'CHILD_OF', 'SIBLING_OF', 'MARRIED_TO', 'MASTER_OF',
                  'APPRENTICE_OF', 'FRIEND_OF', 'ALLY_OF', 'ENEMY_OF', 'BETRAYED',
                  'LOVES', 'BELONGS_TO']
        narrative = ['KILLED', 'SAVED', 'FIGHTS', 'DEFEATED']
        spatial = ['LOCATED_AT', 'HOLDS']
        event = ['PARTICIPATES_IN', 'CAUSES', 'FOLLOWS']

        upper = relation_name.upper()
        if upper in social:
            return 'social'
        if upper in narrative:
            return 'narrative'
        if upper in spatial:
            return 'spatial'
        if upper in event:
            return 'event'
        return 'unknown'
