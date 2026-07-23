"""
Neo4jStorage — Neo4j Community Edition implementation of GraphStorage.

Replaces all Zep Cloud API calls with local Neo4j Cypher queries.
Includes: CRUD, NER/RE-based text ingestion, hybrid search, retry logic.
"""

import json
import time
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable

from neo4j import GraphDatabase, Session as Neo4jSession
from neo4j.exceptions import (
    TransientError,
    ServiceUnavailable,
    SessionExpired,
)

from ..config import Config
from .graph_storage import GraphStorage
from .embedding_service import EmbeddingService
from .ner_extractor import NERExtractor
from .search_service import SearchService
from . import neo4j_schema

logger = logging.getLogger('writegod.neo4j_storage')


class Neo4jStorage(GraphStorage):
    """Neo4j CE implementation of the GraphStorage interface."""

    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1  # seconds

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None,
        ner_extractor: Optional[NERExtractor] = None,
    ):
        self._uri = uri or Config.NEO4J_URI
        self._user = user or Config.NEO4J_USER
        self._password = password or Config.NEO4J_PASSWORD

        self._driver = GraphDatabase.driver(
            self._uri, auth=(self._user, self._password)
        )
        self._embedding = embedding_service or EmbeddingService()
        self._ner = ner_extractor or NERExtractor()
        self._search = SearchService(self._embedding)

        # Initialize schema (indexes, constraints)
        self._ensure_schema()

    def close(self):
        """Close the Neo4j driver connection."""
        self._driver.close()

    def _ensure_schema(self):
        """Create indexes and constraints if they don't exist."""
        with self._driver.session() as session:
            for query in neo4j_schema.ALL_SCHEMA_QUERIES:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Schema query warning (may already exist): {e}")

    # ----------------------------------------------------------------
    # Retry wrapper
    # ----------------------------------------------------------------

    def _call_with_retry(self, func, *args, **kwargs):
        """
        Execute a function with retry on Neo4j transient errors.
        Replaces 3 different retry patterns from the Zep codebase.
        """
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except (TransientError, ServiceUnavailable, SessionExpired) as e:
                last_error = e
                wait = self.RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    f"Neo4j transient error (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                    f"retrying in {wait}s: {e}"
                )
                time.sleep(wait)
            except Exception:
                raise

        raise last_error  # type: ignore

    # ----------------------------------------------------------------
    # Graph lifecycle
    # ----------------------------------------------------------------

    def create_graph(self, name: str, description: str = "") -> str:
        graph_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        def _create(tx):
            tx.run(
                """
                CREATE (g:Graph {
                    graph_id: $graph_id,
                    name: $name,
                    description: $description,
                    ontology_json: '{}',
                    created_at: $created_at
                })
                """,
                graph_id=graph_id,
                name=name,
                description=description,
                created_at=now,
            )

        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _create)

        logger.info(f"Created graph '{name}' with id {graph_id}")
        return graph_id

    def delete_graph(self, graph_id: str) -> None:
        def _delete(tx):
            # Delete all entities and their relationships
            tx.run(
                "MATCH (n {graph_id: $gid}) DETACH DELETE n",
                gid=graph_id,
            )
            # Delete graph node
            tx.run(
                "MATCH (g:Graph {graph_id: $gid}) DELETE g",
                gid=graph_id,
            )

        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _delete)
        logger.info(f"Deleted graph {graph_id}")

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]) -> None:
        def _set(tx):
            tx.run(
                """
                MATCH (g:Graph {graph_id: $gid})
                SET g.ontology_json = $ontology_json
                """,
                gid=graph_id,
                ontology_json=json.dumps(ontology, ensure_ascii=False),
            )

        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _set)

    def get_ontology(self, graph_id: str) -> Dict[str, Any]:
        with self._driver.session() as session:
            result = session.run(
                "MATCH (g:Graph {graph_id: $gid}) RETURN g.ontology_json AS oj",
                gid=graph_id,
            )
            record = result.single()
            if record and record["oj"]:
                return json.loads(record["oj"])
            return {}

    # ----------------------------------------------------------------
    # Add data (NER → nodes/edges)
    # ----------------------------------------------------------------

    def add_text(self, graph_id: str, text: str) -> str:
        """Process text: NER/RE → batch embed → create nodes/edges → return episode_id."""
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        ontology = self.get_ontology(graph_id)
        
        # Extract entities and relations
        logger.info(f"[add_text] Starting NER extraction for chunk ({len(text)} chars)...")
        extraction = self._ner.extract(text, ontology)
        entities = extraction.get("entities", [])
        relations = extraction.get("relations", [])
        ner_error = extraction.get("error")

        if ner_error:
            logger.warning(f"[add_text] NER error for this chunk: {ner_error}")

        logger.info(
            f"[add_text] NER done: {len(entities)} entities, {len(relations)} relations"
            + (f" (with error: {ner_error})" if ner_error else "")
        )

        # --- Batch embed all texts at once ---
        entity_summaries = [f"{e['name']} ({e['type']})" for e in entities]
        fact_texts = [r.get("fact", f"{r['source']} {r['type']} {r['target']}") for r in relations]
        all_texts_to_embed = entity_summaries + fact_texts

        all_embeddings: list = []
        if all_texts_to_embed:
            logger.info(f"[add_text] Batch-embedding {len(all_texts_to_embed)} texts...")
            try:
                all_embeddings = self._embedding.embed_batch(all_texts_to_embed)
            except Exception as e:
                logger.warning(f"[add_text] Batch embedding failed, falling back to empty: {e}")
                all_embeddings = [[] for _ in all_texts_to_embed]

        entity_embeddings = all_embeddings[:len(entities)]
        relation_embeddings = all_embeddings[len(entities):]
        logger.info(f"[add_text] Embedding done, writing to Neo4j...")

        with self._driver.session() as session:
            # Create episode node
            def _create_episode(tx):
                tx.run(
                    """
                    CREATE (ep:Episode {
                        uuid: $uuid,
                        graph_id: $graph_id,
                        data: $data,
                        processed: true,
                        created_at: $created_at
                    })
                    """,
                    uuid=episode_id,
                    graph_id=graph_id,
                    data=text,
                    created_at=now,
                )

            self._call_with_retry(session.execute_write, _create_episode)

            # MERGE entities (upsert by graph_id + name + primary label)
            entity_uuid_map: Dict[str, str] = {}  # name_lower -> uuid
            for idx, entity in enumerate(entities):
                ename = entity["name"]
                etype = entity["type"]
                attrs = entity.get("attributes", {})
                summary_text = entity_summaries[idx]
                embedding = entity_embeddings[idx] if idx < len(entity_embeddings) else []

                e_uuid = str(uuid.uuid4())
                entity_uuid_map[ename.lower()] = e_uuid

                def _merge_entity(tx, _uuid=e_uuid, _name=ename, _type=etype,
                                  _attrs=attrs, _embedding=embedding,
                                  _summary=summary_text, _now=now):
                    # MERGE by graph_id + lowercase name to deduplicate
                    result = tx.run(
                        """
                        MERGE (n:Entity {graph_id: $gid, name_lower: $name_lower})
                        ON CREATE SET
                            n.uuid = $uuid,
                            n.name = $name,
                            n.summary = $summary,
                            n.attributes_json = $attrs_json,
                            n.embedding = $embedding,
                            n.created_at = $now
                        ON MATCH SET
                            n.summary = CASE WHEN n.summary = '' OR n.summary IS NULL
                                THEN $summary ELSE n.summary END,
                            n.attributes_json = $attrs_json,
                            n.embedding = $embedding
                        RETURN n.uuid AS uuid
                        """,
                        gid=graph_id,
                        name_lower=_name.lower(),
                        uuid=_uuid,
                        name=_name,
                        summary=_summary,
                        attrs_json=json.dumps(_attrs, ensure_ascii=False),
                        embedding=_embedding,
                        now=_now,
                    )
                    record = result.single()
                    return record["uuid"] if record else _uuid

                actual_uuid = self._call_with_retry(session.execute_write, _merge_entity)
                entity_uuid_map[ename.lower()] = actual_uuid

                # Add entity type label
                if etype and etype != "Entity":
                    safe_etype_single = etype.replace("`", "").replace("\\", "").strip()
                    if safe_etype_single:
                        try:
                            def _add_label(tx, _name_lower=ename.lower(), _st=safe_etype_single):
                                tx.run(
                                    f"MATCH (n:Entity {{graph_id: $gid, name_lower: $nl}}) SET n:`{_st}`",
                                    gid=graph_id,
                                    nl=_name_lower,
                                )
                            self._call_with_retry(session.execute_write, _add_label)
                        except Exception as e:
                            logger.warning(f"Failed to add label '{etype}' to '{ename}': {e}")

            # Create relations
            for idx, relation in enumerate(relations):
                source_name = relation["source"]
                target_name = relation["target"]
                rtype = relation["type"]
                fact = relation["fact"]

                source_uuid = entity_uuid_map.get(source_name.lower())
                target_uuid = entity_uuid_map.get(target_name.lower())

                if not source_uuid or not target_uuid:
                    logger.warning(
                        f"Skipping relation {source_name}->{target_name}: "
                        f"entity not found in extraction results"
                    )
                    continue

                fact_embedding = relation_embeddings[idx] if idx < len(relation_embeddings) else []
                r_uuid = str(uuid.uuid4())

                def _create_relation(tx, _r_uuid=r_uuid, _source_uuid=source_uuid,
                                     _target_uuid=target_uuid, _rtype=rtype,
                                     _fact=fact, _fact_emb=fact_embedding,
                                     _episode_id=episode_id, _now=now):
                    tx.run(
                        """
                        MATCH (src:Entity {uuid: $src_uuid})
                        MATCH (tgt:Entity {uuid: $tgt_uuid})
                        CREATE (src)-[r:RELATION {
                            uuid: $uuid,
                            graph_id: $gid,
                            name: $name,
                            fact: $fact,
                            fact_embedding: $fact_embedding,
                            attributes_json: '{}',
                            episode_ids: [$episode_id],
                            created_at: $now,
                            valid_at: null,
                            invalid_at: null,
                            expired_at: null
                        }]->(tgt)
                        """,
                        src_uuid=_source_uuid,
                        tgt_uuid=_target_uuid,
                        uuid=_r_uuid,
                        gid=graph_id,
                        name=_rtype,
                        fact=_fact,
                        fact_embedding=_fact_emb,
                        episode_id=_episode_id,
                        now=_now,
                    )

                self._call_with_retry(session.execute_write, _create_relation)

        logger.info(f"[add_text] Chunk done: episode={episode_id}")
        return episode_id

    def add_text_batch(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: Optional[Callable] = None,
    ) -> List[str]:
        """Batch-add text chunks with parallel NER + sequential Neo4j write."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        total = len(chunks)
        processed = 0
        write_lock = threading.Lock()
        
        # 预缓存 ontology，避免 20 线程各查一次
        ontology = self.get_ontology(graph_id)
        
        # 第一阶段：并行 NER + 向量嵌入（不写 Neo4j）
        NER_WORKERS = 20
        
        def process_chunk_ner(idx, chunk):
            if not chunk or not chunk.strip():
                return idx, None, None
            # NER 提取
            extraction = self._ner.extract(chunk, ontology)
            entities = extraction.get("entities", [])
            relations = extraction.get("relations", [])
            ner_error = extraction.get("error")
            
            if ner_error:
                logger.warning(f"[batch NER] Chunk {idx} error: {ner_error}")
            
            # 向量嵌入
            entity_summaries = [f"{e['name']} ({e['type']})" for e in entities]
            fact_texts = [r.get("fact", f"{r['source']} {r['type']} {r['target']}") for r in relations]
            all_texts_to_embed = entity_summaries + fact_texts
            all_embeddings = []
            if all_texts_to_embed:
                try:
                    all_embeddings = self._embedding.embed_batch(all_texts_to_embed)
                except Exception as e:
                    logger.warning(f"Embedding failed: {e}")
                    all_embeddings = [[] for _ in all_texts_to_embed]
            
            entity_embeddings = all_embeddings[:len(entities)]
            relation_embeddings = all_embeddings[len(entities):]
            
            return idx, {
                'chunk': chunk,
                'entities': entities,
                'relations': relations,
                'entity_summaries': entity_summaries,
                'entity_embeddings': entity_embeddings,
                'relation_embeddings': relation_embeddings,
                'ner_error': ner_error,
            }, None
        
        logger.info(f"Starting parallel NER for {total} chunks with {NER_WORKERS} workers...")
        
        # NER + 写入一体化：NER 完成一个 chunk 就立即写入 Neo4j
        # 这样前端轮询时能实时看到节点增长
        results_map = {}
        ner_errors = []
        total_entities_extracted = 0
        total_relations_extracted = 0
        episode_ids = []
        written = 0
        write_lock = threading.Lock()
        
        def process_and_write(idx, chunk):
            """NER + 嵌入 + 立即写入 Neo4j"""
            if not chunk or not chunk.strip():
                return idx, None, None
            # NER 提取
            extraction = self._ner.extract(chunk, ontology)
            entities = extraction.get("entities", [])
            relations = extraction.get("relations", [])
            ner_error = extraction.get("error")
            
            if ner_error:
                logger.warning(f"[batch NER] Chunk {idx} error: {ner_error}")
            
            # 向量嵌入
            entity_summaries = [f"{e['name']} ({e['type']})" for e in entities]
            fact_texts = [r.get("fact", f"{r['source']} {r['type']} {r['target']}") for r in relations]
            all_texts_to_embed = entity_summaries + fact_texts
            all_embeddings = []
            if all_texts_to_embed:
                try:
                    all_embeddings = self._embedding.embed_batch(all_texts_to_embed)
                except Exception as e:
                    logger.warning(f"Embedding failed: {e}")
                    all_embeddings = [[] for _ in all_texts_to_embed]
            
            entity_embeddings = all_embeddings[:len(entities)]
            relation_embeddings = all_embeddings[len(entities):]
            
            data = {
                'chunk': chunk,
                'entities': entities,
                'relations': relations,
                'entity_summaries': entity_summaries,
                'entity_embeddings': entity_embeddings,
                'relation_embeddings': relation_embeddings,
                'ner_error': ner_error,
            }
            
            # 立即写入 Neo4j（加锁避免并发写入冲突）
            with write_lock:
                episode_id = self._write_chunk_to_neo4j(graph_id, data)
            
            return idx, data, episode_id
        
        with ThreadPoolExecutor(max_workers=NER_WORKERS) as executor:
            futures = {}
            for i, chunk in enumerate(chunks):
                future = executor.submit(process_and_write, i, chunk)
                futures[future] = i
            
            for future in as_completed(futures):
                idx, data, episode_id = future.result()
                results_map[idx] = data
                if episode_id:
                    episode_ids.append(episode_id)
                processed += 1
                if data:
                    total_entities_extracted += len(data.get('entities', []))
                    total_relations_extracted += len(data.get('relations', []))
                    if data.get('ner_error'):
                        ner_errors.append(data['ner_error'])
                if progress_callback:
                    err_count = len(ner_errors)
                    msg = f"已处理 {processed}/{total} 段"
                    if total_entities_extracted > 0:
                        msg += f"，提取 {total_entities_extracted} 个实体"
                    if total_relations_extracted > 0:
                        msg += f"，{total_relations_extracted} 个关系"
                    if err_count > 0:
                        msg += f"，{err_count} 段失败"
                    progress_callback(msg, processed / total)
                if data:
                    logger.info(f"NER+write done {processed}/{total}: {len(data['entities'])} entities, {len(data.get('relations', []))} relations")
        
        if total == 0:
            pass
        elif len(ner_errors) == total:
            logger.error(f"ALL {total} chunks failed NER extraction! No entities will be written.")
        elif ner_errors:
            logger.warning(f"{len(ner_errors)}/{total} chunks had NER errors, continuing with partial results.")
        
        return episode_ids

    def _write_chunk_to_neo4j(self, graph_id: str, data: dict) -> str:
        """将 NER 结果写入 Neo4j（单线程调用，无并发问题）"""
        episode_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        entities = data['entities']
        relations = data['relations']
        entity_summaries = data['entity_summaries']
        entity_embeddings = data['entity_embeddings']
        relation_embeddings = data['relation_embeddings']
        text = data['chunk']
        
        with self._driver.session() as session:
            def _create_episode(tx):
                tx.run(
                    """
                    CREATE (ep:Episode {
                        uuid: $uuid, graph_id: $graph_id, data: $data,
                        processed: true, created_at: $created_at
                    })
                    """,
                    uuid=episode_id, graph_id=graph_id, data=text, created_at=now,
                )
            self._call_with_retry(session.execute_write, _create_episode)

            entity_uuid_map: Dict[str, str] = {}
            for idx, entity in enumerate(entities):
                ename = entity["name"]
                etype = entity["type"]
                # 转义 etype 中的特殊字符，防止 Cypher 注入（etype 来自 LLM 输出）
                safe_etype = etype.replace("`", "").replace("\\", "").strip() or "Entity"
                attrs = entity.get("attributes", {})
                summary_text = entity_summaries[idx] if idx < len(entity_summaries) else ename
                embedding = entity_embeddings[idx] if idx < len(entity_embeddings) else []

                e_uuid = str(uuid.uuid4())
                entity_uuid_map[ename.lower()] = e_uuid

                def _merge_entity(tx, _uuid=e_uuid, _name=ename, _type=safe_etype,
                                  _attrs=attrs, _embedding=embedding,
                                  _summary=summary_text, _now=now):
                    result = tx.run(
                        """
                        MERGE (n:Entity {graph_id: $gid, name_lower: $name_lower})
                        ON CREATE SET
                            n.uuid = $uuid, n.name = $name, n.summary = $summary,
                            n.attributes_json = $attrs_json, n.created_at = $now,
                            n.embedding = $embedding
                        ON MATCH SET
                            n.summary = $summary
                        SET n:`""" + _type + """`
                        RETURN n.uuid AS uuid
                        """,
                        gid=graph_id, name_lower=_name.lower(), uuid=_uuid,
                        name=_name, summary=_summary,
                        attrs_json=json.dumps(_attrs, ensure_ascii=False),
                        embedding=_embedding, now=_now,
                    )
                    return result.single()["uuid"]

                actual_uuid = self._call_with_retry(session.execute_write, _merge_entity)
                entity_uuid_map[ename.lower()] = actual_uuid

            # Create relations
            for idx, relation in enumerate(relations):
                source = relation.get("source", "").strip()
                target = relation.get("target", "").strip()
                rtype = relation.get("type", "RELATED_TO").strip()
                fact = relation.get("fact", "")
                r_embedding = relation_embeddings[idx] if idx < len(relation_embeddings) else []

                source_uuid = entity_uuid_map.get(source.lower())
                target_uuid = entity_uuid_map.get(target.lower())
                if not source_uuid or not target_uuid:
                    continue

                r_uuid = str(uuid.uuid4())
                # 转义 rtype 中的特殊字符，防止 Cypher 注入（rtype 来自 LLM 输出）
                safe_rtype = rtype.replace("`", "").replace("\\", "").strip() or "RELATED_TO"
                def _create_relation(tx, _ruuid=r_uuid, _suuid=source_uuid, _tuuid=target_uuid,
                                     _rtype=safe_rtype, _fact=fact, _embedding=r_embedding, _now=now):
                    tx.run(
                        """
                        MATCH (s:Entity {uuid: $suuid}), (t:Entity {uuid: $tuuid})
                        MERGE (s)-[r:RELATION {uuid: $ruuid}]->(t)
                        SET r.graph_id = $gid, r.name = $rtype, r.fact = $fact, r.fact_embedding = $embedding,
                            r.fact_type = $rtype, r.created_at = $now
                        """,
                        suuid=_suuid, tuuid=_tuuid, ruuid=_ruuid, gid=graph_id,
                        rtype=_rtype, fact=_fact, embedding=_embedding, now=_now,
                    )
                self._call_with_retry(session.execute_write, _create_relation)

        logger.info(f"[write] Chunk done: {len(entities)} entities, {len(relations)} relations")
        return episode_id

    def wait_for_processing(
        self,
        episode_ids: List[str],
        progress_callback: Optional[Callable] = None,
        timeout: int = 600,
    ) -> None:
        """No-op — processing is synchronous in Neo4j."""
        if progress_callback:
            progress_callback(1.0)

    # ----------------------------------------------------------------
    # Read nodes
    # ----------------------------------------------------------------

    def get_all_nodes(self, graph_id: str, limit: int = 2000) -> List[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                RETURN n, labels(n) AS labels
                ORDER BY n.created_at DESC
                LIMIT $limit
                """,
                gid=graph_id,
                limit=limit,
            )
            return [self._node_to_dict(record["n"], record["labels"]) for record in result]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_node(self, uuid: str) -> Optional[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                "MATCH (n:Entity {uuid: $uuid}) RETURN n, labels(n) AS labels",
                uuid=uuid,
            )
            record = result.single()
            if record:
                return self._node_to_dict(record["n"], record["labels"])
            return None

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_node_edges(self, node_uuid: str) -> List[Dict[str, Any]]:
        """O(1) Cypher — NOT full scan + filter like the old Zep code."""
        def _read(tx):
            result = tx.run(
                """
                MATCH (n:Entity {uuid: $uuid})-[r:RELATION]-(m:Entity)
                RETURN r, startNode(r).uuid AS src_uuid, endNode(r).uuid AS tgt_uuid
                """,
                uuid=node_uuid,
            )
            return [
                self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_nodes_by_label(self, graph_id: str, label: str) -> List[Dict[str, Any]]:
        def _read(tx):
            safe_label = label.replace("`", "").replace("\\", "").strip()
            if not safe_label:
                return []
            # Dynamic label in query (safe — label comes from ontology, not user input)
            query = f"""
                MATCH (n:Entity:`{safe_label}` {{graph_id: $gid}})
                RETURN n, labels(n) AS labels
            """
            result = tx.run(query, gid=graph_id)
            return [self._node_to_dict(record["n"], record["labels"]) for record in result]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ----------------------------------------------------------------
    # Read edges
    # ----------------------------------------------------------------

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        def _read(tx):
            result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid
                ORDER BY r.created_at DESC
                """,
                gid=graph_id,
            )
            return [
                self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                for record in result
            ]

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ----------------------------------------------------------------
    # Search
    # ----------------------------------------------------------------

    def search(
        self,
        graph_id: str,
        query: str,
        limit: int = 10,
        scope: str = "edges",
    ):
        """
        Hybrid search — returns results matching the scope.

        Returns a dict with 'edges' and/or 'nodes' lists
        (callers like zep_tools will wrap into SearchResult).
        """
        result = {"edges": [], "nodes": [], "query": query}

        with self._driver.session() as session:
            if scope in ("edges", "both"):
                result["edges"] = self._search.search_edges(
                    session, graph_id, query, limit
                )

            if scope in ("nodes", "both"):
                result["nodes"] = self._search.search_nodes(
                    session, graph_id, query, limit
                )

        return result

    # ----------------------------------------------------------------
    # Graph info
    # ----------------------------------------------------------------

    def get_graph_info(self, graph_id: str) -> Dict[str, Any]:
        def _read(tx):
            # Count nodes
            node_result = tx.run(
                "MATCH (n:Entity {graph_id: $gid}) RETURN count(n) AS cnt",
                gid=graph_id,
            )
            node_count = node_result.single()["cnt"]

            # Count edges
            edge_result = tx.run(
                "MATCH ()-[r:RELATION {graph_id: $gid}]->() RETURN count(r) AS cnt",
                gid=graph_id,
            )
            edge_count = edge_result.single()["cnt"]

            # Distinct entity types
            label_result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                UNWIND labels(n) AS lbl
                WITH lbl WHERE lbl <> 'Entity'
                RETURN DISTINCT lbl
                """,
                gid=graph_id,
            )
            entity_types = [record["lbl"] for record in label_result]

            return {
                "graph_id": graph_id,
                "node_count": node_count,
                "edge_count": edge_count,
                "entity_types": entity_types,
            }

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        """
        Full graph dump with enriched edge format (for frontend).
        Includes derived fields: fact_type, source_node_name, target_node_name.
        """
        def _read(tx):
            # Get all nodes
            node_result = tx.run(
                """
                MATCH (n:Entity {graph_id: $gid})
                RETURN n, labels(n) AS labels
                """,
                gid=graph_id,
            )
            nodes = []
            node_map: Dict[str, str] = {}  # uuid -> name
            for record in node_result:
                nd = self._node_to_dict(record["n"], record["labels"])
                nodes.append(nd)
                node_map[nd["uuid"]] = nd["name"]

            # Get all edges with source/target node names (JOIN)
            edge_result = tx.run(
                """
                MATCH (src:Entity)-[r:RELATION {graph_id: $gid}]->(tgt:Entity)
                RETURN r, src.uuid AS src_uuid, tgt.uuid AS tgt_uuid,
                       src.name AS src_name, tgt.name AS tgt_name
                """,
                gid=graph_id,
            )
            edges = []
            for record in edge_result:
                ed = self._edge_to_dict(record["r"], record["src_uuid"], record["tgt_uuid"])
                # Enriched fields for frontend
                ed["fact_type"] = ed["name"]
                ed["source_node_name"] = record["src_name"] or ""
                ed["target_node_name"] = record["tgt_name"] or ""
                # Legacy alias
                ed["episodes"] = ed.get("episode_ids", [])
                edges.append(ed)

            return {
                "graph_id": graph_id,
                "nodes": nodes,
                "edges": edges,
                "node_count": len(nodes),
                "edge_count": len(edges),
            }

        with self._driver.session() as session:
            return self._call_with_retry(session.execute_read, _read)

    # ----------------------------------------------------------------
    # Dict conversion helpers
    # ----------------------------------------------------------------

    @staticmethod
    def _node_to_dict(node, labels: List[str]) -> Dict[str, Any]:
        """Convert Neo4j node to the standard node dict format."""
        props = dict(node)
        attrs_json = props.pop("attributes_json", "{}")
        try:
            attributes = json.loads(attrs_json) if attrs_json else {}
        except (json.JSONDecodeError, TypeError):
            attributes = {}

        # Remove internal fields from dict
        props.pop("embedding", None)
        props.pop("name_lower", None)

        return {
            "uuid": props.get("uuid", ""),
            "name": props.get("name", ""),
            "labels": [l for l in labels if l != "Entity"] if labels else [],
            "summary": props.get("summary", ""),
            "attributes": attributes,
            "created_at": props.get("created_at"),
        }

    @staticmethod
    def _edge_to_dict(rel, source_uuid: str, target_uuid: str) -> Dict[str, Any]:
        """Convert Neo4j relationship to the standard edge dict format."""
        props = dict(rel)
        attrs_json = props.pop("attributes_json", "{}")
        try:
            attributes = json.loads(attrs_json) if attrs_json else {}
        except (json.JSONDecodeError, TypeError):
            attributes = {}

        # Remove internal fields
        props.pop("fact_embedding", None)

        episode_ids = props.get("episode_ids", [])
        if episode_ids and not isinstance(episode_ids, list):
            episode_ids = [str(episode_ids)]

        return {
            "uuid": props.get("uuid", ""),
            "name": props.get("name", ""),
            "fact": props.get("fact", ""),
            "source_node_uuid": source_uuid,
            "target_node_uuid": target_uuid,
            "attributes": attributes,
            "created_at": props.get("created_at"),
            "valid_at": props.get("valid_at"),
            "invalid_at": props.get("invalid_at"),
            "expired_at": props.get("expired_at"),
            "episode_ids": episode_ids,
        }
