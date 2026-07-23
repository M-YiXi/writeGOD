"""
NER/RE Extractor - entity and relation extraction via local LLM

Replaces Zep Cloud's built-in NER/RE pipeline.
Uses LLMClient.chat_json() with a structured prompt to extract
entities and relations from text chunks, guided by the graph's ontology.
"""

import logging
from typing import Dict, Any, List, Optional

from ..utils.llm_client import LLMClient

logger = logging.getLogger('writegod.ner_extractor')

# System prompt template for NER/RE extraction
_SYSTEM_PROMPT = """You are a Named Entity Recognition and Relation Extraction system specialized in **Chinese novels and literary texts**.
Given a text and an ontology (entity types + relation types), extract all entities and relations.

ONTOLOGY:
{ontology_description}

RULES:
1. Extract entities matching the ontology types. If an entity doesn't fit any type, use "Entity" as fallback type.
2. Normalize entity names: strip whitespace, use canonical form.
3. For Character entities, ALWAYS extract these attributes if available: age, gender, title/alias.
4. For Event entities, ALWAYS extract: chapter (which chapter/part it occurs in), outcome if known.
5. Each entity must have: name, type, attributes.
6. CRITICAL - Extract ALL relations between entities, even if the relation type is not in the ontology. Use the closest matching type or "RELATED_TO" as fallback.
7. CRITICAL - The fact sentence MUST be a direct quote or close paraphrase from the source text. Do not fabricate relationships.
8. CRITICAL - Relations are VERY IMPORTANT. Always look for: family relations, master-disciple, friendship, enmity, alliance, location, possession, events/actions between characters.
9. Only extract what is explicitly stated or strongly implied.
10. If no entities found, return empty lists. But ALWAYS try to find relations between any entities mentioned.

Return ONLY valid JSON in this exact format:
{{
  "entities": [
    {{"name": "...", "type": "...", "attributes": {{"key": "value"}}}}
  ],
  "relations": [
    {{"source": "...", "target": "...", "type": "...", "fact": "..."}}
  ]
}}"""

_USER_PROMPT = """Extract entities and relations from the following novel text. For each character, note their title/alias and role.
If the text mentions a character's action or dialogue that implies a relationship, extract it as a relation.

Text:
{text}"""


class NERExtractor:
    """Extract entities and relations from text using local LLM."""

    def __init__(self, llm_client: Optional[LLMClient] = None, max_retries: int = 2):
        self.llm = llm_client or LLMClient()
        self.max_retries = max_retries

    def extract(self, text: str, ontology: Dict[str, Any]) -> Dict[str, Any]:
        """Extract entities and relations from text, guided by ontology.

        Returns a dict with keys:
          - entities: list of entity dicts
          - relations: list of relation dicts
          - error: Optional[str] - error message if extraction failed, None on success
          - error_type: Optional[str] - 'empty_text' | 'llm_failed' | None
        """
        if not text or not text.strip():
            return {"entities": [], "relations": [], "error": None, "error_type": "empty_text"}

        ontology_desc = self._format_ontology(ontology)
        system_msg = _SYSTEM_PROMPT.format(ontology_description=ontology_desc)
        # 添加抑制思考的指令
        system_msg += "\n\nIMPORTANT: Do NOT think or reason. Directly output the JSON result immediately."
        user_msg = _USER_PROMPT.format(text=text.strip())

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self.llm.chat_json(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=8192,
                    disable_thinking=True
                )
                validated = self._validate_and_clean(result, ontology)
                validated["error"] = None
                validated["error_type"] = None
                return validated

            except ValueError as e:
                last_error = e
                logger.warning(
                    f"NER extraction failed (attempt {attempt + 1}): invalid JSON - {e}"
                )
            except Exception as e:
                last_error = e
                logger.error(f"NER extraction error: {e}")
                if attempt >= self.max_retries:
                    break

        error_msg = f"NER extraction failed after {self.max_retries + 1} attempts: {last_error}"
        logger.error(error_msg)
        # 不再静默返回空：带错误信息返回，让上层能感知失败
        return {
            "entities": [],
            "relations": [],
            "error": error_msg,
            "error_type": "llm_failed",
        }

    def _format_ontology(self, ontology: Dict[str, Any]) -> str:
        """Format ontology dict into readable text for the LLM prompt."""
        parts = []

        entity_types = ontology.get("entity_types", [])
        if entity_types:
            parts.append("Entity Types:")
            for et in entity_types:
                if isinstance(et, dict):
                    name = et.get("name", str(et))
                    desc = et.get("description", "")
                    attrs = et.get("attributes", [])
                    line = f"  - {name}"
                    if desc:
                        line += f": {desc}"
                    if attrs:
                        attr_names = [a.get("name", str(a)) if isinstance(a, dict) else str(a) for a in attrs]
                        line += f" (attributes: {', '.join(attr_names)})"
                    parts.append(line)
                else:
                    parts.append(f"  - {et}")

        relation_types = ontology.get("relation_types", ontology.get("edge_types", []))
        if relation_types:
            parts.append("\nRelation Types:")
            for rt in relation_types:
                if isinstance(rt, dict):
                    name = rt.get("name", str(rt))
                    desc = rt.get("description", "")
                    source_targets = rt.get("source_targets", [])
                    line = f"  - {name}"
                    if desc:
                        line += f": {desc}"
                    if source_targets:
                        st_strs = [f"{st.get('source', '?')} -> {st.get('target', '?')}" for st in source_targets]
                        line += f" ({', '.join(st_strs)})"
                    parts.append(line)
                else:
                    parts.append(f"  - {rt}")

        if not parts:
            parts.append("No specific ontology defined. Extract all entities and relations you find.")

        return "\n".join(parts)

    def _validate_and_clean(
        self, result: Dict[str, Any], ontology: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate and normalize LLM output."""
        entities = result.get("entities", [])
        relations = result.get("relations", [])

        # Get valid type names from ontology
        valid_entity_types = set()
        for et in ontology.get("entity_types", []):
            if isinstance(et, dict):
                valid_entity_types.add(et.get("name", "").strip())
            else:
                valid_entity_types.add(str(et).strip())

        valid_relation_types = set()
        for rt in ontology.get("relation_types", ontology.get("edge_types", [])):
            if isinstance(rt, dict):
                valid_relation_types.add(rt.get("name", "").strip())
            else:
                valid_relation_types.add(str(rt).strip())

        # Clean entities
        cleaned_entities = []
        seen_names = set()
        for entity in entities:
            if not isinstance(entity, dict):
                continue
            name = str(entity.get("name", "")).strip()
            etype = str(entity.get("type", "Entity")).strip()
            if not name:
                continue

            # Deduplicate by normalized name
            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # If ontology has types, warn but keep entities with unknown types
            if valid_entity_types and etype not in valid_entity_types:
                logger.debug(f"Entity '{name}' has type '{etype}' not in ontology, keeping anyway")

            cleaned_entities.append({
                "name": name,
                "type": etype,
                "attributes": entity.get("attributes", {}),
            })

        # Clean relations
        cleaned_relations = []
        entity_names_lower = {e["name"].lower() for e in cleaned_entities}
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("source", "")).strip()
            target = str(relation.get("target", "")).strip()
            rtype = str(relation.get("type", "RELATED_TO")).strip()
            fact = str(relation.get("fact", "")).strip()

            if not source or not target:
                continue

            # Ensure source and target entities exist
            # (they might not if LLM hallucinated a relation without the entity)
            if source.lower() not in entity_names_lower:
                cleaned_entities.append({
                    "name": source,
                    "type": "Entity",
                    "attributes": {},
                })
                entity_names_lower.add(source.lower())

            if target.lower() not in entity_names_lower:
                cleaned_entities.append({
                    "name": target,
                    "type": "Entity",
                    "attributes": {},
                })
                entity_names_lower.add(target.lower())

            cleaned_relations.append({
                "source": source,
                "target": target,
                "type": rtype,
                "fact": fact or f"{source} {rtype} {target}",
            })

        return {
            "entities": cleaned_entities,
            "relations": cleaned_relations,
        }
