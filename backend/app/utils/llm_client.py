"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        is_json_model: bool = False,
    ):
        """
        初始化LLM客户端

        Args:
            api_key: API密钥，默认从配置读取
            base_url: API地址，默认从配置读取
            model: 模型名称，默认从配置读取
            is_json_model: 是否为JSON结构化输出专用客户端
                          True 时使用 JSON_LLM_* 配置
                          False 时使用主 LLM_* 配置
        """
        if is_json_model:
            self.api_key = api_key or Config.JSON_LLM_API_KEY
            self.base_url = base_url or Config.JSON_LLM_BASE_URL
            self.model = model or Config.JSON_LLM_MODEL_NAME
        else:
            self.api_key = api_key or Config.LLM_API_KEY
            self.base_url = base_url or Config.LLM_BASE_URL
            self.model = model or Config.LLM_MODEL_NAME

        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None,
        disable_thinking: bool = False
    ) -> str:
        """发送聊天请求"""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            kwargs["response_format"] = response_format

        # 仅在显式请求时关闭思考模式（如 NER 提取）
        if disable_thinking:
            try:
                kwargs["extra_body"] = {"enable_thinking": False}
            except:
                pass

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        content = re.sub(r'<think>[\\s\\S]*?</think>', '', content).strip()
        return content

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        disable_thinking: bool = False
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON

        自动在system message中注入"JSON"关键词
        以满足 response_format=json_object 要求

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数

        Returns:
            解析后的JSON对象
        """
        # 检查是否已包含JSON关键词
        has_json_keyword = False
        json_keywords = ["json", "JSON", "Json"]
        for msg in messages:
            if msg.get("role") in ("system", "user") and msg.get("content"):
                if any(kw in msg["content"] for kw in json_keywords):
                    has_json_keyword = True
                    break

        modified_messages = list(messages)
        if not has_json_keyword:
            json_hint = "\\n\\n请输出纯 JSON 格式，不要包含其他文字。"
            found_system = False
            for i, msg in enumerate(modified_messages):
                if msg.get("role") == "system":
                    modified_messages[i] = dict(msg)
                    modified_messages[i]["content"] = msg["content"] + json_hint
                    found_system = True
                    break
            if not found_system:
                modified_messages.insert(0, {
                    "role": "system",
                    "content": "请输出纯 JSON 格式，不要包含其他文字。"
                })

        response = self.chat(
            messages=modified_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            disable_thinking=disable_thinking
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^`{3}(?:json)?\\s*\\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\\n?`{3}\\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            # DeepSeek JSON 模式偶尔返回空 content
            if not cleaned_response or len(cleaned_response) < 5:
                logger.warning("LLM 返回了空内容，重试中...")
                raise ValueError("LLM返回了空内容")
            
            # 尝试修复被截断的 JSON：补全未闭合的括号
            try:
                fixed = cleaned_response
                # 移除尾部不完整的 JSON 片段
                last_brace = fixed.rfind('}')
                last_bracket = fixed.rfind(']')
                if last_brace > 0 or last_bracket > 0:
                    # 找到最后一个完整闭合的位置
                    cut_pos = max(last_brace, last_bracket)
                    fixed = fixed[:cut_pos + 1]
                    # 补全外层括号
                    open_braces = fixed.count('{') - fixed.count('}')
                    open_brackets = fixed.count('[') - fixed.count(']')
                    if open_brackets > 0:
                        fixed += ']' * open_brackets
                    if open_braces > 0:
                        fixed += '}' * open_braces
                    return json.loads(fixed)
            except:
                pass
            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response[:200]}")