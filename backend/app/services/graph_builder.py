"""
图谱构建服务
使用 GraphStorage (Neo4j) 替代 Zep Cloud API
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from ..storage.graph_storage import GraphStorage
from ..utils.locale import t


@dataclass
class GraphInfo:
    """图谱信息"""
    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBuilderService:
    """
    图谱构建服务
    通过 GraphStorage 接口使用本地 Neo4j 构建知识图谱

    注意：实际的异步构建逻辑在 api/graph.py 的 /build 路由中内联实现，
    此类提供图谱操作的工具方法。
    """

    def __init__(self, storage: GraphStorage):
        self.storage = storage

    def create_graph(self, name: str) -> str:
        """创建图谱"""
        return self.storage.create_graph(
            name=name,
            description="writeGOD Knowledge Graph"
        )

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        """
        设置本体

        直接将 ontology 存储为 Graph 节点的 JSON 属性。
        NER 提取器会读取此本体来指导实体提取。
        """
        self.storage.set_ontology(graph_id, ontology)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None
    ) -> List[str]:
        """分批添加文本到图谱，使用并行 NER 处理"""
        total_chunks = len(chunks)

        if progress_callback:
            progress_callback(t("progress.addingChunks", count=total_chunks), 0.0)

        # 直接调用 storage 的并行批量处理
        episode_uuids = self.storage.add_text_batch(
            graph_id,
            chunks,
            batch_size=batch_size,
            progress_callback=progress_callback
        )

        return episode_uuids

    def _get_graph_info(self, graph_id: str) -> GraphInfo:
        """获取图谱信息"""
        info = self.storage.get_graph_info(graph_id)
        return GraphInfo(
            graph_id=info["graph_id"],
            node_count=info["node_count"],
            edge_count=info["edge_count"],
            entity_types=info.get("entity_types", []),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """获取完整图谱数据"""
        return self.storage.get_graph_data(graph_id)

    def delete_graph(self, graph_id: str):
        """删除图谱"""
        self.storage.delete_graph(graph_id)
