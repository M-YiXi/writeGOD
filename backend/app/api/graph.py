"""
图谱相关API路由
采用项目上下文机制，服务端持久化状态
"""

import os
import json
import time
import queue
import traceback
import threading
from flask import request, jsonify, Response
from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..utils.locale import t, get_locale, set_locale
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# 获取日志器
logger = get_logger('writegod.api')


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== 项目管理接口 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    获取项目详情
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所有项目
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    删除项目
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": t('api.projectDeleteFailed', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "message": t('api.projectDeleted', id=project_id)
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置项目状态（用于重新构建图谱）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    # 重置到本体已生成状态
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": t('api.projectReset', id=project_id),
        "data": project.to_dict()
    })


# ============== 接口1：上传文件并生成本体 ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    接口1：上传文件，分析生成本体定义
    
    请求方式：multipart/form-data
    
    参数：
        files: 上传的文件（PDF/MD/TXT），可多个
        simulation_requirement: 模拟需求描述（必填）
        project_name: 项目名称（可选）
        additional_context: 额外说明（可选）
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== 开始生成本体定义 ===")
        
        # 获取参数
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(f"项目名称: {project_name}")
        logger.debug(f"模拟需求: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationRequirement')
            }), 400
        
        # 获取上传的文件
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": t('api.requireFileUpload')
            }), 400
        
        # 创建项目
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"创建项目: {project.project_id}")
        
        # 保存文件并提取文本
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # 保存文件到项目目录
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                # 提取文本
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t('api.noDocProcessed')
            }), 400
        
        # 保存提取的文本
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文本提取完成，共 {len(all_text)} 字符")
        
        # 生成本体
        logger.info("调用 LLM 生成本体定义...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )
        
        # 保存本体到项目
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"本体生成完成: {entity_count} 个实体类型, {edge_count} 个关系类型")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== 本体生成完成 === 项目ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        logger.error(f"本体生成失败: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 接口2：构建图谱 ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    接口2：根据project_id构建图谱
    
    请求（JSON）：
        {
            "project_id": "proj_xxxx",  // 必填，来自接口1
            "graph_name": "图谱名称",    // 可选
            "chunk_size": 500,          // 可选，默认500
            "chunk_overlap": 50         // 可选，默认50
        }
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "图谱构建任务已启动"
            }
        }
    """
    try:
        logger.info("=== 开始构建图谱 ===")
        

        
        # 解析请求
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"请求参数: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": t('api.requireProjectId')
            }), 400
        
        # 获取项目
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=project_id)
            }), 404

        # 检查项目状态
        force = data.get('force', False)  # 强制重新构建
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": t('api.ontologyNotGenerated')
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": t('api.graphBuilding'),
                "task_id": project.graph_build_task_id
            }), 400
        
        # 如果强制重建，重置状态
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        # 获取配置
        graph_name = data.get('graph_name', project.name or 'writeGOD Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        
        # 更新项目配置
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        
        # 获取提取的文本
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 400
        
        # 获取本体
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": t('api.ontologyNotFound')
            }), 400
        
        # 创建异步任务
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"构建图谱: {graph_name}")
        logger.info(f"创建图谱构建任务: task_id={task_id}, project_id={project_id}")
        
        # 更新项目状态
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        # Capture locale before spawning background thread
        current_locale = get_locale()

        # 启动后台任务
        def build_task():
            set_locale(current_locale)
            build_logger = get_logger('writegod.build')
            try:
                build_logger.info(f"[{task_id}] 开始构建图谱...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message=t('progress.initGraphService')
                )
                
                # 创建图谱构建服务（使用本地 Neo4j）
                from ..storage.neo4j_storage import Neo4jStorage
                storage = Neo4jStorage()
                builder = GraphBuilderService(storage=storage)
                
                # 分块
                task_manager.update_task(
                    task_id,
                    message=t('progress.textChunking'),
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text, 
                    chunk_size=chunk_size, 
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)
                
                # 创建图谱
                task_manager.update_task(
                    task_id,
                    message=t('progress.creatingZepGraph'),
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                
                # 更新项目的graph_id
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                
                # 设置本体
                task_manager.update_task(
                    task_id,
                    message=t('progress.settingOntology'),
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                # 添加文本（progress_callback 签名是 (msg, progress_ratio)）
                total_entities_so_far = [0]  # 用 list 包装以便闭包修改
                total_relations_so_far = [0]
                total_ner_errors = [0]
                
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 80)  # 15% - 95%
                    # NER+写入一体化：每个 chunk 处理完就写入 Neo4j
                    # 每次回调都从 Neo4j 查实时统计，前端能看到节点实时增长
                    try:
                        live_stats = storage.get_graph_info(graph_id)
                        total_entities_so_far[0] = live_stats.get("node_count", 0)
                        total_relations_so_far[0] = live_stats.get("edge_count", 0)
                    except Exception:
                        pass
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress,
                        progress_detail={
                            "chunks_processed": int(progress_ratio * total_chunks),
                            "total_chunks": total_chunks,
                            "graph_id": graph_id,
                            "entities": total_entities_so_far[0],
                            "relations": total_relations_so_far[0],
                        }
                    )
                
                task_manager.update_task(
                    task_id,
                    message=t('progress.addingChunks', count=total_chunks),
                    progress=15
                )
                
                episode_uuids = builder.add_text_batches(
                    graph_id, 
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )
                
                # 等待处理完成（Neo4j 同步处理，无需等待）
                task_manager.update_task(
                    task_id,
                    message='处理完成',
                    progress=55
                )
                
                # 获取图谱数据
                task_manager.update_task(
                    task_id,
                    message=t('progress.fetchingGraphData'),
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                
                # 更新项目状态
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] 图谱构建完成: graph_id={graph_id}, 节点={node_count}, 边={edge_count}")
                
                # 检测：如果节点数为0，标记为警告状态（而非假完成）
                if node_count == 0:
                    warning_msg = (
                        f"图谱构建完成但未提取到任何实体（共 {total_chunks} 段文本）。"
                        "可能原因：LLM API 调用失败、API Key 未配置或余额不足、"
                        "网络超时、或文本内容无法提取实体。请检查后端日志和 API 配置。"
                    )
                    build_logger.warning(f"[{task_id}] {warning_msg}")
                    task_manager.update_task(
                        task_id,
                        status=TaskStatus.COMPLETED_WITH_WARNING,
                        message=warning_msg,
                        progress=100,
                        result={
                            "project_id": project_id,
                            "graph_id": graph_id,
                            "node_count": node_count,
                            "edge_count": edge_count,
                            "chunk_count": total_chunks,
                            "warning": warning_msg,
                        }
                    )
                else:
                    # 完成
                    task_manager.update_task(
                        task_id,
                        status=TaskStatus.COMPLETED,
                        message=t('progress.graphBuildComplete'),
                        progress=100,
                        result={
                            "project_id": project_id,
                            "graph_id": graph_id,
                            "node_count": node_count,
                            "edge_count": edge_count,
                            "chunk_count": total_chunks
                        }
                    )
                
            except Exception as e:
                # 更新项目状态为失败
                build_logger.error(f"[{task_id}] 图谱构建失败: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=t('progress.buildFailed', error=str(e)),
                    error=traceback.format_exc()
                )
        
        # 启动后台线程
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": t('api.graphBuildStarted', taskId=task_id)
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ============== 任务查询接口 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    查询任务状态
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": t('api.taskNotFound', id=task_id)
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    列出所有任务
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== SSE 流式进度推送 ==============

@graph_bp.route('/build/stream/<task_id>', methods=['GET'])
def build_stream(task_id: str):
    """
    SSE 端点：流式推送图谱构建进度
    
    每当 TaskManager.update_task 被调用时，推送一个 SSE 事件。
    任务到达终态（completed/completed_with_warning/failed）后推送最终事件并关闭连接。
    
    客户端用 EventSource 连接：
      const es = new EventSource('/api/graph/build/stream/' + taskId)
      es.onmessage = (e) => { const data = JSON.parse(e.data) ... }
    """
    from ..models.task import TERMINAL_STATUSES
    
    task_manager = TaskManager()
    task = task_manager.get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": t('api.taskNotFound', id=task_id)
        }), 404

    def generate():
        # 订阅事件队列
        q = task_manager.subscribe(task_id)
        if q is None:
            yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
            return

        try:
            # 先推送当前状态
            current = task_manager.get_task(task_id)
            if current:
                yield f"data: {json.dumps(current.to_dict(), ensure_ascii=False)}\n\n"

            # 如果任务已经在终态，直接结束
            if current and current.status in TERMINAL_STATUSES:
                return

            # 持续监听事件队列
            while True:
                try:
                    event_data = q.get(timeout=15)  # 15秒超时
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    # 检查是否到达终态
                    if event_data.get("status") in [s.value for s in TERMINAL_STATUSES]:
                        break

                except queue.Empty:
                    # queue.Empty 超时，发送心跳保持连接
                    yield ": heartbeat\n\n"

                    # 检查任务是否还存在或已到终态
                    current = task_manager.get_task(task_id)
                    if current and current.status in TERMINAL_STATUSES:
                        yield f"data: {json.dumps(current.to_dict(), ensure_ascii=False)}\n\n"
                        break
                    if current is None:
                        break

        finally:
            task_manager.unsubscribe(task_id, q)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # nginx 不缓冲
            'Connection': 'keep-alive',
        }
    )


# ============== 图谱数据接口 ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    获取图谱数据（节点和边）
    """
    try:
        from ..storage.neo4j_storage import Neo4jStorage
        storage = Neo4jStorage()
        builder = GraphBuilderService(storage=storage)
        graph_data = builder.get_graph_data(graph_id)
        
        return jsonify({
            "success": True,
            "data": graph_data
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    删除Zep图谱
    """
    try:
        from ..storage.neo4j_storage import Neo4jStorage
        storage = Neo4jStorage()
        builder = GraphBuilderService(storage=storage)
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": t('api.graphDeleted', id=graph_id)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
        }), 500


# ============== 关联推理接口 ==============

@graph_bp.route('/relation/reason', methods=['POST'])
def reason_relation():
    """推理两个节点之间的关联关系"""
    try:
        data = request.get_json(force=True)
        src = data.get('source_uuid')
        tgt = data.get('target_uuid')
        gid = data.get('graph_id')
        if not all([src, tgt, gid]):
            return jsonify({"success": False, "error": "缺少参数"}), 400
        from ..storage.neo4j_storage import Neo4jStorage
        from ..services.relation_reasoner import RelationReasoner
        storage = Neo4jStorage()
        reasoner = RelationReasoner(storage=storage)
        result = reasoner.reason(src, tgt, gid)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 逻辑检测接口 ==============

@graph_bp.route('/plot/check', methods=['POST'])
def check_plot():
    """检测逻辑漏洞和未回收伏笔"""
    try:
        data = request.get_json(force=True)
        gid = data.get('graph_id')
        if not gid:
            return jsonify({"success": False, "error": "缺少 graph_id"}), 400
        from ..storage.neo4j_storage import Neo4jStorage
        from ..services.plot_checker import PlotChecker
        storage = Neo4jStorage()
        checker = PlotChecker(storage=storage)
        holes = checker.check_holes(gid)
        unresolved = checker.check_unresolved(gid)
        return jsonify({"success": True, "data": {"holes": holes, "unresolved": unresolved}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 素材汇总接口（入口一） ==============

@graph_bp.route('/outline/summary', methods=['POST'])
def outline_summary():
    """生成素材汇总报告"""
    try:
        data = request.get_json(force=True)
        gid = data.get('graph_id')
        if not gid:
            return jsonify({"success": False, "error": "缺少 graph_id"}), 400
        from ..storage.neo4j_storage import Neo4jStorage
        from ..services.graph_tools import GraphToolsService
        storage = Neo4jStorage()
        tools = GraphToolsService(storage=storage)
        stats = tools.get_graph_statistics(gid)
        return jsonify({"success": True, "data": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 角色对话接口（入口二） ==============

@graph_bp.route('/character/chat', methods=['POST'])
def character_chat():
    """与小说角色对话"""
    try:
        data = request.get_json(force=True)
        character_name = data.get('character_name')
        user_message = data.get('message')
        graph_id = data.get('graph_id')
        if not all([character_name, user_message, graph_id]):
            return jsonify({"success": False, "error": "缺少参数"}), 400

        from ..storage.neo4j_storage import Neo4jStorage
        from ..utils.llm_client import LLMClient

        storage = Neo4jStorage()
        llm = LLMClient()

        # 从图谱查找角色信息
        all_nodes = storage.get_all_nodes(graph_id)
        char_node = None
        for node in all_nodes:
            if node.get('name', '') == character_name:
                char_node = node
                break

        if not char_node:
            # 模糊匹配
            for node in all_nodes:
                if character_name in node.get('name', ''):
                    char_node = node
                    break

        if not char_node:
            return jsonify({"success": False, "error": f"未找到角色：{character_name}"}), 404

        # 构建角色人设提示词
        char_name = char_node.get('name', character_name)
        char_attrs = char_node.get('attributes', {})
        char_summary = char_node.get('summary', '')

        # 查找该角色的关系
        relations = []
        for e in storage.get_all_edges(graph_id):
            if e.get('source_node_uuid') == char_node.get('uuid', ''):
                target = storage.get_node(e.get('target_node_uuid', ''))
                if target:
                    relations.append(f"- 与 {target.get('name', '某人')} 的关系：{e.get('fact', e.get('name', '有关联'))}")
            elif e.get('target_node_uuid') == char_node.get('uuid', ''):
                source = storage.get_node(e.get('source_node_uuid', ''))
                if source:
                    relations.append(f"- 与 {source.get('name', '某人')} 的关系：{e.get('fact', e.get('name', '有关联'))}")

        relation_text = "\n".join(relations[:10]) if relations else "暂无已知关系"

        # 向量检索：查找与用户提问相关的记忆片段（原文段落）
        memory_references = []
        try:
            from ..storage.search_service import SearchService
            from ..storage.embedding_service import EmbeddingService
            embedding_svc = EmbeddingService()
            search_svc = SearchService(embedding_svc)
            # 用用户提问检索相关 facts
            with storage._driver.session() as session:
                edge_results = search_svc.search_edges(session, graph_id, user_message, limit=5)
                for r in edge_results:
                    fact = r.get("fact", "")
                    if fact:
                        memory_references.append(fact)
        except Exception as e:
            logger.warning(f"Memory retrieval for character chat failed: {e}")

        memory_text = "\n".join(f"- {m}" for m in memory_references[:5]) if memory_references else "暂无相关记忆片段"

        system_prompt = f"""你正在扮演小说角色【{char_name}】。你必须严格基于以下已知信息进行回答。

## 角色档案
姓名：{char_name}
属性：{json.dumps(char_attrs, ensure_ascii=False)}
简介：{char_summary}

## 已知关系
{relation_text}

## 相关记忆片段（从原文中检索）
{memory_text}

## 对话规则
1. 只回答与角色已知信息相关的问题
2. 对于书中未提及的内容，回答"这在我的故事中并未提及"
3. 保持角色的性格特征和说话风格
4. 回答须引用原文依据

## 用户提问
{user_message}"""

        response = llm.chat([
            {"role": "system", "content": system_prompt}
        ])

        return jsonify({
            "success": True,
            "data": {
                "character_name": char_name,
                "response": response,
                "references": memory_references,
                "character_info": {
                    "name": char_name,
                    "attributes": char_attrs,
                    "summary": char_summary
                }
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 多视角评论接口（入口二） ==============

@graph_bp.route('/reader/comments', methods=['POST'])
def reader_comments():
    """生成多视角读者评论"""
    try:
        data = request.get_json(force=True)
        topic = data.get('topic', '')
        graph_id = data.get('graph_id')
        if not topic or not graph_id:
            return jsonify({"success": False, "error": "缺少参数"}), 400

        from ..utils.llm_client import LLMClient
        llm = LLMClient()

        reader_profiles = [
            {"name": "文学系学生", "perspective": "关注文学手法和叙事技巧"},
            {"name": "高中语文老师", "perspective": "关注教育意义和价值观"},
            {"name": "文化记者", "perspective": "关注文化现象和社会影响"},
            {"name": "网络小说作者", "perspective": "关注写作技巧和情节结构"},
            {"name": "普通读者", "perspective": "关注阅读体验和情感共鸣"},
        ]

        comments = []
        for profile in reader_profiles:
            prompt = f"""你是一位{profile['name']}。请从{profile['perspective']}的角度，对以下小说内容发表一段简短的评论（50-100字）。

评论主题：{topic}

要求：
1. 从你的身份视角出发
2. 简短有力，有自己的观点
3. 不要套话，要像真实读者的评论"""

            response = llm.chat([
                {"role": "system", "content": f"你是一个{profile['name']}，请基于身份发表评论。"},
                {"role": "user", "content": prompt}
            ], temperature=0.7)

            comments.append({
                "reader_type": profile['name'],
                "perspective": profile['perspective'],
                "comment": response.strip()
            })

        return jsonify({
            "success": True,
            "data": {"topic": topic, "comments": comments}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 角色列表接口（供选角对话用） ==============

@graph_bp.route('/characters/<graph_id>', methods=['GET'])
def get_characters(graph_id: str):
    """获取图谱中的角色节点列表，供前端选角对话使用"""
    try:
        from ..storage.neo4j_storage import Neo4jStorage
        from ..services.entity_reader import EntityReader

        storage = Neo4jStorage()
        reader = EntityReader(storage=storage)

        # 获取所有有意义的实体节点
        filtered = reader.filter_defined_entities(graph_id, enrich_with_edges=False)

        # 按类型分组，标记角色类节点
        char_labels = {"Person", "Character", "Miss", "YoungMaster", "Madam",
                       "Master", "HousekeeperMadam", "Maid", "YoungLady"}

        characters = []
        other_entities = []
        for entity in filtered.entities:
            entity_type = entity.get_entity_type()
            item = {
                "uuid": entity.uuid,
                "name": entity.name,
                "type": entity_type,
                "summary": entity.summary,
                "attributes": entity.attributes,
                "is_character": entity_type in char_labels if entity_type else False,
            }
            if item["is_character"]:
                characters.append(item)
            else:
                other_entities.append(item)

        return jsonify({
            "success": True,
            "data": {
                "characters": characters,
                "other_entities": other_entities,
                "total": len(characters) + len(other_entities)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 智能问答接口（向量+LLM） ==============

@graph_bp.route('/qa', methods=['POST'])
def intelligent_qa():
    """智能问答：自然语言查询，向量检索相关段落 + LLM 总结回答"""
    try:
        data = request.get_json(force=True)
        question = data.get('question', '').strip()
        graph_id = data.get('graph_id')
        if not question or not graph_id:
            return jsonify({"success": False, "error": "缺少 question 或 graph_id"}), 400

        from ..storage.neo4j_storage import Neo4jStorage
        from ..storage.search_service import SearchService
        from ..storage.embedding_service import EmbeddingService
        from ..utils.llm_client import LLMClient

        storage = Neo4jStorage()
        embedding_svc = EmbeddingService()
        search_svc = SearchService(embedding_svc)
        llm = LLMClient()

        # 向量检索相关边（facts）和节点
        with storage._driver.session() as session:
            edge_results = search_svc.search_edges(session, graph_id, question, limit=10)
            node_results = search_svc.search_nodes(session, graph_id, question, limit=10)

        # 构建上下文
        context_parts = []
        for r in edge_results:
            fact = r.get("fact", "")
            if fact:
                context_parts.append(f"- {fact}")
        for n in node_results:
            name = n.get("name", "")
            summary = n.get("summary", "")
            if summary:
                context_parts.append(f"- {name}: {summary}")

        context = "\n".join(context_parts[:15]) if context_parts else "未找到相关内容"

        system_prompt = f"""你是一个小说知识助手。基于以下从知识图谱中检索到的信息回答用户问题。
如果检索信息不足以回答，请明确说明"根据已有信息无法回答"。

## 检索到的相关信息
{context}

## 回答规则
1. 只基于检索到的信息回答
2. 引用具体的原文依据
3. 如果信息有矛盾，指出矛盾点"""

        response = llm.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question}
        ])

        return jsonify({
            "success": True,
            "data": {
                "question": question,
                "answer": response,
                "references": context_parts[:5]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 伏笔追踪接口（向量+图谱） ==============

@graph_bp.route('/foreshadow/track', methods=['POST'])
def track_foreshadow():
    """伏笔追踪：向量找相似线索 + 图谱看是否回收，返回未回收伏笔列表"""
    try:
        data = request.get_json(force=True)
        graph_id = data.get('graph_id')
        if not graph_id:
            return jsonify({"success": False, "error": "缺少 graph_id"}), 400

        from ..storage.neo4j_storage import Neo4jStorage
        from ..utils.llm_client import LLMClient

        storage = Neo4jStorage()
        llm = LLMClient()

        all_nodes = storage.get_all_nodes(graph_id)
        all_edges = storage.get_all_edges(graph_id)

        # 统计每个节点的关联边数
        edge_count = {}
        for e in all_edges:
            src = e.get('source_node_uuid', '')
            tgt = e.get('target_node_uuid', '')
            edge_count[src] = edge_count.get(src, 0) + 1
            edge_count[tgt] = edge_count.get(tgt, 0) + 1

        # 找出度数低的节点（可能是伏笔）
        foreshadows = []
        for node in all_nodes:
            nid = node.get('uuid', '')
            count = edge_count.get(nid, 0)
            if count <= 2:  # 度数 <= 2 的节点可能是伏笔
                name = node.get('name', 'Unknown')
                ntype = 'Unknown'
                for label in node.get('labels', []):
                    if label not in ['Entity', 'Node']:
                        ntype = label
                        break

                # 获取该节点的相关 facts
                related_facts = []
                for e in all_edges:
                    if e.get('source_node_uuid') == nid or e.get('target_node_uuid') == nid:
                        fact = e.get('fact', '')
                        if fact:
                            related_facts.append(fact)

                # 用 LLM 判断是否为伏笔以及是否已回收
                if related_facts:
                    facts_text = "\n".join(f"- {f}" for f in related_facts)
                    try:
                        messages = [
                            {"role": "system", "content": "你是小说分析专家。分析给定节点是否是一个伏笔（foreshadowing），以及该伏笔是否已被回收（resolved）。返回JSON：{\"is_foreshadow\": bool, \"is_resolved\": bool, \"reason\": \"分析原因\"}"},
                            {"role": "user", "content": f"节点：{name}（{ntype}）\n相关描述：\n{facts_text}"}
                        ]
                        result = llm.chat_json(messages=messages, temperature=0.1, max_tokens=1024, disable_thinking=True)
                        if result.get("is_foreshadow") and not result.get("is_resolved"):
                            foreshadows.append({
                                "name": name,
                                "type": ntype,
                                "uuid": nid,
                                "description": result.get("reason", "未回收的伏笔"),
                                "related_facts": related_facts,
                                "edge_count": count
                            })
                    except Exception:
                        # LLM 判断失败，作为疑似伏笔
                        foreshadows.append({
                            "name": name,
                            "type": ntype,
                            "uuid": nid,
                            "description": f"节点「{name}」关联度低（{count}条边），可能是未回收的伏笔",
                            "related_facts": related_facts,
                            "edge_count": count
                        })

        return jsonify({
            "success": True,
            "data": {
                "foreshadows": foreshadows,
                "total": len(foreshadows)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 角色一致性检测接口（向量+图谱） ==============

@graph_bp.route('/character/consistency', methods=['POST'])
def check_character_consistency():
    """角色一致性检测：向量找同一角色的所有描述，LLM 比对矛盾"""
    try:
        data = request.get_json(force=True)
        graph_id = data.get('graph_id')
        character_name = data.get('character_name', '').strip()
        if not graph_id:
            return jsonify({"success": False, "error": "缺少 graph_id"}), 400

        from ..storage.neo4j_storage import Neo4jStorage
        from ..utils.llm_client import LLMClient

        storage = Neo4jStorage()
        llm = LLMClient()

        all_nodes = storage.get_all_nodes(graph_id)
        all_edges = storage.get_all_edges(graph_id)

        # 如果指定了角色名，只检测该角色；否则检测所有角色
        char_labels = {"Person", "Character", "Miss", "YoungMaster", "Madam",
                       "Master", "HousekeeperMadam", "Maid", "YoungLady"}

        target_nodes = []
        for node in all_nodes:
            labels = node.get("labels", [])
            if not any(l in char_labels for l in labels):
                continue
            if character_name and node.get("name", "") != character_name:
                continue
            target_nodes.append(node)

        results = []
        for node in target_nodes:
            uuid = node.get("uuid", "")
            name = node.get("name", "Unknown")

            # 收集该角色的所有 facts
            facts = []
            for e in all_edges:
                if e.get("source_node_uuid") == uuid or e.get("target_node_uuid") == uuid:
                    fact = e.get("fact", "")
                    if fact:
                        facts.append(fact)

            if len(facts) < 2:
                continue

            # 用 LLM 检测矛盾
            facts_text = "\n".join(f"- {f}" for f in facts)
            try:
                messages = [
                    {"role": "system", "content": "你是小说逻辑检测专家。分析给定角色的所有描述，找出互相矛盾的描述。返回JSON：{\"contradictions\": [{\"attribute\": \"矛盾属性\", \"desc\": \"矛盾描述\", \"facts\": [\"fact1\", \"fact2\"]}], \"summary\": \"整体一致性评价\"}"},
                    {"role": "user", "content": f"角色：{name}\n相关描述：\n{facts_text}"}
                ]
                result = llm.chat_json(messages=messages, temperature=0.1, max_tokens=2048, disable_thinking=True)
                results.append({
                    "character": name,
                    "uuid": uuid,
                    "contradictions": result.get("contradictions", []),
                    "summary": result.get("summary", ""),
                    "fact_count": len(facts)
                })
            except Exception as e:
                results.append({
                    "character": name,
                    "uuid": uuid,
                    "contradictions": [],
                    "summary": f"检测失败: {e}",
                    "fact_count": len(facts)
                })

        return jsonify({
            "success": True,
            "data": {
                "results": results,
                "total": len(results)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ============== 相似情节检测接口（向量） ==============

@graph_bp.route('/similarity/detect', methods=['POST'])
def detect_similarity():
    """相似情节/重复表达检测：向量找语义重复的场景和表达"""
    try:
        data = request.get_json(force=True)
        graph_id = data.get('graph_id')
        threshold = data.get('threshold', 0.85)
        if not graph_id:
            return jsonify({"success": False, "error": "缺少 graph_id"}), 400

        from ..storage.neo4j_storage import Neo4jStorage

        storage = Neo4jStorage()

        # 直接从 Neo4j 查询带 fact_embedding 的边（get_all_edges 会 pop 掉 embedding）
        with storage._driver.session() as session:
            result = session.run(
                """
                MATCH ()-[r:RELATION {graph_id: $gid}]->()
                WHERE r.fact IS NOT NULL AND r.fact_embedding IS NOT NULL
                RETURN r.fact AS fact, r.fact_embedding AS emb, r.uuid AS uuid
                """,
                gid=graph_id,
            )
            facts_with_emb = []
            for record in result:
                fact = record["fact"] or ""
                emb = record["emb"] or []
                if fact and emb:
                    facts_with_emb.append({"fact": fact, "embedding": emb, "uuid": record["uuid"] or ""})

        if len(facts_with_emb) < 2:
            return jsonify({
                "success": True,
                "data": {"similar_pairs": [], "total": 0, "message": "边数不足，无法检测相似性"}
            })

        # 计算两两相似度
        import math
        similar_pairs = []
        for i in range(len(facts_with_emb)):
            for j in range(i + 1, len(facts_with_emb)):
                emb1 = facts_with_emb[i]["embedding"]
                emb2 = facts_with_emb[j]["embedding"]
                if not emb1 or not emb2 or len(emb1) != len(emb2):
                    continue
                # 余弦相似度
                dot = sum(a * b for a, b in zip(emb1, emb2))
                norm1 = math.sqrt(sum(a * a for a in emb1))
                norm2 = math.sqrt(sum(b * b for b in emb2))
                if norm1 == 0 or norm2 == 0:
                    continue
                sim = dot / (norm1 * norm2)
                if sim >= threshold:
                    similar_pairs.append({
                        "fact1": facts_with_emb[i]["fact"],
                        "fact2": facts_with_emb[j]["fact"],
                        "similarity": round(sim, 4)
                    })

        similar_pairs.sort(key=lambda x: x["similarity"], reverse=True)

        return jsonify({
            "success": True,
            "data": {
                "similar_pairs": similar_pairs[:20],
                "total": len(similar_pairs),
                "threshold": threshold
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
